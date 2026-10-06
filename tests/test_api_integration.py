"""API integration tests with isolated database and storage.

All tests use the ``test_client`` fixture from conftest.py — they never
touch the real plagiarism.db or real storage/ directory.

Coverage:
* Upload: success, empty, duplicate name, wrong extension, oversized
* Analyze: success, 1 submission, missing session, threshold validation,
           re-analysis dedup, pair count mathematics
* Compare GET: retrieves persisted results
* Compare POST: detailed pair comparison, session isolation
* Session isolation: cross-session access denied
* Multiline Python: never causes 500
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upload(client, files_bytes: dict[str, bytes]):
    files = [("files", (name, data, "text/x-python")) for name, data in files_bytes.items()]
    return client.post("/api/upload", files=files)


def _analyze(client, session_id: int, ids: list[int], threshold: float = 0.6):
    return client.post(
        "/api/analyze",
        json={"session_id": session_id, "submission_ids": ids, "threshold": threshold},
    )


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------

class TestUpload:
    def test_upload_four_files_succeeds(self, test_client, sample_files_bytes):
        resp = _upload(test_client, sample_files_bytes)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_submissions"] == 4
        assert len(data["submissions"]) == 4

    def test_upload_creates_session(self, test_client, sample_files_bytes):
        data = _upload(test_client, sample_files_bytes).json()
        assert data["session_id"] > 0

    def test_empty_upload_rejected(self, test_client):
        resp = test_client.post("/api/upload", files=[])
        assert resp.status_code in (400, 422)

    def test_non_python_file_rejected(self, test_client):
        resp = test_client.post(
            "/api/upload",
            files=[("files", ("notes.txt", b"hello", "text/plain"))],
        )
        assert resp.status_code in (400, 422)

    def test_duplicate_filename_rejected(self, test_client):
        resp = test_client.post(
            "/api/upload",
            files=[
                ("files", ("alice.py", b"x = 1", "text/x-python")),
                ("files", ("alice.py", b"x = 2", "text/x-python")),
            ],
        )
        assert resp.status_code == 400
        assert "Duplicate" in resp.json()["detail"]

    def test_path_traversal_rejected(self, test_client):
        resp = test_client.post(
            "/api/upload",
            files=[("files", ("../../evil.py", b"bad = 1", "text/x-python"))],
        )
        assert resp.status_code in (400, 422)

    def test_oversized_file_rejected(self, test_client):
        big = b"x = 1\n" * (2 * 1024 * 1024)  # ~12 MB
        resp = test_client.post(
            "/api/upload",
            files=[("files", ("big.py", big, "text/x-python"))],
        )
        assert resp.status_code == 413

    def test_upload_returns_content_hash(self, test_client):
        resp = test_client.post(
            "/api/upload",
            files=[("files", ("f.py", b"x = 1\n", "text/x-python"))],
        )
        assert resp.status_code == 200
        sub = resp.json()["submissions"][0]
        assert len(sub["content_hash"]) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# Analyze tests
# ---------------------------------------------------------------------------

class TestAnalyze:
    def test_four_files_six_comparisons(self, test_client, uploaded_session):
        ids = [s["id"] for s in uploaded_session["submissions"]]
        resp = _analyze(test_client, uploaded_session["session_id"], ids)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_comparisons"] == 6
        assert len(body["results"]) == 6

    def test_two_files_one_comparison(self, test_client, sample_files_bytes):
        subset = {k: sample_files_bytes[k] for k in ["alice.py", "bob.py"]}
        data = _upload(test_client, subset).json()
        ids = [s["id"] for s in data["submissions"]]
        resp = _analyze(test_client, data["session_id"], ids)
        assert resp.status_code == 200
        assert resp.json()["total_comparisons"] == 1

    def test_one_submission_rejected(self, test_client, sample_files_bytes):
        subset = {"dave.py": sample_files_bytes["dave.py"]}
        data = _upload(test_client, subset).json()
        ids = [s["id"] for s in data["submissions"]]
        resp = _analyze(test_client, data["session_id"], ids)
        assert resp.status_code == 400
        assert "two submissions" in resp.json()["detail"].lower()

    def test_missing_session_returns_404(self, test_client):
        resp = _analyze(test_client, session_id=99999, ids=[1, 2])
        assert resp.status_code == 404

    def test_invalid_threshold_above_one(self, test_client, uploaded_session):
        ids = [s["id"] for s in uploaded_session["submissions"]]
        resp = _analyze(test_client, uploaded_session["session_id"], ids, threshold=1.5)
        assert resp.status_code == 422  # Pydantic validation

    def test_invalid_threshold_below_zero(self, test_client, uploaded_session):
        ids = [s["id"] for s in uploaded_session["submissions"]]
        resp = _analyze(test_client, uploaded_session["session_id"], ids, threshold=-0.1)
        assert resp.status_code == 422

    def test_no_self_comparisons(self, test_client, uploaded_session):
        ids = [s["id"] for s in uploaded_session["submissions"]]
        resp = _analyze(test_client, uploaded_session["session_id"], ids)
        pairs = resp.json()["results"]
        assert all(p["file_a"] != p["file_b"] for p in pairs)

    def test_reanalysis_does_not_duplicate_results(self, test_client, uploaded_session):
        ids = [s["id"] for s in uploaded_session["submissions"]]
        sid = uploaded_session["session_id"]
        _analyze(test_client, sid, ids)
        _analyze(test_client, sid, ids)

        # GET persisted results — should be exactly 6 rows, not 12
        results_resp = test_client.get(f"/api/compare?session_id={sid}")
        assert results_resp.status_code == 200
        assert results_resp.json()["total_comparisons"] == 6

    def test_result_contains_all_metrics(self, test_client, uploaded_session):
        ids = [s["id"] for s in uploaded_session["submissions"]]
        resp = _analyze(test_client, uploaded_session["session_id"], ids)
        pair = resp.json()["results"][0]
        assert "score" in pair
        assert "jaccard_similarity" in pair
        assert "containment_similarity" in pair
        assert "ast_similarity" in pair
        assert "suspicious" in pair

    def test_average_similarity_independent_of_threshold(self, test_client, uploaded_session):
        ids = [s["id"] for s in uploaded_session["submissions"]]
        sid = uploaded_session["session_id"]
        low = _analyze(test_client, sid, ids, threshold=0.3).json()
        high = _analyze(test_client, sid, ids, threshold=0.9).json()
        assert low["average_similarity"] == high["average_similarity"]

    def test_cross_session_ids_are_filtered(self, test_client, sample_files_bytes):
        """IDs from session A must not appear in session B's analysis."""
        data_a = _upload(test_client, {"alice.py": sample_files_bytes["alice.py"],
                                        "bob.py": sample_files_bytes["bob.py"]}).json()
        data_b = _upload(test_client, {"carol.py": sample_files_bytes["carol.py"],
                                        "dave.py": sample_files_bytes["dave.py"]}).json()

        # Try to analyze session B but inject session A IDs
        foreign_ids = [s["id"] for s in data_a["submissions"]]
        resp = _analyze(test_client, data_b["session_id"], foreign_ids)
        # Either 404 (no valid IDs found) or 400 (too few)
        assert resp.status_code in (400, 404)


