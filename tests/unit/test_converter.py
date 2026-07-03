"""Unit tests for the PDF <-> DICOM converter functionality."""

import io
from pathlib import Path

import pydicom
import pytest
from pypdf import PdfReader

from dicom_pdf.converter import (
    MAX_DICOM_SIZE_BYTES,
    DICOMCreationError,
    InvalidDICOMError,
    InvalidPDFError,
    PDFExtractionError,
    _create_dicom_dataset,
    _validate_dicom,
    _validate_pdf,
    convert_pdf_to_dicom,
    extract_pdf_from_dicom,
)

# Test data paths
FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures"
SAMPLE_PDF = FIXTURES_PATH / "radiology_report.pdf"
CORRUPTED_PDF = FIXTURES_PATH / "corrupted.pdf"
SAMPLE_DICOM = FIXTURES_PATH / "encapsulated_report.dcm"

CT_IMAGE_SOP = "1.2.840.10008.5.1.4.1.1.2"


class TestPDFValidation:
    """Test PDF validation functionality."""

    def test_validate_valid_pdf(self):
        """Test validation with a valid PDF file."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        # Should not raise any exception
        _validate_pdf(pdf_bytes)

    def test_validate_corrupted_pdf(self):
        """Test validation with corrupted PDF file."""
        with open(CORRUPTED_PDF, "rb") as f:
            pdf_bytes = f.read()

        with pytest.raises(InvalidPDFError, match="Not a valid PDF file"):
            _validate_pdf(pdf_bytes)

    def test_validate_empty_pdf(self):
        """Test validation with empty PDF."""
        with pytest.raises(InvalidPDFError, match="PDF file too small"):
            _validate_pdf(b"")

    def test_validate_large_pdf(self):
        """Test validation with oversized PDF."""
        # Create a fake large PDF (over 100MB)
        large_pdf = b"%PDF-1.4" + b"x" * (101 * 1024 * 1024)

        with pytest.raises(InvalidPDFError, match="PDF file too large"):
            _validate_pdf(large_pdf)

    def test_validate_invalid_magic_bytes(self):
        """Test validation with invalid PDF magic bytes."""
        invalid_pdf = b"NOT_PDF" + b"x" * 1000

        with pytest.raises(InvalidPDFError, match="Not a valid PDF file"):
            _validate_pdf(invalid_pdf)

    def test_validate_zero_page_pdf(self):
        """Test validation rejects a structurally valid PDF with no pages."""
        zero_page_pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
            b"xref\n0 3\n0000000000 65535 f \n"
            b"0000000009 00000 n \n0000000052 00000 n \n"
            b"trailer<</Size 3/Root 1 0 R>>\nstartxref\n96\n%%EOF\n"
        )

        with pytest.raises(InvalidPDFError, match="PDF contains no pages"):
            _validate_pdf(zero_page_pdf)


class TestDICOMValidation:
    """Test DICOM validation for the extraction path."""

    def test_validate_valid_dicom(self):
        """Test validation with the committed Encapsulated PDF fixture."""
        with open(SAMPLE_DICOM, "rb") as f:
            dicom_bytes = f.read()

        ds = _validate_dicom(dicom_bytes)
        assert ds.SOPClassUID == "1.2.840.10008.5.1.4.1.1.104.1"

    def test_validate_empty_dicom(self):
        """Test validation with empty input."""
        with pytest.raises(InvalidDICOMError, match="DICOM file too small"):
            _validate_dicom(b"")

    def test_validate_oversized_dicom(self):
        """Test validation with oversized DICOM."""
        large_dicom = b"x" * (MAX_DICOM_SIZE_BYTES + 1)

        with pytest.raises(InvalidDICOMError, match="DICOM file too large"):
            _validate_dicom(large_dicom)

    def test_validate_not_dicom(self):
        """Test validation with bytes that are not DICOM."""
        not_dicom = b"this is definitely not a dicom file " * 10

        with pytest.raises(InvalidDICOMError, match="Not a valid DICOM file"):
            _validate_dicom(not_dicom)

    def test_validate_wrong_sop_class(self, build_dicom_bytes):
        """Test validation rejects a non Encapsulated PDF object (e.g. CT)."""
        dicom_bytes = build_dicom_bytes(sop_class_uid=CT_IMAGE_SOP)

        with pytest.raises(InvalidDICOMError, match="Not an Encapsulated PDF object"):
            _validate_dicom(dicom_bytes)

    def test_validate_missing_sop_class(self, build_dicom_bytes):
        """Test validation rejects a dataset without SOPClassUID."""
        dicom_bytes = build_dicom_bytes(sop_class_uid=None)

        with pytest.raises(InvalidDICOMError, match="no SOPClassUID"):
            _validate_dicom(dicom_bytes)

    def test_validate_missing_encapsulated_document(self, build_dicom_bytes):
        """Test validation rejects a dataset without EncapsulatedDocument."""
        dicom_bytes = build_dicom_bytes(document=None)

        with pytest.raises(InvalidDICOMError, match="no EncapsulatedDocument"):
            _validate_dicom(dicom_bytes)

    def test_validate_wrong_mime_type(self, build_dicom_bytes):
        """Test validation rejects a contradicting MIME type."""
        dicom_bytes = build_dicom_bytes(mime_type="text/xml")

        with pytest.raises(InvalidDICOMError, match="not PDF"):
            _validate_dicom(dicom_bytes)

    def test_validate_missing_mime_type_allowed(self, build_dicom_bytes):
        """Test validation tolerates an absent MIME type element."""
        dicom_bytes = build_dicom_bytes(mime_type=None)

        # Should not raise — the %PDF magic check on the payload is authoritative
        ds = _validate_dicom(dicom_bytes)
        assert "MIMETypeOfEncapsulatedDocument" not in ds


class TestExtractPDFFromDICOM:
    """Test the PDF extraction function."""

    def test_extract_from_fixture(self):
        """Test extraction from the committed fixture."""
        with open(SAMPLE_DICOM, "rb") as f:
            dicom_bytes = f.read()

        result = extract_pdf_from_dicom(dicom_bytes)

        assert result.pdf_bytes.startswith(b"%PDF")
        assert result.patient_id == "12345"
        assert result.study_instance_uid == "1.2.3.4.5.6.7.8.9"
        assert result.sop_instance_uid == "1.2.3.4.5.6.7.8.11"

        # Extracted PDF must be readable
        assert len(PdfReader(io.BytesIO(result.pdf_bytes)).pages) > 0

    def test_extract_strips_padding(self, build_dicom_bytes):
        """Test the OB even-length pad is stripped when no length is declared."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        # The sample PDF is odd-length, so DICOM pads it — extraction must undo that
        assert len(pdf_bytes) % 2 == 1
        dicom_bytes = build_dicom_bytes(document=pdf_bytes)

        result = extract_pdf_from_dicom(dicom_bytes)
        assert result.pdf_bytes == pdf_bytes
        assert not result.pdf_bytes.endswith(b"\x00")

    def test_extract_non_pdf_payload(self, build_dicom_bytes):
        """Test extraction fails when the embedded document is not a PDF."""
        dicom_bytes = build_dicom_bytes(document=b"NOT A PDF " * 20)

        with pytest.raises(InvalidDICOMError, match="Encapsulated PDF is corrupted"):
            extract_pdf_from_dicom(dicom_bytes)

    def test_extract_empty_document(self, build_dicom_bytes):
        """Test extraction fails when the embedded document is empty."""
        dicom_bytes = build_dicom_bytes(document=b"")

        with pytest.raises(InvalidDICOMError, match="Encapsulated PDF is corrupted"):
            extract_pdf_from_dicom(dicom_bytes)

    def test_extract_corrupted_embedded_pdf(self, build_dicom_bytes):
        """Test extraction fails when the embedded PDF is corrupted."""
        dicom_bytes = build_dicom_bytes(document=b"%PDF-1.4 garbage " + b"x" * 200)

        with pytest.raises(InvalidDICOMError, match="Encapsulated PDF is corrupted"):
            extract_pdf_from_dicom(dicom_bytes)

    def test_extract_missing_patient_id(self, build_dicom_bytes):
        """Test extraction returns empty strings for absent attributes."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()
        dicom_bytes = build_dicom_bytes(document=pdf_bytes, patient_id=None)

        result = extract_pdf_from_dicom(dicom_bytes)
        assert result.patient_id == ""

    def test_extract_honors_declared_document_length(self, build_dicom_bytes):
        """Test EncapsulatedDocumentLength is used to recover the exact payload."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()
        dicom_bytes = build_dicom_bytes(
            document=pdf_bytes, declared_length=len(pdf_bytes)
        )

        result = extract_pdf_from_dicom(dicom_bytes)
        assert result.pdf_bytes == pdf_bytes

    def test_extract_falls_back_on_bad_declared_length(self, build_dicom_bytes):
        """Test an implausible declared length falls back to the pad heuristic."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()
        dicom_bytes = build_dicom_bytes(
            document=pdf_bytes, declared_length=len(pdf_bytes) + 1000
        )

        result = extract_pdf_from_dicom(dicom_bytes)
        assert result.pdf_bytes == pdf_bytes

    def test_extract_falls_back_on_empty_declared_length(self):
        """Test a present-but-empty length element degrades to the heuristic."""
        from pydicom.dataset import Dataset, FileMetaDataset
        from pydicom.uid import ExplicitVRLittleEndian

        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.104.1"
        file_meta.MediaStorageSOPInstanceUID = "1.2.3"
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = Dataset()
        ds.file_meta = file_meta
        ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.104.1"
        ds.SOPInstanceUID = "1.2.3"
        ds.MIMETypeOfEncapsulatedDocument = "application/pdf"
        ds.EncapsulatedDocument = pdf_bytes
        ds.add_new(0x00420015, "IS", None)  # empty EncapsulatedDocumentLength
        output = io.BytesIO()
        ds.save_as(output, enforce_file_format=True)

        result = extract_pdf_from_dicom(output.getvalue())
        assert result.pdf_bytes == pdf_bytes

    def test_extract_from_implicit_vr_reencode(self):
        """Test extraction from a file re-encoded with Implicit VR (PACS do this)."""
        from pydicom.uid import ImplicitVRLittleEndian

        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()
        with open(SAMPLE_DICOM, "rb") as f:
            ds = pydicom.dcmread(io.BytesIO(f.read()))
        ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
        output = io.BytesIO()
        ds.save_as(output, enforce_file_format=True)

        result = extract_pdf_from_dicom(output.getvalue())
        assert result.pdf_bytes == pdf_bytes


class TestRoundTrip:
    """Test that extraction is the exact inverse of conversion."""

    def test_round_trip_odd_length_pdf(self):
        """Test byte-identical round-trip with an odd-length PDF (padded)."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()
        assert len(pdf_bytes) % 2 == 1

        dicom_bytes = convert_pdf_to_dicom(
            pdf_bytes=pdf_bytes, patient_name="Doe^John", patient_id="12345"
        )
        result = extract_pdf_from_dicom(dicom_bytes)
        assert result.pdf_bytes == pdf_bytes

    def test_round_trip_even_length_pdf(self):
        """Test byte-identical round-trip with an even-length PDF (no padding)."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read() + b"\n"
        assert len(pdf_bytes) % 2 == 0

        dicom_bytes = convert_pdf_to_dicom(
            pdf_bytes=pdf_bytes, patient_name="Doe^John", patient_id="12345"
        )
        result = extract_pdf_from_dicom(dicom_bytes)
        assert result.pdf_bytes == pdf_bytes

    def test_round_trip_pdf_ending_in_null_byte(self):
        """Test a PDF whose last byte is a legit 0x00 survives the round-trip.

        The declared EncapsulatedDocumentLength protects the trailing byte from
        being mistaken for OB padding.
        """
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read() + b"\x00"
        assert len(pdf_bytes) % 2 == 0

        dicom_bytes = convert_pdf_to_dicom(
            pdf_bytes=pdf_bytes, patient_name="Doe^John", patient_id="12345"
        )
        result = extract_pdf_from_dicom(dicom_bytes)
        assert result.pdf_bytes == pdf_bytes

    def test_round_trip_unicode_patient_name(self):
        """Test non-ASCII patient names survive encoding (UTF-8 charset)."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        dicom_bytes = convert_pdf_to_dicom(
            pdf_bytes=pdf_bytes, patient_name="Popescu^Ștefan", patient_id="RO123"
        )
        ds = pydicom.dcmread(io.BytesIO(dicom_bytes))
        assert str(ds.PatientName) == "Popescu^Ștefan"
        assert ds.SpecificCharacterSet == "ISO_IR 192"


