#!/usr/bin/env python3
"""SQLite database layer for job queue persistence"""

import sqlite3
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

DB_PATH = Path("jobs.db")


@contextmanager
def get_db():
    """Context manager for thread-safe database connections"""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database schema"""
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                title TEXT,
                status TEXT NOT NULL,
                progress_current INTEGER DEFAULT 0,
                progress_total INTEGER DEFAULT 0,
                current_pass TEXT,
                pdf_path TEXT,
                output_path TEXT,
                latex TEXT,
                error TEXT,
                enable_compile_check BOOLEAN DEFAULT 0,
                created_at REAL NOT NULL,
                started_at REAL,
                completed_at REAL
            )
        """
        )
        conn.commit()


def create_job(
    job_id: str,
    filename: str,
    title: Optional[str] = None,
    enable_compile_check: bool = False,
) -> Dict[str, Any]:
    """Create a new job in queued status"""
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, filename, title, status, enable_compile_check, created_at
            ) VALUES (?, ?, ?, 'queued', ?, ?)
        """,
            (job_id, filename, title, enable_compile_check, time.time()),
        )
        conn.commit()
        return get_job(job_id)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a single job by ID"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def list_jobs(
    limit: int = 100, status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List jobs with optional status filter"""
    with get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]


def update_job_status(
    job_id: str,
    status: str,
    error: Optional[str] = None,
    latex: Optional[str] = None,
    output_path: Optional[str] = None,
):
    """Update job status and optional fields"""
    with get_db() as conn:
        # Build dynamic update query
        updates = ["status = ?"]
        params = [status]

        if error is not None:
            updates.append("error = ?")
            params.append(error)

        if latex is not None:
            updates.append("latex = ?")
            params.append(latex)

        if output_path is not None:
            updates.append("output_path = ?")
            params.append(output_path)

        # Set timestamps
        if status == "running":
            updates.append("started_at = ?")
            params.append(time.time())
        elif status in ("completed", "failed", "cancelled"):
            updates.append("completed_at = ?")
            params.append(time.time())

        params.append(job_id)

        conn.execute(
            f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()


def update_job_progress(
    job_id: str, current: int, total: int, current_pass: str
):
    """Update job progress"""
    with get_db() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET progress_current = ?, progress_total = ?, current_pass = ?
            WHERE id = ?
        """,
            (current, total, current_pass, job_id),
        )
        conn.commit()


def update_job_paths(job_id: str, pdf_path: str, output_path: str):
    """Update job file paths"""
    with get_db() as conn:
        conn.execute(
            "UPDATE jobs SET pdf_path = ?, output_path = ? WHERE id = ?",
            (pdf_path, output_path, job_id),
        )
        conn.commit()


def delete_job(job_id: str):
    """Delete a job from database"""
    with get_db() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()


def cleanup_old_jobs(days: int = 7):
    """Delete jobs older than specified days"""
    cutoff = time.time() - (days * 24 * 60 * 60)
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM jobs WHERE created_at < ?", (cutoff,)
        )
        deleted = cursor.rowcount
        conn.commit()
        return deleted
