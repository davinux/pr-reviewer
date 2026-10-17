"""Runs AI code reviews of pull requests.

For each review the app:

1. clones (or refreshes) the repository into ``DATA_DIR/workspaces``,
2. fetches and checks out the pull request's head branch,
3. builds a review prompt and runs the selected agent CLI in that checkout,
4. stores the agent's output in the database.

Reviews run in a background thread; the web layer polls the ``reviews`` table
for status and output.
"""

import os
import shlex
import subprocess
import threading
import time
from datetime import datetime, timezone

import agents
import providers
import storage

WORKSPACES_DIR = os.path.join(storage.DATA_DIR, "workspaces")

DEFAULT_REVIEW_TIMEOUT = 900
DEFAULT_MAX_DESCRIPTION_CHARS = 8000

# The prompt template used when ``review_prompt`` is not set in Settings.
# Placeholders: {kind}, {kind_title}, {provider}, {host}, {repo}, {number},
# {title}, {author}, {url}, {base_ref}, {head_ref}, {body}, {diff_command}.
DEFAULT_REVIEW_PROMPT = """You are an expert code reviewer. Review the {kind} below.

Host: {host}
Repository: {repo}
{kind_title}: #{number} — {title}
Author: {author}
URL: {url}
Target branch: {base_ref}
Source branch: {head_ref}

The repository is checked out in the current working directory with the
{kind}'s head branch checked out. Inspect the changes it introduces, for
example with:
    {diff_command}

Description:
---
{body}
---

Produce a focused, actionable review:
- Start with a 1-3 sentence summary and an overall assessment.
- List concrete findings grouped by severity: **Blocking**, **Important**, **Nit**.
- Reference specific files and line numbers and explain *why* something is an issue.
- Call out bugs, edge cases, security, performance, error handling and missing tests.
- If the change looks good, say so plainly.
- Do NOT modify any files. This is a read-only review.
Return the review as Markdown.
"""

_active_lock = threading.Lock()
_active_prs = set()


def _as_int(value, default):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _now():
    return datetime.now(timezone.utc).isoformat()


def _repo_from_pr(pr):
    host = pr.get("host") or "github.com"
    full_name = pr["repo"]
    return {
        "provider": pr.get("provider") or "github",
        "host": host,
        "full_name": full_name,
        "slug": pr.get("slug") or f"{host}/{full_name}",
    }


def workspace_dir(slug):
    safe = slug.replace("/", "__").replace(os.sep, "_")
    return os.path.join(WORKSPACES_DIR, safe)


def _redact(text, token):
    if text and token:
        return text.replace(token, "***")
    return text


def _git(args, cwd, token=None, timeout=600):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
        timeout=timeout, env=env,
    )
    if proc.returncode != 0:
        detail = _redact((proc.stderr or proc.stdout or "").strip(), token)
        raise RuntimeError(f"git {' '.join(shlex.quote(a) for a in args)} failed: {detail}")
    return proc.stdout


def prepare_workspace(repo, pr, token=None, settings=None):
    """Ensure a checkout of ``pr`` exists and return its path."""
    provider = providers.get_provider(repo["provider"])
    path = workspace_dir(repo["slug"])
    os.makedirs(WORKSPACES_DIR, exist_ok=True)

    if not os.path.isdir(os.path.join(path, ".git")):
        _git(["clone", "--quiet", provider.clone_url(repo, token, settings), path],
             cwd=None, token=token)
    else:
        _git(["fetch", "--quiet", "--prune", "origin"], cwd=path, token=token)

    base_ref = pr.get("base_ref") or "main"
    number = pr["number"]

    # Base branch is best-effort: the request head is what matters most.
    try:
        _git(["fetch", "--quiet", "origin", base_ref], cwd=path, token=token)
    except RuntimeError:
        pass

    # GitHub exposes refs/pull/<n>/head; GitLab uses refs/merge-requests/<n>/head.
    _git(
        ["fetch", "--quiet", "origin",
         f"{provider.head_ref(number)}:refs/remotes/origin/pr-{number}"],
        cwd=path, token=token,
    )
    _git(
        ["checkout", "--quiet", "--force", "-B", f"pr-{number}", f"origin/pr-{number}"],
        cwd=path, token=token,
    )
    return path


