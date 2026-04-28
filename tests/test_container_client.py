from unittest.mock import MagicMock, patch

import pytest
import requests

from src.container_client import ContainerClient


def test_run_bash():
    client = ContainerClient("http://localhost:5001")
    with patch.object(requests, "post", return_value=MagicMock(status_code=200, json=lambda: {"returncode": 0})) as mock_post:
        result = client.run_bash("echo hi")
        assert result["returncode"] == 0
        mock_post.assert_called_once()


def test_run_python():
    client = ContainerClient("http://localhost:5001")
    with patch.object(requests, "post", return_value=MagicMock(status_code=200, json=lambda: {"stdout": "42\n", "stderr": "", "returncode": 0})) as mock_post:
        result = client.run_python("print(42)")
        assert result["stdout"] == "42\n"
        assert result["returncode"] == 0


def test_health_check_ok():
    client = ContainerClient("http://localhost:5001")
    with patch.object(requests, "get", return_value=MagicMock(status_code=200)):
        assert client.health_check() is True


def test_health_check_fail():
    client = ContainerClient("http://localhost:5001")
    with patch.object(requests, "get", side_effect=requests.exceptions.ConnectionError()):
        assert client.health_check() is False


def test_retry_on_500():
    client = ContainerClient("http://localhost:5001", max_retries=3)
    responses = [
        MagicMock(status_code=500, raise_for_status=lambda: (_ for _ in ()).throw(requests.exceptions.HTTPError(response=MagicMock(status_code=500)))),
        MagicMock(status_code=200, json=lambda: {"returncode": 0}),
    ]
    with patch.object(requests, "post", side_effect=responses) as mock_post:
        result = client.run_bash("echo hi")
        assert result["returncode"] == 0
        assert mock_post.call_count == 2
