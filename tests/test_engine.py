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

import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz

from kogo.engine import _is_cjk, compare_pdfs


def make_pdf(path: Path, pages: list[tuple[str, str]]) -> None:
    document = fitz.open()
    for text, figure in pages:
        page = document.new_page(width=595, height=842)
        page.insert_text((60, 75), "Revision comparison sample", fontsize=11)
        page.insert_textbox(fitz.Rect(60, 110, 535, 220), text, fontsize=14)
        if figure == "square":
            page.draw_rect(
                fitz.Rect(100, 300, 260, 440),
                color=(0.1, 0.3, 0.7),
                fill=(0.80, 0.88, 0.98),
                width=3,
            )
        elif figure == "circle":
            page.draw_circle(
                fitz.Point(195, 370),
                88,
                color=(0.7, 0.2, 0.2),
                fill=(0.98, 0.84, 0.82),
                width=3,
            )
    document.save(path)
    document.close()


def make_two_column_pdf(path: Path, *, reverse_vertical_order: bool = False) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((205, 65), "Two-column comparison", fontsize=13)
    left_lines = [
        "Left column first stable sentence.",
        "Left column second stable sentence.",
        "Left column third stable sentence.",
    ]
    right_lines = [
        "Right column first stable sentence.",
        "Right column second stable sentence.",
        "Right column third stable sentence.",
    ]
    left_y = (110, 140, 170) if not reverse_vertical_order else (125, 155, 185)
    right_y = (125, 155, 185) if not reverse_vertical_order else (110, 140, 170)
    for y, text in zip(left_y, left_lines):
        page.insert_text((55, y), text, fontsize=11)
    for y, text in zip(right_y, right_lines):
        page.insert_text((320, y), text, fontsize=11)
    document.save(path)
    document.close()


def make_slide_pdf(path: Path, *, updated: bool) -> None:
    document = fitz.open()
    page = document.new_page(width=960, height=540)
    page.insert_text((360, 55), "Quarterly review", fontsize=24)
    stable = "The reference panel remains exactly the same."
    changed = (
        "Deployment status is verified and ready."
        if updated
        else "Deployment status is stable and ready."
    )
    if updated:
        page.insert_textbox(fitz.Rect(80, 145, 430, 250), stable, fontsize=18)
        page.insert_textbox(fitz.Rect(530, 145, 880, 250), changed, fontsize=18)
    else:
        page.insert_textbox(fitz.Rect(80, 145, 430, 250), changed, fontsize=18)
        page.insert_textbox(fitz.Rect(530, 145, 880, 250), stable, fontsize=18)
    document.save(path)
    document.close()


def make_shifted_graphics_pdf(path: Path, *, offset: float) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.draw_rect(
        fitz.Rect(90 + offset, 120 + offset, 500 + offset, 690 + offset),
        color=(0.15, 0.15, 0.15),
        width=2,
    )
    for index in range(6):
        y = 180 + index * 70 + offset
        page.draw_line(
            fitz.Point(130 + offset, y),
            fitz.Point(450 + offset, y),
            color=(0.18, 0.35, 0.72),
            width=3,
        )
        page.draw_circle(
            fitz.Point(165 + offset, y),
            18,
            color=(0.75, 0.2, 0.2),
            fill=(0.96, 0.82, 0.80),
            width=2,
        )
    document.save(path)
    document.close()


def make_single_column_reflow_pdf(path: Path, *, width: float) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    text = (
        "A layout-aware comparison must preserve identical words when line wrapping changes. "
        "The paragraph remains semantically identical even when the available column width is different."
    )
    page.insert_textbox(fitz.Rect(60, 110, 60 + width, 400), text, fontsize=14)
    document.save(path)
    document.close()


def make_graphics_deck(path: Path, layouts: list[str]) -> None:
    document = fitz.open()
    for layout in layouts:
        page = document.new_page(width=640, height=360)
        if layout == "left":
            page.draw_rect(fitz.Rect(60, 70, 260, 290), color=(0.1, 0.2, 0.7), width=5)
        elif layout == "right":
            page.draw_circle(fitz.Point(500, 180), 95, color=(0.7, 0.2, 0.1), width=5)
        else:
            page.draw_line(
                fitz.Point(100, 80),
                fitz.Point(540, 280),
                color=(0.2, 0.6, 0.2),
                width=8,
            )
            page.draw_line(
                fitz.Point(540, 80),
                fitz.Point(100, 280),
                color=(0.2, 0.6, 0.2),
                width=8,
            )
    document.save(path)
    document.close()


