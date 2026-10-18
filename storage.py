"""SQLite-backed storage for pr-reviewer.

Everything lives in a single project-local folder (``DATA_DIR``)::

    data/
        settings.json     application settings (github token, poll interval)
        pr_reviewer.db    SQLite database with repos, pull_requests and comments

The folder can be overridden with the ``DATA_DIR`` environment variable. The
old JSON dump in ``/tmp`` is migrated automatically on first start.
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
DB_PATH = os.path.join(DATA_DIR, "pr_reviewer.db")

# Location used by older versions of the app, kept only for one-time migration.
LEGACY_DATA_PATH = "/tmp/pr-reviewer-data.json"

DEFAULT_SETTINGS = {
    # Hosting providers
    "github_token": "",
    "github_url": "https://github.com",
    "github_api_url": "",
    "gitlab_token": "",
    "gitlab_url": "https://gitlab.com",
    "gitlab_api_url": "",
    # Agents
    "default_agent": "",
    "default_model": "",
    "custom_command": "",
    "agent_commands": {},
    "agent_binaries": {},
    "agent_model_commands": {},
    # Review prompt
    "review_prompt": "",
    # Limits
    "review_timeout": 900,
    "max_prompt_chars": 400000,
    "max_description_chars": 8000,
    # Watching for new pull requests
    "watch_interval": 60,
    # Web server
    "host": "0.0.0.0",
    "port": 5000,
}

# Settings a single repository may override. Everything else is global; the
# values in ``DEFAULT_SETTINGS`` (edited in the global Settings dialog) are the
# fallback for any repository that does not override a key.
REPO_SETTINGS = (
    "review_prompt",
    "default_agent",
    "default_model",
    "review_timeout",
    "max_prompt_chars",
    "max_description_chars",
)
# The subset of ``REPO_SETTINGS`` that is numeric.
REPO_INT_SETTINGS = ("review_timeout", "max_prompt_chars", "max_description_chars")

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name  TEXT NOT NULL,
    provider   TEXT NOT NULL DEFAULT 'github',
    host       TEXT NOT NULL DEFAULT 'github.com',
    slug       TEXT,
    watch      INTEGER NOT NULL DEFAULT 0,
    settings   TEXT,
    added_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pull_requests (
    id            INTEGER PRIMARY KEY,
    repo_id       INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    full_name     TEXT NOT NULL,
    slug          TEXT,
    provider      TEXT,
    host          TEXT,
    number        INTEGER NOT NULL,
    title         TEXT,
    user          TEXT,
    body          TEXT,
    state         TEXT,
    url           TEXT,
    created_at    TEXT,
    updated_at    TEXT,
    draft         INTEGER DEFAULT 0,
    labels        TEXT DEFAULT '[]',
    base_ref      TEXT,
    head_ref      TEXT,
    additions     INTEGER,
    deletions     INTEGER,
    changed_files INTEGER,
    author_avatar TEXT,
    UNIQUE (repo_id, number)
);

CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY,
    pr_id      INTEGER NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    user       TEXT,
    body       TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id       INTEGER NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    repo        TEXT NOT NULL,
    number      INTEGER NOT NULL,
    agent       TEXT NOT NULL,
    model       TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    prompt      TEXT,
    command     TEXT,
    workspace   TEXT,
    output      TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL,
    finished_at TEXT,
    duration_ms INTEGER
);

-- Pull requests the user has cleared from the "AI Reviewed" sidebar list.
-- Membership of that list is derived from the reviews table; this only records
-- the ones the user removed, so a fresh review brings the request back.
CREATE TABLE IF NOT EXISTS dismissed_reviews (
    pr_id        INTEGER PRIMARY KEY REFERENCES pull_requests(id) ON DELETE CASCADE,
    dismissed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id      INTEGER REFERENCES pull_requests(id) ON DELETE CASCADE,
    repo       TEXT,
    slug       TEXT,
    number     INTEGER,
    title      TEXT,
    url        TEXT,
    created_at TEXT NOT NULL,
    seen       INTEGER NOT NULL DEFAULT 0
);
"""

