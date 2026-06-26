import pytest

from wiki_workspace import cli, errors


def test_build_parser_has_subcommands():
    p = cli.build_parser()
    with pytest.raises(SystemExit) as ei:  # --help 退出码 0
        p.parse_args(["--help"])
    assert ei.value.code == 0


def test_main_no_subcommand_returns_user_error(capsys, monkeypatch):
    monkeypatch.setattr(cli, "resolve_default_workspace", lambda: "/tmp/fake_ws")
    code = cli.main([])
    assert code == errors.EXIT_USER_ERROR


def test_main_unknown_subcommand(monkeypatch):
    with pytest.raises(SystemExit):  # argparse 错误 -> 退出码 2
        cli.main(["bogus-command"])


def test_global_flags_set_errors_config(monkeypatch):
    from wiki_workspace import errors as e

    captured = {}
    monkeypatch.setattr(
        e, "configure", lambda quiet=False, debug=False: captured.update(q=quiet, d=debug)
    )
    # 不真正分派命令——本测试只验证全局 flag 接到 errors.configure
    monkeypatch.setattr(cli, "_dispatch", lambda func, args: 0)
    cli.main(["-q", "--debug", "list"])
    assert captured == {"q": True, "d": True}
