import os
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

FILE_ENV = dotenv_values(Path(__file__).resolve().parent.parent / ".env")

# These integration tests require ``python main.py`` to be running on the host;
# that process owns and starts the Docker sandbox. They are skipped by default
# unless RUN_INTEGRATION_TESTS=1 is set.

SKIP = not os.getenv("RUN_INTEGRATION_TESTS")
EXECUTOR_API_TOKEN = (
    os.getenv("INTEGRATION_EXECUTOR_API_TOKEN")
    or FILE_ENV.get("EXECUTOR_API_TOKEN")
    or ""
)
EXECUTOR_HEADERS = (
    {"Authorization": f"Bearer {EXECUTOR_API_TOKEN}"}
    if EXECUTOR_API_TOKEN else {}
)


@pytest.mark.skipif(SKIP, reason="Set RUN_INTEGRATION_TESTS=1 to run integration tests")
class TestIntegration:
    def test_health_endpoint(self):
        # Assumes executor server is running on 5001 or main app on 5000
        resp = requests.get("http://localhost:5000/health", timeout=5)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_executor_bash(self):
        resp = requests.post(
            "http://localhost:5001/bash",
            json={"command": "echo hello_integration", "session_id": "int_test"},
            headers=EXECUTOR_HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "hello_integration" in data["stdout"]
        assert data["returncode"] == 0

    def test_executor_python(self):
        resp = requests.post(
            "http://localhost:5001/python",
            json={"code": "print(42)", "session_id": "int_test"},
            headers=EXECUTOR_HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "42" in data["stdout"]

    def test_executor_javascript(self):
        resp = requests.post(
            "http://localhost:5001/javascript",
            json={"code": "console.log(42)", "session_id": "int_test_js"},
            headers=EXECUTOR_HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["returncode"] == 0, data
        assert data["stdout"].strip() == "42"

    def test_executor_has_9router_runtime_dependencies(self):
        resp = requests.post(
            "http://localhost:5001/bash",
            json={
                "command": (
                    "command -v curl >/dev/null && command -v jq >/dev/null && "
                    "test -r /skills/9router/SKILL.md"
                ),
                "session_id": "int_test",
            },
            headers=EXECUTOR_HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        assert resp.json()["returncode"] == 0

    def test_repository_knowledge_mount_permissions(self):
        created = requests.post(
            "http://localhost:5001/bash",
            json={
                "command": (
                    "set -eu; "
                    "test -r /skills/9router/SKILL.md; "
                    "test ! -w /skills/9router/SKILL.md; "
                    "printf '# probe\\n' > /methods/.integration-method-probe.md"
                ),
                "session_id": "int_methods_writer",
            },
            headers=EXECUTOR_HEADERS,
            timeout=10,
        )
        assert created.status_code == 200
        assert created.json()["returncode"] == 0, created.json()

        reused = requests.post(
            "http://localhost:5001/bash",
            json={
                "command": (
                    "set -eu; probe=/methods/.integration-method-probe.md; "
                    "test -r \"$probe\"; test -w \"$probe\"; "
                    "printf 'reused\\n' >> \"$probe\"; rm -f \"$probe\""
                ),
                "session_id": "int_methods_reader",
            },
            headers=EXECUTOR_HEADERS,
            timeout=10,
        )
        assert reused.status_code == 200
        assert reused.json()["returncode"] == 0, reused.json()

    def test_persistent_dependencies_are_available_to_a_later_session(self):
        created = requests.post(
            "http://localhost:5001/bash",
            json={
                "command": (
                    "set -eu; "
                    "mkdir -p /dependencies/python "
                    "/dependencies/node/node_modules/persistent-probe "
                    "/dependencies/bin; "
                    "printf \"VALUE = 'persisted'\\n\" "
                    "> /dependencies/python/persistent_probe.py; "
                    "printf \"module.exports = 'persisted';\\n\" "
                    "> /dependencies/node/node_modules/persistent-probe/index.js; "
                    "printf '#!/bin/sh\\nprintf persisted\\n' "
                    "> /dependencies/bin/persistent-probe; "
                    "chmod +x /dependencies/bin/persistent-probe"
                ),
                "session_id": "int_dependency_writer",
            },
            headers=EXECUTOR_HEADERS,
            timeout=10,
        )
        assert created.status_code == 200
        assert created.json()["returncode"] == 0, created.json()

        reused = requests.post(
            "http://localhost:5001/bash",
            json={
                "command": (
                    "set -eu; "
                    "python -c \"import persistent_probe; "
                    "assert persistent_probe.VALUE == 'persisted'\"; "
                    "node -e \"if (require('persistent-probe') !== 'persisted') "
                    "process.exit(1)\"; "
                    "test \"$(persistent-probe)\" = persisted; "
                    "rm -f /dependencies/python/persistent_probe.py "
                    "/dependencies/bin/persistent-probe; "
                    "rm -rf /dependencies/node/node_modules/persistent-probe"
                ),
                "session_id": "int_dependency_reader",
            },
            headers=EXECUTOR_HEADERS,
            timeout=10,
        )
        assert reused.status_code == 200
        assert reused.json()["returncode"] == 0, reused.json()
