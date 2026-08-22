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

from .alignment import align_pages
from .compare import ComparisonError, compare_pdfs
from .words import _is_cjk

__all__ = ["compare_pdfs", "ComparisonError"]
