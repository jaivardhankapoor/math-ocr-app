#!/usr/bin/env python3
"""SQLite database layer for job queue persistence"""

import sqlite3
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


class RateLimitExceeded(Exception):
    def __init__(self, count: int, limit: int):
        super().__init__(f"Daily limit reached ({count}/{limit})")
        self.count = count
        self.limit = limit

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
        # Users table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                image TEXT,
                tier TEXT DEFAULT 'free',
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                created_at REAL NOT NULL
            )
        """
        )

        # Jobs table
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
                user_id TEXT,
                created_at REAL NOT NULL,
                started_at REAL,
                completed_at REAL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """
        )

        # Create index for user_id lookups
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id)"
        )

        conn.commit()


def create_user(
    user_id: str, email: str, name: Optional[str] = None, image: Optional[str] = None
) -> Dict[str, Any]:
    """Create or update a user"""
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, name, image, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                email=excluded.email,
                name=excluded.name,
                image=excluded.image
        """,
            (user_id, email, name, image, time.time()),
        )
        conn.commit()
        return get_user(user_id)


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get a user by ID"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get a user by email"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        return dict(row) if row else None


def list_users(limit: int = 100) -> List[Dict[str, Any]]:
    """List all users"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def update_user_tier(
    user_id: str,
    tier: str,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
):
    """Update user tier and Stripe info"""
    with get_db() as conn:
        updates = ["tier = ?"]
        params = [tier]

        if stripe_customer_id is not None:
            updates.append("stripe_customer_id = ?")
            params.append(stripe_customer_id)

        if stripe_subscription_id is not None:
            updates.append("stripe_subscription_id = ?")
            params.append(stripe_subscription_id)

        params.append(user_id)

        conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params
        )
        conn.commit()


def get_user_job_count_24h(user_id: str) -> int:
    """Count jobs submitted by user in last 24 hours"""
    cutoff = time.time() - (24 * 60 * 60)
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE user_id = ? AND created_at > ?",
            (user_id, cutoff),
        ).fetchone()
        return row[0] if row else 0


def create_job(
    job_id: str,
    filename: str,
    user_id: str,
    title: Optional[str] = None,
    enable_compile_check: bool = False,
) -> Dict[str, Any]:
    """Create a new job in queued status"""
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, filename, title, status, enable_compile_check, user_id, created_at
            ) VALUES (?, ?, ?, 'queued', ?, ?, ?)
        """,
            (job_id, filename, title, enable_compile_check, user_id, time.time()),
        )
        conn.commit()
        return get_job(job_id)


def create_job_with_limit(
    job_id: str,
    filename: str,
    user_id: str,
    title: Optional[str] = None,
    enable_compile_check: bool = False,
    daily_limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a job with optional daily usage limit enforcement"""
    cutoff = time.time() - (24 * 60 * 60)
    with get_db() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")

            if daily_limit is not None:
                row = conn.execute(
                    "SELECT COUNT(*) FROM jobs WHERE user_id = ? AND created_at > ?",
                    (user_id, cutoff),
                ).fetchone()
                count = row[0] if row else 0
                if count >= daily_limit:
                    raise RateLimitExceeded(count=count, limit=daily_limit)

            conn.execute(
                """
                INSERT INTO jobs (
                    id, filename, title, status, enable_compile_check, user_id, created_at
                ) VALUES (?, ?, ?, 'queued', ?, ?, ?)
            """,
                (job_id, filename, title, enable_compile_check, user_id, time.time()),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return get_job(job_id)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a single job by ID"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def list_jobs(
    limit: int = 100, status: Optional[str] = None, user_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List jobs with optional status and user_id filter"""
    with get_db() as conn:
        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM jobs WHERE {where_clause} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
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


def cleanup_old_jobs(days: int = 7) -> List[str]:
    """Delete jobs older than specified days, returning affected job directories"""
    cutoff = time.time() - (days * 24 * 60 * 60)
    deleted_paths: List[str] = []
    with get_db() as conn:
        rows = conn.execute(
            "SELECT pdf_path FROM jobs WHERE created_at < ?", (cutoff,)
        ).fetchall()
        deleted_paths = [row["pdf_path"] for row in rows if row["pdf_path"]]

        conn.execute("DELETE FROM jobs WHERE created_at < ?", (cutoff,))
        conn.commit()
        return deleted_paths
