#!/usr/bin/env python3
"""Background job queue worker for OCR processing"""

import logging
import os
import queue
import shutil
import threading
from pathlib import Path
from typing import Dict, Optional

import database
from ocr import convert, CancelledException

log = logging.getLogger(__name__)

JOBS_DIR = Path("jobs")


class JobQueue:
    """Background worker thread for processing OCR jobs"""

    def __init__(self):
        self.queue = queue.Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.running = False
        self.cancellation_events: Dict[str, threading.Event] = {}

    def start(self):
        """Start the worker thread"""
        if self.worker_thread and self.worker_thread.is_alive():
            log.warning("Worker thread already running")
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        log.info("Job queue worker started")

    def stop(self):
        """Stop the worker thread gracefully"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
            log.info("Job queue worker stopped")

    def submit_job(
        self,
        job_id: str,
        pdf_bytes: bytes,
        filename: str,
        title: Optional[str] = None,
        enable_compile_check: bool = False,
    ):
        """Submit a new job to the queue"""
        # Create job directory
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Save PDF file
        pdf_path = job_dir / "input.pdf"
        pdf_path.write_bytes(pdf_bytes)

        # Create job in database
        database.create_job(job_id, filename, title, enable_compile_check)

        # Update paths
        output_path = job_dir / "output.tex"
        database.update_job_paths(job_id, str(pdf_path), str(output_path))

        # Add to queue
        self.queue.put(job_id)
        log.info(f"Job {job_id} submitted to queue")

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running or queued job"""
        job = database.get_job(job_id)
        if not job:
            return False

        if job["status"] in ("completed", "failed", "cancelled"):
            return False

        # Set cancellation event if running
        if job_id in self.cancellation_events:
            self.cancellation_events[job_id].set()

        # Update status
        database.update_job_status(job_id, "cancelled")
        log.info(f"Job {job_id} cancelled")
        return True

    def _worker(self):
        """Background worker that processes jobs sequentially"""
        log.info("Worker thread started, waiting for jobs...")

        while self.running:
            try:
                # Get next job (with timeout so we can check self.running)
                job_id = self.queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                self._process_job(job_id)
            except Exception as e:
                log.error(f"Unexpected error processing job {job_id}: {e}")
                database.update_job_status(
                    job_id, "failed", error=f"Unexpected error: {str(e)}"
                )
            finally:
                self.queue.task_done()

    def _process_job(self, job_id: str):
        """Process a single job"""
        log.info(f"Processing job {job_id}...")

        # Get job from database
        job = database.get_job(job_id)
        if not job:
            log.error(f"Job {job_id} not found in database")
            return

        # Check if already cancelled
        if job["status"] == "cancelled":
            log.info(f"Job {job_id} was cancelled before processing")
            return

        # Mark as running
        database.update_job_status(job_id, "running")

        # Create cancellation event
        cancel_event = threading.Event()
        self.cancellation_events[job_id] = cancel_event

        try:
            # Progress callback
            def progress_callback(current: int, total: int, pass_name: str):
                database.update_job_progress(job_id, current, total, pass_name)
                log.info(f"Job {job_id}: {pass_name} - page {current}/{total}")

            # Run OCR conversion
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

            # Read result
            latex = Path(output_path).read_text(encoding="utf-8")

            # Update job as completed
            database.update_job_status(
                job_id, "completed", latex=latex, output_path=output_path
            )
            log.info(f"Job {job_id} completed successfully")

        except CancelledException:
            database.update_job_status(job_id, "cancelled")
            log.info(f"Job {job_id} was cancelled during processing")

        except Exception as e:
            log.error(f"Job {job_id} failed: {e}")
            database.update_job_status(job_id, "failed", error=str(e))

        finally:
            # Clean up cancellation event
            if job_id in self.cancellation_events:
                del self.cancellation_events[job_id]


# Global job queue instance
_job_queue: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    """Get the global job queue instance"""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue()
    return _job_queue
