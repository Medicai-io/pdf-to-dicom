"""PDF to DICOM converter package."""

__version__ = "0.1.0"
__author__ = "Alexandru Artimon"

from .converter import convert_pdf_to_dicom

__all__ = ["convert_pdf_to_dicom"]
