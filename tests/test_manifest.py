from wiki_workspace import manifest

SAMPLE = """\
schema_version = "1"
created = "2026-06-26"

[workspace]
default_model = "claude-sonnet-4-6"

[wikis.llm-systems]
path = "llm-systems"
display_name = "LLM Systems"
description = "research"
model = "claude-opus-4-8"
created = "2026-06-26"
tags = ["research", "papers"]
"""


def test_parse_builds_manifest():
    m = manifest.parse(SAMPLE)
    assert m.schema_version == "1"
    assert m.created == "2026-06-26"
    assert m.default_model == "claude-sonnet-4-6"
    w = m.wikis["llm-systems"]
    assert w.display_name == "LLM Systems"
    assert w.model == "claude-opus-4-8"
    assert w.tags == ["research", "papers"]


def test_parse_missing_fields_default():
    m = manifest.parse(
        'schema_version = "1"\ncreated = "2026-06-26"\n[workspace]\ndefault_model = "x"\n'
    )
    assert m.wikis == {}


def test_serialize_round_trips(tmp_path):
    m = manifest.parse(SAMPLE)
    text = manifest.serialize(m)
    m2 = manifest.parse(text)
    assert m2.wikis["llm-systems"].tags == ["research", "papers"]
    assert m2.default_model == "claude-sonnet-4-6"


def test_empty_manifest_helper():
    m = manifest.empty_manifest("2026-06-26")
    assert m.schema_version == "1"
    assert m.wikis == {}
    assert m.default_model == "claude-sonnet-4-6"


def test_wiki_entry_defaults():
    e = manifest.WikiEntry(name="r", path="r", display_name="R", created="2026-06-26")
    assert e.description == ""
    assert e.model is None
    assert e.tags == []


def _entry(name, **kw):
    base = dict(path=name, display_name=name.title(), created="2026-06-26")
    base.update(kw)
    return manifest.WikiEntry(name=name, **base)


def _manifest(wikis):
    return manifest.Manifest("1", "2026-06-26", "claude-sonnet-4-6", {w.name: w for w in wikis})


def test_validate_clean(tmp_path):
    ws = tmp_path
    (ws / "llm-systems").mkdir()
    (ws / "llm-systems" / "CLAUDE.md").write_text("x", encoding="utf-8")
    m = _manifest([_entry("llm-systems")])
    issues = manifest.validate(m, ws)
    assert [i for i in issues if i.severity == "error"] == []


def test_validate_path_missing(tmp_path):
    m = _manifest([_entry("ghost")])
    issues = manifest.validate(m, tmp_path)
    errs = [i for i in issues if i.severity == "error"]
    assert errs and "不存在" in errs[0].message


def test_validate_missing_claude_md(tmp_path):
    (tmp_path / "w").mkdir()
    m = _manifest([_entry("w")])
    issues = manifest.validate(m, tmp_path)
    errs = [i for i in issues if i.severity == "error"]
    assert errs and "CLAUDE.md" in errs[0].message


def test_validate_bad_name():
    m = _manifest([_entry("Bad_Name", path="x")])
    issues = manifest.validate(m, "/tmp")
    assert any(i.category == "manifest-validation-failed" and "kebab" in i.message for i in issues)


def test_validate_path_escape(tmp_path):
    m = _manifest([_entry("evil", path="../escape")])
    issues = manifest.validate(m, tmp_path)
    assert any(
        "位于 workspace 内" in i.message or ".." in i.message
        for i in issues
        if i.severity == "error"
    )


def test_validate_unknown_model_warns_not_fails(tmp_path):
    (tmp_path / "w").mkdir()
    (tmp_path / "w" / "CLAUDE.md").write_text("x", encoding="utf-8")
    m = _manifest([_entry("w", model="claude-bogus-9")])
    issues = manifest.validate(m, tmp_path)
    assert any(i.severity == "warn" and "未知" in i.message for i in issues)
    assert not [i for i in issues if i.severity == "error"]


def test_validate_bad_date():
    m = _manifest([_entry("w", created="06/26/2026")])
    issues = manifest.validate(m, "/tmp")
    assert any("YYYY-MM-DD" in i.message for i in issues if i.severity == "error")


def test_load_and_validate_returns_manifest_and_issues(tmp_path):
    (tmp_path / "w").mkdir()
    (tmp_path / "w" / "CLAUDE.md").write_text("x", encoding="utf-8")
    text = manifest.serialize(_manifest([_entry("w")]))
    m, issues = manifest.load_and_validate(text, tmp_path)
    assert isinstance(m, manifest.Manifest)
    assert [i for i in issues if i.severity == "error"] == []