# Indexes are created after column migrations so they can reference new columns.
INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_repos_slug ON repos(slug);
CREATE INDEX IF NOT EXISTS idx_pull_requests_repo ON pull_requests(repo_id);
CREATE INDEX IF NOT EXISTS idx_pull_requests_slug ON pull_requests(slug);
CREATE INDEX IF NOT EXISTS idx_comments_pr ON comments(pr_id);
CREATE INDEX IF NOT EXISTS idx_reviews_pr ON reviews(pr_id);
CREATE INDEX IF NOT EXISTS idx_notifications_seen ON notifications(seen);
"""

# Columns added after the first release; applied to existing databases too.
_EXTRA_REPO_COLUMNS = {
    "provider": "TEXT DEFAULT 'github'",
    "host": "TEXT DEFAULT 'github.com'",
    "slug": "TEXT",
    "watch": "INTEGER NOT NULL DEFAULT 0",
    "settings": "TEXT",
}

_EXTRA_PR_COLUMNS = {
    "slug": "TEXT",
    "provider": "TEXT",
    "host": "TEXT",
    "draft": "INTEGER DEFAULT 0",
    "labels": "TEXT DEFAULT '[]'",
    "base_ref": "TEXT",
    "head_ref": "TEXT",
    "additions": "INTEGER",
    "deletions": "INTEGER",
    "changed_files": "INTEGER",
    "author_avatar": "TEXT",
}

_init_lock = threading.Lock()
_initialized = False


def _now():
    return datetime.now(timezone.utc).isoformat()


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


@contextmanager
def get_conn():
    """Open a connection to the SQLite database, committing on success."""
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create the data folder and schema. Safe to call multiple times."""
    global _initialized
    with _init_lock:
        if _initialized:
            return
        ensure_data_dir()
        with get_conn() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            _ensure_columns(conn, "repos", _EXTRA_REPO_COLUMNS)
            _ensure_columns(conn, "pull_requests", _EXTRA_PR_COLUMNS)
            _backfill_provider_columns(conn)
            conn.executescript(INDEXES)
        _initialized = True


def _ensure_columns(conn, table, columns):
    """Add columns that were introduced after the initial schema."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, decl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def _backfill_provider_columns(conn):
    """Populate provider/host/slug for rows created before multi-host support."""
    conn.execute("UPDATE repos SET provider = 'github' WHERE provider IS NULL OR provider = ''")
    conn.execute("UPDATE repos SET host = 'github.com' WHERE host IS NULL OR host = ''")
    conn.execute("UPDATE repos SET slug = host || '/' || full_name WHERE slug IS NULL OR slug = ''")
    conn.execute("UPDATE pull_requests SET provider = 'github' WHERE provider IS NULL OR provider = ''")
    conn.execute("UPDATE pull_requests SET host = 'github.com' WHERE host IS NULL OR host = ''")
    conn.execute(
        "UPDATE pull_requests SET slug = host || '/' || full_name WHERE slug IS NULL OR slug = ''"
    )
    # Rows stored before states were tracked were all open requests; default
    # them so the "Open" tab and the per-state counts agree.
    conn.execute("UPDATE pull_requests SET state = 'open' WHERE state IS NULL OR state = ''")


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
def load_settings():
    """Return application settings from ``settings.json``.

    Settings are owned by ``data/settings.json`` and edited in the web UI; no
    environment variables override them. Only ``DATA_DIR`` (which locates this
    file) is still read from the environment.
    """
    ensure_data_dir()
    settings = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f) or {}
            if isinstance(stored, dict):
                settings.update(stored)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Warning: could not read settings ({SETTINGS_PATH}): {exc}")
    return settings


def save_settings(settings):
    """Persist settings atomically."""
    ensure_data_dir()
    payload = dict(DEFAULT_SETTINGS)
    payload.update(settings or {})
    tmp_path = SETTINGS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, SETTINGS_PATH)
    return payload


# --------------------------------------------------------------------------- #
# Repositories
# --------------------------------------------------------------------------- #
def _slug(host, full_name):
    return f"{host}/{full_name}"


def _load_repo_settings(raw):
    """Parse a repository's JSON settings overrides, tolerating bad data."""
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _repo_dict(row):
    """A repository row as a dict, with its settings overrides parsed."""
    keys = row.keys()
    watch = bool(row["watch"]) if "watch" in keys else False
    return {
        "full_name": row["full_name"],
        "provider": row["provider"] if "provider" in keys and row["provider"] else "github",
        "host": row["host"] if "host" in keys and row["host"] else "github.com",
        "slug": row["slug"] if "slug" in keys and row["slug"] else None,
        "watch": watch,
        "settings": _load_repo_settings(row["settings"]) if "settings" in keys else {},
    }


