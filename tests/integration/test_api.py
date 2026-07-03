"""Integration tests for API endpoints."""

import io
import json
from pathlib import Path

import pydicom
from fastapi.testclient import TestClient

from dicom_pdf.main import app

# Test client
client = TestClient(app)

# Test data paths
FIXTURES_PATH = Path(__file__).parent.parent.parent / "fixtures"
SAMPLE_PDF = FIXTURES_PATH / "radiology_report.pdf"
CORRUPTED_PDF = FIXTURES_PATH / "corrupted.pdf"
SAMPLE_DICOM = FIXTURES_PATH / "encapsulated_report.dcm"


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_endpoint(self):
        """Test health endpoint returns proper response."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["version"] == "0.2.0"
        assert "timestamp" in data


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_endpoint(self):
        """Test root endpoint returns API information."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert data["message"] == "DICOM PDF Converter API"
        assert data["version"] == "0.2.0"
        assert data["docs"] == "/docs"
        assert data["health"] == "/health"


class TestPdfToDicomEndpoint:
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
            "series_description": "Test Series",
            "series_number": 999,
            "study_date": "20240315",
            "study_time": "143000",
            "study_id": "RAD2024003",
            "accession_number": "ACC-2024-001",
        }

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)},
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
        assert ds.StudyDescription == "Test Study"
        assert ds.SeriesDescription == "Test Series"
        assert ds.SeriesNumber == 999
        assert ds.StudyDate == "20240315"
        assert ds.StudyTime == "143000"
        assert ds.StudyID == "RAD2024003"
        assert ds.AccessionNumber == "ACC-2024-001"

    def test_successful_conversion_with_minimal_metadata(self):
        """Test successful conversion with only required fields."""
        metadata = {"patient_name": "Smith^Jane", "patient_id": "67890"}

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)},
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

    def test_conversion_with_diacritic_patient_id(self):
        """Test a non-ASCII patient id yields an ASCII filename, not a 500."""
        metadata = {"patient_name": "Popescu^Ștefan", "patient_id": "PĂ123"}

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)},
            )

        assert response.status_code == 200
        # Non-ASCII stripped from the filename (latin-1 header safety)
        assert "dicom_P123_" in response.headers["content-disposition"]
        ds = pydicom.dcmread(io.BytesIO(response.content))
        assert str(ds.PatientName) == "Popescu^Ștefan"
        assert ds.PatientID == "PĂ123"

    def test_invalid_pdf_file(self):
        """Test error handling with invalid PDF file."""
        metadata = {"patient_name": "Test^Patient", "patient_id": "TEST123"}

        with open(CORRUPTED_PDF, "rb") as f:
            response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("corrupted.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)},
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
                "/pdf-to-dicom",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)},
            )

        assert response.status_code == 422
        data = response.json()
        assert "validation error" in data["detail"].lower()

    def test_invalid_json_metadata(self):
        """Test error handling with invalid JSON metadata."""
        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": "invalid json"},
            )

        assert response.status_code == 400
        data = response.json()
        assert "Metadata must be valid JSON" in data["detail"]

    def test_empty_patient_name(self):
        """Test validation error with empty patient name."""
        metadata = {"patient_name": "", "patient_id": "12345"}

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)},
            )

        assert response.status_code == 422
        data = response.json()
        assert "validation error" in data["detail"].lower()

    def test_invalid_uid_format(self):
        """Test validation error with invalid UID format."""
        metadata = {
            "patient_name": "Test^Patient",
            "patient_id": "12345",
            "study_instance_uid": "invalid.uid.format.with.letters",
        }

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)},
            )

        assert response.status_code == 422
        data = response.json()
        assert "validation error" in data["detail"].lower()

    def test_invalid_study_date_format(self):
        """Test validation error with invalid study date."""
        metadata = {
            "patient_name": "Test^Patient",
            "patient_id": "12345",
            "study_date": "2024-03-15",
        }

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)},
            )

        assert response.status_code == 422
        data = response.json()
        assert "validation error" in data["detail"].lower()

    def test_invalid_series_number(self):
        """Test validation error with non-positive series number."""
        metadata = {
            "patient_name": "Test^Patient",
            "patient_id": "12345",
            "series_number": 0,
        }

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)},
            )

        assert response.status_code == 422
        data = response.json()
        assert "validation error" in data["detail"].lower()

    def test_non_pdf_file_extension(self):
        """Test error with non-PDF file extension."""
        metadata = {"patient_name": "Test^Patient", "patient_id": "12345"}

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("test.txt", f, "text/plain")},
                data={"metadata": json.dumps(metadata)},
            )

        assert response.status_code == 400
        data = response.json()
        assert "File must be a PDF" in data["detail"]

    def test_missing_pdf_file(self):
        """Test error when PDF file is missing."""
        metadata = {"patient_name": "Test^Patient", "patient_id": "12345"}

        response = client.post("/pdf-to-dicom", data={"metadata": json.dumps(metadata)})

        assert response.status_code == 422  # FastAPI validation error

    def test_missing_metadata(self):
        """Test error when metadata is missing."""
        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
            )

        assert response.status_code == 422  # FastAPI validation error

    def test_dicom_creation_failure_returns_500(self, monkeypatch):
        """Test DICOMCreationError maps to a 500 response."""
        import dicom_pdf.api as api_module
        from dicom_pdf.converter import DICOMCreationError

        def boom(**kwargs):
            raise DICOMCreationError("boom")

        monkeypatch.setattr(api_module, "convert_pdf_to_dicom", boom)
        metadata = {"patient_name": "Test^Patient", "patient_id": "12345"}

        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)},
            )

        assert response.status_code == 500
        assert "DICOM creation failed" in response.json()["detail"]


