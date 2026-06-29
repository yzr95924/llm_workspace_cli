"""workspace 级业务: init / config / list"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from llmw import __version__
from llmw.errors import (
    ConfigKeyMissing,
    GitUnavailable,
    InvalidConfigKey,
    KeyNotUnsettable,
    ModelDefaultAmbiguous,
    ModelDefaultNotSet,
    ModelNotInRegistry,
    RegistryMissing,
    WikiDirMissing,
    WikiNotFound,
    WorkspaceExists,
)
from llmw._compat import TOMLDecodeError
from llmw.fsutil import now_iso8601
from llmw.workspace import store as ws_store

# config KEY 白名单: name -> (can_set, can_unset, type)
CONFIG_KEYS = {
    "default_model": (True, True, str),
    "templates_version": (False, False, str),  # 只读
    "created_at": (False, False, str),  # 只读
    "schema_version": (False, False, int),  # 只读
}


# ===== workspace 级 .gitignore helper =====

# workspace 级 .gitignore managed block 内容（registry + overlay + trash 备份目录）
# 单仓模型：wiki 是 workspace 直属子目录，*/.claude/settings.local.json 通配覆盖所有
# wiki 的 overlay secret，不依赖 per-wiki .gitignore / wiki scaffold（见 §9.6）。
# .llmw-trash/ 由 wiki remove --purge 写入,默认走备份路径(spec wiki-spec.md:14 "delete 带备份")
GITIGNORE_LINES = (
    "workspace_models.toml",
    "*/.claude/settings.local.json",
    ".llmw-trash/",
)


def _ensure_workspace_gitignore(workspace_root: Path) -> None:
    """确保 workspace 级 .gitignore 含 llmw managed block（两行 secret 忽略）。

    - 文件不存在 → 创建（带 marker 段）
    - 已是最新两行 block → 跳过
    - 有老 block（如早期单行）→ 替换 marker 区间为最新两行
    - 无 block → 追加
    """
    import re

    from llmw.fsutil import atomic_write

    gitignore = workspace_root / ".gitignore"
    marker_start = "# >>> llmw (managed by llmw) >>>"
    marker_end = "# <<< llmw <<<"
    block = marker_start + "\n" + "\n".join(GITIGNORE_LINES) + "\n" + marker_end

    if not gitignore.is_file():
        atomic_write(gitignore, block + "\n")
        return

    text = gitignore.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(marker_start) + r".*?" + re.escape(marker_end), re.DOTALL)
    m = pattern.search(text)
    if m:
        if m.group(0) == block:
            return  # 已是最新两行 block
        new_text = pattern.sub(block, text)  # 老 block → 替换为两行
    else:
        # 无 block → 追加（保证前导换行 + 末尾换行）
        sep = "" if (text.endswith("\n") or not text) else "\n"
        tail = "" if text.endswith("\n") else "\n"
        new_text = text + sep + block + tail
    atomic_write(gitignore, new_text)


# ===== init =====


def _is_effectively_empty(path: Path) -> bool:
    """目录是否为空（忽略 git 元数据 .git）。
    只含 .git（git 仓目录或 worktree 的 .git 指针文件）的目录视为空，
    允许在已有的 git 空仓上 init。git init 本身幂等，重跑无害。
    """
    return all(entry.name == ".git" for entry in path.iterdir())


def init(path: Path, git: bool = True) -> Path:
    """初始化 workspace 根。返回 path"""
    path = path.resolve()
    if path.exists():
        if not _is_effectively_empty(path):
            raise WorkspaceExists(
                f"路径已存在且非空: {path}",
                hint="指定空目录或先备份内容（仅含 .git 的 git 空仓可直接 init）",
            )
    else:
        path.mkdir(parents=True)

    if git:
        try:
            subprocess.run(
                ["git", "init", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise GitUnavailable(f"git init 失败: {e}")

    ws_store.create_skeleton(path)

    # 写 workspace 级 .gitignore（workspace 本身就是 git 仓）
    _ensure_workspace_gitignore(path)

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
        prompt = f"输入新值（回车跳过 / '-' 清空）: "
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
        except (WikiNotFound, WikiDirMissing, ModelNotInRegistry, ModelDefaultNotSet, ModelDefaultAmbiguous, RegistryMissing, OSError, TOMLDecodeError):
            model_info = None

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
            }
            for r in rows
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # 表格
    if not rows:
        print("# (no wikis registered)")
        return 0
    name_w = max(len(r["name"]) for r in rows + [{"name": "NAME"}])
    path_w = max(len(r["path"]) for r in rows + [{"path": "PATH"}])
    print(f"{'NAME'.ljust(name_w)}  {'PATH'.ljust(path_w)}  DISPLAY_NAME  TAGS  MODEL")
    for r in rows:
        prefix = "⚠ " if not r["exists"] else "  "
        dn = r["display_name"] or "-"
        tags = ",".join(r["tags"]) or "-"
        if r["model"]:
            model_cell = r["model"]
            if r["model_source"]:
                model_cell += f" ({r['model_source']})"
        else:
            model_cell = "-"
        print(
            f"{prefix}{r['name'].ljust(name_w - 2)}  {r['path'].ljust(path_w)}  {dn}  {tags}  {model_cell}"
        )
    return 0
