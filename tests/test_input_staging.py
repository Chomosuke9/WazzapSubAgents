"""Tests for the cross-process input-file staging fix.

Bug being guarded against: WazzapAgents stages input_files at host paths
that aren't bind-mounted into the executor sidecar, so the agent's
bash/python tools see "file not found" and the user gets back a "tidak
ditemukan pada path yang dipakai" message even though the bridge swore it
just staged the file. Re-staging into ``<workdir>/input/`` makes the
files visible inside the container regardless of how the bridge was
configured.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from src.input_staging import (
    INPUT_SUBDIR,
    is_input_path,
    stage_inputs_into_workdir,
)


@pytest.fixture
def workdir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def src_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _write(path: str, content: bytes = b"hello") -> None:
    with open(path, "wb") as f:
        f.write(content)


def test_returns_empty_list_when_no_inputs(workdir):
    assert stage_inputs_into_workdir(workdir, []) == []
    # No-op should not create the staging dir.
    assert not os.path.exists(os.path.join(workdir, INPUT_SUBDIR))


def test_copies_each_file_into_inputs_subdir(workdir, src_dir):
    foo = os.path.join(src_dir, "foo.zip")
    bar = os.path.join(src_dir, "bar.pdf")
    _write(foo, b"foo-bytes")
    _write(bar, b"bar-bytes")

    staged = stage_inputs_into_workdir(workdir, [foo, bar])

    assert len(staged) == 2
    assert all(p.startswith(os.path.join(workdir, INPUT_SUBDIR)) for p in staged)
    assert os.path.basename(staged[0]) == "foo.zip"
    assert os.path.basename(staged[1]) == "bar.pdf"
    # Bytes are copied (not just symlinked); container-side bash should be
    # able to read them even if the original source path is unreachable.
    with open(staged[0], "rb") as f:
        assert f.read() == b"foo-bytes"


def test_skips_missing_and_non_files(workdir, src_dir):
    real = os.path.join(src_dir, "real.txt")
    _write(real)
    missing = os.path.join(src_dir, "missing.txt")
    a_dir = os.path.join(src_dir, "a_directory")
    os.makedirs(a_dir)

    staged = stage_inputs_into_workdir(workdir, [real, missing, a_dir])

    assert len(staged) == 1
    assert os.path.basename(staged[0]) == "real.txt"


def test_resolves_basename_collisions(workdir, src_dir):
    a = os.path.join(src_dir, "a")
    b = os.path.join(src_dir, "b")
    os.makedirs(a)
    os.makedirs(b)
    src1 = os.path.join(a, "doc.zip")
    src2 = os.path.join(b, "doc.zip")
    _write(src1, b"first")
    _write(src2, b"second")

    staged = stage_inputs_into_workdir(workdir, [src1, src2])

    assert len(staged) == 2
    names = sorted(os.path.basename(p) for p in staged)
    assert names == ["doc.zip", "doc_1.zip"]
    # Both copies survive; nobody clobbers anyone.
    contents = sorted(open(p, "rb").read() for p in staged)
    assert contents == [b"first", b"second"]


def test_is_input_path_recognises_inputs_subdir(workdir):
    inputs_dir = os.path.join(workdir, INPUT_SUBDIR)
    os.makedirs(inputs_dir)
    inside = os.path.join(inputs_dir, "x.bin")
    _write(inside)

    assert is_input_path(workdir, inside) is True
    assert is_input_path(workdir, inputs_dir) is True


def test_is_input_path_rejects_other_paths(workdir):
    output = os.path.join(workdir, "result.bin")
    _write(output)
    nested_output = os.path.join(workdir, "subdir", "nested.txt")
    os.makedirs(os.path.dirname(nested_output))
    _write(nested_output)

    assert is_input_path(workdir, output) is False
    assert is_input_path(workdir, nested_output) is False
    assert is_input_path(workdir, "/etc/passwd") is False


def test_is_input_path_handles_empty_args():
    assert is_input_path("", "/a") is False
    assert is_input_path("/a", "") is False
