"""全局配置 + workspace 路径解析 + 包内路径定位"""

import os
from pathlib import Path

from llmw.errors import WorkspaceNotFound

DEFAULT_WORKSPACE = Path.home() / "yzr_llm_wiki_workspace"


def resolve_workspace_root(
    explicit: str = None,
    cwd: Path = None,
) -> Path:
    """解析 workspace 根路径

    优先级:
      1. explicit (--workspace flag)
      2. $LLMW_WORKSPACE env var
      3. ~/yzr_llm_wiki_workspace (默认)

    解析后校验: 必须存在、是目录、含 workspace.toml。
    不存在 → WorkspaceNotFound
    """
    if explicit:
        root = Path(explicit).resolve()
    elif os.environ.get("LLMW_WORKSPACE"):
        root = Path(os.environ["LLMW_WORKSPACE"]).resolve()
    else:
        root = DEFAULT_WORKSPACE.resolve()

    if not root.is_dir():
        raise WorkspaceNotFound(
            hint=f"路径不存在: {root}。可指定 --workspace 或 $LLMW_WORKSPACE",
        )
    if not (root / "workspace.toml").is_file():
        raise WorkspaceNotFound(
            hint=f"目录 {root} 不是 llmw workspace（缺少 workspace.toml）。"
            f"可运行 `llmw init --path {root}`",
        )
    return root


def package_root() -> Path:
    """返回 llmw 包根 (含 __init__.py 的目录的父)"""
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    """返回仓库根 (package_root 的父目录)"""
    return package_root().parent


def skill_setup_script() -> Path:
    """解析 setup_wiki.py 路径

    优先级:
      1. $LLMW_SKILL_SETUP_SCRIPT env var
      2. <repo>/my_SKILL/llm-wiki-management/scripts/setup_wiki.py

    不存在 → 由调用方 raise SkillMissing / SkillScriptMissing
    """
    env_path = os.environ.get("LLMW_SKILL_SETUP_SCRIPT")
    if env_path:
        return Path(env_path).resolve()
    return (
        repo_root() / "my_SKILL" / "llm-wiki-management" / "scripts" / "setup_wiki.py"
    )


def templates_dir() -> Path:
    return repo_root() / "templates"
