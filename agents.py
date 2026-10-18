"""Registry of coding-agent CLIs the reviewer can drive.

Each supported agent is just a **command template**. The built-in templates
below can be overridden per agent in Settings (``agent_commands``), and the
binary name/path can be overridden too (``agent_binaries``). Anything not
covered can be run through the ``custom`` agent and the ``custom_command``
setting.

Template syntax
---------------
- ``{prompt}`` — the review prompt. Appended automatically if omitted.
- ``{model}`` — the model (empty when none is chosen).
- ``[...]``    — an optional group. It is dropped when a placeholder inside it
  resolves to an empty value, which is how the model flag stays optional.
  Example: ``opencode run [--model {model}] {prompt}``.

Templates are split with shell rules, so quoting works: use ``"{prompt}"`` if
you want the prompt passed verbatim as one argument.
"""

import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

# A prompt larger than this is truncated before being passed to the agent. It is
# a safety valve so an enormous diff cannot blow past the OS argument limit.
DEFAULT_MAX_PROMPT_CHARS = 400_000


@dataclass(frozen=True)
class AgentSpec:
    id: str
    label: str
    binaries: Sequence[str]
    command: str
    note: str = ""
    model_command: str = ""


AGENTS = (
    AgentSpec(
        "opencode", "OpenCode", ("opencode",),
        "opencode run --format default --auto [--model {model}] {prompt}",
        "Runs `opencode run` in the checked-out workspace.",
        "opencode models",
    ),
    AgentSpec(
        "pi", "pi", ("pi",),
        "pi --print --mode text --no-session [--model {model}] {prompt}",
        "Runs `pi --print --mode text` in the checked-out workspace.",
        "pi --list-models",
    ),
    AgentSpec(
        "claude", "Claude Code", ("claude",),
        "claude --print --output-format text [--model {model}] {prompt}",
        "Runs `claude --print` in the checked-out workspace.",
        "",
    ),
    AgentSpec(
        "copilot", "GitHub Copilot CLI", ("copilot",),
        "copilot --allow-all-tools [--model {model}] --prompt {prompt}",
        "Runs the Copilot CLI in the checked-out workspace.",
        "",
    ),
)

CUSTOM_ID = "custom"
CUSTOM_LABEL = "Custom command"

_OPTIONAL_RE = re.compile(r"\[([^\[\]]*)\]")

# Tokens (provider or model ids) are simple: letters, digits, dot, dash, underscore.
_MODEL_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# Header words used by some CLIs ("provider model ...").
_MODEL_HEADERS = {"provider", "model", "name", "models", "id", "family"}

# Model listings are cached briefly since the CLIs can be slow to start.
MODEL_CACHE_TTL = 300
MODEL_LIST_TIMEOUT = 30
_model_cache = {}
_model_cache_lock = threading.Lock()



def _as_int(value, default):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _which(binaries: Sequence[str]) -> Optional[str]:
    for name in binaries:
        if not name:
            continue
        path = shutil.which(name)
        if path:
            return path
    return None


def get_agent(agent_id: str) -> Optional[AgentSpec]:
    return next((a for a in AGENTS if a.id == agent_id), None)


def agent_binaries(spec: AgentSpec, settings=None) -> list:
    """Binary names to look for, honouring an ``agent_binaries`` override."""
    override = ((settings or {}).get("agent_binaries") or {}).get(spec.id) or ""
    override = str(override).strip()
    return [override] if override else list(spec.binaries)


def agent_command(spec: AgentSpec, settings=None) -> str:
    """Command template for an agent, honouring an ``agent_commands`` override."""
    override = ((settings or {}).get("agent_commands") or {}).get(spec.id) or ""
    return str(override).strip() or spec.command


def agent_model_command(agent_id: str, settings=None) -> str:
    """Command that lists an agent's models, or "" when none is configured."""
    override = ((settings or {}).get("agent_model_commands") or {}).get(agent_id) or ""
    override = str(override).strip()
    if override:
        return override
    spec = get_agent(agent_id)
    return spec.model_command if spec else ""


