"""Canonical filesystem paths shared by the service and executor manager."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_WORKDIR_BASE = "/storage/subagent_work"


def workdir_base() -> str:
    """Return the configured per-session workdir root.

    The host service defaults to a repository-local runtime directory. The
    Docker manager bind-mounts it to a fixed Linux path inside the sandbox.
    """
    default = PROJECT_ROOT / ".runtime" / "subagent_work"
    return os.path.realpath(
        os.path.expanduser(os.getenv("WORKDIR_BASE", str(default)))
    )


def host_path_to_sandbox(path: str, host_base: str | None = None) -> str:
    """Translate a path inside the host workdir root to its Docker path."""
    base = os.path.realpath(host_base or workdir_base())
    candidate = os.path.realpath(path)
    try:
        if os.path.commonpath((candidate, base)) != base:
            raise ValueError("host path is outside WORKDIR_BASE")
    except ValueError as exc:
        raise ValueError("host path is outside WORKDIR_BASE") from exc
    relative = os.path.relpath(candidate, base)
    if relative == os.curdir:
        return SANDBOX_WORKDIR_BASE
    return str(PurePosixPath(SANDBOX_WORKDIR_BASE, *Path(relative).parts))


def sandbox_path_to_host(path: str, host_base: str | None = None) -> str:
    """Translate an absolute sandbox workdir path back to the host."""
    sandbox_root = PurePosixPath(SANDBOX_WORKDIR_BASE)
    candidate = PurePosixPath(path)
    try:
        relative = candidate.relative_to(sandbox_root)
    except ValueError as exc:
        raise ValueError("sandbox path is outside the sandbox workdir") from exc
    base = os.path.realpath(host_base or workdir_base())
    translated = os.path.realpath(os.path.join(base, *relative.parts))
    try:
        if os.path.commonpath((translated, base)) != base:
            raise ValueError("sandbox path escapes WORKDIR_BASE")
    except ValueError as exc:
        raise ValueError("sandbox path escapes WORKDIR_BASE") from exc
    return translated
