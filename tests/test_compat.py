from wiki_workspace import _compat


def test_find_skill_root_env_var(tmp_path, monkeypatch, fake_skill):
    monkeypatch.setenv("LLM_WIKI_MANAGEMENT_PATH", str(fake_skill))
    assert _compat.find_skill_root(workspace_root=tmp_path) == fake_skill.resolve()


def test_find_skill_root_sibling(tmp_path, monkeypatch, fake_skill):
    # workspace 在 tmp_path/ws，skill 同级在 tmp_path/llm-wiki-management（fake_skill 已是）
    monkeypatch.delenv("LLM_WIKI_MANAGEMENT_PATH", raising=False)
    ws = tmp_path / "ws"
    ws.mkdir()
    assert _compat.find_skill_root(workspace_root=ws) == fake_skill.resolve()


def test_find_skill_root_installed(tmp_path, monkeypatch, fake_skill):
    monkeypatch.delenv("LLM_WIKI_MANAGEMENT_PATH", raising=False)
    installed = tmp_path / "home" / ".claude" / "skills" / "llm-wiki-management"
    installed.mkdir(parents=True)
    (installed / "SKILL.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(_compat, "_HOME_SKILL_PATH", installed, raising=False)
    assert _compat.find_skill_root(workspace_root=tmp_path) == installed.resolve()


def test_find_skill_root_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_WIKI_MANAGEMENT_PATH", raising=False)
    monkeypatch.setattr(_compat, "_HOME_SKILL_PATH", tmp_path / "nope", raising=False)
    assert _compat.find_skill_root(workspace_root=tmp_path / "ws") is None


def test_slugify_matches_real_when_skill_present(fake_skill):
    _compat.configure(fake_skill)
    assert _compat.slugify("LLM Systems!!") == "llm-systems"


def test_slugify_stub_when_missing(tmp_path):
    _compat.configure(None)
    assert _compat.slugify("LLM Systems!!") == "llm-systems"  # stub 同结果


def test_parse_frontmatter_stub_when_missing():
    _compat.configure(None)
    assert _compat.parse_frontmatter_simple("no frontmatter here") == {}


def test_parse_frontmatter_real_when_present(fake_skill):
    _compat.configure(fake_skill)
    text = '---\ntitle: "X"\ntags: ["a", "b"]\n---\nbody'
    result = _compat.parse_frontmatter_simple(text)
    assert result["title"] == "X"
    assert result["tags"] == ["a", "b"]


def test_configure_loads_real_scripts(tmp_path):
    """configure() 真正经 importlib 加载 skill 的 scripts/setup_wiki.py 与
    ingest_diff.py，取出真 slugify / parse_frontmatter_simple（覆盖
    _load_module 成功返回路径 + 真 func 提取）。"""
    skill = tmp_path / "llm-wiki-management"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("# x\n", encoding="utf-8")
    (skill / "scripts" / "setup_wiki.py").write_text(
        "def slugify(name):\n    return 'REAL-' + name\n", encoding="utf-8"
    )
    (skill / "scripts" / "ingest_diff.py").write_text(
        "def parse_frontmatter_simple(text):\n    return {'real': True}\n", encoding="utf-8"
    )
    _compat.configure(skill)
    assert _compat.slugify("foo") == "REAL-foo"  # 真 slugify，非 stub
    assert _compat.parse_frontmatter_simple("anything") == {"real": True}


def test_parse_frontmatter_stub_multiline_and_empty_list(tmp_path):
    """stub 的缩进多行列表、空列表、循环结束时的 flush 分支。"""
    _compat.configure(None)
    text = "---\naliases: []\nrelated:\n  - a\n  - b\n---\nbody"
    r = _compat.parse_frontmatter_simple(text)
    assert r["aliases"] == []
    assert r["related"] == ["a", "b"]
