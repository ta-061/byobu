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

"""Layout-aware PDF comparison engine.

Text is compared at word precision (character precision for CJK languages)
after reconstructing a reading order from page whitespace. Figures,
equations, and layout changes are detected as pixel differences outside
text areas. Pages are aligned with a similarity-based sequence alignment
so inserted or removed pages do not desynchronize the comparison.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Sequence

import cv2
import pymupdf as fitz
import numpy as np


__all__ = ["compare_pdfs", "ComparisonError"]

MARKER_AUTHOR = "kogo"

ADD_COLOR = (0.10, 0.72, 0.34)
DELETE_COLOR = (0.91, 0.25, 0.22)
VISUAL_COLOR = (0.49, 0.28, 0.88)
PAGE_COLOR = (0.96, 0.64, 0.10)
STYLE_COLOR = (0.95, 0.63, 0.08)

# Ceiling on rendered pixel area (width_px * height_px) for a single page.
# The PDF spec allows page boxes up to 14,400pt/side; without this, such a
# page rendered at the max supported DPI would allocate multi-gigabyte RGB
# buffers. Mirrors the fixed-thumbnail approach already used for signatures.
MAX_RENDER_PIXELS = 40_000_000

# Link kinds PyMuPDF exposes as safe to keep on baked output pages. Anything
# else (Launch, GoToR, and actions such as SubmitForm/ImportData/JavaScript,
# which PyMuPDF folds into LINK_NAMED/LINK_NONE) is active content and is
# dropped by _scrub_active_content.
_SAFE_LINK_KINDS = frozenset((fitz.LINK_GOTO, fitz.LINK_URI))


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
    for page in doc:
        for link in list(page.links()):
            if link.get("kind") not in _SAFE_LINK_KINDS:
                page.delete_link(link)


class ComparisonError(ValueError):
    """A user-facing PDF comparison error."""


@dataclass(frozen=True)
class Word:
    text: str
    normalized: str
    rect: fitz.Rect
    block: int
    line: int
    order: int
    size: float
    bold: bool
    italic: bool


@dataclass(frozen=True)
class TextLine:
    page: int
    words: tuple[Word, ...]
    rect: fitz.Rect


@dataclass(frozen=True)
class VisualRegion:
    old_rect: fitz.Rect
    new_rect: fitz.Rect


@dataclass(frozen=True)
class AnnotationSnapshot:
    fingerprint: tuple[Any, ...]
    display_rects: tuple[tuple[float, float, float, float], ...]


def _normalize_word(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u00ad", "").strip()
    return value


def _is_cjk(character: str) -> bool:
    if not character:
        return False
    codepoint = ord(character[0])
    return (
        0x3040 <= codepoint <= 0x30FF  # Hiragana / Katakana
        or 0x3400 <= codepoint <= 0x4DBF  # CJK Extension A
        or 0x4E00 <= codepoint <= 0x9FFF  # CJK Unified Ideographs
        or 0xF900 <= codepoint <= 0xFAFF  # CJK Compatibility Ideographs
        or 0xAC00 <= codepoint <= 0xD7AF  # Hangul syllables
        or 0xFF65 <= codepoint <= 0xFF9F  # Halfwidth Katakana
        or 0x20000 <= codepoint <= 0x3347F  # CJK Extensions B-J and supplements
    )


def _is_joined_word_character(character: str) -> bool:
    category = unicodedata.category(character)
    return category[0] in {"L", "M", "N"} or character in {"'", "’", "-", "_"}


def _page_words(page: fitz.Page) -> list[Word]:
    """Extract positioned tokens, keeping CJK changes at character precision."""
    words: list[Word] = []
    order = 0
    raw = page.get_text("rawdict", sort=True)
    for block_position, block in enumerate(raw.get("blocks", [])):
        if block.get("type") != 0:
            continue
        block_number = int(block.get("number", block_position))
        for line_number, line in enumerate(block.get("lines", [])):
            pending_chars: list[str] = []
            pending_rect: fitz.Rect | None = None
            pending_style: tuple[float, bool, bool] | None = None

            def flush_pending() -> None:
                nonlocal order, pending_rect, pending_style
                if not pending_chars or pending_rect is None:
                    pending_chars.clear()
                    pending_rect = None
                    pending_style = None
                    return
                text = "".join(pending_chars)
                normalized = _normalize_word(text)
                if normalized:
                    size, bold, italic = pending_style or (0.0, False, False)
                    words.append(
                        Word(
                            text=text,
                            normalized=normalized,
                            rect=fitz.Rect(pending_rect),
                            block=block_number,
                            line=line_number,
                            order=order,
                            size=size,
                            bold=bold,
                            italic=italic,
                        )
                    )
                    order += 1
                pending_chars.clear()
                pending_rect = None
                pending_style = None

            for span in line.get("spans", []):
                span_size = round(float(span.get("size", 0.0)), 1)
                span_flags = int(span.get("flags", 0))
                span_bold = bool(span_flags & 16)
                span_italic = bool(span_flags & 2)
                for character_data in span.get("chars", []):
                    character = str(character_data.get("c", ""))
                    if not character:
                        continue
                    rect = fitz.Rect(character_data.get("bbox", (0, 0, 0, 0)))
                    if character.isspace():
                        flush_pending()
                    elif _is_cjk(character) or not _is_joined_word_character(character):
                        flush_pending()
                        normalized = _normalize_word(character)
                        if normalized:
                            words.append(
                                Word(
                                    text=character,
                                    normalized=normalized,
                                    rect=rect,
                                    block=block_number,
                                    line=line_number,
                                    order=order,
                                    size=span_size,
                                    bold=span_bold,
                                    italic=span_italic,
                                )
                            )
                            order += 1
                    else:
                        pending_chars.append(character)
                        if pending_rect is None:
                            pending_rect = fitz.Rect(rect)
                            pending_style = (span_size, span_bold, span_italic)
                        else:
                            pending_rect.include_rect(rect)
            flush_pending()
    return _layout_order_words(words)


def _words_rect(words: Sequence[Word]) -> fitz.Rect:
    rect = fitz.Rect(words[0].rect)
    for word in words[1:]:
        rect.include_rect(word.rect)
    return rect


def _largest_axis_gap(
    blocks: Sequence[tuple[int, fitz.Rect, tuple[Word, ...]]],
    axis: str,
) -> tuple[
    float,
    list[tuple[int, fitz.Rect, tuple[Word, ...]]],
    list[tuple[int, fitz.Rect, tuple[Word, ...]]],
] | None:
    """Return the widest whitespace cut that no text block crosses."""
    low, high = (0, 2) if axis == "x" else (1, 3)
    ordered = sorted(blocks, key=lambda item: (item[1][low], item[1][high], item[0]))
    if len(ordered) < 2:
        return None

    best: tuple[
        float,
        list[tuple[int, fitz.Rect, tuple[Word, ...]]],
        list[tuple[int, fitz.Rect, tuple[Word, ...]]],
    ] | None = None
    covered_until = ordered[0][1][high]
    for index in range(1, len(ordered)):
        next_start = ordered[index][1][low]
        if next_start > covered_until:
            gap = next_start - covered_until
            if best is None or gap > best[0]:
                best = (gap, ordered[:index], ordered[index:])
        covered_until = max(covered_until, ordered[index][1][high])
    return best


def _layout_order_words(words: Sequence[Word]) -> list[Word]:
    """Order text by whitespace regions instead of interleaving page columns.

    PDF text streams rarely contain a reliable semantic reading order. Recursive
    XY cuts first separate headers / body / footers and then independent columns
    or slide text boxes. This also works for one-column documents because no
    vertical cut is made when blocks span the page width.
    """
    if len(words) < 2:
        return list(words)

    by_block: dict[int, list[Word]] = defaultdict(list)
    for word in words:
        by_block[word.block].append(word)
    blocks = [
        (block, _words_rect(block_words), tuple(block_words))
        for block, block_words in by_block.items()
    ]
    word_heights = [word.rect.height for word in words if word.rect.height > 0]
    text_height = max(6.0, median(word_heights) if word_heights else 10.0)

    def cut(
        items: Sequence[tuple[int, fitz.Rect, tuple[Word, ...]]],
    ) -> list[tuple[int, fitz.Rect, tuple[Word, ...]]]:
        # An explicit worklist avoids Python's recursion limit on pages with
        # many independent blocks (dense grids/forms can peel off one block
        # per cut, producing recursion depth equal to the block count).
        result: list[tuple[int, fitz.Rect, tuple[Word, ...]]] = []
        stack: list[Sequence[tuple[int, fitz.Rect, tuple[Word, ...]]]] = [items]
        while stack:
            current = stack.pop()
            if len(current) < 2:
                result.extend(current)
                continue
            horizontal = _largest_axis_gap(current, "x")
            vertical = _largest_axis_gap(current, "y")
            candidates: list[
                tuple[
                    float,
                    int,
                    tuple[
                        float,
                        list[tuple[int, fitz.Rect, tuple[Word, ...]]],
                        list[tuple[int, fitz.Rect, tuple[Word, ...]]],
                    ],
                ]
            ] = []
            if horizontal and horizontal[0] >= max(10.0, text_height * 0.8):
                candidates.append((horizontal[0] / max(text_height * 0.55, 4.0), 1, horizontal))
            if vertical and vertical[0] >= max(7.0, text_height * 0.55):
                # Prefer a top/bottom band split when normalized gaps are tied.
                candidates.append((vertical[0] / max(text_height, 6.0), 2, vertical))
            if not candidates:
                result.extend(
                    sorted(current, key=lambda item: (round(item[1].y0, 1), item[1].x0, item[0]))
                )
                continue
            _, _, selected = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))
            # Push the second half first so the first half is popped (and thus
            # fully expanded) before it, matching cut(low) + cut(high) order.
            stack.append(selected[2])
            stack.append(selected[1])
        return result

    ordered: list[Word] = []
    for _, _, block_words in cut(blocks):
        ordered.extend(sorted(block_words, key=lambda word: (word.line, word.order)))
    return ordered


def _signature(words: Sequence[Word]) -> Counter[str]:
    result: Counter[str] = Counter()

    def add_cjk_run(run: list[str]) -> None:
        if not run:
            return
        if len(run) < 3:
            result["".join(run).casefold()] += 1
        else:
            for index in range(len(run) - 2):
                result["".join(run[index : index + 3]).casefold()] += 1

    cjk_run: list[str] = []
    for word in words:
        if len(word.normalized) == 1 and _is_cjk(word.normalized):
            cjk_run.append(word.normalized)
            continue
        add_cjk_run(cjk_run)
        cjk_run.clear()
        token = re.sub(r"\W+", "", word.normalized.casefold(), flags=re.UNICODE)
        if len(token) >= 2 and not token.isdecimal():
            result[token] += 1
    add_cjk_run(cjk_run)
    return result


def _signature_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left and not right:
        return 0.72
    if not left or not right:
        return 0.0
    overlap = sum((left & right).values())
    return (2.0 * overlap) / (sum(left.values()) + sum(right.values()))


def _page_visual_signature(page: fitz.Page, size: int = 48) -> np.ndarray:
    scale = min(0.35, 110.0 / max(page.rect.width, page.rect.height, 1.0))
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        colorspace=fitz.csGRAY,
        alpha=False,
        annots=False,
    )
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width)
    thumbnail = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)
    # Ink rather than raw white pixels keeps unrelated mostly-white pages from
    # appearing deceptively similar.
    return (255.0 - thumbnail.astype(np.float32)) / 255.0


def _page_visual_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm < 1e-6 and right_norm < 1e-6:
        return 0.72
    if left_norm < 1e-6 or right_norm < 1e-6:
        return 0.0
    cosine = float(np.sum(left * right) / (left_norm * right_norm))
    density = min(float(np.sum(left)), float(np.sum(right))) / max(
        float(np.sum(left)), float(np.sum(right)), 1e-6
    )
    return max(0.0, min(1.0, 0.88 * cosine + 0.12 * density))


def align_pages(
    old_words: Sequence[Sequence[Word]],
    new_words: Sequence[Sequence[Word]],
    old_visual: Sequence[np.ndarray] | None = None,
    new_visual: Sequence[np.ndarray] | None = None,
) -> list[tuple[int | None, int | None]]:
    """Align pages in order, allowing inserted or removed pages."""
    old_count, new_count = len(old_words), len(new_words)
    old_signatures = [_signature(words) for words in old_words]
    new_signatures = [_signature(words) for words in new_words]
    gap = -0.42
    scores = np.full((old_count + 1, new_count + 1), -np.inf, dtype=np.float64)
    moves = np.zeros((old_count + 1, new_count + 1), dtype=np.uint8)
    scores[0, 0] = 0.0
    for i in range(1, old_count + 1):
        scores[i, 0] = i * gap
        moves[i, 0] = 1
    for j in range(1, new_count + 1):
        scores[0, j] = j * gap
        moves[0, j] = 2

    for i in range(1, old_count + 1):
        for j in range(1, new_count + 1):
            similarity = _signature_similarity(old_signatures[i - 1], new_signatures[j - 1])
            if (
                old_visual is not None
                and new_visual is not None
                and (len(old_words[i - 1]) < 20 or len(new_words[j - 1]) < 20)
            ):
                similarity = _page_visual_similarity(old_visual[i - 1], new_visual[j - 1])
            old_pos = i / max(old_count, 1)
            new_pos = j / max(new_count, 1)
            positional_bonus = max(0.0, 0.08 - abs(old_pos - new_pos) * 0.12)
            candidates = (
                scores[i - 1, j - 1] + (1.85 * similarity - 1.327) + positional_bonus,
                scores[i - 1, j] + gap,
                scores[i, j - 1] + gap,
            )
            move = int(np.argmax(candidates))
            scores[i, j] = candidates[move]
            moves[i, j] = move

    aligned: list[tuple[int | None, int | None]] = []
    i, j = old_count, new_count
    while i or j:
        move = int(moves[i, j])
        if i and j and move == 0:
            aligned.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif i and (not j or move == 1):
            aligned.append((i - 1, None))
            i -= 1
        else:
            aligned.append((None, j - 1))
            j -= 1
    aligned.reverse()
    return aligned


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


def _changed_words(
    old_words: Sequence[Word], new_words: Sequence[Word]
) -> tuple[list[Word], list[Word]]:
    matcher = SequenceMatcher(
        None,
        [word.normalized for word in old_words],
        [word.normalized for word in new_words],
        autojunk=False,
    )
    deleted: list[Word] = []
    added: list[Word] = []
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            deleted.extend(old_words[old_start:old_end])
        if tag in {"replace", "insert"}:
            added.extend(new_words[new_start:new_end])
    return deleted, added


def _text_lines(words_by_page: Sequence[Sequence[Word]]) -> list[list[TextLine]]:
    pages: list[list[TextLine]] = []
    for page_index, words in enumerate(words_by_page):
        grouped: dict[tuple[int, int], list[Word]] = defaultdict(list)
        for word in words:
            grouped[(word.block, word.line)].append(word)
        pages.append(
            [
                TextLine(page_index, tuple(line_words), _words_rect(line_words))
                for line_words in grouped.values()
            ]
        )
    return pages


def _line_signature(line: TextLine) -> tuple[str, ...]:
    return tuple(word.normalized for word in line.words)


def _meaningful_line_signature(signature: Sequence[str]) -> bool:
    compact = re.sub(r"[\W_]+", "", "".join(signature), flags=re.UNICODE)
    if len(compact) >= 3:
        return True
    # Short table / equation labels such as PI, PS, and PC are meaningful,
    # whereas a lone CJK character or page number is too ambiguous globally.
    return len(signature) == 1 and bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9]+", compact))


def _match_exact_lines(
    old_lines: Sequence[TextLine],
    new_lines: Sequence[TextLine],
    matched_old: set[int],
    matched_new: set[int],
    style_changes: list[tuple[Word, Word]] | None = None,
) -> None:
    """Suppress identical text lines even when their page or position moved."""
    old_by_signature: dict[tuple[str, ...], list[TextLine]] = defaultdict(list)
    new_by_signature: dict[tuple[str, ...], list[TextLine]] = defaultdict(list)
    for line in old_lines:
        if not any(id(word) in matched_old for word in line.words):
            signature = _line_signature(line)
            if _meaningful_line_signature(signature):
                old_by_signature[signature].append(line)
    for line in new_lines:
        if not any(id(word) in matched_new for word in line.words):
            signature = _line_signature(line)
            if _meaningful_line_signature(signature):
                new_by_signature[signature].append(line)

    for signature, old_matches in old_by_signature.items():
        new_matches = new_by_signature.get(signature)
        if not new_matches:
            continue
        old_matches.sort(key=lambda line: (line.page, line.rect.y0, line.rect.x0))
        new_matches.sort(key=lambda line: (line.page, line.rect.y0, line.rect.x0))
        for old_line, new_line in zip(old_matches, new_matches):
            matched_old.update(id(word) for word in old_line.words)
            matched_new.update(id(word) for word in new_line.words)
            if style_changes is not None:
                for old_word, new_word in zip(old_line.words, new_line.words):
                    if (old_word.size, old_word.bold, old_word.italic) != (
                        new_word.size,
                        new_word.bold,
                        new_word.italic,
                    ):
                        style_changes.append((old_word, new_word))


def _document_text_differences(
    old_words_by_page: Sequence[Sequence[Word]],
    new_words_by_page: Sequence[Sequence[Word]],
    alignment: Sequence[tuple[int | None, int | None]],
) -> tuple[list[list[Word]], list[list[Word]], dict[tuple[int, int], list[tuple[Word, Word]]], bool]:
    """Diff text across the document while tolerating layout and page reflow.

    Exact lines are matched independently of position first. Remaining text is
    compared in whitespace-derived reading order across page boundaries. The
    two stages prevent unchanged columns, slide text boxes, and table cells from
    becoming delete/insert pairs merely because their PDF extraction order moved.
    """
    old_lines_by_page = _text_lines(old_words_by_page)
    new_lines_by_page = _text_lines(new_words_by_page)
    matched_old: set[int] = set()
    matched_new: set[int] = set()
    style_changes_by_pair: dict[tuple[int, int], list[tuple[Word, Word]]] = {}

    # Prefer same-row matches so repeated headers and labels remain associated
    # with the correct page. A second pass then handles genuine page reflow.
    # Style changes are only collected here, on unchanged-position lines; the
    # document-wide reflow pass below does not report them.
    for old_index, new_index in alignment:
        if old_index is not None and new_index is not None:
            pair_style_changes: list[tuple[Word, Word]] = []
            _match_exact_lines(
                old_lines_by_page[old_index],
                new_lines_by_page[new_index],
                matched_old,
                matched_new,
                pair_style_changes,
            )
            if pair_style_changes:
                style_changes_by_pair[(old_index, new_index)] = pair_style_changes
    _match_exact_lines(
        [line for page in old_lines_by_page for line in page],
        [line for page in new_lines_by_page for line in page],
        matched_old,
        matched_new,
        None,
    )

    old_remaining_by_page = [
        [word for word in words if id(word) not in matched_old] for words in old_words_by_page
    ]
    new_remaining_by_page = [
        [word for word in words if id(word) not in matched_new] for words in new_words_by_page
    ]
    old_remaining = [word for page in old_remaining_by_page for word in page]
    new_remaining = [word for page in new_remaining_by_page for word in page]

    # SequenceMatcher with autojunk disabled is important for CJK characters,
    # but its worst case is quadratic. Similar revisions leave few words after
    # exact-line matching; unrelated very large documents use bounded page pairs.
    large_document_fallback = len(old_remaining) * len(new_remaining) > 60_000_000
    if not large_document_fallback:
        deleted, added = _changed_words(old_remaining, new_remaining)
    else:
        deleted = []
        added = []
        for old_index, new_index in alignment:
            if old_index is not None and new_index is not None:
                page_deleted, page_added = _changed_words(
                    old_remaining_by_page[old_index], new_remaining_by_page[new_index]
                )
                deleted.extend(page_deleted)
                added.extend(page_added)
            elif old_index is not None:
                deleted.extend(old_remaining_by_page[old_index])
            elif new_index is not None:
                added.extend(new_remaining_by_page[new_index])

    old_page_for_word = {
        id(word): page_index
        for page_index, words in enumerate(old_words_by_page)
        for word in words
    }
    new_page_for_word = {
        id(word): page_index
        for page_index, words in enumerate(new_words_by_page)
        for word in words
    }
    deleted_by_page: list[list[Word]] = [[] for _ in old_words_by_page]
    added_by_page: list[list[Word]] = [[] for _ in new_words_by_page]
    for word in deleted:
        deleted_by_page[old_page_for_word[id(word)]].append(word)
    for word in added:
        added_by_page[new_page_for_word[id(word)]].append(word)
    return deleted_by_page, added_by_page, style_changes_by_pair, large_document_fallback


def _difference_snippets(words: Sequence[Word], limit: int = 6) -> list[str]:
    if not words:
        return []
    chunks: list[list[Word]] = [[words[0]]]
    for word in words[1:]:
        previous = chunks[-1][-1]
        if (
            word.block == previous.block
            and word.line == previous.line
            and word.order == previous.order + 1
        ):
            chunks[-1].append(word)
        else:
            chunks.append([word])
    return [_snippet(chunk) for chunk in chunks[:limit]]


def _is_single_cjk_word(word: Word) -> bool:
    return len(word.normalized) == 1 and _is_cjk(word.normalized)


def _snippet(words: Sequence[Word], limit: int = 120) -> str:
    parts: list[str] = []
    for index, word in enumerate(words):
        if index > 0 and not (
            _is_single_cjk_word(words[index - 1]) and _is_single_cjk_word(word)
        ):
            parts.append(" ")
        parts.append(word.text)
    text = "".join(parts)
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _clamp_rect(rect: fitz.Rect, page_rect: fitz.Rect, inset: float = 0.0) -> fitz.Rect | None:
    x0 = max(page_rect.x0 + inset, rect.x0)
    y0 = max(page_rect.y0 + inset, rect.y0)
    x1 = min(page_rect.x1 - inset, rect.x1)
    y1 = min(page_rect.y1 - inset, rect.y1)
    if x1 <= x0 or y1 <= y0:
        return None
    return fitz.Rect(x0, y0, x1, y1)


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


def _clamped_render_scale(rect: fitz.Rect, dpi: int) -> float:
    """Scale factor for `dpi`, reduced so the rendered pixel area stays under
    MAX_RENDER_PIXELS (same pattern as `_page_visual_signature`'s fixed thumbnail)."""
    scale = dpi / 72.0
    area = (rect.width * scale) * (rect.height * scale)
    if area > MAX_RENDER_PIXELS:
        scale *= math.sqrt(MAX_RENDER_PIXELS / max(area, 1.0))
    return scale


def _render_page(page: fitz.Page, dpi: int, *, annotations: bool = False) -> np.ndarray:
    scale = _clamped_render_scale(page.rect, dpi)
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        colorspace=fitz.csRGB,
        alpha=False,
        annots=annotations,
    )
    array = np.frombuffer(pixmap.samples, dtype=np.uint8)
    return array.reshape(pixmap.height, pixmap.width, pixmap.n)[:, :, :3].copy()


