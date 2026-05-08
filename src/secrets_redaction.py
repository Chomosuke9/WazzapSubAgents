"""
Secrets redaction utility.

Scans strings for known secret values (API keys, tokens) loaded from
environment variables and replaces them with ``[REDACTED]``.

This is applied to all tool output and ``end_task`` reports before they
are fed back to the LLM, preventing accidental key leakage.

**Architecture note — why we still list LLM_API_KEY here:**
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
from typing import List

# ---------------------------------------------------------------------------
# Which env vars count as "secrets"?
# Add new secret variable names here.  Values that are empty or look like
# placeholders (e.g. "sk-...", empty string) are skipped.
# ---------------------------------------------------------------------------
SECRET_ENV_VARS: List[str] = [
    "LLM_API_KEY",
    "BRAVE_SEARCH_API_KEY",
]

_REDACTED = "[REDACTED]"

# ---------------------------------------------------------------------------
# Build a single regex that matches any non-empty secret value.
# Compiled once at import time; re-built if ``rebuild()`` is called after
# the env changes (rare, but handy for tests).
# ---------------------------------------------------------------------------
_pattern: re.Pattern | None = None


def _build_pattern() -> re.Pattern | None:
    """Compile a regex alternation of all current secret values."""
    parts: List[str] = []
    for var in SECRET_ENV_VARS:
        val = os.getenv(var, "")
        # Skip empty, placeholder, or obviously fake values
        if not val or val.endswith("...") or val == "sk-...":
            continue
        # Escape the value so regex metacharacters are treated literally
        parts.append(re.escape(val))
    if not parts:
        return None
    # Sort longest-first so longer secrets take priority over substrings
    parts.sort(key=len, reverse=True)
    return re.compile("|".join(parts))


def _get_pattern() -> re.Pattern | None:
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
    """Force re-read of env vars and recompile the redaction regex.

    Call this if you change env vars at runtime (e.g. in tests).
    Normal production usage never needs this — secrets are loaded once
    on first call to ``redact_secrets``.
    """
    global _pattern
    _pattern = _build_pattern()
