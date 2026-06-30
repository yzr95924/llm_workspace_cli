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
    """保留旧 API 以防有外部调用；返回 None 表示已废弃

    spec 0.2.0 起 wiki 创建由 CLI 内联实现(llmw.wiki.init_wiki),不再依赖
    my_SKILL/.../scripts/setup_wiki.py。本函数保留以便旧代码导入不报错。
    """
    return None


def wiki_spec_templates_dir() -> Path:
    """SKILL 仓 references/ 目录路径(CLI 字节金标准的来源)

    包含:
      - claude-md-template.md (CLAUDE.md 拷贝模板)
      - fixtures/index.md.txt / log.md.txt / memory-readme.txt / gitignore.txt

    不存在 → 由调用方 raise SkillMissing
    """
    return repo_root() / "my_SKILL" / "llm-wiki-management" / "references"


def workspace_spec_templates_dir() -> Path:
    """workspace SKILL 仓 references/ 目录路径(workspace CLAUDE.md 模板来源)

    包含:
      - workspace-claude-md-template.md (workspace CLAUDE.md 拷贝模板, spec §4)
      - workspace-spec.md

    不存在 → 由调用方 raise SkillMissing
    """
    return repo_root() / "my_SKILL" / "llm-workspace-management" / "references"


def templates_dir() -> Path:
    return repo_root() / "templates"
