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

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pymupdf as fitz

from .alignment import _page_visual_signature, align_pages
from .annotations import AnnotationSnapshot, _annotation_differences, _annotation_snapshots
from .render import (
    ADD_COLOR,
    DELETE_COLOR,
    MARKER_AUTHOR,
    _add_annotation_change_boxes,
    _add_highlights,
    _add_page_box,
    _add_style_boxes,
    _add_visual_boxes,
    _artifact_info,
    _comparison_pdf,
    _group_word_rects,
    _preview_page,
)
from .result_types import ComparisonResult
from .text_diff import _difference_snippets, _document_text_differences, _snippet
from .visual_diff import VisualRegion, _visual_differences
from .words import Word, _page_words

# Link kinds PyMuPDF exposes as safe to keep on baked output pages. Anything
# else (Launch, GoToR, and actions such as SubmitForm/ImportData/JavaScript,
# which PyMuPDF folds into LINK_NAMED/LINK_NONE) is active content and is
# dropped by _scrub_active_content.
_SAFE_LINK_KINDS = frozenset((fitz.LINK_GOTO, fitz.LINK_URI))

# Only these URI schemes are kept on a LINK_URI link; anything else (notably
# javascript:, which some viewers execute on click) is dropped.
_SAFE_URI_PREFIXES = ("http://", "https://")

# Keys that can carry their own action (e.g. a JavaScript action) on the
# document catalog, a page, or a form-field widget.
_ACTIVE_ACTION_KEYS = ("OpenAction", "AA")


def _strip_object_actions(doc: fitz.Document, xref: int) -> None:
    """Remove OpenAction/AA (additional-actions) from one PDF object.

    doc.scrub(javascript=True) walks indirect objects and clears the action
    type on each one, but it does not recurse into a *direct* (inline,
    non-indirect) action dict, nor into page- or widget-level /AA
    dictionaries - either of which can carry an untouched JavaScript action.
    Setting the key to the PDF null object removes it regardless of whether
    it was originally a direct dict or an indirect reference.
    """
    for key in _ACTIVE_ACTION_KEYS:
        if doc.xref_get_key(xref, key)[0] != "null":
            doc.xref_set_key(xref, key, "null")


def _scrub_active_content(doc: fitz.Document) -> None:
    """Strip JavaScript, embedded/attached files, and dangerous link actions.

    Must run immediately after opening an untrusted document, before any
    other processing, so that malicious active content (e.g. an /OpenAction
    or a Launch/GoToR link) never survives into the baked, re-shared output
    PDFs.
    """
    doc.scrub(
        attached_files=True,
        clean_pages=False,
        embedded_files=True,
        hidden_text=False,
        javascript=True,
        metadata=False,
        redactions=False,
        redact_images=False,
        remove_links=False,
        reset_fields=True,
        reset_responses=True,
        thumbnails=True,
    )
    _strip_object_actions(doc, doc.pdf_catalog())
    for page in doc:
        _strip_object_actions(doc, page.xref)
        for widget in page.widgets():
            _strip_object_actions(doc, widget.xref)
        for link in list(page.links()):
            kind = link.get("kind")
            if kind not in _SAFE_LINK_KINDS:
                page.delete_link(link)
            elif kind == fitz.LINK_URI and not str(link.get("uri") or "").lower().startswith(
                _SAFE_URI_PREFIXES
            ):
                page.delete_link(link)


class ComparisonError(ValueError):
    """A user-facing PDF comparison error."""


