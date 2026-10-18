"""Tests for how a review run's outcome is decided.

A review is the app's reason to exist, so its ``done``/``error`` decision must
not be derailed by a non-fatal agent failure. Some CLIs exit non-zero *after*
the agent has produced the complete review -- OpenCode, for example, exits 1
when its web-search tool is unavailable. Because a completed review always ends
with a verdict marker (see ``specs/008-review-status-api``), that marker -- not
the exit code alone -- decides whether the review counts as complete.

Run with: ``python3 -m unittest discover -s tests``
"""

import atexit
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

# storage reads DATA_DIR at import time, so point it at a throwaway folder
# before importing the application modules.
_TMP_DIR = tempfile.mkdtemp(prefix="pr-reviewer-reviewer-tests-")
os.environ["DATA_DIR"] = _TMP_DIR
atexit.register(shutil.rmtree, _TMP_DIR, ignore_errors=True)

import reviewer  # noqa: E402
import storage  # noqa: E402


def _pr(pr_id, number, head_sha="abc"):
    """A stored-PR shape for ``acme/api``."""
    return {
        "id": pr_id,
        "repo": "acme/api",
        "slug": "github.com/acme/api",
        "provider": "github",
        "host": "github.com",
        "number": number,
        "title": f"PR {number}",
        "user": "octocat",
        "body": "",
        "state": "open",
        "url": f"https://github.com/acme/api/pull/{number}",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "draft": False,
        "labels": [],
        "base_ref": "main",
        "head_ref": f"feature-{number}",
        "head_sha": head_sha,
    }


class ReviewOutcomeTest(unittest.TestCase):
    """The ``done``/``error`` decision for a finished agent process."""

    def setUp(self):
        storage.init_db()
        storage.save_pr(_pr(1, 1))

    def _run(self, returncode, stdout, stderr=""):
        """Run one review against a stubbed agent process; return the row."""
        pr = storage.get_pr(1)
        review_id = storage.create_review(1, "acme/api", 1, "opencode", None)
        proc = subprocess.CompletedProcess(
            args=["agent"], returncode=returncode, stdout=stdout, stderr=stderr
        )
        with mock.patch.object(reviewer, "prepare_workspace", lambda *a, **k: "/tmp/ws"), \
             mock.patch.object(
                 reviewer, "_record_head_sha", lambda *a, **k: None, create=True,
             ), \
             mock.patch.object(
                 reviewer.agents, "resolve_command",
                 lambda *a, **k: (["agent", "review"], None),
             ), \
             mock.patch.object(reviewer.agents, "run_streaming", lambda *a, **k: proc):
            reviewer._run_review(review_id, pr, "opencode", None, {})
        return storage.get_review(review_id)

    def test_nonzero_exit_with_a_passing_verdict_is_a_completed_review(self):
        # OpenCode exits 1 when its web-search tool is cancelled, but the review
        # itself finished; the trailing verdict proves it, so it must be stored
        # as done rather than failed.
        review = self._run(
            returncode=1,
            stdout="## Review\nLooks good to merge.\n\nREVIEW_VERDICT: PASS\n",
            stderr="Error: Web search cancelled",
        )
        self.assertEqual(review["status"], "done")
        self.assertEqual(review["verdict"], "passed")
        self.assertIn("Looks good to merge.", review["output"])
        # The CLI's stderr is still kept, as for any completed review.
        self.assertIn("Web search cancelled", review["error"] or "")

    def test_nonzero_exit_with_a_failing_verdict_is_a_completed_review(self):
        review = self._run(
            returncode=1,
            stdout="## Review\nThere is a blocking bug.\n\nREVIEW_VERDICT: FAIL\n",
            stderr="Error: Web search cancelled",
        )
        self.assertEqual(review["status"], "done")
        self.assertEqual(review["verdict"], "failed")

    def test_nonzero_exit_without_a_verdict_is_an_error(self):
        # No verdict means the agent never finished; the non-zero exit stands.
        review = self._run(
            returncode=1,
            stdout="I started reviewing but could not finish.",
            stderr="",
        )
        self.assertEqual(review["status"], "error")
        self.assertIsNone(review["verdict"])

    def test_zero_exit_without_a_verdict_is_done_unknown(self):
        # A clean exit is trusted even when the agent omitted the marker.
        review = self._run(returncode=0, stdout="No marker here.", stderr="")
        self.assertEqual(review["status"], "done")
        self.assertEqual(review["verdict"], "unknown")


if __name__ == "__main__":
    unittest.main()
