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

from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Sequence

import pymupdf as fitz

from .visual_diff import _clamped_render_scale
from .words import Word

if TYPE_CHECKING:
    # Deferred to avoid a runtime import cycle: annotations.py imports
    # MARKER_AUTHOR from this module. Safe under `from __future__ import
    # annotations`, which never evaluates this annotation at runtime.
    from .annotations import AnnotationSnapshot

MARKER_AUTHOR = "kogo"

ADD_COLOR = (0.10, 0.72, 0.34)
DELETE_COLOR = (0.91, 0.25, 0.22)
VISUAL_COLOR = (0.49, 0.28, 0.88)
PAGE_COLOR = (0.96, 0.64, 0.10)
STYLE_COLOR = (0.95, 0.63, 0.08)


def _clamp_rect(rect: fitz.Rect, page_rect: fitz.Rect, inset: float = 0.0) -> fitz.Rect | None:
    x0 = max(page_rect.x0 + inset, rect.x0)
    y0 = max(page_rect.y0 + inset, rect.y0)
    x1 = min(page_rect.x1 - inset, rect.x1)
    y1 = min(page_rect.y1 - inset, rect.y1)
    if x1 <= x0 or y1 <= y0:
        return None
    return fitz.Rect(x0, y0, x1, y1)


def _group_word_rects(words: Sequence[Word]) -> list[fitz.Rect]:
    if not words:
        return []
    groups: list[fitz.Rect] = []
    current = fitz.Rect(words[0].rect)
    previous = words[0]
    for word in words[1:]:
        same_line = word.block == previous.block and word.line == previous.line
        allowed_gap = max(6.0, max(current.height, word.rect.height) * 1.15)
        close = word.rect.x0 - current.x1 <= allowed_gap
        if same_line and close:
            current.include_rect(word.rect)
        else:
            groups.append(current)
            current = fitz.Rect(word.rect)
        previous = word
    groups.append(current)
    return groups


def _add_highlights(
    page: fitz.Page,
    rects: Iterable[fitz.Rect],
    color: tuple[float, float, float],
    content: str,
) -> None:
    for source_rect in rects:
        rect = _clamp_rect(source_rect, page.rect)
        if rect is None:
            continue
        try:
            annotation = page.add_highlight_annot(rect)
            annotation.set_colors(stroke=color)
            annotation.set_opacity(0.38)
            annotation.set_info(title=MARKER_AUTHOR, content=content)
            annotation.update()
        except (RuntimeError, ValueError):
            # Some malformed text quads cannot become a highlight; a translucent
            # rectangle keeps the result useful instead of failing the whole job.
            annotation = page.add_rect_annot(rect)
            annotation.set_colors(stroke=color, fill=color)
            annotation.set_border(width=0.7)
            annotation.set_opacity(0.20)
            annotation.set_info(title=MARKER_AUTHOR, content=content)
            annotation.update()


def _add_visual_boxes(page: fitz.Page, rects: Iterable[fitz.Rect]) -> None:
    for source_rect in rects:
        rect = _clamp_rect(source_rect, page.rect)
        if rect is None:
            continue
        annotation = page.add_rect_annot(rect)
        annotation.set_colors(stroke=VISUAL_COLOR, fill=VISUAL_COLOR)
        annotation.set_border(width=1.8, dashes=[4, 2])
        annotation.set_opacity(0.18)
        annotation.set_info(
            title=MARKER_AUTHOR,
            content="Visual difference in figures, equations, or layout",
        )
        annotation.update()


def _add_style_boxes(
    page: fitz.Page,
    rects: Iterable[fitz.Rect],
    content: str = "Font size or emphasis changed while text stayed the same",
) -> None:
    for source_rect in rects:
        rect = _clamp_rect(source_rect, page.rect)
        if rect is None:
            continue
        annotation = page.add_rect_annot(rect)
        annotation.set_colors(stroke=STYLE_COLOR, fill=STYLE_COLOR)
        annotation.set_border(width=0.9)
        annotation.set_opacity(0.22)
        annotation.set_info(title=MARKER_AUTHOR, content=content)
        annotation.update()


