"""workspace 级业务: init / config / list"""

import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional

from llmw import WORKSPACE_SPEC_VERSION, __version__
from llmw._compat import TOMLDecodeError
from llmw.config import workspace_spec_templates_dir
from llmw.errors import (
    ConfigKeyMissing,
    InvalidConfigKey,
    KeyNotUnsettable,
    ModelDefaultAmbiguous,
    ModelDefaultNotSet,
    ModelNotInRegistry,
    RegistryMissing,
    SetupFailed,
    SkillMissing,
    WikiDirMissing,
    WikiNotFound,
    WorkspaceExists,
)
from llmw.fsutil import atomic_write
from llmw.workspace import store as ws_store

# config KEY 白名单: name -> (can_set, can_unset, type)
CONFIG_KEYS = {
    "default_model": (True, True, str),
    "enter_cli": (True, True, str),  # 白名单见 _check_enter_cli
    "templates_version": (False, False, str),  # 只读
    "created_at": (False, False, str),  # 只读
    "schema_version": (False, False, int),  # 只读
}


_ENTER_CLI_WHITELIST = frozenset({"claude", "qodercli"})


def _check_enter_cli(value: str) -> None:
    """enter_cli 白名单校验；非白名单值抛 InvalidConfigKey。"""
    if value not in _ENTER_CLI_WHITELIST:
        raise InvalidConfigKey(
            f"enter_cli 值 '{value}' 不在白名单",
            hint=f"可选: {', '.join(sorted(_ENTER_CLI_WHITELIST))}",
        )


# ===== workspace 级 .gitignore helper =====

# workspace 级 .gitignore managed block 内容（spec workspace-spec.md §10 v0.6.1 + llmw 自有 trash）
# 前 3 行严格对齐 spec §10 v0.6.1（registry + Claude Code / Qoder IDE 项目级 overlay）。
# 单仓模型：wiki 是 workspace 直属子目录，**/.<agent>/settings*.json 通配覆盖所有
# wiki 的 overlay secret，不依赖 per-wiki .gitignore / wiki scaffold（见 §10）。
# 0.5.0 加 .qoder，0.6.0 把 */ 改 **/（覆盖 workspace 根级），0.6.1 把 settings.local.json
# 加宽到 settings*.json（含 settings.json / settings.<env>.json 等所有变体）。
# 第 4 行 .llmw-trash/ 为 llmw 自有扩展（spec §10 字面未列）：wiki remove --purge
# 写入的备份目录，spec 允许"至少包含"语义下保留以避免误提交（见 MEMORY 驳正条目）。
GITIGNORE_LINES = (
    "workspace_models.toml",
    "**/.claude/settings*.json",
    "**/.qoder/settings*.json",
    ".llmw-trash/",
)

# spec §10: workspace .gitignore 的通用忽略段（OS / 编辑器 / Obsidian / 临时）。
# 全新 init 时与 managed block 一同落盘；已有 .gitignore 时不追加（尊重外部来源）。
_GITIGNORE_COMMON = """\
# OS / 编辑器
.DS_Store
.idea/
.vscode/
*.swp
*.swo

# Obsidian 配置（保留 vault 内容）
.obsidian/workspace*
.obsidian/cache

# 临时文件
*.tmp
*.bak
"""


