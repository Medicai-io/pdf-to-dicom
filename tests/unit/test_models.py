"""Unit tests for the Pydantic metadata model validators."""

import pytest
from pydantic import ValidationError

from dicom_pdf.models import ConversionMetadata

REQUIRED = {"patient_name": "Doe^John", "patient_id": "12345"}


class TestConversionMetadataValidators:
    """Test field validators on ConversionMetadata."""

    def test_minimal_metadata_valid(self):
        """Test the required-only payload validates."""
        metadata = ConversionMetadata(**REQUIRED)
        assert metadata.patient_name == "Doe^John"
        assert metadata.patient_id == "12345"

    def test_all_optional_fields_valid(self):
        """Test a fully populated payload validates."""
        metadata = ConversionMetadata(
            **REQUIRED,
            study_instance_uid="1.2.3.4",
            series_instance_uid="1.2.3.5",
            sop_instance_uid="1.2.3.6",
            study_description="Radiology Report Review",
            series_description="PDF Documents",
            series_number=999,
            study_date="20240315",
            study_time="143000",
            study_id="RAD2024003",
            accession_number="ACC-2024-001",
        )
        assert metadata.series_number == 999
        assert metadata.accession_number == "ACC-2024-001"

    def test_empty_patient_id_rejected(self):
        """Test empty patient ID is rejected."""
        with pytest.raises(ValidationError, match="Patient ID cannot be empty"):
            ConversionMetadata(patient_name="Doe^John", patient_id="   ")

    def test_uid_with_double_dots_rejected(self):
        """Test malformed UID structure is rejected."""
        with pytest.raises(ValidationError, match="UID format is invalid"):
            ConversionMetadata(**REQUIRED, study_instance_uid="1.2..3")

    def test_study_date_wrong_length_rejected(self):
        """Test study date must be exactly 8 digits."""
        with pytest.raises(ValidationError, match="YYYYMMDD"):
            ConversionMetadata(**REQUIRED, study_date="2024315")

    def test_study_date_invalid_calendar_date_rejected(self):
        """Test study date must be a real calendar date."""
        with pytest.raises(ValidationError, match="valid date"):
            ConversionMetadata(**REQUIRED, study_date="20241332")

    def test_study_time_wrong_length_rejected(self):
        """Test study time must be exactly 6 digits."""
        with pytest.raises(ValidationError, match="HHMMSS"):
            ConversionMetadata(**REQUIRED, study_time="1430")

    def test_study_time_invalid_time_rejected(self):
        """Test study time must be a real time of day."""
        with pytest.raises(ValidationError, match="valid time"):
            ConversionMetadata(**REQUIRED, study_time="256161")

    def test_study_id_non_alphanumeric_rejected(self):
        """Test study ID rejects non-alphanumeric characters."""
        with pytest.raises(ValidationError):
            ConversionMetadata(**REQUIRED, study_id="STUDY-001")

    def test_study_id_non_ascii_rejected(self):
        """Test study ID rejects non-ASCII letters (DICOM SH VR is ASCII)."""
        with pytest.raises(ValidationError):
            ConversionMetadata(**REQUIRED, study_id="STUDIU№1")

    def test_study_id_too_long_rejected(self):
        """Test study ID rejects values over 16 characters."""
        with pytest.raises(ValidationError):
            ConversionMetadata(**REQUIRED, study_id="A" * 17)

    def test_accession_number_invalid_characters_rejected(self):
        """Test accession number rejects characters beyond alnum + hyphen."""
        with pytest.raises(ValidationError):
            ConversionMetadata(**REQUIRED, accession_number="ACC_2024")

    def test_series_number_zero_rejected(self):
        """Test series number must be >= 1."""
        with pytest.raises(ValidationError):
            ConversionMetadata(**REQUIRED, series_number=0)

    def test_series_number_beyond_is_range_rejected(self):
        """Test series number must fit the DICOM IS VR (32-bit signed int)."""
        with pytest.raises(ValidationError):
            ConversionMetadata(**REQUIRED, series_number=2**31)

    def test_description_too_long_rejected(self):
        """Test descriptions are capped at the DICOM LO VR limit (64 chars)."""
        with pytest.raises(ValidationError):
            ConversionMetadata(**REQUIRED, study_description="x" * 65)
