# DICOM PDF Converter

[![CI/CD Pipeline](https://github.com/Medicai-io/dicom-pdf/actions/workflows/ci.yml/badge.svg)](https://github.com/Medicai-io/dicom-pdf/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Medicai-io/dicom-pdf/graph/badge.svg?token=MJUAE9QIUW)](https://codecov.io/gh/Medicai-io/dicom-pdf)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://hub.docker.com/r/medicai/dicom-pdf)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A production-ready service for converting PDF files to DICOM Encapsulated PDF Storage objects — and extracting them back. Perfect for integrating PDF documents (reports, consent forms, clinical documents) into PACS and medical imaging workflows.

## Features

- 📄 **DICOM Compliant** - Creates valid Encapsulated PDF Storage objects (SOP Class UID 1.2.840.10008.5.1.4.1.1.104.1)
- 🔁 **Both Directions** - PDF → DICOM encapsulation and DICOM → PDF extraction, byte-identical round-trip
- 🚀 **FastAPI REST API** - High-performance async endpoints with automatic validation
- 🔒 **Comprehensive Validation** - PDF/DICOM format checks, size limits, and metadata validation
- 📊 **Auto-generated Docs** - Interactive OpenAPI documentation at `/docs` and `/redoc`
- 🐳 **Docker Ready** - Multi-stage builds with security best practices
- ✅ **Production Tested** - 90%+ test coverage with unit and integration tests

## Quick Start

### Using Docker (Recommended)

```bash
# Pull and run the latest image
docker run -p 8000:8000 medicai/dicom-pdf:latest

# Or build and run locally with Docker Compose
docker compose up -d --wait      # http://localhost:8000/docs
docker compose down

# Or plain Docker
docker build -t dicom-pdf .
docker run -p 8000:8000 dicom-pdf
```

### Local Development

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install package with dev dependencies
pip install -e ".[dev]"

# Run the development server
uvicorn src.dicom_pdf.main:app --reload

# Run tests
pytest --cov=src
```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

## API Usage

### Convert PDF to DICOM

#### Basic Usage (Required Fields Only)
```bash
curl -X POST "http://localhost:8000/pdf-to-dicom" \
  -F "pdf_file=@example.pdf" \
  -F 'metadata={"patient_name":"Doe^John","patient_id":"12345"}' \
  --output converted.dcm
```

#### Complete Usage (All Available Fields)
```bash
curl -X POST "http://localhost:8000/pdf-to-dicom" \
  -F "pdf_file=@example.pdf" \
  -F 'metadata={
    "patient_name": "Doe^John^James",
    "patient_id": "12345",
    "study_instance_uid": "1.2.826.0.1.3680043.8.498.12345678901234567890",
    "series_instance_uid": "1.2.826.0.1.3680043.8.498.12345678901234567891",
    "sop_instance_uid": "1.2.826.0.1.3680043.8.498.12345678901234567892",
    "study_description": "Radiology Report Review",
    "series_description": "PDF Documents",
    "series_number": 999,
    "study_date": "20240315",
    "study_time": "143000",
    "study_id": "RAD2024003",
    "accession_number": "ACC-2024-001"
  }' \
  --output converted.dcm
```

### Extract PDF from DICOM

```bash
curl -X POST "http://localhost:8000/dicom-to-pdf" \
  -F "dicom_file=@converted.dcm" \
  --output extracted.pdf
```

The upload must be a DICOM Encapsulated PDF object (SOP Class `1.2.840.10008.5.1.4.1.1.104.1`); no file extension is required — the content is validated. The response carries `X-Patient-ID`, `X-Study-Instance-UID` and `X-SOP-Instance-UID` headers so callers can correlate the PDF back to the study without parsing DICOM.

#### Health Check

```bash
curl http://localhost:8000/health
```

#### API Documentation
- Interactive docs: http://localhost:8000/docs
- Alternative docs: http://localhost:8000/redoc



### Metadata Structure

The `metadata` field must be a JSON string containing patient and study information:

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `patient_name` | string | ✅ Yes | Patient name in DICOM format (Family^Given^Middle) | `"Doe^John^James"` |
| `patient_id` | string | ✅ Yes | Unique patient identifier | `"12345"` |
| `study_instance_uid` | string | ❌ No | Study Instance UID (auto-generated if not provided) | `"1.2.826.0.1.3680043.8.498.123..."` |
| `series_instance_uid` | string | ❌ No | Series Instance UID (auto-generated if not provided) | `"1.2.826.0.1.3680043.8.498.124..."` |
| `sop_instance_uid` | string | ❌ No | SOP Instance UID (auto-generated if not provided) | `"1.2.826.0.1.3680043.8.498.125..."` |
| `study_description` | string | ❌ No | Description of the study (max 64 chars) | `"Radiology Report Review"` |
| `series_description` | string | ❌ No | Description of the series (max 64 chars) | `"PDF Documents"` |
| `series_number` | int | ❌ No | Series number for viewer ordering (default `1`) | `999` |
| `study_date` | string | ❌ No | Study date, `YYYYMMDD` (default: current date) | `"20240315"` |
| `study_time` | string | ❌ No | Study time, `HHMMSS` (default: current time) | `"143000"` |
| `study_id` | string | ❌ No | Study ID, alphanumeric, max 16 chars (default `"1"`) | `"RAD2024003"` |
| `accession_number` | string | ❌ No | Accession number, alphanumeric + hyphens, max 16 chars | `"ACC-2024-001"` |

#### Notes:
- **Patient Name Format**: Use DICOM format with `^` separators (Family^Given^Middle)
- **UIDs**: Must contain only digits and dots if provided. Auto-generated UIDs follow standard format
- **Study association**: to attach the document to an existing study, pass the source study's `study_instance_uid` — and ideally its `study_date`, `study_time` and `accession_number` too; strict viewers (e.g. Horos) match on those, not just the UID
- **File Limits**: PDF files must be under 100MB; DICOM uploads under 101MB (an encapsulated 100MB PDF slightly exceeds 100MB)
- **Output**: `/pdf-to-dicom` returns `application/dicom`; `/dicom-to-pdf` returns `application/pdf`

### Programmatic Usage

```python
from dicom_pdf.converter import convert_pdf_to_dicom, extract_pdf_from_dicom

# Load PDF file
with open('document.pdf', 'rb') as f:
    pdf_bytes = f.read()

# Convert to DICOM
dicom_bytes = convert_pdf_to_dicom(
    pdf_bytes=pdf_bytes,
    patient_name="Doe^John",
    patient_id="12345"
)

# Save DICOM file
with open('output.dcm', 'wb') as f:
    f.write(dicom_bytes)

# ... and extract it back (byte-identical)
result = extract_pdf_from_dicom(dicom_bytes)
assert result.pdf_bytes == pdf_bytes
print(result.patient_id, result.study_instance_uid)
```

## Tech Stack

- **Python 3.11+** (3.13 recommended) - Modern Python runtime
- **FastAPI** - High-performance async web framework with automatic OpenAPI docs
- **pydicom 3.0+** - DICOM file creation and manipulation
- **pypdf 3.17+** - PDF validation and processing
- **Pydantic V2** - Data validation and serialization
- **pytest** - Testing framework with 90%+ coverage requirement
- **uvicorn** - Lightning-fast ASGI server
- **Docker** - Multi-stage builds optimized for production

## Development

### Local helper

`run-tests.sh` wraps the common loop (build, run, smoke-test, lint) so you don't have to remember the individual commands:

```bash
./run-tests.sh up        # build + run the container, wait for /health
./run-tests.sh smoke     # health check + convert + extract + byte-compare
./run-tests.sh all       # up -> smoke -> down
./run-tests.sh suite     # pytest + black/isort/flake8/mypy/bandit
./run-tests.sh dev       # local uvicorn --reload, no Docker
```

Override the port with `PORT=8010 ./run-tests.sh up`. It's just a convenience over `docker compose` and the tools below — CI doesn't depend on it.

### Running Tests

```bash
# Run all tests with coverage
pytest --cov=src

# Run specific test files
pytest tests/unit/test_converter.py
pytest tests/integration/test_api.py

# Generate HTML coverage report
pytest --cov=src --cov-report=html
```

## Use Cases

- **PACS Integration** - Store PDF reports alongside DICOM images
- **Clinical Documentation** - Convert consent forms, clinical notes to DICOM format
- **Document Retrieval** - Pull the original PDF back out of PACS-stored encapsulated documents
- **Telehealth** - Archive telehealth session PDFs in medical imaging systems
- **Research** - Include protocol documents and study materials in DICOM archives
- **Compliance** - Maintain PDF documents within regulated DICOM workflows

## Roadmap
Coming soon, let us know your thoughts in the meantime.

## License

MIT License - see LICENSE file for details.
