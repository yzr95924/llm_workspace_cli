"""wiki 仓初始化: 读 SKILL 仓 references/ 下的模板与 fixtures,
按 wiki-spec.md v0.19.0 §1-§7 + §9.1 + §14 把 wiki 仓"出生形态"落盘.

CLI 内联实现(spec 0.2.0 起 wiki 创建归 CLI 负责,SKILL 仓只管运行时纪律).
fixtures 是 CLI 字节级金标准(fixtures/README.md 附录 A):
渲染后用 cmp -s 与 fixtures / canonical 比对,不一致 = CLI 实现 bug.

落盘 8 件产物(spec 0.11.0 AGENTS.md SSOT 拆出):
  AGENTS.md, CLAUDE.md(薄壳), .gitignore, wiki/index.md, wiki/log.md,
  MEMORY/MEMORY.md, wiki/tags.md, scripts/SCRIPTS.md
子目录: raw/{articles,assets}, wiki/{5 类内容页}, MEMORY/, scripts/

git 红线(spec §7, 0.16.0+): CLI 绝不碰 git——init 仅落盘目录树 + .gitkeep 占位
+ 打印手动 hint;所有 git 操作由用户自行触发。.gitkeep 无条件落盘(7 个空目录:
5 内容页 + raw/articles + raw/assets),便于用户后续 `git add .` 跟踪空目录。
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

# spec §7 step 3 (0.15.0+): 需要 .gitkeep 占位的空目录——5 内容页子目录 + raw 两个默认
# 子目录。MEMORY/ 与 scripts/ 不需要(各有真实索引文件 MEMORY.md / SCRIPTS.md 让目录被
# git 跟踪)。.gitkeep 无条件落盘(不 gated on --git),纯目录树下无害。
_GITKEEP_DIRS = [Path("wiki") / d for d in _CONTENT_SUBDIRS] + [
    Path("raw") / d for d in _RAW_SUBDIRS
]


def check_not_initialized(wiki_dir: Path) -> None:
    """spec §8: 5 类 CLI 落盘产物任一已存在 → 拒绝覆盖

    spec §8 表格列 CLAUDE.md + wiki/index.md 是必检;§8 总段"绝不允许覆盖已有 wiki"
    的精神把范围扩到 MEMORY.md / tags.md / SCRIPTS.md。
    必须在 mkdir 前调用,避免留下半成品目录.
    """
    files = [
        wiki_dir / "AGENTS.md",  # spec §2 (用户宪法/SSOT, 0.11.0+)
        wiki_dir / "CLAUDE.md",  # spec §2 (薄壳, Claude Code 自动加载)
        wiki_dir / "wiki" / "index.md",  # spec §3 (agent 单一入口)
        wiki_dir / "MEMORY" / "MEMORY.md",  # spec §5.1 (0.10.0+ 移 wiki 根)
        wiki_dir / "wiki" / "tags.md",  # spec §9.1 (0.8.0+)
        wiki_dir / "scripts" / "SCRIPTS.md",  # spec §14 (0.9.0+)
    ]
    for f in files:
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
    """按 wiki-spec.md v0.19.0 落盘 wiki 仓骨架.

    Args:
        wiki_dir: wiki 仓根目录 (含路径名);调用方应已 mkdir 此目录.
        topic: 主题名 (人类可读, e.g. "LLM Systems"),用于 AGENTS.md / CLAUDE.md / index.md / log.md 占位符.
        today: YYYY-MM-DD,setup 日期.
        cli_version: llmw.__version__,用于 AGENTS.md 占位符.
        spec_version: llmw.WIKI_SPEC_VERSION,用于 AGENTS.md 占位符.

    Raises:
        SkillMissing: SKILL submodule 的 references/ 目录不存在.
        SetupFailed: 模板读取失败 / 占位符残留 / atomic_write 失败.

    Note:
        spec §7 (0.16.0+): 本函数不碰 git——仅落盘目录树 + .gitkeep 占位 + 8 份字面量
        产物;所有 git 操作由用户自行触发(调用方负责打印手动 hint)。
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

    # 读 8 份字面量源(spec §2 / §3 / §4 / §5.1 / §6 / §9.1 / §14)
    # spec §2 (0.11.0+): AGENTS.md (SSOT, 工具无关) + CLAUDE.md (薄壳, Claude Code 自动加载)
    # 占位符子集不同 — AGENTS.md 4 占位符, CLAUDE.md 仅 {{TOPIC_NAME}};
    # 共享 mapping, str.replace 对不存在的 key 是 no-op, 不影响
    try:
        agents_md_tmpl = (refs / "agents-md-template.md").read_text(encoding="utf-8")
        claude_md_tmpl = (refs / "claude-md-template.md").read_text(encoding="utf-8")
        index_md_tmpl = (fixtures / "index.md.txt").read_text(encoding="utf-8")
        log_md_tmpl = (fixtures / "log.md.txt").read_text(encoding="utf-8")
        memory_md_tmpl = (fixtures / "memory-index.txt").read_text(encoding="utf-8")
        tags_md_tmpl = (fixtures / "tags.md.txt").read_text(encoding="utf-8")
        scripts_md_tmpl = (fixtures / "scripts.md.txt").read_text(encoding="utf-8")
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
    # 4 份有占位符: AGENTS.md (4) / CLAUDE.md 薄壳 (1) / index.md (2) / log.md (2)
    # 4 份无占位符少数派: memory-index / tags / scripts / gitignore
    # (SKILL 仓 2026-07-02 修订后 fixture 已经不含占位符,无需 _substitute)
    try:
        agents_md = _substitute(agents_md_tmpl, mapping)
        claude_md = _substitute(claude_md_tmpl, mapping)
        index_md = _substitute(index_md_tmpl, mapping)
        log_md = _substitute(log_md_tmpl, mapping)
    except SetupFailed:
        raise

    # 落盘顺序: 先建所有子目录, 再 .gitkeep 占位, 再 atomic_write 8 份字面量产物
    # MEMORY/ 0.10.0+ 起在 wiki 根,与 wiki/ 平级;scripts/ 0.9.0+ 必须始终创建
    for d in (
        [wiki_dir / "raw" / x for x in _RAW_SUBDIRS]
        + [wiki_dir / "wiki" / x for x in _CONTENT_SUBDIRS]
        + [wiki_dir / "MEMORY"]
        + [wiki_dir / "scripts"]
    ):
        d.mkdir(parents=True, exist_ok=True)

    # spec §7 step 3 (0.16.0+): .gitkeep 无条件落盘——7 个空目录占位,便于用户后续
    # `git add .` 跟踪。touch 是幂等 best-effort:目录已建,空文件无害;失败不阻断落盘。
    for rel in _GITKEEP_DIRS:
        try:
            (wiki_dir / rel / ".gitkeep").touch()
        except OSError:
            pass

    try:
        # spec §2 (0.11.0+): 先写 AGENTS.md (SSOT), 再写 CLAUDE.md (薄壳)
        atomic_write(wiki_dir / "AGENTS.md", agents_md)
        atomic_write(wiki_dir / "CLAUDE.md", claude_md)
        atomic_write(wiki_dir / ".gitignore", gitignore_tmpl)
        atomic_write(wiki_dir / "wiki" / "index.md", index_md)
        atomic_write(wiki_dir / "wiki" / "log.md", log_md)
        atomic_write(wiki_dir / "MEMORY" / "MEMORY.md", memory_md_tmpl)
        atomic_write(wiki_dir / "wiki" / "tags.md", tags_md_tmpl)
        atomic_write(wiki_dir / "scripts" / "SCRIPTS.md", scripts_md_tmpl)
    except OSError as e:
        raise SetupFailed(
            f"写入文件失败: {e.filename or e.strerror}",
            hint="检查磁盘空间 + 目录权限",
        )
