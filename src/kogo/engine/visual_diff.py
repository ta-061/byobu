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

import math
from dataclasses import dataclass
from typing import Sequence

import cv2
import pymupdf as fitz
import numpy as np

from .words import Word

# Ceiling on rendered pixel area (width_px * height_px) for a single page.
# The PDF spec allows page boxes up to 14,400pt/side; without this, such a
# page rendered at the max supported DPI would allocate multi-gigabyte RGB
# buffers. Mirrors the fixed-thumbnail approach already used for signatures.
#
# Sized against the default Docker deployment's memory budget, not just a
# single allocation: _visual_differences holds both pages' RGB images plus
# several transient single-channel buffers (diff/blur/masks/morphology) at
# once, roughly ~13 bytes/pixel combined, so one worst-case comparison at
# this ceiling is ~310MB; docker-compose.yml's default MAX_CONCURRENT_JOBS=2
# against mem_limit: 2g leaves comfortable headroom for two of those at once
# plus interpreter/library overhead. Raise together with those settings.
MAX_RENDER_PIXELS = 24_000_000


@dataclass(frozen=True)
class VisualRegion:
    old_rect: fitz.Rect
    new_rect: fitz.Rect


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
