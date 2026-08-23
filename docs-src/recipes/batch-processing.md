# Recipe: batch-compare a directory of PDF pairs

Comparing many revisions at once — a folder of `*-old.pdf`/`*-new.pdf` pairs
from a shared drive, or every chapter of a book — without a shell loop
re-invoking the CLI (and paying process startup cost) for each pair.

```python
from pathlib import Path

import kogo

def find_pairs(directory: Path) -> list[tuple[Path, Path]]:
    pairs = []
    for old_path in sorted(directory.glob("*-old.pdf")):
        new_path = old_path.with_name(old_path.name.replace("-old.pdf", "-new.pdf"))
        if new_path.exists():
            pairs.append((old_path, new_path))
    return pairs

results = []
for old_path, new_path in find_pairs(Path("revisions/")):
    out_dir = Path("out") / old_path.stem.removesuffix("-old")
    try:
        result = kogo.compare_pdfs(old_path, new_path, out_dir, artifacts=False)
    except kogo.ComparisonError as exc:
        print(f"{old_path.name}: skipped - {exc}")
        continue
    results.append((old_path.name, result["summary"]))

# A CSV/JSON rollup across every pair, e.g. for a spreadsheet or dashboard:
import csv
import sys

writer = csv.writer(sys.stdout)
writer.writerow(["file", "changed_pages", "added_words", "deleted_words", "visual_regions"])
for name, summary in results:
    writer.writerow(
        [name, summary["changed_pages"], summary["added_words"], summary["deleted_words"], summary["visual_regions"]]
    )
```

Notes:

- `kogo.ComparisonError` is the only exception `compare_pdfs` raises for
  user-facing problems (encrypted, empty, oversized, or unreadable PDFs) —
  catch it per pair so one bad file doesn't abort the whole batch.
- `artifacts=False` matters more here than for a single comparison: with
  hundreds of pairs, skipping the marked-PDF writes for pairs you're only
  summarizing avoids a proportional amount of disk I/O. Drop it for the
  specific pairs you actually want marked PDFs for.
- Each `compare_pdfs` call opens its own PDFs and does its own page
  rendering — there's no cross-call state to reuse, so parallelizing across
  pairs (e.g. with `concurrent.futures.ProcessPoolExecutor`) is safe and
  straightforward if I/O or CPU throughput matters more than simplicity.
