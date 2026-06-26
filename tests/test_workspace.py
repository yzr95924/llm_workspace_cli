import os

from wiki_workspace import workspace


def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "out.toml"
    workspace.atomic_write(target, "hello\n")
    assert target.read_text(encoding="utf-8") == "hello\n"


def test_atomic_write_overwrites(tmp_path):
    target = tmp_path / "out.toml"
    target.write_text("old", encoding="utf-8")
    workspace.atomic_write(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_no_partial_on_failure(tmp_path, monkeypatch):
    """os.replace 炸了，目标文件必须原样不动，且不留 tmp 残留。"""
    target = tmp_path / "out.toml"
    target.write_text("keep", encoding="utf-8")

    def boom(*a, **k):
        raise OSError("simulated")

    monkeypatch.setattr(os, "replace", boom)
    try:
        workspace.atomic_write(target, "new")
    except OSError:
        pass

    assert target.read_text(encoding="utf-8") == "keep"
    assert not list(tmp_path.glob(".*.tmp"))
