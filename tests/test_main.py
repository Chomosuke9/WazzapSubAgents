from unittest.mock import MagicMock

import main


def _manager(*, image_current: bool, running: bool, current_container: bool = True):
    manager = MagicMock()
    manager.image_is_current.return_value = image_current
    manager.container_running.return_value = running
    manager.container_uses_current_image.return_value = current_container
    return manager


def test_host_service_builds_and_starts_its_sandbox(monkeypatch):
    manager = _manager(image_current=False, running=False)
    manager_factory = MagicMock(return_value=manager)
    app = MagicMock()
    create = MagicMock(return_value=app)
    monkeypatch.setitem(main.config, "executor_port", 5123)
    monkeypatch.setattr(main, "DockerManager", manager_factory)
    monkeypatch.setattr(main, "create_app", create)

    assert main.build_app() is app

    manager_factory.assert_called_once_with(container_port=5123)
    manager.build_image.assert_called_once_with()
    manager.start_container.assert_called_once_with()
    manager.wait_for_container_ready.assert_called_once_with(timeout=30)
    create.assert_called_once_with(docker_mgr=manager)


def test_host_service_replaces_stale_running_sandbox(monkeypatch):
    manager = _manager(image_current=False, running=True)
    monkeypatch.setattr(main, "DockerManager", MagicMock(return_value=manager))
    monkeypatch.setattr(main, "create_app", MagicMock())

    main.build_app()

    manager.stop_container.assert_called_once_with()
    manager.build_image.assert_called_once_with()
    manager.start_container.assert_called_once_with()


def test_host_service_reuses_current_running_sandbox(monkeypatch):
    manager = _manager(image_current=True, running=True, current_container=True)
    monkeypatch.setattr(main, "DockerManager", MagicMock(return_value=manager))
    monkeypatch.setattr(main, "create_app", MagicMock())

    main.build_app()

    manager.stop_container.assert_not_called()
    manager.build_image.assert_not_called()
    manager.start_container.assert_not_called()
    manager.wait_for_container_ready.assert_called_once_with(timeout=30)
