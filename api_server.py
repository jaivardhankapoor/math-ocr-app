#!/usr/bin/env python3
"""FastAPI server for OCR API. Usage: uvicorn api_server:app --host 0.0.0.0 --port 8000"""

import os
import tempfile
import base64
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ocr import convert

app = FastAPI(title="Math OCR API", version="1.0.0")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your Vercel domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConvertRequest(BaseModel):
    pdf_base64: str
    filename: str
    title: Optional[str] = None
    enable_compile_check: bool = False


class ConvertResponse(BaseModel):
    latex: str
    title: str
    pages: int
    cache_path: Optional[str] = None


@app.get("/")
async def root():
    return {"status": "ok", "service": "Math OCR API", "model": "gemini-3-flash-preview"}


@app.get("/health")
async def health():
    """Health check endpoint"""
    api_key = os.getenv("GEMINI_API_KEY")
    return {
        "status": "healthy",
        "api_key_configured": bool(api_key),
    }


@app.post("/convert", response_model=ConvertResponse)
async def convert_pdf(req: ConvertRequest):
    """
    Convert PDF to LaTeX.

    Expects:
    - pdf_base64: Base64-encoded PDF file
    - filename: Original filename (for title inference)
    - title: Optional custom title
    - enable_compile_check: Enable 3rd pass compile check (default: false)
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

    # Decode PDF
    try:
        pdf_bytes = base64.b64decode(req.pdf_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

    # Save to temp file
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        pdf_path = tmpdir / req.filename
        pdf_path.write_bytes(pdf_bytes)

        # Convert
        try:
            output_path = convert(
                pdf_path=str(pdf_path),
                output=str(tmpdir / "output.tex"),
                api_key=api_key,
                title=req.title,
                enable_compile_check=req.enable_compile_check,
                use_cache=False,  # Don't cache in temp dir
                clear_cache=False,
            )

            latex = Path(output_path).read_text(encoding="utf-8")

            # Count pages (estimate from cache or PDF)
            from pdf2image import convert_from_path
            images = convert_from_path(str(pdf_path), dpi=72)  # Low DPI just for count
            pages = len(images)

            title = req.title or pdf_path.stem.replace("_", " ").replace("-", " ").title()

            return ConvertResponse(
                latex=latex,
                title=title,
                pages=pages,
                cache_path=None,
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")


@app.post("/convert/upload", response_model=ConvertResponse)
async def convert_upload(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    enable_compile_check: bool = Form(False),
):
    """
    Convert PDF to LaTeX (multipart/form-data upload).

    Alternative endpoint that accepts file upload directly.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    pdf_bytes = await file.read()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        pdf_path = tmpdir / file.filename
        pdf_path.write_bytes(pdf_bytes)

        try:
            output_path = convert(
                pdf_path=str(pdf_path),
                output=str(tmpdir / "output.tex"),
                api_key=api_key,
                title=title,
                enable_compile_check=enable_compile_check,
                use_cache=False,
                clear_cache=False,
            )

            latex = Path(output_path).read_text(encoding="utf-8")

            from pdf2image import convert_from_path
            images = convert_from_path(str(pdf_path), dpi=72)
            pages = len(images)

            final_title = title or pdf_path.stem.replace("_", " ").replace("-", " ").title()

            return ConvertResponse(
                latex=latex,
                title=final_title,
                pages=pages,
                cache_path=None,
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
