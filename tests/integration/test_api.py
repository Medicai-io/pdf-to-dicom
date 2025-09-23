"""Integration tests for API endpoints."""

import io
import json
from pathlib import Path

import pytest
import pydicom
from fastapi.testclient import TestClient

from pdf_to_dicom.main import app

# Test client
client = TestClient(app)

# Test data paths
FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures"
SAMPLE_PDF = FIXTURES_PATH / "radiology_report.pdf"
CORRUPTED_PDF = FIXTURES_PATH / "corrupted.pdf"


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_endpoint(self):
        """Test health endpoint returns proper response."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_endpoint(self):
        """Test root endpoint returns API information."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert data["message"] == "PDF to DICOM Converter API"
        assert data["version"] == "0.1.0"
        assert data["docs"] == "/docs"
        assert data["health"] == "/health"


class TestConvertEndpoint:
    """Test PDF to DICOM conversion endpoint."""

    def test_successful_conversion_with_complete_metadata(self):
        """Test successful conversion with all metadata fields."""
        metadata = {
            "patient_name": "Doe^John",
            "patient_id": "12345",
            "study_instance_uid": "1.2.3.4.5.6.7.8.9",
            "series_instance_uid": "1.2.3.4.5.6.7.8.10",
            "sop_instance_uid": "1.2.3.4.5.6.7.8.11",
            "study_description": "Test Study",
            "series_description": "Test Series"
        }

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/convert",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)}
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/dicom"
        assert "attachment" in response.headers["content-disposition"]
        assert "dicom_12345_" in response.headers["content-disposition"]

        # Verify DICOM content
        dicom_bytes = response.content
        ds = pydicom.dcmread(io.BytesIO(dicom_bytes))

        assert ds.PatientName == "Doe^John"
        assert ds.PatientID == "12345"
        assert ds.StudyInstanceUID == "1.2.3.4.5.6.7.8.9"
        assert ds.SOPClassUID == "1.2.840.10008.5.1.4.1.1.104.1"

    def test_successful_conversion_with_minimal_metadata(self):
        """Test successful conversion with only required fields."""
        metadata = {
            "patient_name": "Smith^Jane",
            "patient_id": "67890"
        }

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/convert",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)}
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/dicom"

        # Verify DICOM content
        dicom_bytes = response.content
        ds = pydicom.dcmread(io.BytesIO(dicom_bytes))

        assert ds.PatientName == "Smith^Jane"
        assert ds.PatientID == "67890"
        # UIDs should be auto-generated
        assert ds.StudyInstanceUID.startswith("1.2.826.0.1.3680043.8.498.")

    def test_invalid_pdf_file(self):
        """Test error handling with invalid PDF file."""
        metadata = {
            "patient_name": "Test^Patient",
            "patient_id": "TEST123"
        }

        with open(CORRUPTED_PDF, "rb") as f:
            response = client.post(
                "/convert",
                files={"pdf_file": ("corrupted.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)}
            )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid PDF file" in data["detail"]

    def test_missing_metadata_fields(self):
        """Test validation error with missing required fields."""
        metadata = {
            "patient_name": "Test^Patient"
            # Missing patient_id
        }

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/convert",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)}
            )

        assert response.status_code == 422
        data = response.json()
        assert "validation error" in data["detail"].lower()

    def test_invalid_json_metadata(self):
        """Test error handling with invalid JSON metadata."""
        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/convert",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": "invalid json"}
            )

        assert response.status_code == 400
        data = response.json()
        assert "Metadata must be valid JSON" in data["detail"]

    def test_empty_patient_name(self):
        """Test validation error with empty patient name."""
        metadata = {
            "patient_name": "",
            "patient_id": "12345"
        }

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/convert",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)}
            )

        assert response.status_code == 422
        data = response.json()
        assert "validation error" in data["detail"].lower()

    def test_invalid_uid_format(self):
        """Test validation error with invalid UID format."""
        metadata = {
            "patient_name": "Test^Patient",
            "patient_id": "12345",
            "study_instance_uid": "invalid.uid.format.with.letters"
        }

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/convert",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)}
            )

        assert response.status_code == 422
        data = response.json()
        assert "validation error" in data["detail"].lower()

    def test_non_pdf_file_extension(self):
        """Test error with non-PDF file extension."""
        metadata = {
            "patient_name": "Test^Patient",
            "patient_id": "12345"
        }

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/convert",
                files={"pdf_file": ("test.txt", f, "text/plain")},
                data={"metadata": json.dumps(metadata)}
            )

        assert response.status_code == 400
        data = response.json()
        assert "File must be a PDF" in data["detail"]

    def test_missing_pdf_file(self):
        """Test error when PDF file is missing."""
        metadata = {
            "patient_name": "Test^Patient",
            "patient_id": "12345"
        }

        response = client.post(
            "/convert",
            data={"metadata": json.dumps(metadata)}
        )

        assert response.status_code == 422  # FastAPI validation error

    def test_missing_metadata(self):
        """Test error when metadata is missing."""
        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/convert",
                files={"pdf_file": ("test.pdf", f, "application/pdf")}
            )

        assert response.status_code == 422  # FastAPI validation error


class TestOpenAPIDocumentation:
    """Test OpenAPI documentation endpoints."""

    def test_docs_endpoint(self):
        """Test that OpenAPI docs are available."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_openapi_json(self):
        """Test OpenAPI JSON schema."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        assert schema["info"]["title"] == "PDF to DICOM Converter"
        assert schema["info"]["version"] == "0.1.0"

        # Check that our endpoints are documented
        paths = schema["paths"]
        assert "/convert" in paths
        assert "/health" in paths
        assert "post" in paths["/convert"]
        assert "get" in paths["/health"]