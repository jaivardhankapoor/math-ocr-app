#!/usr/bin/env python3
"""FastAPI server for OCR API. Usage: uvicorn api_server:app --host 0.0.0.0 --port 8000"""

import os
import tempfile
import base64
import uuid
import asyncio
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ocr import convert
import database
from job_queue import get_job_queue

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


class JobSubmitRequest(BaseModel):
    pdf_base64: str
    filename: str
    title: Optional[str] = None
    enable_compile_check: bool = False


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str


@app.on_event("startup")
async def startup_event():
    """Initialize database and start job queue worker"""
    database.init_db()
    get_job_queue().start()

    # Schedule cleanup task (runs every hour)
    async def cleanup_task():
        while True:
            await asyncio.sleep(3600)  # 1 hour
            deleted = database.cleanup_old_jobs(days=7)
            if deleted > 0:
                print(f"Cleaned up {deleted} old jobs")

    asyncio.create_task(cleanup_task())


@app.on_event("shutdown")
async def shutdown_event():
    """Stop job queue worker gracefully"""
    get_job_queue().stop()


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


# Job Queue Endpoints


@app.post("/jobs", response_model=JobSubmitResponse)
async def submit_job(req: JobSubmitRequest):
    """Submit a new conversion job to the queue"""
    # Decode PDF
    try:
        pdf_bytes = base64.b64decode(req.pdf_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Submit to queue
    try:
        get_job_queue().submit_job(
            job_id=job_id,
            pdf_bytes=pdf_bytes,
            filename=req.filename,
            title=req.title,
            enable_compile_check=req.enable_compile_check,
        )
        return JobSubmitResponse(job_id=job_id, status="queued")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit job: {e}")


@app.get("/jobs")
async def list_jobs(
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
):
    """List all jobs with optional status filter"""
    try:
        jobs = database.list_jobs(limit=limit, status=status)
        return {"jobs": jobs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {e}")


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get a single job by ID"""
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running or queued job"""
    success = get_job_queue().cancel_job(job_id)
    if not success:
        job = database.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        raise HTTPException(
            status_code=400,
            detail=f"Job cannot be cancelled (status: {job['status']})"
        )
    return {"message": "Job cancelled", "job_id": job_id}


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job"""
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Delete files
    if job["pdf_path"]:
        job_dir = Path(job["pdf_path"]).parent
        if job_dir.exists():
            import shutil
            shutil.rmtree(job_dir)

    # Delete from database
    database.delete_job(job_id)
    return {"message": "Job deleted", "job_id": job_id}


@app.get("/jobs/{job_id}/download")
async def download_job(job_id: str):
    """Download the LaTeX output file"""
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed (status: {job['status']})"
        )

    output_path = job.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        output_path,
        media_type="text/plain",
        filename=f"{job['title'] or 'output'}.tex"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