def _mask_words(
    mask: np.ndarray,
    words: Sequence[Word],
    page_rect: fitz.Rect,
) -> None:
    height, width = mask.shape[:2]
    scale_x = width / max(page_rect.width, 1.0)
    scale_y = height / max(page_rect.height, 1.0)
    for word in words:
        x0 = max(0, int((word.rect.x0 - page_rect.x0) * scale_x) - 3)
        y0 = max(0, int((word.rect.y0 - page_rect.y0) * scale_y) - 3)
        x1 = min(width - 1, int(math.ceil((word.rect.x1 - page_rect.x0) * scale_x)) + 3)
        y1 = min(height - 1, int(math.ceil((word.rect.y1 - page_rect.y0) * scale_y)) + 3)
        if x1 > x0 and y1 > y0:
            cv2.rectangle(mask, (x0, y0), (x1, y1), 255, thickness=-1)


def _estimate_page_translation(
    old_image: np.ndarray,
    new_image: np.ndarray,
) -> tuple[float, float]:
    """Estimate a small scanner/export translation using page edge structure."""
    height, width = old_image.shape[:2]
    longest = max(height, width)
    scale = min(1.0, 900.0 / max(longest, 1))
    if scale < 1.0:
        sample_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        old_sample = cv2.resize(old_image, sample_size, interpolation=cv2.INTER_AREA)
        new_sample = cv2.resize(new_image, sample_size, interpolation=cv2.INTER_AREA)
    else:
        old_sample = old_image
        new_sample = new_image

    old_gray = cv2.cvtColor(old_sample, cv2.COLOR_RGB2GRAY)
    new_gray = cv2.cvtColor(new_sample, cv2.COLOR_RGB2GRAY)
    old_edges = cv2.Canny(old_gray, 70, 180).astype(np.float32)
    new_edges = cv2.Canny(new_gray, 70, 180).astype(np.float32)
    if np.count_nonzero(old_edges) < 80 or np.count_nonzero(new_edges) < 80:
        return 0.0, 0.0

    window = cv2.createHanningWindow(
        (old_edges.shape[1], old_edges.shape[0]),
        cv2.CV_32F,
    )
    (sample_x, sample_y), response = cv2.phaseCorrelate(old_edges, new_edges, window)
    if not math.isfinite(response) or response < 0.18:
        return 0.0, 0.0
    shift_x = sample_x / scale
    shift_y = sample_y / scale
    if abs(shift_x) > width * 0.012 or abs(shift_y) > height * 0.012:
        return 0.0, 0.0
    if abs(shift_x) < 0.35 and abs(shift_y) < 0.35:
        return 0.0, 0.0
    return shift_x, shift_y


