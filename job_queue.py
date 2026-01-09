#!/usr/bin/env python3
"""RQ-backed job queue helpers for OCR processing"""

import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Optional

from redis import Redis
from rq import Queue

import database
from ocr import convert, CancelledException

log = logging.getLogger(__name__)

JOBS_DIR = Path("jobs")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def enqueue_job(
    job_id: str,
    pdf_bytes: bytes,
    filename: str,
    user_id: str,
    title: Optional[str] = None,
    enable_compile_check: bool = False,
    daily_limit: Optional[int] = None,
) -> None:
    """Create job record, write files, and enqueue for processing."""
    database.create_job_with_limit(
        job_id,
        filename,
        user_id,
        title,
        enable_compile_check,
        daily_limit,
    )

    job_dir = JOBS_DIR / job_id
    output_path = job_dir / "output.tex"
    pdf_path = job_dir / "input.pdf"

    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)
        database.update_job_paths(job_id, str(pdf_path), str(output_path))

        queue = Queue("ocr", connection=Redis.from_url(REDIS_URL))
        queue.enqueue(process_job, job_id)
        log.info("Job %s enqueued", job_id)
    except Exception:
        database.delete_job(job_id)
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
        raise


def process_job(job_id: str):
    """Process a single job (invoked by RQ worker)."""
    log.info("Processing job %s...", job_id)

    job = database.get_job(job_id)
    if not job:
        log.error("Job %s not found in database", job_id)
        return

    if job["status"] == "cancelled":
        log.info("Job %s was cancelled before processing", job_id)
        return

    database.update_job_status(job_id, "running")

    cancel_event = threading.Event()

    try:
        def progress_callback(current: int, total: int, pass_name: str):
            database.update_job_progress(job_id, current, total, pass_name)
            log.info("Job %s: %s - page %s/%s", job_id, pass_name, current, total)

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not configured")

        output_path = convert(
            pdf_path=job["pdf_path"],
            output=job["output_path"],
            api_key=api_key,
            title=job["title"],
            enable_compile_check=job["enable_compile_check"],
            use_cache=True,
            clear_cache=False,
            cancellation_event=cancel_event,
            progress_callback=progress_callback,
        )

        latex = Path(output_path).read_text(encoding="utf-8")
        database.update_job_status(
            job_id, "completed", latex=latex, output_path=output_path
        )
        log.info("Job %s completed successfully", job_id)

    except CancelledException:
        database.update_job_status(job_id, "cancelled")
        log.info("Job %s was cancelled during processing", job_id)

    except Exception as e:
        log.error("Job %s failed: %s", job_id, e)
        database.update_job_status(job_id, "failed", error=str(e))
