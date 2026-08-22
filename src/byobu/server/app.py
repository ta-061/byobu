# byobu - layout-aware PDF diff for revisions.
# Copyright (C) 2026  ta-061
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from byobu import __version__
from byobu.engine import ComparisonError, compare_pdfs


APP_DIR = Path(__file__).resolve().parent
JOBS_DIR = Path(os.getenv("JOBS_DIR", "~/.local/share/byobu/jobs")).expanduser().resolve()
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "100")) * 1024 * 1024
MAX_PAGES = int(os.getenv("MAX_PAGES", "200"))
JOB_TTL_SECONDS = max(3600, int(os.getenv("JOB_TTL_HOURS", "24")) * 3600)
MAX_CONCURRENT_JOBS = max(1, int(os.getenv("MAX_CONCURRENT_JOBS", "2")))
JOB_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

JOBS_DIR.mkdir(parents=True, exist_ok=True)
# One semaphore per worker process: it bounds concurrency within this process only,
# not across multiple uvicorn/gunicorn workers.
comparison_slots = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
logger = logging.getLogger("byobu")

VENDOR_COMPLETE_MARKER = ".complete"
_PACKAGE_VENDOR_DIR = APP_DIR / "static" / "vendor" / "pdfjs"
_EXTERNAL_VENDOR_DIR = Path(
    os.getenv("BYOBU_VENDOR_DIR", "~/.local/share/byobu/vendor/pdfjs")
).expanduser()


def _job_directory(job_id: str) -> Path:
    if not JOB_ID_PATTERN.fullmatch(job_id):
        raise HTTPException(status_code=404, detail="Comparison result not found.")
    return JOBS_DIR / job_id


def _cleanup_expired_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    try:
        entries = list(JOBS_DIR.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if entry.is_dir() and not entry.is_symlink() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry)
        except OSError:
            continue


async def _periodic_cleanup() -> None:
    interval = max(60, min(900, JOB_TTL_SECONDS // 4))
    while True:
        await asyncio.sleep(interval)
        await run_in_threadpool(_cleanup_expired_jobs)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_in_threadpool(_cleanup_expired_jobs)
    cleanup_task = asyncio.create_task(_periodic_cleanup())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


app = FastAPI(
    title="byobu",
    description="Compare two revisions of a PDF and highlight added or deleted text, figures, and annotations.",
    version=__version__,
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
if not (_PACKAGE_VENDOR_DIR / "build" / "pdf.mjs").is_file() and (
    _EXTERNAL_VENDOR_DIR / VENDOR_COMPLETE_MARKER
).is_file():
    app.mount(
        "/static/vendor/pdfjs", StaticFiles(directory=_EXTERNAL_VENDOR_DIR), name="pdfjs-vendor"
    )
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


async def _save_pdf(upload: UploadFile, destination: Path) -> int:
    if not upload.filename:
        raise HTTPException(status_code=400, detail="Please choose a PDF file.")
    size = 0
    prefix = bytearray()
    magic_checked = False
    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Files must be at most {MAX_UPLOAD_BYTES // 1024 // 1024} MB each.",
                    )
                if not magic_checked:
                    if len(prefix) < 8:
                        prefix.extend(chunk[: 8 - len(prefix)])
                    if len(prefix) >= 8:
                        magic_checked = True
                        if not bytes(prefix).lstrip().startswith(b"%PDF-"):
                            raise HTTPException(
                                status_code=400, detail="The selected file is not a PDF."
                            )
                output.write(chunk)
    finally:
        await upload.close()
    if size == 0:
        raise HTTPException(status_code=400, detail="Empty files cannot be compared.")
    if not magic_checked and not bytes(prefix).lstrip().startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="The selected file is not a PDF.")
    return size


def _load_result(job_dir: Path) -> dict:
    result_path = job_dir / "result.json"
    if not result_path.is_file():
        raise HTTPException(status_code=404, detail="Comparison result is missing or still processing.")
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Could not read the comparison result.") from exc


def _allowed_artifacts(result: dict) -> set[str]:
    allowed = {
        str(item["name"])
        for item in result.get("artifacts", {}).values()
        if isinstance(item, dict) and item.get("name")
    }
    for row in result.get("rows", []):
        for side in ("old", "new"):
            value = row.get(side)
            if isinstance(value, dict) and value.get("preview"):
                allowed.add(str(value["preview"]))
    return allowed


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(APP_DIR / "templates" / "index.html")


@app.get("/viewer", include_in_schema=False)
async def pdf_viewer() -> FileResponse:
    return FileResponse(APP_DIR / "templates" / "pdf-viewer.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
async def config() -> dict[str, int]:
    return {
        "max_upload_mb": MAX_UPLOAD_BYTES // 1024 // 1024,
        "max_pages": MAX_PAGES,
    }


@app.post("/api/compare")
async def compare(
    old_pdf: Annotated[UploadFile, File(description="Old version PDF")],
    new_pdf: Annotated[UploadFile, File(description="New version PDF")],
    dpi: Annotated[int, Form(ge=96, le=180)] = 144,
    sensitivity: Annotated[str, Form(pattern="^(high|standard|low)$")] = "standard",
) -> JSONResponse:
    await run_in_threadpool(_cleanup_expired_jobs)
    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(mode=0o700, parents=True)
    old_path = job_dir / "old-input.pdf"
    new_path = job_dir / "new-input.pdf"
    old_name = Path(old_pdf.filename or "old.pdf").name[:180]
    new_name = Path(new_pdf.filename or "new.pdf").name[:180]

    try:
        async with comparison_slots:
            await _save_pdf(old_pdf, old_path)
            await _save_pdf(new_pdf, new_path)
            result = await run_in_threadpool(
                compare_pdfs,
                old_path,
                new_path,
                job_dir,
                old_name=old_name,
                new_name=new_name,
                dpi=dpi,
                sensitivity=sensitivity,
                max_pages=MAX_PAGES,
            )
        # Inputs are unnecessary after generated artifacts are complete.
        old_path.unlink(missing_ok=True)
        new_path.unlink(missing_ok=True)
        return JSONResponse({"job_id": job_id, "result": result})
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except ComparisonError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected failure while processing job %s", job_id)
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail="Comparison failed. Check the PDF contents or the server logs.",
        ) from exc


@app.get("/api/jobs/{job_id}")
async def get_result(job_id: str) -> dict:
    job_dir = _job_directory(job_id)
    return {"job_id": job_id, "result": await run_in_threadpool(_load_result, job_dir)}


@app.get("/api/jobs/{job_id}/artifacts/{artifact_path:path}")
async def get_artifact(
    job_id: str,
    artifact_path: str,
    download: Annotated[bool, Query()] = False,
) -> FileResponse:
    job_dir = _job_directory(job_id)
    result = await run_in_threadpool(_load_result, job_dir)
    if artifact_path not in _allowed_artifacts(result):
        raise HTTPException(status_code=404, detail="File not found.")
    target = (job_dir / artifact_path).resolve()
    if job_dir.resolve() not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    headers = {"Cache-Control": "private, max-age=3600"}
    if download:
        return FileResponse(target, filename=target.name, headers=headers)
    return FileResponse(target, headers=headers)