def _add_annotation_change_boxes(
    page: fitz.Page,
    annotations: Sequence[AnnotationSnapshot],
    color: tuple[float, float, float],
    content: str,
) -> None:
    for snapshot in annotations:
        for coordinates in snapshot.display_rects:
            rect = _clamp_rect(fitz.Rect(coordinates), page.rect)
            if rect is None:
                continue
            marker = page.add_rect_annot(rect)
            marker.set_colors(stroke=color)
            marker.set_border(width=1.8, dashes=[3, 2])
            marker.set_opacity(0.82)
            marker.set_info(title=MARKER_AUTHOR, content=content)
            marker.update()


def _add_page_box(page: fitz.Page, color: tuple[float, float, float], content: str) -> None:
    rect = fitz.Rect(page.rect)
    margin = min(8.0, max(2.0, min(rect.width, rect.height) / 40.0))
    rect.x0 += margin
    rect.y0 += margin
    rect.x1 -= margin
    rect.y1 -= margin
    annotation = page.add_rect_annot(rect)
    annotation.set_colors(stroke=color, fill=color)
    annotation.set_border(width=4.0)
    annotation.set_opacity(0.12)
    annotation.set_info(title=MARKER_AUTHOR, content=content)
    annotation.update()


def _preview_page(page: fitz.Page, destination: Path, dpi: int = 112) -> None:
    scale = _clamped_render_scale(page.rect, dpi)
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        colorspace=fitz.csRGB,
        alpha=False,
        annots=True,
    )
    destination.write_bytes(pixmap.tobytes("jpeg", jpg_quality=84))


def _comparison_pdf(
    old_doc: fitz.Document,
    new_doc: fitz.Document,
    alignment: Sequence[tuple[int | None, int | None]],
    destination: Path,
) -> None:
    report = fitz.open()
    default_width, default_height = fitz.paper_size("a4")
    gutter = 28.0
    header = 42.0
    for row_number, (old_index, new_index) in enumerate(alignment, start=1):
        old_page = old_doc[old_index] if old_index is not None else None
        new_page = new_doc[new_index] if new_index is not None else None
        old_width = old_page.rect.width if old_page else (new_page.rect.width if new_page else default_width)
        new_width = new_page.rect.width if new_page else (old_page.rect.width if old_page else default_width)
        old_height = old_page.rect.height if old_page else (new_page.rect.height if new_page else default_height)
        new_height = new_page.rect.height if new_page else (old_page.rect.height if old_page else default_height)
        report_page = report.new_page(
            width=old_width + gutter + new_width,
            height=header + max(old_height, new_height),
        )
        report_page.draw_rect(report_page.rect, color=(0.87, 0.88, 0.90), fill=(0.98, 0.98, 0.97))
        old_label = f"OLD  p.{old_index + 1}" if old_index is not None else "OLD  (no page)"
        new_label = f"NEW  p.{new_index + 1}" if new_index is not None else "NEW  (no page)"
        report_page.insert_text((12, 25), old_label, fontsize=11, fontname="helv", color=(0.16, 0.18, 0.22))
        report_page.insert_text(
            (old_width + gutter + 12, 25),
            new_label,
            fontsize=11,
            fontname="helv",
            color=(0.16, 0.18, 0.22),
        )
        report_page.insert_text(
            (max(12.0, old_width + gutter / 2 - 12), 25),
            f"{row_number}",
            fontsize=8,
            fontname="helv",
            color=(0.45, 0.48, 0.52),
        )
        if old_page:
            report_page.show_pdf_page(
                fitz.Rect(0, header, old_width, header + old_height),
                old_doc,
                old_index,
            )
        if new_page:
            report_page.show_pdf_page(
                fitz.Rect(old_width + gutter, header, old_width + gutter + new_width, header + new_height),
                new_doc,
                new_index,
            )
    if report.page_count:
        report.set_metadata(
            {
                "title": "kogo - Side-by-side comparison",
                "creator": MARKER_AUTHOR,
            }
        )
        report.save(destination, garbage=4, deflate=True)
    report.close()


def _artifact_info(path: Path, label: str) -> dict[str, Any]:
    return {
        "name": path.name,
        "label": label,
        "size": path.stat().st_size,
    }
