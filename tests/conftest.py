"""pytest 共享 fixture: 构造最小 workspace + wiki 用于 rename 测试。

rename 测试只关心 workspace.toml + wiki 子目录 + wiki_metadata.toml;
不需要 CLAUDE.md / wiki/ / raw/ 等 wiki 骨架(由 SKILL fixtures 渲染)。
因此手工构造 fixture,不依赖 init_wiki.render_and_write(避免耦合 my_SKILL)。
"""

from pathlib import Path

import pytest

from llmw.wiki import store as wiki_store
from llmw.workspace import store as ws_store


@pytest.fixture
def workspace_with_wiki(tmp_path: Path) -> Path:
    """构造最小 workspace + 一个 wiki ``foo``(topic 默认=foo)。

    Returns:
        tmp_path: 既是 workspace 根,也是 wiki ``foo`` 父目录
    """
    # workspace.toml (含 wiki foo 注册)
    ws = ws_store.create_skeleton(tmp_path)
    ws.wikis["foo"] = ws_store.WikiEntry(
        name="foo", path="foo", created_at="2026-01-01T00:00:00Z"
    )
    ws_store.save(tmp_path, ws)

    # foo/wiki_metadata.toml (topic=foo 模拟 add 默认行为)
    foo_dir = tmp_path / "foo"
    foo_dir.mkdir()
    wiki_store.create_skeleton(foo_dir, name="foo", topic="foo")

    # 放一个 dummy 文件,验证 copytree 后内容保留
    (foo_dir / "CLAUDE.md").write_text("# foo scaffold\n", encoding="utf-8")

    return tmp_path


@pytest.fixture
def workspace_with_two_wikis(tmp_path: Path) -> Path:
    """workspace + 两个 wiki (foo / bar),用于冲突测试。"""
    ws = ws_store.create_skeleton(tmp_path)
    for name, ca in [("foo", "2026-01-01T00:00:00Z"), ("bar", "2026-02-01T00:00:00Z")]:
        ws.wikis[name] = ws_store.WikiEntry(name=name, path=name, created_at=ca)
    ws_store.save(tmp_path, ws)
    for name in ("foo", "bar"):
        d = tmp_path / name
        d.mkdir()
        wiki_store.create_skeleton(d, name=name, topic=name)
    return tmp_path
