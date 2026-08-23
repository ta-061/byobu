# Library API

`pip install kogo` is enough for library use — the `serve` extra (FastAPI,
uvicorn) is only needed for the web app.

```python
import kogo

result: kogo.ComparisonResult = kogo.compare_pdfs("old.pdf", "new.pdf", "out/")
```

`kogo.compare_pdfs` is the entry point. Everything else on this page is
typing support for its return value — the return value itself is a plain
`dict` at runtime (also written to `output_dir/result.json`), so none of this
changes behavior.

::: kogo.compare_pdfs

## `ComparisonResult` and friends

These are `TypedDict`s, useful for type-checking and
editor autocomplete when you store or pass around a result:

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
