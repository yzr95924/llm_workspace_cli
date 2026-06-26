import os

import pytest

from wiki_workspace import errors, manifest, workspace


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


def test_load_toml_parses(tmp_path):
    f = tmp_path / "m.toml"
    f.write_text('schema_version = "1"\ncreated = "2026-06-26"\n', encoding="utf-8")
    data = workspace.load_toml(f)
    assert data["schema_version"] == "1"
    assert data["created"] == "2026-06-26"


def test_dump_toml_round_trips(tmp_path):
    data = {
        "schema_version": "1",
        "created": "2026-06-26",
        "workspace": {"default_model": "claude-sonnet-4-6"},
        "wikis": {
            "llm-systems": {
                "path": "llm-systems",
                "display_name": "LLM Systems",
                "description": "research",
                "model": "claude-opus-4-8",
                "created": "2026-06-26",
                "tags": ["research", "papers"],
            },
            "recipes": {
                "path": "recipes",
                "display_name": "Recipes",
                "created": "2026-06-20",
                "tags": [],
            },
        },
    }
    text = workspace.dump_toml(data)
    reparsed = workspace.load_toml_str(text)
    assert reparsed["wikis"]["llm-systems"]["model"] == "claude-opus-4-8"
    assert reparsed["wikis"]["recipes"]["tags"] == []
    assert reparsed["workspace"]["default_model"] == "claude-sonnet-4-6"


def test_dump_toml_escapes_quotes():
    data = {
        "schema_version": "1",
        "created": "2026-06-26",
        "workspace": {"default_model": "x"},
        "wikis": {
            "w": {
                "path": "w",
                "display_name": 'he said "hi"',
                "created": "2026-06-26",
                "tags": [],
            }
        },
    }
    text = workspace.dump_toml(data)
    assert '\\"' in text  # 引号被转义
    reparsed = workspace.load_toml_str(text)
    assert reparsed["wikis"]["w"]["display_name"] == 'he said "hi"'


def test_find_root_cli_flag_wins(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    (explicit / ".workspace.toml").write_text('schema_version = "1"\n', encoding="utf-8")
    env_root = tmp_path / "env"
    env_root.mkdir()
    monkeypatch.setenv("LLMW_WORKSPACE", str(env_root))
    assert workspace.find_root(cli_workspace=str(explicit)) == explicit.resolve()


def test_find_root_env_when_no_flag(tmp_path, monkeypatch):
    env_root = tmp_path / "env"
    env_root.mkdir()
    (env_root / ".workspace.toml").write_text('schema_version = "1"\n', encoding="utf-8")
    monkeypatch.setenv("LLMW_WORKSPACE", str(env_root))
    assert workspace.find_root(cli_workspace=None, cwd=tmp_path / "elsewhere") == env_root.resolve()


def test_find_root_walks_up_to_workspace_toml(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    (ws / "deep" / "dir").mkdir(parents=True)
    (ws / ".workspace.toml").write_text('schema_version = "1"\n', encoding="utf-8")
    monkeypatch.delenv("LLMW_WORKSPACE", raising=False)
    found = workspace.find_root(cli_workspace=None, cwd=ws / "deep" / "dir", home=tmp_path / "home")
    assert found == ws.resolve()


def test_find_root_falls_back_to_home_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LLMW_WORKSPACE", raising=False)
    home = tmp_path / "home"
    found = workspace.find_root(cli_workspace=None, cwd=tmp_path, home=home)
    assert found == (home / "llm_workspace").resolve()


def test_workspace_helpers(tmp_path):
    assert workspace.manifest_filename() == ".workspace.toml"
    assert workspace.is_initialized(tmp_path) is False
    (tmp_path / ".workspace.toml").write_text('schema_version = "1"\n', encoding="utf-8")
    assert workspace.is_initialized(tmp_path) is True


def test_save_manifest_writes_and_reparses(tmp_path):
    m = manifest.empty_manifest("2026-06-26")
    workspace.save_manifest(tmp_path, m)
    written = (tmp_path / ".workspace.toml").read_text(encoding="utf-8")
    assert "schema_version" in written
    manifest.parse(written)  # 重解析成功（无异常）


def test_save_manifest_raises_internal_on_reparse_failure(tmp_path, monkeypatch):
    m = manifest.empty_manifest("2026-06-26")
    # 让 serialize 写出不可解析的 TOML
    monkeypatch.setattr(manifest, "serialize", lambda _m: "this is = = not toml =")
    with pytest.raises(errors.CommandError) as ei:
        workspace.save_manifest(tmp_path, m)
    assert ei.value.exit_code == errors.EXIT_INTERNAL
    assert ei.value.category == "internal-state-corruption"
