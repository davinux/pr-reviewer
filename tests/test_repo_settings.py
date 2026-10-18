"""Tests for per-repository settings.

Covers the storage parsing, the inherit/override/clear round trip, the
multi-host ambiguity fix and the validation added to the API endpoint.

Run with: ``python3 -m unittest discover -s tests``
"""

import atexit
import os
import shutil
import tempfile
import unittest

# storage reads DATA_DIR at import time, so point it at a throwaway folder
# before importing the application modules.
_TMP_DIR = tempfile.mkdtemp(prefix="pr-reviewer-tests-")
os.environ["DATA_DIR"] = _TMP_DIR
atexit.register(shutil.rmtree, _TMP_DIR, ignore_errors=True)

import app as app_module  # noqa: E402
import storage  # noqa: E402

GITHUB_SLUG = "github.com/acme/api"
GITLAB_SLUG = "gitlab.com/acme/api"


class RepoSettingsTest(unittest.TestCase):
    def setUp(self):
        storage.init_db()
        with storage.get_conn() as conn:
            conn.execute("DELETE FROM repos")
        self.client = app_module.app.test_client()

    def _add_repo(self, full_name, provider, host):
        storage.add_repos(
            [{"full_name": full_name, "provider": provider, "host": host}]
        )

    def _add_shared_name(self):
        """The same owner/repo on two hosts, which share a ``full_name``."""
        self._add_repo("acme/api", "github", "github.com")
        self._add_repo("acme/api", "gitlab", "gitlab.com")

    # -- storage parsing --------------------------------------------------- #
    def test_load_repo_settings_tolerates_bad_data(self):
        self.assertEqual(storage._load_repo_settings(None), {})
        self.assertEqual(storage._load_repo_settings(""), {})
        self.assertEqual(storage._load_repo_settings("not json"), {})
        self.assertEqual(storage._load_repo_settings("[1, 2]"), {})
        self.assertEqual(
            storage._load_repo_settings('{"review_timeout": 120}'),
            {"review_timeout": 120},
        )

    def test_get_repo_matches_slug_only(self):
        self._add_shared_name()
        self.assertEqual(storage.get_repo(GITHUB_SLUG)["slug"], GITHUB_SLUG)
        self.assertEqual(storage.get_repo(GITLAB_SLUG)["slug"], GITLAB_SLUG)
        # A bare full_name is ambiguous, so it must not resolve to a repo.
        self.assertIsNone(storage.get_repo("acme/api"))

    def test_set_repo_settings_touches_one_host_only(self):
        self._add_shared_name()
        self.assertTrue(storage.set_repo_settings(GITHUB_SLUG, {"review_timeout": 42}))
        self.assertEqual(storage.get_repo(GITHUB_SLUG)["settings"], {"review_timeout": 42})
        self.assertEqual(storage.get_repo(GITLAB_SLUG)["settings"], {})
        # A bare full_name must not match (or update) any repo.
        self.assertFalse(storage.set_repo_settings("acme/api", {"review_timeout": 7}))

    # -- merge ------------------------------------------------------------- #
    def test_effective_settings_inherit_override_and_clear(self):
        settings = app_module.get_settings()
        base = settings["review_timeout"]

        inherited = app_module.effective_repo_settings(settings, {"settings": {}})
        self.assertEqual(inherited["review_timeout"], base)

        overridden = app_module.effective_repo_settings(
            settings, {"settings": {"review_timeout": 120}}
        )
        self.assertEqual(overridden["review_timeout"], 120)
        self.assertEqual(overridden["max_prompt_chars"], settings["max_prompt_chars"])

        # A missing repo falls back to the global settings object unchanged.
        self.assertIs(app_module.effective_repo_settings(settings, None), settings)

    def test_effective_settings_ignore_corrupt_stored_values(self):
        settings = app_module.get_settings()
        merged = app_module.effective_repo_settings(
            settings, {"settings": {"review_timeout": "garbage", "default_agent": "pi"}}
        )
        self.assertEqual(merged["review_timeout"], settings["review_timeout"])
        self.assertEqual(merged["default_agent"], "pi")

    # -- endpoint ---------------------------------------------------------- #
    def _post(self, slug, payload):
        return self.client.post(f"/api/repos/{slug}/settings", json=payload)

    def test_round_trip_and_clear(self):
        self._add_repo("acme/api", "github", "github.com")
        global_timeout = app_module.get_settings()["review_timeout"]

        data = self._post(GITHUB_SLUG, {"review_timeout": 120, "default_model": "a/b"}).get_json()
        self.assertEqual(data["overrides"], {"review_timeout": 120, "default_model": "a/b"})

        # Empty value clears an override; a value equal to the global default is
        # dropped, so the repo inherits it again.
        data = self._post(GITHUB_SLUG, {"default_model": ""}).get_json()
        self.assertNotIn("default_model", data["overrides"])
        data = self._post(GITHUB_SLUG, {"review_timeout": global_timeout}).get_json()
        self.assertEqual(data["overrides"], {})

    def test_prompt_equal_to_fallback_is_dropped(self):
        self._add_repo("acme/api", "github", "github.com")
        builtin = app_module.reviewer.DEFAULT_REVIEW_PROMPT
        data = self._post(GITHUB_SLUG, {"review_prompt": builtin}).get_json()
        self.assertEqual(data["overrides"], {})
        data = self._post(GITHUB_SLUG, {"review_prompt": "Only care about {repo}"}).get_json()
        self.assertEqual(data["overrides"]["review_prompt"], "Only care about {repo}")

    def test_invalid_number_is_rejected_and_not_persisted(self):
        self._add_repo("acme/api", "github", "github.com")
        response = self._post(GITHUB_SLUG, {"review_timeout": "notanumber"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())
        self.assertEqual(storage.get_repo(GITHUB_SLUG)["settings"], {})

    def test_timeout_is_floored_at_one(self):
        self._add_repo("acme/api", "github", "github.com")
        data = self._post(GITHUB_SLUG, {"review_timeout": 0}).get_json()
        self.assertEqual(data["overrides"]["review_timeout"], 1)
        data = self._post(GITHUB_SLUG, {"review_timeout": -30}).get_json()
        self.assertEqual(data["overrides"]["review_timeout"], 1)

    def test_unknown_agent_is_rejected(self):
        self._add_repo("acme/api", "github", "github.com")
        response = self._post(GITHUB_SLUG, {"default_agent": "not-an-agent"})
        self.assertEqual(response.status_code, 400)

    def test_unknown_keys_are_ignored(self):
        self._add_repo("acme/api", "github", "github.com")
        data = self._post(GITHUB_SLUG, {"github_token": "secret", "host": "evil"}).get_json()
        self.assertEqual(data["overrides"], {})

    def test_missing_repo_returns_404(self):
        server = self.client.get("/api/repos/github.com/nope/nope/settings")
        self.assertEqual(server.status_code, 404)

    def test_post_uses_slug_so_other_host_is_untouched(self):
        self._add_shared_name()
        self._post(GITHUB_SLUG, {"review_timeout": 33})
        self.assertEqual(storage.get_repo(GITHUB_SLUG)["settings"], {"review_timeout": 33})
        self.assertEqual(storage.get_repo(GITLAB_SLUG)["settings"], {})


if __name__ == "__main__":
    unittest.main()
