# kogo

kogo (校合) compares an old and new PDF and highlights added or deleted text,
figures, equations, and annotations — in the browser and in marked-up PDFs.
"校合" is the Japanese publishing term for checking a revision against the
original.

All processing happens locally; nothing is sent to an external service.

## Install

```bash
pip install kogo
```

## CLI

```bash
kogo diff old.pdf new.pdf -o out/
```

See the [CLI reference](cli.md) for all flags.

## Library

```python
import kogo

result: kogo.ComparisonResult = kogo.compare_pdfs("old.pdf", "new.pdf", "out/")
print(result["summary"]["changed_pages"])
```

`pip install kogo` is enough for library use — no web extras required. See the
[Library API reference](library-api.md) for the full signature and result
shape.

## Web app

```bash
pip install "kogo[serve]"
kogo fetch-viewer
kogo serve
```

Then open <http://127.0.0.1:8080>. See [Web app](web-app.md) for configuration
and Docker deployment.

## Where to go next

- [Library API](library-api.md) — `compare_pdfs` signature, `ComparisonResult`
  shape, write-less mode, progress callback
- [How it works](architecture.md) — page alignment, text diff, and visual diff
  algorithms
- [Recipes](recipes/ci-integration.md) — using kogo from a CI step
- [FAQ](faq.md)
