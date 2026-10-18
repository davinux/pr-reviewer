"""Git hosting providers.

The reviewer works against GitHub and GitLab. A repository is identified by a
``slug`` of ``<host>/<owner>/<repo>`` so the same ``owner/repo`` on two hosts
never collides. Each provider knows how to list merge requests / pull requests,
fetch their comments, build a clone URL and locate the request's head ref.

Add a new provider by implementing the same small surface and registering it in
:data:`PROVIDERS`.
"""

import threading
from urllib.parse import quote, urlparse

import requests
from github import Auth, Github

DEFAULT_HOSTS = {"github": "github.com", "gitlab": "gitlab.com"}
# GitLab calls it "opened"; the UI uses "open".
STATE_MAP = {"opened": "open", "locked": "open"}

# Caps so one huge request cannot pull unbounded data into the UI.
MAX_COMMITS = 250
MAX_FILES = 3000


# --------------------------------------------------------------------------- #
# Repository parsing
# --------------------------------------------------------------------------- #
def parse_repo(text, default_provider="github", hosts=None):
    """Parse a repository reference into a provider/host/slug record.

    Accepts ``owner/repo`` (uses ``default_provider``), ``gitlab:owner/repo``,
    ``github:owner/repo``, ``gitlab.com/owner/repo`` and full ``http(s)://`` URLs.
    ``hosts`` maps provider id -> default host (from the configured URLs).
    """
    hosts = dict(hosts or DEFAULT_HOSTS)
    text = (text or "").strip().rstrip("/")
    if not text:
        raise ValueError("empty repository")
    if text.endswith(".git"):
        text = text[:-4]

    provider = None

    # Explicit prefix, e.g. "gitlab:group/project".
    if "://" not in text and ":" in text:
        prefix, _, rest = text.partition(":")
        if prefix in DEFAULT_HOSTS and rest:
            provider = prefix
            text = rest

    host = None
    if "://" in text:
        parsed = urlparse(text)
        host = parsed.netloc.rsplit("@", 1)[-1]
        text = parsed.path.strip("/")
        if provider is None:
            provider = _provider_for_host(host)
    else:
        first, sep, rest = text.partition("/")
        # host/path form, e.g. "gitlab.example.com/group/project".
        if sep and "." in first and first not in DEFAULT_HOSTS:
            host = first
            text = rest
            if provider is None:
                provider = _provider_for_host(host)

    provider = provider or default_provider
    if host is None:
        host = hosts.get(provider) or DEFAULT_HOSTS.get(provider, "github.com")

    full_name = text.strip("/")
    if "/" not in full_name:
        raise ValueError("expected owner/repo")
    return {
        "provider": provider,
        "host": host,
        "full_name": full_name,
        "slug": f"{host}/{full_name}",
    }


def provider_hosts(settings):
    """Default host per provider, derived from the configured URLs."""
    settings = settings or {}
    github = urlparse(settings.get("github_url") or "").hostname or "github.com"
    gitlab = urlparse(settings.get("gitlab_url") or "").hostname or "gitlab.com"
    return {"github": github, "gitlab": gitlab}


def _provider_for_host(host):
    if host == "github.com":
        return "github"
    if host == "gitlab.com" or "gitlab" in host:
        return "gitlab"
    return None


def token_for(provider, settings):
    if provider == "gitlab":
        return (settings.get("gitlab_token") or "").strip()
    return (settings.get("github_token") or "").strip()


def get_provider(name):
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ValueError(f"Unknown provider: {name}")
    return provider