def _agent_env():
    env = dict(os.environ)
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    # Force non-interactive, non-paged output for the CLIs.
    env.setdefault("NO_COLOR", "1")
    env.setdefault("CI", "1")
    return env


def detect_agents(settings=None) -> list:
    """Return every supported agent with its availability on this system."""
    settings = settings or {}
    detected = []
    for spec in AGENTS:
        names = agent_binaries(spec, settings)
        path = _which(names)
        detected.append({
            "id": spec.id,
            "label": spec.label,
            "installed": path is not None,
            "path": path,
            "binaries": names,
            "command": agent_command(spec, settings),
            "default_command": spec.command,
            "default_binaries": list(spec.binaries),
            "model_command": agent_model_command(spec.id, settings),
            "default_model_command": spec.model_command,
            "note": spec.note,
        })
    return detected


def available_agents(settings=None) -> list:
    """Only the agents that are actually installed."""
    return [a for a in detect_agents(settings) if a["installed"]]


def parse_models(output: str) -> list:
    """Extract ``provider/model`` ids from a model-listing command's output.

    Handles both one-per-line output (``opencode models``) and whitespace tables
    with a ``provider  model  ...`` header (``pi --list-models``).
    """
    models = []
    seen = set()
    for raw in (output or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        cols = line.split()
        candidate = None
        if len(cols) == 1:
            candidate = cols[0]
        elif (
            _MODEL_TOKEN_RE.match(cols[0])
            and cols[0].lower() not in _MODEL_HEADERS
            and _MODEL_TOKEN_RE.match(cols[1])
        ):
            candidate = f"{cols[0]}/{cols[1]}"
        if not candidate:
            continue
        provider, sep, model = candidate.partition("/")
        if not sep or not provider or not model:
            continue
        if not _MODEL_TOKEN_RE.match(provider):
            continue
        if any(ch.isspace() for ch in model):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        models.append(candidate)
    return models


def list_models(agent_id, settings=None, force=False, timeout=MODEL_LIST_TIMEOUT):
    """List an agent's models by running its model command.

    Returns ``{"agent", "models", "command", "error"}``. Results are cached for a
    few minutes; pass ``force=True`` to refresh.
    """
    settings = settings or {}
    command = agent_model_command(agent_id, settings)
    result = {"agent": agent_id, "models": [], "command": command, "error": None}
    if not command:
        result["error"] = "No model listing command is configured for this agent."
        return result

    cache_key = (agent_id, command)
    now = time.time()
    if not force:
        with _model_cache_lock:
            cached = _model_cache.get(cache_key)
        if cached and now - cached[0] < MODEL_CACHE_TTL:
            return {"agent": agent_id, "models": cached[1], "command": command, "error": None, "cached": True}

    try:
        argv = shlex.split(command)
    except ValueError as exc:
        result["error"] = f"Invalid model command: {exc}"
        return result
    if not argv:
        result["error"] = "No model listing command is configured for this agent."
        return result

    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, env=_agent_env()
        )
    except FileNotFoundError:
        result["error"] = f"Command not found: {argv[0]}"
        return result
    except subprocess.TimeoutExpired:
        result["error"] = f"Listing models timed out after {timeout} seconds."
        return result
    except Exception as exc:  # noqa: BLE001 - surfaced in the UI
        result["error"] = str(exc)
        return result

    models = parse_models("\n".join(part for part in (proc.stdout, proc.stderr) if part))
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        result["error"] = detail or f"Command exited with code {proc.returncode}"
    elif not models:
        result["error"] = (proc.stderr or "").strip() or "No models were reported."

    with _model_cache_lock:
        _model_cache[cache_key] = (now, models)
    result["models"] = models
    return result


