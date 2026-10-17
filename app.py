"""PR Reviewer - a Flask app for reviewing GitHub and GitLab merge requests
with local coding-agent CLIs.

It lists open pull/merge requests, and on demand clones a repository, checks out
the request and runs an installed agent (opencode, pi, claude, copilot, ...) to
produce a review.

Data lives in ``DATA_DIR`` (default ``./data``); see ``storage.py``. Hosting
providers are in ``providers.py``, agents in ``agents.py`` and the review
orchestration in ``reviewer.py``.
"""

import threading
import time

from flask import Flask, jsonify, render_template, request

import agents
import providers
import reviewer
import storage

app = Flask(__name__)

# Settings fields the UI can edit, grouped by type.
TEXT_SETTINGS = (
    "github_token", "github_url", "github_api_url",
    "gitlab_token", "gitlab_url", "gitlab_api_url",
    "default_agent", "default_model", "custom_command",
    "review_prompt", "host",
)
INT_SETTINGS = (
    "review_timeout", "max_prompt_chars", "max_description_chars",
    "watch_interval", "port",
)
DICT_SETTINGS = ("agent_commands", "agent_binaries", "agent_model_commands")

# The watcher never polls faster than this, whatever ``watch_interval`` says.
WATCH_MIN_INTERVAL = 15

# Serializes syncs so the background watcher and a manual "Sync PRs" click
# never fetch the same providers at the same time.
_sync_lock = threading.Lock()
_watch_thread = None


def _as_int(value, default):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def get_settings():
    """Load settings with consistent types."""
    settings = storage.load_settings()
    for key in TEXT_SETTINGS:
        settings[key] = str(settings.get(key) or "")
    for key in INT_SETTINGS:
        settings[key] = _as_int(settings.get(key), storage.DEFAULT_SETTINGS[key])
    for key in DICT_SETTINGS:
        value = settings.get(key)
        settings[key] = value if isinstance(value, dict) else {}
    return settings


def settings_payload():
    """Settings as sent to the UI: tokens masked, defaults included."""
    settings = get_settings()
    settings["github_token"] = "***" if settings["github_token"] else ""
    settings["gitlab_token"] = "***" if settings["gitlab_token"] else ""
    settings["default_review_prompt"] = reviewer.DEFAULT_REVIEW_PROMPT
    settings["defaults"] = {key: storage.DEFAULT_SETTINGS[key] for key in storage.DEFAULT_SETTINGS}
    return settings


# Human-readable labels for the review statuses shown in the sidebar list.
REVIEW_STATUS_LABELS = {
    "pending": "Queued",
    "preparing": "Preparing",
    "running": "Running",
    "done": "Reviewed",
    "error": "Failed",
}


def reviewed_prs_payload():
    """AI-reviewed pull requests with a display label for their latest status."""
    items = storage.list_reviewed_prs()
    for item in items:
        status = item.get("status") or "pending"
        item["status_label"] = REVIEW_STATUS_LABELS.get(status, status.title())
    return items


def sync_repos(only_watched=False):
    """Fetch open pull/merge requests from every repository's provider.

    New requests in a *watched* repository are queued as notifications, unless
    the repository is being synced for the very first time (everything would
    look new then). Returns the sync summary; when new watched requests were
    found, ``notifications`` carries them for immediate display.
    """
    if not _sync_lock.acquire(blocking=False):
        return {"new_prs": 0, "total_prs": storage.count_prs(), "busy": True}

    try:
        settings = get_settings()
        known = storage.existing_pr_meta()
        new_prs = 0
        notifications = []

        for repo in storage.list_repos():
            if only_watched and not repo["watch"]:
                continue

            # First sync of a repository is a baseline: store, but don't alert.
            first_sync = storage.count_prs(repo["slug"]) == 0

            provider = providers.get_provider(repo["provider"])
            token = providers.token_for(repo["provider"], settings)
            try:
                entries = provider.fetch_resources(repo, token, settings)
            except Exception as exc:  # noqa: BLE001
                print(f"Error fetching resources for {repo['slug']}: {exc}")
                continue

            for entry in entries:
                if entry.get("id") is None:
                    continue
                is_new = entry["id"] not in known
                if is_new or known.get(entry["id"]) != entry.get("updated_at"):
                    comments = provider.fetch_comments(repo, entry["number"], token, settings)
                    storage.save_pr(entry, comments)
                    if is_new:
                        new_prs += 1
                        if repo["watch"] and not first_sync:
                            notifications.append(entry)
                else:
                    storage.save_pr(entry)
                known[entry["id"]] = entry.get("updated_at")

        for entry in notifications:
            storage.add_notification(entry)

        payload = {"new_prs": new_prs, "total_prs": storage.count_prs()}
        if notifications:
            payload["notifications"] = [
                {
                    "pr_id": entry["id"],
                    "repo": entry.get("repo"),
                    "slug": entry.get("slug"),
                    "number": entry.get("number"),
                    "title": entry.get("title"),
                    "url": entry.get("url"),
                }
                for entry in notifications
            ]
        return payload
    finally:
        _sync_lock.release()