# ---------------------------------------------------------------------------
# Compare POST tests
# ---------------------------------------------------------------------------

class TestComparePairPost:
    def test_compare_returns_explanation(self, test_client, uploaded_session):
        subs = uploaded_session["submissions"]
        alice = next(s for s in subs if s["filename"] == "alice.py")
        bob = next(s for s in subs if s["filename"] == "bob.py")
        resp = test_client.post(
            "/api/compare",
            json={
                "session_id": uploaded_session["session_id"],
                "left_id": alice["id"],
                "right_id": bob["id"],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "explanation" in body
        assert "similarity" in body["explanation"].lower()

    def test_compare_returns_all_metrics(self, test_client, uploaded_session):
        subs = uploaded_session["submissions"]
        resp = test_client.post(
            "/api/compare",
            json={
                "session_id": uploaded_session["session_id"],
                "left_id": subs[0]["id"],
                "right_id": subs[1]["id"],
            },
        )
        body = resp.json()
        assert "jaccard_similarity" in body
        assert "containment_similarity" in body
        assert "ast_similarity" in body
        assert "left_lines" in body
        assert "right_lines" in body

    def test_compare_self_rejected(self, test_client, uploaded_session):
        sub_id = uploaded_session["submissions"][0]["id"]
        resp = test_client.post(
            "/api/compare",
            json={
                "session_id": uploaded_session["session_id"],
                "left_id": sub_id,
                "right_id": sub_id,
            },
        )
        assert resp.status_code == 422

    def test_cross_session_compare_rejected(self, test_client, sample_files_bytes):
        data_a = _upload(test_client, {"alice.py": sample_files_bytes["alice.py"]}).json()
        data_b = _upload(test_client, {"bob.py": sample_files_bytes["bob.py"]}).json()
        resp = test_client.post(
            "/api/compare",
            json={
                "session_id": data_a["session_id"],
                "left_id": data_a["submissions"][0]["id"],
                "right_id": data_b["submissions"][0]["id"],
            },
        )
        assert resp.status_code == 404

    def test_low_threshold_shows_low_similarity_status(self, test_client, sample_files_bytes):
        subset = {k: sample_files_bytes[k] for k in ["alice.py", "carol.py"]}
        data = _upload(test_client, subset).json()
        alice = next(s for s in data["submissions"] if s["filename"] == "alice.py")
        carol = next(s for s in data["submissions"] if s["filename"] == "carol.py")
        resp = test_client.post(
            "/api/compare",
            json={
                "session_id": data["session_id"],
                "left_id": alice["id"],
                "right_id": carol["id"],
                "threshold": 0.99,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "LOW SIMILARITY"


# ---------------------------------------------------------------------------
# Session isolation tests
# ---------------------------------------------------------------------------

class TestSessionIsolation:
    def test_list_submissions_requires_session_id(self, test_client):
        resp = test_client.get("/api/submissions")
        # Without session_id param this should fail (422 from Pydantic/FastAPI)
        assert resp.status_code == 422

    def test_list_submissions_scoped_to_session(self, test_client, sample_files_bytes):
        data_a = _upload(test_client, {"alice.py": sample_files_bytes["alice.py"]}).json()
        data_b = _upload(test_client, {"bob.py": sample_files_bytes["bob.py"]}).json()

        resp_a = test_client.get(f"/api/submissions?session_id={data_a['session_id']}")
        resp_b = test_client.get(f"/api/submissions?session_id={data_b['session_id']}")

        names_a = {s["filename"] for s in resp_a.json()["submissions"]}
        names_b = {s["filename"] for s in resp_b.json()["submissions"]}
        assert names_a == {"alice.py"}
        assert names_b == {"bob.py"}
        assert names_a.isdisjoint(names_b)

    def test_compare_get_scoped_to_session(self, test_client, sample_files_bytes):
        data_a = _upload(test_client, {"alice.py": sample_files_bytes["alice.py"],
                                        "bob.py": sample_files_bytes["bob.py"]}).json()
        data_b = _upload(test_client, {"carol.py": sample_files_bytes["carol.py"],
                                        "dave.py": sample_files_bytes["dave.py"]}).json()

        ids_a = [s["id"] for s in data_a["submissions"]]
        ids_b = [s["id"] for s in data_b["submissions"]]
        _analyze(test_client, data_a["session_id"], ids_a)
        _analyze(test_client, data_b["session_id"], ids_b)

        results_a = test_client.get(f"/api/compare?session_id={data_a['session_id']}").json()
        results_b = test_client.get(f"/api/compare?session_id={data_b['session_id']}").json()

        # Each session should only see its own pair
        assert results_a["total_comparisons"] == 1
        assert results_b["total_comparisons"] == 1

    def test_invalid_session_returns_404(self, test_client):
        resp = test_client.get("/api/compare?session_id=99999")
        assert resp.status_code == 404

    def test_submissions_endpoint_404_for_unknown_session(self, test_client):
        resp = test_client.get("/api/submissions?session_id=99999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Multiline Python regression tests
# ---------------------------------------------------------------------------

class TestMultilinePython:
    """Valid multiline Python must never cause a 500 error."""

    def _upload_source(self, client, name: str, source: str):
        return client.post(
            "/api/upload",
            files=[("files", (name, source.encode(), "text/x-python"))],
        )

    def _analyze_two(self, client, src_a: str, src_b: str):
        up_a = self._upload_source(client, "a.py", src_a)
        up_b = self._upload_source(client, "b.py", src_b)
        # Upload both in one request
        resp = client.post(
            "/api/upload",
            files=[
                ("files", ("a.py", src_a.encode(), "text/x-python")),
                ("files", ("b.py", src_b.encode(), "text/x-python")),
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        ids = [s["id"] for s in data["submissions"]]
        return client.post(
            "/api/analyze",
            json={"session_id": data["session_id"], "submission_ids": ids},
        )

    def test_multiline_function_call(self, test_client):
        src = "def f():\n    return foo(\n        1,\n        2\n    )"
        resp = self._analyze_two(test_client, src, "def g():\n    return bar(3)")
        assert resp.status_code == 200

    def test_multiline_list(self, test_client):
        src = "x = [\n    1,\n    2,\n    3\n]"
        resp = self._analyze_two(test_client, src, "y = [4, 5, 6]")
        assert resp.status_code == 200

    def test_multiline_dict(self, test_client):
        src = "d = {\n    'key': 'value',\n    'other': 42\n}"
        resp = self._analyze_two(test_client, src, "e = {'a': 1}")
        assert resp.status_code == 200

    def test_multiline_function_def(self, test_client):
        src = "def complicated(\n    arg1,\n    arg2,\n    arg3\n):\n    return arg1 + arg2 + arg3"
        resp = self._analyze_two(test_client, src, "def simple(x):\n    return x")
        assert resp.status_code == 200

    def test_multiline_expression(self, test_client):
        src = "result = (\n    value_one\n    + value_two\n    + value_three\n)"
        resp = self._analyze_two(test_client, src, "result = a + b")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Invalid Python tests
# ---------------------------------------------------------------------------

class TestInvalidPython:
    def test_invalid_python_does_not_crash_valid_pair(self, test_client, sample_files_bytes):
        """One invalid file must not prevent valid files from being analyzed."""
        resp = test_client.post(
            "/api/upload",
            files=[
                ("files", ("good_a.py", sample_files_bytes["alice.py"], "text/x-python")),
                ("files", ("bad.py", b"def f(:\n    bad syntax", "text/x-python")),
                ("files", ("good_b.py", sample_files_bytes["bob.py"], "text/x-python")),
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        ids = [s["id"] for s in data["submissions"]]
        analyze_resp = test_client.post(
            "/api/analyze",
            json={"session_id": data["session_id"], "submission_ids": ids},
        )
        # Must not 500
        assert analyze_resp.status_code == 200

    def test_empty_fingerprints_not_flagged_as_plagiarism(self, test_client):
        """Two tiny files that can't produce fingerprints must not show similarity 1.0."""
        resp = test_client.post(
            "/api/upload",
            files=[
                ("files", ("a.py", b"x = 1", "text/x-python")),
                ("files", ("b.py", b"y = 2", "text/x-python")),
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        ids = [s["id"] for s in data["submissions"]]
        analyze_resp = test_client.post(
            "/api/analyze",
            json={"session_id": data["session_id"], "submission_ids": ids},
        )
        assert analyze_resp.status_code == 200
        results = analyze_resp.json()["results"]
        for pair in results:
            # score must not be exactly 1.0 unless it's a genuine exact duplicate
            if not pair.get("is_exact_duplicate"):
                # If fingerprints are empty → jaccard is 0.0, not 1.0
                assert pair["jaccard_similarity"] != 1.0 or pair["score"] != 1.0 or pair["is_exact_duplicate"]


# ---------------------------------------------------------------------------
# Exact duplicate detection
# ---------------------------------------------------------------------------

class TestExactDuplicateDetection:
    def test_identical_content_flagged_as_exact_duplicate(self, test_client, sample_files_bytes):
        content = sample_files_bytes["alice.py"]
        resp = test_client.post(
            "/api/upload",
            files=[
                ("files", ("copy_a.py", content, "text/x-python")),
                ("files", ("copy_b.py", content, "text/x-python")),
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        ids = [s["id"] for s in data["submissions"]]
        analyze_resp = test_client.post(
            "/api/analyze",
            json={"session_id": data["session_id"], "submission_ids": ids},
        )
        assert analyze_resp.status_code == 200
        pair = analyze_resp.json()["results"][0]
        assert pair["is_exact_duplicate"] is True
        assert pair["suspicious"] is True

    def test_different_content_not_flagged_as_exact_duplicate(
        self, test_client, sample_files_bytes
    ):
        resp = test_client.post(
            "/api/upload",
            files=[
                ("files", ("alice.py", sample_files_bytes["alice.py"], "text/x-python")),
                ("files", ("bob.py", sample_files_bytes["bob.py"], "text/x-python")),
            ],
        )
        data = resp.json()
        ids = [s["id"] for s in data["submissions"]]
        analyze_resp = test_client.post(
            "/api/analyze",
            json={"session_id": data["session_id"], "submission_ids": ids},
        )
        pair = analyze_resp.json()["results"][0]
        assert pair["is_exact_duplicate"] is False
