#!/usr/bin/env python3
"""RQ worker entrypoint for OCR jobs."""

import os

from redis import Redis
from rq import Worker, Queue, Connection

from job_queue import process_job

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


if __name__ == "__main__":
    with Connection(Redis.from_url(REDIS_URL)):
        Worker([Queue("ocr")], name="ocr-worker").work()
