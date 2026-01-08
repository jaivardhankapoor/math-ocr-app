#!/usr/bin/env python3
"""PDF → LaTeX via Gemini 3 Flash. Usage: python ocr.py input.pdf [output.tex]"""

import json
import logging
import os
import sys
import threading
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Callable

from google import genai
from google.genai import types
from pdf2image import convert_from_path
from PIL import Image

from prompts import FIX_PROMPT, PAGE_PROMPT, REFINE_PROMPT

MODEL = "gemini-3-flash-preview"
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


class CancelledException(Exception):
    """Raised when a job is cancelled"""
    pass


def image_to_part(img: Image.Image) -> types.Part:
    """Convert PIL Image to Gemini Part"""
    buf = BytesIO()
    img.save(buf, format="PNG")
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")


def extract_page(
    client: genai.Client,
    img: Image.Image,
    page_num: int,
    total_pages: int,
    title: str,
    prev_latex: Optional[str] = None,
) -> str:
    """Extract LaTeX from single page with optional context from previous page"""
    prompt = PAGE_PROMPT.format(i=page_num, n=total_pages, title=title)
    if prev_latex:
        prompt += (
            f"\n\n(Previous page provided for continuity; maintain consistent notation)"
        )

    contents = [prompt, image_to_part(img)]
    if prev_latex:
        contents.append(f"Previous page LaTeX:\n{prev_latex}")  # Limit context

    try:
        log.info(f"  Calling Gemini API for page {page_num}...")
        resp = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(temperature=0.1, candidate_count=1),
        )
        log.info(f"  ✓ Received response for page {page_num}")
    except Exception as e:
        log.error(f"  ✗ Error on page {page_num}: {e}")
        return f"% Page {page_num}: ERROR - {str(e)}\n"

    text = (resp.text or "").strip()
    if not text:
        log.warning(f"  ⚠ Page {page_num}: empty response")
        return f"% Page {page_num}: no content\n"

    return f"% Page {page_num}\n{text}\n"


def refine(
    client: genai.Client, pages: List[str], title: str, insert_labels: bool = True
) -> str:
    """Global refinement pass to unify document"""
    labels_instruction = (
        "Insert \\label{...} for theorems/definitions/examples and reference them with \\ref where appropriate."
        if insert_labels
        else "Do not add labels or references."
    )

    # Strip page markers, keep bodies only
    bodies = [
        "\n".join(line for line in p.splitlines() if not line.startswith("% Page"))
        for p in pages
        if "no content" not in p.lower()
    ]

    joined = "\n\n% ==== PAGE BREAK ====\n\n".join([b for b in bodies if b.strip()])
    if not joined:
        return ""

    prompt = REFINE_PROMPT.format(title=title, labels=labels_instruction, body=joined)

    resp = client.models.generate_content(
        model=MODEL,
        contents=[prompt],
        config=types.GenerateContentConfig(temperature=0.15, candidate_count=1),
    )

    result = (resp.text or "").strip()

    # Extract LaTeX from markdown code blocks if present
    import re

    for pattern in [
        r"```latex\s*\n(.*?)\n```",
        r"```tex\s*\n(.*?)\n```",
        r"```\s*\n(.*?)\n```",
    ]:
        matches = re.findall(pattern, result, re.DOTALL | re.IGNORECASE)
        if matches and "\\documentclass" in matches[0]:
            result = matches[0].strip()
            break

    return result


def compile_fix(
    client: genai.Client, doc: str, output_path: Path, max_attempts: int = 2
) -> str:
    """Optional compile check with error fixing"""
    import subprocess

    current = doc
    for attempt in range(1, max_attempts + 1):
        log.info(f"Compile check {attempt}/{max_attempts}...")

        tmp = output_path.parent / f"__tmp_{attempt}.tex"
        tmp.write_text(current, encoding="utf-8")

        # Run pdflatex
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tmp.name],
            cwd=tmp.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )

        # Clean up temp files
        for ext in [".aux", ".log", ".pdf", ".out", ".toc", ".tex"]:
            p = tmp.with_suffix(ext)
            if p.exists():
                p.unlink()

        if result.returncode == 0:
            log.info("✓ Compilation successful")
            return current

        # Parse errors
        output_lines = result.stdout + result.stderr
        errors = [
            line.strip()
            for line in output_lines.splitlines()
            if line.strip()
            and (
                line.startswith("!")
                or any(
                    kw in line.lower()
                    for kw in ["error", "undefined", "missing", "runaway"]
                )
            )
        ][:20]  # Limit to first 20 errors

        if attempt == max_attempts:
            log.warning(
                f"✗ Max compile attempts reached. Returning document with potential errors."
            )
            break

        # Ask Gemini to fix
        log.info(f"Found {len(errors)} errors, asking Gemini to fix...")
        fix_prompt = FIX_PROMPT.format(errs="\n".join(errors), doc=current)

        resp = client.models.generate_content(
            model=MODEL,
            contents=[fix_prompt],
            config=types.GenerateContentConfig(temperature=0.1, candidate_count=1),
        )

        fixed = (resp.text or "").strip()
        if fixed and len(fixed) > 100:
            current = fixed
        else:
            log.warning("Gemini returned invalid fix, keeping original")
            break

    return current


