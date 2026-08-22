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

from dataclasses import dataclass
from typing import Any, Sequence

import pymupdf as fitz

from .render import MARKER_AUTHOR
from .words import _normalize_word


@dataclass(frozen=True)
class AnnotationSnapshot:
    fingerprint: tuple[Any, ...]
    display_rects: tuple[tuple[float, float, float, float], ...]


def _normalized_rect(rect: fitz.Rect, page_rect: fitz.Rect) -> tuple[float, float, float, float]:
    width = max(page_rect.width, 1.0)
    height = max(page_rect.height, 1.0)
    return (
        round((rect.x0 - page_rect.x0) / width, 4),
        round((rect.y0 - page_rect.y0) / height, 4),
        round((rect.x1 - page_rect.x0) / width, 4),
        round((rect.y1 - page_rect.y0) / height, 4),
    )


def _annotation_snapshots(page: fitz.Page) -> list[AnnotationSnapshot]:
    snapshots: list[AnnotationSnapshot] = []
    for annotation in page.annots() or []:
        info = annotation.info or {}
        if info.get("title") in {MARKER_AUTHOR, "byobu", "PDF Diff Lab"}:
            # Derived markers should not multiply when an exported result is
            # compared again.
            continue
        annotation_type = annotation.type
        type_code = int(annotation_type[0])
        type_name = str(annotation_type[1])
        rect = fitz.Rect(annotation.rect)
        raw_vertices = annotation.vertices or []
        vertices: list[tuple[float, float]] = []
        for point in raw_vertices:
            try:
                x, y = float(point[0]), float(point[1])
            except (TypeError, ValueError, IndexError):
                continue
            vertices.append((x, y))
        normalized_vertices = tuple(
            (
                round((x - page.rect.x0) / max(page.rect.width, 1.0), 4),
                round((y - page.rect.y0) / max(page.rect.height, 1.0), 4),
            )
            for x, y in vertices
        )
        colors = annotation.colors or {}
        stroke = tuple(round(float(value), 3) for value in (colors.get("stroke") or []))
        fill = tuple(round(float(value), 3) for value in (colors.get("fill") or []))
        border = annotation.border or {}
        dashes = tuple(round(float(value), 2) for value in (border.get("dashes") or []))
        content = " ".join(_normalize_word(str(info.get("content", ""))).split())
        subject = " ".join(_normalize_word(str(info.get("subject", ""))).split())
        fingerprint: tuple[Any, ...] = (
            type_code,
            type_name,
            _normalized_rect(rect, page.rect),
            normalized_vertices,
            stroke,
            fill,
            round(float(annotation.opacity), 3),
            round(float(border.get("width") or 0.0), 2),
            dashes,
            content,
            subject,
            int(annotation.flags),
        )

        display_rects: list[tuple[float, float, float, float]] = []
        if type_code in {8, 9, 10, 11} and len(vertices) >= 4:
            for index in range(0, len(vertices) - 3, 4):
                quad = vertices[index : index + 4]
                display_rects.append(
                    (
                        min(point[0] for point in quad),
                        min(point[1] for point in quad),
                        max(point[0] for point in quad),
                        max(point[1] for point in quad),
                    )
                )
        if not display_rects:
            display_rects.append((rect.x0, rect.y0, rect.x1, rect.y1))
        snapshots.append(AnnotationSnapshot(fingerprint, tuple(display_rects)))
    return snapshots


def _annotation_differences(
    old_annotations: Sequence[AnnotationSnapshot],
    new_annotations: Sequence[AnnotationSnapshot],
) -> tuple[list[AnnotationSnapshot], list[AnnotationSnapshot]]:
    new_by_fingerprint: dict[tuple[Any, ...], list[AnnotationSnapshot]] = {}
    for annotation in new_annotations:
        new_by_fingerprint.setdefault(annotation.fingerprint, []).append(annotation)
    deleted: list[AnnotationSnapshot] = []
    for annotation in old_annotations:
        matches = new_by_fingerprint.get(annotation.fingerprint)
        if matches:
            matches.pop()
            if not matches:
                new_by_fingerprint.pop(annotation.fingerprint, None)
        else:
            deleted.append(annotation)
    added = [annotation for matches in new_by_fingerprint.values() for annotation in matches]
    return deleted, added
