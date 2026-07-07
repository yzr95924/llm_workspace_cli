"""llmw wiki rename: happy + error paths + 原子性 (staging 清理)。

按 MEMORY 短条目"测试优先级低 — prototype 阶段不写自动化测试,跑通后补;
agent 不主动加测试代码"。本次实现同步补基本 happy path + 关键 error + 原子性回归,
后续补充覆盖由维护者按需添加。
"""

from pathlib import Path

import pytest

from llmw.errors import (
    InvalidWikiName,
    WikiExists,
    WikiNotFound,
)
from llmw.wiki import manager as wiki_mgr
from llmw.wiki import store as wiki_store
from llmw.workspace import store as ws_store


# ===== happy path =====


def test_rename_happy_path(workspace_with_wiki: Path, capsys):
    """foo → bar: 3 处全改 (workspace.toml key, 目录名, meta.name)。"""
    ws_root = workspace_with_wiki
    old_dir = ws_root / "foo"

    wiki_mgr.rename(ws_root, "foo", "bar")

    # 1. workspace.toml 切换
    ws = ws_store.load(ws_root)
    assert "foo" not in ws.wikis
    assert "bar" in ws.wikis
    # created_at 保留
    assert ws.wikis["bar"].created_at == "2026-01-01T00:00:00Z"
    assert ws.wikis["bar"].path == "bar"

    # 2. 子目录改名,旧目录消失
    assert not old_dir.exists()
    new_dir = ws_root / "bar"
    assert new_dir.is_dir()

    # 3. wiki_metadata.toml name 改写
    meta = wiki_store.load(new_dir)
    assert meta.name == "bar"

    # 4. 原有内容保留 (copytree 验证)
    assert (new_dir / "CLAUDE.md").read_text(encoding="utf-8") == "# foo scaffold\n"

    # 5. 打印信息含 old → new + path
    out = capsys.readouterr().out
    assert "foo" in out and "bar" in out
    assert "path" in out


def test_rename_topic_syncs_when_default(workspace_with_wiki: Path):
    """topic 默认值 == old (add 时未传 --topic) → 同步成 new。"""
    ws_root = workspace_with_wiki
    wiki_mgr.rename(ws_root, "foo", "bar")
    meta = wiki_store.load(ws_root / "bar")
    assert meta.topic == "bar"


def test_rename_topic_preserved_when_custom(workspace_with_wiki: Path):
    """topic 与 old 不同 → 不动 topic。"""
    ws_root = workspace_with_wiki
    # 改 foo 的 topic 为自定义值
    foo_dir = ws_root / "foo"
    meta = wiki_store.load(foo_dir)
    meta.topic = "My Custom Topic"
    wiki_store.save(foo_dir, meta)

    wiki_mgr.rename(ws_root, "foo", "bar")
    meta = wiki_store.load(ws_root / "bar")
    assert meta.topic == "My Custom Topic"
    assert meta.name == "bar"


def test_rename_json_output(workspace_with_wiki: Path, capsys):
    """--json 模式输出可解析 JSON,含 topic_changed 等关键字段。"""
    import json

    wiki_mgr.rename(workspace_with_wiki, "foo", "bar", as_json=True)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["old"] == "foo"
    assert data["new"] == "bar"
    assert data["topic_changed"] is True
    assert data["topic_old"] == "foo"
    assert data["topic_new"] == "bar"
    assert data["created_at"] == "2026-01-01T00:00:00Z"
    assert data["path"].endswith("/bar")


def test_rename_quiet_suppresses_info(workspace_with_wiki: Path, capsys):
    """--quiet 只打一行,不打 path / topic / created_at 行。"""
    wiki_mgr.rename(workspace_with_wiki, "foo", "bar", quiet=True)
    out = capsys.readouterr().out
    assert "wiki 已重命名" in out
    assert "path:" not in out
    assert "created_at" not in out


# ===== error paths =====


def test_rename_new_already_in_registry(workspace_with_two_wikis: Path):
    """new 已是另一个 wiki → WikiExists,foo 与 bar 均不变。"""
    ws_root = workspace_with_two_wikis
    with pytest.raises(WikiExists):
        wiki_mgr.rename(ws_root, "foo", "bar")

    # 状态完全不变
    ws = ws_store.load(ws_root)
    assert set(ws.wikis) == {"foo", "bar"}
    assert (ws_root / "foo").is_dir()
    assert (ws_root / "bar").is_dir()


