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

import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Sequence

from .words import Word, TextLine, _is_cjk, _words_rect


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
