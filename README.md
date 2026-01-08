# Math OCR

Convert handwritten math notes (PDF) to LaTeX using Google Gemini 3 Flash.

## Architecture

### System Overview
```
+------------------+       HTTP        +------------------+
|                  |  POST /convert    |                  |
|   Next.js App    | ---------------->|   FastAPI        |
|   (port 3000)    | <---------------- |   (port 8000)    |
|                  |   JSON response   |                  |
+------------------+                   +------------------+
        |                                      |
        v                                      v
   localStorage                         Gemini 3 Flash API
   (history)                            (PDF -> LaTeX)
```

### Python Backend Pipeline
```
PDF Input
    |
    v
+-------------------+
| pdf2image         |  Convert pages to images
+-------------------+
    |
    v
+-------------------+
| Pass 1: Extract   |  Page-by-page with context
| (PAGE_PROMPT)     |  Cached per page
+-------------------+
    |
    v
+-------------------+
| Pass 2: Refine    |  Unify notation, add preamble
| (REFINE_PROMPT)   |
+-------------------+
    |
    v (optional)
+-------------------+
| Pass 3: Compile   |  pdflatex + fix errors
| (FIX_PROMPT)      |
+-------------------+
    |
    v
LaTeX Output
```

## Quick Start

### 1. Install Dependencies

**System dependencies:**
```bash
# macOS
brew install poppler

# Ubuntu
sudo apt-get install poppler-utils
```

**Python & Node.js dependencies:**
```bash
# Install uv (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies
npm install
uv sync
```

### 2. Set API Key

```bash
export GEMINI_API_KEY="your-api-key-here"
```

Get your key: https://aistudio.google.com/apikey

### 3. Start

```bash
./start.sh
```

Open http://localhost:3000

## What's Remaining

**Job Queue System** (see PLAN-job-queue.md for details):
- SQLite persistence for job history
- Progress tracking (current page / total pages)
- Job cancellation support
- Auto-cleanup after 7 days

This will replace the current localStorage-based history with a proper queue system that persists across page refreshes and server restarts.

## File Structure

```
math-ocr-app/
├── api_server.py          # FastAPI server
├── ocr.py                 # Multi-pass conversion engine
├── prompts.py             # Gemini AI prompts
├── requirements.txt       # Python dependencies
├── pyproject.toml         # uv configuration
├── app/
│   ├── page.tsx           # Main UI component
│   ├── layout.tsx         # Root layout
│   └── globals.css        # Tailwind CSS styles
├── package.json           # Node.js dependencies
├── start.sh               # Quick start script
└── kill-servers.sh        # Stop servers script
```

## Usage

**Web UI:** Upload PDF via drag-and-drop at http://localhost:3000

**CLI:**
```bash
# Basic conversion
uv run python ocr.py notes.pdf output.tex

# With compile check
uv run python ocr.py notes.pdf --enable-compile-check

# Clear cache
uv run python ocr.py notes.pdf --clear-cache
```

**API:** See interactive docs at http://localhost:8000/docs

## Troubleshooting

**"No API key" error:**
```bash
export GEMINI_API_KEY="your-key"
```

**"poppler not found" error:**
```bash
brew install poppler  # macOS
sudo apt-get install poppler-utils  # Ubuntu
```

**Servers won't stop:**
```bash
./kill-servers.sh
```

## License

MIT
