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

import json
import os
import shutil
import tempfile
import unittest

_JOBS_DIR = tempfile.mkdtemp(prefix="kogo-test-jobs-")
os.environ["JOBS_DIR"] = _JOBS_DIR

from fastapi.testclient import TestClient  # noqa: E402

from kogo.server.app import JOBS_DIR, app  # noqa: E402


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

    def test_artifact_not_in_allowlist_is_rejected(self) -> None:
        job_id = "1" * 32
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "result.json").write_text(
            json.dumps({"artifacts": {}, "rows": []}), encoding="utf-8"
        )
        (job_dir / "old-input.pdf").write_bytes(b"%PDF-1.4 not a real artifact")

        response = self.client.get(f"/api/jobs/{job_id}/artifacts/old-input.pdf")
        self.assertEqual(response.status_code, 404)

    def test_unknown_job_is_not_found(self) -> None:
        response = self.client.get("/api/jobs/nonexistent")
        self.assertEqual(response.status_code, 404)

    def test_security_headers_present_on_index(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(response.headers.get("referrer-policy"), "no-referrer")
        self.assertIn("default-src 'self'", response.headers.get("content-security-policy", ""))


if __name__ == "__main__":
    unittest.main()
