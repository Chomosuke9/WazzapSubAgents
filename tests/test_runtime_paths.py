import pytest

from src.runtime_paths import host_path_to_sandbox, sandbox_path_to_host


def test_host_and_sandbox_workdir_paths_round_trip(tmp_path):
    host_base = tmp_path / "work"
    host_file = host_base / "session-a" / "input" / "document.pdf"
    host_file.parent.mkdir(parents=True)
    host_file.write_bytes(b"pdf")

    sandbox_file = host_path_to_sandbox(str(host_file), host_base=str(host_base))

    assert sandbox_file == "/storage/subagent_work/session-a/input/document.pdf"
    assert sandbox_path_to_host(sandbox_file, host_base=str(host_base)) == str(
        host_file.resolve()
    )


def test_workdir_path_translation_rejects_paths_outside_roots(tmp_path):
    host_base = tmp_path / "work"
    host_base.mkdir()

    with pytest.raises(ValueError, match="outside WORKDIR_BASE"):
        host_path_to_sandbox(str(tmp_path / "outside.txt"), host_base=str(host_base))
    with pytest.raises(ValueError, match="outside the sandbox workdir"):
        sandbox_path_to_host("/etc/passwd", host_base=str(host_base))