def test_rename_old_not_found(workspace_with_wiki: Path):
    with pytest.raises(WikiNotFound):
        wiki_mgr.rename(workspace_with_wiki, "nonexistent", "bar")


def test_rename_same_name_rejected(workspace_with_wiki: Path):
    """old == new → InvalidWikiName (带 hint),原件不动。"""
    with pytest.raises(InvalidWikiName) as exc_info:
        wiki_mgr.rename(workspace_with_wiki, "foo", "foo")
    assert "无变更" in str(exc_info.value)
    # 原件仍存在
    assert (workspace_with_wiki / "foo").is_dir()


def test_rename_invalid_new_name_format(workspace_with_wiki: Path):
    """new 含大写字母 → InvalidWikiName (NAME_RE 检查)。"""
    with pytest.raises(InvalidWikiName):
        wiki_mgr.rename(workspace_with_wiki, "foo", "FOO")


def test_rename_new_path_exists_on_disk(workspace_with_wiki: Path):
    """new 不在 registry 但 fs 上已有同名目录 (残留空目录) → WikiExists。"""
    ws_root = workspace_with_wiki
    stray = ws_root / "bar"
    stray.mkdir()
    (stray / "garbage.txt").write_text("x", encoding="utf-8")

    with pytest.raises(WikiExists):
        wiki_mgr.rename(ws_root, "foo", "bar")

    # 残留目录未动
    assert stray.is_dir()
    assert (stray / "garbage.txt").exists()
    # 原 foo 仍存在
    assert (ws_root / "foo").is_dir()


# ===== 原子性: staging 清理 =====


def test_rename_staging_cleaned_on_happy_path(workspace_with_wiki: Path):
    """成功路径下 .llmw-trash/rename-*-to-* staging 已被切到新名,不应残留。"""
    ws_root = workspace_with_wiki
    wiki_mgr.rename(ws_root, "foo", "bar")

    trash = ws_root / ".llmw-trash"
    if trash.exists():
        leftovers = list(trash.glob("rename-*-to-*"))
        assert not leftovers, f"staging 未清理: {leftovers}"


def test_rename_staging_cleaned_on_phase2_failure(
    workspace_with_wiki: Path, monkeypatch
):
    """Phase 2 (workspace.toml save) 失败 → staging 必须被清掉,原件不动。"""
    from llmw.wiki import manager as m

    def boom(*args, **kwargs):
        raise OSError("simulated workspace.toml write failure")

    # 在 ws_store.save 调用前一步 patch(Phase 2 第一行 ws.wikis[new] = 之后,
    # 但 save 调用点前;实际通过 monkeypatch 整个 ws_store.save 即可)
    monkeypatch.setattr(m.ws_store, "save", boom)

    with pytest.raises(OSError, match="simulated"):
        m.rename(workspace_with_wiki, "foo", "bar")

    # staging 必须清理
    trash = workspace_with_wiki / ".llmw-trash"
    if trash.exists():
        leftovers = list(trash.glob("rename-*-to-*"))
        assert not leftovers, f"staging 残留: {leftovers}"

    # 原件不动
    assert (workspace_with_wiki / "foo").is_dir()
    ws = ws_store.load(workspace_with_wiki)
    assert "foo" in ws.wikis
    assert "bar" not in ws.wikis


def test_rename_staging_cleaned_on_phase3_failure(
    workspace_with_wiki: Path, monkeypatch
):
    """Phase 3 (atomic rename) 失败 → staging 清理 + workspace.toml 回滚。"""
    from llmw.wiki import manager as m

    # 强制 staging.rename 抛 OSError(模拟 POSIX rename 失败)
    def boom_rename(self, *args, **kwargs):
        raise OSError("simulated atomic rename failure")

    monkeypatch.setattr(m.Path, "rename", boom_rename)

    with pytest.raises(OSError, match="simulated"):
        m.rename(workspace_with_wiki, "foo", "bar")

    # staging 必须清理
    trash = workspace_with_wiki / ".llmw-trash"
    if trash.exists():
        leftovers = list(trash.glob("rename-*-to-*"))
        assert not leftovers, f"staging 残留: {leftovers}"

    # workspace.toml 必须回滚
    ws = ws_store.load(workspace_with_wiki)
    assert "foo" in ws.wikis, "workspace.toml 未回滚,foo 丢失"
    assert "bar" not in ws.wikis, "workspace.toml 未回滚,残留 bar"

    # foo 元数据未变
    assert (workspace_with_wiki / "foo").is_dir()
