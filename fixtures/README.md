# Test Fixtures

This directory contains test data files for the DICOM PDF converter.

## Contents

- `radiology_report.pdf` - Sample radiology report PDF file for testing conversion (odd byte length on purpose — it exercises the DICOM padding path)
- `corrupted.pdf` - Corrupted PDF file for error handling tests
- `encapsulated_report.dcm` - DICOM Encapsulated PDF wrapping `radiology_report.pdf`, used by the extraction tests (keeps decoder tests independent of encoder bugs)
- `metadata/` - Sample metadata JSON files

## Usage

These files are used by the test suite to validate PDF ↔ DICOM conversion functionality. The `radiology_report.pdf` contains a sample medical report with charts and imaging data suitable for testing DICOM encapsulation.

## Regenerating `encapsulated_report.dcm`

Only needed if the encoder's tag layout changes on purpose. The pinned values match `metadata/sample_metadata.json` and the test assertions:

```bash
python -c "
from pathlib import Path
from dicom_pdf.converter import convert_pdf_to_dicom
pdf = Path('fixtures/radiology_report.pdf').read_bytes()
Path('fixtures/encapsulated_report.dcm').write_bytes(convert_pdf_to_dicom(
    pdf_bytes=pdf, patient_name='Doe^John', patient_id='12345',
    study_uid='1.2.3.4.5.6.7.8.9', series_uid='1.2.3.4.5.6.7.8.10', sop_uid='1.2.3.4.5.6.7.8.11'))
"
```