def convert(
    pdf_path: str,
    output: Optional[str] = None,
    api_key: Optional[str] = None,
    title: Optional[str] = None,
    enable_compile_check: bool = False,
    use_cache: bool = True,
    clear_cache: bool = False,
    cancellation_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> str:
    """
    Convert PDF to LaTeX using 2-pass (or 3-pass if compile check enabled).

    Pass 1: Sequential page extraction with context
    Pass 2: Global refinement
    Pass 3: Optional compile check (disabled by default)

    Args:
        cancellation_event: Event to signal cancellation
        progress_callback: Called with (current_page, total_pages, pass_name)
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    api_key = api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("No API key: use --api-key or set GEMINI_API_KEY")

    client = genai.Client(api_key=api_key)
    out_path = Path(output or pdf_path).with_suffix(".tex")
    cache_dir = out_path.with_suffix(".cache")
    title = title or pdf_path.stem.replace("_", " ").replace("-", " ").title()

    log.info(f"Converting: {pdf_path} → {out_path}")
    log.info(f"Title: {title}")

    # Clear cache if requested
    if clear_cache and cache_dir.exists():
        import shutil

        shutil.rmtree(cache_dir)

    # Pass 1: Sequential page extraction
    log.info("Pass 1: Sequential page extraction with context...")
    images = convert_from_path(str(pdf_path), dpi=200)
    pages = []
    prev_latex = None

    for i, img in enumerate(images, 1):
        # Check for cancellation
        if cancellation_event and cancellation_event.is_set():
            log.info("Cancellation requested")
            raise CancelledException("Job was cancelled")

        cache_file = (cache_dir / f"page_{i:03d}.tex") if use_cache else None

        if cache_file and cache_file.exists():
            log.info(f"  Page {i}/{len(images)}: cache hit")
            latex = cache_file.read_text(encoding="utf-8")
        else:
            log.info(f"  Page {i}/{len(images)}: processing...")
            latex = extract_page(client, img, i, len(images), title, prev_latex)

            if cache_file:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(latex, encoding="utf-8")

        pages.append(latex)
        prev_latex = latex

        # Report progress
        if progress_callback:
            progress_callback(i, len(images), "pass_1")

    # Save cache metadata
    if use_cache:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "model": MODEL,
                    "pages": len(images),
                    "title": title,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    # Pass 2: Global refinement
    log.info("Pass 2: Global refinement...")
    if progress_callback:
        progress_callback(0, 1, "pass_2")
    doc = refine(client, pages, title) or "\n\n".join(pages)
    if progress_callback:
        progress_callback(1, 1, "pass_2")

    # Pass 3: Optional compile check
    if enable_compile_check and doc:
        log.info("Pass 3: Compile check and error fixing...")
        if progress_callback:
            progress_callback(0, 1, "pass_3")
        doc = compile_fix(client, doc, out_path)
        if progress_callback:
            progress_callback(1, 1, "pass_3")

    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    log.info(f"✓ Done: {out_path}")

    if use_cache and cache_dir.exists():
        log.info(
            f"  Cache: {len(list(cache_dir.glob('page_*.tex')))} pages in {cache_dir}"
        )

    return str(out_path)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="PDF → LaTeX via Gemini 3 Flash (2-pass default)"
    )
    parser.add_argument("pdf_path", help="Input PDF file")
    parser.add_argument("output_path", nargs="?", help="Output .tex file (optional)")
    parser.add_argument(
        "--api-key", help="Gemini API key (or set GEMINI_API_KEY env var)"
    )
    parser.add_argument("--title", help="Document title (optional)")
    parser.add_argument(
        "--enable-compile-check",
        action="store_true",
        help="Enable 3rd pass: compile check",
    )
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    parser.add_argument(
        "--clear-cache", action="store_true", help="Clear cache before running"
    )

    args = parser.parse_args()

    try:
        result = convert(
            pdf_path=args.pdf_path,
            output=args.output_path,
            api_key=args.api_key,
            title=args.title,
            enable_compile_check=args.enable_compile_check,
            use_cache=not args.no_cache,
            clear_cache=args.clear_cache,
        )
        print(f"\n✓ Conversion complete: {result}")
        print(f'Compile with: pdflatex "{result}"')
    except Exception as e:
        log.error(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
