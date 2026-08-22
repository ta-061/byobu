# kogo - layout-aware PDF diff for revisions.
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

"""Command-line interface for kogo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from kogo import __version__
from kogo.engine import ComparisonError, compare_pdfs

# Keep in sync with ARG PDFJS_VERSION in Dockerfile.
PDFJS_VERSION = "6.2.108"
PDFJS_TARBALL_URL = f"https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-{PDFJS_VERSION}.tgz"
# SHA-256 of the tarball above (`curl -sL <url> | sha256sum`). Must be updated
# together with PDFJS_VERSION whenever the pinned version changes.
PDFJS_TARBALL_SHA256 = "b3e68d5cda70551a90b3f771419d379e20fc788ce056fa32de73608e01df47f4"
VENDOR_COMPLETE_MARKER = ".complete"

# (source within the tarball's "package/" prefix, destination relative to the vendor dir)
PDFJS_FILE_MAP = (
    ("build/pdf.min.mjs", "build/pdf.mjs"),
    ("build/pdf.worker.min.mjs", "build/pdf.worker.mjs"),
    ("web/pdf_viewer.mjs", "web/pdf_viewer.mjs"),
    ("web/pdf_viewer.css", "web/pdf_viewer.css"),
    ("LICENSE", "LICENSE"),
)
PDFJS_DIR_MAP = (
    ("web/images", "web/images"),
    ("cmaps", "cmaps"),
    ("standard_fonts", "standard_fonts"),
    ("wasm", "wasm"),
)


def _default_vendor_dir() -> Path:
    return Path(
        os.getenv("KOGO_VENDOR_DIR", "~/.local/share/kogo/vendor/pdfjs")
    ).expanduser()


def _dpi(value: str) -> int:
    dpi = int(value)
    if not 96 <= dpi <= 180:
        raise argparse.ArgumentTypeError("--dpi must be between 96 and 180")
    return dpi


def _max_pages(value: str) -> int:
    pages = int(value)
    if not 1 <= pages <= 2000:
        raise argparse.ArgumentTypeError("--max-pages must be between 1 and 2000")
    return pages


def _add_diff_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("diff", help="Compare two PDF revisions")
    parser.add_argument("old_pdf", type=Path)
    parser.add_argument("new_pdf", type=Path)
    parser.add_argument("-o", "--out", default="kogo-diff")
    parser.add_argument("--dpi", type=_dpi, default=144)
    parser.add_argument(
        "--sensitivity", choices=("high", "standard", "low"), default="standard"
    )
    parser.add_argument("--max-pages", type=_max_pages, default=200)
    parser.add_argument("--no-previews", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=_run_diff)


def _add_serve_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("serve", help="Run the kogo web application")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--jobs-dir", default=None)
    parser.set_defaults(handler=_run_serve)


def _add_fetch_viewer_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "fetch-viewer", help="Download the local PDF.js viewer assets"
    )
    parser.add_argument("--dir", type=Path, default=None)
    parser.set_defaults(handler=_run_fetch_viewer)


def _run_diff(args: argparse.Namespace) -> int:
    output_dir = Path(args.out)
    try:
        result = compare_pdfs(
            args.old_pdf,
            args.new_pdf,
            output_dir,
            old_name=args.old_pdf.name,
            new_name=args.new_pdf.name,
            dpi=args.dpi,
            sensitivity=args.sensitivity,
            max_pages=args.max_pages,
            previews=not args.no_previews,
        )
    except ComparisonError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Comparison failed unexpectedly: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    files = result["files"]
    summary = result["summary"]
    artifacts = result["artifacts"]
    print(f"{files['old']['name']} ({files['old']['pages']} pages) vs "
          f"{files['new']['name']} ({files['new']['pages']} pages)")
    print(f"Changed pages: {summary['changed_pages']} / {summary['compared_rows']}")
    print(f"Added tokens: {summary['added_words']}  Deleted tokens: {summary['deleted_words']}")
    print(f"Visual regions: {summary['visual_regions']}  Annotation changes: {summary['annotation_changes']}")
    print("Output files:")
    for artifact in artifacts.values():
        print(f"  {output_dir / artifact['name']}")
    print(f"  {output_dir / 'result.json'}")
    return 0


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_unsafe_member_name(name: str) -> None:
    if not name or name.startswith("/") or name.startswith("\\"):
        raise ValueError(f"Refusing to extract tar member with an unsafe path: {name!r}")
    if ".." in Path(name).parts:
        raise ValueError(f"Refusing to extract tar member with an unsafe path: {name!r}")


def _safe_join(destination: Path, destination_root: Path, *relative_parts: str) -> Path:
    out_path = destination.joinpath(*relative_parts)
    if not out_path.resolve().is_relative_to(destination_root):
        raise ValueError(f"Refusing to extract outside the destination directory: {out_path}")
    return out_path


def _extract_pdfjs(tarball_path: Path, destination: Path) -> None:
    destination_root = destination.resolve()
    with tarfile.open(tarball_path, mode="r:gz") as archive:
        for source, target in PDFJS_FILE_MAP:
            member = archive.getmember(f"package/{source}")
            _reject_unsafe_member_name(member.name)
            out_path = _safe_join(destination, destination_root, target)
            with archive.extractfile(member) as handle:
                data = handle.read()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)
        for source, target in PDFJS_DIR_MAP:
            prefix = f"package/{source}/"
            for member in archive.getmembers():
                if not member.name.startswith(prefix) or not member.isfile():
                    continue
                _reject_unsafe_member_name(member.name)
                relative = member.name[len(prefix) :]
                out_path = _safe_join(destination, destination_root, target, relative)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as handle:
                    out_path.write_bytes(handle.read())


def _run_fetch_viewer(args: argparse.Namespace) -> int:
    vendor_dir = args.dir if args.dir is not None else _default_vendor_dir()
    if (vendor_dir / VENDOR_COMPLETE_MARKER).is_file():
        print(f"PDF.js viewer assets are already installed at {vendor_dir}")
        print('"kogo serve" will use the local viewer.')
        return 0

    print(f"Downloading pdfjs-dist {PDFJS_VERSION}…")
    vendor_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=vendor_dir.parent) as work_dir_name:
        work_dir = Path(work_dir_name)
        tarball_path = work_dir / "pdfjs-dist.tgz"
        try:
            with urllib.request.urlopen(PDFJS_TARBALL_URL, timeout=30) as response, tarball_path.open("wb") as output:
                shutil.copyfileobj(response, output)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"Could not download the PDF.js viewer assets: {exc}", file=sys.stderr)
            return 1

        actual_sha256 = _sha256_of(tarball_path)
        if actual_sha256 != PDFJS_TARBALL_SHA256:
            print(
                "Downloaded PDF.js tarball does not match the pinned SHA-256 checksum "
                f"(expected {PDFJS_TARBALL_SHA256}, got {actual_sha256}); aborting.",
                file=sys.stderr,
            )
            return 1

        staging_dir = work_dir / "staging"
        try:
            _extract_pdfjs(tarball_path, staging_dir)
        except (tarfile.TarError, KeyError, OSError, ValueError) as exc:
            print(f"Could not extract the PDF.js viewer assets: {exc}", file=sys.stderr)
            return 1

        # Written last, on the same filesystem as vendor_dir, so the rename below
        # cannot leave a directory that has the marker but is missing files.
        (staging_dir / VENDOR_COMPLETE_MARKER).touch()
        if vendor_dir.exists():
            shutil.rmtree(vendor_dir)
        staging_dir.rename(vendor_dir)

    print(f"Installed the PDF.js viewer assets in {vendor_dir}")
    print('"kogo serve" will now use the local viewer.')
    return 0


def _run_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            'Web dependencies are missing. Install them with: pip install "kogo[serve]"',
            file=sys.stderr,
        )
        return 1

    if args.jobs_dir is not None:
        os.environ["JOBS_DIR"] = args.jobs_dir

    source_url = os.environ.get("KOGO_SOURCE_URL", "https://github.com/ta-061/kogo")
    print(f"kogo {__version__}  Copyright (C) 2026 ta-061")
    print("License: AGPL-3.0-only <https://www.gnu.org/licenses/agpl-3.0.html>")
    print(f"Source code: {source_url}")
    print("This is free software: you are free to change and redistribute it under the terms of the AGPL.")
    uvicorn.run("kogo.server.app:app", host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kogo")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_diff_parser(subparsers)
    _add_serve_parser(subparsers)
    _add_fetch_viewer_parser(subparsers)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