def compare_pdfs(
    old_path: Path,
    new_path: Path,
    output_dir: Path,
    *,
    old_name: str | None = None,
    new_name: str | None = None,
    dpi: int = 144,
    sensitivity: str = "standard",
    max_pages: int = 200,
    previews: bool = True,
    artifacts: bool = True,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> ComparisonResult:
    """Compare two revisions of a PDF document and produce marked outputs.

    Text is compared at word precision (character precision for CJK text,
    including supplementary-plane kanji), after reconstructing a reading
    order from page layout. Figures, equations, and layout changes are
    detected visually outside text areas, and existing PDF annotations
    (highlights, comments, ink) are fingerprinted and diffed. Style-only
    changes (bold, italic, font size) on unchanged text are reported as
    well. All markers are baked into the output PDFs.

    Args:
        old_path: PDF of the previous revision.
        new_path: PDF of the updated revision.
        output_dir: Directory for results; created if missing.
        old_name: Display name of the old file; defaults to its file name.
        new_name: Display name of the new file; defaults to its file name.
        dpi: Rendering resolution for the visual diff, 96-180.
        sensitivity: Figure detection sensitivity: "high", "standard",
            or "low".
        max_pages: Maximum number of pages allowed per file.
        previews: Whether to generate per-page JPEG previews.
        artifacts: Whether to bake and save the marked old/new/side-by-side
            PDFs. Set to False to skip that I/O when only the JSON summary
            is needed (e.g. a CI step); ``result["artifacts"]`` is then
            ``None``. ``result.json`` is still written either way.
        on_progress: Optional callback invoked as
            ``on_progress(phase, current, total)`` while the comparison
            runs, with ``phase`` one of ``"aligned"``, ``"comparing"``
            (once per aligned row), ``"rendering"``, and ``"previews"``.
            Purely informational; exceptions it raises are not caught.

    Returns:
        A `ComparisonResult` dict (also written to output_dir/result.json) with keys:

        - "files": {"old": {"name", "pages"}, "new": {"name", "pages"}}
        - "settings": {"dpi", "sensitivity", "large_document_fallback"}
        - "summary": word/page/visual-region/annotation/style change counts
        - "legend": human-readable color explanations
        - "artifacts": {"old", "new", "side_by_side"} -> {"name", "label", "size"}, or None when artifacts=False
        - "rows": one entry per aligned page pair with "kind", "old"/"new" page info, and "changes" counts/snippets

        Files written to output_dir: result.json always; old-highlighted.pdf,
        new-highlighted.pdf, and side-by-side.pdf when artifacts is True;
        previews/ when previews is True.

    Raises:
        ComparisonError: user-facing problems such as encrypted, empty,
            oversized, unreadable, or non-PDF input.

    Example:
        ```python
        import kogo

        result = kogo.compare_pdfs("old.pdf", "new.pdf", "out/")
        print(result["summary"]["changed_pages"])
        ```
    """
    old_name = old_name or Path(old_path).name
    new_name = new_name or Path(new_path).name

    def _report(phase: str, current: int, total: int) -> None:
        if on_progress is not None:
            on_progress(phase, current, total)

    output_dir.mkdir(parents=True, exist_ok=True)
    preview_dir = output_dir / "previews"
    if previews:
        preview_dir.mkdir(exist_ok=True)

    try:
        old_doc = fitz.open(old_path)
        new_doc = fitz.open(new_path)
    except Exception as exc:
        raise ComparisonError(
            "Could not open the PDF. It may be corrupted or in an unsupported format."
        ) from exc

    try:
        if not old_doc.is_pdf or not new_doc.is_pdf:
            raise ComparisonError("Please provide two PDF files.")
        if old_doc.needs_pass or new_doc.needs_pass:
            raise ComparisonError(
                "Password-protected PDFs are not supported. Remove the password and try again."
            )
        if old_doc.page_count == 0 or new_doc.page_count == 0:
            raise ComparisonError("Cannot compare a PDF that contains no pages.")
        if old_doc.page_count > max_pages or new_doc.page_count > max_pages:
            raise ComparisonError(f"Up to {max_pages} pages per file can be compared.")

        for doc in (old_doc, new_doc):
            _scrub_active_content(doc)

        old_words_by_page = [_page_words(page) for page in old_doc]
        new_words_by_page = [_page_words(page) for page in new_doc]
        if any(len(words) < 20 for words in (*old_words_by_page, *new_words_by_page)):
            old_page_visuals = [_page_visual_signature(page) for page in old_doc]
            new_page_visuals = [_page_visual_signature(page) for page in new_doc]
        else:
            old_page_visuals = None
            new_page_visuals = None
        alignment = align_pages(
            old_words_by_page,
            new_words_by_page,
            old_page_visuals,
            new_page_visuals,
        )
        _report("aligned", 1, 1)
        deleted_words_by_page, added_words_by_page, style_changes_by_pair, large_document_fallback = (
            _document_text_differences(
                old_words_by_page,
                new_words_by_page,
                alignment,
            )
        )

        rows: list[dict[str, Any]] = []
        total_added = 0
        total_deleted = 0
        total_visual = 0
        total_added_annotations = 0
        total_deleted_annotations = 0
        total_style_changes = 0
        added_pages = 0
        deleted_pages = 0

        for row_index, (old_index, new_index) in enumerate(alignment, start=1):
            added_words: list[Word] = []
            deleted_words: list[Word] = []
            added_snippets: list[str] = []
            deleted_snippets: list[str] = []
            visual_regions: list[VisualRegion] = []
            visual_regions_truncated = False
            added_annotations: list[AnnotationSnapshot] = []
            deleted_annotations: list[AnnotationSnapshot] = []
            style_changes: list[tuple[Word, Word]] = []

            if old_index is not None and new_index is not None:
                old_page = old_doc[old_index]
                new_page = new_doc[new_index]
                old_words = old_words_by_page[old_index]
                new_words = new_words_by_page[new_index]
                old_annotations = _annotation_snapshots(old_page)
                new_annotations = _annotation_snapshots(new_page)
                deleted_annotations, added_annotations = _annotation_differences(
                    old_annotations, new_annotations
                )
                deleted_words = deleted_words_by_page[old_index]
                added_words = added_words_by_page[new_index]
                deleted_snippets = _difference_snippets(deleted_words)
                added_snippets = _difference_snippets(added_words)
                style_changes = style_changes_by_pair.get((old_index, new_index), [])
                visual_regions, visual_regions_truncated = _visual_differences(
                    old_page,
                    new_page,
                    old_words,
                    new_words,
                    dpi,
                    sensitivity,
                )
                _add_highlights(
                    old_page,
                    _group_word_rects(deleted_words),
                    DELETE_COLOR,
                    "Text deleted from the old version",
                )
                _add_highlights(
                    new_page,
                    _group_word_rects(added_words),
                    ADD_COLOR,
                    "Text added in the new version",
                )
                _add_visual_boxes(old_page, (region.old_rect for region in visual_regions))
                _add_visual_boxes(new_page, (region.new_rect for region in visual_regions))
                _add_annotation_change_boxes(
                    old_page,
                    deleted_annotations,
                    DELETE_COLOR,
                    "PDF annotation removed in the new version",
                )
                _add_annotation_change_boxes(
                    new_page,
                    added_annotations,
                    ADD_COLOR,
                    "PDF annotation added in the new version",
                )
                _add_style_boxes(old_page, (old_word.rect for old_word, _ in style_changes))
                _add_style_boxes(new_page, (new_word.rect for _, new_word in style_changes))
                kind = (
                    "changed"
                    if added_words
                    or deleted_words
                    or visual_regions
                    or added_annotations
                    or deleted_annotations
                    or style_changes
                    else "unchanged"
                )
            elif old_index is not None:
                old_page = old_doc[old_index]
                deleted_words = old_words_by_page[old_index]
                deleted_snippets = [_snippet(deleted_words)] if deleted_words else []
                _add_page_box(old_page, DELETE_COLOR, "Page removed in the new version")
                deleted_pages += 1
                kind = "deleted_page"
            else:
                assert new_index is not None
                new_page = new_doc[new_index]
                added_words = new_words_by_page[new_index]
                added_snippets = [_snippet(added_words)] if added_words else []
                _add_page_box(new_page, ADD_COLOR, "Page added in the new version")
                added_pages += 1
                kind = "added_page"

            total_added += len(added_words)
            total_deleted += len(deleted_words)
            total_visual += len(visual_regions)
            total_added_annotations += len(added_annotations)
            total_deleted_annotations += len(deleted_annotations)
            total_style_changes += len(style_changes)
            _report("comparing", row_index, len(alignment))
            rows.append(
                {
                    "row": row_index,
                    "kind": kind,
                    "has_changes": kind != "unchanged",
                    "old": {"page": old_index + 1} if old_index is not None else None,
                    "new": {"page": new_index + 1} if new_index is not None else None,
                    "changes": {
                        "added_words": len(added_words),
                        "deleted_words": len(deleted_words),
                        "visual_regions": len(visual_regions),
                        "visual_regions_truncated": visual_regions_truncated,
                        "added_annotations": len(added_annotations),
                        "deleted_annotations": len(deleted_annotations),
                        "style_changes": len(style_changes),
                        "added_snippets": added_snippets,
                        "deleted_snippets": deleted_snippets,
                    },
                }
            )

        old_output = output_dir / "old-highlighted.pdf"
        new_output = output_dir / "new-highlighted.pdf"
        compare_output = output_dir / "side-by-side.pdf"
        if artifacts:
            old_doc.set_metadata({**old_doc.metadata, "creator": MARKER_AUTHOR})
            new_doc.set_metadata({**new_doc.metadata, "creator": MARKER_AUTHOR})
            # Convert annotations into regular page content so markers remain visible
            # when printing or when a PDF viewer hides annotations by default.
            old_doc.bake(annots=True, widgets=False)
            new_doc.bake(annots=True, widgets=False)
            old_doc.save(old_output, garbage=4, deflate=True)
            new_doc.save(new_output, garbage=4, deflate=True)
            _comparison_pdf(old_doc, new_doc, alignment, compare_output)
            _report("rendering", 1, 1)

        if previews:
            for row in rows:
                row_number = int(row["row"])
                if row["old"] is not None:
                    old_preview = preview_dir / f"row-{row_number:04d}-old.jpg"
                    _preview_page(old_doc[int(row["old"]["page"]) - 1], old_preview)
                    row["old"]["preview"] = f"previews/{old_preview.name}"
                if row["new"] is not None:
                    new_preview = preview_dir / f"row-{row_number:04d}-new.jpg"
                    _preview_page(new_doc[int(row["new"]["page"]) - 1], new_preview)
                    row["new"]["preview"] = f"previews/{new_preview.name}"
            _report("previews", 1, 1)

        changed_pages = sum(1 for row in rows if row["has_changes"])
        result: ComparisonResult = {
            "files": {
                "old": {"name": old_name, "pages": old_doc.page_count},
                "new": {"name": new_name, "pages": new_doc.page_count},
            },
            "settings": {
                "dpi": dpi,
                "sensitivity": sensitivity,
                "large_document_fallback": large_document_fallback,
            },
            "summary": {
                "compared_rows": len(rows),
                "changed_pages": changed_pages,
                "unchanged_pages": len(rows) - changed_pages,
                "added_pages": added_pages,
                "deleted_pages": deleted_pages,
                "added_words": total_added,
                "deleted_words": total_deleted,
                "visual_regions": total_visual,
                "annotation_changes": total_added_annotations + total_deleted_annotations,
                "added_annotations": total_added_annotations,
                "deleted_annotations": total_deleted_annotations,
                "style_changes": total_style_changes,
            },
            "legend": {
                "added": "Text or pages added in the new version",
                "deleted": "Text or pages deleted from the old version",
                "visual": "Visual changes in figures, equations, and layout",
                "annotation": "Highlights, comments, and ink annotations added to or removed from the PDF",
                "style": "Font size, bold, or italic changes on otherwise-unchanged text",
            },
            "artifacts": (
                {
                    "old": _artifact_info(old_output, "Old version with deletions marked"),
                    "new": _artifact_info(new_output, "New version with additions marked"),
                    "side_by_side": _artifact_info(compare_output, "Side-by-side comparison"),
                }
                if artifacts
                else None
            ),
            "rows": rows,
        }
        (output_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result
    finally:
        old_doc.close()
        new_doc.close()
