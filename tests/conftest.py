"""Pytest configuration and fixtures."""

import pytest


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