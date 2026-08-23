# Changelog

## 0.1.6 - 2026-08-23 - Library API round-out & project infrastructure

- Library API: `compare_pdfs` return type is now the typed `ComparisonResult` (and nested `Files`/`Settings`/`Summary`/`Legend`/`Artifacts`/`ArtifactInfo`/`Row`/`RowChanges`/`PageRef`) `TypedDict`s, exported from `kogo` for IDE/type-checker support. Runtime shape is unchanged.
- Library API: new `artifacts: bool = True` keyword — set to `False` to skip baking/saving the marked PDFs (and `_comparison_pdf`) when only the JSON summary is needed, e.g. in a CI step; `result["artifacts"]` is `None` in that case.
- Library API: new `on_progress` keyword — an optional `(phase, current, total)` callback invoked as a comparison runs (`"aligned"`, `"comparing"` per row, `"rendering"`, `"previews"`). `kogo diff` now shows row-by-row progress on stderr when not run with `--json`.
- Project: added GitHub issue/PR templates, `CODE_OF_CONDUCT.md`, enabled Discussions, and set the repo homepage.
- Project: added a documentation site (`docs-src/`, mkdocs-material + mkdocstrings) published at kogo.tatu-sec.dev/manual/, alongside the existing docstrings and README.

## 0.1.5 - 2026-08-23 - Maintainability & supply-chain hardening

- Internal: split engine.py into the kogo.engine package (words/alignment/text_diff/visual_diff/annotations/render/compare). Public API unchanged.
- Dockerfile: base images pinned by digest (node:26-alpine, python:3.14-slim)
- Dependencies: major-version upper bounds added (PyMuPDF<2, numpy<3, opencv-python-headless<5, fastapi<1, uvicorn<1, python-multipart<1)

## 0.1.4 - 2026-08-23 - Security hardening release

Findings from an internal security/code audit; see individual items below.

- Active PDF content (JavaScript, `/OpenAction`, embedded/attached files, and `Launch`/`GoToR`-class link actions) is now stripped from both input documents before any processing, so a malicious uploaded PDF can no longer be re-baked and redistributed through the output PDFs (A1)
- `/api/compare` now rejects oversized request bodies by `Content-Length` before Starlette buffers them, and wraps the comparison in a configurable wall-clock timeout (`JOB_TIMEOUT_SECONDS`, default 900s) so a pathological upload can no longer permanently exhaust the concurrency semaphore (A2)
- Page rendering (visual diff and previews) is now clamped to a 40-megapixel budget, mirroring the existing page-signature safeguard, preventing multi-gigabyte allocations from PDFs with oversized page boxes (A3)
- `docker-compose.yml` now sets `mem_limit`, `cpus`, and `pids_limit` as a resource backstop for the native PDF/image parsers (A4)
- `kogo fetch-viewer` now verifies a pinned SHA-256 checksum of the downloaded `pdfjs-dist` tarball and rejects any tar member that would extract outside the destination directory (A5)
- The web app footer and `kogo serve` startup banner now read the "Source code" link from `KOGO_SOURCE_URL`, so operators of a modified deployment can point it at their own fork to satisfy AGPL-3.0 §13 (A6)
- Added baseline security response headers (`X-Content-Type-Options`, `Referrer-Policy`, `Content-Security-Policy`) to every response (A7)
- Job directories are now created after acquiring the processing semaphore rather than before (A8)
- GitHub Actions in `ci.yml`/`pages.yml`/`publish.yml` are now pinned to commit SHAs instead of mutable tags
- Removed the dead, unused `_text_differences` helper from `engine.py`
- New tests: oversized-page render clamping, active-content scrubbing regression, `fetch-viewer` path-traversal rejection, artifact allowlist rejection, and security headers presence

## 0.1.3 - 2026-08-23 - Library documentation

- Full docstring for `kogo.compare_pdfs` (usable via `help()` and IDEs)
- `py.typed` marker: the package is now PEP 561 typed
- Project site: API result-structure table added (EN/JA)

## 0.1.2 - 2026-08-23 - Project site, PyPI page fix

- Project website published (GitHub Pages): https://portfolio.tatu-sec.dev/kogo/
- README screenshot now uses an absolute URL so it renders on the PyPI project page

## 0.1.1 - 2026-08-22 - Library API

- Export `compare_pdfs` and `ComparisonError` from the top-level `kogo` package so `import kogo` is enough to use the diff engine as a library
- `compare_pdfs` `old_name` / `new_name` are now optional and default to the input file names

## 0.1.0 - 2026-08-22 - Initial release

Initial release of kogo. The project was formerly prototyped under the name "byobu"; it was renamed before PyPI publication to avoid collision with the existing `byobu` terminal multiplexer.

- Word-level text diff for Latin text, character-level diff for CJK text (including rare kanji across CJK Extensions B-J), with reading order reconstructed from page layout
- Similarity-based page alignment tolerant of inserted or removed pages
- Visual diff for figures, equations, and layout, with text areas masked out and registration for scanned pages
- Detection of added or removed highlights, comments, and ink annotations
- Style-change detection (bold, italic, font-size changes on otherwise-unchanged text)
- Markers baked into output PDFs so they show up in any viewer
- Web app with a selectable-text PDF.js preview, page-by-page diff view, and downloadable marked-up PDFs
- CLI (`kogo diff`) for scripted comparisons
- Docker image bundling the PDF.js viewer assets
