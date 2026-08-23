# Roadmap

Prioritized, roughly highest-impact first. Not a commitment or a schedule.

1. Moved-text detection, so a paragraph moved elsewhere on the page is reported as "moved" instead of a delete+add pair
2. Font-name-swap detection beyond bold/italic/size (e.g. a full typeface change)
3. Vertical text (tategaki) support
4. Table-aware diff using `page.find_tables`, so cell edits don't get reported as unstructured text noise
5. OCR extra for scan-only PDFs, so word-level diffs work without a pre-existing text layer
6. Non-monotonic page alignment, to handle reordered chapters/sections
7. Affine scan registration, beyond the current translation-only correction
8. Annotation reflow tolerance, so an annotation that shifts slightly with reflowed text isn't reported as removed+added
9. Highlight-over-unchanged-word grouping fix
10. ~~Split `engine.py` into submodules as it continues to grow~~ (done in 0.1.5)
11. CI matrix hardening (more platforms, pinned dependency ranges, coverage reporting)
12. Process-pool isolation for `compare_pdfs`, so a timed-out comparison job can actually be `terminate()`-d instead of merely abandoned in a thread
13. ~~Docker base-image digest pinning (`node:26-alpine`, `python:3.14-slim`) instead of mutable tags~~ (done in 0.1.5)
14. Evaluate a dependency lockfile (`pip-compile`/`uv lock`) for reproducible, reviewable Python dependency bumps (major-version upper bounds were added in 0.1.5)
15. Global job-storage quota (bounded total bytes/job count across `JOBS_DIR`, with eviction), so many completed jobs can't fill the volume within `JOB_TTL_HOURS` — item 12's process-pool isolation is the other half of bounding a single misbehaving job; this one bounds accumulation across many of them