def add_repo(full_name, provider="github", host="github.com"):
    """Add a single repository. Returns True when it was newly inserted."""
    return add_repos([full_name], provider=provider, host=host) > 0


def add_repos(full_names, provider="github", host="github.com"):
    """Add several repositories in one transaction. Returns the count added.

    Each entry may be a plain ``owner/repo`` string or a dict with
    ``full_name``/``provider``/``host`` keys.
    """
    added = 0
    with get_conn() as conn:
        for item in full_names or []:
            if isinstance(item, dict):
                full_name = (item.get("full_name") or "").strip()
                repo_provider = item.get("provider") or provider
                repo_host = item.get("host") or host
            else:
                full_name = (item or "").strip()
                repo_provider = provider
                repo_host = host
            if not full_name:
                continue
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO repos (full_name, provider, host, slug, added_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (full_name, repo_provider, repo_host, _slug(repo_host, full_name), _now()),
            )
            added += cur.rowcount
    return added


def remove_repo(slug):
    """Remove a repository and all of its stored PRs (cascade)."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM repos WHERE slug = ? OR full_name = ?", (slug, slug))
        return cur.rowcount > 0


def list_repos():
    """Every repository as a record (slug, full_name, provider, host, watch, settings)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT full_name, provider, host, slug, watch, settings "
            "FROM repos ORDER BY full_name"
        ).fetchall()
    return [_repo_dict(row) for row in rows]


def list_repo_slugs():
    return [repo["slug"] for repo in list_repos()]


def get_repo(slug):
    """One repository by its unique slug (``<host>/<owner>/<repo>``)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT full_name, provider, host, slug, watch, settings "
            "FROM repos WHERE slug = ?",
            (slug,),
        ).fetchone()
    return _repo_dict(row) if row else None


def set_repo_settings(slug, overrides):
    """Replace one repository's settings overrides. Returns True if it existed.

    Matches by slug only: a bare ``owner/repo`` is not unique, since the same
    path may exist on two hosts.
    """
    payload = json.dumps(overrides or {})
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE repos SET settings = ? WHERE slug = ?", (payload, slug)
        )
        return cur.rowcount > 0


def set_repo_watch(slug, watch):
    """Turn new-PR watching on/off for a repository. Returns True if it existed."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE repos SET watch = ? WHERE slug = ? OR full_name = ?",
            (1 if watch else 0, slug, slug),
        )
        return cur.rowcount > 0


def repo_stats():
    """Return every repository with the number of stored pull requests.

    ``count`` is the total stored for the repo; ``open_count`` is how many are
    still open, which is what the sidebar badge shows now that closed and merged
    requests are kept too.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.full_name AS full_name, r.provider AS provider,
                   r.host AS host, r.slug AS slug, r.watch AS watch,
                   r.settings AS settings,
                   COUNT(p.id) AS count,
                   COUNT(CASE WHEN p.state = 'open' THEN 1 END) AS open_count
            FROM repos r
            LEFT JOIN pull_requests p ON p.repo_id = r.id
            GROUP BY r.id
            ORDER BY r.full_name
            """
        ).fetchall()
    return [_repo_dict(row) | {"count": row["count"], "open_count": row["open_count"]}
            for row in rows]


