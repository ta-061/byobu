# レシピ: PDFペアのディレクトリを一括比較する

共有ドライブ上の `*-old.pdf`/`*-new.pdf` ペアのフォルダや、書籍の各章など、
多数の改訂を一度に比較したい場合 — シェルループでペアごとにCLIを再起動し
(プロセス起動コストを払い)続けることなく行いたいケース。

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

# ペア全体を横断した CSV/JSON の集計、例えばスプレッドシートやダッシュボード向けに:
import csv
import sys

writer = csv.writer(sys.stdout)
writer.writerow(["file", "changed_pages", "added_words", "deleted_words", "visual_regions"])
for name, summary in results:
    writer.writerow(
        [name, summary["changed_pages"], summary["added_words"], summary["deleted_words"], summary["visual_regions"]]
    )
```

補足:

- `kogo.ComparisonError` は、`compare_pdfs` がユーザー起因の問題(暗号化・空・
  過大・読み込み不能なPDF)に対して送出する唯一の例外です — ペアごとに捕捉することで、
  1つの不正なファイルがバッチ全体を中断させないようにできます。
- `artifacts=False` は単発の比較よりもここで重要です: 数百ペアある場合、
  要約だけが必要なペアについてマーカー付きPDFの書き込みを省略すると、
  それに比例するディスクI/Oを削減できます。実際にマーカー付きPDFが必要な
  特定のペアについては外してください。
- 各 `compare_pdfs` 呼び出しは自分自身でPDFを開き、自分自身でページを
  レンダリングします — 呼び出し間で再利用する状態はないため、シンプルさより
  I/OやCPUのスループットを優先する場合は、ペアごとの並列化
  (例えば `concurrent.futures.ProcessPoolExecutor`)は安全かつ簡単です。
