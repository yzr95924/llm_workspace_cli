"""wiki enter 的 byobu 窗口模式 — 固定 session llm_workspace 内按 wiki 名开窗口

workspace.toml#enter_byobu = true 时，enter 不再阻塞直启 agent CLI，改为在 byobu
固定 session 里开窗口（fire-and-forget）。本模块是 byobu/tmux 的薄封装 + 开窗编排，
只被 llmw/wiki/enter.py 调用；不写元数据、不读配置。

设计要点：

- **一律调 ``byobu-tmux``**（/usr/bin/byobu 的 symlink）：byobu 启动脚本经 argv[0]
  强制 BYOBU_BACKEND=tmux（盖过 ~/.byobu/backend 配置）；带参数调用时
  ``exec tmux -u -f <byobu tmuxrc> "$@"`` 全透传（/usr/bin/byobu:258-267）。
- **窗口 target 一律用 ``#{window_id}``（@N），不用名字**——wiki NAME_RE 允许纯数字
  名（如 123），``select-window -t session:123`` 有 name/index 解析歧义。
- **agent argv[0] 先经 shutil.which 解析为绝对路径**：tmux server 的环境来自启动
  server 的进程（可能是很久前的登录 shell），其 PATH 不一定含 agent 所在目录
  （如 ~/.local/bin）；llmw 里 which 通过 ≠ 窗口里 sh -c 找得到。
- **agent 命令拼 shell 字符串**（tmux ≥3.2 即可；多 argv 直 exec 是 3.4 行为，不依赖）。
  py3.7 无 shlex.join，手写 ``" ".join(shlex.quote(a) for a in argv)``。
- **窗口名经 ``new-window -n`` 锁定**：tmux 对显式命名的窗口自动关闭该窗口的
  automatic-rename，agent 进程改名（OSC escape 只改 pane title）不影响窗口名。
- **竞争只做线性降级（≤3 步），不上锁**：双 enter 首建竞争的产物是同名窗口共存
  （tmux 允许），后续 find_window 取第一个精确匹配，行为确定（README 已知限制）。
"""

import os
import shlex
import shutil
import subprocess
from typing import Dict, List, Optional

from llmw.errors import ByobuCommandFailed

_BYOBU_BIN = "byobu-tmux"
_BYOBU_SESSION = "llm_workspace"  # 固定 session 名（代码常量，不可配）


def byobu_available() -> bool:
    return shutil.which(_BYOBU_BIN) is not None


def _run(args: List[str]) -> "subprocess.CompletedProcess[str]":
    """调 byobu-tmux；只信 returncode。

    byobu 包装器每次调用都会先跑 byobu-janitor 等副作用（/usr/bin/byobu:108），
    stderr 可能有杂讯——不作为失败判据，仅供上层拼错误提示。
    """
    return subprocess.run(
        [_BYOBU_BIN] + args,
        capture_output=True,
        text=True,
        check=False,
    )


def current_session() -> Optional[str]:
    """llmw 进程所在的 tmux session 名；不在 tmux 内或 server 已死 → None。"""
    if not os.environ.get("TMUX"):
        return None
    p = _run(["display-message", "-p", "#S"])
    return p.stdout.strip() if p.returncode == 0 else None


def has_session() -> bool:
    """llm_workspace session 是否存在（无 server / 无 session 统一 False）。"""
    return _run(["has-session", "-t", _BYOBU_SESSION]).returncode == 0


def find_window(name: str) -> Optional[str]:
    """按精确窗口名查 llm_workspace 内窗口，返回 window_id（@N）；无 → None。

    同名窗口共存（竞争产物）时取第一个精确匹配，行为确定。
    """
    p = _run(
        ["list-windows", "-t", _BYOBU_SESSION, "-F", "#{window_id}\t#{window_name}"]
    )
    if p.returncode != 0:
        return None
    for line in p.stdout.splitlines():
        wid, _, wname = line.partition("\t")
        if wname == name:
            return wid
    return None


def select_window(window_id: str) -> bool:
    return _run(["select-window", "-t", window_id]).returncode == 0


def _env_args(env: Dict[str, str]) -> List[str]:
    """``-e K=V`` 对（tmux ≥3.2）；k/v 作为独立 argv 元素传递，无需 shell quoting。"""
    args: List[str] = []
    for k, v in env.items():
        args += ["-e", f"{k}={v}"]
    return args


def _new_session(name: str, cwd: str, shell_cmd: str, env: Dict[str, str]):
    """session 与首窗口一步建成（避免先建 session 留下裸 shell window 0）。"""
    return _run(
        ["new-session", "-d", "-s", _BYOBU_SESSION, "-n", name, "-c", cwd]
        + _env_args(env)
        + [shell_cmd]
    )


def _new_window(name: str, cwd: str, shell_cmd: str, env: Dict[str, str]):
    return _run(
        ["new-window", "-t", _BYOBU_SESSION, "-n", name, "-c", cwd]
        + _env_args(env)
        + [shell_cmd]
    )


def spawn_window(name: str, cwd: str, cmd_argv: List[str], env: Dict[str, str]) -> bool:
    """在 llm_workspace 里为 wiki 开窗口（或复用同名窗口）。

    返回 True=新建窗口 / False=复用已有窗口（select-window 已切焦点）。

    线性降级（≤3 步，不循环）：

    1. 无 session → new-session 一步带首窗口；失败（并发竞争 duplicate session）
       → 落入窗口级路径
    2. 有同名窗口 → select-window；窗口刚好死掉（select 失败）→ 降级 new-window
    3. 无同名窗口 → new-window；session 刚好被 kill（失败）→ 重试一次 new-session

    再失败抛 ByobuCommandFailed（hint 带两条命令的 stderr 摘要；命令行无 secret）。
    """
    resolved = shutil.which(cmd_argv[0]) or cmd_argv[0]
    shell_cmd = " ".join(shlex.quote(a) for a in [resolved] + list(cmd_argv[1:]))

    if not has_session():
        if _new_session(name, cwd, shell_cmd, env).returncode == 0:
            return True
        # 并发下另一个 enter 抢先建了 session → 落入窗口级路径

    wid = find_window(name)
    if wid is not None and select_window(wid):
        return False

    p = _new_window(name, cwd, shell_cmd, env)
    if p.returncode == 0:
        return True

    # new-window 失败：session 在 has_session 之后被 kill → 最后重试一次一步建
    p2 = _new_session(name, cwd, shell_cmd, env)
    if p2.returncode == 0:
        return True
    raise ByobuCommandFailed(
        f"byobu 开窗失败 (session={_BYOBU_SESSION}, window={name})",
        hint=(
            f"new-window: {p.stderr.strip() or '(no stderr)'}; "
            f"new-session: {p2.stderr.strip() or '(no stderr)'}"
        ),
    )
