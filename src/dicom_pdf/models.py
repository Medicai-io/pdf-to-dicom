"""Pydantic models for API request/response validation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ConversionMetadata(BaseModel):
    """Metadata schema for PDF to DICOM conversion.

    This model defines the required and optional metadata fields needed
    to create a valid DICOM Encapsulated PDF Storage object.
    """

    patient_name: str = Field(
        ...,
        description="Patient name in DICOM format (Family^Given^Middle)",
        examples=["Doe^John^James", "Smith^Jane", "Johnson^Robert^Michael"],
    )
    patient_id: str = Field(
        ...,
        description="Unique patient identifier",
        examples=["12345", "PAT001", "ABC123"],
    )
    study_instance_uid: Optional[str] = Field(
        None,
        description="Study Instance UID (auto-generated if not provided). Must contain only digits and dots.",
        examples=["1.2.826.0.1.3680043.8.498.12345678901234567890"],
    )
    series_instance_uid: Optional[str] = Field(
        None,
        description="Series Instance UID (auto-generated if not provided). Must contain only digits and dots.",
        examples=["1.2.826.0.1.3680043.8.498.12345678901234567891"],
    )
    sop_instance_uid: Optional[str] = Field(
        None,
        description="SOP Instance UID (auto-generated if not provided). Must contain only digits and dots.",
        examples=["1.2.826.0.1.3680043.8.498.12345678901234567892"],
    )
    study_description: Optional[str] = Field(
        None,
        max_length=64,
        description="Human-readable description of the study (max 64 characters)",
        examples=[
            "Radiology Report Review",
            "Patient Discharge Summary",
            "Lab Results",
        ],
    )
    series_description: Optional[str] = Field(
        None,
        max_length=64,
        description="Human-readable description of the series (max 64 characters)",
        examples=["PDF Documents", "Medical Reports", "Clinical Documents"],
    )
    series_number: Optional[int] = Field(
        None,
        ge=1,
        le=2147483647,
        description="Series number controlling ordering in viewers (defaults to 1)",
        examples=[1, 2, 999],
    )
    study_date: Optional[str] = Field(
        None,
        description="Study date in YYYYMMDD format (defaults to current date). "
        "Match the source study for proper study association in PACS viewers.",
        examples=["20240315"],
    )
    study_time: Optional[str] = Field(
        None,
        description="Study time in HHMMSS format (defaults to current time)",
        examples=["143000"],
    )
    study_id: Optional[str] = Field(
        None,
        max_length=16,
        pattern=r"^[A-Za-z0-9]+$",
        description="Study ID, alphanumeric, max 16 characters (defaults to '1')",
        examples=["STUDY001", "RAD2024003"],
    )
    accession_number: Optional[str] = Field(
        None,
        max_length=16,
        pattern=r"^[A-Za-z0-9-]+$",
        description="Accession number for study grouping, alphanumeric and hyphens, max 16 characters",
        examples=["ACC-2024-001", "RAD20240315"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"patient_name": "Doe^John", "patient_id": "12345"},
                {
                    "patient_name": "Smith^Jane^Marie",
                    "patient_id": "PAT001",
                    "study_description": "Radiology Report Review",
                    "series_description": "PDF Documents",
                    "series_number": 999,
                },
                {
                    "patient_name": "Johnson^Robert^Michael",
                    "patient_id": "ABC123",
                    "study_instance_uid": "1.2.826.0.1.3680043.8.498.12345678901234567890",
                    "series_instance_uid": "1.2.826.0.1.3680043.8.498.12345678901234567891",
                    "sop_instance_uid": "1.2.826.0.1.3680043.8.498.12345678901234567892",
                    "study_description": "Patient Discharge Summary",
                    "series_description": "Clinical Documents",
                    "study_date": "20240315",
                    "study_time": "143000",
                    "study_id": "RAD2024003",
                    "accession_number": "ACC-2024-001",
                },
            ]
        }
    }

    @field_validator("patient_name")
    @classmethod
    def validate_patient_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Patient name cannot be empty")
        return v.strip()

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Patient ID cannot be empty")
        return v.strip()

    @field_validator("study_instance_uid", "series_instance_uid", "sop_instance_uid")
    @classmethod
    def validate_uid_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            # Basic UID format validation (digits and dots)
            if not v.replace(".", "").isdigit():
                raise ValueError("UID must contain only digits and dots")
            if v.startswith(".") or v.endswith(".") or ".." in v:
                raise ValueError("UID format is invalid")
        return v

    @field_validator("study_date")
    @classmethod
    def validate_study_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if len(v) != 8:
                raise ValueError("Study date must be in YYYYMMDD format")
            try:
                datetime.strptime(v, "%Y%m%d")
            except ValueError:
                raise ValueError("Study date must be a valid date in YYYYMMDD format")
        return v

    @field_validator("study_time")
    @classmethod
    def validate_study_time(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if len(v) != 6:
                raise ValueError("Study time must be in HHMMSS format")
            try:
                datetime.strptime(v, "%H%M%S")
            except ValueError:
                raise ValueError("Study time must be a valid time in HHMMSS format")
        return v


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str = Field(..., description="Service health status")
    version: str = Field(..., description="Application version")
    timestamp: datetime = Field(..., description="Response timestamp")


class ErrorDetail(BaseModel):
    """Error detail model for API responses."""

    loc: list = Field(..., description="Error location")
    msg: str = Field(..., description="Error message")
    type: str = Field(..., description="Error type")


class ErrorResponse(BaseModel):
    """Standard error response model."""

    detail: str = Field(..., description="Error description")
    error_type: str = Field(..., description="Type of error")


class ValidationErrorResponse(BaseModel):
    """Validation error response model."""

    detail: list[ErrorDetail] = Field(..., description="List of validation errors")
