"""Core conversion logic: PDF -> DICOM encapsulation and DICOM -> PDF extraction."""

import io
from datetime import datetime
from typing import NamedTuple, Optional

import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.errors import InvalidDicomError
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from pypdf import PdfReader

ENCAPSULATED_PDF_SOP_CLASS_UID = "1.2.840.10008.5.1.4.1.1.104.1"

MAX_PDF_SIZE_BYTES = 100 * 1024 * 1024
# A 100MB PDF wrapped in DICOM exceeds 100MB (tags + preamble + padding), so the
# DICOM limit gets headroom — otherwise we'd reject files this service produced.
MAX_DICOM_SIZE_BYTES = MAX_PDF_SIZE_BYTES + 1024 * 1024


class InvalidPDFError(ValueError):
    """Raised when PDF file is invalid or corrupted."""

    pass


class DICOMCreationError(RuntimeError):
    """Raised when DICOM file creation fails."""

    pass


class InvalidDICOMError(ValueError):
    """Raised when DICOM file is invalid or contains no extractable PDF."""

    pass


class PDFExtractionError(RuntimeError):
    """Raised when PDF extraction from DICOM fails unexpectedly."""

    pass


class ExtractionResult(NamedTuple):
    """Result of extracting a PDF from a DICOM Encapsulated PDF object."""

    pdf_bytes: bytes
    patient_id: str
    study_instance_uid: str
    sop_instance_uid: str


def convert_pdf_to_dicom(
    pdf_bytes: bytes,
    patient_name: str,
    patient_id: str,
    study_uid: Optional[str] = None,
    series_uid: Optional[str] = None,
    sop_uid: Optional[str] = None,
    study_description: Optional[str] = None,
    series_description: Optional[str] = None,
    series_number: Optional[int] = None,
    study_date: Optional[str] = None,
    study_time: Optional[str] = None,
    study_id: Optional[str] = None,
    accession_number: Optional[str] = None,
) -> bytes:
    """Convert PDF to DICOM Encapsulated PDF Storage.

    Args:
        pdf_bytes: PDF file as bytes
        patient_name: Patient name (required)
        patient_id: Patient ID (required)
        study_uid: Study Instance UID (optional, generated if not provided)
        series_uid: Series Instance UID (optional, generated if not provided)
        sop_uid: SOP Instance UID (optional, generated if not provided)
        study_description: Study description (optional)
        series_description: Series description (optional)
        series_number: Series number for viewer ordering (optional, defaults to 1)
        study_date: Study date in YYYYMMDD format (optional, defaults to now)
        study_time: Study time in HHMMSS format (optional, defaults to now)
        study_id: Study ID (optional, defaults to "1")
        accession_number: Accession number for study grouping (optional)

    Returns:
        DICOM file as bytes

    Raises:
        InvalidPDFError: If PDF is invalid or metadata is missing
        DICOMCreationError: If DICOM creation fails
    """
    try:
        # Validate PDF format and content
        _validate_pdf(pdf_bytes)

        # Validate required metadata
        if not patient_name or not patient_id:
            raise InvalidPDFError("Patient name and ID are required")

        # Generate UIDs if not provided
        study_uid = study_uid or generate_uid()
        series_uid = series_uid or generate_uid()
        sop_uid = sop_uid or generate_uid()

        # Create DICOM dataset
        ds = _create_dicom_dataset(
            pdf_bytes=pdf_bytes,
            patient_name=patient_name,
            patient_id=patient_id,
            study_uid=study_uid,
            series_uid=series_uid,
            sop_uid=sop_uid,
            study_description=study_description,
            series_description=series_description,
            series_number=series_number,
            study_date=study_date,
            study_time=study_time,
            study_id=study_id,
            accession_number=accession_number,
        )

        # Convert to bytes
        output = io.BytesIO()
        ds.save_as(output, enforce_file_format=True)
        return output.getvalue()

    except InvalidPDFError:
        raise
    except Exception as e:
        raise DICOMCreationError(f"Failed to create DICOM file: {str(e)}")