def _watch_interval(settings):
    return max(
        WATCH_MIN_INTERVAL,
        _as_int(settings.get("watch_interval"), storage.DEFAULT_SETTINGS["watch_interval"]),
    )


def _watch_loop():
    """Poll watched repositories for new pull/merge requests, forever."""
    while True:
        interval = _watch_interval(get_settings())
        time.sleep(interval)
        try:
            sync_repos(only_watched=True)
        except Exception as exc:  # noqa: BLE001 - the loop must keep running
            print(f"Warning: background watch sync failed: {exc}")


def start_watcher():
    """Start the background watcher once (a no-op if it is already running)."""
    global _watch_thread
    if _watch_thread is not None and _watch_thread.is_alive():
        return
    _watch_thread = threading.Thread(target=_watch_loop, name="pr-watcher", daemon=True)
    _watch_thread.start()


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    repos = storage.repo_stats()
    selected_slug = request.args.get("repo") or None
    selected = None
    if selected_slug:
        selected = next((r for r in repos if r["slug"] == selected_slug), None)
        if selected is None:
            selected_slug = None

    settings = settings_payload()
    return render_template(
        "index.html",
        repos=repos,
        selected=selected,
        selected_slug=selected_slug,
        pr_data=storage.list_prs(selected_slug),
        total_prs=storage.count_prs(),
        repo_total=storage.count_prs(selected_slug),
        reviewed=reviewed_prs_payload(),
        settings=settings,
        agents=agents.detect_agents(settings),
        default_review_prompt=reviewer.DEFAULT_REVIEW_PROMPT,
    )


@app.route("/api/sync", methods=["GET", "POST"])
def api_sync():
    """Fetch open pull/merge requests on demand."""
    return jsonify(sync_repos())


@app.route("/api/prs")
def api_prs():
    """Read the stored pull requests without contacting any provider."""
    repo = request.args.get("repo") or None
    return jsonify({"prs": storage.list_prs(repo), "total": storage.count_prs(repo)})


@app.route("/api/repos", methods=["GET", "POST"])
def api_repos():
    """List or add repositories (GitHub or GitLab)."""
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        settings = get_settings()
        default_provider = data.get("provider") or "github"
        hosts = providers.provider_hosts(settings)
        records, errors = [], []
        for item in data.get("repos", []):
            try:
                records.append(providers.parse_repo(item, default_provider, hosts))
            except ValueError as exc:
                errors.append(f"{item}: {exc}")
        added = storage.add_repos(records)
        payload = {"added": added, "repos": storage.repo_stats()}
        if errors:
            payload["errors"] = errors
        return jsonify(payload)
    return jsonify({"repos": storage.repo_stats()})


@app.route("/api/repos/<path:slug>", methods=["DELETE"])
def api_repo_delete(slug):
    if storage.remove_repo(slug):
        return jsonify({"removed": slug, "repos": storage.repo_stats()})
    return jsonify({"error": "repo not found"}), 404


@app.route("/api/repos/<path:slug>/watch", methods=["POST"])
def api_repo_watch(slug):
    """Turn new-PR watching on/off for one repository."""
    data = request.get_json(silent=True) or {}
    watch = bool(data.get("watch"))
    if storage.set_repo_watch(slug, watch):
        return jsonify({"slug": slug, "watch": watch, "repos": storage.repo_stats()})
    return jsonify({"error": "repo not found"}), 404


@app.route("/api/notifications")
def api_notifications():
    """Notifications about new requests in watched repositories."""
    unseen = request.args.get("unseen", "").lower() in ("1", "true", "yes")
    return jsonify({"notifications": storage.list_notifications(unseen_only=unseen)})


@app.route("/api/notifications/seen", methods=["POST"])
def api_notifications_seen():
    """Mark notifications as seen so they are not shown again."""
    data = request.get_json(silent=True) or {}
    return jsonify({"marked": storage.mark_notifications_seen(data.get("ids"))})


@app.route("/api/agents")
def api_agents():
    """Supported coding agents and whether they are installed here."""
    return jsonify({"agents": agents.detect_agents(get_settings())})


@app.route("/api/agents/<agent_id>/models")
def api_agent_models(agent_id):
    """List the models an agent reports as available."""
    force = request.args.get("refresh", "").lower() in ("1", "true", "yes")
    return jsonify(agents.list_models(agent_id, get_settings(), force=force))


@app.route("/api/providers")
def api_providers():
    settings = get_settings()
    hosts = providers.provider_hosts(settings)
    return jsonify({
        "providers": [
            {"id": "github", "label": "GitHub", "host": hosts["github"],
             "url": settings["github_url"], "configured": bool(settings["github_token"])},
            {"id": "gitlab", "label": "GitLab", "host": hosts["gitlab"],
             "url": settings["gitlab_url"], "configured": bool(settings["gitlab_token"])},
        ]
    })


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        settings = storage.load_settings()
        for field in TEXT_SETTINGS:
            if field in data:
                settings[field] = str(data[field]).strip()
        for field in INT_SETTINGS:
            if field in data:
                settings[field] = _as_int(data[field], storage.DEFAULT_SETTINGS[field])
        for field in DICT_SETTINGS:
            if field in data:
                value = data[field]
                if isinstance(value, dict):
                    settings[field] = {
                        str(k): str(v).strip()
                        for k, v in value.items()
                        if str(v).strip()
                    }
        storage.save_settings(settings)
        return jsonify(settings_payload())

    return jsonify(settings_payload())


