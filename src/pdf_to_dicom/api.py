"""API router for PDF to DICOM conversion endpoints."""

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import ValidationError

from .converter import convert_pdf_to_dicom, InvalidPDFError, DICOMCreationError
from .models import ConversionMetadata, HealthResponse, ErrorResponse

# Create API router
router = APIRouter()


@router.post(
    "/convert",
    responses={
        200: {
            "description": "DICOM file successfully created",
            "content": {"application/dicom": {}},
            "headers": {
                "Content-Disposition": {
                    "description": "Attachment with DICOM filename (e.g., dicom_12345_20240101_120000.dcm)",
                    "schema": {"type": "string"}
                }
            }
        },
        400: {
            "model": ErrorResponse,
            "description": "Invalid PDF file or malformed JSON metadata"
        },
        413: {
            "model": ErrorResponse,
            "description": "PDF file exceeds 100MB size limit"
        },
        422: {
            "description": "Metadata validation error - missing required fields or invalid format"
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal server error during DICOM creation"
        }
    },
    summary="Convert PDF to DICOM Encapsulated PDF Storage",
    description="""Convert a PDF file to DICOM Encapsulated PDF Storage format.

        Upload Requirements:
        - File must be a valid PDF (checked by extension and content)
        - File size must be under 100MB
        - Metadata must be valid JSON with required fields (see metadata parameter below)

        Returns:
        - Binary DICOM file with Content-Type: application/dicom
        - Filename format: dicom_{patient_id}_{timestamp}.dcm"""
)
async def convert_pdf_to_dicom_endpoint(
    pdf_file: UploadFile = File(
        ...,
        description="PDF file to convert (max 100MB, must have .pdf extension)"
    ),
    metadata: str = Form(
        ...,
        description="""JSON string with patient metadata.

            Required Fields:
            - patient_name: Patient name in DICOM format (Family^Given^Middle)
            - patient_id: Unique patient identifier

            Optional Fields:
            - study_instance_uid: Auto-generated if not provided
            - series_instance_uid: Auto-generated if not provided
            - sop_instance_uid: Auto-generated if not provided
            - study_description: Human-readable study description
            - series_description: Human-readable series description

            Example: {"patient_name":"Doe^John","patient_id":"12345"}"""
    )
) -> Response:
    """Convert PDF file to DICOM format.

    Args:
        pdf_file: Uploaded PDF file
        metadata: JSON string with conversion metadata

    Returns:
        DICOM file as binary response

    Raises:
        HTTPException: On validation or conversion errors
    """
    # Validate file type
    if not pdf_file.filename or not pdf_file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a PDF"
        )

    # Check file size (100MB limit)
    if pdf_file.size and pdf_file.size > 100 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 100MB limit"
        )

    # Parse and validate metadata
    try:
        metadata_dict = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metadata must be valid JSON"
        )

    try:
        conversion_metadata = ConversionMetadata(**metadata_dict)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Metadata validation error: {str(e)}"
        )

    # Read PDF file and convert to DICOM
    try:
        pdf_bytes = await pdf_file.read()

        # Convert to DICOM
        dicom_bytes = convert_pdf_to_dicom(
            pdf_bytes=pdf_bytes,
            patient_name=conversion_metadata.patient_name,
            patient_id=conversion_metadata.patient_id,
            study_uid=conversion_metadata.study_instance_uid,
            series_uid=conversion_metadata.series_instance_uid,
            sop_uid=conversion_metadata.sop_instance_uid
        )

        # Generate filename
        safe_patient_id = "".join(c for c in conversion_metadata.patient_id if c.isalnum())
        filename = f"dicom_{safe_patient_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dcm"

        # Return DICOM file
        return Response(
            content=dicom_bytes,
            media_type="application/dicom",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except InvalidPDFError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid PDF file: {str(e)}"
        )
    except DICOMCreationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DICOM creation failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check service health and get version information"
)
async def health_check() -> HealthResponse:
    """Health check endpoint with version and timestamp."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        timestamp=datetime.now()
    )