import json

from wiki_workspace import errors


def test_exit_code_constants():
    assert errors.EXIT_OK == 0
    assert errors.EXIT_USER_ERROR == 1
    assert errors.EXIT_ENV_ERROR == 2
    assert errors.EXIT_INTERNAL == 3


def test_emit_error_writes_to_stderr(capsys):
    errors.emit_error("wiki-not-found", "no such wiki 'foo'", hint="llmw list")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[ERROR]" in captured.err
    assert "wiki-not-found" in captured.err
    assert "no such wiki 'foo'" in captured.err
    assert "llmw list" in captured.err


def test_emit_warn_suppressed_when_quiet(capsys):
    errors.configure(quiet=True)
    errors.emit_warn("be careful")
    assert capsys.readouterr().err == ""


def test_emit_warn_shown_by_default(capsys):
    errors.emit_warn("be careful")
    assert "[WARN]" in capsys.readouterr().err


def test_emit_debug_only_when_debug(capsys):
    errors.emit_debug("secret")
    assert capsys.readouterr().err == ""
    errors.configure(debug=True)
    errors.emit_debug("secret")
    assert "[DEBUG]" in capsys.readouterr().err


def test_render_json_envelope():
    out = errors.render_json_result(
        exit_code=1,
        errors=[
            errors.ErrorRecord("invalid-wiki-name", "'Foo' must be kebab-case", "llmw add foo")
        ],
    )
    obj = json.loads(out)
    assert obj["exit_code"] == 1
    assert obj["errors"][0]["category"] == "invalid-wiki-name"
    assert obj["errors"][0]["hint"] == "llmw add foo"


def test_command_error_carries_exit_code():
    err = errors.CommandError(errors.EXIT_USER_ERROR, "wiki-not-found", "msg")
    assert err.exit_code == 1
    assert err.category == "wiki-not-found"