def _ensure_workspace_gitignore(workspace_root: Path) -> None:
    """确保 workspace 级 .gitignore 含 llmw managed block + 通用忽略段（spec §10）。

    - 文件不存在 → 创建（managed block + OS / Obsidian / 临时通用段）
    - 文件存在 → 仅更新 managed marker 区间（secret 排除行），通用段不动
      （已有 .gitignore 视为用户/外部来源，不覆盖其内容）
    """
    gitignore = workspace_root / ".gitignore"
    marker_start = "# >>> llmw (managed by llmw) >>>"
    marker_end = "# <<< llmw <<<"
    block = marker_start + "\n" + "\n".join(GITIGNORE_LINES) + "\n" + marker_end

    if not gitignore.is_file():
        atomic_write(gitignore, block + "\n\n" + _GITIGNORE_COMMON)
        return

    text = gitignore.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(marker_start) + r".*?" + re.escape(marker_end), re.DOTALL
    )
    m = pattern.search(text)
    if m:
        if m.group(0) == block:
            return  # 已是最新 block
        new_text = pattern.sub(block, text)  # 老 block → 替换为最新
    else:
        # 无 block → 追加（保证前导换行 + 末尾换行）
        sep = "" if (text.endswith("\n") or not text) else "\n"
        tail = "" if text.endswith("\n") else "\n"
        new_text = text + sep + block + tail
    atomic_write(gitignore, new_text)


# ===== init =====


def _is_effectively_empty(path: Path) -> bool:
    """目录是否为空（忽略 git 元数据 .git 与 .gitignore）。
    只含 .git（git 仓目录或 worktree 的 .git 指针文件）和/或 .gitignore 的目录视为空，
    允许在已有的 git 空仓上 init。git init 本身幂等，重跑无害。

    .gitignore 也忽略：它是 git 工作流的常规伴随文件，且正是 init 自身
    （_ensure_workspace_gitignore）会写/维护的文件。若不忽略，llmw 写出的 .gitignore
    会反过来挡住自身的 re-init（自反矛盾）。
    """
    ignored = {".git", ".gitignore"}
    return all(entry.name in ignored for entry in path.iterdir())


def _write_workspace_agents_md(workspace_root: Path, display_name: str) -> None:
    """spec §4 (0.4.0+): 按 workspace-agents-md-template.md 拷贝生成 <workspace>/AGENTS.md (SSOT)。

    用户所有的 workspace 宪法 (工具无关纪律)——CLI 仅在 init 时拷模板 + 替换 4 占位符:
      {{WORKSPACE_DISPLAY_NAME}} / {{SETUP_DATE}} / {{WORKSPACE_SPEC_VERSION}} / {{CLI_VERSION}}

    spec §12: AGENTS.md 已存在 → 拒绝覆盖 (schema 是用户所有)。
    """
    agents_md = workspace_root / "AGENTS.md"
    if agents_md.exists():
        raise WorkspaceExists(
            f"{agents_md} 已存在；拒绝覆盖",
            hint="AGENTS.md 是 workspace schema（用户所有），若需更新请手动编辑",
        )

    refs = workspace_spec_templates_dir()
    if not refs.is_dir():
        raise SkillMissing(
            f"找不到 workspace SKILL references/ 目录: {refs}",
            hint="运行 `git submodule update --init` 初始化 SKILL",
        )
    try:
        tmpl = (refs / "workspace-agents-md-template.md").read_text(encoding="utf-8")
    except OSError as e:
        raise SetupFailed(
            f"读取 workspace AGENTS.md 模板失败: {e.filename}",
            hint="检查 my_SKILL/llm-workspace-management/references/ 是否完整",
        )

    mapping = {
        "WORKSPACE_DISPLAY_NAME": display_name,
        "SETUP_DATE": date.today().isoformat(),
        "WORKSPACE_SPEC_VERSION": WORKSPACE_SPEC_VERSION,
        "CLI_VERSION": __version__,
    }
    for k, v in mapping.items():
        tmpl = tmpl.replace("{{" + k + "}}", v)
    leftover = re.findall(r"\{\{[^}]+\}\}", tmpl)
    if leftover:
        raise SetupFailed(
            f"workspace AGENTS.md 模板占位符未替换干净: {leftover}",
            hint="检查模板占位符与 mapping 是否匹配",
        )

    try:
        atomic_write(agents_md, tmpl)
    except OSError as e:
        raise SetupFailed(
            f"写入 workspace AGENTS.md 失败: {e.filename or e.strerror}",
            hint="检查磁盘空间 + 目录权限",
        )


