"""Tests for turning provider payloads into stored request entries.

Each provider reports a request's head commit in its own shape, and the review
pipeline leans on that value to tell "already reviewed" from "gained commits".
These tests pin the extraction for GitHub and GitLab so a wrong field cannot slip
through silently and send the watcher into a re-review loop.

Run with: ``python3 -m unittest discover -s tests``
"""

import atexit
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace

# storage reads DATA_DIR at import time; keep imports off the real data folder.
_TMP_DIR = tempfile.mkdtemp(prefix="pr-reviewer-provider-tests-")
os.environ["DATA_DIR"] = _TMP_DIR
atexit.register(shutil.rmtree, _TMP_DIR, ignore_errors=True)

import providers  # noqa: E402

GITHUB_REPO = {
    "full_name": "acme/api",
    "slug": "github.com/acme/api",
    "provider": "github",
    "host": "github.com",
}
GITLAB_REPO = {
    "full_name": "acme/api",
    "slug": "gitlab.com/acme/api",
    "provider": "gitlab",
    "host": "gitlab.com",
}


def _github_pull(head_sha="head123"):
    """The slice of a PyGithub PullRequest that ``_github_entry`` reads."""
    return SimpleNamespace(
        id=11,
        number=7,
        title="Add a thing",
        body="body",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-02T00:00:00Z",
        state="open",
        merged=False,
        html_url="https://github.com/acme/api/pull/7",
        draft=False,
        labels=[SimpleNamespace(name="bug")],
        base=SimpleNamespace(ref="main"),
        head=SimpleNamespace(ref="feature", sha=head_sha),
        additions=1,
        deletions=2,
        changed_files=1,
        user=SimpleNamespace(login="octocat", avatar_url=None),
    )


def _gitlab_mr(**overrides):
    """The slice of a GitLab MR dict that ``_gitlab_entry`` reads."""
    mr = {
        "id": 1,
        "iid": 7,
        "title": "Add a thing",
        "description": "body",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "state": "opened",
        "web_url": "https://gitlab.com/acme/api/-/merge_requests/7",
        "draft": False,
        "work_in_progress": False,
        "labels": [],
        "target_branch": "main",
        "source_branch": "feature",
        "sha": "cafe123",
        "author": {"username": "octocat", "avatar_url": None},
    }
    mr.update(overrides)
    return mr


class GithubEntryTest(unittest.TestCase):
    def test_head_sha_comes_from_the_head_commit(self):
        entry = providers._github_entry(_github_pull(head_sha="cafe123"), GITHUB_REPO)
        self.assertEqual(entry["head_sha"], "cafe123")
        self.assertEqual(entry["head_ref"], "feature")
        self.assertEqual(entry["base_ref"], "main")


class GitlabEntryTest(unittest.TestCase):
    def test_head_sha_comes_from_the_mr_sha(self):
        entry = providers._gitlab_entry(_gitlab_mr(sha="beef456"), GITLAB_REPO)
        self.assertEqual(entry["head_sha"], "beef456")
        self.assertEqual(entry["head_ref"], "feature")

    def test_head_sha_falls_back_to_the_diff_ref(self):
        # ``sha`` is the source-branch tip; if an API version omits it, the diff
        # ref names the same commit.
        mr = _gitlab_mr(sha=None, diff_refs={"head_sha": "feed789"})
        entry = providers._gitlab_entry(mr, GITLAB_REPO)
        self.assertEqual(entry["head_sha"], "feed789")


if __name__ == "__main__":
    unittest.main()
