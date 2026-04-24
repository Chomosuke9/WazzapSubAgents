#!/usr/bin/env bash
set -e

echo "Running unit tests (no docker required)..."
pytest tests/test_agent_tools.py tests/test_agent_loop.py tests/test_session_manager.py tests/test_container_client.py tests/test_docker_manager.py -v
