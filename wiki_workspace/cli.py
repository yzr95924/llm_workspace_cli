"""顶层 argparse + 分派 + 全局 flag 接线（spec §3.0、§3.8）。"""

import argparse
import sys

from wiki_workspace import errors


def resolve_default_workspace():
    # 间接层，测试可 monkeypatch 而不碰 $HOME。
    from wiki_workspace import workspace

    return str(workspace.find_root())


def build_parser():
    p = argparse.ArgumentParser(prog="llmw", description="LLM Workspace CLI")
    p.add_argument("--workspace", "-w", help="workspace 根目录")
    p.add_argument("--json", action="store_true", help="结构化 JSON 输出")
    p.add_argument("--quiet", "-q", action="store_true", help="抑制 WARN/INFO")
    p.add_argument("--debug", action="store_true", help="调试输出")

    sub = p.add_subparsers(dest="command", metavar="<command>")

    # init
    sp = sub.add_parser("init", help="初始化一个 workspace")
    sp.add_argument("--default-model", default="claude-sonnet-4-6")
    sp.set_defaults(func="init")

    # list
    sp = sub.add_parser("list", help="列出 wiki")
    sp.add_argument("--tag")
    sp.set_defaults(func="list")

    # add
    sp = sub.add_parser("add", help="新建一个 wiki")
    sp.add_argument("name")
    sp.add_argument("--display-name")
    sp.add_argument("--description")
    sp.add_argument("--model")
    sp.add_argument("--tag", action="append", default=[])
    sp.add_argument("--topic")
    sp.add_argument("--no-git", action="store_true")
    sp.set_defaults(func="add")

    # remove
    sp = sub.add_parser("remove", help="从 manifest 移除 wiki")
    sp.add_argument("name")
    sp.add_argument("--purge", action="store_true")
    sp.add_argument("--yes", "-y", action="store_true")
    sp.set_defaults(func="remove")

    # show
    sp = sub.add_parser("show", help="显示单个 wiki 详情")
    sp.add_argument("name")
    sp.set_defaults(func="show")

    # config
    sp = sub.add_parser("config", help="读写 wiki 配置")
    sp.add_argument("name")
    sp.add_argument("action", choices=["show", "get", "set", "unset"])
    sp.add_argument("key", nargs="?")
    sp.add_argument("value", nargs="?")
    sp.set_defaults(func="config")

    # enter
    sp = sub.add_parser("enter", help="在 wiki 上下文里启动 Claude Code")
    sp.add_argument("name")
    sp.add_argument("--model")
    sp.add_argument("--claude-md-check", choices=["warn", "fail", "skip"], default="warn")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func="enter")

    return p


def _dispatch(func_name, args):
    # 惰性 import：缺命令模块不会影响 --help。
    from wiki_workspace.commands import (
        add_cmd,
        config_cmd,
        enter_cmd,
        init_cmd,
        list_cmd,
        remove_cmd,
        show_cmd,
    )

    table = {
        "init": init_cmd.run,
        "list": list_cmd.run,
        "add": add_cmd.run,
        "remove": remove_cmd.run,
        "show": show_cmd.run,
        "config": config_cmd.run,
        "enter": enter_cmd.run,
    }
    return table[func_name](args)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    errors.configure(quiet=getattr(args, "quiet", False), debug=getattr(args, "debug", False))

    if not getattr(args, "command", None):
        parser.print_help(sys.stdout)
        return errors.EXIT_USER_ERROR

    try:
        return _dispatch(args.func, args)
    except errors.CommandError as exc:
        errors.emit_error(exc.category, exc.message, exc.hint)
        return exc.exit_code
