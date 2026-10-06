"""Original API threshold and review tests — now using isolated DB/storage.

All tests in this file used to run against the real plagiarism.db.
They now use the ``test_client`` and ``uploaded_session`` fixtures from
conftest.py so they run against an isolated in-memory SQLite database and a
temporary storage directory, making them safe to run from any environment.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upload_four(client, sample_files_bytes):
    files = [
        ("files", (name, data, "text/plain"))
        for name, data in sample_files_bytes.items()
    ]
    resp = client.post("/api/upload", files=files)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Tests (class-based to match original structure)
# ---------------------------------------------------------------------------

class TestThresholdAndReview:

    def test_average_similarity_uses_all_comparison_scores(
        self, test_client, sample_files_bytes
    ):
        upload = _upload_four(test_client, sample_files_bytes)
        ids = [item["id"] for item in upload["submissions"]]

        low = test_client.post(
            "/api/analyze",
            json={"session_id": upload["session_id"], "submission_ids": ids, "threshold": 0.6},
        )
        high = test_client.post(
            "/api/analyze",
            json={"session_id": upload["session_id"], "submission_ids": ids, "threshold": 0.75},
        )

        assert low.status_code == 200, low.text
        assert high.status_code == 200, high.text
        assert low.json()["average_similarity"] == high.json()["average_similarity"]
        assert low.json()["suspicious_pair_count"] != high.json()["suspicious_pair_count"]

    def test_compare_response_has_explanation_for_review(
        self, test_client, sample_files_bytes
    ):
        upload = _upload_four(test_client, sample_files_bytes)
        left = next(s for s in upload["submissions"] if s["filename"] == "alice.py")
        right = next(s for s in upload["submissions"] if s["filename"] == "bob.py")

        resp = test_client.post(
            "/api/compare",
            json={
                "session_id": upload["session_id"],
                "left_id": left["id"],
                "right_id": right["id"],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "explanation" in body
        assert "similarity" in body["explanation"].lower()

    def test_compare_response_uses_low_similarity_status(
        self, test_client, sample_files_bytes
    ):
        upload = _upload_four(test_client, sample_files_bytes)
        left = next(s for s in upload["submissions"] if s["filename"] == "alice.py")
        right = next(s for s in upload["submissions"] if s["filename"] == "carol.py")

        resp = test_client.post(
            "/api/compare",
            json={
                "session_id": upload["session_id"],
                "left_id": left["id"],
                "right_id": right["id"],
                "threshold": 0.99,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "LOW SIMILARITY"
        assert "threshold" in resp.json()["explanation"].lower()

    def test_path_traversal_name_is_rejected(self, test_client):
        resp = test_client.post(
            "/api/upload",
            files=[("files", ("../../evil.py", b"print('bad')", "text/x-python"))],
        )
        assert resp.status_code in (400, 422)
        assert "Only Python (.py) files are allowed." in resp.json()["detail"]

    def test_invalid_file_type_is_rejected(self, test_client):
        resp = test_client.post(
            "/api/upload",
            files=[("files", ("notes.txt", b"plain text", "text/plain"))],
        )
        assert resp.status_code in (400, 422)

    def test_empty_upload_is_rejected(self, test_client):
        resp = test_client.post("/api/upload", files=[])
        assert resp.status_code in (400, 422)

    def test_one_submission_is_rejected_for_analysis(
        self, test_client, sample_files_bytes
    ):
        """Must fail because of the one-submission condition, not a session issue."""
        single = {"dave.py": sample_files_bytes["dave.py"]}
        upload = test_client.post(
            "/api/upload",
            files=[("files", ("dave.py", sample_files_bytes["dave.py"], "text/x-python"))],
        )
        assert upload.status_code == 200, upload.text
        session_id = upload.json()["session_id"]
        single_id = [upload.json()["submissions"][0]["id"]]

        resp = test_client.post(
            "/api/analyze",
            json={
                "session_id": session_id,
                "submission_ids": single_id,
                "threshold": 0.6,
            },
        )
        assert resp.status_code == 400, resp.text

    def test_invalid_threshold_is_rejected(self, test_client, sample_files_bytes):
        """Threshold validation must reject 1.5; session and IDs are valid."""
        upload = _upload_four(test_client, sample_files_bytes)
        ids = [item["id"] for item in upload["submissions"]]

        resp = test_client.post(
            "/api/analyze",
            json={
                "session_id": upload["session_id"],
                "submission_ids": ids,
                "threshold": 1.5,
            },
        )
        assert resp.status_code == 422, resp.text  # Pydantic le=1.0

    def test_analysis_session_is_created(self, test_client, sample_files_bytes):
        upload = _upload_four(test_client, sample_files_bytes)
        assert "session_id" in upload
        assert upload["session_id"] > 0

    def test_one_submission_returns_clear_error(self, test_client, sample_files_bytes):
        upload = test_client.post(
            "/api/upload",
            files=[("files", ("dave.py", sample_files_bytes["dave.py"], "text/x-python"))],
        )
        assert upload.status_code == 200, upload.text
        session_id = upload.json()["session_id"]
        single_id = [upload.json()["submissions"][0]["id"]]

        resp = test_client.post(
            "/api/analyze",
            json={"session_id": session_id, "submission_ids": single_id, "threshold": 0.6},
        )
        assert resp.status_code == 400, resp.text
        assert "At least two submissions are required" in resp.json()["detail"]

    def test_two_submissions_produce_one_unique_comparison(
        self, test_client, sample_files_bytes
    ):
        subset = {k: sample_files_bytes[k] for k in ["alice.py", "bob.py"]}
        upload = test_client.post(
            "/api/upload",
            files=[("files", (n, d, "text/x-python")) for n, d in subset.items()],
        )
        assert upload.status_code == 200, upload.text
        data = upload.json()

        resp = test_client.post(
            "/api/analyze",
            json={
                "session_id": data["session_id"],
                "submission_ids": [s["id"] for s in data["submissions"]],
                "threshold": 0.6,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_submissions"] == 2
        assert body["total_comparisons"] == 1
        assert len(body["results"]) == 1

    def test_four_submissions_produce_six_unique_comparisons(
        self, test_client, sample_files_bytes
    ):
        upload = _upload_four(test_client, sample_files_bytes)
        ids = [s["id"] for s in upload["submissions"]]

        resp = test_client.post(
            "/api/analyze",
            json={
                "session_id": upload["session_id"],
                "submission_ids": ids,
                "threshold": 0.6,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_submissions"] == 4
        assert body["total_comparisons"] == 6
        assert len(body["results"]) == 6

    def test_duplicate_filename_within_same_session_is_rejected(self, test_client):
        resp = test_client.post(
            "/api/upload",
            files=[
                ("files", ("alice.py", b"print('one')", "text/x-python")),
                ("files", ("alice.py", b"print('two')", "text/x-python")),
            ],
        )
        assert resp.status_code == 400, resp.text
        assert "Duplicate filename found" in resp.json()["detail"]

    def test_old_session_does_not_contaminate_new_session(
        self, test_client, sample_files_bytes
    ):
        old = _upload_four(test_client, sample_files_bytes)
        old_ids = [s["id"] for s in old["submissions"]]
        old_resp = test_client.post(
            "/api/analyze",
            json={"session_id": old["session_id"], "submission_ids": old_ids, "threshold": 0.6},
        )
        assert old_resp.status_code == 200, old_resp.text

        new_files = [
            ("files", (n, sample_files_bytes[n], "text/x-python"))
            for n in ["alice.py", "bob.py"]
        ]
        new_upload = test_client.post("/api/upload", files=new_files)
        assert new_upload.status_code == 200, new_upload.text
        new_data = new_upload.json()

        new_resp = test_client.post(
            "/api/analyze",
            json={
                "session_id": new_data["session_id"],
                "submission_ids": [s["id"] for s in new_data["submissions"]],
                "threshold": 0.6,
            },
        )
        assert new_resp.status_code == 200, new_resp.text
        body = new_resp.json()
        assert body["total_submissions"] == 2
        assert body["total_comparisons"] == 1
        assert body["session_id"] != old["session_id"]

    def test_no_self_comparison_or_cross_session_pairing(
        self, test_client, sample_files_bytes
    ):
        upload = _upload_four(test_client, sample_files_bytes)
        ids = [s["id"] for s in upload["submissions"]]
        resp = test_client.post(
            "/api/analyze",
            json={"session_id": upload["session_id"], "submission_ids": ids, "threshold": 0.6},
        )
        assert resp.status_code == 200, resp.text
        pairs = resp.json()["results"]
        assert all(p["file_a"] != p["file_b"] for p in pairs)
        assert len(pairs) == 6
