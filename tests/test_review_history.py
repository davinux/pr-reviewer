"""Tests for the review-history sidebars.

Covers the storage reads that back the lists (a request's full review history,
and the newest reviews across requests with their request identity), the
status/verdict labelling, the ``/api/reviews`` endpoint and the two rendered
sidebars (the request page and the dashboard). See
``specs/010-review-history-sidebar``.

Run with: ``python3 -m unittest discover -s tests``
"""

import atexit
import os
import shutil
import tempfile
import unittest

# storage reads DATA_DIR at import time, so point it at a throwaway folder
# before importing the application modules.
_TMP_DIR = tempfile.mkdtemp(prefix="pr-reviewer-history-tests-")
os.environ["DATA_DIR"] = _TMP_DIR
atexit.register(shutil.rmtree, _TMP_DIR, ignore_errors=True)

import app as app_module  # noqa: E402
import storage  # noqa: E402

SLUG = "github.com/acme/api"
OTHER_SLUG = "gitlab.com/group/project"


def _pr(pr_id, number, slug=SLUG, repo="acme/api", host="github.com",
        title="Fix the thing", state="open"):
    return {
        "id": pr_id,
        "repo": repo,
        "slug": slug,
        "provider": "gitlab" if host.startswith("gitlab") else "github",
        "host": host,
        "number": number,
        "title": title,
        "user": "octocat",
        "body": "",
        "state": state,
        "url": f"https://{host}/{repo}/pull/{number}",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "draft": False,
        "labels": [],
        "base_ref": "main",
        "head_ref": f"feature-{number}",
    }