def extract_pdf_from_dicom(dicom_bytes: bytes) -> ExtractionResult:
    """Extract the embedded PDF from a DICOM Encapsulated PDF Storage object.

    Args:
        dicom_bytes: DICOM file as bytes

    Returns:
        ExtractionResult with the PDF bytes and identifying attributes
        (empty strings for attributes absent in the dataset)

    Raises:
        InvalidDICOMError: If the DICOM is invalid or contains no valid PDF
        PDFExtractionError: If extraction fails unexpectedly
    """
    try:
        ds = _validate_dicom(dicom_bytes)

        # pydicom reads an empty OB element back as None
        pdf_bytes = bytes(ds.EncapsulatedDocument or b"")

        # Recover the exact payload: honor a plausible declared length, otherwise
        # strip the single OB even-length padding byte pydicom keeps. A missing or
        # empty length element falls through to the heuristic.
        declared_length = int(ds.get("EncapsulatedDocumentLength") or 0)
        if 0 < declared_length <= len(pdf_bytes):
            pdf_bytes = pdf_bytes[:declared_length]
        elif pdf_bytes.endswith(b"\x00"):
            pdf_bytes = pdf_bytes[:-1]

        # Never emit a PDF this service wouldn't itself accept on the encode side
        try:
            _validate_pdf(pdf_bytes)
        except InvalidPDFError as e:
            raise InvalidDICOMError(f"Encapsulated PDF is corrupted: {str(e)}")

        return ExtractionResult(
            pdf_bytes=pdf_bytes,
            patient_id=str(ds.get("PatientID", "")),
            study_instance_uid=str(ds.get("StudyInstanceUID", "")),
            sop_instance_uid=str(ds.get("SOPInstanceUID", "")),
        )

    except InvalidDICOMError:
        raise
    except Exception as e:
        raise PDFExtractionError(f"Failed to extract PDF from DICOM: {str(e)}")


def _validate_pdf(pdf_bytes: bytes) -> None:
    """Validate PDF format and constraints.

    Args:
        pdf_bytes: PDF file as bytes

    Raises:
        InvalidPDFError: If PDF is invalid
    """
    # Check size limit (100MB)
    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        raise InvalidPDFError("PDF file too large (max 100MB)")

    # Check minimum size
    if len(pdf_bytes) < 100:
        raise InvalidPDFError("PDF file too small or corrupted")

    # Check PDF magic bytes
    if not pdf_bytes.startswith(b"%PDF"):
        raise InvalidPDFError("Not a valid PDF file")

    # Try to parse PDF with pypdf
    try:
        pdf_stream = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_stream)

        # Verify we can read at least one page
        if len(reader.pages) == 0:
            raise InvalidPDFError("PDF contains no pages")

    except Exception as e:
        raise InvalidPDFError(f"PDF file is corrupted or invalid: {str(e)}")


def _validate_dicom(dicom_bytes: bytes) -> Dataset:
    """Validate DICOM format and Encapsulated PDF structure.

    Args:
        dicom_bytes: DICOM file as bytes

    Returns:
        Parsed DICOM dataset

    Raises:
        InvalidDICOMError: If the DICOM is invalid or not an Encapsulated PDF
    """
    # Check size limit (101MB — see MAX_DICOM_SIZE_BYTES)
    if len(dicom_bytes) > MAX_DICOM_SIZE_BYTES:
        raise InvalidDICOMError("DICOM file too large (max 101MB)")

    # Check minimum size (128-byte preamble + "DICM" marker)
    if len(dicom_bytes) < 132:
        raise InvalidDICOMError("DICOM file too small or corrupted")

    # Parse with pydicom; force=False rejects non-Part-10 input cleanly
    try:
        ds = pydicom.dcmread(io.BytesIO(dicom_bytes), force=False)
    except InvalidDicomError:
        raise InvalidDICOMError("Not a valid DICOM file (missing DICM header)")
    except Exception as e:
        raise InvalidDICOMError(f"DICOM file is corrupted or invalid: {str(e)}")

    # Verify SOP class (missing vs wrong are different failures)
    sop_class_uid = str(ds.get("SOPClassUID", ""))
    if not sop_class_uid:
        raise InvalidDICOMError("DICOM file has no SOPClassUID")
    if sop_class_uid != ENCAPSULATED_PDF_SOP_CLASS_UID:
        raise InvalidDICOMError(
            f"Not an Encapsulated PDF object (SOPClassUID: {sop_class_uid})"
        )

    # Verify the embedded document exists
    if "EncapsulatedDocument" not in ds:
        raise InvalidDICOMError("DICOM file has no EncapsulatedDocument element")

    # MIME type: strict on contradiction, lenient on omission (the %PDF magic
    # check on the payload is the authoritative guard)
    if "MIMETypeOfEncapsulatedDocument" in ds:
        mime_type = str(ds.MIMETypeOfEncapsulatedDocument).strip().lower()
        if mime_type != "application/pdf":
            raise InvalidDICOMError(
                f"Encapsulated document is not PDF (MIME type: {mime_type})"
            )

    return ds


