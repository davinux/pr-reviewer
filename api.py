"""Public, read-only HTTP API and its Swagger documentation.

This is a thin read layer over ``storage.py``: it answers whether a pull/merge
request *passed* its latest review and never contacts a hosting provider or
starts work. The interface is described by ``openapi.json`` and browsable at
``/api/docs``.

Two endpoint families live here (see ``specs/008-review-status-api``):

* ``GET /api/v1/reviews/status`` -- one request, looked up by repo slug +
  number or by the internal ``pr_id``.
* ``GET /api/v1/reviews`` -- reviewed requests, filterable by repo and verdict.

When the ``api_token`` setting is set, the data endpoints require it in an
``Authorization: Bearer <token>`` or ``X-API-Token: <token>`` header. The docs
page and the OpenAPI document stay open so the token can be entered in the UI.
"""

import hmac
import json
import os
from functools import wraps

from flask import Blueprint, jsonify, request

import storage

try:  # The docs are optional at runtime; the data API works without them.
    from flask_swagger_ui import get_swaggerui_blueprint

    SWAGGER_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the dependency
    get_swaggerui_blueprint = None
    SWAGGER_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OPENAPI_FILENAME = "openapi.json"

API_PREFIX = "/api/v1"
DOCS_URL = "/api/docs"
OPENAPI_URL = f"{API_PREFIX}/openapi.json"

bp = Blueprint("api_v1", __name__, url_prefix=API_PREFIX)

# Verdicts a caller may filter on. Only these are ever stored on a review.
VERDICTS = ("passed", "failed", "unknown")
DEFAULT_LIMIT = 50
MAX_LIMIT = 500


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def _provided_token():
    """The token a caller sent, from either accepted header."""
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return (request.headers.get("X-API-Token") or "").strip()


def _authorized():
    """True when the request may proceed.

    An empty ``api_token`` means the API is open; otherwise the caller must
    present the configured token.
    """
    expected = (storage.load_settings().get("api_token") or "").strip()
    if not expected:
        return True
    given = _provided_token()
    return bool(given) and hmac.compare_digest(given, expected)


def require_token(view):
    """Guard a data endpoint behind the optional API token."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not _authorized():
            response = jsonify({
                "error": "unauthorized",
                "message": "A valid API token is required. Send it as "
                           "'Authorization: Bearer <token>' or the 'X-API-Token' header.",
            })
            response.status_code = 401
            response.headers["WWW-Authenticate"] = "Bearer"
            return response
        return view(*args, **kwargs)

    return wrapper


# --------------------------------------------------------------------------- #
# Result shaping
# --------------------------------------------------------------------------- #
def _passed(verdict):
    """The boolean a caller gates on: True/False once decided, else None."""
    if verdict == "passed":
        return True
    if verdict == "failed":
        return False
    return None


def _review_summary(review):
    """The compact review view shared by both endpoints."""
    if not review:
        return None
    return {
        "id": review["id"],
        "status": review["status"],
        "verdict": review["verdict"],
        "agent": review["agent"],
        "model": review["model"],
        "created_at": review["created_at"],
        "finished_at": review["finished_at"],
        "duration_ms": review["duration_ms"],
    }


def _result(pr, review, total_reviews):
    """The API view of one request and its latest review."""
    verdict = review["verdict"] if review else None
    return {
        "repo": pr["slug"],
        "number": pr["number"],
        "pr_id": pr["id"],
        "title": pr.get("title"),
        "state": pr.get("state"),
        "url": pr.get("url"),
        "passed": _passed(verdict),
        "verdict": verdict,
        "review_status": review["status"] if review else None,
        "reviews": total_reviews,
        "review": _review_summary(review),
    }


def _result_from_row(row):
    """The same view, built from a ``storage.list_review_statuses`` row."""
    verdict = row["verdict"]
    return {
        "repo": row["slug"] or row["full_name"],
        "number": row["number"],
        "pr_id": row["pr_id"],
        "title": row["title"],
        "state": row["state"],
        "url": row["url"],
        "passed": _passed(verdict),
        "verdict": verdict,
        "review_status": row["status"],
        "reviews": row["review_count"],
        "review": {
            "id": row["review_id"],
            "status": row["status"],
            "verdict": row["verdict"],
            "agent": row["agent"],
            "model": row["model"],
            "created_at": row["review_created_at"],
            "finished_at": row["finished_at"],
            "duration_ms": row["duration_ms"],
        },
    }


def _error(message, status, code):
    return jsonify({"error": code, "message": message}), status


def _limit_argument():
    """Clamp ``?limit=`` to a sane, bounded window."""
    raw = request.args.get("limit")
    if raw in (None, ""):
        return DEFAULT_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, value))


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@bp.route("/reviews/status")
@require_token
def review_status():
    """Whether one pull/merge request passed its latest review."""
    pr_id = (request.args.get("pr_id") or "").strip()
    repo = (request.args.get("repo") or "").strip()
    number = (request.args.get("number") or "").strip()

    if pr_id:
        try:
            pr = storage.get_pr(int(pr_id))
        except (TypeError, ValueError):
            return _error("'pr_id' must be a whole number.", 400, "invalid_parameter")
    elif repo and number:
        try:
            number_value = int(number)
        except (TypeError, ValueError):
            return _error("'number' must be a whole number.", 400, "invalid_parameter")
        pr = storage.get_pr_by_number(repo, number_value)
    else:
        return _error(
            "Provide 'repo' and 'number', or 'pr_id'.",
            400,
            "missing_parameters",
        )

    if not pr:
        return _error("No stored request matches that identifier.", 404, "not_found")

    return jsonify(_result(pr, storage.latest_review(pr["id"]), storage.count_reviews(pr["id"])))


@bp.route("/reviews")
@require_token
def review_list():
    """Reviewed requests with their latest verdict, newest review first."""
    repo = (request.args.get("repo") or "").strip() or None
    verdict = (request.args.get("verdict") or "").strip().lower() or None
    if verdict and verdict not in VERDICTS:
        return _error(
            f"'verdict' must be one of: {', '.join(VERDICTS)}.",
            400,
            "invalid_parameter",
        )

    rows = storage.list_review_statuses(repo=repo, verdict=verdict, limit=_limit_argument())
    results = [_result_from_row(row) for row in rows]
    return jsonify({"reviews": results, "count": len(results)})


@bp.route("/openapi.json")
def openapi_document():
    """The OpenAPI 3 description of this API (no token needed)."""
    try:
        with open(os.path.join(BASE_DIR, OPENAPI_FILENAME), "r", encoding="utf-8") as handle:
            spec = json.load(handle)
    except (OSError, ValueError):
        return _error("The OpenAPI document is unavailable.", 500, "unavailable")
    return jsonify(spec)


def register(app):
    """Attach the API and the Swagger UI to a Flask app."""
    app.register_blueprint(bp)
    if not SWAGGER_AVAILABLE:
        print("Warning: flask-swagger-ui is not installed; /api/docs is unavailable")
        return
    docs = get_swaggerui_blueprint(
        DOCS_URL,
        OPENAPI_URL,
        config={
            "app_name": "PR Reviewer API",
            "persistAuthorization": True,
            "displayRequestDuration": True,
            "defaultModelsExpandDepth": -1,
        },
    )
    app.register_blueprint(docs)
