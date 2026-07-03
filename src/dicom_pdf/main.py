"""FastAPI application for the DICOM PDF conversion service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router

app = FastAPI(
    title="DICOM PDF Converter",
    description="Convert PDF files to DICOM Encapsulated PDF Storage objects and extract them back",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


@app.get("/")
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "message": "DICOM PDF Converter API",
        "version": "0.2.0",
        "docs": "/docs",
        "health": "/health",
    }
