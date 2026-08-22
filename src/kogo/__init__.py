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

"""kogo: layout-aware PDF diff for revisions.

Library usage:

    import kogo

    result = kogo.compare_pdfs("old.pdf", "new.pdf", "out/")
    # -> old-highlighted.pdf, new-highlighted.pdf, side-by-side.pdf,
    #    result.json (and previews/) under out/
"""

from kogo.engine import ComparisonError, compare_pdfs

__version__ = "0.1.2"

__all__ = ["ComparisonError", "compare_pdfs", "__version__"]