def _write_workspace_claude_md(workspace_root: Path, display_name: str) -> None:
    """spec §4 (0.4.0+): 按 workspace-claude-md-template.md 拷贝生成 <workspace>/CLAUDE.md (薄壳)。

    薄壳 = @AGENTS.md 一行 + 声明 (~10 行);CLI 仅在 init 时拷模板 + 替换 1 占位符
      {{WORKSPACE_DISPLAY_NAME}} (薄壳不持 spec 版本——版本在 AGENTS.md §六)。
    spec §4 字面: 薄壳仅替换 WORKSPACE_DISPLAY_NAME,不共享 AGENTS.md 的 4 键 mapping。

    spec §12: CLAUDE.md 已存在 → 拒绝覆盖 (薄壳也是 schema, 用户所有)。
    """
    claude_md = workspace_root / "CLAUDE.md"
    if claude_md.exists():
        raise WorkspaceExists(
            f"{claude_md} 已存在；拒绝覆盖",
            hint="CLAUDE.md 是 workspace schema 薄壳（用户所有），若需更新请手动编辑",
        )

    refs = workspace_spec_templates_dir()
    if not refs.is_dir():
        raise SkillMissing(
            f"找不到 workspace SKILL references/ 目录: {refs}",
            hint="运行 `git submodule update --init` 初始化 SKILL",
        )
    try:
        tmpl = (refs / "workspace-claude-md-template.md").read_text(encoding="utf-8")
    except OSError as e:
        raise SetupFailed(
            f"读取 workspace CLAUDE.md 模板失败: {e.filename}",
            hint="检查 my_SKILL/llm-workspace-management/references/ 是否完整",
        )

    # spec §4: 薄壳仅替换 WORKSPACE_DISPLAY_NAME。残留占位符 = 模板漂移,assert 兜底。
    tmpl = tmpl.replace("{{WORKSPACE_DISPLAY_NAME}}", display_name)
    leftover = re.findall(r"\{\{[^}]+\}\}", tmpl)
    if leftover:
        raise SetupFailed(
            f"workspace CLAUDE.md 模板占位符未替换干净: {leftover}",
            hint="薄壳模板应仅含 {{WORKSPACE_DISPLAY_NAME}};检查模板是否漂移",
        )

    try:
        atomic_write(claude_md, tmpl)
    except OSError as e:
        raise SetupFailed(
            f"写入 workspace CLAUDE.md 失败: {e.filename or e.strerror}",
            hint="检查磁盘空间 + 目录权限",
        )


def _write_workspace_memory_index(workspace_root: Path) -> None:
    """spec §9.1: 拷 references/fixtures/memory-index.txt → <workspace>/MEMORY/MEMORY.md (索引)。

    无 frontmatter、被 <workspace>/CLAUDE.md 用 @MEMORY/MEMORY.md import 会话常驻。
    幂等 (spec §9.1): 已存在则跳过——MEMORY 是 LLM agent 私有记忆,init 重跑不应覆盖。

    与 _write_workspace_claude_md 的拒绝策略对照:
      - workspace.toml / CLAUDE.md / .gitignore / workspace_models.toml: 已存在 → 拒绝 / 块替换
      - MEMORY/MEMORY.md: 已存在 → 跳过(spec §9.1 idempotent)
    """
    target = workspace_root / "MEMORY" / "MEMORY.md"
    if target.exists():
        # spec §9.1 idempotent: 已存在即跳过;由 skill 在 cross-wiki MEMORY 工作时维护
        return

    refs = workspace_spec_templates_dir()
    if not refs.is_dir():
        raise SkillMissing(
            f"找不到 workspace SKILL references/ 目录: {refs}",
            hint="运行 `git submodule update --init` 初始化 SKILL",
        )
    try:
        content = (refs / "fixtures" / "memory-index.txt").read_text(encoding="utf-8")
    except OSError as e:
        raise SetupFailed(
            f"读取 workspace MEMORY.md fixture 失败: {e.filename}",
            hint="检查 my_SKILL/llm-workspace-management/references/fixtures/ 是否完整",
        )

    (workspace_root / "MEMORY").mkdir(parents=True, exist_ok=True)
    try:
        atomic_write(target, content)
    except OSError as e:
        raise SetupFailed(
            f"写入 workspace MEMORY.md 失败: {e.filename or e.strerror}",
            hint="检查磁盘空间 + 目录权限",
        )


