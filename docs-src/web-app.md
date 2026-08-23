# Web app

```bash
pip install "kogo[serve]"
kogo fetch-viewer
kogo serve
```

Then open <http://127.0.0.1:8080>. The preview is a selectable-text view
powered by [Mozilla PDF.js](https://github.com/mozilla/pdf.js), with
downloadable old-highlighted, new-highlighted, and side-by-side comparison
PDFs.

## Docker

```bash
docker compose up -d --build
```

Then open <http://localhost:8080>. By default the container only binds to
`127.0.0.1`. To share it on a LAN — there is no authentication built in, so
only do this on a trusted network:

```bash
KOGO_HOST=0.0.0.0 docker compose up -d --build
```

`docker-compose.yml` sets `mem_limit: 2g`, `cpus: 2`, and `pids_limit: 256` as
a backstop, since PyMuPDF and OpenCV are native-code parsers processing
untrusted PDFs. Raise these if legitimate large comparisons get OOM-killed or
throttled.

## Configuration

Environment variables read by the web app:

| Variable | Default | Description |
|---|---:|---|
| `JOBS_DIR` | `~/.local/share/kogo/jobs` | Where uploaded files and comparison results are stored |
| `MAX_UPLOAD_MB` | 100 | Maximum size per uploaded PDF |
| `MAX_PAGES` | 200 | Maximum pages per PDF |
| `JOB_TTL_HOURS` | 24 | How long comparison results are kept before cleanup |
| `MAX_CONCURRENT_JOBS` | 2 | Number of comparisons processed at once |
| `JOB_TIMEOUT_SECONDS` | 900 | Wall-clock limit for a single comparison before it's aborted (minimum 60) |
| `KOGO_VENDOR_DIR` | `~/.local/share/kogo/vendor/pdfjs` | Where `kogo fetch-viewer` installs (and the server looks for) the local PDF.js viewer assets |
| `KOGO_SOURCE_URL` | `https://github.com/ta-061/kogo` | Source code link shown in the web app footer and the `kogo serve` startup banner |

!!! warning "No built-in authentication"
    There is no authentication built in. `kogo serve` and the default Docker
    Compose setup only bind to localhost; put the web app behind a reverse
    proxy with authentication before exposing it to anything beyond your
    local machine or trusted LAN.

!!! note "AGPL-3.0 §13"
    If you modify kogo and let others use it over a network (for example, by
    self-hosting a modified version of the web app), AGPL-3.0 §13 requires
    you to offer those users the corresponding source code. Set
    `KOGO_SOURCE_URL` to your own fork's repository to satisfy this. See the
    [license section of the README](https://github.com/ta-061/kogo#license)
    for details.
