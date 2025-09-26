"""Unit tests for PDF to DICOM converter functionality."""

import pytest
import pydicom
from pathlib import Path

from pdf_to_dicom.converter import (
    convert_pdf_to_dicom,
    InvalidPDFError,
    DICOMCreationError,
    _validate_pdf,
    _create_dicom_dataset,
)

# Test data paths
FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures"
SAMPLE_PDF = FIXTURES_PATH / "radiology_report.pdf"
CORRUPTED_PDF = FIXTURES_PATH / "corrupted.pdf"


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
            sop_uid="1.2.3.4.5.6.7.8.11"
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
        assert ds.Manufacturer == "medicai-pdf-to-dicom"
        assert ds.ManufacturerModelName == "PDF to DICOM Converter"

        # Verify Encapsulated Document Module
        assert ds.MIMETypeOfEncapsulatedDocument == "application/pdf"
        assert ds.EncapsulatedDocument == pdf_bytes


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
            sop_uid="1.2.3.4.5.6.7.8.11"
        )

        # Verify we got bytes back
        assert isinstance(dicom_bytes, bytes)
        assert len(dicom_bytes) > 0

        # Verify we can read it as DICOM
        import io
        ds = pydicom.dcmread(io.BytesIO(dicom_bytes))
        assert ds.SOPClassUID == "1.2.840.10008.5.1.4.1.1.104.1"
        assert ds.PatientName == "Doe^John"
        assert ds.PatientID == "12345"

    def test_convert_with_minimal_metadata(self):
        """Test conversion with only required metadata (UIDs auto-generated)."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        dicom_bytes = convert_pdf_to_dicom(
            pdf_bytes=pdf_bytes,
            patient_name="Smith^Jane",
            patient_id="67890"
        )

        # Verify conversion succeeded
        assert isinstance(dicom_bytes, bytes)
        assert len(dicom_bytes) > 0

        # Verify DICOM content
        import io
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
                pdf_bytes=pdf_bytes,
                patient_name="",
                patient_id="12345"
            )

    def test_convert_missing_patient_id(self):
        """Test conversion fails with missing patient ID."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        with pytest.raises(InvalidPDFError, match="Patient name and ID are required"):
            convert_pdf_to_dicom(
                pdf_bytes=pdf_bytes,
                patient_name="Doe^John",
                patient_id=""
            )

    def test_convert_invalid_pdf(self):
        """Test conversion fails with invalid PDF."""
        with open(CORRUPTED_PDF, "rb") as f:
            pdf_bytes = f.read()

        with pytest.raises(InvalidPDFError):
            convert_pdf_to_dicom(
                pdf_bytes=pdf_bytes,
                patient_name="Doe^John",
                patient_id="12345"
            )

    def test_convert_oversized_pdf(self):
        """Test conversion fails with oversized PDF."""
        # Create fake oversized PDF
        large_pdf = b"%PDF-1.4" + b"x" * (101 * 1024 * 1024)

        with pytest.raises(InvalidPDFError, match="PDF file too large"):
            convert_pdf_to_dicom(
                pdf_bytes=large_pdf,
                patient_name="Doe^John",
                patient_id="12345"
            )


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_invalid_pdf_error_inheritance(self):
        """Test InvalidPDFError inherits from ValueError."""
        assert issubclass(InvalidPDFError, ValueError)

    def test_dicom_creation_error_inheritance(self):
        """Test DICOMCreationError inherits from RuntimeError."""
        assert issubclass(DICOMCreationError, RuntimeError)

    def test_pdf_validation_error_messages(self):
        """Test PDF validation provides meaningful error messages."""
        # Test empty file
        with pytest.raises(InvalidPDFError) as exc_info:
            _validate_pdf(b"")
        assert "too small" in str(exc_info.value)

        # Test invalid format (larger than 100 bytes)
        with pytest.raises(InvalidPDFError) as exc_info:
            _validate_pdf(b"not a pdf file but long enough text to pass size validation, needs to be over 100 bytes long and here is more text to make it really long enough to trigger the right validation error path")
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
    dicom_bytes = convert_pdf_to_dicom(
        pdf_bytes=pdf_bytes,
        **sample_patient_data
    )

    # Verify the DICOM file
    import io
    ds = pydicom.dcmread(io.BytesIO(dicom_bytes))

    # Verify all metadata is preserved
    assert ds.PatientName == sample_patient_data["patient_name"]
    assert ds.PatientID == sample_patient_data["patient_id"]
    assert ds.StudyInstanceUID == sample_patient_data["study_uid"]
    assert ds.SeriesInstanceUID == sample_patient_data["series_uid"]
    assert ds.SOPInstanceUID == sample_patient_data["sop_uid"]

    # Verify PDF is embedded correctly
    # DICOM may add padding bytes, so check that the embedded document contains our PDF
    assert ds.EncapsulatedDocument.startswith(b'%PDF')
    assert pdf_bytes in ds.EncapsulatedDocument
    assert ds.MIMETypeOfEncapsulatedDocument == "application/pdf"