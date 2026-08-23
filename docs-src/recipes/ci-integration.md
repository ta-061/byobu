# Recipe: summarize a PDF diff in CI

A common use case: a CI job builds a PDF from source (LaTeX, Word export,
generated report) and you want a short changed/unchanged summary — for
example, posted as a PR comment — without paying for three marked PDFs your
CI job will just discard.

```python
import json
import sys

import kogo

result = kogo.compare_pdfs(
    "old/build/paper.pdf",
    "new/build/paper.pdf",
    "out/",
    artifacts=False,  # skip old/new/side-by-side.pdf; result.json is still written
)

summary = result["summary"]
if summary["changed_pages"] == 0:
    print("No changes detected.")
    sys.exit(0)

print(
    f"{summary['changed_pages']} of {summary['compared_rows']} pages changed "
    f"(+{summary['added_words']} / -{summary['deleted_words']} words, "
    f"{summary['visual_regions']} visual regions, "
    f"{summary['style_changes']} style-only changes)"
)

# result["rows"] has per-page snippets if you want more detail, e.g. in a PR comment:
for row in result["rows"]:
    if row["has_changes"] and row["changes"]["added_snippets"]:
        print(f"  page {row.get('new', {}).get('page')}: + {row['changes']['added_snippets'][0]!r}")
```

If you do want the marked PDFs as CI artifacts (e.g. to attach to the job),
drop `artifacts=False` and upload `out/old-highlighted.pdf`,
`out/new-highlighted.pdf`, and `out/side-by-side.pdf` as build artifacts.

For a comparison that may take a while (large documents, many pages), use
`on_progress` to stream status into the job log instead of it looking stuck:

```python
def log_progress(phase: str, current: int, total: int) -> None:
    if phase == "comparing":
        print(f"::debug::comparing page {current}/{total}", flush=True)

kogo.compare_pdfs("old.pdf", "new.pdf", "out/", on_progress=log_progress)
```