class ReviewHistoryTest(unittest.TestCase):
    def setUp(self):
        storage.init_db()
        with storage.get_conn() as conn:
            conn.execute("DELETE FROM reviews")
            conn.execute("DELETE FROM dismissed_reviews")
            conn.execute("DELETE FROM notifications")
            conn.execute("DELETE FROM pull_requests")
            conn.execute("DELETE FROM repos")
        self.client = app_module.app.test_client()

    # -- helpers ----------------------------------------------------------- #
    def _store(self, pr_id, number, **kwargs):
        storage.save_pr(_pr(pr_id, number, **kwargs))

    def _review(self, pr_id, number, status="done", verdict="passed",
                agent="opencode", model=None):
        review_id = storage.create_review(pr_id, "acme/api", number, agent, model)
        storage.update_review(review_id, status=status, verdict=verdict)
        return review_id

    # -- storage: a request's full history --------------------------------- #
    def test_list_reviews_returns_the_full_history_newest_first(self):
        self._store(1, 1)
        ids = [self._review(1, 1) for _ in range(25)]
        reviews = storage.list_reviews(1)
        self.assertEqual(len(reviews), 25)
        self.assertEqual([r["id"] for r in reviews], sorted(ids, reverse=True))

    def test_list_reviews_honours_an_explicit_limit(self):
        self._store(1, 1)
        self._review(1, 1)
        self._review(1, 1)
        self.assertEqual(len(storage.list_reviews(1, limit=1)), 1)

    def test_list_reviews_is_scoped_to_the_request(self):
        self._store(1, 1)
        self._store(2, 2)
        self._review(1, 1)
        self._review(2, 2)
        self._review(2, 2)
        self.assertEqual(len(storage.list_reviews(1)), 1)
        self.assertEqual(len(storage.list_reviews(2)), 2)

    # -- storage: recent reviews across requests --------------------------- #
    def test_list_recent_reviews_carries_request_identity(self):
        self._store(1, 7, title="First")
        self._store(2, 8, slug=OTHER_SLUG, repo="group/project", host="gitlab.com",
                    title="Second")
        self._review(1, 7)
        self._review(2, 8)

        recent = storage.list_recent_reviews()
        self.assertEqual([r["number"] for r in recent], [8, 7])  # newest first
        newest = recent[0]
        self.assertEqual(newest["title"], "Second")
        self.assertEqual(newest["full_name"], "group/project")
        self.assertEqual(newest["slug"], OTHER_SLUG)
        self.assertEqual(newest["pr_id"], 2)

    def test_list_recent_reviews_respects_the_limit(self):
        self._store(1, 1)
        for _ in range(5):
            self._review(1, 1)
        self.assertEqual(len(storage.list_recent_reviews(limit=3)), 3)

    # -- labelling --------------------------------------------------------- #
    def test_review_history_payload_labels_status_and_verdict(self):
        self._store(1, 1)
        passed = self._review(1, 1, status="done", verdict="passed")
        failed = self._review(1, 1, status="done", verdict="failed")
        running = self._review(1, 1, status="running", verdict=None)
        payload = app_module.review_history_payload(storage.list_reviews(1))
        # The status label describes the run; the verdict is separate.
        self.assertEqual([p["status_label"] for p in payload],
                         ["Running", "Reviewed", "Reviewed"])
        by_id = {p["id"]: p for p in payload}
        self.assertEqual(by_id[passed]["verdict_label"], "Passed")
        self.assertEqual(by_id[failed]["verdict_label"], "Needs work")
        self.assertIsNone(by_id[running]["verdict_label"])
        self.assertEqual(by_id[running]["status_label"], "Running")

    def test_review_history_payload_labels_an_unknown_verdict(self):
        self._store(1, 1)
        self._review(1, 1, status="done", verdict="unknown")
        payload = app_module.review_history_payload(storage.list_reviews(1))
        self.assertEqual(payload[0]["verdict_label"], "No verdict")

    # -- endpoint ---------------------------------------------------------- #
    def test_api_reviews_returns_the_labelled_recent_list(self):
        self._store(1, 7)
        self._review(1, 7, status="done", verdict="passed")
        response = self.client.get("/api/reviews")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["reviews"]), 1)
        entry = data["reviews"][0]
        self.assertEqual(entry["status_label"], "Reviewed")
        self.assertEqual(entry["verdict_label"], "Passed")
        self.assertEqual(entry["pr_id"], 1)
        self.assertEqual(entry["number"], 7)

    def test_api_reviews_empty(self):
        response = self.client.get("/api/reviews")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"reviews": []})

    # -- request page sidebar ---------------------------------------------- #
    def test_request_page_lists_every_review(self):
        self._store(1, 1)
        self._review(1, 1, status="done", verdict="passed")
        self._review(1, 1, status="done", verdict="failed")
        self._review(1, 1, status="error", verdict=None)
        body = self.client.get("/pr/1").get_data(as_text=True)
        self.assertEqual(body.count('class="review-history-row"'), 3)
        self.assertIn("verdict-passed", body)
        self.assertIn("verdict-failed", body)
        self.assertIn("status-error", body)

    def test_request_page_shows_an_empty_state_without_reviews(self):
        self._store(1, 1)
        body = self.client.get("/pr/1").get_data(as_text=True)
        self.assertEqual(body.count('class="review-history-row"'), 0)
        self.assertIn("No reviews yet. Run one above.", body)

    # -- dashboard sidebar ------------------------------------------------- #
    def test_dashboard_lists_recent_reviews(self):
        self._store(1, 7, title="First")
        self._store(2, 8, slug=OTHER_SLUG, repo="group/project", host="gitlab.com",
                    title="Second")
        first = self._review(1, 7, status="done", verdict="passed")
        second = self._review(2, 8, status="running", verdict=None)
        body = self.client.get("/").get_data(as_text=True)
        # One entry per review (the poller's JS template string uses concatenation,
        # so these literal attributes come only from the server-rendered list).
        self.assertIn(f'data-review-id="{first}"', body)
        self.assertIn(f'data-review-id="{second}"', body)
        self.assertIn("reviewHistoryList", body)
        self.assertIn("verdict-passed", body)
        # The running review carries a running status dot (in the review list and
        # in the AI Reviewed list, so at least one) but no verdict label.
        self.assertGreaterEqual(body.count("reviewed-dot status-running"), 1)


if __name__ == "__main__":
    unittest.main()
