"""Tests for the live review timer and streaming logs.

A review can run for many minutes, so the request page shows a ticking clock and
the agent's output as it is produced. The agent is run through
``agents.run_streaming``, which reports stdout/stderr line by line; ``reviewer``
keeps a bounded, token-redacted transcript in the ``reviews.log`` column. See
``specs/011-review-timer-and-logs``.

Run with: ``python3 -m unittest discover -s tests``
"""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

# storage reads DATA_DIR at import time, so point it at a throwaway folder
# before importing the application modules.
_TMP_DIR = tempfile.mkdtemp(prefix="pr-reviewer-logs-tests-")
os.environ["DATA_DIR"] = _TMP_DIR
atexit.register(shutil.rmtree, _TMP_DIR, ignore_errors=True)

import agents  # noqa: E402
import app as app_module  # noqa: E402
import reviewer  # noqa: E402
import storage  # noqa: E402

SLUG = "github.com/acme/api"


def _pr(pr_id, number, head_sha="abc"):
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


class RunStreamingTest(unittest.TestCase):
    """``agents.run_streaming`` reports output as it arrives."""

    def test_collects_stdout_and_stderr(self):
        script = (
            "import sys\n"
            "print('out-one')\n"
            "print('err-one', file=sys.stderr)\n"
            "print('out-two')\n"
        )
        seen = []
        proc = agents.run_streaming(
            [sys.executable, "-c", script], cwd=_TMP_DIR, timeout=30,
            on_output=lambda stream, line: seen.append((stream, line)),
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("out-one", proc.stdout)
        self.assertIn("out-two", proc.stdout)
        self.assertIn("err-one", proc.stderr)
        # stdout and stderr are reported separately, as they are produced.
        self.assertIn(("stdout", "out-one\n"), seen)
        self.assertIn(("stderr", "err-one\n"), seen)

    def test_reports_a_line_while_the_process_is_still_running(self):
        # The child prints one line, then blocks until the callback creates a
        # marker file, then prints a second line. If output were only delivered
        # at exit, the child would never see the marker and the run would time
        # out instead of finishing -- so this proves streaming is live.
        marker = os.path.join(_TMP_DIR, "stream-marker")
        script = (
            "import os, sys, time\n"
            "print('first', flush=True)\n"
            "target = sys.argv[1]\n"
            "for _ in range(200):\n"
            "    if os.path.exists(target):\n"
            "        break\n"
            "    time.sleep(0.05)\n"
            "print('second', flush=True)\n"
        )

        def on_output(stream, line):
            if "first" in line:
                with open(marker, "w", encoding="utf-8") as handle:
                    handle.write("ok")

        proc = agents.run_streaming(
            [sys.executable, "-c", script, marker], cwd=_TMP_DIR, timeout=15,
            on_output=on_output,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("first", proc.stdout)
        self.assertIn("second", proc.stdout)

    def test_timeout_kills_the_process_but_keeps_partial_output(self):
        script = "import sys, time\nprint('working', flush=True)\ntime.sleep(60)\n"
        seen = []
        with self.assertRaises(subprocess.TimeoutExpired):
            agents.run_streaming(
                [sys.executable, "-c", script], cwd=_TMP_DIR, timeout=1,
                on_output=lambda stream, line: seen.append(line),
            )
        # Whatever was printed before the kill has already been streamed.
        self.assertIn("working\n", seen)


class ReviewLogPolicyTest(unittest.TestCase):
    """The log writer redacts tokens and keeps the newest output."""

    def setUp(self):
        storage.init_db()
        storage.save_pr(_pr(1, 1))

    def test_token_is_redacted(self):
        review_id = storage.create_review(1, "acme/api", 1, "opencode", None)
        log = reviewer._ReviewLog(review_id, token="sekret-123")
        log.append("using token sekret-123 now\n")
        rendered = log.render()
        self.assertNotIn("sekret-123", rendered)
        self.assertIn("***", rendered)

    def test_log_is_capped_and_keeps_the_newest_output(self):
        review_id = storage.create_review(1, "acme/api", 1, "opencode", None)
        log = reviewer._ReviewLog(
            review_id, max_chars=100, flush_seconds=10 ** 12
        )
        for i in range(10):
            log.append(f"line-{i}".ljust(60) + "\n")
        rendered = log.render()
        self.assertIn("line-9", rendered)      # newest kept
        self.assertNotIn("line-0", rendered)   # oldest dropped


class ReviewRunLogTest(unittest.TestCase):
    """``_run_review`` records the streamed transcript on the review."""

    def setUp(self):
        storage.init_db()
        storage.save_pr(_pr(1, 1))

    def _run(self, stdout, stderr="", token=None):
        pr = storage.get_pr(1)
        settings = {"github_token": token} if token else {}
        review_id = storage.create_review(1, "acme/api", 1, "opencode", None)

        def fake_streaming(command, cwd=None, timeout=None, env=None, on_output=None):
            for line in stdout.splitlines(keepends=True):
                if on_output:
                    on_output("stdout", line)
            for line in stderr.splitlines(keepends=True):
                if on_output:
                    on_output("stderr", line)
            return subprocess.CompletedProcess(command, 0, stdout, stderr)

        with mock.patch.object(reviewer, "prepare_workspace", lambda *a, **k: "/tmp/ws"), \
             mock.patch.object(reviewer, "_record_head_sha", lambda *a, **k: None, create=True), \
             mock.patch.object(
                 reviewer.agents, "resolve_command",
                 lambda *a, **k: (["agent", "review"], None),
             ), \
             mock.patch.object(reviewer.agents, "run_streaming", fake_streaming):
            reviewer._run_review(review_id, pr, "opencode", None, settings)
        return storage.get_review(review_id)

    def test_log_contains_the_streamed_output_and_the_verdict_still_parses(self):
        review = self._run(
            "## Review\nLooks good to merge.\n\nREVIEW_VERDICT: PASS\n",
            stderr="note from the agent\n",
        )
        self.assertEqual(review["status"], "done")
        self.assertEqual(review["verdict"], "passed")
        self.assertIn("Looks good to merge.", review["log"])
        self.assertIn("[stderr] note from the agent", review["log"])
        # The final output is still stored separately and in full.
        self.assertIn("Looks good to merge.", review["output"])

    def test_token_is_not_persisted_in_the_log(self):
        review = self._run(
            "leaking ghp-secret-token here\n\nREVIEW_VERDICT: FAIL\n",
            token="ghp-secret-token",
        )
        self.assertEqual(review["verdict"], "failed")
        self.assertNotIn("ghp-secret-token", review["log"] or "")
        self.assertIn("***", review["log"] or "")

    def test_log_and_timing_are_exposed_by_the_review_api(self):
        review = self._run("done\n\nREVIEW_VERDICT: PASS\n")
        self.client = app_module.app.test_client()
        payload = self.client.get(f"/api/reviews/{review['id']}").get_json()
        self.assertIn("log", payload)
        self.assertIn("done", payload["log"])
        self.assertIsNotNone(payload["created_at"])
        self.assertIsNotNone(payload["finished_at"])


class LiveStreamingIntegrationTest(unittest.TestCase):
    """End-to-end: the stored log grows while the agent is still running."""

    def setUp(self):
        storage.init_db()
        storage.save_pr(_pr(3, 3))

    def _wait_for(self, predicate, review_id, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate(storage.get_review(review_id)):
                return True
            time.sleep(0.1)
        return False

    def test_log_is_persisted_before_the_run_finishes(self):
        # The agent prints a line every ~1.1s, longer than the log flush interval,
        # so its first line reaches storage while it is still working.
        script = (
            "import time\n"
            "for i in range(3):\n"
            "    print('chunk-' + str(i), flush=True)\n"
            "    time.sleep(1.1)\n"
        )
        pr = storage.get_pr(3)
        review_id = storage.create_review(3, "acme/api", 3, "opencode", None)
        with mock.patch.object(reviewer, "prepare_workspace", lambda *a, **k: _TMP_DIR), \
             mock.patch.object(reviewer, "_record_head_sha", lambda *a, **k: None, create=True), \
             mock.patch.object(
                 reviewer.agents, "resolve_command",
                 lambda *a, **k: ([sys.executable, "-c", script], None),
             ):
            thread = threading.Thread(
                target=reviewer._run_review,
                args=(review_id, pr, "opencode", None, {"review_timeout": 60}),
            )
            thread.start()
            try:
                observed = self._wait_for(
                    lambda review: review["log"] and "chunk-0" in review["log"],
                    review_id, timeout=8,
                )
            finally:
                thread.join(timeout=20)

        self.assertTrue(observed, "the log was not persisted while the run was in progress")
        review = storage.get_review(review_id)
        self.assertEqual(review["status"], "done")
        self.assertIn("chunk-2", review["log"])


class ReviewPanelRenderTest(unittest.TestCase):
    """The request page carries the timer and log elements."""

    def setUp(self):
        storage.init_db()
        storage.save_pr(_pr(2, 2))
        self.client = app_module.app.test_client()

    def test_details_page_renders_the_timer_and_log_area(self):
        html = self.client.get("/pr/2").get_data(as_text=True)
        self.assertIn('id="reviewTimer"', html)
        self.assertIn('id="reviewLog"', html)
        self.assertIn("toggleReviewLog", html)

    def test_history_shows_a_finished_review_with_its_duration(self):
        pr = storage.get_pr(2)
        review_id = storage.create_review(2, "acme/api", 2, "opencode", "gpt-x")
        storage.update_review(
            review_id, status="done", output="ok", verdict="passed",
            finished_at="2024-01-01T00:05:00+00:00", duration_ms=12345,
        )
        self.assertIsNotNone(pr)
        html = self.client.get("/pr/2").get_data(as_text=True)
        self.assertIn(f'value="{review_id}"', html)
        self.assertIn("12.3s", html)


if __name__ == "__main__":
    unittest.main()