class TestDICOMCreation:
    """Test DICOM dataset creation."""

    def test_create_dicom_dataset_basic(self):
        """Test basic DICOM dataset creation."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        ds = _create_dicom_dataset(
            pdf_bytes=pdf_bytes,
            patient_name="Doe^John",
            patient_id="12345",
            study_uid="1.2.3.4.5.6.7.8.9",
            series_uid="1.2.3.4.5.6.7.8.10",
            sop_uid="1.2.3.4.5.6.7.8.11",
        )

        # Verify SOP Class
        assert ds.SOPClassUID == "1.2.840.10008.5.1.4.1.1.104.1"
        assert ds.SOPInstanceUID == "1.2.3.4.5.6.7.8.11"

        # Verify Patient Module
        assert ds.PatientName == "Doe^John"
        assert ds.PatientID == "12345"

        # Verify Study Module
        assert ds.StudyInstanceUID == "1.2.3.4.5.6.7.8.9"
        assert hasattr(ds, "StudyDate")
        assert hasattr(ds, "StudyTime")

        # Verify Series Module
        assert ds.SeriesInstanceUID == "1.2.3.4.5.6.7.8.10"
        assert ds.SeriesNumber == 1
        assert ds.Modality == "DOC"

        # Verify Equipment Module
        assert ds.Manufacturer == "medicai-dicom-pdf"
        assert ds.ManufacturerModelName == "DICOM PDF Converter"

        # Verify Encapsulated Document Module
        assert ds.MIMETypeOfEncapsulatedDocument == "application/pdf"
        assert ds.EncapsulatedDocument == pdf_bytes
        assert ds.EncapsulatedDocumentLength == len(pdf_bytes)

    def test_create_dicom_dataset_defaults(self):
        """Test optional study fields keep the historical defaults when absent."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        ds = _create_dicom_dataset(
            pdf_bytes=pdf_bytes,
            patient_name="Doe^John",
            patient_id="12345",
            study_uid="1.2.3.4.5.6.7.8.9",
            series_uid="1.2.3.4.5.6.7.8.10",
            sop_uid="1.2.3.4.5.6.7.8.11",
        )

        assert ds.SeriesNumber == 1
        assert ds.StudyID == "1"
        assert "StudyDescription" not in ds
        assert "SeriesDescription" not in ds
        assert "AccessionNumber" not in ds

    def test_create_dicom_dataset_with_optional_study_fields(self):
        """Test all optional study fields are written when provided."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        ds = _create_dicom_dataset(
            pdf_bytes=pdf_bytes,
            patient_name="Doe^John",
            patient_id="12345",
            study_uid="1.2.3.4.5.6.7.8.9",
            series_uid="1.2.3.4.5.6.7.8.10",
            sop_uid="1.2.3.4.5.6.7.8.11",
            study_description="Radiology Report Review",
            series_description="PDF Documents",
            series_number=999,
            study_date="20240315",
            study_time="143000",
            study_id="RAD2024003",
            accession_number="ACC-2024-001",
        )

        assert ds.StudyDescription == "Radiology Report Review"
        assert ds.SeriesDescription == "PDF Documents"
        assert ds.SeriesNumber == 999
        assert ds.StudyDate == "20240315"
        assert ds.StudyTime == "143000"
        assert ds.StudyID == "RAD2024003"
        assert ds.AccessionNumber == "ACC-2024-001"
        # Content date/time mirror the study date/time
        assert ds.ContentDate == "20240315"
        assert ds.ContentTime == "143000"


class TestConvertPDFToDICOM:
    """Test main conversion function."""

    def test_convert_with_valid_pdf_complete_metadata(self):
        """Test conversion with valid PDF and complete metadata."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        dicom_bytes = convert_pdf_to_dicom(
            pdf_bytes=pdf_bytes,
            patient_name="Doe^John",
            patient_id="12345",
            study_uid="1.2.3.4.5.6.7.8.9",
            series_uid="1.2.3.4.5.6.7.8.10",
            sop_uid="1.2.3.4.5.6.7.8.11",
        )

        # Verify we got bytes back
        assert isinstance(dicom_bytes, bytes)
        assert len(dicom_bytes) > 0

        # Verify we can read it as DICOM
        ds = pydicom.dcmread(io.BytesIO(dicom_bytes))
        assert ds.SOPClassUID == "1.2.840.10008.5.1.4.1.1.104.1"
        assert ds.PatientName == "Doe^John"
        assert ds.PatientID == "12345"

    def test_convert_with_minimal_metadata(self):
        """Test conversion with only required metadata (UIDs auto-generated)."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        dicom_bytes = convert_pdf_to_dicom(
            pdf_bytes=pdf_bytes, patient_name="Smith^Jane", patient_id="67890"
        )

        # Verify conversion succeeded
        assert isinstance(dicom_bytes, bytes)
        assert len(dicom_bytes) > 0

        # Verify DICOM content
        ds = pydicom.dcmread(io.BytesIO(dicom_bytes))
        assert ds.PatientName == "Smith^Jane"
        assert ds.PatientID == "67890"

        # Verify UIDs were generated
        assert ds.StudyInstanceUID.startswith("1.2.826.0.1.3680043.8.498.")
        assert ds.SeriesInstanceUID.startswith("1.2.826.0.1.3680043.8.498.")
        assert ds.SOPInstanceUID.startswith("1.2.826.0.1.3680043.8.498.")

    def test_convert_missing_patient_name(self):
        """Test conversion fails with missing patient name."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        with pytest.raises(InvalidPDFError, match="Patient name and ID are required"):
            convert_pdf_to_dicom(
                pdf_bytes=pdf_bytes, patient_name="", patient_id="12345"
            )

    def test_convert_missing_patient_id(self):
        """Test conversion fails with missing patient ID."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        with pytest.raises(InvalidPDFError, match="Patient name and ID are required"):
            convert_pdf_to_dicom(
                pdf_bytes=pdf_bytes, patient_name="Doe^John", patient_id=""
            )

    def test_convert_invalid_pdf(self):
        """Test conversion fails with invalid PDF."""
        with open(CORRUPTED_PDF, "rb") as f:
            pdf_bytes = f.read()

        with pytest.raises(InvalidPDFError):
            convert_pdf_to_dicom(
                pdf_bytes=pdf_bytes,
                patient_name="Doe^John",
                patient_id="12345",
            )

    def test_convert_oversized_pdf(self):
        """Test conversion fails with oversized PDF."""
        # Create fake oversized PDF
        large_pdf = b"%PDF-1.4" + b"x" * (101 * 1024 * 1024)

        with pytest.raises(InvalidPDFError, match="PDF file too large"):
            convert_pdf_to_dicom(
                pdf_bytes=large_pdf,
                patient_name="Doe^John",
                patient_id="12345",
            )


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_invalid_pdf_error_inheritance(self):
        """Test InvalidPDFError inherits from ValueError."""
        assert issubclass(InvalidPDFError, ValueError)

    def test_dicom_creation_error_inheritance(self):
        """Test DICOMCreationError inherits from RuntimeError."""
        assert issubclass(DICOMCreationError, RuntimeError)

    def test_invalid_dicom_error_inheritance(self):
        """Test InvalidDICOMError inherits from ValueError."""
        assert issubclass(InvalidDICOMError, ValueError)

    def test_pdf_extraction_error_inheritance(self):
        """Test PDFExtractionError inherits from RuntimeError."""
        assert issubclass(PDFExtractionError, RuntimeError)

    def test_unexpected_creation_failure_wrapped(self, monkeypatch):
        """Test unexpected failures during creation surface as DICOMCreationError."""
        import dicom_pdf.converter as converter_module

        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(converter_module, "_create_dicom_dataset", boom)
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        with pytest.raises(DICOMCreationError, match="Failed to create DICOM file"):
            convert_pdf_to_dicom(
                pdf_bytes=pdf_bytes, patient_name="Doe^John", patient_id="12345"
            )

    def test_unexpected_extraction_failure_wrapped(self, monkeypatch):
        """Test unexpected failures during extraction surface as PDFExtractionError."""
        import dicom_pdf.converter as converter_module

        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(converter_module, "_validate_pdf", boom)
        with open(SAMPLE_DICOM, "rb") as f:
            dicom_bytes = f.read()

        with pytest.raises(PDFExtractionError, match="Failed to extract PDF"):
            extract_pdf_from_dicom(dicom_bytes)

    def test_pdf_validation_error_messages(self):
        """Test PDF validation provides meaningful error messages."""
        # Test empty file
        with pytest.raises(InvalidPDFError) as exc_info:
            _validate_pdf(b"")
        assert "too small" in str(exc_info.value)

        # Test invalid format (larger than 100 bytes)
        long_text = (
            b"not a pdf file but long enough text to pass size validation, "
            b"needs to be over 100 bytes long and here is more text to make it "
            b"really long enough to trigger the right validation error path"
        )
        with pytest.raises(InvalidPDFError) as exc_info:
            _validate_pdf(long_text)
        assert "Not a valid PDF file" in str(exc_info.value)


@pytest.fixture
def sample_patient_data():
    """Fixture providing sample patient metadata."""
    return {
        "patient_name": "Test^Patient",
        "patient_id": "TEST123",
        "study_uid": "1.2.3.4.5.6.7.8.9",
        "series_uid": "1.2.3.4.5.6.7.8.10",
        "sop_uid": "1.2.3.4.5.6.7.8.11",
    }


def test_end_to_end_conversion(sample_patient_data):
    """Test complete end-to-end conversion process."""
    with open(SAMPLE_PDF, "rb") as f:
        pdf_bytes = f.read()

    # Convert PDF to DICOM
    dicom_bytes = convert_pdf_to_dicom(pdf_bytes=pdf_bytes, **sample_patient_data)

    # Verify the DICOM file
    ds = pydicom.dcmread(io.BytesIO(dicom_bytes))

    # Verify all metadata is preserved
    assert ds.PatientName == sample_patient_data["patient_name"]
    assert ds.PatientID == sample_patient_data["patient_id"]
    assert ds.StudyInstanceUID == sample_patient_data["study_uid"]
    assert ds.SeriesInstanceUID == sample_patient_data["series_uid"]
    assert ds.SOPInstanceUID == sample_patient_data["sop_uid"]

    # Verify PDF is embedded correctly
    # DICOM may add padding bytes, so check that the embedded document contains our PDF
    assert ds.EncapsulatedDocument.startswith(b"%PDF")
    assert pdf_bytes in ds.EncapsulatedDocument
    assert ds.MIMETypeOfEncapsulatedDocument == "application/pdf"
