#!/usr/bin/env python3
"""RQ worker entrypoint for OCR jobs."""

import os
import sys

# Avoid macOS fork safety crash with Objective-C libs used by pdf2image/PIL.
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

from redis import Redis
from rq import Worker, Queue
from rq.worker import SimpleWorker

from job_queue import process_job

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


if __name__ == "__main__":
    redis_conn = Redis.from_url(REDIS_URL)
    queue = Queue("ocr", connection=redis_conn)
    worker_cls = SimpleWorker if sys.platform == "darwin" else Worker
    worker_cls([queue], connection=redis_conn, name="ocr-worker").work()