def init(path: Path, display_name: str = "LLM Wiki Workspace") -> Path:
    """初始化 workspace 根。返回 path

    git 由用户在外部自行 init/clone——CLI 不碰 git；若 path 已是 git 空仓
    （仅含 .git/.gitignore），允许在其上 init。
    """
    path = path.resolve()
    if path.exists():
        if not _is_effectively_empty(path):
            raise WorkspaceExists(
                f"路径已存在且非空: {path}",
                hint="指定空目录或先备份内容（仅含 .git / .gitignore 的 git 空仓可直接 init）",
            )
    else:
        path.mkdir(parents=True)

    ws_store.create_skeleton(path)

    # 写 workspace 级 .gitignore（spec §10：无论是否启用 git 都生成，便于后续补 git）
    _ensure_workspace_gitignore(path)

    # spec §3: workspace init 时刻创建空 workspace_models.toml 骨架
    # （含 schema_version=2 + 空 models=[]；save 内置 chmod 600 + NFS 跳过）
    from llmw.models.store import (
        create_skeleton as create_models_skeleton,
        save as save_models,
    )

    save_models(path, create_models_skeleton(path))

    # spec §4 (0.4.0+): 先写 AGENTS.md (SSOT), 再写 CLAUDE.md (薄壳)
    _write_workspace_agents_md(path, display_name)
    _write_workspace_claude_md(path, display_name)

    # spec §9.1: 拷 workspace MEMORY.md 索引（agent 跨 wiki 持久化记忆,LLM 拥有）
    _write_workspace_memory_index(path)

    print(f"[llmw] workspace 已初始化于 {path}", file=sys.stdout)
    print(
        f"[llmw] cd {path} 后可用 `llmw wiki add <name>` 新建第一个 wiki",
        file=sys.stdout,
    )
    return path


# ===== config =====


def _check_key(key: str) -> tuple:
    if key not in CONFIG_KEYS:
        raise InvalidConfigKey(
            f"KEY '{key}' 不在白名单",
            hint=f"可用 KEY: {', '.join(sorted(CONFIG_KEYS.keys()))}",
        )
    return CONFIG_KEYS[key]


def config_get(workspace_root: Path, key: Optional[str]) -> None:
    """无 KEY: dump 整个 workspace.toml; 有 KEY: 打印该字段值"""
    ws = ws_store.load(workspace_root)
    if key is None:
        # dump
        print(f"# workspace: {workspace_root}")
        if ws.default_model is not None:
            print(f"default_model = {ws.default_model}")
        else:
            print("# default_model: <unset>")
        if ws.enter_cli is not None:
            print(f"enter_cli = {ws.enter_cli}")
        else:
            print("# enter_cli: <unset> (= claude)")
        print(f"created_at = {ws.created_at}")
        print(f"templates_version = {ws.templates_version}")
        print(f"schema_version = {ws.schema_version}")
        wikis = list(ws.wikis.keys())
        if wikis:
            print(f"wikis = {', '.join(sorted(wikis))}")
        else:
            print("# wikis: <empty>")
        return

    if key not in CONFIG_KEYS:
        raise ConfigKeyMissing(f"KEY '{key}' 不存在")
    val = getattr(ws, key, None)
    if val is None:
        print("<unset>")
    else:
        print(val)


