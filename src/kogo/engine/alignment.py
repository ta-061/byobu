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
from collections import Counter
from typing import Sequence

import cv2
import pymupdf as fitz
import numpy as np

from .words import Word, _is_cjk


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
