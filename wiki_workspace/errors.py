"""退出码、分类错误发射器与 CommandError。

所有人读的诊断都打到 stderr，保证 stdout 可被机器解析（spec §4.4）。
``--json`` 调用方改用 ``render_json_result``。
"""

import json
import sys

# --- 退出码（spec §4.1）----------------------------------------------------
EXIT_OK = 0
EXIT_USER_ERROR = 1  # 改输入即可修
EXIT_ENV_ERROR = 2  # 得装东西 / 改环境才能修
EXIT_INTERNAL = 3  # bug；去报 issue

# --- 模块级冗长度（cli.main 从全局 flag 一次性设置）-----------------------
QUIET = False
DEBUG = False


def configure(quiet=False, debug=False):
    global QUIET, DEBUG
    QUIET = bool(quiet)
    DEBUG = bool(debug)


class ErrorRecord:
    def __init__(self, category, message, hint=None):
        self.category = category
        self.message = message
        self.hint = hint

    def to_dict(self):
        d = {"category": self.category, "message": self.message}
        if self.hint:
            d["hint"] = self.hint
        return d


class CommandError(Exception):
    """命令抛出；cli.main 捕获 -> emit + 返回 exit_code。"""

    def __init__(self, exit_code, category, message, hint=None):
        super().__init__(message)
        self.exit_code = exit_code
        self.category = category
        self.message = message
        self.hint = hint


def emit_error(category, message, hint=None):
    parts = ["[ERROR] {}: {}".format(category, message)]
    if hint:
        parts.append("  hint: {}".format(hint))
    for line in parts:
        print(line, file=sys.stderr)


def emit_warn(message):
    if not QUIET:
        print("[WARN] {}".format(message), file=sys.stderr)


def emit_info(message):
    if not QUIET:
        print("[INFO] {}".format(message), file=sys.stderr)


def emit_debug(message):
    if DEBUG:
        print("[DEBUG] {}".format(message), file=sys.stderr)


def render_json_result(exit_code, errors=None, result=None):
    """构造 ``--json`` 信封（spec §4.2）。result 打到 stdout。"""
    payload = {"exit_code": exit_code}
    if errors:
        payload["errors"] = [e.to_dict() for e in errors]
    if result is not None:
        payload["result"] = result
    return json.dumps(payload, ensure_ascii=False, indent=2)