def config_set(workspace_root: Path, key: str, value: str) -> None:
    can_set, _, expected_type = _check_key(key)
    if not can_set:
        raise InvalidConfigKey(f"KEY '{key}' 不可 set（只读）")
    if key == "enter_cli":
        _check_enter_cli(value)
    ws = ws_store.load(workspace_root)
    setattr(ws, key, expected_type(value))
    ws_store.save(workspace_root, ws)
    print(f"✓ {key} = {value!r}", file=sys.stdout)


def config_unset(workspace_root: Path, key: str) -> None:
    can_set, can_unset, _ = _check_key(key)
    if not can_unset:
        raise KeyNotUnsettable(f"KEY '{key}' 不可 unset")
    ws = ws_store.load(workspace_root)
    setattr(ws, key, None)
    ws_store.save(workspace_root, ws)
    print(f"✓ {key} unset", file=sys.stdout)


def config_interactive(workspace_root: Path) -> None:
    """TTY 下 `llmw config` 无参数进入; 非 TTY 打印字段列表后退出 0"""
    if not sys.stdin.isatty():
        # 非 TTY: 打印字段列表 + 用法, 退出 0
        print("[llmw] config 子命令: get KEY / set KEY VALUE / unset KEY")
        print(f"[llmw] workspace: {workspace_root}")
        print("[llmw] 可用 KEY:")
        for i, key in enumerate(CONFIG_KEYS, 1):
            can_set, can_unset, _ = CONFIG_KEYS[key]
            ro = " (只读)" if not can_set else ""
            print(f"  {i}. {key}{ro}")
        return

    ws = ws_store.load(workspace_root)
    keys = list(CONFIG_KEYS.keys())
    while True:
        print(f"\nworkspace 配置项 ({workspace_root}/workspace.toml):")
        for i, key in enumerate(keys, 1):
            can_set, can_unset, _ = CONFIG_KEYS[key]
            val = getattr(ws, key, None)
            cur = repr(val) if val is not None else "<unset>"
            ro = " (只读)" if not can_set else ""
            print(f"  {i}. {key}{ro}    当前: {cur}")

        try:
            choice = input(f"\n选择要编辑的项 [1-{len(keys)}, q 退出]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice.lower() in ("q", ""):
            return
        try:
            idx = int(choice) - 1
            key = keys[idx]
        except (ValueError, IndexError):
            print("[llmw] 输入无效，重试")
            continue

        can_set, _, _ = CONFIG_KEYS[key]
        if not can_set:
            print(f"⚠ {key} 是只读字段，无法编辑")
            try:
                again = input("继续编辑？[Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return
            if again in ("n", "no"):
                return
            continue

        cur = getattr(ws, key, None) or ""
        prompt = "输入新值（回车跳过 / '-' 清空）: "
        try:
            new_val = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return
        if new_val == "":
            pass  # 跳过
        elif new_val == "-":
            config_unset(workspace_root, key)
            ws = ws_store.load(workspace_root)
        else:
            config_set(workspace_root, key, new_val)
            ws = ws_store.load(workspace_root)

        try:
            again = input("继续编辑？[Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if again in ("n", "no"):
            return


# ===== list =====


def list_wikis(
    workspace_root: Path, as_json: bool = False, tag_filter: Optional[List[str]] = None
) -> int:
    """返回 0; 输出由调用方决定 (stdout)"""
    ws = ws_store.load(workspace_root)
    rows = []
    for name in sorted(ws.wikis.keys()):
        entry = ws.wikis[name]
        wiki_path = workspace_root / entry.path
        exists = wiki_path.is_dir()
        meta = None
        if exists:
            toml_p = wiki_path / "wiki_metadata.toml"
            if toml_p.is_file():
                from llmw.wiki.store import load as wiki_load

                try:
                    meta = wiki_load(wiki_path)
                except Exception:
                    meta = None

        if tag_filter:
            tags = meta.tags if meta else []
            if not all(t in tags for t in tag_filter):
                continue

        # 通过 resolve 拿 model 来源（若失败则不阻断 list, 标为 <unresolved>）
        model_info = None
        try:
            from llmw.models.resolve import resolve_for_wiki

            entry_obj = resolve_for_wiki(workspace_root, name)
            model_info = {
                "model_id": entry_obj.model_id,
                "name": entry_obj.name,
                "source": "wiki override"
                if (meta and meta.model)
                else "registry default",
            }
        except (
            WikiNotFound,
            WikiDirMissing,
            ModelNotInRegistry,
            ModelDefaultNotSet,
            ModelDefaultAmbiguous,
            RegistryMissing,
            OSError,
            TOMLDecodeError,
        ):
            model_info = None

        # last_activity: 派生自 <wiki>/wiki/log.md mtime(与 wiki show 同款派生,见 wiki/manager.py:show)
        last_activity = None
        if exists:
            log_md_p = wiki_path / "wiki" / "log.md"
            if log_md_p.is_file():
                last_activity = datetime.fromtimestamp(
                    log_md_p.stat().st_mtime, tz=timezone.utc
                ).isoformat()

        rows.append(
            {
                "name": name,
                "path": entry.path,
                "exists": exists,
                "display_name": meta.display_name if meta else "",
                "tags": list(meta.tags) if meta else [],
                "model": model_info["model_id"]
                if model_info
                else (meta.model if meta else None),
                "model_source": model_info["source"] if model_info else None,
                "created_at": meta.created_at if meta else None,
                "last_activity": last_activity,
            }
        )

    if as_json:
        import json

        out = [
            {
                "name": r["name"],
                "path": r["path"],
                "display_name": r["display_name"] or None,
                "tags": r["tags"],
                "model": r["model"],
                "model_source": r["model_source"],
                "wiki_dir_exists": r["exists"],
                "last_activity": r["last_activity"],
            }
            for r in rows
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # 表格
    if not rows:
        print("# (no wikis registered)")
        return 0
    # meta 缺失时时间列用 "-" 占位, 保持列对齐
    created_cells = [r["created_at"] or "-" for r in rows]
    last_activity_cells = [r["last_activity"] or "-" for r in rows]
    name_w = max(len(r["name"]) for r in rows + [{"name": "NAME"}])
    path_w = max(len(r["path"]) for r in rows + [{"path": "PATH"}])
    created_w = max(len(c) for c in created_cells + ["CREATED"])
    last_activity_w = max(len(c) for c in last_activity_cells + ["LAST_ACTIVITY"])
    dn_w = max(
        len(r["display_name"] or "-") for r in rows + [{"display_name": "DISPLAY_NAME"}]
    )
    tags_w = max(len(",".join(r["tags"]) or "-") for r in rows + [{"tags": ["TAGS"]}])
    model_cells = []
    for r in rows:
        if r["model"]:
            cell = r["model"]
            if r["model_source"]:
                cell += f" ({r['model_source']})"
        else:
            cell = "-"
        model_cells.append(cell)
    model_w = max(len(c) for c in model_cells + ["MODEL"])
    print(
        f"{'NAME'.ljust(name_w)}  {'PATH'.ljust(path_w)}  "
        f"{'CREATED'.ljust(created_w)}  "
        f"{'LAST_ACTIVITY'.ljust(last_activity_w)}  "
        f"{'DISPLAY_NAME'.ljust(dn_w)}  {'TAGS'.ljust(tags_w)}  "
        f"{'MODEL'.ljust(model_w)}"
    )
    for r, created, last_act, model_cell in zip(
        rows, created_cells, last_activity_cells, model_cells
    ):
        prefix = "⚠ " if not r["exists"] else "  "
        dn = r["display_name"] or "-"
        tags = ",".join(r["tags"]) or "-"
        print(
            f"{prefix}{r['name'].ljust(name_w - 2)}  {r['path'].ljust(path_w)}  "
            f"{created.ljust(created_w)}  "
            f"{last_act.ljust(last_activity_w)}  "
            f"{dn.ljust(dn_w)}  {tags.ljust(tags_w)}  {model_cell.ljust(model_w)}"
        )
    return 0