def _create_dicom_dataset(
    pdf_bytes: bytes,
    patient_name: str,
    patient_id: str,
    study_uid: str,
    series_uid: str,
    sop_uid: str,
    study_description: Optional[str] = None,
    series_description: Optional[str] = None,
    series_number: Optional[int] = None,
    study_date: Optional[str] = None,
    study_time: Optional[str] = None,
    study_id: Optional[str] = None,
    accession_number: Optional[str] = None,
) -> Dataset:
    """Create DICOM Encapsulated PDF Storage dataset.

    Args:
        pdf_bytes: PDF file as bytes
        patient_name: Patient name
        patient_id: Patient ID
        study_uid: Study Instance UID
        series_uid: Series Instance UID
        sop_uid: SOP Instance UID
        study_description: Study description (optional)
        series_description: Series description (optional)
        series_number: Series number for viewer ordering (optional, defaults to 1)
        study_date: Study date in YYYYMMDD format (optional, defaults to now)
        study_time: Study time in HHMMSS format (optional, defaults to now)
        study_id: Study ID (optional, defaults to "1")
        accession_number: Accession number for study grouping (optional)

    Returns:
        DICOM Dataset
    """
    # Create File Meta Information
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = ENCAPSULATED_PDF_SOP_CLASS_UID  # type: ignore
    file_meta.MediaStorageSOPInstanceUID = sop_uid  # type: ignore
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()
    file_meta.ImplementationVersionName = "dicom-pdf 0.2.0"

    # Create main dataset. UTF-8 charset so non-ASCII patient names (diacritics)
    # survive instead of being replaced with '?' by the default ISO-IR 6.
    ds = Dataset()
    ds.file_meta = file_meta
    ds.SpecificCharacterSet = "ISO_IR 192"

    # SOP Class and Instance
    ds.SOPClassUID = ENCAPSULATED_PDF_SOP_CLASS_UID  # Encapsulated PDF Storage
    ds.SOPInstanceUID = sop_uid

    # Patient Module
    ds.PatientName = patient_name
    ds.PatientID = patient_id

    # Study Module
    ds.StudyInstanceUID = study_uid
    now = datetime.now()
    ds.StudyDate = study_date or now.strftime("%Y%m%d")
    ds.StudyTime = study_time or now.strftime("%H%M%S")
    ds.StudyID = study_id or "1"
    if accession_number:
        ds.AccessionNumber = accession_number
    if study_description:
        ds.StudyDescription = study_description

    # Series Module
    ds.SeriesInstanceUID = series_uid
    ds.SeriesNumber = series_number if series_number is not None else 1
    ds.Modality = "DOC"
    if series_description:
        ds.SeriesDescription = series_description

    # Equipment Module
    ds.Manufacturer = "medicai-dicom-pdf"
    ds.ManufacturerModelName = "DICOM PDF Converter"
    ds.SoftwareVersions = "0.2.0"

    # Encapsulated Document Module. The exact length lets decoders recover the
    # payload without relying on the OB even-length padding heuristic.
    ds.MIMETypeOfEncapsulatedDocument = "application/pdf"
    ds.EncapsulatedDocument = pdf_bytes
    ds.EncapsulatedDocumentLength = len(pdf_bytes)

    # General Image Module (required for some viewers)
    ds.InstanceNumber = 1
    ds.ContentDate = ds.StudyDate
    ds.ContentTime = ds.StudyTime

    return ds