class TestDicomToPdfEndpoint:
    """Test DICOM to PDF extraction endpoint."""

    def test_successful_extraction(self):
        """Test successful extraction from the committed fixture."""
        with open(SAMPLE_DICOM, "rb") as f:
            response = client.post(
                "/dicom-to-pdf",
                files={"dicom_file": ("report.dcm", f, "application/dicom")},
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]
        assert "pdf_12345_" in response.headers["content-disposition"]
        assert response.headers["x-patient-id"] == "12345"
        assert response.headers["x-study-instance-uid"] == "1.2.3.4.5.6.7.8.9"
        assert response.headers["x-sop-instance-uid"] == "1.2.3.4.5.6.7.8.11"

        # Extracted PDF is byte-identical to the source fixture
        with open(SAMPLE_PDF, "rb") as f:
            assert response.content == f.read()

    def test_extraction_without_file_extension(self):
        """Test extraction works for a DICOM upload without a file extension."""
        with open(SAMPLE_DICOM, "rb") as f:
            response = client.post(
                "/dicom-to-pdf",
                files={"dicom_file": ("instance", f, "application/octet-stream")},
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    def test_api_round_trip(self):
        """Test POST /pdf-to-dicom output feeds back through POST /dicom-to-pdf."""
        metadata = {"patient_name": "Doe^John", "patient_id": "12345"}

        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()

        convert_response = client.post(
            "/pdf-to-dicom",
            files={"pdf_file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"metadata": json.dumps(metadata)},
        )
        assert convert_response.status_code == 200

        extract_response = client.post(
            "/dicom-to-pdf",
            files={
                "dicom_file": (
                    "converted.dcm",
                    io.BytesIO(convert_response.content),
                    "application/dicom",
                )
            },
        )
        assert extract_response.status_code == 200
        assert extract_response.content == pdf_bytes

    def test_patient_id_header_keeps_raw_value(self):
        """Test X-Patient-ID carries the exact dataset value, not a sanitized one."""
        metadata = {"patient_name": "Doe^John", "patient_id": "PAT-001"}

        with open(SAMPLE_PDF, "rb") as f:
            convert_response = client.post(
                "/pdf-to-dicom",
                files={"pdf_file": ("test.pdf", f, "application/pdf")},
                data={"metadata": json.dumps(metadata)},
            )
        assert convert_response.status_code == 200

        extract_response = client.post(
            "/dicom-to-pdf",
            files={
                "dicom_file": (
                    "converted.dcm",
                    io.BytesIO(convert_response.content),
                    "application/dicom",
                )
            },
        )
        assert extract_response.status_code == 200
        # Header keeps the hyphen (PACS correlation); the filename strips it
        assert extract_response.headers["x-patient-id"] == "PAT-001"
        assert "pdf_PAT001_" in extract_response.headers["content-disposition"]

    def test_unsafe_uid_dropped_from_headers(self, build_dicom_bytes):
        """Test a UID with CRLF is not echoed into a response header."""
        with open(SAMPLE_PDF, "rb") as f:
            pdf_bytes = f.read()
        # Craft a StudyInstanceUID carrying a header-injection payload
        from pydicom.dataset import Dataset, FileMetaDataset
        from pydicom.uid import ExplicitVRLittleEndian

        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.104.1"
        file_meta.MediaStorageSOPInstanceUID = "1.2.3"
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = Dataset()
        ds.file_meta = file_meta
        ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.104.1"
        ds.SOPInstanceUID = "1.2.3"
        ds.PatientID = "12345"
        ds.add_new(0x0020000D, "UI", "1.2.3\r\nX-Evil: injected")
        ds.MIMETypeOfEncapsulatedDocument = "application/pdf"
        ds.EncapsulatedDocument = pdf_bytes
        output = io.BytesIO()
        ds.save_as(output, enforce_file_format=True)

        response = client.post(
            "/dicom-to-pdf",
            files={
                "dicom_file": (
                    "x.dcm",
                    io.BytesIO(output.getvalue()),
                    "application/dicom",
                )
            },
        )

        assert response.status_code == 200
        assert "x-study-instance-uid" not in response.headers
        assert "x-evil" not in response.headers
        # Safe headers still present
        assert response.headers["x-patient-id"] == "12345"

    def test_non_dicom_file(self):
        """Test error handling when the upload is not a DICOM file."""
        with open(SAMPLE_PDF, "rb") as f:
            response = client.post(
                "/dicom-to-pdf",
                files={"dicom_file": ("report.pdf", f, "application/pdf")},
            )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid DICOM file" in data["detail"]

    def test_dicom_without_embedded_pdf(self, build_dicom_bytes):
        """Test error handling for a DICOM without an EncapsulatedDocument."""
        dicom_bytes = build_dicom_bytes(document=None)

        response = client.post(
            "/dicom-to-pdf",
            files={
                "dicom_file": (
                    "no_doc.dcm",
                    io.BytesIO(dicom_bytes),
                    "application/dicom",
                )
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "no EncapsulatedDocument" in data["detail"]

    def test_wrong_sop_class(self, build_dicom_bytes):
        """Test error handling for a DICOM that is not an Encapsulated PDF."""
        dicom_bytes = build_dicom_bytes(sop_class_uid="1.2.840.10008.5.1.4.1.1.2")

        response = client.post(
            "/dicom-to-pdf",
            files={
                "dicom_file": (
                    "ct.dcm",
                    io.BytesIO(dicom_bytes),
                    "application/dicom",
                )
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "Not an Encapsulated PDF object" in data["detail"]

    def test_missing_dicom_file(self):
        """Test error when the DICOM file is missing."""
        response = client.post("/dicom-to-pdf")

        assert response.status_code == 422  # FastAPI validation error

    def test_pdf_extraction_failure_returns_500(self, monkeypatch):
        """Test PDFExtractionError maps to a 500 response."""
        import dicom_pdf.api as api_module
        from dicom_pdf.converter import PDFExtractionError

        def boom(dicom_bytes):
            raise PDFExtractionError("boom")

        monkeypatch.setattr(api_module, "extract_pdf_from_dicom", boom)

        with open(SAMPLE_DICOM, "rb") as f:
            response = client.post(
                "/dicom-to-pdf",
                files={"dicom_file": ("report.dcm", f, "application/dicom")},
            )

        assert response.status_code == 500
        assert "PDF extraction failed" in response.json()["detail"]


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
        assert schema["info"]["title"] == "DICOM PDF Converter"
        assert schema["info"]["version"] == "0.2.0"

        # Check that our endpoints are documented
        paths = schema["paths"]
        assert "/pdf-to-dicom" in paths
        assert "/dicom-to-pdf" in paths
        assert "/health" in paths
        assert "/convert" not in paths
        assert "post" in paths["/pdf-to-dicom"]
        assert "post" in paths["/dicom-to-pdf"]
        assert "get" in paths["/health"]
