"""Tests for the automatic review trigger on watched repositories.

Enabling a repository's watch (the bell icon) turns on two things: a
notification for each new open request, and an automatic review. These tests
cover which requests trigger a review, that the repository's own settings are
honoured, and that watchers never queue a review with no usable agent.

Run with: ``python3 -m unittest discover -s tests``
"""

import atexit
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

# storage reads DATA_DIR at import time, so point it at a throwaway folder
# before importing the application modules.
_TMP_DIR = tempfile.mkdtemp(prefix="pr-reviewer-auto-tests-")
os.environ["DATA_DIR"] = _TMP_DIR
atexit.register(shutil.rmtree, _TMP_DIR, ignore_errors=True)

import agents  # noqa: E402
import app as app_module  # noqa: E402
import providers  # noqa: E402
import reviewer  # noqa: E402
import storage  # noqa: E402

SLUG = "github.com/acme/api"


def _pr(pr_id, number, state="open", updated="2024-01-02T00:00:00Z", head_sha=None):
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
        "head_sha": head_sha,
    }


class FakeProvider:
    """Stands in for a real provider so syncs never touch the network."""

    def __init__(self, entries):
        self.entries = entries

    def fetch_resources(self, repo, token, settings):
        return list(self.entries)

    def fetch_comments(self, repo, number, token, settings):
        return []


