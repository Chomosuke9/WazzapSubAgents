from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_skills_are_not_baked_into_the_image():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY skills/" not in dockerfile
    assert "COPY dependencies/" not in dockerfile
    assert "COPY main.py" not in dockerfile
    assert "COPY src/ ./src/" not in dockerfile
    assert "COPY src/executor_server.py" in dockerfile
    assert 'CMD ["python", "-m", "src.executor_server"]' in dockerfile


def test_obsolete_two_container_compose_layout_is_removed():
    assert not (PROJECT_ROOT / "docker-compose.yml").exists()


def test_main_has_no_external_or_auto_executor_mode():
    source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    assert "external" not in source
    assert "executor_management_mode" not in source


def test_downloaded_dependencies_are_not_committed_or_baked():
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "dependencies/" in dockerignore
    assert "dependencies/*" in gitignore
    assert "!dependencies/.dependencies-root" in gitignore
    assert "!dependencies/README.md" in gitignore