def render_command(template: str, prompt: str, model: Optional[str] = None):
    """Render a command template into an argv list. Returns (argv, error).

    Optional ``[...]`` groups are removed when a placeholder inside them resolves
    to an empty value (so ``[--model {model}]`` disappears when no model is set).
    """
    values = {"prompt": prompt, "model": (model or "").strip()}

    def _keep_group(match):
        group = match.group(1)
        names = re.findall(r"\{([^}]+)\}", group)
        if any(not values.get(name, "x").strip() for name in names):
            return ""
        return group

    stripped = _OPTIONAL_RE.sub(_keep_group, template)

    try:
        argv = shlex.split(stripped)
    except ValueError as exc:
        return None, f"Invalid command template: {exc}"

    argv = [
        part.replace("{prompt}", prompt).replace("{model}", values["model"])
        for part in argv
    ]
    if "{prompt}" not in template:
        argv.append(prompt)
    argv = [part for part in argv if part != ""]

    if not argv:
        return None, "Command template is empty."
    return argv, None


def resolve_command(agent_id, prompt, model=None, settings=None):
    """Build the argv for an agent. Returns (command, error_or_None).

    ``custom`` uses the ``custom_command`` setting as a template; the built-in
    agents use their (optionally overridden) command template.
    """
    settings = settings or {}
    max_chars = _as_int(settings.get("max_prompt_chars"), DEFAULT_MAX_PROMPT_CHARS)
    if max_chars and len(prompt) > max_chars:
        prompt = prompt[:max_chars] + "\n\n[... prompt truncated ...]"

    if agent_id == CUSTOM_ID:
        template = str(settings.get("custom_command") or "").strip()
        if not template:
            return None, "No custom command configured."
        return render_command(template, prompt, model)

    spec = get_agent(agent_id)
    if spec is None:
        return None, f"Unknown agent: {agent_id}"
    names = agent_binaries(spec, settings)
    if _which(names) is None:
        return None, f"{spec.label} is not installed (looked for {', '.join(names)})."
    return render_command(agent_command(spec, settings), prompt, model)


def run(command: Sequence[str], cwd: str, timeout: int = 900, env=None) -> subprocess.CompletedProcess:
    """Run an agent command, capturing output. Raises subprocess.TimeoutExpired."""
    run_env = _agent_env()
    if env:
        run_env.update(env)
    return subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=run_env,
    )


def run_streaming(
    command: Sequence[str],
    cwd: str,
    timeout: int = 900,
    env=None,
    on_output: Optional[Callable[[str, str], None]] = None,
) -> subprocess.CompletedProcess:
    """Run an agent command, reporting output as it arrives.

    Reads ``stdout`` and ``stderr`` line by line and calls
    ``on_output(stream, line)`` for each line as the process produces it
    (``stream`` is ``"stdout"`` or ``"stderr"``), so a review that runs for
    minutes can show its progress live. Returns a
    ``subprocess.CompletedProcess`` with the complete ``stdout``/``stderr`` text,
    so the caller decides success exactly as with :func:`run`. Raises
    ``subprocess.TimeoutExpired`` after killing the process on timeout; whatever
    was streamed before the kill has already been reported.
    """
    run_env = _agent_env()
    if env:
        run_env.update(env)
    argv = list(command)
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=run_env,
    )

    buffers = {"stdout": [], "stderr": []}
    lock = threading.Lock()

    def _pump(stream, name):
        try:
            for line in iter(stream.readline, ""):
                with lock:
                    buffers[name].append(line)
                if on_output is not None:
                    try:
                        on_output(name, line)
                    except Exception:  # noqa: BLE001 - never lose the stream
                        pass
        finally:
            stream.close()

    readers = [
        threading.Thread(target=_pump, args=(proc.stdout, "stdout"), daemon=True),
        threading.Thread(target=_pump, args=(proc.stderr, "stderr"), daemon=True),
    ]
    for reader in readers:
        reader.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        for reader in readers:
            reader.join(timeout=5)
        raise

    for reader in readers:
        reader.join(timeout=5)

    return subprocess.CompletedProcess(
        argv,
        proc.returncode,
        "".join(buffers["stdout"]),
        "".join(buffers["stderr"]),
    )
