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

import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Sequence

import pymupdf as fitz


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
