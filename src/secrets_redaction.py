"""
Secrets redaction utility.

Scans strings for known secret values loaded from ``.env.secrets`` and
replaces them with ``[REDACTED]``.

Secret keys are discovered **automatically** by parsing
``.env.secrets.example`` (always in version control) and
``.env.secrets`` (git-ignored, real values).  Only the keys defined in
those files are redacted — their actual runtime values are read from
``os.environ`` (which is populated by ``python-dotenv`` before this
module is first called).

This is applied to all tool output and ``end_task`` reports before they
are fed back to the LLM, preventing accidental key leakage.

**Architecture note — why we also scan ``os.environ``:**
The sidecar container (executor-executor) never receives ``LLM_API_KEY`` —
only the main service (executor-service) loads ``LLM_API_KEY`` from ``.env``
because it runs the LLM agent loop.  The sidecar gets only skill-specific
keys like ``BRAVE_SEARCH_API_KEY`` as explicit env vars, so the LLM cannot
``echo $LLM_API_KEY`` inside a bash command.  However, the main service
processes tool output *before* feeding it back to the LLM, and that output
could still contain a key that was echoed by a bash command, logged by a
Python script, or embedded in a URL.  Redacting on the main-service side
provides a safety net regardless of the source.

Usage::

    from src.secrets_redaction import redact_secrets

    safe = redact_secrets(some_string)
"""

import os
import re
from pathlib import Path
from typing import List, Optional, Set

_REDACTED = "[REDACTED]"

# Placeholder patterns for values that should never be redacted.
_PLACEHOLDER_PATTERNS: List[str] = [
    r"^$",               # empty string
    r"\.\.\.+$",         # ends with ...  (e.g. "sk-...")
    r"^sk-\.\.\.$",      # literal "sk-..."
    r"^your[_-]",        # "your-key-here", "your_api_key"
    r"^<",               # "<insert>", "<your-key>"
    r"^xxx+$",           # "xxx", "xxxxx"
    r"^change[_-]me",    # "change_me", "change-me"
    r"^replace[_-]",     # "replace_with_your_key"
    r"^TODO$",            # "TODO"
    r"^_put_your_",      # "_put_your_api_key_here"
]

_PLACEHOLDER_RE: re.Pattern = re.compile(
    "|".join(f"(?:{p})" for p in _PLACEHOLDER_PATTERNS),
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# .env.secrets file parsing
# ---------------------------------------------------------------------------

def _parse_env_key_names(path: Path) -> Set[str]:
    """Parse an env file and return the **key names** found in it.

    Values are ignored — we only care about which keys are defined, because
    real values come from ``os.environ`` at runtime.
    """
    keys: Set[str] = set()
    if not path.is_file():
        return keys

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return keys

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, _, _ = line.partition("=")
        key = key.strip()
        if key:
            keys.add(key)

    return keys


def _find_project_root() -> Path:
    """Walk up from CWD to find the project root (directory with ``.git``)."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").is_dir() or (parent / "pyproject.toml").is_file():
            return parent
    return cwd


def _discover_secret_keys() -> Set[str]:
    """Collect all key names from ``.env.secrets`` and ``.env.secrets.example``.

    ``.env.secrets.example`` is always in version control and acts as the
    canonical list of which keys are considered secrets.  ``.env.secrets``
    (git-ignored) may contain additional keys added by the deployer.
    """
    root = _find_project_root()
    keys: Set[str] = set()

    # .env.secrets.example is always present and lists the expected keys.
    example_path = root / ".env.secrets.example"
    keys |= _parse_env_key_names(example_path)

    # .env.secrets (git-ignored) may have additional keys.
    secrets_path = root / ".env.secrets"
    keys |= _parse_env_key_names(secrets_path)

    return keys


# ---------------------------------------------------------------------------
# Pattern compilation and caching
# ---------------------------------------------------------------------------
_pattern: Optional[re.Pattern] = None


def _build_pattern() -> Optional[re.Pattern]:
    """Build a regex alternation of all secret values from ``os.environ``.

    Only keys discovered in ``.env.secrets`` / ``.env.secrets.example`` are
    considered.  Values that are empty or look like placeholders are skipped.
    """
    secret_keys = _discover_secret_keys()
    values: List[str] = []

    for key in sorted(secret_keys):  # sort for deterministic order
        val = os.getenv(key, "")
        if not val or _PLACEHOLDER_RE.match(val):
            continue
        values.append(val)

    if not values:
        return None

    # Sort longest-first so longer secrets take priority over substrings
    parts = sorted((re.escape(v) for v in values), key=len, reverse=True)
    return re.compile("|".join(parts))


def _get_pattern() -> Optional[re.Pattern]:
    global _pattern
    if _pattern is None:
        _pattern = _build_pattern()
    return _pattern


def redact_secrets(text: str) -> str:
    """Replace any known secret values in *text* with ``[REDACTED]``.

    This is deliberately simple: exact-value matching avoids false positives
    on short or common substrings.  The compiled regex is cached across
    calls so the overhead is minimal.
    """
    pat = _get_pattern()
    if pat is None:
        return text
    return pat.sub(_REDACTED, text)


def rebuild() -> None:
    """Force re-read of env vars/files and recompile the redaction regex.

    Call this if you change env vars at runtime (e.g. in tests).
    Normal production usage never needs this — secrets are loaded once
    on first call to ``redact_secrets``.
    """
    global _pattern
    _pattern = _build_pattern()
