"""Pytest configuration and fixtures."""

import io

import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian

from dicom_pdf.converter import ENCAPSULATED_PDF_SOP_CLASS_UID


@pytest.fixture
def sample_patient_data():
    """Sample patient metadata for testing."""
    return {
        "patient_name": "Doe^John",
        "patient_id": "12345",
        "study_uid": "1.2.3.4.5.6.7.8.9",
        "series_uid": "1.2.3.4.5.6.7.8.10",
        "sop_uid": "1.2.3.4.5.6.7.8.11",
    }


@pytest.fixture
def build_dicom_bytes():
    """Builder for minimal synthesized DICOM bytes (malformed-input tests).

    Pass None for document/mime_type/patient_id to omit the element entirely.
    """

    def _build(
        sop_class_uid=ENCAPSULATED_PDF_SOP_CLASS_UID,
        document=b"%PDF-1.4 " + b"x" * 200,
        mime_type="application/pdf",
        patient_id="12345",
        declared_length=None,
    ):
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = (
            sop_class_uid or ENCAPSULATED_PDF_SOP_CLASS_UID
        )
        file_meta.MediaStorageSOPInstanceUID = "1.2.3.4.5.6.7.8.11"
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

        ds = Dataset()
        ds.file_meta = file_meta
        if sop_class_uid:
            ds.SOPClassUID = sop_class_uid
        ds.SOPInstanceUID = "1.2.3.4.5.6.7.8.11"
        if patient_id:
            ds.PatientID = patient_id
        ds.StudyInstanceUID = "1.2.3.4.5.6.7.8.9"
        ds.Modality = "DOC"
        if mime_type:
            ds.MIMETypeOfEncapsulatedDocument = mime_type
        if document is not None:
            ds.EncapsulatedDocument = document
        if declared_length is not None:
            ds.EncapsulatedDocumentLength = declared_length

        output = io.BytesIO()
        ds.save_as(output, enforce_file_format=True)
        return output.getvalue()

    return _build
