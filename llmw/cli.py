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

    # ===== wiki 级 =====
    p_wiki = sub.add_parser("wiki", help="wiki 子命令")
    p_wiki.add_argument("--name", required=True, metavar="NAME",
                        help="目标 wiki 名")
    wiki_sub = p_wiki.add_subparsers(dest="wiki_action", metavar="ACTION")

    # add
    pw_add = wiki_sub.add_parser("add", help="新建 wiki")
    pw_add.add_argument("--topic", default=None)
    pw_add.add_argument("--display-name", default=None, dest="display_name")
    pw_add.add_argument("--description", default=None)
    pw_add.add_argument("--tag", action="append", default=[], dest="tags")
    pw_add.add_argument("--model", default=None)
    pw_add.add_argument("--no-setup", action="store_true", dest="no_setup")

    # remove
    pw_rm = wiki_sub.add_parser("remove", help="移除 wiki")
    pw_rm.add_argument("--purge", action="store_true")
    pw_rm.add_argument("--yes", "-y", action="store_true")

    # show
    pw_show = wiki_sub.add_parser("show", help="查看 wiki 详情")

    # config (sub: get / set / unset)
    pw_cfg = wiki_sub.add_parser("config", help="读写 wiki_metadata.toml")
    pw_cfg.add_argument("cfg_action", nargs="?", default=None,
                        choices=[None, "get", "set", "unset"])
    pw_cfg.add_argument("cfg_key", nargs="?", default=None)
    pw_cfg.add_argument("cfg_value", nargs="?", default=None)

    # enter
    pw_enter = wiki_sub.add_parser("enter", help="启动 Claude Code session")
    pw_enter.add_argument("--dry-run", action="store_true", dest="dry_run")

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

        if args.command == "wiki":
            from llmw.wiki.manager import (
                add as wiki_add, remove as wiki_rm, show as wiki_show,
                wiki_config_get, wiki_config_set, wiki_config_unset,
                wiki_config_interactive,
            )
            wa = args.wiki_action
            if wa == "add":
                wiki_add(
                    ws_root, args.name,
                    topic=args.topic, display_name=args.display_name,
                    description=args.description, tags=args.tags or None,
                    model=args.model, no_setup=args.no_setup,
                )
            elif wa == "remove":
                wiki_rm(ws_root, args.name, purge=args.purge, yes=args.yes)
            elif wa == "show":
                wiki_show(ws_root, args.name, as_json=args.json)
            elif wa == "config":
                if args.cfg_action is None:
                    wiki_config_interactive(ws_root, args.name)
                elif args.cfg_action == "get":
                    wiki_config_get(ws_root, args.name, args.cfg_key)
                elif args.cfg_action == "set":
                    wiki_config_set(ws_root, args.name, args.cfg_key, args.cfg_value)
                elif args.cfg_action == "unset":
                    wiki_config_unset(ws_root, args.name, args.cfg_key)
            elif wa == "enter":
                from llmw.wiki.enter import enter as wiki_enter
                return wiki_enter(ws_root, args.name, dry_run=args.dry_run)
            else:
                print("[llmw] wiki 子命令需要 ACTION (add/remove/show/config/enter)",
                      file=sys.stderr)
                return 1
            return 0

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
