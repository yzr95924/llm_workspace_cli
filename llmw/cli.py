"""argparse 顶层 + 全局 flag + 子命令分派"""
import argparse
import sys
from llmw import __version__


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
    # workspace: init / config / list (Task 12)
    # wiki: add / remove / show / config / enter (Tasks 14 / 16)
    return parser


def main(argv: list = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print(f"[llmw stub] argv={argv or sys.argv[1:]} parsed={args}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())