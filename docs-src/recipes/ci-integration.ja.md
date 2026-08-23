# レシピ: CIでPDF差分の要約を出す

よくある用途: CIジョブがソース(LaTeX、Wordからのエクスポート、生成されたレポートなど)
からPDFをビルドし、CIジョブがどうせ捨ててしまう3つのマーカー付きPDFのコストを払わずに、
(例えばPRコメントとして投稿するような)短い変更・非変更の要約だけが欲しい場合。

```python
import json
import sys

import kogo

result = kogo.compare_pdfs(
    "old/build/paper.pdf",
    "new/build/paper.pdf",
    "out/",
    artifacts=False,  # old/new/side-by-side.pdf は生成しない。result.json は生成される
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

# より詳細に、例えばPRコメントに使いたい場合、result["rows"] にはページごとのスニペットがある
for row in result["rows"]:
    if row["has_changes"] and row["changes"]["added_snippets"]:
        print(f"  page {row.get('new', {}).get('page')}: + {row['changes']['added_snippets'][0]!r}")
```

マーカー付きPDFをCIの成果物として欲しい場合(例えばジョブに添付したい場合)は、
`artifacts=False` を外し、`out/old-highlighted.pdf`、`out/new-highlighted.pdf`、
`out/side-by-side.pdf` をビルド成果物としてアップロードしてください。

比較に時間がかかりそうな場合(大きな文書、多くのページ)は、ジョブが固まったように
見えないよう、`on_progress` を使ってジョブログに状況を流し込んでください:

```python
def log_progress(phase: str, current: int, total: int) -> None:
    if phase == "comparing":
        print(f"::debug::comparing page {current}/{total}", flush=True)

kogo.compare_pdfs("old.pdf", "new.pdf", "out/", on_progress=log_progress)
```