def prompt_template(settings=None):
    """The configured review prompt template, or the built-in default."""
    settings = settings or {}
    template = str(settings.get("review_prompt") or "").strip()
    return template or DEFAULT_REVIEW_PROMPT


def build_prompt(pr, base_ref, settings=None):
    """Render the review prompt from the configured template."""
    settings = settings or {}
    max_desc = _as_int(
        settings.get("max_description_chars"), DEFAULT_MAX_DESCRIPTION_CHARS
    )

    body = (pr.get("body") or "").strip()
    if max_desc and len(body) > max_desc:
        body = body[:max_desc] + "\n[... description truncated ...]"

    kind = "merge request" if pr.get("provider") == "gitlab" else "pull request"
    values = {
        "kind": kind,
        "kind_title": kind.capitalize(),
        "provider": pr.get("provider") or "github",
        "host": pr.get("host") or "github.com",
        "repo": pr.get("repo") or "",
        "number": str(pr.get("number") or ""),
        "title": pr.get("title") or "",
        "author": pr.get("user") or "unknown",
        "user": pr.get("user") or "unknown",
        "url": pr.get("url") or "",
        "base_ref": base_ref,
        "head_ref": pr.get("head_ref") or "unknown",
        "body": body or "(no description provided)",
        "diff_command": f"git diff origin/{base_ref}...HEAD",
    }

    result = prompt_template(settings)
    for key, value in values.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def start_review(pr, agent_id, model=None, settings=None):
    """Create a review row and run it in the background. Returns the review id."""
    settings = settings or storage.load_settings()
    model = (model or "").strip() or None

    with _active_lock:
        if pr["id"] in _active_prs:
            raise RuntimeError("A review is already running for this pull request.")
        _active_prs.add(pr["id"])

    prompt = build_prompt(pr, pr.get("base_ref") or "main", settings)
    review_id = storage.create_review(
        pr["id"], pr.get("slug") or pr["repo"], pr["number"], agent_id, model, prompt
    )
    thread = threading.Thread(
        target=_run_review,
        args=(review_id, pr, agent_id, model, settings),
        daemon=True,
    )
    thread.start()
    return review_id


def _run_review(review_id, pr, agent_id, model, settings):
    repo = _repo_from_pr(pr)
    token = providers.token_for(repo["provider"], settings)
    timeout = _as_int(settings.get("review_timeout"), DEFAULT_REVIEW_TIMEOUT)
    started = time.time()

    def finish(status, **fields):
        fields.setdefault("finished_at", _now())
        fields.setdefault("duration_ms", int((time.time() - started) * 1000))
        storage.update_review(review_id, status=status, **fields)

    try:
        storage.update_review(review_id, status="preparing")
        workspace = prepare_workspace(repo, pr, token, settings)
        storage.update_review(review_id, workspace=workspace)

        prompt = build_prompt(pr, pr.get("base_ref") or "main", settings)
        command, error = agents.resolve_command(agent_id, prompt, model, settings)
        if error:
            finish("error", error=error)
            return

        display = " ".join(shlex.quote("<prompt>" if arg == prompt else arg) for arg in command)
        storage.update_review(review_id, status="running", command=_redact(display, token))

        proc = agents.run(command, cwd=workspace, timeout=timeout)
        output = (proc.stdout or "").strip()
        stderr = _redact((proc.stderr or "").strip(), token)

        if proc.returncode == 0:
            finish("done", output=output, error=stderr or None)
        else:
            finish(
                "error",
                output=output or None,
                error=stderr or f"Agent exited with code {proc.returncode}",
            )
    except subprocess.TimeoutExpired:
        finish("error", error=f"Agent timed out after {timeout} seconds.")
    except Exception as exc:  # noqa: BLE001 - surfaced in the UI
        finish("error", error=_redact(str(exc), token))
    finally:
        with _active_lock:
            _active_prs.discard(pr["id"])
