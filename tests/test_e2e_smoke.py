import contextlib
import io
import json

from wiki_workspace import cli, workspace
from wiki_workspace.commands import add_cmd


def test_init_add_list_show_config_remove(tmp_path, monkeypatch, fake_skill):
    monkeypatch.setattr(workspace, "today_iso", lambda: "2026-06-26")
    monkeypatch.setenv("LLMW_WORKSPACE", str(tmp_path))

    # 假装 setup_wiki.py 成功
    def fake(cmd, **kw):
        root = __import__("pathlib").Path(cmd[-1])
        root.mkdir(parents=True, exist_ok=True)
        (root / "CLAUDE.md").write_text("# " + cmd[-2], encoding="utf-8")
        (root / "wiki").mkdir(exist_ok=True)

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(add_cmd.subprocess, "run", fake)

    ws = tmp_path / "ws"
    assert cli.main(["init", "-w", str(ws)]) == 0
    assert (
        cli.main(
            [
                "add",
                "llm-systems",
                "--display-name",
                "LLM Systems",
                "--topic",
                "LLM Systems",
                "-w",
                str(ws),
                "--tag",
                "research",
            ]
        )
        == 0
    )

    # list --json
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(["list", "--json", "-w", str(ws)])
    assert code == 0
    obj = json.loads(buf.getvalue())
    assert obj["result"]["wikis"][0]["name"] == "llm-systems"

    # show（经 env 指到 skill）
    assert cli.main(["show", "llm-systems", "-w", str(ws)]) == 0

    # config set
    assert (
        cli.main(["config", "llm-systems", "set", "description", "research notes", "-w", str(ws)])
        == 0
    )

    # remove（仅 manifest）
    assert cli.main(["remove", "llm-systems", "--yes", "-w", str(ws)]) == 0
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        cli.main(["list", "--json", "-w", str(ws)])
    assert json.loads(buf2.getvalue())["result"]["wikis"] == []