def _visual_differences(
    old_page: fitz.Page,
    new_page: fitz.Page,
    old_words: Sequence[Word],
    new_words: Sequence[Word],
    dpi: int,
    sensitivity: str,
) -> tuple[list[VisualRegion], bool]:
    old_image = _render_page(old_page, dpi)
    new_image = _render_page(new_page, dpi)
    target_height, target_width = old_image.shape[:2]
    if new_image.shape[:2] != (target_height, target_width):
        new_image = cv2.resize(
            new_image,
            (target_width, target_height),
            interpolation=cv2.INTER_AREA,
        )

    # Dense selectable text is already compared semantically and may genuinely
    # reflow. Registration is reserved for image-only / image-dominant pages,
    # where a small scanner offset would otherwise paint the whole page purple.
    if len(old_words) < 20 and len(new_words) < 20:
        shift_x, shift_y = _estimate_page_translation(old_image, new_image)
    else:
        shift_x, shift_y = 0.0, 0.0
    validity = np.full((target_height, target_width), 255, dtype=np.uint8)
    if shift_x or shift_y:
        align_matrix = np.float32([[1.0, 0.0, -shift_x], [0.0, 1.0, -shift_y]])
        new_image = cv2.warpAffine(
            new_image,
            align_matrix,
            (target_width, target_height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),
        )
        validity = cv2.warpAffine(
            validity,
            align_matrix,
            (target_width, target_height),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )

    settings = {
        "high": (18, 18),
        "standard": (28, 34),
        "low": (42, 72),
    }
    threshold, min_pixels = settings.get(sensitivity, settings["standard"])
    raw_diff = cv2.absdiff(old_image, new_image).max(axis=2).astype(np.uint8)
    blurred = cv2.GaussianBlur(raw_diff, (3, 3), 0)
    binary = np.where(blurred >= threshold, 255, 0).astype(np.uint8)

    # Text is diffed semantically. Removing all detected glyph areas here prevents
    # each changed letter from being reported again as a figure difference.
    old_text_mask = np.zeros_like(binary)
    new_text_mask = np.zeros_like(binary)
    _mask_words(old_text_mask, old_words, old_page.rect)
    _mask_words(new_text_mask, new_words, new_page.rect)
    if shift_x or shift_y:
        new_text_mask = cv2.warpAffine(
            new_text_mask,
            align_matrix,
            (target_width, target_height),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
    binary[np.maximum(old_text_mask, new_text_mask) > 0] = 0
    binary[validity == 0] = 0

    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    grouped = cv2.dilate(binary, np.ones((9, 9), np.uint8), iterations=1)
    components, _, stats, _ = cv2.connectedComponentsWithStats(grouped, connectivity=8)
    boxes: list[tuple[int, int, int, int, int]] = []
    for label in range(1, components):
        x, y, width, height, _ = [int(value) for value in stats[label]]
        changed_pixels = int(np.count_nonzero(binary[y : y + height, x : x + width]))
        if changed_pixels < min_pixels or width < 5 or height < 5:
            continue
        boxes.append((x, y, width, height, changed_pixels))

    # Keep previews and output PDFs responsive even for scanned pages with noise.
    boxes.sort(key=lambda item: item[4], reverse=True)
    truncated = len(boxes) > 120
    boxes = boxes[:120]
    boxes.sort(key=lambda item: (item[1], item[0]))

    old_scale_x = old_page.rect.width / max(target_width, 1)
    old_scale_y = old_page.rect.height / max(target_height, 1)
    new_scale_x = new_page.rect.width / max(target_width, 1)
    new_scale_y = new_page.rect.height / max(target_height, 1)
    regions: list[VisualRegion] = []
    for x, y, width, height, _ in boxes:
        pad = 3
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(target_width, x + width + pad), min(target_height, y + height + pad)
        regions.append(
            VisualRegion(
                old_rect=fitz.Rect(
                    old_page.rect.x0 + x0 * old_scale_x,
                    old_page.rect.y0 + y0 * old_scale_y,
                    old_page.rect.x0 + x1 * old_scale_x,
                    old_page.rect.y0 + y1 * old_scale_y,
                ),
                new_rect=fitz.Rect(
                    new_page.rect.x0 + (x0 + shift_x) * new_scale_x,
                    new_page.rect.y0 + (y0 + shift_y) * new_scale_y,
                    new_page.rect.x0 + (x1 + shift_x) * new_scale_x,
                    new_page.rect.y0 + (y1 + shift_y) * new_scale_y,
                ),
            )
        )
    return regions, truncated


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
) -> dict[str, Any]:
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

    Returns:
        A dict (also written to output_dir/result.json) with keys:

        - "files": {"old": {"name", "pages"}, "new": {"name", "pages"}}
        - "settings": {"dpi", "sensitivity", "large_document_fallback"}
        - "summary": counts such as "compared_rows", "changed_pages",
          "added_pages", "deleted_pages", "added_words", "deleted_words",
          "visual_regions", "style_changes", "annotation_changes"
        - "legend": human-readable color explanations
        - "artifacts": {"old", "new", "side_by_side"} ->
          {"name", "label", "size"}
        - "rows": one entry per aligned page pair with "kind"
          ("unchanged", "changed", "added_page", "deleted_page"),
          "old"/"new" page info, and "changes" counts/snippets

        Files written to output_dir: old-highlighted.pdf,
        new-highlighted.pdf, side-by-side.pdf, result.json, and
        previews/ when previews is True.

    Raises:
        ComparisonError: user-facing problems such as encrypted, empty,
            oversized, unreadable, or non-PDF input.

    Example:
        import kogo

        result = kogo.compare_pdfs("old.pdf", "new.pdf", "out/")
        print(result["summary"]["changed_pages"])
    """
    old_name = old_name or Path(old_path).name
    new_name = new_name or Path(new_path).name
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
        old_doc.set_metadata({**old_doc.metadata, "creator": MARKER_AUTHOR})
        new_doc.set_metadata({**new_doc.metadata, "creator": MARKER_AUTHOR})
        # Convert annotations into regular page content so markers remain visible
        # when printing or when a PDF viewer hides annotations by default.
        old_doc.bake(annots=True, widgets=False)
        new_doc.bake(annots=True, widgets=False)
        old_doc.save(old_output, garbage=4, deflate=True)
        new_doc.save(new_output, garbage=4, deflate=True)

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

        _comparison_pdf(old_doc, new_doc, alignment, compare_output)
        changed_pages = sum(1 for row in rows if row["has_changes"])
        result: dict[str, Any] = {
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
            "artifacts": {
                "old": _artifact_info(old_output, "Old version with deletions marked"),
                "new": _artifact_info(new_output, "New version with additions marked"),
                "side_by_side": _artifact_info(compare_output, "Side-by-side comparison"),
            },
            "rows": rows,
        }
        (output_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result
    finally:
        old_doc.close()
        new_doc.close()
