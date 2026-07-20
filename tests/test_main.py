from unittest.mock import MagicMock

import main


def test_auto_mode_treats_compose_dns_as_external(monkeypatch):
    monkeypatch.setitem(main.config, "executor_management_mode", "auto")
    monkeypatch.setitem(
        main.config,
        "container_executor_url",
        "http://executor-executor:5001",
    )
    assert main._executor_management_mode() == "external"


def test_auto_mode_manages_loopback_executor(monkeypatch):
    monkeypatch.setitem(main.config, "executor_management_mode", "auto")
    monkeypatch.setitem(
        main.config,
        "container_executor_url",
        "http://127.0.0.1:5001",
    )
    assert main._executor_management_mode() == "managed"


def test_external_mode_uses_configured_executor_url(monkeypatch):
    url = "http://executor-executor:5001"
    app = MagicMock()
    waited: list[str] = []
    monkeypatch.setitem(main.config, "executor_management_mode", "external")
    monkeypatch.setitem(main.config, "container_executor_url", url)
    monkeypatch.setattr(main, "_wait_for_external_executor", waited.append)
    create = MagicMock(return_value=app)
    monkeypatch.setattr(main, "create_app", create)

    assert main.build_app() is app
    assert waited == [url]
    create.assert_called_once_with(docker_mgr=None, container_url=url)
