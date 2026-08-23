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

"""Typed shape of the dict returned by `compare_pdfs` (and `result.json`).

These are `TypedDict`s for static type-checking and editor autocomplete only;
`compare_pdfs` still returns (and writes) a plain dict at runtime, so this is
purely additive and never changes behavior.
"""

from __future__ import annotations

from typing import TypedDict


class FileInfo(TypedDict):
    name: str
    pages: int


class Files(TypedDict):
    old: FileInfo
    new: FileInfo


class Settings(TypedDict):
    dpi: int
    sensitivity: str
    large_document_fallback: bool


class Summary(TypedDict):
    compared_rows: int
    changed_pages: int
    unchanged_pages: int
    added_pages: int
    deleted_pages: int
    added_words: int
    deleted_words: int
    visual_regions: int
    annotation_changes: int
    added_annotations: int
    deleted_annotations: int
    style_changes: int


class Legend(TypedDict):
    added: str
    deleted: str
    visual: str
    annotation: str
    style: str


class ArtifactInfo(TypedDict):
    name: str
    label: str
    size: int


class Artifacts(TypedDict):
    old: ArtifactInfo
    new: ArtifactInfo
    side_by_side: ArtifactInfo


class _PageRefRequired(TypedDict):
    page: int


class PageRef(_PageRefRequired, total=False):
    # Present only when `compare_pdfs(..., previews=True)`.
    preview: str


class RowChanges(TypedDict):
    added_words: int
    deleted_words: int
    visual_regions: int
    visual_regions_truncated: bool
    added_annotations: int
    deleted_annotations: int
    style_changes: int
    added_snippets: list[str]
    deleted_snippets: list[str]


class Row(TypedDict):
    row: int
    kind: str  # "unchanged" | "changed" | "added_page" | "deleted_page"
    has_changes: bool
    old: PageRef | None
    new: PageRef | None
    changes: RowChanges


class ComparisonResult(TypedDict):
    files: Files
    settings: Settings
    summary: Summary
    legend: Legend
    # None when `compare_pdfs(..., artifacts=False)`.
    artifacts: Artifacts | None
    rows: list[Row]
