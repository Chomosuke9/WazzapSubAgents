"""Canonical filesystem paths shared by the service and executor manager."""
from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def workdir_base() -> str:
    """Return the configured per-session workdir root.

    Native/managed deployments default to a repository-local runtime directory.
    Docker Compose sets ``WORKDIR_BASE=/storage/subagent_work`` explicitly.
    """
    default = PROJECT_ROOT / ".runtime" / "subagent_work"
    return os.path.realpath(
        os.path.expanduser(os.getenv("WORKDIR_BASE", str(default)))
    )
