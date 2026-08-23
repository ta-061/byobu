# レシピ: すべてのPRにLaTeX差分の要約をコメントする

kogo(校合)は、改訂版を原本と照合するという意味の日本の出版用語にちなんで
名付けられました — このレシピは、その作業を自動化したものです。GitHub Actions
のジョブがプルリクエストの両側でLaTeX論文をビルドし、2つのPDFを比較して、
何が変わったかをPRコメントとして投稿します。レビュアーはどちらのファイルを
開く前にも、内容のある要約を見ることができます。

## ワークフロー

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
    artifacts=False,  # このジョブは要約だけが必要で、マーカー付きPDFは不要
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

## 補足

- `paths: ["paper/**"]` により、論文に触れていないPRでは実行されず(無駄な通知を
  避けられ)ます。
- `xu-cheng/latex-action` は、文書をビルドする手段(Wordエクスポート、
  Sphinx/typstビルドなど、最終的にPDFになるもの)に合わせて置き換えてください。
  以降の手順は同じように動作します。
- マーカー入りPDFも添付して、変更がどこに入ったか正確に見たいレビュアー向けに
  したい場合は、`artifacts=False` を外し、`out/` 以下の3つのファイルを
  コメントと一緒に `actions/upload-artifact` でアップロードしてください。
- `gh pr comment` は実行のたびに新しいコメントを投稿します。プッシュのたびに
  1つのコメントをその場で更新したい場合は `gh pr comment --edit-last`
  を使ってください(初回実行時は新規作成にフォールバックします)。
