#!/usr/bin/env bash
set -e

echo "Running the full non-integration test suite..."
pytest -q
