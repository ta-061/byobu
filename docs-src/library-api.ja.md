# ライブラリ API

ライブラリとして使うだけなら `pip install kogo` で十分です — `serve` 追加パッケージ
(FastAPI、uvicorn)はWebアプリ用にのみ必要です。

```python
import kogo

result: kogo.ComparisonResult = kogo.compare_pdfs("old.pdf", "new.pdf", "out/")
```

`kogo.compare_pdfs` がエントリーポイントです。このページの残りは戻り値の型付けの
ためのものです — 戻り値自体は実行時には通常の `dict` です
(`output_dir/result.json` にも書き出されます)。型付けの有無で挙動は変わりません。

!!! note "以下のAPIリファレンスは英語で表示されます"
    このセクションはPythonのdocstringから[mkdocstrings](https://mkdocstrings.github.io/)
    によって自動生成されており、docstring自体は英語で書かれています。日本語訳への
    貢献に興味があれば、[コントリビュート](contributing.ja.md)を参照してください。

::: kogo.compare_pdfs

## `ComparisonResult` とその仲間

これらは `TypedDict` で、結果を保存したりやり取りしたりする際の型チェックや
エディタの自動補完に役立ちます:

```python
def summarize(result: kogo.ComparisonResult) -> str:
    return f"{result['summary']['changed_pages']} pages changed"
```

::: kogo.ComparisonResult
::: kogo.Files
::: kogo.FileInfo
::: kogo.Settings
::: kogo.Summary
::: kogo.Legend
::: kogo.Artifacts
::: kogo.ArtifactInfo
::: kogo.Row
::: kogo.RowChanges
::: kogo.PageRef

## `ComparisonError`

::: kogo.ComparisonError
