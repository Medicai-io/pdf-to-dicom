"""DICOM PDF converter package: PDF -> DICOM encapsulation and DICOM -> PDF extraction."""

__version__ = "0.2.0"
__author__ = "Alexandru Artimon"

from .converter import ExtractionResult, convert_pdf_to_dicom, extract_pdf_from_dicom

__all__ = ["convert_pdf_to_dicom", "extract_pdf_from_dicom", "ExtractionResult"]
