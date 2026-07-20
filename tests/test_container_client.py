from unittest.mock import MagicMock, patch

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
    with patch.object(requests, "post", return_value=MagicMock(status_code=200, json=lambda: {"stdout": "42\n", "stderr": "", "returncode": 0})):
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


def test_run_bash_passes_timeout():
    client = ContainerClient("http://localhost:5001")
    with patch.object(requests, "post", return_value=MagicMock(status_code=200, json=lambda: {"returncode": 0})) as mock_post:
        result = client.run_bash("sleep 5", timeout=3)
        assert result["returncode"] == 0
        call_args = mock_post.call_args
        assert call_args.kwargs["json"]["timeout"] == 3
        assert call_args.kwargs["timeout"] == 8


def test_run_python_passes_timeout():
    client = ContainerClient("http://localhost:5001")
    with patch.object(requests, "post", return_value=MagicMock(status_code=200, json=lambda: {"stdout": "ok", "returncode": 0})) as mock_post:
        client.run_python("print('ok')", timeout=7)
        call_args = mock_post.call_args
        assert call_args.kwargs["json"]["timeout"] == 7
        assert call_args.kwargs["timeout"] == 12


def test_retry_reuses_idempotency_key():
    client = ContainerClient("http://localhost:5001", max_retries=2)
    responses = [
        requests.exceptions.ReadTimeout("response lost"),
        MagicMock(status_code=200, json=lambda: {"returncode": 0}),
    ]
    with patch.object(requests, "post", side_effect=responses) as mock_post, \
            patch("src.container_client.time.sleep"):
        assert client.run_bash("echo once")["returncode"] == 0

    first_id = mock_post.call_args_list[0].kwargs["json"]["request_id"]
    second_id = mock_post.call_args_list[1].kwargs["json"]["request_id"]
    assert first_id == second_id


def test_executor_token_is_sent_as_bearer_header():
    client = ContainerClient("http://localhost:5001", api_token="secret-token")
    response = MagicMock(status_code=200, json=lambda: {"returncode": 0})
    with patch.object(requests, "post", return_value=response) as mock_post:
        client.run_bash("echo authenticated")

    assert mock_post.call_args.kwargs["headers"] == {
        "Authorization": "Bearer secret-token",
    }
