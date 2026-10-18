"""Tests for auto-archiving reviewed requests when they finish.

A request that is tracked in the "AI Reviewed" sidebar list and that changes
from open to closed/merged during a sync leaves the list on its own, keeping its
review history. Only the transition triggers it, so a review started on a request
that was already finished is not hidden.

Run with: ``python3 -m unittest discover -s tests``
"""

import atexit
import os
import shutil
import tempfile
import unittest
from unittest import mock

# storage reads DATA_DIR at import time, so point it at a throwaway folder
# before importing the application modules.
_TMP_DIR = tempfile.mkdtemp(prefix="pr-reviewer-archive-tests-")
os.environ["DATA_DIR"] = _TMP_DIR
atexit.register(shutil.rmtree, _TMP_DIR, ignore_errors=True)

import app as app_module  # noqa: E402
import providers  # noqa: E402
import storage  # noqa: E402

SLUG = "github.com/acme/api"


def _pr(pr_id, number, state="open", updated="2024-01-02T00:00:00Z"):
    """A provider entry (and stored-PR shape) for ``acme/api``."""
    return {
        "id": pr_id,
        "repo": "acme/api",
        "slug": SLUG,
        "provider": "github",
        "host": "github.com",
        "number": number,
        "title": f"PR {number}",
        "user": "octocat",
        "body": "",
        "state": state,
        "url": f"https://github.com/acme/api/pull/{number}",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": updated,
        "draft": False,
        "labels": [],
        "base_ref": "main",
        "head_ref": f"feature-{number}",
    }


class FakeProvider:
    """Stands in for a real provider so syncs never touch the network."""

    def __init__(self, entries):
        self.entries = entries

    def fetch_resources(self, repo, token, settings):
        return list(self.entries)

    def fetch_comments(self, repo, number, token, settings):
        return []


class ArchiveReviewedTest(unittest.TestCase):
    def setUp(self):
        storage.init_db()
        with storage.get_conn() as conn:
            conn.execute("DELETE FROM reviews")
            conn.execute("DELETE FROM notifications")
            conn.execute("DELETE FROM dismissed_reviews")
            conn.execute("DELETE FROM pull_requests")
            conn.execute("DELETE FROM repos")

    def _add_repo(self, watch=False):
        storage.add_repos(
            [{"full_name": "acme/api", "provider": "github", "host": "github.com"}]
        )
        if watch:
            storage.set_repo_watch(SLUG, True)

    def _reviewed(self, pr_id, number):
        """Store a request and give it one review, so it is in the list."""
        storage.save_pr(_pr(pr_id, number))
        storage.create_review(pr_id, "acme/api", number, "opencode", None)
        return pr_id

    def _run_sync(self, entries, only_watched=False):
        fake = FakeProvider(entries)
        with mock.patch.object(providers, "get_provider", lambda name: fake):
            return app_module.sync_repos(only_watched=only_watched)

    # -- storage helpers --------------------------------------------------- #
    def test_existing_pr_states_maps_id_to_state(self):
        storage.save_pr(_pr(1, 1, state="open"))
        storage.save_pr(_pr(2, 2, state="merged"))
        self.assertEqual(storage.existing_pr_states(), {1: "open", 2: "merged"})

    def test_archive_review_ignores_unreviewed_requests(self):
        storage.save_pr(_pr(1, 1))
        self.assertFalse(storage.archive_review(1))
        self.assertEqual(storage.list_reviewed_prs(), [])

    def test_archive_review_hides_a_reviewed_request(self):
        pr_id = self._reviewed(1, 1)
        self.assertEqual([r["pr_id"] for r in storage.list_reviewed_prs()], [pr_id])
        self.assertTrue(storage.archive_review(pr_id))
        self.assertEqual(storage.list_reviewed_prs(), [])
        # Archiving is idempotent and keeps the history.
        self.assertTrue(storage.archive_review(pr_id))
        self.assertEqual(len(storage.list_reviews(pr_id)), 1)

    # -- sync transitions -------------------------------------------------- #
    def test_open_to_merged_archives_and_keeps_history(self):
        self._add_repo()
        pr_id = self._reviewed(1, 1)
        payload = self._run_sync([_pr(1, 1, state="merged", updated="2024-02-01T00:00:00Z")])
        self.assertEqual(payload["archived"], 1)
        self.assertEqual(storage.list_reviewed_prs(), [])
        self.assertEqual(len(storage.list_reviews(pr_id)), 1)

    def test_open_to_closed_archives(self):
        self._add_repo()
        self._reviewed(1, 1)
        payload = self._run_sync([_pr(1, 1, state="closed", updated="2024-02-01T00:00:00Z")])
        self.assertEqual(payload["archived"], 1)
        self.assertEqual(storage.list_reviewed_prs(), [])

    def test_state_change_archives_even_when_updated_at_is_unchanged(self):
        self._add_repo()
        self._reviewed(1, 1)
        payload = self._run_sync([_pr(1, 1, state="merged")])  # same updated_at
        self.assertEqual(payload["archived"], 1)
        self.assertEqual(storage.list_reviewed_prs(), [])

    def test_already_finished_request_is_left_alone(self):
        self._add_repo()
        storage.save_pr(_pr(1, 1, state="closed"))
        storage.create_review(1, "acme/api", 1, "opencode", None)
        payload = self._run_sync([_pr(1, 1, state="closed", updated="2024-02-01T00:00:00Z")])
        self.assertNotIn("archived", payload)
        self.assertEqual([r["pr_id"] for r in storage.list_reviewed_prs()], [1])

    def test_reopened_request_is_not_archived(self):
        self._add_repo()
        self._reviewed(1, 1)
        payload = self._run_sync([_pr(1, 1, state="open", updated="2024-02-01T00:00:00Z")])
        self.assertNotIn("archived", payload)
        self.assertEqual([r["pr_id"] for r in storage.list_reviewed_prs()], [1])

    def test_unreviewed_request_that_finishes_is_not_archived(self):
        self._add_repo()
        storage.save_pr(_pr(1, 1, state="open"))
        payload = self._run_sync([_pr(1, 1, state="merged", updated="2024-02-01T00:00:00Z")])
        self.assertNotIn("archived", payload)
        self.assertEqual(storage.list_reviewed_prs(), [])

    def test_background_watch_sync_also_archives(self):
        self._add_repo(watch=True)
        self._reviewed(1, 1)
        payload = self._run_sync(
            [_pr(1, 1, state="merged", updated="2024-02-01T00:00:00Z")],
            only_watched=True,
        )
        self.assertEqual(payload["archived"], 1)
        self.assertEqual(storage.list_reviewed_prs(), [])

    def test_a_new_review_brings_an_archived_request_back(self):
        self._add_repo()
        pr_id = self._reviewed(1, 1)
        self._run_sync([_pr(1, 1, state="merged", updated="2024-02-01T00:00:00Z")])
        self.assertEqual(storage.list_reviewed_prs(), [])
        storage.create_review(pr_id, "acme/api", 1, "opencode", None)
        self.assertEqual([r["pr_id"] for r in storage.list_reviewed_prs()], [pr_id])


if __name__ == "__main__":
    unittest.main()
