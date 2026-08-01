# Persistent Dependencies

This directory is bind-mounted read-write at `/dependencies` in the executor.
It holds lightweight third-party dependencies that a subagent needs but that
are not preinstalled in the Docker image.

Runtime layout:

- `python/` — Python packages installed with `pip --target` and exposed through
  `PYTHONPATH`; `python/bin` is also on `PATH` for package scripts.
- `node/` — Node packages installed with `npm --prefix` and exposed through
  `NODE_PATH`; package binaries under `node/node_modules/.bin` are on `PATH`.
- `bin/` — verified standalone executables, also on `PATH`.
- `cache/` — pip/npm download caches.

Downloaded contents are intentionally ignored by Git but remain on the host and
survive session cleanup and container recreation. Record the exact dependency
name and pinned version in the corresponding method under `methods/`.

This directory contains shared executable code. Every subagent can modify it;
do not store credentials here, and periodically review or clear it when testing
untrusted packages.
