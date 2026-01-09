#!/usr/bin/env python3
"""FastAPI server for OCR API. Usage: uvicorn api_server:app --host 0.0.0.0 --port 8000"""

import os
import tempfile
import base64
import uuid
import asyncio
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from jose import jwt, JWTError

from ocr import convert
import database
from database import RateLimitExceeded
from job_queue import enqueue_job

# Get NextAuth secret from environment
NEXTAUTH_SECRET = os.getenv("NEXTAUTH_SECRET", "")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")
MAX_PDF_BYTES = int(os.getenv("MAX_PDF_BYTES", str(15 * 1024 * 1024)))
if not NEXTAUTH_SECRET or len(NEXTAUTH_SECRET) < 32:
    raise ValueError(
        "NEXTAUTH_SECRET must be set and at least 32 characters. "
        "Generate with: openssl rand -base64 32"
    )

app = FastAPI(title="Math OCR API", version="1.0.0")

# Enable CORS for Next.js frontend
# In production, set FRONTEND_URL to your deployed domain
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
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


class UserSyncRequest(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    image: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    tier: str
    usage_24h: int
    limit: int


# Auth dependency
async def get_current_user(authorization: str = Header(...)) -> dict:
    """Verify JWT token and return user payload"""
    if not NEXTAUTH_SECRET:
        raise HTTPException(status_code=500, detail="Auth not configured")

    try:
        # Extract token from "Bearer <token>"
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization header")

        token = authorization.replace("Bearer ", "")

        # Decode JWT
        payload = jwt.decode(token, NEXTAUTH_SECRET, algorithms=["HS256"])

        # NextAuth JWT structure: { sub: user_id, email, name, ... }
        if "sub" not in payload:
            raise HTTPException(status_code=401, detail="Invalid token: missing sub")

        return payload

    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def require_internal_key(
    internal_key: Optional[str] = Header(None, alias="X-Internal-API-Key"),
) -> None:
    if not INTERNAL_API_KEY:
        raise HTTPException(status_code=500, detail="Internal auth not configured")
    if not internal_key or internal_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Not authorized")


def estimate_base64_size(b64_data: str) -> int:
    trimmed = "".join(b64_data.split())
    padding = trimmed.count("=")
    return max(0, (len(trimmed) * 3) // 4 - padding)


def enforce_pdf_size(pdf_bytes: bytes):
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF too large (max {MAX_PDF_BYTES // (1024 * 1024)}MB)",
        )


@app.on_event("startup")
async def startup_event():
    """Initialize database and start job queue worker"""
    database.init_db()

    # Schedule cleanup task (runs every hour)
    async def cleanup_task():
        while True:
            await asyncio.sleep(3600)  # 1 hour
            deleted_paths = database.cleanup_old_jobs(days=7)
            if deleted_paths:
                for pdf_path in deleted_paths:
                    job_dir = Path(pdf_path).parent
                    if job_dir.exists():
                        import shutil
                        shutil.rmtree(job_dir, ignore_errors=True)
                print(f"Cleaned up {len(deleted_paths)} old jobs")

    asyncio.create_task(cleanup_task())


@app.on_event("shutdown")
async def shutdown_event():
    """Stop job queue worker gracefully"""
    pass


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


# User Endpoints


@app.post("/users/sync")
async def sync_user(req: UserSyncRequest, user: dict = Depends(get_current_user)):
    """Sync user from NextAuth to database"""
    # Verify the token user matches the request
    if user["sub"] != req.id:
        raise HTTPException(status_code=403, detail="Token mismatch")
    if user.get("email") and req.email and user["email"] != req.email:
        raise HTTPException(status_code=403, detail="Email mismatch")

    # Create or update user
    db_user = database.create_user(
        req.id,
        user.get("email") or req.email,
        user.get("name") or req.name,
        user.get("picture") or req.image,
    )
    return {"message": "User synced", "user": db_user}


@app.get("/users/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user info with usage stats"""
    user_id = user["sub"]

    # Get user from database
    db_user = database.get_user(user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found in database. Call /users/sync first.")

    # Get usage stats
    usage_24h = database.get_user_job_count_24h(user_id)

    # Determine limit based on tier
    tier = db_user["tier"]
    if tier == "unlimited":
        limit = -1  # Unlimited
    elif tier == "paid":
        limit = 50
    else:
        limit = 3

    return UserResponse(
        id=db_user["id"],
        email=db_user["email"],
        name=db_user["name"],
        tier=tier,
        usage_24h=usage_24h,
        limit=limit,
    )


class UpdateTierRequest(BaseModel):
    tier: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None


@app.put("/users/{user_id}/tier")
async def update_tier(
    user_id: str,
    req: UpdateTierRequest,
    _: None = Depends(require_internal_key),
):
    """Update user tier (called by Stripe webhook or admin)"""
    if req.tier not in ("free", "paid", "unlimited"):
        raise HTTPException(status_code=400, detail="Invalid tier")

    database.update_user_tier(
        user_id,
        req.tier,
        req.stripe_customer_id,
        req.stripe_subscription_id
    )

    return {"message": "Tier updated", "tier": req.tier}


@app.post("/convert", response_model=ConvertResponse)
async def convert_pdf(req: ConvertRequest, _: None = Depends(require_internal_key)):
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

    if req.filename and not req.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    if estimate_base64_size(req.pdf_base64) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF too large (max {MAX_PDF_BYTES // (1024 * 1024)}MB)",
        )

    # Decode PDF
    try:
        pdf_bytes = base64.b64decode(req.pdf_base64, validate=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

    enforce_pdf_size(pdf_bytes)

    # Save to temp file
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        pdf_path = tmpdir / "input.pdf"
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
    _: None = Depends(require_internal_key),
):
    """
    Convert PDF to LaTeX (multipart/form-data upload).

    Alternative endpoint that accepts file upload directly.
    """
    if not file.filename or not Path(file.filename).suffix.lower() == ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    pdf_buffer = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        pdf_buffer.extend(chunk)
        if len(pdf_buffer) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"PDF too large (max {MAX_PDF_BYTES // (1024 * 1024)}MB)",
            )
    pdf_bytes = bytes(pdf_buffer)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        pdf_path = tmpdir / "input.pdf"
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
async def submit_job(req: JobSubmitRequest, user: dict = Depends(get_current_user)):
    """Submit a new conversion job to the queue"""
    user_id = user["sub"]

    # Get user from database
    db_user = database.get_user(user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found. Call /users/sync first.")

    if req.filename and not req.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    if estimate_base64_size(req.pdf_base64) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF too large (max {MAX_PDF_BYTES // (1024 * 1024)}MB)",
        )

    # Decode PDF first to validate before rate limit check
    try:
        pdf_bytes = base64.b64decode(req.pdf_base64, validate=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}")

    enforce_pdf_size(pdf_bytes)

    # Generate job ID
    job_id = str(uuid.uuid4())

    tier = db_user["tier"]
    if tier == "unlimited":
        daily_limit = None
    elif tier == "paid":
        daily_limit = 50
    else:
        daily_limit = 3

    # Submit to queue (creates job in DB atomically with limit enforcement)
    try:
        enqueue_job(
            job_id=job_id,
            pdf_bytes=pdf_bytes,
            filename=req.filename,
            user_id=user_id,
            title=req.title,
            enable_compile_check=req.enable_compile_check,
            daily_limit=daily_limit,
        )
    except RateLimitExceeded as e:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily limit reached ({e.count}/{e.limit}). Upgrade to Pro for 50/day."
                if daily_limit == 3
                else f"Daily limit reached ({e.count}/{e.limit}). Try again tomorrow."
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit job: {e}")

    return JobSubmitResponse(job_id=job_id, status="queued")


@app.get("/jobs")
async def list_jobs(
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """List user's jobs with optional status filter"""
    user_id = user["sub"]
    try:
        jobs = database.list_jobs(limit=limit, status=status, user_id=user_id)
        return {"jobs": jobs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {e}")


@app.get("/jobs/{job_id}")
async def get_job(job_id: str, user: dict = Depends(get_current_user)):
    """Get a single job by ID"""
    user_id = user["sub"]
    job = database.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify ownership
    if job["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")

    return job


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, user: dict = Depends(get_current_user)):
    """Cancel a running or queued job"""
    user_id = user["sub"]
    job = database.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify ownership
    if job["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this job")

    if job["status"] in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Job cannot be cancelled (status: {job['status']})"
        )

    database.update_job_status(job_id, "cancelled")
    return {"message": "Job cancelled", "job_id": job_id}


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str, user: dict = Depends(get_current_user)):
    """Delete a job"""
    user_id = user["sub"]
    job = database.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify ownership
    if job["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this job")

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
async def download_job(job_id: str, user: dict = Depends(get_current_user)):
    """Download the LaTeX output file"""
    user_id = user["sub"]
    job = database.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify ownership
    if job["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to download this job")

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
