"""argparse 顶层 + 全局 flag + 子命令分派"""

import argparse
import sys
from pathlib import Path
from llmw import __version__
from llmw.errors import LlmwError, InternalError, format_error


def _common_flags() -> argparse.ArgumentParser:
    """全局 flag 的共享 parent。

    经 ``parents=[_common_flags()]`` 同时挂到主 parser 与每个子 parser，使全局 flag
    既可写在子命令前（``llmw --json list``）也可写在子命令后（``llmw list --json``，
    spec §3.1 / 设计 01 §1.3）。``default=SUPPRESS`` 是关键：子 parser 解析时若用户
    没在该位置传该 flag，就不写入 namespace，从而不会用默认值覆盖主 parser 已解析
    到的同名值（argparse 子 parser 默认会 clobber）。故读取处须用 ``getattr``。
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--workspace",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="workspace 根路径 (默认: $LLMW_WORKSPACE 或 ~/yzr_llm_wiki_workspace)",
    )
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="全局: 输出 JSON 格式",
    )
    common.add_argument(
        "--debug",
        action="store_true",
        default=argparse.SUPPRESS,
        help="全局: 打印 traceback",
    )
    common.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=argparse.SUPPRESS,
        help="全局: 抑制 INFO",
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _common_flags()
    parser = argparse.ArgumentParser(
        prog="llmw",
        description="Wiki workspace CLI (manage wikis under one git repo)",
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=f"llmw {__version__}")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ===== workspace 级 =====
    p_init = sub.add_parser("init", help="初始化 workspace", parents=[common])
    p_init.add_argument("--path", metavar="PATH", default=None)
    p_init.add_argument(
        "--display-name",
        default=None,
        dest="display_name",
        help="workspace display name (写入 CLAUDE.md; 默认 'LLM Wiki Workspace')",
    )

    p_config = sub.add_parser("config", help="workspace.toml 读写", parents=[common])
    p_config.add_argument(
        "action", nargs="?", default=None, choices=[None, "get", "set", "unset"]
    )
    p_config.add_argument("key", nargs="?", default=None)
    p_config.add_argument("value", nargs="?", default=None)

    p_list = sub.add_parser("list", help="列出 wiki", parents=[common])
    p_list.add_argument(
        "--tag",
        action="append",
        default=[],
        metavar="TAG",
        help="仅列出含此 tag 的 wiki (可重复, AND 关系)",
    )

    # ===== model registry =====
    p_model = sub.add_parser("model", help="workspace model registry", parents=[common])
    model_sub = p_model.add_subparsers(dest="model_action", metavar="ACTION")

    pm_add = model_sub.add_parser("add", help="新增 model 条目", parents=[common])
    pm_add.add_argument("--model-id", default=None, dest="model_id")
    pm_add.add_argument("--name", default=None)
    pm_add.add_argument("--base-url", default=None, dest="base_url")
    pm_add.add_argument("--api-key", default=None, dest="api_key")
    pm_add.add_argument("--default", action="store_true", dest="as_default")

    model_sub.add_parser("list", help="列出所有 model 条目", parents=[common])

    pm_show = model_sub.add_parser("show", help="查看单条 model", parents=[common])
    pm_show.add_argument("--model-id", required=True, dest="model_id")

    pm_sd = model_sub.add_parser("set-default", help="标记默认 model", parents=[common])
    pm_sd.add_argument("--model-id", required=True, dest="model_id")

    model_sub.add_parser("unset-default", help="清空默认标记", parents=[common])

    pm_rm = model_sub.add_parser("remove", help="删除 model 条目", parents=[common])
    pm_rm.add_argument("--model-id", required=True, dest="model_id")
    pm_rm.add_argument("--yes", "-y", action="store_true")

    # ===== wiki 级 =====
    p_wiki = sub.add_parser("wiki", help="wiki 子命令", parents=[common])
    p_wiki.add_argument("--name", required=True, metavar="NAME", help="目标 wiki 名")
    wiki_sub = p_wiki.add_subparsers(dest="wiki_action", metavar="ACTION")

    # add
    pw_add = wiki_sub.add_parser("add", help="新建 wiki", parents=[common])
    pw_add.add_argument("--topic", default=None)
    pw_add.add_argument("--display-name", default=None, dest="display_name")
    pw_add.add_argument("--description", default=None)
    pw_add.add_argument("--tag", action="append", default=[], dest="tags")
    pw_add.add_argument("--model", default=None)
    pw_add.add_argument("--git", action="store_true", default=False,
                        help="opt-in: 初始化 git 仓 (spec §7);默认不碰 git")

    # remove
    pw_rm = wiki_sub.add_parser("remove", help="移除 wiki", parents=[common])
    pw_rm.add_argument("--purge", action="store_true",
                       help="同时删除 wiki 子目录(默认先备份到 .llmw-trash/)")
    pw_rm.add_argument("--no-backup", dest="backup", action="store_false",
                       help="跳过 --purge 的备份步骤,直接 rmtree(CI / 脚本场景)")
    pw_rm.add_argument("--yes", "-y", action="store_true")

    # show
    wiki_sub.add_parser("show", help="查看 wiki 详情", parents=[common])

    # config (sub: get / set / unset)
    pw_cfg = wiki_sub.add_parser(
        "config", help="读写 wiki_metadata.toml", parents=[common]
    )
    pw_cfg.add_argument(
        "cfg_action", nargs="?", default=None, choices=[None, "get", "set", "unset"]
    )
    pw_cfg.add_argument("cfg_key", nargs="?", default=None)
    pw_cfg.add_argument("cfg_value", nargs="?", default=None)

    # enter
    pw_enter = wiki_sub.add_parser(
        "enter", help="启动 Claude Code session", parents=[common]
    )
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
            ws_init(
                Path(target),
                display_name=args.display_name or "LLM Wiki Workspace",
            )
            return 0

        # 下列命令需要先解析 workspace_root
        from llmw.config import resolve_workspace_root

        ws_root = resolve_workspace_root(getattr(args, "workspace", None))

        if args.command == "config":
            from llmw.workspace.manager import (
                config_get,
                config_set,
                config_unset,
                config_interactive,
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

        if args.command == "model":
            from llmw.models.manager import (
                model_add,
                model_list,
                model_show,
                model_set_default,
                model_unset_default,
                model_remove,
            )

            ma = args.model_action
            if ma == "add":
                model_add(
                    ws_root,
                    model_id=args.model_id,
                    name=args.name,
                    base_url=args.base_url,
                    api_key=args.api_key,
                    as_default=args.as_default,
                )
            elif ma == "list":
                return model_list(ws_root, as_json=getattr(args, "json", False))
            elif ma == "show":
                model_show(ws_root, args.model_id, as_json=getattr(args, "json", False))
            elif ma == "set-default":
                model_set_default(ws_root, args.model_id)
            elif ma == "unset-default":
                model_unset_default(ws_root)
            elif ma == "remove":
                model_remove(ws_root, args.model_id, yes=args.yes)
            else:
                print(
                    "[llmw] model 子命令需要 ACTION (add/list/show/set-default/unset-default/remove)",
                    file=sys.stderr,
                )
                return 1
            return 0

        if args.command == "list":
            from llmw.workspace.manager import list_wikis

            return list_wikis(
                ws_root,
                as_json=getattr(args, "json", False),
                tag_filter=args.tag or None,
            )

        if args.command == "wiki":
            from llmw.wiki.manager import (
                add as wiki_add,
                remove as wiki_rm,
                show as wiki_show,
                wiki_config_get,
                wiki_config_set,
                wiki_config_unset,
                wiki_config_interactive,
            )

            wa = args.wiki_action
            if wa == "add":
                wiki_add(
                    ws_root, args.name,
                    topic=args.topic, display_name=args.display_name,
                    description=args.description, tags=args.tags or None,
                    model=args.model, git=args.git,
                )
            elif wa == "remove":
                wiki_rm(ws_root, args.name, purge=args.purge, yes=args.yes,
                        no_backup=args.backup is False)
            elif wa == "show":
                wiki_show(ws_root, args.name, as_json=getattr(args, "json", False))
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
                print(
                    "[llmw] wiki 子命令需要 ACTION (add/remove/show/config/enter)",
                    file=sys.stderr,
                )
                return 1
            return 0

    except LlmwError as e:
        print(format_error(e, debug=getattr(args, "debug", False)), file=sys.stderr)
        return e.exit_code
    except Exception as e:
        if getattr(args, "debug", False):
            raise
        print(format_error(InternalError(str(e)), debug=False), file=sys.stderr)
        return 3

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
