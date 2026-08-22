# byobu - layout-aware PDF diff for revisions.
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

import os
import shutil
import tempfile
import unittest

_JOBS_DIR = tempfile.mkdtemp(prefix="byobu-test-jobs-")
os.environ["JOBS_DIR"] = _JOBS_DIR

from fastapi.testclient import TestClient  # noqa: E402

from byobu.server.app import app  # noqa: E402


def tearDownModule() -> None:
    shutil.rmtree(_JOBS_DIR, ignore_errors=True)


class AppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_config(self) -> None:
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("max_upload_mb", payload)
        self.assertIn("max_pages", payload)

    def test_index(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_artifact_path_traversal_is_rejected(self) -> None:
        job_id = "0" * 32
        response = self.client.get(f"/api/jobs/{job_id}/artifacts/../../etc/passwd")
        self.assertEqual(response.status_code, 404)

    def test_unknown_job_is_not_found(self) -> None:
        response = self.client.get("/api/jobs/nonexistent")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