@app.route("/api/pr/<int:pr_id>")
def api_pr_detail(pr_id):
    pr = storage.get_pr(pr_id)
    if pr:
        return jsonify(pr)
    return jsonify({"error": "PR not found"}), 404


@app.route("/pr/<int:pr_id>")
def pr_detail(pr_id):
    pr = storage.get_pr(pr_id)
    if pr:
        settings = get_settings()
        return render_template(
            "pr_detail.html",
            pr=pr,
            settings=settings,
            agents=agents.detect_agents(settings),
            reviews=storage.list_reviews(pr["id"]),
        )
    return "PR not found", 404


@app.route("/api/pr/<int:pr_id>/review", methods=["POST"])
def api_start_review(pr_id):
    """Start an agent review for a pull/merge request."""
    pr = storage.get_pr(pr_id)
    if not pr:
        return jsonify({"error": "PR not found"}), 404

    settings = get_settings()
    data = request.get_json(silent=True) or {}

    agent_id = (data.get("agent") or settings["default_agent"] or "").strip()
    if not agent_id:
        installed = agents.available_agents(settings)
        if not installed:
            return jsonify({
                "error": "No coding agent found. Install opencode, pi, claude or copilot."
            }), 400
        agent_id = installed[0]["id"]

    model = (data.get("model") or settings["default_model"] or "").strip()
    try:
        review_id = reviewer.start_review(pr, agent_id, model, settings)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"review": storage.get_review(review_id)}), 202


@app.route("/api/reviews/<int:review_id>")
def api_review(review_id):
    review = storage.get_review(review_id)
    if not review:
        return jsonify({"error": "review not found"}), 404
    return jsonify(review)


@app.route("/api/pr/<int:pr_id>/reviews")
def api_pr_reviews(pr_id):
    return jsonify({"reviews": storage.list_reviews(pr_id)})


@app.route("/api/reviewed")
def api_reviewed():
    """Pull requests with at least one agent review (the sidebar list)."""
    return jsonify({"reviewed": reviewed_prs_payload()})


@app.route("/api/reviewed/<int:pr_id>", methods=["DELETE"])
def api_reviewed_dismiss(pr_id):
    """Remove a pull request from the "AI Reviewed" list."""
    if not storage.dismiss_review(pr_id):
        return jsonify({"error": "PR not found"}), 404
    return jsonify({"dismissed": pr_id, "reviewed": reviewed_prs_payload()})


def _repo_ref(pr):
    """Build a provider repo record from a stored pull request."""
    host = pr.get("host") or "github.com"
    return {
        "provider": pr.get("provider") or "github",
        "host": host,
        "full_name": pr["repo"],
        "slug": pr.get("slug") or f"{host}/{pr['repo']}",
    }


@app.route("/api/pr/<int:pr_id>/commits")
def api_pr_commits(pr_id):
    """Commits in a pull/merge request, fetched live from the provider."""
    pr = storage.get_pr(pr_id)
    if not pr:
        return jsonify({"error": "PR not found"}), 404
    settings = get_settings()
    provider = providers.get_provider(pr.get("provider") or "github")
    token = providers.token_for(pr.get("provider") or "github", settings)
    commits = provider.fetch_commits(_repo_ref(pr), pr["number"], token, settings)
    return jsonify({"commits": commits})


@app.route("/api/pr/<int:pr_id>/files")
def api_pr_files(pr_id):
    """Changed files with their unified diffs, fetched live from the provider."""
    pr = storage.get_pr(pr_id)
    if not pr:
        return jsonify({"error": "PR not found"}), 404
    settings = get_settings()
    provider = providers.get_provider(pr.get("provider") or "github")
    token = providers.token_for(pr.get("provider") or "github", settings)
    files = provider.fetch_files(_repo_ref(pr), pr["number"], token, settings)
    return jsonify({"files": files})


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "total_prs": storage.count_prs(),
        "repos": storage.list_repo_slugs(),
        "agents": [a["id"] for a in agents.available_agents(get_settings())],
    })


def bootstrap():
    """Prepare storage and migrate legacy data."""
    storage.init_db()
    imported = storage.migrate_legacy_data()
    if imported:
        print(f"Migrated {imported} pull request(s) from legacy JSON storage")
    settings = get_settings()
    installed = [a["label"] for a in agents.available_agents(settings)]
    print(f"Coding agents available: {', '.join(installed) if installed else 'none'}")
    start_watcher()
    watched = [r["slug"] for r in storage.list_repos() if r["watch"]]
    if watched:
        print(f"Watching {len(watched)} repository(ies) for new requests")


if __name__ == "__main__":
    bootstrap()
    settings = get_settings()
    host = settings["host"] or "0.0.0.0"
    port = settings["port"] or 5000
    app.run(host=host, port=port, debug=False)
