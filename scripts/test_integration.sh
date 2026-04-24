#!/usr/bin/env bash
set -e

echo "Running integration tests (requires docker)..."
export RUN_INTEGRATION_TESTS=1
pytest tests/test_integration.py -v