# --------------------------------------------------------------------------- #
# GitHub
# --------------------------------------------------------------------------- #
class GitHub:
    id = "github"
    label = "GitHub"
    DEFAULT_API = "https://api.github.com"

    def __init__(self):
        self._lock = threading.Lock()
        self._clients = {}

    def api_base(self, settings=None):
        """GitHub API base URL from settings, defaulting from ``github_url``."""
        settings = settings or {}
        explicit = (settings.get("github_api_url") or "").strip()
        if explicit:
            return explicit.rstrip("/")
        web = (settings.get("github_url") or "https://github.com").strip().rstrip("/")
        host = urlparse(web).hostname or "github.com"
        if host == "github.com":
            return self.DEFAULT_API
        return f"{web}/api/v3"

    def _client(self, token, settings=None):
        if not token:
            return None
        base = self.api_base(settings)
        key = (base, token)
        with self._lock:
            client = self._clients.get(key)
            if client is not None:
                return client
            try:
                client = Github(auth=Auth.Token(token), base_url=base)
                client.get_user()
                self._clients[key] = client
            except Exception as exc:  # noqa: BLE001
                print(f"Invalid GitHub token: {exc}")
                return None
            return client

    def clone_url(self, repo, token, settings=None):
        if token:
            return f"https://x-access-token:{token}@{repo['host']}/{repo['full_name']}.git"
        return f"https://{repo['host']}/{repo['full_name']}.git"

    def head_ref(self, number):
        return f"refs/pull/{number}/head"

    def fetch_resources(self, repo, token, settings=None):
        gh = self._client(token, settings)
        if gh is None:
            return []
        try:
            # Fetch every state so requests that have since been closed or merged
            # are updated instead of lingering as "open" in storage.
            pulls = gh.get_repo(repo["full_name"]).get_pulls(
                state="all", sort="created", direction="asc"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Error fetching PRs for {repo['slug']}: {exc}")
            return []
        return [_github_entry(pull, repo) for pull in pulls]

    def fetch_comments(self, repo, number, token, settings=None):
        gh = self._client(token, settings)
        if gh is None:
            return []
        try:
            pull = gh.get_repo(repo["full_name"]).get_pull(number)
            return [
                {
                    "id": comment.id,
                    "user": comment.user.login if comment.user else None,
                    "body": comment.body,
                    "created_at": _iso(comment.created_at),
                }
                for comment in pull.get_comments()
            ]
        except Exception as exc:  # noqa: BLE001
            print(f"Error fetching comments for {repo['slug']} #{number}: {exc}")
            return []

    def fetch_commits(self, repo, number, token, settings=None):
        gh = self._client(token, settings)
        if gh is None:
            return []
        try:
            pull = gh.get_repo(repo["full_name"]).get_pull(number)
        except Exception as exc:  # noqa: BLE001
            print(f"Error fetching commits for {repo['slug']} #{number}: {exc}")
            return []
        commits = []
        try:
            for commit in pull.get_commits():
                git = commit.commit
                author = git.author if git else None
                commits.append({
                    "sha": commit.sha,
                    "short_sha": commit.sha[:7],
                    "message": git.message if git else "",
                    "author_name": author.name if author else None,
                    "author_login": commit.author.login if commit.author else None,
                    "author_avatar": commit.author.avatar_url if commit.author else None,
                    "date": _iso(author.date) if author else None,
                    "url": commit.html_url,
                })
                if len(commits) >= MAX_COMMITS:
                    break
        except Exception as exc:  # noqa: BLE001
            print(f"Error listing commits for {repo['slug']} #{number}: {exc}")
        return commits

    def fetch_files(self, repo, number, token, settings=None):
        gh = self._client(token, settings)
        if gh is None:
            return []
        try:
            pull = gh.get_repo(repo["full_name"]).get_pull(number)
        except Exception as exc:  # noqa: BLE001
            print(f"Error fetching files for {repo['slug']} #{number}: {exc}")
            return []
        files = []
        try:
            for changed in pull.get_files():
                files.append({
                    "filename": changed.filename,
                    "previous_filename": getattr(changed, "previous_filename", None),
                    "status": changed.status,
                    "additions": changed.additions,
                    "deletions": changed.deletions,
                    "changes": changed.changes,
                    "patch": getattr(changed, "patch", None),
                    "blob_url": getattr(changed, "blob_url", None),
                })
                if len(files) >= MAX_FILES:
                    break
        except Exception as exc:  # noqa: BLE001
            print(f"Error listing files for {repo['slug']} #{number}: {exc}")
        return files


def _github_state(pull):
    """Normalise a GitHub PR state, telling merged pulls from plain closed ones.

    GitHub reports a merged pull request with ``state == "closed"``; the merged
    flag is what distinguishes it, so the UI can offer a separate "Merged" tab.
    """
    if pull.state == "open":
        return "open"
    return "merged" if _safe(lambda: pull.merged) else "closed"


def _github_entry(pull, repo):
    try:
        avatar = pull.user.avatar_url
    except Exception:  # noqa: BLE001
        avatar = None
    return {
        "id": pull.id,
        "repo": repo["full_name"],
        "slug": repo["slug"],
        "provider": repo["provider"],
        "host": repo["host"],
        "number": pull.number,
        "title": pull.title,
        "user": pull.user.login if pull.user else None,
        "body": pull.body,
        "created_at": _iso(pull.created_at),
        "updated_at": _iso(pull.updated_at),
        "state": _github_state(pull),
        "url": pull.html_url,
        "draft": bool(getattr(pull, "draft", False)),
        "labels": _safe(lambda: [label.name for label in pull.labels]) or [],
        "base_ref": _safe(lambda: pull.base.ref) or "main",
        "head_ref": _safe(lambda: pull.head.ref),
        "head_sha": _safe(lambda: pull.head.sha),
        "additions": _safe_int(lambda: pull.additions),
        "deletions": _safe_int(lambda: pull.deletions),
        "changed_files": _safe_int(lambda: pull.changed_files),
        "author_avatar": avatar,
    }


# --------------------------------------------------------------------------- #
# GitLab
# --------------------------------------------------------------------------- #
class GitLab:
    id = "gitlab"
    label = "GitLab"

    def _base(self, repo, settings=None):
        api = ((settings or {}).get("gitlab_api_url") or "").strip().rstrip("/")
        if not api:
            api = f"https://{repo['host']}/api/v4"
        return f"{api}/projects/{quote(repo['full_name'], safe='')}"

    def _request(self, url, token, params=None):
        headers = {"PRIVATE-TOKEN": token} if token else {}
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response

    def _get_all(self, url, token, params=None):
        results = []
        page = "1"
        while page:
            query = dict(params or {})
            query["page"] = page
            response = self._request(url, token, query)
            data = response.json()
            if not isinstance(data, list):
                break
            results.extend(data)
            page = response.headers.get("X-Next-Page") or ""
            if len(results) > 2000:
                break
        return results

    def clone_url(self, repo, token, settings=None):
        if token:
            return f"https://oauth2:{token}@{repo['host']}/{repo['full_name']}.git"
        return f"https://{repo['host']}/{repo['full_name']}.git"

    def head_ref(self, number):
        return f"refs/merge-requests/{number}/head"

    def fetch_resources(self, repo, token, settings=None):
        try:
            # Fetch every state so requests that have since been closed or merged
            # are updated instead of lingering as "open" in storage.
            data = self._get_all(
                f"{self._base(repo, settings)}/merge_requests",
                token,
                {"state": "all", "order_by": "created_at", "sort": "asc", "per_page": 100},
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Error fetching MRs for {repo['slug']}: {exc}")
            return []
        return [_gitlab_entry(mr, repo) for mr in data]

    def fetch_comments(self, repo, number, token, settings=None):
        try:
            notes = self._get_all(
                f"{self._base(repo, settings)}/merge_requests/{number}/notes",
                token,
                {"per_page": 100, "sort": "asc"},
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Error fetching notes for {repo['slug']} !{number}: {exc}")
            return []
        comments = []
        for note in notes:
            if note.get("system"):
                continue
            comments.append({
                "id": note.get("id"),
                "user": (note.get("author") or {}).get("username"),
                "body": note.get("body"),
                "created_at": note.get("created_at"),
            })
        return comments

    def fetch_commits(self, repo, number, token, settings=None):
        try:
            data = self._get_all(
                f"{self._base(repo, settings)}/merge_requests/{number}/commits",
                token,
                {"per_page": 100},
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Error fetching commits for {repo['slug']} !{number}: {exc}")
            return []
        commits = []
        for commit in data[:MAX_COMMITS]:
            sha = commit.get("id") or ""
            commits.append({
                "sha": sha,
                "short_sha": commit.get("short_id") or sha[:7],
                "message": commit.get("message") or commit.get("title") or "",
                "author_name": commit.get("author_name"),
                "author_login": None,
                "author_avatar": None,
                "date": commit.get("created_at"),
                "url": commit.get("web_url"),
            })
        return commits

    def fetch_files(self, repo, number, token, settings=None):
        try:
            response = self._request(
                f"{self._base(repo, settings)}/merge_requests/{number}/changes",
                token,
            )
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"Error fetching changes for {repo['slug']} !{number}: {exc}")
            return []
        files = []
        for change in (data.get("changes") or [])[:MAX_FILES]:
            diff = change.get("diff")
            additions, deletions = _diff_stats(diff)
            if change.get("new_file"):
                status = "added"
            elif change.get("deleted_file"):
                status = "removed"
            elif change.get("renamed_file"):
                status = "renamed"
            else:
                status = "modified"
            old_path = change.get("old_path")
            new_path = change.get("new_path")
            files.append({
                "filename": new_path or old_path,
                "previous_filename": old_path if status == "renamed" else None,
                "status": status,
                "additions": additions,
                "deletions": deletions,
                "changes": additions + deletions,
                "patch": diff,
                "blob_url": None,
            })
        return files


def _diff_stats(text):
    """Count added/removed lines in a unified diff (ignoring the +++/--- header)."""
    additions = deletions = 0
    for line in (text or "").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return additions, deletions


def _gitlab_entry(mr, repo):
    author = mr.get("author") or {}
    title = mr.get("title") or ""
    draft = bool(mr.get("draft") or mr.get("work_in_progress"))
    if not draft:
        lowered = title.lower()
        draft = lowered.startswith(("draft:", "wip:"))
    changed = mr.get("changes_count")
    try:
        changed_files = int(changed) if changed is not None else None
    except (TypeError, ValueError):
        changed_files = None
    return {
        "id": mr.get("id"),
        "repo": repo["full_name"],
        "slug": repo["slug"],
        "provider": repo["provider"],
        "host": repo["host"],
        "number": mr.get("iid"),
        "title": title,
        "user": author.get("username"),
        "body": mr.get("description"),
        "created_at": mr.get("created_at"),
        "updated_at": mr.get("updated_at"),
        "state": STATE_MAP.get(mr.get("state"), mr.get("state")),
        "url": mr.get("web_url"),
        "draft": draft,
        "labels": mr.get("labels") or [],
        "base_ref": mr.get("target_branch") or "main",
        "head_ref": mr.get("source_branch"),
        "head_sha": mr.get("sha"),
        "additions": None,
        "deletions": None,
        "changed_files": changed_files,
        "author_avatar": author.get("avatar_url"),
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value is not None else None)


def _safe(fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None


def _safe_int(fn):
    value = _safe(fn)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


PROVIDERS = {
    "github": GitHub(),
    "gitlab": GitLab(),
}
