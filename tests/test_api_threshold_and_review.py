import os
import unittest

from fastapi.testclient import TestClient

from backend.app import app


class ThresholdAndReviewTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _upload_sample_files(self):
        files = []
        for name in ["alice.py", "bob.py", "carol.py", "dave.py"]:
            path = os.path.join("submissions", name)
            with open(path, "rb") as handle:
                files.append(("files", (name, handle.read(), "text/plain")))

        response = self.client.post("/api/upload", files=files)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_average_similarity_uses_all_comparison_scores(self):
        upload = self._upload_sample_files()
        ids = [item["id"] for item in upload["submissions"]]

        low = self.client.post(
            "/api/analyze",
            json={"session_id": upload["session_id"], "submission_ids": ids, "threshold": 0.6},
        )
        high = self.client.post(
            "/api/analyze",
            json={"session_id": upload["session_id"], "submission_ids": ids, "threshold": 0.75},
        )

        self.assertEqual(low.status_code, 200, low.text)
        self.assertEqual(high.status_code, 200, high.text)
        self.assertEqual(low.json()["average_similarity"], high.json()["average_similarity"])
        self.assertNotEqual(low.json()["suspicious_pair_count"], high.json()["suspicious_pair_count"])

    def test_compare_response_has_explanation_for_review(self):
        upload = self._upload_sample_files()
        left = next(item for item in upload["submissions"] if item["filename"] == "alice.py")
        right = next(item for item in upload["submissions"] if item["filename"] == "bob.py")

        response = self.client.post(
            "/api/compare",
            json={"session_id": upload["session_id"], "left_id": left["id"], "right_id": right["id"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("explanation", body)
        self.assertIn("similarity", body["explanation"].lower())

    def test_compare_response_uses_low_similarity_status(self):
        upload = self._upload_sample_files()
        left = next(item for item in upload["submissions"] if item["filename"] == "alice.py")
        right = next(item for item in upload["submissions"] if item["filename"] == "carol.py")

        response = self.client.post(
            "/api/compare",
            json={
                "session_id": upload["session_id"],
                "left_id": left["id"],
                "right_id": right["id"],
                "threshold": 0.99,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "LOW SIMILARITY")
        self.assertIn("threshold", response.json()["explanation"].lower())

    def test_path_traversal_name_is_rejected(self):
        response = self.client.post(
            "/api/upload",
            files=[("files", ("../../evil.py", b"print('bad')", "text/x-python"))],
        )
        self.assertIn(response.status_code, {400, 422})
        self.assertIn("Only Python (.py) files are allowed.", response.json()["detail"])

    def test_invalid_file_type_is_rejected(self):
        response = self.client.post(
            "/api/upload",
            files=[("files", ("notes.txt", b"plain text", "text/plain"))],
        )
        self.assertIn(response.status_code, {400, 422})

    def test_empty_upload_is_rejected(self):
        response = self.client.post("/api/upload", files=[])
        self.assertIn(response.status_code, {400, 422})

    def test_one_submission_is_rejected_for_analysis(self):
        upload = self._upload_sample_files()
        single_id = [upload["submissions"][0]["id"]]

        response = self.client.post("/api/analyze", json={"submission_ids": single_id, "threshold": 0.6})
        self.assertEqual(response.status_code, 400, response.text)

    def test_invalid_threshold_is_rejected(self):
        upload = self._upload_sample_files()
        ids = [item["id"] for item in upload["submissions"]]

        response = self.client.post("/api/analyze", json={"submission_ids": ids, "threshold": 1.5})
        self.assertEqual(response.status_code, 400, response.text)

    def test_analysis_session_is_created(self):
        upload = self._upload_sample_files()
        self.assertIn("session_id", upload)
        self.assertGreater(upload["session_id"], 0)

    def test_one_submission_returns_clear_error(self):
        with open("submissions/dave.py", "rb") as handle:
            file = [("files", ("dave.py", handle.read(), "text/x-python"))]

        upload = self.client.post("/api/upload", files=file)
        self.assertEqual(upload.status_code, 200, upload.text)
        session_id = upload.json()["session_id"]

        response = self.client.post(
            "/api/analyze",
            json={"session_id": session_id, "submission_ids": [upload.json()["submissions"][0]["id"]], "threshold": 0.6},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("At least two submissions are required for comparison.", response.json()["detail"])

    def test_two_submissions_produce_one_unique_comparison(self):
        files = []
        for name in ["alice.py", "bob.py"]:
            with open(os.path.join("submissions", name), "rb") as handle:
                files.append(("files", (name, handle.read(), "text/x-python")))

        upload = self.client.post("/api/upload", files=files)
        self.assertEqual(upload.status_code, 200, upload.text)
        data = upload.json()

        response = self.client.post(
            "/api/analyze",
            json={"session_id": data["session_id"], "submission_ids": [item["id"] for item in data["submissions"]], "threshold": 0.6},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total_submissions"], 2)
        self.assertEqual(body["total_comparisons"], 1)
        self.assertEqual(len(body["results"]), 1)

    def test_four_submissions_produce_six_unique_comparisons(self):
        upload = self._upload_sample_files()
        ids = [item["id"] for item in upload["submissions"]]

        response = self.client.post(
            "/api/analyze",
            json={"session_id": upload["session_id"], "submission_ids": ids, "threshold": 0.6},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total_submissions"], 4)
        self.assertEqual(body["total_comparisons"], 6)
        self.assertEqual(len(body["results"]), 6)

    def test_duplicate_filename_within_same_session_is_rejected(self):
        files = [
            ("files", ("alice.py", b"print('one')", "text/x-python")),
            ("files", ("alice.py", b"print('two')", "text/x-python")),
        ]

        response = self.client.post("/api/upload", files=files)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Duplicate filename found", response.json()["detail"])

    def test_old_session_does_not_contaminate_new_session(self):
        old_upload = self._upload_sample_files()
        old_ids = [item["id"] for item in old_upload["submissions"]]
        old_response = self.client.post(
            "/api/analyze",
            json={"session_id": old_upload["session_id"], "submission_ids": old_ids, "threshold": 0.6},
        )
        self.assertEqual(old_response.status_code, 200, old_response.text)

        new_files = []
        for name in ["alice.py", "bob.py"]:
            with open(os.path.join("submissions", name), "rb") as handle:
                new_files.append(("files", (name, handle.read(), "text/x-python")))

        new_upload = self.client.post("/api/upload", files=new_files)
        self.assertEqual(new_upload.status_code, 200, new_upload.text)
        new_session_id = new_upload.json()["session_id"]

        response = self.client.post(
            "/api/analyze",
            json={"session_id": new_session_id, "submission_ids": [item["id"] for item in new_upload.json()["submissions"]], "threshold": 0.6},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total_submissions"], 2)
        self.assertEqual(body["total_comparisons"], 1)
        self.assertNotEqual(body["session_id"], old_upload["session_id"])

    def test_no_self_comparison_or_cross_session_pairing(self):
        four_upload = self._upload_sample_files()
        ids = [item["id"] for item in four_upload["submissions"]]
        response = self.client.post(
            "/api/analyze",
            json={"session_id": four_upload["session_id"], "submission_ids": ids, "threshold": 0.6},
        )
        self.assertEqual(response.status_code, 200, response.text)
        comparisons = response.json()["results"]
        self.assertTrue(all(pair["file_a"] != pair["file_b"] for pair in comparisons))
        self.assertEqual(len(comparisons), 6)


if __name__ == "__main__":
    unittest.main()
