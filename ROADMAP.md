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
10. Split `engine.py` into submodules as it continues to grow
11. CI matrix hardening (more platforms, pinned dependency ranges, coverage reporting)
