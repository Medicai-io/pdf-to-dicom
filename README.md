# PDF to DICOM Converter

[![CI/CD Pipeline](https://github.com/Medicai-io/pdf-to-dicom/actions/workflows/ci.yml/badge.svg)](https://github.com/Medicai-io/pdf-to-dicom/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Medicai-io/pdf-to-dicom/graph/badge.svg)](https://codecov.io/gh/Medicai-io/pdf-to-dicom)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A production-ready service for converting PDF files to DICOM Encapsulated PDF Storage objects with REST API interface.

## Features

- 📄 Convert PDF files to valid DICOM Encapsulated PDF Storage objects
- 🚀 FastAPI-based REST API
- 🔒 Comprehensive validation and error handling
- 📊 Auto-generated OpenAPI docs at `/docs` and `/redoc`

## Quick Start

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install package in development mode
pip install -e .

# Install development dependencies
pip install pytest pytest-cov httpx

# Run the development server
uvicorn src.pdf_to_dicom.main:app --reload

# Run tests
pytest --cov=src
```

## API Usage

### Convert PDF to DICOM

#### Basic Usage (Required Fields Only)
```bash
curl -X POST "http://localhost:8000/convert" \
  -F "pdf_file=@example.pdf" \
  -F 'metadata={"patient_name":"Doe^John","patient_id":"12345"}' \
  --output converted.dcm
```

#### Complete Usage (All Available Fields)
```bash
curl -X POST "http://localhost:8000/convert" \
  -F "pdf_file=@example.pdf" \
  -F 'metadata={
    "patient_name": "Doe^John^James",
    "patient_id": "12345",
    "study_instance_uid": "1.2.826.0.1.3680043.8.498.12345678901234567890",
    "series_instance_uid": "1.2.826.0.1.3680043.8.498.12345678901234567891",
    "sop_instance_uid": "1.2.826.0.1.3680043.8.498.12345678901234567892",
    "study_description": "Radiology Report Review",
    "series_description": "PDF Documents"
  }' \
  --output converted.dcm
```

### Metadata Structure

The `metadata` field must be a JSON string containing patient and study information:

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `patient_name` | string | ✅ Yes | Patient name in DICOM format (Family^Given^Middle) | `"Doe^John^James"` |
| `patient_id` | string | ✅ Yes | Unique patient identifier | `"12345"` |
| `study_instance_uid` | string | ❌ No | Study Instance UID (auto-generated if not provided) | `"1.2.826.0.1.3680043.8.498.123..."` |
| `series_instance_uid` | string | ❌ No | Series Instance UID (auto-generated if not provided) | `"1.2.826.0.1.3680043.8.498.124..."` |
| `sop_instance_uid` | string | ❌ No | SOP Instance UID (auto-generated if not provided) | `"1.2.826.0.1.3680043.8.498.125..."` |
| `study_description` | string | ❌ No | Description of the study | `"Radiology Report Review"` |
| `series_description` | string | ❌ No | Description of the series | `"PDF Documents"` |

#### Notes:
- **Patient Name Format**: Use DICOM format with `^` separators (Family^Given^Middle)
- **UIDs**: Must contain only digits and dots if provided. Auto-generated UIDs follow standard format
- **File Limits**: PDF files must be under 100MB
- **Output**: Returns DICOM file with Content-Type `application/dicom`

### Health Check

```bash
curl http://localhost:8000/health
```

### API Documentation
- Interactive docs: http://localhost:8000/docs
- Alternative docs: http://localhost:8000/redoc

### Programmatic Usage

```python
from pdf_to_dicom.converter import convert_pdf_to_dicom

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
```

## Tech Stack

- **Python 3.11+** - Runtime with modern features
- **FastAPI** - High-performance async web framework
- **pydicom 3.0.1** - DICOM file creation and manipulation
- **pypdf 3.17.1** - PDF validation and processing
- **Pydantic V2** - Data validation and serialization
- **pytest** - Testing framework with coverage
- **uvicorn** - Lightning-fast ASGI server

## Development

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

### Code Quality

```bash
# Format code
black .

# Sort imports
isort .

# Lint code
flake8

# Type checking
mypy src
```


## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request