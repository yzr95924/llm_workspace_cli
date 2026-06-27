"""argparse 顶层 + 全局 flag + 子命令分派"""
import argparse
import sys
from pathlib import Path
from llmw import __version__
from llmw.errors import LlmwError, InternalError, format_error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llmw",
        description="Wiki workspace CLI (manage wikis under one git repo)",
    )
    parser.add_argument("--version", action="version", version=f"llmw {__version__}")
    parser.add_argument(
        "--workspace", metavar="PATH", default=None,
        help="workspace 根路径 (默认: $LLMW_WORKSPACE 或 ~/yzr_llm_workspace)",
    )
    parser.add_argument("--json", action="store_true", help="全局: 输出 JSON 格式")
    parser.add_argument("--debug", action="store_true", help="全局: 打印 traceback")
    parser.add_argument("--quiet", "-q", action="store_true", help="全局: 抑制 INFO")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ===== workspace 级 =====
    p_init = sub.add_parser("init", help="初始化 workspace")
    p_init.add_argument("--path", metavar="PATH", default=None)
    p_init.add_argument("--git", action="store_true", default=True)
    p_init.add_argument("--no-git", dest="git", action="store_false")

    p_config = sub.add_parser("config", help="workspace.toml 读写")
    p_config.add_argument("action", nargs="?", default=None, choices=[None, "get", "set", "unset"])
    p_config.add_argument("key", nargs="?", default=None)
    p_config.add_argument("value", nargs="?", default=None)

    p_list = sub.add_parser("list", help="列出 wiki")
    p_list.add_argument("--tag", action="append", default=[], metavar="TAG",
                        help="仅列出含此 tag 的 wiki (可重复, AND 关系)")

    # wiki 子命令见 Tasks 14 / 16

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            from llmw.config import DEFAULT_WORKSPACE
            from llmw.workspace.manager import init as ws_init
            target = Path(args.path) if args.path else DEFAULT_WORKSPACE
            ws_init(Path(target), git=args.git)
            return 0

        # 下列命令需要先解析 workspace_root
        from llmw.config import resolve_workspace_root
        ws_root = resolve_workspace_root(args.workspace)

        if args.command == "config":
            from llmw.workspace.manager import (
                config_get, config_set, config_unset, config_interactive,
            )
            if args.action is None:
                config_interactive(ws_root)
                return 0
            if args.action == "get":
                config_get(ws_root, args.key)
            elif args.action == "set":
                config_set(ws_root, args.key, args.value)
            elif args.action == "unset":
                config_unset(ws_root, args.key)
            return 0

        if args.command == "list":
            from llmw.workspace.manager import list_wikis
            return list_wikis(ws_root, as_json=args.json, tag_filter=args.tag or None)

    except LlmwError as e:
        print(format_error(e, debug=args.debug), file=sys.stderr)
        return e.exit_code
    except Exception as e:
        if args.debug:
            raise
        print(format_error(InternalError(str(e)), debug=False), file=sys.stderr)
        return 3

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
