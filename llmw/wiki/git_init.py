"""wiki 仓 opt-in git 初始化 (spec §7)

默认不调 git; 只有 `llmw wiki add --git` 才走本模块.
前置任一不通过 (git 二进制缺失 / 已在仓内) → 跳过 + warn,不阻断落盘.
"""
import shutil
import subprocess
import sys
from pathlib import Path

from llmw.errors import SetupFailed


_GITKEEP_SUBDIRS = ["comparisons", "concepts", "entities", "sources", "syntheses"]


def _run(cmd, *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """subprocess.run 包装: capture_output + text,失败由调用方处理"""
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=check)


def init(wiki_dir: Path) -> bool:
    """spec §7 完整流程: 前置检查 → git init → .gitkeep → add → commit

    Returns:
        True: 已完整执行 (git init + commit)
        False: 前置不通过,已 warn 跳过 (wiki 仍落盘, 但没新建 git 仓)

    Raises:
        SetupFailed: git init / add / commit 任一步骤失败
    """
    # 前置 1: git 二进制可用
    if shutil.which("git") is None:
        print(
            "[llmw] warning: 未找到 git,已跳过 --git;wiki 仍可用,后续可手动 git init",
            file=sys.stderr,
        )
        return False

    # 前置 2: 不在已有 git 仓内
    r = _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=wiki_dir, check=False)
    if r.returncode == 0:
        print(
            f"[llmw] warning: {wiki_dir} 已在 git 仓内,跳过 --git;"
            f"如需提交请自行 add + commit",
            file=sys.stderr,
        )
        return False

    # 1. git init
    r = _run(["git", "init"], cwd=wiki_dir, check=False)
    if r.returncode != 0:
        raise SetupFailed(
            f"git init 失败: {(r.stderr or '').strip()}",
            hint="检查目录权限",
        )

    # 2. 默认 main 分支
    _run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=wiki_dir, check=False)

    # 3. local user.email / user.name(若 global 未配)
    for key, default in [("user.email", "wiki@local"), ("user.name", "LLM Wiki")]:
        r = _run(["git", "config", "--global", "--get", key], cwd=wiki_dir, check=False)
        if r.returncode != 0 or not (r.stdout or "").strip():
            _run(["git", "config", key, default], cwd=wiki_dir, check=False)

    # 4. 为 5 个空内容页子目录放 .gitkeep (spec §7 第 4 步)
    for d in _GITKEEP_SUBDIRS:
        (wiki_dir / "wiki" / d / ".gitkeep").touch()

    # 5. git add .
    r = _run(["git", "add", "."], cwd=wiki_dir, check=False)
    if r.returncode != 0:
        raise SetupFailed(
            f"git add 失败: {(r.stderr or '').strip()}",
        )

    # 6. git commit
    r = _run(["git", "commit", "-m", "Initial wiki scaffold"], cwd=wiki_dir, check=False)
    if r.returncode != 0:
        raise SetupFailed(
            f"git commit 失败: {(r.stderr or '').strip()}",
            hint="检查 git user.email / user.name 是否配置",
        )

    return True