class DiffEngineTests(unittest.TestCase):
    def test_image_only_inserted_page_uses_visual_page_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_graphics_deck(root / "old.pdf", ["left", "right"])
            make_graphics_deck(root / "new.pdf", ["left", "middle", "right"])

            result = compare_pdfs(
                root / "old.pdf",
                root / "new.pdf",
                root / "result",
                old_name="old.pdf",
                new_name="new.pdf",
                dpi=96,
            )

            self.assertEqual(
                [row["kind"] for row in result["rows"]],
                ["unchanged", "added_page", "unchanged"],
            )

    def test_single_column_line_wrapping_does_not_create_text_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_single_column_reflow_pdf(root / "old.pdf", width=470)
            make_single_column_reflow_pdf(root / "new.pdf", width=350)

            result = compare_pdfs(
                root / "old.pdf",
                root / "new.pdf",
                root / "result",
                old_name="old.pdf",
                new_name="new.pdf",
                dpi=96,
            )

            self.assertEqual(result["summary"]["added_words"], 0)
            self.assertEqual(result["summary"]["deleted_words"], 0)

    def test_small_image_only_page_translation_is_registered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_shifted_graphics_pdf(root / "old.pdf", offset=0)
            make_shifted_graphics_pdf(root / "new.pdf", offset=3)

            result = compare_pdfs(
                root / "old.pdf",
                root / "new.pdf",
                root / "result",
                old_name="old.pdf",
                new_name="new.pdf",
                dpi=96,
            )

            self.assertEqual(result["summary"]["added_words"], 0)
            self.assertEqual(result["summary"]["deleted_words"], 0)
            self.assertEqual(result["summary"]["visual_regions"], 0)

    def test_two_column_vertical_reflow_does_not_create_text_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_two_column_pdf(root / "old.pdf")
            make_two_column_pdf(root / "new.pdf", reverse_vertical_order=True)

            result = compare_pdfs(
                root / "old.pdf",
                root / "new.pdf",
                root / "result",
                old_name="old.pdf",
                new_name="new.pdf",
                dpi=96,
            )

            self.assertEqual(result["summary"]["deleted_words"], 0)
            self.assertEqual(result["summary"]["added_words"], 0)

    def test_moved_slide_text_only_marks_the_edited_word(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_slide_pdf(root / "old.pdf", updated=False)
            make_slide_pdf(root / "new.pdf", updated=True)

            result = compare_pdfs(
                root / "old.pdf",
                root / "new.pdf",
                root / "result",
                old_name="old.pdf",
                new_name="new.pdf",
                dpi=96,
            )

            self.assertEqual(result["summary"]["deleted_words"], 1)
            self.assertEqual(result["summary"]["added_words"], 1)
            self.assertEqual(result["rows"][0]["changes"]["deleted_snippets"], ["stable"])
            self.assertEqual(result["rows"][0]["changes"]["added_snippets"], ["verified"])

    def test_existing_pdf_highlight_is_detected_and_baked_into_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_path = root / "old.pdf"
            new_path = root / "new.pdf"
            make_pdf(old_path, [("The highlighted sentence is unchanged.", "square")])
            make_pdf(new_path, [("The highlighted sentence is unchanged.", "square")])

            document = fitz.open(new_path)
            page = document[0]
            target = page.search_for("highlighted sentence")[0]
            annotation = page.add_highlight_annot(target)
            annotation.set_colors(stroke=(1.0, 0.45, 0.0))
            annotation.set_opacity(0.4)
            annotation.update()
            annotated_path = root / "new-with-annotation.pdf"
            document.save(annotated_path)
            document.close()

            result = compare_pdfs(
                old_path,
                annotated_path,
                root / "result",
                old_name="old.pdf",
                new_name="new.pdf",
                dpi=96,
            )

            self.assertEqual(result["summary"]["changed_pages"], 1)
            self.assertEqual(result["summary"]["annotation_changes"], 1)
            self.assertEqual(result["summary"]["added_annotations"], 1)
            self.assertEqual(result["summary"]["deleted_annotations"], 0)
            self.assertEqual(result["rows"][0]["changes"]["added_annotations"], 1)

            baked = fitz.open(root / "result" / "new-highlighted.pdf")
            self.assertIsNone(baked[0].first_annot)
            original = fitz.open(annotated_path)
            original_pixels = original[0].get_pixmap(annots=False).samples
            baked_pixels = baked[0].get_pixmap(annots=False).samples
            self.assertNotEqual(original_pixels, baked_pixels)
            original.close()
            baked.close()

    def test_japanese_changes_are_detected_at_character_precision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, text in (
                ("old", "本研究では高速な手法を提案する。"),
                ("new", "本研究では高精度な手法を提案する。"),
            ):
                document = fitz.open()
                page = document.new_page(width=595, height=842)
                page.insert_text((60, 100), text, fontsize=15, fontname="japan")
                document.save(root / f"{name}.pdf")
                document.close()

            result = compare_pdfs(
                root / "old.pdf",
                root / "new.pdf",
                root / "result",
                old_name="old.pdf",
                new_name="new.pdf",
                dpi=96,
            )

            self.assertEqual(result["summary"]["deleted_words"], 1)
            self.assertEqual(result["summary"]["added_words"], 2)
            self.assertEqual(result["rows"][0]["changes"]["deleted_snippets"], ["速"])
            self.assertEqual(result["rows"][0]["changes"]["added_snippets"], ["精度"])

    def test_text_and_figure_changes_create_all_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_path = root / "old.pdf"
            new_path = root / "new.pdf"
            output = root / "result"
            make_pdf(old_path, [("The old method is accurate and fast.", "square")])
            make_pdf(new_path, [("The new method is accurate and robust.", "circle")])

            result = compare_pdfs(
                old_path,
                new_path,
                output,
                old_name="old.pdf",
                new_name="new.pdf",
                dpi=120,
            )

            self.assertGreater(result["summary"]["added_words"], 0)
            self.assertGreater(result["summary"]["deleted_words"], 0)
            self.assertGreater(result["summary"]["visual_regions"], 0)
            self.assertEqual(result["summary"]["changed_pages"], 1)
            for artifact in result["artifacts"].values():
                self.assertGreater((output / artifact["name"]).stat().st_size, 500)
            self.assertTrue((output / result["rows"][0]["old"]["preview"]).is_file())
            self.assertTrue((output / result["rows"][0]["new"]["preview"]).is_file())

            annotated = fitz.open(output / "new-highlighted.pdf")
            self.assertIsNone(annotated[0].first_annot)
            annotated.close()

            side_by_side = fitz.open(output / "side-by-side.pdf")
            comparison_text = side_by_side[0].get_text()
            self.assertIn("old method", comparison_text)
            self.assertIn("new method", comparison_text)
            side_by_side.close()

    def test_inserted_page_is_aligned_as_an_addition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_path = root / "old.pdf"
            new_path = root / "new.pdf"
            output = root / "result"
            make_pdf(
                old_path,
                [
                    ("Alpha section discusses experiments and measurements.", "square"),
                    ("Omega section reports conclusions and future work.", "circle"),
                ],
            )
            make_pdf(
                new_path,
                [
                    ("Alpha section discusses experiments and measurements.", "square"),
                    ("Inserted appendix with supplementary calibration details.", "square"),
                    ("Omega section reports conclusions and future work.", "circle"),
                ],
            )

            result = compare_pdfs(
                old_path,
                new_path,
                output,
                old_name="old.pdf",
                new_name="new.pdf",
                dpi=96,
            )

            self.assertEqual(result["summary"]["added_pages"], 1)
            self.assertEqual(result["summary"]["deleted_pages"], 0)
            self.assertEqual([row["kind"] for row in result["rows"]], ["unchanged", "added_page", "unchanged"])

    def test_completely_replaced_page_is_deleted_and_added_not_paired(self) -> None:
        # Regression test: before the align_pages intercept fix, a delete+insert
        # pair (2 * gap = -0.84) always scored worse than pairing two totally
        # unrelated pages (1.85*0 - 0.62 = -0.62), so a fully replaced page was
        # reported as a single low-quality "changed" page instead of a proper
        # deletion plus addition. Pages 1 and 3 stay identical; page 2 shares no
        # vocabulary between the old and new revisions.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_path = root / "old.pdf"
            new_path = root / "new.pdf"
            page1 = (
                "Zephyr quantum sensor calibration procedures verified across "
                "seventeen independent laboratory testbeds during springtime "
                "evaluation cycles nationwide today",
                "square",
            )
            page3 = (
                "Orbital telemetry archive summarizing spacecraft descent "
                "trajectories analyzed extensively by mission control engineers "
                "throughout the recovery operation phase",
                "square",
            )
            page2_old = (
                "Legacy municipal transportation infrastructure committees "
                "reviewed outdated bridge maintenance schedules following "
                "decades of neglected asphalt resurfacing budgets across rural "
                "counties statewide",
                "circle",
            )
            page2_new = (
                "Quarterly boutique retail apparel merchandising forecasts "
                "projected substantial revenue growth driven primarily by "
                "holiday season consumer footwear accessory purchases globally",
                "circle",
            )
            make_pdf(old_path, [page1, page2_old, page3])
            make_pdf(new_path, [page1, page2_new, page3])

            result = compare_pdfs(
                old_path,
                new_path,
                root / "result",
                old_name="old.pdf",
                new_name="new.pdf",
                dpi=96,
            )

            self.assertEqual(result["summary"]["added_pages"], 1)
            self.assertEqual(result["summary"]["deleted_pages"], 1)
            self.assertEqual(
                [row["kind"] for row in result["rows"]],
                ["unchanged", "added_page", "deleted_page", "unchanged"],
            )

    def test_is_cjk_covers_supplementary_plane_and_halfwidth_katakana(self) -> None:
        self.assertTrue(_is_cjk(chr(0x2000B)))
        self.assertTrue(_is_cjk("ｱ"))

    def test_dense_grid_of_isolated_blocks_does_not_recurse(self) -> None:
        # Regression test: cut() used to recurse once per block. A page where
        # every whitespace gap is tied for widest peels off exactly one block
        # per split (a grid/form layout), which used to exceed Python's
        # recursion limit and crash the whole comparison.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            grid_path = root / "grid.pdf"
            block_count = 1500
            vertical_gap = 20
            document = fitz.open()
            page = document.new_page(width=200, height=vertical_gap * block_count + 50)
            for index in range(block_count):
                page.insert_text((10, 20 + index * vertical_gap), "X", fontsize=8)
            document.save(grid_path)
            document.close()

            result = compare_pdfs(
                grid_path,
                grid_path,
                root / "result",
                old_name="grid.pdf",
                new_name="grid.pdf",
                dpi=96,
            )

            self.assertEqual(result["summary"]["changed_pages"], 0)

    def test_style_only_change_is_detected_and_marked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_path = root / "old.pdf"
            new_path = root / "new.pdf"
            sentence = "This sentence stays exactly the same in both revisions today."

            for path, fontname in ((old_path, "helv"), (new_path, "hebo")):
                document = fitz.open()
                page = document.new_page(width=595, height=842)
                page.insert_text((60, 100), sentence, fontsize=14, fontname=fontname)
                document.save(path)
                document.close()

            result = compare_pdfs(
                old_path,
                new_path,
                root / "result",
                old_name="old.pdf",
                new_name="new.pdf",
                dpi=96,
            )

            self.assertGreaterEqual(result["summary"]["style_changes"], 1)
            self.assertEqual(result["summary"]["added_words"], 0)
            self.assertEqual(result["summary"]["deleted_words"], 0)
            self.assertEqual(result["rows"][0]["kind"], "changed")

    def test_identical_documents_have_no_style_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_path = root / "old.pdf"
            new_path = root / "new.pdf"
            sentence = "This sentence stays exactly the same in both revisions today."

            for path in (old_path, new_path):
                document = fitz.open()
                page = document.new_page(width=595, height=842)
                page.insert_text((60, 100), sentence, fontsize=14, fontname="helv")
                document.save(path)
                document.close()

            result = compare_pdfs(
                old_path,
                new_path,
                root / "result",
                old_name="old.pdf",
                new_name="new.pdf",
                dpi=96,
            )

            self.assertEqual(result["summary"]["style_changes"], 0)

    def test_library_api_with_default_names(self) -> None:
        import kogo

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_pdf(root / "before.pdf", [("The library API sentence stays here.", "square")])
            make_pdf(root / "after.pdf", [("The library API sentence stays here.", "circle")])

            result = kogo.compare_pdfs(root / "before.pdf", root / "after.pdf", root / "out", dpi=96)

            self.assertEqual(result["files"]["old"]["name"], "before.pdf")
            self.assertEqual(result["files"]["new"]["name"], "after.pdf")
            self.assertGreater(result["summary"]["visual_regions"], 0)


if __name__ == "__main__":
    unittest.main()
