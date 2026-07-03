"""API router for the PDF <-> DICOM conversion endpoints."""

import json
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import ValidationError

from .converter import (
    MAX_DICOM_SIZE_BYTES,
    MAX_PDF_SIZE_BYTES,
    DICOMCreationError,
    InvalidDICOMError,
    InvalidPDFError,
    PDFExtractionError,
    convert_pdf_to_dicom,
    extract_pdf_from_dicom,
)
from .models import ConversionMetadata, ErrorResponse, HealthResponse

# Create API router
router = APIRouter()


@router.post(
    "/pdf-to-dicom",
    responses={
        200: {
            "description": "DICOM file successfully created",
            "content": {"application/dicom": {}},
            "headers": {
                "Content-Disposition": {
                    "description": "Attachment with DICOM filename (e.g., dicom_12345_20240101_120000.dcm)",
                    "schema": {"type": "string"},
                }
            },
        },
        400: {
            "model": ErrorResponse,
            "description": "Invalid PDF file or malformed JSON metadata",
        },
        413: {
            "model": ErrorResponse,
            "description": "PDF file exceeds 100MB size limit",
        },
        422: {
            "description": "Metadata validation error - missing required fields or invalid format"
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal server error during DICOM creation",
        },
    },
    summary="Convert PDF to DICOM Encapsulated PDF Storage",
    description="""Convert a PDF file to DICOM Encapsulated PDF Storage format.

        Upload Requirements:
        - File must be a valid PDF (checked by extension and content)
        - File size must be under 100MB
        - Metadata must be valid JSON with required fields (see metadata parameter below)

        Returns:
        - Binary DICOM file with Content-Type: application/dicom
        - Filename format: dicom_{patient_id}_{timestamp}.dcm""",
)
def convert_pdf_to_dicom_endpoint(
    pdf_file: UploadFile = File(
        ...,
        description="PDF file to convert (max 100MB, must have .pdf extension)",
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
            - study_description: Human-readable study description (max 64 chars)
            - series_description: Human-readable series description (max 64 chars)
            - series_number: Series number for viewer ordering (defaults to 1)
            - study_date: YYYYMMDD, match the source study for proper association (defaults to now)
            - study_time: HHMMSS (defaults to now)
            - study_id: Alphanumeric, max 16 chars (defaults to "1")
            - accession_number: Alphanumeric + hyphens, max 16 chars

            Example: {"patient_name":"Doe^John","patient_id":"12345"}""",
    ),
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
    if not pdf_file.filename or not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a PDF",
        )

    # Check file size (100MB limit)
    if pdf_file.size and pdf_file.size > MAX_PDF_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 100MB limit",
        )

    # Parse and validate metadata
    try:
        metadata_dict = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metadata must be valid JSON",
        )

    try:
        conversion_metadata = ConversionMetadata(**metadata_dict)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Metadata validation error: {str(e)}",
        )

    # Read PDF file and convert to DICOM. The handler is deliberately sync (no
    # async def): FastAPI runs it in the threadpool, so the CPU-bound conversion
    # of up-to-100MB payloads doesn't stall the event loop (or /health).
    try:
        pdf_bytes = pdf_file.file.read()

        # Convert to DICOM
        dicom_bytes = convert_pdf_to_dicom(
            pdf_bytes=pdf_bytes,
            patient_name=conversion_metadata.patient_name,
            patient_id=conversion_metadata.patient_id,
            study_uid=conversion_metadata.study_instance_uid,
            series_uid=conversion_metadata.series_instance_uid,
            sop_uid=conversion_metadata.sop_instance_uid,
            study_description=conversion_metadata.study_description,
            series_description=conversion_metadata.series_description,
            series_number=conversion_metadata.series_number,
            study_date=conversion_metadata.study_date,
            study_time=conversion_metadata.study_time,
            study_id=conversion_metadata.study_id,
            accession_number=conversion_metadata.accession_number,
        )

        # Generate filename. Keep ASCII alnum only — the filename lands in a
        # latin-1-encoded header, so a diacritic patient id would otherwise 500.
        safe_patient_id = (
            "".join(
                c for c in conversion_metadata.patient_id if c.isascii() and c.isalnum()
            )
            or "unknown"
        )
        filename = (
            f"dicom_{safe_patient_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dcm"
        )

        # Return DICOM file
        return Response(
            content=dicom_bytes,
            media_type="application/dicom",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except InvalidPDFError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid PDF file: {str(e)}",
        )
    except DICOMCreationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"DICOM creation failed: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )


@router.post(
    "/dicom-to-pdf",
    responses={
        200: {
            "description": "PDF successfully extracted from the DICOM object",
            "content": {"application/pdf": {}},
            "headers": {
                "Content-Disposition": {
                    "description": "Attachment with PDF filename (e.g., pdf_12345_20240101_120000.pdf)",
                    "schema": {"type": "string"},
                },
                "X-Patient-ID": {
                    "description": "PatientID from the DICOM dataset (omitted if absent)",
                    "schema": {"type": "string"},
                },
                "X-Study-Instance-UID": {
                    "description": "StudyInstanceUID from the DICOM dataset (omitted if absent)",
                    "schema": {"type": "string"},
                },
                "X-SOP-Instance-UID": {
                    "description": "SOPInstanceUID from the DICOM dataset (omitted if absent)",
                    "schema": {"type": "string"},
                },
            },
        },
        400: {
            "model": ErrorResponse,
            "description": "Invalid DICOM file, wrong SOP class, or no embedded PDF",
        },
        413: {
            "model": ErrorResponse,
            "description": "DICOM file exceeds 101MB size limit",
        },
        422: {"description": "Missing DICOM file"},
        500: {
            "model": ErrorResponse,
            "description": "Internal server error during PDF extraction",
        },
    },
    summary="Extract PDF from DICOM Encapsulated PDF Storage",
    description="""Extract the embedded PDF from a DICOM Encapsulated PDF Storage object.

        Upload Requirements:
        - File must be a valid DICOM Encapsulated PDF object (validated by content;
          no file extension required — DICOM files often ship without one)
        - File size must be under 101MB

        Returns:
        - Binary PDF file with Content-Type: application/pdf
        - Filename format: pdf_{patient_id}_{timestamp}.pdf
        - X-Patient-ID / X-Study-Instance-UID / X-SOP-Instance-UID response headers
          for correlating the PDF back to the study""",
)
def extract_pdf_from_dicom_endpoint(
    dicom_file: UploadFile = File(
        ...,
        description="DICOM Encapsulated PDF file (max 101MB, validated by content)",
    ),
) -> Response:
    """Extract the embedded PDF from a DICOM file.

    Args:
        dicom_file: Uploaded DICOM Encapsulated PDF file

    Returns:
        PDF file as binary response

    Raises:
        HTTPException: On validation or extraction errors
    """
    # Check file size (101MB limit)
    if dicom_file.size and dicom_file.size > MAX_DICOM_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 101MB limit",
        )

    # Read DICOM file and extract the PDF. Sync handler on purpose — see the
    # threadpool note on the convert endpoint.
    try:
        dicom_bytes = dicom_file.file.read()

        result = extract_pdf_from_dicom(dicom_bytes)

        # Generate filename. ASCII alnum only — see the note on the convert route.
        safe_patient_id = (
            "".join(c for c in result.patient_id if c.isascii() and c.isalnum())
            or "unknown"
        )
        filename = (
            f"pdf_{safe_patient_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )

        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        # Correlation headers carry the raw dataset values (a sanitized PatientID
        # would no longer match the PACS), but the values come from untrusted
        # DICOM elements, so drop any that aren't header-safe.
        if _header_safe(result.patient_id):
            headers["X-Patient-ID"] = result.patient_id
        if _header_safe(result.study_instance_uid):
            headers["X-Study-Instance-UID"] = result.study_instance_uid
        if _header_safe(result.sop_instance_uid):
            headers["X-SOP-Instance-UID"] = result.sop_instance_uid

        # Return PDF file
        return Response(
            content=result.pdf_bytes,
            media_type="application/pdf",
            headers=headers,
        )

    except InvalidDICOMError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid DICOM file: {str(e)}",
        )
    except PDFExtractionError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF extraction failed: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check service health and get version information",
)
async def health_check() -> HealthResponse:
    """Health check endpoint with version and timestamp."""
    return HealthResponse(status="healthy", version="0.2.0", timestamp=datetime.now())


def _header_safe(value: str) -> bool:
    """Whether an untrusted DICOM value is safe to emit as an HTTP header.

    Rejects empty, non-ASCII (would fail latin-1 header encoding) and
    non-printable values (CR/LF control chars enable response splitting).
    """
    return bool(value) and value.isascii() and value.isprintable()
