"""Prompts for PDF → LaTeX conversion via Gemini 3 Flash"""

PAGE_PROMPT = """You convert handwritten math to clean, compilable LaTeX.

Context: page {i}/{n} of "{title}". Continue notation from previous pages if any.

Rules:
- Use $...$ and \\[...\\]; use align/equation/gather as needed for multi-line equations
- Keep definitions/theorems/proofs as environments (\\begin{{theorem}}, etc.) if clearly indicated
- Preserve logical breaks; no \\documentclass; no markdown fences
- If unclear: % [UNCLEAR: best guess]; diagrams as % [DIAGRAM: description]

Return only the LaTeX body for this page."""

REFINE_PROMPT = """You are a LaTeX editor. Given page bodies from "{title}", output a complete, compilable document:

Requirements:
- Proper preamble (\\documentclass{{article}}, amsmath, amssymb, amsfonts, amsthm, hyperref)
- \\title, \\author, \\date with a note that this was auto-converted from handwritten notes
- Unify notation across pages; fix unmatched braces/environments; remove duplicates
- Add \\section and \\subsection if obvious from content structure
- {labels}
- Keep [UNCLEAR] and [DIAGRAM] notes as LaTeX comments

Return full document from \\documentclass to \\end{{document}}. ONLY the LaTeX document, no additional comments or markdown.

Pages:
{body}"""

FIX_PROMPT = """LaTeX failed to compile. Fix syntax errors only; keep all content/structure unchanged.

Errors/log:
{errs}

Current document:
{doc}

Return the corrected full document. ONLY the LaTeX document, no comments. The output should compile with pdflatex."""
