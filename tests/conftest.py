import pytest


@pytest.fixture
def workspace_factory(tmp_path):
    """返回一个 callable，用来构造 workspace 目录 + 最小 .workspace.toml。"""

    def make(name="ws", wikis=None):
        root = tmp_path / name
        root.mkdir()
        return root

    return make


@pytest.fixture
def fake_skill(tmp_path):
    """构造一个假的 llm-wiki-management checkout，含 scripts/ + references/。"""

    root = tmp_path / "llm-wiki-management"
    (root / "scripts").mkdir(parents=True)
    (root / "references").mkdir(parents=True)
    (root / "SKILL.md").write_text("# fake skill\n", encoding="utf-8")
    (root / "references" / "claude-md-template.md").write_text(
        "# {{TOPIC_NAME}}\nsetup {{SETUP_DATE}}\n", encoding="utf-8"
    )
    return root
