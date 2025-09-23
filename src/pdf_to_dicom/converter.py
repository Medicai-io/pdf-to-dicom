"""Core PDF to DICOM conversion functionality."""

from datetime import datetime
from typing import Optional
import io

import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import generate_uid, ExplicitVRLittleEndian
from pypdf import PdfReader


class InvalidPDFError(ValueError):
    """Raised when PDF file is invalid or corrupted."""
    pass


class DICOMCreationError(RuntimeError):
    """Raised when DICOM file creation fails."""
    pass


def convert_pdf_to_dicom(
    pdf_bytes: bytes,
    patient_name: str,
    patient_id: str,
    study_uid: Optional[str] = None,
    series_uid: Optional[str] = None,
    sop_uid: Optional[str] = None,
) -> bytes:
    """Convert PDF to DICOM Encapsulated PDF Storage.

    Args:
        pdf_bytes: PDF file as bytes
        patient_name: Patient name (required)
        patient_id: Patient ID (required)
        study_uid: Study Instance UID (optional, generated if not provided)
        series_uid: Series Instance UID (optional, generated if not provided)
        sop_uid: SOP Instance UID (optional, generated if not provided)

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
            pdf_bytes, patient_name, patient_id,
            study_uid, series_uid, sop_uid
        )

        # Convert to bytes
        output = io.BytesIO()
        ds.save_as(output, enforce_file_format=True)
        return output.getvalue()

    except InvalidPDFError:
        raise
    except Exception as e:
        raise DICOMCreationError(f"Failed to create DICOM file: {str(e)}")


def _validate_pdf(pdf_bytes: bytes) -> None:
    """Validate PDF format and constraints.

    Args:
        pdf_bytes: PDF file as bytes

    Raises:
        InvalidPDFError: If PDF is invalid
    """
    # Check size limit (100MB)
    if len(pdf_bytes) > 100 * 1024 * 1024:
        raise InvalidPDFError("PDF file too large (max 100MB)")

    # Check minimum size
    if len(pdf_bytes) < 100:
        raise InvalidPDFError("PDF file too small or corrupted")

    # Check PDF magic bytes
    if not pdf_bytes.startswith(b'%PDF'):
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


def _create_dicom_dataset(
    pdf_bytes: bytes,
    patient_name: str,
    patient_id: str,
    study_uid: str,
    series_uid: str,
    sop_uid: str
) -> Dataset:
    """Create DICOM Encapsulated PDF Storage dataset.

    Args:
        pdf_bytes: PDF file as bytes
        patient_name: Patient name
        patient_id: Patient ID
        study_uid: Study Instance UID
        series_uid: Series Instance UID
        sop_uid: SOP Instance UID

    Returns:
        DICOM Dataset
    """
    # Create File Meta Information
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.104.1"
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()
    file_meta.ImplementationVersionName = "pdf-to-dicom 0.1.0"

    # Create main dataset
    ds = Dataset()
    ds.file_meta = file_meta

    # SOP Class and Instance
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.104.1"  # Encapsulated PDF Storage
    ds.SOPInstanceUID = sop_uid

    # Patient Module
    ds.PatientName = patient_name
    ds.PatientID = patient_id

    # Study Module
    ds.StudyInstanceUID = study_uid
    now = datetime.now()
    ds.StudyDate = now.strftime("%Y%m%d")
    ds.StudyTime = now.strftime("%H%M%S")
    ds.StudyID = "1"

    # Series Module
    ds.SeriesInstanceUID = series_uid
    ds.SeriesNumber = 1
    ds.Modality = "DOC"

    # Equipment Module
    ds.Manufacturer = "medicai-pdf-to-dicom"
    ds.ManufacturerModelName = "PDF to DICOM Converter"
    ds.SoftwareVersions = "0.1.0"

    # Encapsulated Document Module
    ds.MIMETypeOfEncapsulatedDocument = "application/pdf"
    ds.EncapsulatedDocument = pdf_bytes

    # General Image Module (required for some viewers)
    ds.InstanceNumber = 1
    ds.ContentDate = ds.StudyDate
    ds.ContentTime = ds.StudyTime

    return ds