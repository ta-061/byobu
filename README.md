# kogo

Layout-aware PDF diff for revisions — compare an old and new PDF and highlight added or deleted text, figures, and annotations, in the browser and in marked PDFs.

kogo (校合) is the Japanese publishing term for checking a revision against the original.

![kogo results](https://ta-061.github.io/kogo/screenshot-results.png)

Website: <https://portfolio.tatu-sec.dev/kogo/>

## Features

- Word-level text diff for Latin text, character-level precision for CJK (Chinese, Japanese, Korean) text, including rare kanji across CJK Extensions B-J
- Reading order reconstructed from whitespace layout, so multi-column pages and slide-style text boxes are compared correctly instead of interleaved
- Page alignment that tolerates inserted or removed pages, using both text and visual page signatures
- Visual diff for figures, equations, and layout, with text areas masked out and scanner/export shift registration for image-only pages
- Detects added or removed highlights, comments, and ink annotations
- Detects style-only changes (bold, italic, font-size) on otherwise-unchanged text, marked in amber
- Markers are baked into the output PDFs so they show up in any viewer, even with annotations hidden
- Selectable-text web preview powered by Mozilla PDF.js
- Downloadable old-highlighted, new-highlighted, and side-by-side comparison PDFs
- All processing happens locally — nothing is sent to an external service

## Quick start

### CLI only

```bash
pip install kogo
kogo diff old.pdf new.pdf -o out/
```

### Web app

```bash
pip install "kogo[serve]"
kogo fetch-viewer
kogo serve
```

`kogo fetch-viewer` downloads the local PDF.js viewer assets used by the web preview (see [Configuration](#configuration)); it's not needed with Docker, which bundles them in the image.

Then open <http://127.0.0.1:8080>.

### Docker

```bash
docker compose up -d --build
```

Then open <http://localhost:8080>. By default the container only binds to `127.0.0.1` (localhost). To share it on a LAN, there is no authentication built in, so only do this on a trusted network:

```bash
KOGO_HOST=0.0.0.0 docker compose up -d --build
```

## CLI usage

```bash
kogo diff OLD.pdf NEW.pdf \
  -o kogo-diff \
  --dpi 144 \
  --sensitivity standard \
  --max-pages 200
```

Options:

- `-o, --out` — output directory (default `kogo-diff`)
- `--dpi` — rendering resolution for the visual diff, 96–180 (default 144)
- `--sensitivity` — `high`, `standard`, or `low` (default `standard`)
- `--max-pages` — maximum pages per file (default 200)
- `--no-previews` — skip generating page preview images
- `--json` — print the full result as JSON

`kogo serve` runs the web application:

```bash
kogo serve --host 127.0.0.1 --port 8080
```

## Use as a library

The diff engine is a regular Python API — `pip install kogo` is enough (no web dependencies needed):

```python
import kogo

result = kogo.compare_pdfs("old.pdf", "new.pdf", "out/")
print(result["summary"])
# out/ now contains old-highlighted.pdf, new-highlighted.pdf,
# side-by-side.pdf, result.json, and page previews.
```

`kogo.compare_pdfs` raises `kogo.ComparisonError` for user-facing problems (encrypted, empty, oversized, or unreadable PDFs). Keyword options mirror the CLI: `dpi`, `sensitivity`, `max_pages`, `previews`, `old_name`, `new_name`.

## Configuration

The web app reads these environment variables:

| Variable | Default | Description |
|---|---:|---|
| `JOBS_DIR` | `~/.local/share/kogo/jobs` | Where uploaded files and comparison results are stored |
| `MAX_UPLOAD_MB` | 100 | Maximum size per uploaded PDF |
| `MAX_PAGES` | 200 | Maximum pages per PDF |
| `JOB_TTL_HOURS` | 24 | How long comparison results are kept before cleanup |
| `MAX_CONCURRENT_JOBS` | 2 | Number of comparisons processed at once |
| `KOGO_VENDOR_DIR` | `~/.local/share/kogo/vendor/pdfjs` | Where `kogo fetch-viewer` installs (and the server looks for) the local PDF.js viewer assets |

## How it works

Text is extracted at word precision (character precision for CJK) and reordered using recursive whitespace cuts, so columns, slide text boxes, and reflowed paragraphs are read in a sensible order rather than the PDF's raw internal stream order. Pages are aligned across the two documents with a similarity-based sequence alignment (combining text and, for image-heavy pages, visual signatures) so inserted or removed pages don't desynchronize the rest of the comparison. Remaining differences are then diffed with Python's `difflib`.

Figures, equations, and other non-text layout are compared by rendering each page to an image, masking out the areas already covered by the text diff, and taking a pixel difference. Image-only pages get a small registration step to correct for scanner or export shifts before the pixel diff runs. Existing PDF annotations (highlights, comments, ink) are fingerprinted and diffed separately.

## Limitations

- Scan-only PDFs (no embedded text layer) are compared visually; add an OCR text layer first if you need word-level text diffs
- Password-protected PDFs are not supported
- Complex tables and vertical text layouts may need a visual check in addition to the automated diff
- There is no authentication built in. `kogo serve` and the default Docker Compose setup only bind to localhost; put the web app behind a reverse proxy with authentication before exposing it to anything beyond your local machine or trusted LAN

## Development

```bash
python -m unittest discover -s tests -v
```

## License

kogo is licensed under AGPL-3.0. See [LICENSE](LICENSE).

Copyright (C) 2026 ta-061. Released under the GNU Affero General Public License v3.0 (AGPL-3.0-only).

PyMuPDF (and the underlying MuPDF library) is distributed under AGPL-3.0-or-commercial; check its license terms before redistributing kogo or offering it as a network service.

If you modify kogo and let others use it over a network (for example, by self-hosting a modified version of the web app), AGPL-3.0 §13 requires you to offer those users the corresponding source code. The "Source code" link in the web app's footer is where self-hosters should point to their source.

Credits:

- [Mozilla PDF.js](https://github.com/mozilla/pdf.js) (Apache-2.0)
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) (AGPL-3.0-or-commercial)
- [OpenCV](https://github.com/opencv/opencv) (Apache-2.0)
- [FastAPI](https://github.com/tiangolo/fastapi) (MIT)