def _get_or_create_repo(conn, full_name, provider="github", host="github.com"):
    slug = _slug(host, full_name)
    row = conn.execute("SELECT id FROM repos WHERE slug = ?", (slug,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO repos (full_name, provider, host, slug, added_at) VALUES (?, ?, ?, ?, ?)",
        (full_name, provider, host, slug, _now()),
    )
    return cur.lastrowid


# --------------------------------------------------------------------------- #
# Pull requests
# --------------------------------------------------------------------------- #
def existing_pr_ids():
    """Set of GitHub PR ids already stored (used to skip known pull requests)."""
    with get_conn() as conn:
        rows = conn.execute("SELECT id FROM pull_requests").fetchall()
    return {row["id"] for row in rows}


def existing_pr_meta():
    """Map of stored PR id -> updated_at, used to detect changed pull requests."""
    with get_conn() as conn:
        rows = conn.execute("SELECT id, updated_at FROM pull_requests").fetchall()
    return {row["id"]: row["updated_at"] for row in rows}


def existing_pr_states():
    """Map of stored PR id -> state, used to spot open -> closed/merged changes."""
    with get_conn() as conn:
        rows = conn.execute("SELECT id, state FROM pull_requests").fetchall()
    return {row["id"]: row["state"] for row in rows}


def save_pr(pr, comments=None):
    """Insert or update a pull request and its comments."""
    labels = pr.get("labels")
    if not isinstance(labels, str):
        labels = json.dumps(list(labels or []))
    draft = 1 if pr.get("draft") else 0
    provider = pr.get("provider") or "github"
    host = pr.get("host") or "github.com"
    slug = pr.get("slug") or _slug(host, pr["repo"])

    with get_conn() as conn:
        repo_id = _get_or_create_repo(conn, pr["repo"], provider, host)
        conn.execute(
            """
            INSERT INTO pull_requests
                (id, repo_id, full_name, slug, provider, host, number, title, user,
                 body, state, url, created_at, updated_at, draft, labels, base_ref,
                 head_ref, additions, deletions, changed_files, author_avatar)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                title         = excluded.title,
                body          = excluded.body,
                state         = excluded.state,
                url           = excluded.url,
                updated_at    = excluded.updated_at,
                draft         = excluded.draft,
                labels        = excluded.labels,
                base_ref      = excluded.base_ref,
                head_ref      = excluded.head_ref,
                additions     = excluded.additions,
                deletions     = excluded.deletions,
                changed_files = excluded.changed_files,
                author_avatar = excluded.author_avatar
            """,
            (
                pr["id"], repo_id, pr["repo"], slug, provider, host, pr.get("number"),
                pr.get("title"), pr.get("user"), pr.get("body"), pr.get("state"),
                pr.get("url"), pr.get("created_at"), pr.get("updated_at"), draft,
                labels, pr.get("base_ref"), pr.get("head_ref"), pr.get("additions"),
                pr.get("deletions"), pr.get("changed_files"), pr.get("author_avatar"),
            ),
        )
        for comment in comments or []:
            conn.execute(
                """
                INSERT INTO comments (id, pr_id, user, body, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    body = excluded.body
                """,
                (
                    comment["id"], pr["id"], comment.get("user"),
                    comment.get("body"), comment.get("created_at"),
                ),
            )


def get_pr(pr_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM pull_requests WHERE id = ?", (pr_id,)).fetchone()
        if row is None:
            return None
        comment_rows = conn.execute(
            "SELECT * FROM comments WHERE pr_id = ? ORDER BY created_at ASC", (pr_id,)
        ).fetchall()
    return _pr_dict(row, [_comment_dict(c) for c in comment_rows])


def list_prs(repo=None, state=None):
    """Return stored pull requests (newest first).

    Optionally narrowed to one repo slug and/or one state (``open``, ``closed``,
    ``merged``); ``state="all"`` (or ``None``) does not filter by state.
    """
    where = []
    params = []
    if repo:
        where.append("(slug = ? OR full_name = ?)")
        params.extend((repo, repo))
    if state and state != "all":
        where.append("state = ?")
        params.append(state)
    clause = f" WHERE {' AND '.join(where)}" if where else ""

    with get_conn() as conn:
        pr_rows = conn.execute(
            f"SELECT * FROM pull_requests{clause} ORDER BY created_at DESC", params
        ).fetchall()
        comment_rows = []
        if pr_rows:
            pr_ids = [row["id"] for row in pr_rows]
            placeholders = ",".join("?" for _ in pr_ids)
            comment_rows = conn.execute(
                f"SELECT * FROM comments WHERE pr_id IN ({placeholders}) "
                "ORDER BY created_at ASC",
                pr_ids,
            ).fetchall()

    comments = {}
    for row in comment_rows:
        comments.setdefault(row["pr_id"], []).append(_comment_dict(row))
    return [_pr_dict(row, comments.get(row["id"], [])) for row in pr_rows]


def count_prs(repo=None, state=None):
    """Count stored pull requests, optionally for one repo and/or state."""
    where = []
    params = []
    if repo:
        where.append("(slug = ? OR full_name = ?)")
        params.extend((repo, repo))
    if state and state != "all":
        where.append("state = ?")
        params.append(state)
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM pull_requests{clause}", params
        ).fetchone()
    return row["n"]


def pr_state_counts(repo=None):
    """Number of stored pull requests per state, plus an ``all`` total.

    Used to label the status tabs in the UI. Any unrecognised state is folded
    into its own key rather than being dropped.
    """
    where = ""
    params = []
    if repo:
        where = " WHERE slug = ? OR full_name = ?"
        params = [repo, repo]
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT state, COUNT(*) AS n FROM pull_requests{where} GROUP BY state",
            params,
        ).fetchall()

    counts = {"open": 0, "closed": 0, "merged": 0}
    total = 0
    for row in rows:
        total += row["n"]
        key = row["state"] or "open"
        counts[key] = counts.get(key, 0) + row["n"]
    counts["all"] = total
    return counts


