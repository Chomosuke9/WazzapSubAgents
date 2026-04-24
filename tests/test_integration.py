import os
import time

import pytest
import requests

# These integration tests require a running docker daemon and may build images.
# They are skipped by default unless RUN_INTEGRATION_TESTS=1 is set.

SKIP = not os.getenv("RUN_INTEGRATION_TESTS")


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
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "42" in data["output"]
