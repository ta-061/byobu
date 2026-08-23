# Recipe: comment a LaTeX diff summary on every PR

kogo (校合) is named after the Japanese publishing term for checking a
revision against the original — this is that workflow, automated: a GitHub
Actions job builds a LaTeX paper on both sides of a pull request, compares
the two PDFs, and posts what changed as a PR comment, so reviewers see a
substantive summary before opening either file.

## Workflow

```yaml
name: Paper diff

on:
  pull_request:
    paths:
      - "paper/**"

permissions:
  pull-requests: write

jobs:
  diff:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout PR (new)
        uses: actions/checkout@v5
        with:
          path: new

      - name: Checkout base (old)
        uses: actions/checkout@v5
        with:
          ref: ${{ github.event.pull_request.base.sha }}
          path: old

      - name: Build both PDFs
        uses: xu-cheng/latex-action@v4
        with:
          working_directory: new/paper
          root_file: paper.tex
      - uses: xu-cheng/latex-action@v4
        with:
          working_directory: old/paper
          root_file: paper.tex

      - name: Install kogo
        run: pip install kogo

      - name: Compare and comment
        run: python .github/scripts/comment_paper_diff.py
        env:
          GH_TOKEN: ${{ github.token }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
```

## `.github/scripts/comment_paper_diff.py`

```python
import os
import subprocess

import kogo

result = kogo.compare_pdfs(
    "old/paper/paper.pdf",
    "new/paper/paper.pdf",
    "out/",
    artifacts=False,  # this job only needs the summary, not marked PDFs
)
summary = result["summary"]

if summary["changed_pages"] == 0:
    body = "No visible changes in the built PDF."
else:
    lines = [
        f"**{summary['changed_pages']} of {summary['compared_rows']} pages changed** "
        f"(+{summary['added_words']} / -{summary['deleted_words']} words, "
        f"{summary['visual_regions']} figure/layout regions, "
        f"{summary['style_changes']} style-only changes)",
        "",
    ]
    for row in result["rows"]:
        snippets = row["changes"]["added_snippets"][:1]
        if row["has_changes"] and snippets:
            page = (row.get("new") or row.get("old") or {}).get("page")
            lines.append(f"- p.{page}: {snippets[0]!r}")
    body = "\n".join(lines)

subprocess.run(
    ["gh", "pr", "comment", os.environ["PR_NUMBER"], "--body", body],
    check=True,
)
```

## Notes

- `paths: ["paper/**"]` keeps this from running (and posting noise) on PRs
  that don't touch the paper.
- Swap `xu-cheng/latex-action` for whatever builds your document — a Word
  export step, a Sphinx/typst build, anything that ends in a PDF works the
  same way from here on.
- Want the marked-up PDF attached too, for reviewers who want to see exactly
  where changes landed? Drop `artifacts=False` and `actions/upload-artifact`
  the three files under `out/` alongside the comment.
- `gh pr comment` posts a new comment on every run; if you'd rather update
  one comment in place across pushes, use `gh pr comment --edit-last` (falls
  back to creating one on the first run).
