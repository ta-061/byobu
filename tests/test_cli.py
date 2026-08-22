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

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz

from kogo import __version__, cli


def make_tiny_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=200, height=200)
    page.insert_text((20, 20), "Hello world", fontsize=12)
    document.save(path)
    document.close()


class CliTests(unittest.TestCase):
    def test_version_exits_zero_and_prints_version(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn(__version__, stdout.getvalue())

    def test_diff_of_two_pdfs_writes_expected_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_pdf = root / "old.pdf"
            new_pdf = root / "new.pdf"
            make_tiny_pdf(old_pdf)
            make_tiny_pdf(new_pdf)
            out_dir = root / "out"

            exit_code = cli.main(
                ["diff", str(old_pdf), str(new_pdf), "-o", str(out_dir), "--dpi", "96"]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((out_dir / "old-highlighted.pdf").is_file())
            self.assertTrue((out_dir / "new-highlighted.pdf").is_file())
            self.assertTrue((out_dir / "side-by-side.pdf").is_file())
            self.assertTrue((out_dir / "result.json").is_file())

    def test_diff_of_missing_file_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            missing_pdf = root / "missing.pdf"
            existing_pdf = root / "existing.pdf"
            make_tiny_pdf(existing_pdf)

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = cli.main(
                    ["diff", str(missing_pdf), str(existing_pdf), "-o", str(root / "out")]
                )

            self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
