from wiki_workspace import errors, manifest, workspace
from wiki_workspace.commands import show_cmd


def _args(name, **kw):
    base = dict(workspace=None, json=False, name=name)
    base.update(kw)
    return type("A", (), base)()


def _seed_full(root, name="llm-systems"):
    d = root / name
    (d / "wiki" / "sources").mkdir(parents=True)
    (d / "wiki" / "concepts").mkdir(parents=True)
    (d / "CLAUDE.md").write_text("# " + name, encoding="utf-8")
    (d / "wiki" / "log.md").write_text(
        '---\ntitle: "Log"\n---\n## [2026-06-25] ingest | Attention\n', encoding="utf-8"
    )
    (d / "wiki" / "sources" / "a.md").write_text("x", encoding="utf-8")
    m = manifest.Manifest(
        "1",
        "2026-06-26",
        "claude-sonnet-4-6",
        {
            name: manifest.WikiEntry(
                name=name,
                path=name,
                display_name="LLM Systems",
                created="2026-06-26",
                model="claude-opus-4-8",
                tags=["research"],
            )
        },
    )
    workspace.save_manifest(root, m)


def test_show_basic(tmp_path, capsys):
    _seed_full(tmp_path)
    code = show_cmd.run(_args("llm-systems", workspace=str(tmp_path)))
    out = capsys.readouterr().out
    assert code == 0
    assert "llm-systems" in out
    assert "claude-opus-4-8" in out


def test_show_counts_and_log(tmp_path, capsys, fake_skill, monkeypatch):
    monkeypatch.setenv("LLM_WIKI_MANAGEMENT_PATH", str(fake_skill))
    _seed_full(tmp_path)
    show_cmd.run(_args("llm-systems", workspace=str(tmp_path)))
    out = capsys.readouterr().out
    assert "sources: 1" in out
    assert "ingest" in out  # log 条目被带出


def test_show_not_found(tmp_path):
    _seed_full(tmp_path)
    code = show_cmd.run(_args("ghost", workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR


def test_show_skill_missing_warns(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("LLM_WIKI_MANAGEMENT_PATH", str(tmp_path / "nope"))
    # 隔离：屏蔽真实的 ~/.claude/skills/llm-wiki-management
    from wiki_workspace import _compat

    monkeypatch.setattr(_compat, "_HOME_SKILL_PATH", tmp_path / "no-skill", raising=False)
    _seed_full(tmp_path)
    code = show_cmd.run(_args("llm-systems", workspace=str(tmp_path)))
    err = capsys.readouterr().err
    assert code == 0
    assert "[WARN]" in err  # 优雅降级
