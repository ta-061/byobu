# CLI reference

## `kogo diff`

```bash
kogo diff OLD.pdf NEW.pdf \
  -o kogo-diff \
  --dpi 144 \
  --sensitivity standard \
  --max-pages 200
```

| Flag | Default | Description |
|---|---:|---|
| `-o`, `--out` | `kogo-diff` | Output directory |
| `--dpi` | `144` | Rendering resolution for the visual diff, 96–180 |
| `--sensitivity` | `standard` | Figure/visual detection sensitivity: `high`, `standard`, or `low` |
| `--max-pages` | `200` | Maximum pages per file |
| `--no-previews` | off | Skip generating page preview images |
| `--json` | off | Print the full result as JSON instead of a text summary |

When not run with `--json`, progress is printed to stderr as each aligned
page pair is compared (`Comparing page N/total...`), backed by the library's
`on_progress` callback — see [Library API](library-api.md).

## `kogo serve`

```bash
kogo serve --host 127.0.0.1 --port 8080
```

Requires the `serve` extra: `pip install "kogo[serve]"`. See
[Web app](web-app.md) for configuration.

## `kogo fetch-viewer`

```bash
kogo fetch-viewer
```

Downloads the local [PDF.js](https://github.com/mozilla/pdf.js) viewer assets
used by the web preview, verifying a pinned SHA-256 checksum. Not needed with
Docker, which bundles them in the image.