class AutoReviewTest(unittest.TestCase):
    def setUp(self):
        storage.init_db()
        with storage.get_conn() as conn:
            conn.execute("DELETE FROM reviews")
            conn.execute("DELETE FROM notifications")
            conn.execute("DELETE FROM dismissed_reviews")
            conn.execute("DELETE FROM pull_requests")
            conn.execute("DELETE FROM repos")

    def _add_repo(self, watch=True, overrides=None):
        storage.add_repos(
            [{"full_name": "acme/api", "provider": "github", "host": "github.com"}]
        )
        if watch:
            storage.set_repo_watch(SLUG, True)
        if overrides:
            storage.set_repo_settings(SLUG, overrides)

    def _store_reviewed(self, pr_id, number, head_sha, state="open"):
        """Store a request and give it one review recorded at ``head_sha``."""
        storage.save_pr(_pr(pr_id, number, state=state, head_sha=head_sha))
        storage.create_review(
            pr_id, "acme/api", number, "opencode", None, head_sha=head_sha
        )

    def _run_sync(self, entries, installed=("opencode",)):
        """Run one sync with a fake provider, faking agent detection/reviews."""
        fake = FakeProvider(entries)
        calls = []

        def fake_start(pr, agent_id, model, settings):
            calls.append({"pr_id": pr["id"], "agent": agent_id, "model": model})
            return 999

        installed_agents = [{"id": a} for a in installed]
        with mock.patch.object(providers, "get_provider", lambda name: fake), \
             mock.patch.object(agents, "available_agents",
                              lambda settings=None: installed_agents), \
             mock.patch.object(reviewer, "start_review", fake_start):
            payload = app_module.sync_repos()
        return payload, calls

    # -- which requests trigger a review ---------------------------------- #
    def test_new_open_pr_in_watched_repo_is_reviewed(self):
        self._add_repo(watch=True)
        storage.save_pr(_pr(1, 1))  # baseline so this is not the first sync
        payload, calls = self._run_sync([_pr(2, 2)])
        self.assertEqual(payload["auto_reviewed"], 1)
        self.assertEqual([c["pr_id"] for c in calls], [2])

    def test_unwatched_repo_is_not_reviewed(self):
        self._add_repo(watch=False)
        storage.save_pr(_pr(1, 1))
        payload, calls = self._run_sync([_pr(2, 2)])
        self.assertNotIn("auto_reviewed", payload)
        self.assertEqual(calls, [])

    def test_first_sync_only_establishes_a_baseline(self):
        self._add_repo(watch=True)  # nothing stored yet -> first sync
        payload, calls = self._run_sync([_pr(2, 2), _pr(3, 3)])
        self.assertNotIn("auto_reviewed", payload)
        self.assertEqual(calls, [])

    def test_closed_new_pr_is_not_reviewed(self):
        self._add_repo(watch=True)
        storage.save_pr(_pr(1, 1))
        _, calls = self._run_sync([_pr(2, 2, state="closed")])
        self.assertEqual(calls, [])

    def test_review_runs_with_no_installed_agent_are_skipped(self):
        self._add_repo(watch=True)
        storage.save_pr(_pr(1, 1))
        payload, calls = self._run_sync([_pr(2, 2)], installed=())
        self.assertNotIn("auto_reviewed", payload)
        self.assertEqual(calls, [])

    def test_repo_overrides_choose_agent_and_model(self):
        self._add_repo(watch=True, overrides={"default_agent": "pi", "default_model": "x/y"})
        storage.save_pr(_pr(1, 1))
        _, calls = self._run_sync([_pr(2, 2)], installed=("opencode", "pi"))
        self.assertEqual(calls, [{"pr_id": 2, "agent": "pi", "model": "x/y"}])

    # -- re-review when a watched request gains commits -------------------- #
    def test_new_commits_on_watched_reviewed_pr_are_reviewed_again(self):
        self._add_repo(watch=True)
        self._store_reviewed(1, 1, head_sha="aaa")
        payload, calls = self._run_sync(
            [_pr(1, 1, updated="2024-02-01T00:00:00Z", head_sha="bbb")]
        )
        self.assertEqual(payload["auto_reviewed"], 1)
        self.assertEqual([c["pr_id"] for c in calls], [1])

    def test_new_commits_are_detected_without_an_updated_at_change(self):
        # Head comparison, not updated_at, is what triggers: same timestamp here.
        self._add_repo(watch=True)
        self._store_reviewed(1, 1, head_sha="aaa")
        payload, calls = self._run_sync([_pr(1, 1, head_sha="bbb")])
        self.assertEqual(payload["auto_reviewed"], 1)
        self.assertEqual([c["pr_id"] for c in calls], [1])

    def test_unchanged_head_is_not_reviewed_again(self):
        self._add_repo(watch=True)
        self._store_reviewed(1, 1, head_sha="aaa")
        payload, calls = self._run_sync(
            [_pr(1, 1, updated="2024-02-01T00:00:00Z", head_sha="aaa")]
        )
        self.assertNotIn("auto_reviewed", payload)
        self.assertEqual(calls, [])

    def test_re_review_is_not_announced_as_a_new_request(self):
        self._add_repo(watch=True)
        self._store_reviewed(1, 1, head_sha="aaa")
        payload, _ = self._run_sync(
            [_pr(1, 1, updated="2024-02-01T00:00:00Z", head_sha="bbb")]
        )
        self.assertNotIn("notifications", payload)
        self.assertEqual(storage.list_notifications(), [])

    def test_new_commits_in_an_unwatched_repo_are_not_reviewed(self):
        self._add_repo(watch=False)
        self._store_reviewed(1, 1, head_sha="aaa")
        _, calls = self._run_sync(
            [_pr(1, 1, updated="2024-02-01T00:00:00Z", head_sha="bbb")]
        )
        self.assertEqual(calls, [])

    def test_new_commits_on_a_closed_pr_are_not_reviewed(self):
        self._add_repo(watch=True)
        self._store_reviewed(1, 1, head_sha="aaa")
        _, calls = self._run_sync(
            [_pr(1, 1, state="closed", updated="2024-02-01T00:00:00Z", head_sha="bbb")]
        )
        self.assertEqual(calls, [])

    def test_pr_without_a_prior_review_is_not_re_reviewed(self):
        self._add_repo(watch=True)
        storage.save_pr(_pr(1, 1, head_sha="aaa"))
        _, calls = self._run_sync(
            [_pr(1, 1, updated="2024-02-01T00:00:00Z", head_sha="bbb")]
        )
        self.assertEqual(calls, [])

    def test_prior_review_without_a_head_is_not_a_baseline(self):
        self._add_repo(watch=True)
        storage.save_pr(_pr(1, 1, head_sha="aaa"))
        storage.create_review(1, "acme/api", 1, "opencode", None)  # no head recorded
        _, calls = self._run_sync(
            [_pr(1, 1, updated="2024-02-01T00:00:00Z", head_sha="bbb")]
        )
        self.assertEqual(calls, [])

    def test_missing_current_head_is_not_reviewed_again(self):
        self._add_repo(watch=True)
        self._store_reviewed(1, 1, head_sha="aaa")
        _, calls = self._run_sync([_pr(1, 1, updated="2024-02-01T00:00:00Z")])
        self.assertEqual(calls, [])

    def test_re_review_is_skipped_when_one_is_already_running(self):
        self._add_repo(watch=True)
        self._store_reviewed(1, 1, head_sha="aaa")
        with mock.patch.object(agents, "available_agents",
                               lambda settings=None: [{"id": "opencode"}]), \
             mock.patch.object(reviewer, "start_review",
                               side_effect=RuntimeError("already running")):
            started = app_module.start_auto_reviews([(1, storage.get_repo(SLUG))], {})
        self.assertEqual(started, 0)

    def test_recorded_head_suppresses_the_next_re_review(self):
        # A re-review records the head it actually checked out; the following
        # sync, which reports the same provider head, must not review again.
        self._add_repo(watch=True)
        self._store_reviewed(1, 1, head_sha="aaa")

        created = []

        def fake_start(pr, agent_id, model, settings):
            review_id = storage.create_review(
                pr["id"], "acme/api", pr["number"], agent_id, model,
                head_sha=pr.get("head_sha"),
            )
            created.append(review_id)
            return review_id

        entry = _pr(1, 1, updated="2024-02-01T00:00:00Z", head_sha="bbb")
        with mock.patch.object(providers, "get_provider", lambda name: FakeProvider([entry])), \
             mock.patch.object(agents, "available_agents",
                               lambda settings=None: [{"id": "opencode"}]), \
             mock.patch.object(reviewer, "start_review", fake_start):
            first = app_module.sync_repos()
            self.assertEqual(len(created), 1)
            # The review finishes by recording the commit it checked out.
            with mock.patch.object(reviewer, "_git", lambda *a, **k: "bbb\n"):
                reviewer._record_head_sha(created[0], "/tmp/ws")
            second = app_module.sync_repos()

        self.assertEqual(first["auto_reviewed"], 1)
        self.assertNotIn("auto_reviewed", second)
        self.assertEqual(len(created), 1)
        self.assertEqual(storage.latest_review(1)["head_sha"], "bbb")

    def test_has_new_commits_tolerates_non_string_heads(self):
        # A malformed provider head must not raise and abort the sync loop.
        self.assertFalse(app_module._has_new_commits(None, {"head_sha": "x"}))
        self.assertTrue(app_module._has_new_commits({"head_sha": 1}, {"head_sha": 2}))
        self.assertFalse(app_module._has_new_commits({"head_sha": 7}, {"head_sha": 7}))
        self.assertFalse(app_module._has_new_commits({"head_sha": 7}, {"head_sha": None}))

    # -- agent selection --------------------------------------------------- #
    def test_auto_review_agent_prefers_first_installed(self):
        with mock.patch.object(agents, "available_agents",
                               lambda settings=None: [{"id": "pi"}, {"id": "claude"}]):
            self.assertEqual(app_module.auto_review_agent({}), "pi")

    def test_auto_review_agent_skips_uninstalled_configured_agent(self):
        with mock.patch.object(agents, "available_agents",
                               lambda settings=None: [{"id": "opencode"}]):
            self.assertIsNone(app_module.auto_review_agent({"default_agent": "claude"}))

    def test_auto_review_agent_allows_custom_with_a_command(self):
        self.assertEqual(
            app_module.auto_review_agent({"default_agent": "custom", "custom_command": "x"}),
            "custom",
        )
        self.assertIsNone(app_module.auto_review_agent({"default_agent": "custom"}))

    # -- the head a review records ----------------------------------------- #
    def test_create_review_records_the_head(self):
        storage.save_pr(_pr(1, 1))
        review_id = storage.create_review(
            1, "acme/api", 1, "opencode", None, head_sha="abc"
        )
        self.assertEqual(storage.get_review(review_id)["head_sha"], "abc")
        self.assertEqual(storage.latest_review(1)["head_sha"], "abc")

    def test_start_review_uses_the_request_head(self):
        storage.save_pr(_pr(1, 1, head_sha="abc"))
        captured = {}

        def fake_create(pr_id, repo, number, agent, model, prompt=None, head_sha=None):
            captured["head_sha"] = head_sha
            return 7

        self.addCleanup(reviewer._active_prs.discard, 1)
        with mock.patch.object(storage, "create_review", fake_create), \
             mock.patch.object(reviewer.threading, "Thread"):
            review_id = reviewer.start_review(storage.get_pr(1), "opencode", None, {})
        self.assertEqual(review_id, 7)
        self.assertEqual(captured["head_sha"], "abc")

    def test_record_head_sha_prefers_the_checked_out_commit(self):
        storage.save_pr(_pr(1, 1, head_sha="stale"))
        review_id = storage.create_review(
            1, "acme/api", 1, "opencode", None, head_sha="stale"
        )
        with mock.patch.object(reviewer, "_git", lambda *a, **k: "realhead\n"):
            reviewer._record_head_sha(review_id, "/tmp/ws")
        self.assertEqual(storage.get_review(review_id)["head_sha"], "realhead")

    # -- the request-list watch indicator ---------------------------------- #
    def test_watched_repo_marks_its_request_rows(self):
        self._add_repo(watch=True)
        storage.save_pr(_pr(1, 1))
        html = app_module.app.test_client().get("/").get_data(as_text=True)
        self.assertIn('class="watch-flag', html)

    def test_unwatched_repo_has_no_watch_marker(self):
        self._add_repo(watch=False)
        storage.save_pr(_pr(1, 1))
        html = app_module.app.test_client().get("/").get_data(as_text=True)
        self.assertNotIn('class="watch-flag', html)

    # -- the head columns migrate with the rest of storage ----------------- #
    def test_head_columns_exist(self):
        with storage.get_conn() as conn:
            pr_columns = {row["name"] for row in conn.execute("PRAGMA table_info(pull_requests)")}
            review_columns = {row["name"] for row in conn.execute("PRAGMA table_info(reviews)")}
        self.assertIn("head_sha", pr_columns)
        self.assertIn("head_sha", review_columns)

    @unittest.skipIf(
        sqlite3.sqlite_version_info < (3, 35, 0),
        "ALTER TABLE ... DROP COLUMN requires SQLite 3.35+",
    )
    def test_missing_head_columns_are_added_on_start(self):
        # Simulate an older database, then confirm init_db heals it.
        with storage.get_conn() as conn:
            conn.execute("ALTER TABLE pull_requests DROP COLUMN head_sha")
            conn.execute("ALTER TABLE reviews DROP COLUMN head_sha")
        storage._initialized = False
        storage.init_db()
        with storage.get_conn() as conn:
            pr_columns = {row["name"] for row in conn.execute("PRAGMA table_info(pull_requests)")}
            review_columns = {row["name"] for row in conn.execute("PRAGMA table_info(reviews)")}
        self.assertIn("head_sha", pr_columns)
        self.assertIn("head_sha", review_columns)

    # -- per-repository workspace lock ------------------------------------ #
    def test_workspace_lock_is_per_slug(self):
        self.assertIs(reviewer._workspace_lock("host/a"), reviewer._workspace_lock("host/a"))
        self.assertIsNot(reviewer._workspace_lock("host/a"), reviewer._workspace_lock("host/b"))


if __name__ == "__main__":
    unittest.main()