def _load_labels(raw):
    if not raw:
        return []
    try:
        labels = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return labels if isinstance(labels, list) else []


def _pr_dict(row, comments):
    keys = row.keys()
    full_name = row["full_name"]
    host = row["host"] if "host" in keys and row["host"] else "github.com"
    return {
        "id": row["id"],
        "repo": full_name,
        "slug": row["slug"] if "slug" in keys and row["slug"] else f"{host}/{full_name}",
        "provider": row["provider"] if "provider" in keys and row["provider"] else "github",
        "host": host,
        "number": row["number"],
        "title": row["title"],
        "user": row["user"],
        "body": row["body"],
        "state": row["state"],
        "url": row["url"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "draft": bool(row["draft"]) if "draft" in keys else False,
        "labels": _load_labels(row["labels"]) if "labels" in keys else [],
        "base_ref": row["base_ref"] if "base_ref" in keys else None,
        "head_ref": row["head_ref"] if "head_ref" in keys else None,
        "additions": row["additions"] if "additions" in keys else None,
        "deletions": row["deletions"] if "deletions" in keys else None,
        "changed_files": row["changed_files"] if "changed_files" in keys else None,
        "author_avatar": row["author_avatar"] if "author_avatar" in keys else None,
        "comments": comments,
    }


def _comment_dict(row):
    return {
        "id": row["id"],
        "user": row["user"],
        "body": row["body"],
        "created_at": row["created_at"],
    }


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #
# Keep the table from growing without bound; only the newest are ever shown.
NOTIFICATION_LIMIT = 200


def add_notification(pr):
    """Record a new-pull-request notification. Returns its id."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO notifications (pr_id, repo, slug, number, title, url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pr.get("id"), pr.get("repo"), pr.get("slug"), pr.get("number"),
                pr.get("title"), pr.get("url"), _now(),
            ),
        )
        conn.execute(
            "DELETE FROM notifications WHERE id NOT IN "
            "(SELECT id FROM notifications ORDER BY id DESC LIMIT ?)",
            (NOTIFICATION_LIMIT,),
        )
        return cur.lastrowid


def list_notifications(unseen_only=False, limit=50):
    """Newest last, optionally only the ones the UI has not seen yet."""
    query = "SELECT * FROM notifications"
    if unseen_only:
        query += " WHERE seen = 0"
    query += " ORDER BY id ASC LIMIT ?"
    with get_conn() as conn:
        rows = conn.execute(query, (limit,)).fetchall()
    return [_notification_dict(row) for row in rows]


def mark_notifications_seen(ids=None):
    """Mark specific notifications seen, or all of them when ``ids`` is empty."""
    with get_conn() as conn:
        if ids:
            placeholders = ",".join("?" for _ in ids)
            cur = conn.execute(
                f"UPDATE notifications SET seen = 1 WHERE id IN ({placeholders})",
                list(ids),
            )
        else:
            cur = conn.execute("UPDATE notifications SET seen = 1 WHERE seen = 0")
        return cur.rowcount


def _notification_dict(row):
    return {
        "id": row["id"],
        "pr_id": row["pr_id"],
        "repo": row["repo"],
        "slug": row["slug"],
        "number": row["number"],
        "title": row["title"],
        "url": row["url"],
        "created_at": row["created_at"],
        "seen": bool(row["seen"]),
    }


# --------------------------------------------------------------------------- #
# Reviews
# --------------------------------------------------------------------------- #
REVIEW_FIELDS = {
    "status", "prompt", "command", "workspace", "output", "error",
    "finished_at", "duration_ms", "model", "agent",
}


def create_review(pr_id, repo, number, agent, model, prompt=None):
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO reviews (pr_id, repo, number, agent, model, status, prompt, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (pr_id, repo, number, agent, model or None, prompt, _now()),
        )
        # A new review surfaces the pull request in the "AI Reviewed" list again,
        # even if the user had previously cleared it.
        conn.execute("DELETE FROM dismissed_reviews WHERE pr_id = ?", (pr_id,))
        return cur.lastrowid


def update_review(review_id, **fields):
    updates = {k: v for k, v in fields.items() if k in REVIEW_FIELDS}
    if not updates:
        return False
    assignments = ", ".join(f"{k} = ?" for k in updates)
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE reviews SET {assignments} WHERE id = ?",
            (*updates.values(), review_id),
        )
        return cur.rowcount > 0


def get_review(review_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    return _review_dict(row) if row else None


def list_reviews(pr_id, limit=20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reviews WHERE pr_id = ? ORDER BY id DESC LIMIT ?",
            (pr_id, limit),
        ).fetchall()
    return [_review_dict(row) for row in rows]


def _review_dict(row):
    return {
        "id": row["id"],
        "pr_id": row["pr_id"],
        "repo": row["repo"],
        "number": row["number"],
        "agent": row["agent"],
        "model": row["model"],
        "status": row["status"],
        "prompt": row["prompt"],
        "command": row["command"],
        "workspace": row["workspace"],
        "output": row["output"],
        "error": row["error"],
        "created_at": row["created_at"],
        "finished_at": row["finished_at"],
        "duration_ms": row["duration_ms"],
    }


# --------------------------------------------------------------------------- #
# AI-reviewed pull requests (the sidebar list)
# --------------------------------------------------------------------------- #
def dismiss_review(pr_id):
    """Hide a pull request from the "AI Reviewed" list. False if it is unknown."""
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM pull_requests WHERE id = ?", (pr_id,)
        ).fetchone()
        if not exists:
            return False
        conn.execute(
            """
            INSERT INTO dismissed_reviews (pr_id, dismissed_at) VALUES (?, ?)
            ON CONFLICT (pr_id) DO UPDATE SET dismissed_at = excluded.dismissed_at
            """,
            (pr_id, _now()),
        )
        return True


def archive_review(pr_id):
    """Archive a *reviewed* pull request from the "AI Reviewed" list.

    Only requests that have at least one review are in the list, so a request
    with no reviews is left untouched. Archiving is the same dismissal the
    sidebar's remove button writes: the request is hidden, its review history is
    kept, and starting a new review brings it back. Returns True when the request
    has a review (whether or not it was already archived).
    """
    with get_conn() as conn:
        reviewed = conn.execute(
            "SELECT 1 FROM reviews WHERE pr_id = ? LIMIT 1", (pr_id,)
        ).fetchone()
        if not reviewed:
            return False
        conn.execute(
            """
            INSERT INTO dismissed_reviews (pr_id, dismissed_at) VALUES (?, ?)
            ON CONFLICT (pr_id) DO UPDATE SET dismissed_at = excluded.dismissed_at
            """,
            (pr_id, _now()),
        )
        return True


def list_reviewed_prs(limit=50):
    """Pull requests that have been reviewed and not dismissed, newest first.

    Membership comes from the ``reviews`` table, so existing reviews show up
    automatically. The most recent review supplies the status/agent shown in the
    sidebar; ``dismissed_reviews`` hides requests the user is done with.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT p.id            AS pr_id,
                   p.number        AS number,
                   p.title         AS title,
                   p.full_name     AS full_name,
                   p.slug          AS slug,
                   p.host          AS host,
                   p.state         AS state,
                   p.draft         AS draft,
                   p.url           AS url,
                   r.status        AS status,
                   r.agent         AS agent,
                   r.model         AS model,
                   r.error         AS error,
                   r.created_at    AS review_created_at,
                   r.finished_at   AS finished_at
            FROM pull_requests p
            JOIN (
                SELECT pr_id, MAX(id) AS review_id
                FROM reviews
                GROUP BY pr_id
            ) latest ON latest.pr_id = p.id
            JOIN reviews r ON r.id = latest.review_id
            LEFT JOIN dismissed_reviews d ON d.pr_id = p.id
            WHERE d.pr_id IS NULL
            ORDER BY r.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------- #
# Migration
# --------------------------------------------------------------------------- #
def migrate_legacy_data(path=None, remove_source=False):
    """Import the old JSON dump, once.

    Returns the number of pull requests imported.
    """
    path = path or LEGACY_DATA_PATH
    imported = 0

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Warning: could not read legacy data ({path}): {exc}")
            data = None

        for pr in data or []:
            if not isinstance(pr, dict) or "id" not in pr or not pr.get("repo"):
                continue
            add_repo(pr["repo"])
            save_pr(pr, pr.get("comments", []))
            imported += 1

        if imported and remove_source:
            try:
                os.replace(path, path + ".migrated")
            except OSError:
                pass

    return imported
