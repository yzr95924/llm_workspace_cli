"""wiki 仓初始化: 读 SKILL 仓 references/ 下的模板与 fixtures,
按 wiki-spec.md v0.3.0 §1-§6 把 wiki 仓"出生形态"落盘.

CLI 内联实现(spec 0.2.0 起 wiki 创建归 CLI 负责,SKILL 仓只管运行时纪律).
fixtures 是 CLI 字节级金标准(fixtures/README.md 附录 A):
渲染后用 cmp -s 与 fixtures 比对,不一致 = CLI 实现 bug.
"""
import re
from pathlib import Path
from typing import Dict

from llmw.config import wiki_spec_templates_dir
from llmw.errors import SetupFailed, SkillMissing, WikiAlreadyInitialized
from llmw.fsutil import atomic_write


# spec §1: 内容页子目录 + MEMORY/, 字母序创建
_CONTENT_SUBDIRS = [
    "comparisons",
    "concepts",
    "entities",
    "sources",
    "syntheses",
]
_RAW_SUBDIRS = ["articles", "assets"]


def check_not_initialized(wiki_dir: Path) -> None:
    """spec §8: CLAUDE.md 或 wiki/index.md 已存在 → 拒绝覆盖

    必须在 mkdir 前调用,避免留下半成品目录.
    """
    for f in [wiki_dir / "CLAUDE.md", wiki_dir / "wiki" / "index.md"]:
        if f.exists():
            raise WikiAlreadyInitialized(
                f"{f} 已存在,拒绝覆盖",
                hint="若要重新初始化,请先备份 + 删除该文件",
            )


def _substitute(text: str, mapping: Dict[str, str]) -> str:
    """替换 {{KEY}} 占位符; 末尾 assert 无残留"""
    for k, v in mapping.items():
        text = text.replace("{{" + k + "}}", v)
    leftover = re.findall(r"\{\{[^}]+\}\}", text)
    if leftover:
        raise SetupFailed(
            f"模板占位符未替换干净: {leftover}",
            hint="检查 mapping 是否覆盖所有占位符",
        )
    return text


def render_and_write(
    wiki_dir: Path,
    topic: str,
    today: str,
    cli_version: str,
    spec_version: str,
) -> None:
    """按 wiki-spec.md v0.3.0 落盘 wiki 仓骨架.

    Args:
        wiki_dir: wiki 仓根目录 (含路径名);调用方应已 mkdir 此目录.
        topic: 主题名 (人类可读, e.g. "LLM Systems"),用于 CLAUDE.md / index.md / log.md / memory-readme.
        today: YYYY-MM-DD,setup 日期.
        cli_version: llmw.__version__,用于 CLAUDE.md 占位符.
        spec_version: llmw.WIKI_SPEC_VERSION,用于 CLAUDE.md 占位符.

    Raises:
        SkillMissing: SKILL submodule 的 references/ 目录不存在.
        SetupFailed: 模板读取失败 / 占位符残留 / atomic_write 失败.
    """
    refs = wiki_spec_templates_dir()
    if not refs.is_dir():
        raise SkillMissing(
            f"找不到 SKILL references/ 目录: {refs}",
            hint="运行 `git submodule update --init` 初始化 SKILL",
        )
    fixtures = refs / "fixtures"
    if not fixtures.is_dir():
        raise SetupFailed(
            f"fixtures 目录缺失: {fixtures}",
            hint="检查 SKILL 仓 references/fixtures/ 是否完整",
        )

    # 读 5 份字面量源
    try:
        claude_md_tmpl = (refs / "claude-md-template.md").read_text(encoding="utf-8")
        index_md_tmpl  = (fixtures / "index.md.txt").read_text(encoding="utf-8")
        log_md_tmpl    = (fixtures / "log.md.txt").read_text(encoding="utf-8")
        memory_md_tmpl = (fixtures / "memory-readme.txt").read_text(encoding="utf-8")
        gitignore_tmpl = (fixtures / "gitignore.txt").read_text(encoding="utf-8")
    except OSError as e:
        raise SetupFailed(
            f"读取模板失败: {e.filename}",
            hint="检查 SKILL submodule 是否完整 (git submodule update --init)",
        )

    mapping = {
        "TOPIC_NAME": topic,
        "SETUP_DATE": today,
        "WIKI_SPEC_VERSION": spec_version,
        "CLI_VERSION": cli_version,
    }

    # 渲染(占位符替换 + assert 无残留)
    try:
        claude_md = _substitute(claude_md_tmpl, mapping)
        index_md  = _substitute(index_md_tmpl, mapping)
        log_md    = _substitute(log_md_tmpl, mapping)
        memory_md = _substitute(memory_md_tmpl, mapping)
        # gitignore 无占位符,跳过 substitute 直接落盘
    except SetupFailed:
        raise

    # 落盘顺序: 先建所有子目录, 再 atomic_write 5 份字面量产物
    # (atomic_write 内部也 mkdir parent, 但 spec §1 要求显式建 5 个空子目录以备后续 .gitkeep)
    for d in [wiki_dir / "raw" / x for x in _RAW_SUBDIRS] + \
             [wiki_dir / "wiki" / x for x in _CONTENT_SUBDIRS] + \
             [wiki_dir / "wiki" / "MEMORY"]:
        d.mkdir(parents=True, exist_ok=True)

    try:
        atomic_write(wiki_dir / "CLAUDE.md", claude_md)
        atomic_write(wiki_dir / ".gitignore", gitignore_tmpl)
        atomic_write(wiki_dir / "wiki" / "index.md", index_md)
        atomic_write(wiki_dir / "wiki" / "log.md", log_md)
        atomic_write(wiki_dir / "wiki" / "MEMORY" / "README.md", memory_md)
    except OSError as e:
        raise SetupFailed(
            f"写入文件失败: {e.filename or e.strerror}",
            hint="检查磁盘空间 + 目录权限",
        )