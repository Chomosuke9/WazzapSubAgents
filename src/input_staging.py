"""Stage caller-supplied input files so the executor container can read them.

Background
----------
The executor sidecar container only bind-mounts ``WORKDIR_BASE`` (and
optionally ``SUBAGENT_STORAGE_DIR`` → ``/storage``) from the host. When
WazzapAgents sends ``input_files`` paths in ``/execute`` that live outside
those mounts — for example, the bridge default ``<repo>/data/subagent_in/...``
— the agent's ``bash``/``python`` tools run inside the container and see
nothing at that path. The user-visible symptom is that the sub-agent fails
with "file not found" on a file the bridge swears it just staged.

The fix: before running the agent, copy each input file into
``<workdir>/input/<basename>``. ``<workdir>`` is rooted in
``WORKDIR_BASE``, which IS bind-mounted at the same host/container path,
so the copies are reachable from inside the container regardless of how
the operator deployed the bridge. Cleanup is automatic — ``SessionManager``
already ``rmtree``s the workdir when the session ends.

The name ``input`` is chosen so it is:

* Distinct from anything the agent is likely to create itself
  (``output``/``out``/etc).
"""
from __future__ import annotations

import os
import shutil
from typing import Iterable, List

from src.logger import get_logger

logger = get_logger(__name__)


INPUT_SUBDIR = "input"


def stage_inputs_into_workdir(
    workdir: str,
    raw_paths: Iterable[str],
) -> List[str]:
    """Copy ``raw_paths`` into ``<workdir>/input/`` and return the new paths.

    Files that don't exist or aren't regular files are silently skipped
    with a warning (the agent will see a shorter list and decide what to
    do — same semantics as before). Basename collisions are resolved by
    appending an integer suffix (``foo.zip`` → ``foo_1.zip``).

    Returns absolute paths inside the workdir, in input order, omitting
    skipped entries. The empty list is returned if there are no inputs to
    stage or if the staging directory cannot be created.
    """
    paths = [str(p) for p in raw_paths if isinstance(p, (str, os.PathLike))]
    if not paths:
        return []

    target_root = os.path.join(workdir, INPUT_SUBDIR)
    try:
        os.makedirs(target_root, exist_ok=True)
    except OSError as err:
        logger.exception(
            "stage_inputs_into_workdir: failed to create %s: %s",
            target_root, err,
        )
        return []

    used_names: set[str] = set()
    staged: list[str] = []
    for src in paths:
        name = os.path.basename(src) or "unnamed"
        if not src or not os.path.exists(src):
            logger.warning(
                "stage_inputs_into_workdir: source missing, skipping: %s",
                src,
            )
            continue
        if not os.path.isfile(src):
            logger.warning(
                "stage_inputs_into_workdir: not a regular file, skipping: %s",
                src,
            )
            continue

        # Avoid clobbering when two source files share a basename.
        final_name = name
        counter = 1
        while final_name in used_names or os.path.exists(
            os.path.join(target_root, final_name)
        ):
            stem, ext = os.path.splitext(name)
            final_name = f"{stem}_{counter}{ext}"
            counter += 1
        used_names.add(final_name)

        dest = os.path.join(target_root, final_name)
        try:
            shutil.copyfile(src, dest)
        except OSError as err:
            logger.warning(
                "stage_inputs_into_workdir: copy failed for %s -> %s: %s",
                src, dest, err,
            )
            continue
        staged.append(os.path.abspath(dest))

    return staged


def is_input_path(workdir: str, path: str) -> bool:
    """Return True if ``path`` lives under ``<workdir>/input/``.

    Note: Currently disabled to allow input files to be returned as outputs.
    """
    return False
