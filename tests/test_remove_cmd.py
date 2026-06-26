from wiki_workspace import errors, manifest, workspace
from wiki_workspace.commands import remove_cmd


def _args(name, **kw):
    base = dict(workspace=None, json=False, name=name, purge=False, yes=False)
    base.update(kw)
    return type("A", (), base)()


def _seed(root, name="w", with_dir=True):
    if with_dir:
        d = root / name
        d.mkdir()
        (d / "CLAUDE.md").write_text("x", encoding="utf-8")
    m = manifest.Manifest(
        "1",
        "2026-06-26",
        "claude-sonnet-4-6",
        {
            name: manifest.WikiEntry(
                name=name, path=name, display_name=name.title(), created="2026-06-26"
            )
        },
    )
    workspace.save_manifest(root, m)


def test_remove_manifest_only(tmp_path):
    _seed(tmp_path)
    code = remove_cmd.run(_args("w", yes=True, workspace=str(tmp_path)))
    assert code == 0
    m, _ = manifest.load_and_validate(
        (tmp_path / ".workspace.toml").read_text(encoding="utf-8"), tmp_path
    )
    assert "w" not in m.wikis
    assert (tmp_path / "w").is_dir()  # 目录原样保留


def test_remove_purge_deletes_dir(tmp_path):
    _seed(tmp_path)
    code = remove_cmd.run(_args("w", yes=True, purge=True, workspace=str(tmp_path)))
    assert code == 0
    assert not (tmp_path / "w").exists()


def test_remove_purge_requires_yes(tmp_path):
    _seed(tmp_path)
    code = remove_cmd.run(_args("w", purge=True, yes=False, workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR
    assert (tmp_path / "w").exists()  # 什么都没删


def test_remove_not_found(tmp_path):
    _seed(tmp_path)
    code = remove_cmd.run(_args("ghost", yes=True, workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR
