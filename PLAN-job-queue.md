# Math OCR App - Job Queue System Implementation Plan

## Overview

Add a persistent job queue system to the Math OCR app so that:
- Jobs persist across page refreshes and server restarts (SQLite)
- Users see queued, running, and completed jobs globally
- Running jobs can be cancelled (nice-to-have)
- Jobs auto-cleanup after 7 days

## Architecture

```
Frontend (Next.js) ─── polls every 2s ───> GET /jobs
        │                                      │
        └── POST /jobs ──────────────────> API Server
                                               │
                                          ┌────┴────┐
                                          │ SQLite  │
                                          │ jobs.db │
                                          └────┬────┘
                                               │
                                    ┌──────────┴──────────┐
                                    │  Background Worker  │
                                    │  (threading.Thread) │
                                    └──────────┬──────────┘
                                               │
                                          ocr.convert()
```

## Files to Create

### 1. `database.py` (NEW)

SQLite persistence layer with schema:

```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,              -- UUID
    filename TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL,             -- queued/running/completed/failed/cancelled
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER DEFAULT 0,
    current_pass TEXT,                -- pass_1/pass_2/pass_3
    pdf_path TEXT,
    output_path TEXT,
    latex TEXT,
    error TEXT,
    enable_compile_check BOOLEAN DEFAULT 0,
    created_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL
);
```

Operations: `create_job()`, `get_job()`, `list_jobs()`, `update_job_status()`, `update_job_progress()`, `delete_job()`, `cleanup_old_jobs()`

### 2. `job_queue.py` (NEW)

Background worker using `threading.Thread` + `queue.Queue`:
- Single worker thread processes jobs sequentially
- `cancellation_events: Dict[str, threading.Event]` for cancellation
- Calls `ocr.convert()` with progress callback
- Updates database after each page

## Files to Modify

### 3. `ocr.py`

Add to `convert()` function signature:
```python
def convert(
    ...,
    cancellation_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> str:
```

In page loop (around line 235-250):
- Check `cancellation_event.is_set()` before each page
- Call `progress_callback(current_page, total_pages, "pass_1")` after each page
- Raise `CancellationException` if cancelled

### 4. `api_server.py`

Add new endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/jobs` | POST | Submit new job (returns immediately with job_id) |
| `/jobs` | GET | List all jobs (limit, status filter) |
| `/jobs/{id}` | GET | Get single job status |
| `/jobs/{id}/cancel` | POST | Cancel running/queued job |
| `/jobs/{id}` | DELETE | Delete completed/failed job |
| `/jobs/{id}/download` | GET | Download .tex file |

Add startup/shutdown handlers:
- Initialize database and start worker thread
- Start hourly cleanup task (delete jobs older than 7 days)

### 5. `app/page.tsx`

Replace localStorage history with job queue:

**Remove:**
- `history` state and localStorage logic
- `saveToHistory()` function
- History section in UI

**Add:**
- `jobs` state with polling (every 2 seconds)
- `handleConvert()` → POST to `/jobs`, returns immediately
- `handleCancelJob(jobId)` → POST to `/jobs/{id}/cancel`
- `handleDeleteJob(jobId)` → DELETE `/jobs/{id}`
- Job list UI with:
  - Status badges (queued/running/completed/failed/cancelled)
  - Progress bar for running jobs (page X/Y)
  - Cancel button (running jobs only)
  - View/Download/Delete buttons (completed jobs)

## File Storage

```
jobs/
├── <job_id>/
│   ├── input.pdf
│   ├── output.tex
│   └── output.cache/
```

## Implementation Order

1. **Backend foundation**: Create `database.py` and `job_queue.py`
2. **Modify OCR**: Add cancellation + progress to `ocr.py`
3. **API endpoints**: Add job endpoints to `api_server.py`
4. **Frontend**: Update `page.tsx` with job queue UI
5. **Testing**: End-to-end testing of full flow

## Key Design Decisions

- **No new dependencies**: Uses Python stdlib only (sqlite3, threading, queue)
- **Single worker thread**: Sequential processing prevents resource exhaustion
- **2-second polling**: Simple, reliable (WebSockets can be added later)
- **Global visibility**: No auth needed, all sessions see all jobs
- **Keep legacy `/convert`**: Backward compatibility
