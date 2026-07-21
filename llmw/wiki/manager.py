"""wiki 级业务: add / remove / show / config / rename"""

import errno
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional

from llmw import WIKI_SPEC_VERSION, __version__
from llmw.errors import (
    BackupFailed,
    InvalidConfigKey,
    InvalidWikiName,
    KeyNotUnsettable,
    MissingRequiredFlag,
    ModelDefaultAmbiguous,
    ModelDefaultNotSet,
    ModelNotInRegistry,
    PurgeRequiresConfirmation,
    SchemaVersionUnsupported,
    WikiDirMissing,
    WikiExists,
    WikiNotFound,
)
from llmw._compat import TOMLDecodeError
from llmw.models.resolve import resolve_for_wiki
from llmw.models.store import RegistryMissing, load
from llmw.fsutil import now_iso8601, safe_rmtree
from llmw.wiki import init_wiki
from llmw.wiki import store as wiki_store
from llmw.workspace import store as ws_store


def _wiki_abs(workspace_root: Path, name: str) -> Path:
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(
            f"wiki '{name}' 不在当前 workspace 中",
            hint="运行 `llmw list` 查看已注册 wiki",
        )
    return workspace_root / ws.wikis[name].path


def _print_git_hint(wiki_dir: Path) -> None:
    """spec §7 (0.16.0+) git 红线: CLI 不碰 git——落盘后打印手动 hint,让用户自行决定。

    .gitkeep 占位文件已在 init_wiki.render_and_write 无条件落盘(7 个空目录);
    用户 `git add .` 时空目录自然纳入跟踪。
    """
    print(f"[llmw] wiki 已落盘为纯目录树: {wiki_dir}", file=sys.stdout)
    print("[llmw] 若需 git 版本控制,请手动执行:", file=sys.stdout)
    print(f"[llmw]   cd {wiki_dir}", file=sys.stdout)
    print(
        "[llmw]   git init && git symbolic-ref HEAD refs/heads/main",
        file=sys.stdout,
    )
    print(
        '[llmw]   git add . && git commit -m "Initial wiki scaffold"',
        file=sys.stdout,
    )
    print(
        "[llmw] .gitkeep 占位文件已放入空目录;后续 raw/ 真实文件由你 `git add` 后纳入跟踪。",
        file=sys.stdout,
    )


def _interactive_fill_metadata(workspace_root, wiki_dir, meta):
    """交互填充 display_name / description / tags / model"""

    def ask(label, cur):
        suffix = " [当前: <未设置>]" if not cur else f" [当前: {cur!r}]"
        try:
            v = input(f"  {label}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise
        return v

    # display_name
    v = ask("display_name", meta.display_name)
    if v:
        meta.display_name = v
    # description
    v = ask("description", meta.description)
    if v:
        meta.description = v
    # tags
    cur_tags = list(meta.tags)
    while True:
        print(f"  tags [当前: {cur_tags}]: <a 添加 / r 移除 / s 替换 / d 完成>")
        try:
            op = input("    操作: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if op == "a":
            t = input("    新 tag: ").strip()
            if t:
                wiki_store.validate_tag(t)
                if t not in cur_tags:
                    cur_tags.append(t)
        elif op == "r":
            if not cur_tags:
                print("    (空)")
                continue
            for i, t in enumerate(cur_tags):
                print(f"      {i + 1}. {t}")
            try:
                idx = int(input("    移除编号: ").strip()) - 1
                if 0 <= idx < len(cur_tags):
                    cur_tags.pop(idx)
            except (ValueError, EOFError, KeyboardInterrupt):
                pass
        elif op == "s":
            t = input("    全部 tags (逗号分隔): ").strip()
            new_tags = [x.strip() for x in t.split(",") if x.strip()]
            for x in new_tags:
                wiki_store.validate_tag(x)
            cur_tags = new_tags
        elif op == "d":
            break
    meta.tags = cur_tags

    # model
    v = ask("model", meta.model or "")
    if v:
        meta.model = v

    meta.bump()
    wiki_store.save(wiki_dir, meta)
    print("[llmw] metadata 已写入 wiki_metadata.toml", file=sys.stdout)


def add(
    workspace_root: Path,
    name: str,
    topic: Optional[str] = None,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    model: Optional[str] = None,
) -> Path:
    wiki_store.validate_name(name)

    ws = ws_store.load(workspace_root)
    if name in ws.wikis:
        raise WikiExists(f"wiki '{name}' 已存在")

    # Phase 2: 校验 model_id 存在于 registry
    if model is not None:
        try:
            reg = load(workspace_root)
        except RegistryMissing:
            raise ModelDefaultNotSet(
                "workspace 还没有 registry, 无法校验 model",
                hint="先跑 `llmw model add --model-id=... --name=... --base-url=... --api-key=... --default` 至少一条",
            )
        if model not in reg.models:
            raise ModelNotInRegistry(
                f"model_id '{model}' 不在 registry 中",
                hint="运行 `llmw model list` 查看可用 model_id",
            )

    wiki_dir = workspace_root / name

    # spec §8: 文件级拒绝条件(在 mkdir 前检查,失败无需清理半成品目录)
    init_wiki.check_not_initialized(wiki_dir)

    # 非 TTY 下: 必须所有 metadata flag 齐
    if not sys.stdin.isatty():
        missing = []
        if display_name is None:
            missing.append("--display-name")
        if description is None:
            missing.append("--description")
        if not tags:
            missing.append("--tag")
        if model is None:
            missing.append("--model")
        if missing:
            raise MissingRequiredFlag(
                f"非 TTY 下 add 缺 metadata flag: {', '.join(missing)}",
                hint="补齐 flag 重试，或在 TTY 下用交互模式",
            )

    # 默认 topic = name
    if topic is None:
        topic = name

    # 创建子目录(exist_ok=True: 允许目标目录已存在; spec §8 已在更早 check_not_initialized
    # 阻断 AGENTS.md / CLAUDE.md / wiki/index.md / MEMORY.md / tags.md / SCRIPTS.md
    # 已存在的覆盖场景)
    wiki_dir.mkdir(parents=False, exist_ok=True)

    # CLI 内联实现 wiki 骨架(spec 0.2.0 起取代原 setup_wiki.py subprocess)
    init_wiki.render_and_write(
        wiki_dir,
        topic,
        date.today().isoformat(),
        cli_version=__version__,
        spec_version=WIKI_SPEC_VERSION,
    )

    # 写 wiki_metadata.toml
    meta = wiki_store.create_skeleton(wiki_dir, name, topic)

    # 交互模式填 metadata
    if sys.stdin.isatty():
        try:
            _interactive_fill_metadata(workspace_root, wiki_dir, meta)
        except (EOFError, KeyboardInterrupt):
            print("\n[llmw] 跳过剩余 metadata", file=sys.stderr)
        meta = wiki_store.load(wiki_dir)  # reload
    else:
        # 非 TTY: 一次性写入 flags
        if display_name is not None:
            meta.display_name = display_name
        if description is not None:
            meta.description = description
        if tags:
            meta.tags = tags
        if model is not None:
            meta.model = model
        meta.bump()
        wiki_store.save(wiki_dir, meta)

    # 注册到 workspace.toml
    ws.wikis[name] = ws_store.WikiEntry(
        name=name,
        path=name,
        created_at=now_iso8601(),
    )
    ws_store.save(workspace_root, ws)

    print(f"[llmw] wiki 已创建: {name} ({wiki_dir})", file=sys.stdout)
    # spec §7 (0.16.0+) git 红线: CLI 不碰 git,统一打印手动 hint。
    # (cli.py 的 `--git` flag 保留为向后兼容的 vestigial flag,不再传到本函数;
    # 0.16.0 前它会触发 git init/commit,现已无操作——无论是否传 --git 都打印同一份 hint)
    _print_git_hint(wiki_dir)
    return wiki_dir


def _purge_with_backup(
    workspace_root: Path,
    wiki_path: Path,
    name: str,
    no_backup: bool,
) -> None:
    """`wiki remove --purge` 的物理删除:默认备份到 .llmw-trash/,失败阻断。

    spec wiki-spec.md:14 "delete 带备份" 的 CLI 落地;--no-backup 是 escape hatch
    (CI / 脚本场景)。

    Args:
        workspace_root: workspace 根(用于 .llmw-trash/ 和 .gitignore 升级)。
        wiki_path: 待删除的 wiki 目录绝对路径。
        name: wiki 名(用于备份目录命名)。
        no_backup: True → 直接 rmtree;False → 先备份。

    Raises:
        BackupFailed: 备份步骤任一失败(mkdir / rename);失败时不删 wiki。
    """
    # 1. 确保 workspace .gitignore managed block 为最新版（含 .llmw-trash/ 排除行）
    # 老 workspace 的旧版 block（行数/内容不等）会被整体替换为当前 GITIGNORE_LINES。
    # .gitignore 写入失败不阻断备份(用户可手动 gitignore)。
    try:
        from llmw.workspace.manager import _ensure_workspace_gitignore

        _ensure_workspace_gitignore(workspace_root)
    except (OSError, ImportError):
        pass

    if no_backup:
        safe_rmtree(wiki_path)
        print(f"[llmw] --no-backup: 直接删除 {wiki_path}", file=sys.stdout)
        return

    # 2. 默认路径: 备份到 <workspace>/.llmw-trash/<name>-<ISO8601>/
    # now_iso8601 形如 "2026-06-29T12:00:00Z";冒号不能在路径里,剥掉。
    ts = now_iso8601().replace(":", "")
    trash_root = workspace_root / ".llmw-trash"
    backup_path = trash_root / f"{name}-{ts}"

    try:
        trash_root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise BackupFailed(
            f"无法创建备份目录 {trash_root}: {e}",
            hint="检查 workspace 目录权限",
        )

    if backup_path.exists():
        # 同一秒内两次 purge 才可能撞上;极少但要给清晰错误
        raise BackupFailed(
            f"备份目标已存在: {backup_path}",
            hint="同一秒内连续 purge 两次? 重试",
        )

    try:
        # POSIX rename 在同一 FS 下是原子的;wiki_path 和 backup_path 都在
        # workspace 下,共享 FS,rename 等价于 mv 且无中间态。
        wiki_path.rename(backup_path)
    except OSError as e:
        raise BackupFailed(
            f"备份移动失败: {wiki_path} → {backup_path}: {e}",
            hint="检查磁盘空间 + 权限; --no-backup 跳过备份直接删",
        )

    print(f"[llmw] 备份: {backup_path}", file=sys.stdout)


def remove(
    workspace_root: Path,
    name: str,
    purge: bool = False,
    yes: bool = False,
    no_backup: bool = False,
) -> None:
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(f"wiki '{name}' 不在当前 workspace 中")

    wiki_path = workspace_root / ws.wikis[name].path

    if purge and not yes:
        if not sys.stdin.isatty():
            raise PurgeRequiresConfirmation(
                "非 TTY 下 --purge 需要 --yes 确认",
                hint="加 --yes 或在 TTY 下手动确认",
            )
        try:
            ans = (
                input(f"将删除 {wiki_path} 子目录及所有内容，确认？[y/N]: ")
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            print()
            ans = "n"
        if ans not in ("y", "yes"):
            print("[llmw] 取消")
            return

    del ws.wikis[name]
    ws_store.save(workspace_root, ws)

    if purge:
        if wiki_path.is_dir():
            _purge_with_backup(workspace_root, wiki_path, name, no_backup=no_backup)

    suffix = " 并删除子目录" if purge else ""
    print(f"[llmw] wiki '{name}' 已取消注册{suffix}", file=sys.stdout)


def rename(
    workspace_root: Path,
    old: str,
    new: str,
    as_json: bool = False,
    quiet: bool = False,
) -> None:
    """rename wiki ``old`` → ``new``: 3 阶段原地 rename + 廉价回滚。

    改动 3 处 (workspace.toml key / 子目录 / wiki_metadata.toml name) + 若 topic
    默认值==old 则同步 topic。子目录走 POSIX rename (同 FS 下 O(1) 原子, 只改目录项,
    不动 inode 数据 / symlink), raw/ 下大量文件零拷贝 —— 取代旧的 staging copytree 副本。

    失败策略 (每步失败都回滚到 rename 前一致状态):
    - Phase 1 (改 old_path metadata) 失败: atomic_write 不留半成品, old_path 完全不动
    - Phase 2 (old_path.rename(new_path)) 失败: metadata 改回 (EXDEV 附 hint), 目录仍在 old_path
    - Phase 3 (切 workspace.toml) 失败: fs rename 回来 + metadata 改回

    Raises:
        InvalidWikiName: new 不符 NAME_RE,或 old == new
        WikiNotFound: old 不在 workspace registry
        WikiExists: new 已在 workspace registry,或 new_path 已存在
        WikiDirMissing: old_path 目录或 wiki_metadata.toml 缺失
        SchemaVersionUnsupported: wiki_metadata.toml schema_version 不被支持
        OSError: 文件系统操作失败 (如跨 FS 的 EXDEV; 经 InternalError 包装由 cli 顶层处理)
    """
    wiki_store.validate_name(new)
    if old == new:
        raise InvalidWikiName(
            f"--old 与 --new 均为 '{old}', 无变更",
            hint="提供不同的 new 名",
        )

    ws = ws_store.load(workspace_root)
    if old not in ws.wikis:
        raise WikiNotFound(
            f"wiki '{old}' 不在当前 workspace 中",
            hint="运行 `llmw list` 查看已注册 wiki",
        )
    if new in ws.wikis:
        raise WikiExists(f"wiki '{new}' 已存在")

    old_path = workspace_root / ws.wikis[old].path
    new_path = workspace_root / new
    if new_path.exists():
        # 防 registry 与 fs 不一致 (残留空目录 / 手工 mkdir)
        raise WikiExists(
            f"目标路径已存在: {new_path}",
            hint="清理后重试, 或选别的 new 名",
        )
    if not old_path.is_dir() or not (old_path / "wiki_metadata.toml").is_file():
        # registry 有登记但磁盘目录不完整 (被手动移走 / 删除 / 残缺)
        raise WikiDirMissing(
            f"wiki 目录或 wiki_metadata.toml 缺失: {old_path}",
            hint=f"registry 仍登记 '{old}', 但磁盘目录不完整; 检查是否被手动移走",
        )

    # created_at 跨 rename 保留,维持时间锚点
    created_at = ws.wikis[old].created_at

    # ===== Phase 1: 原地改 old_path 的 metadata (name→new) =====
    # wiki_store.save 走 atomic_write (tmp + rename), 失败不留半成品 → old_path 完全不动。
    # 目录名此刻仍为 old, 与 metadata.name=new 短暂不一致, Phase 2 原子 rename 后即对齐。
    meta = wiki_store.load(old_path)  # SchemaVersionUnsupported / TOMLDecodeError 透传
    old_topic = meta.topic
    meta.name = new
    if meta.topic == old:
        meta.topic = new
    meta.bump()
    wiki_store.save(old_path, meta)

    # ===== Phase 2: 原子重命名 old_path → new_path (O(1), 同 FS) =====
    # POSIX rename 同 FS 下只改目录项, 不动 inode 数据 / symlink → raw/ 下大量文件零拷贝。
    # 跨 FS 抛 EXDEV (workspace 目录应同 FS; NFS 不安全, 见 AGENTS.md)。
    try:
        old_path.rename(new_path)
    except OSError as e:
        # 回滚 Phase 1: metadata 的 name/topic 恢复成 rename 前
        try:
            meta.name = old
            meta.topic = old_topic
            wiki_store.save(old_path, meta)
        except OSError as rollback_err:
            print(
                f"[llmw] warning: 回滚 metadata 失败: {rollback_err}; "
                f"{old_path}/wiki_metadata.toml 可能停留在 name={new}",
                file=sys.stderr,
            )
        if e.errno == errno.EXDEV:
            print(
                "[llmw] hint: old/new 不在同一文件系统 (EXDEV); workspace 目录应位于"
                "同一 FS, NFS 挂载不安全 (见 AGENTS.md)",
                file=sys.stderr,
            )
        raise

    # ===== Phase 3: 切换 workspace.toml (del old / add new) =====
    try:
        ws.wikis[new] = ws_store.WikiEntry(name=new, path=new, created_at=created_at)
        del ws.wikis[old]
        ws_store.save(workspace_root, ws)
    except (OSError, TOMLDecodeError):
        # 回滚 Phase 2 + 1: fs rename 回来 + metadata 恢复
        try:
            new_path.rename(old_path)
            meta.name = old
            meta.topic = old_topic
            wiki_store.save(old_path, meta)
        except OSError as rollback_err:
            print(
                f"[llmw] warning: 回滚失败: {rollback_err}; fs/registry 可能不一致, "
                f"手动检查 {new_path} 与 workspace.toml",
                file=sys.stderr,
            )
        raise

    topic_changed = old_topic == old

    if as_json:
        out = {
            "old": old,
            "new": new,
            "path": str(new_path),
            "topic_changed": topic_changed,
            "topic_old": old_topic if topic_changed else None,
            "topic_new": new if topic_changed else None,
            "created_at": created_at,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if not quiet:
        print(f"[llmw] wiki 已重命名: {old} → {new}", file=sys.stdout)
        print(f"[llmw]   path: {new_path}", file=sys.stdout)
        if topic_changed:
            print(
                f"[llmw]   topic: {old_topic} → {new} (随 name 同步)",
                file=sys.stdout,
            )
        print(f"[llmw]   created_at 保留: {created_at}", file=sys.stdout)
    else:
        # 安静模式: 只保留主信息行, 抑制 path / topic / created_at 详情
        print(f"[llmw] wiki 已重命名: {old} → {new}", file=sys.stdout)


def show(workspace_root: Path, name: str, as_json: bool = False) -> None:
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(f"wiki '{name}' 不在当前 workspace 中")

    wiki_path = workspace_root / ws.wikis[name].path
    meta = None
    if (wiki_path / "wiki_metadata.toml").is_file():
        try:
            meta = wiki_store.load(wiki_path)
        except (OSError, TOMLDecodeError, SchemaVersionUnsupported) as e:
            print(
                f"[llmw] warning: 无法读取 wiki_metadata.toml: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            meta = None

    claude_md_p = wiki_path / "CLAUDE.md"
    raw_p = wiki_path / "raw"
    wiki_sub_p = wiki_path / "wiki"
    claude_md_exists = claude_md_p.is_file()
    raw_count = sum(1 for _ in raw_p.rglob("*") if _.is_file()) if raw_p.is_dir() else 0
    wiki_count = (
        sum(1 for _ in wiki_sub_p.rglob("*.md") if _.is_file())
        if wiki_sub_p.is_dir()
        else 0
    )
    # last_activity: 从 <wiki>/wiki/log.md mtime 派生 —— 不依赖 SKILL/CLI 配合,
    # SKILL spec 强制 ingest/query/lint 后必须写 log.md,OS mtime 直接给真实活跃时刻。
    # log.md 不存在 → None(降级为 "-");NFS 上 stat 安全(chmod 才会 silently fail)。
    last_activity = None
    log_md_p = wiki_sub_p / "log.md"
    if log_md_p.is_file():
        last_activity = datetime.fromtimestamp(
            log_md_p.stat().st_mtime, tz=timezone.utc
        ).isoformat()

    # 通过 resolve 拿最终 model + 来源
    final_model = None
    model_source = None
    try:
        m = resolve_for_wiki(workspace_root, name)
        final_model = m.model_id
        model_source = "wiki override" if (meta and meta.model) else "registry default"
    except (
        WikiNotFound,
        WikiDirMissing,
        ModelNotInRegistry,
        ModelDefaultNotSet,
        ModelDefaultAmbiguous,
    ):
        # resolve 失败 → 维持向后兼容：旧逻辑
        final_model = (meta.model if meta else None) or ws.default_model
        if final_model:
            if meta and meta.model:
                model_source = "wiki.metadata.model"
            elif ws.default_model:
                model_source = "workspace.default_model"

    if as_json:
        out = {
            "name": name,
            "path": str(wiki_path),
            "topic": meta.topic if meta else None,
            "display_name": meta.display_name if meta else None,
            "description": meta.description if meta else None,
            "tags": list(meta.tags) if meta else [],
            "model": final_model,
            "model_source": model_source,
            "schema_version": meta.schema_version if meta else None,
            "created_at": meta.created_at if meta else None,
            "last_activity": last_activity,
            "existence": {
                "claude_md": claude_md_exists,
                "wiki_metadata_toml": meta is not None,
                "raw_dir": raw_p.is_dir(),
                "wiki_dir": wiki_sub_p.is_dir(),
            },
            "counts": {
                "raw_files": raw_count,
                "wiki_pages": wiki_count,
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # 表格: 收集 (label, value) 对, label 宽度 = max(len(label)), 统一对齐
    created_line = meta.created_at if meta else "-"
    model_line = final_model or "-"
    if model_source:
        model_line += f"  (fallback: {model_source})"
    rows = [
        ("NAME", name),
        ("PATH", str(wiki_path)),
        ("TOPIC", meta.topic if meta else "-"),
        ("DISPLAY_NAME", meta.display_name if meta else "-"),
        ("DESCRIPTION", meta.description if meta else "-"),
        ("TAGS", ",".join(meta.tags) if meta and meta.tags else "-"),
        ("MODEL", model_line),
        ("CREATED_AT", created_line),
        ("LAST_ACTIVITY", last_activity or "-"),
        ("CLAUDE_MD", "✓ found" if claude_md_exists else "✗ missing"),
        ("WIKI_METADATA", "✓ found" if meta else "✗ missing"),
        (
            "RAW_DIR",
            f"{'✓ found' if raw_p.is_dir() else '✗ missing'} ({raw_count} files)",
        ),
        (
            "WIKI_DIR",
            f"{'✓ found' if wiki_sub_p.is_dir() else '✗ missing'} ({wiki_count} pages)",
        ),
    ]
    label_w = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"{label.ljust(label_w)}  {value}")


# wiki config KEY 白名单
WIKI_CONFIG_KEYS = {
    "display_name": (True, True, str),
    "description": (True, True, str),
    "tags": (True, True, list),
    "model": (True, True, str),
    # name / topic / schema_version / created_at / updated_at 全部只读
}


def wiki_config_get(workspace_root: Path, name: str, key: Optional[str]) -> None:
    wiki_dir = _wiki_abs(workspace_root, name)
    meta = wiki_store.load(wiki_dir)
    if key is None:
        # dump
        print(f"# wiki: {name} ({wiki_dir}/wiki_metadata.toml)")
        for k in WIKI_CONFIG_KEYS:
            v = getattr(meta, k)
            print(f"{k} = {v!r}")
        return
    if key not in WIKI_CONFIG_KEYS:
        raise InvalidConfigKey(
            f"KEY '{key}' 不在 wiki 白名单",
            hint=f"可用 KEY: {', '.join(WIKI_CONFIG_KEYS.keys())}",
        )
    val = getattr(meta, key)
    if val is None or val == "" or val == []:
        print("<unset>")
    else:
        print(val if not isinstance(val, list) else ",".join(val))


def wiki_config_set(workspace_root: Path, name: str, key: str, value: str) -> None:
    if key not in WIKI_CONFIG_KEYS:
        raise InvalidConfigKey(f"KEY '{key}' 不在 wiki 白名单")
    can_set, _, _ = WIKI_CONFIG_KEYS[key]
    if not can_set:
        raise InvalidConfigKey(f"KEY '{key}' 不可 set（只读）")
    wiki_dir = _wiki_abs(workspace_root, name)
    meta = wiki_store.load(wiki_dir)
    if key == "tags":
        new_tags = [t.strip() for t in value.split(",") if t.strip()]
        for t in new_tags:
            wiki_store.validate_tag(t)
        meta.tags = new_tags
    elif key == "model":
        try:
            reg = load(workspace_root)
        except RegistryMissing:
            raise ModelDefaultNotSet(
                "workspace 还没有 registry, 无法校验 model",
                hint="先跑 `llmw model add ...` 至少一条",
            )
        if value not in reg.models:
            raise ModelNotInRegistry(
                f"model_id '{value}' 不在 registry 中",
                hint="运行 `llmw model list` 查看可用 model_id",
            )
        meta.model = value or None
    else:
        setattr(meta, key, value or None)
    meta.bump()
    wiki_store.save(wiki_dir, meta)
    print(f"✓ {key} 已更新", file=sys.stdout)


def wiki_config_unset(workspace_root: Path, name: str, key: str) -> None:
    if key not in WIKI_CONFIG_KEYS:
        raise InvalidConfigKey(f"KEY '{key}' 不在 wiki 白名单")
    can_set, can_unset, _ = WIKI_CONFIG_KEYS[key]
    if not can_unset:
        raise KeyNotUnsettable(f"KEY '{key}' 不可 unset")
    wiki_dir = _wiki_abs(workspace_root, name)
    meta = wiki_store.load(wiki_dir)
    if key == "tags":
        meta.tags = []
    elif key in ("display_name", "description"):
        setattr(meta, key, "")
    elif key == "model":
        meta.model = None
    meta.bump()
    wiki_store.save(wiki_dir, meta)
    print(f"✓ {key} unset", file=sys.stdout)


def wiki_config_interactive(workspace_root: Path, name: str) -> None:
    """wiki config 无参数: 默认就是交互模式（不要求 TTY）"""
    wiki_dir = _wiki_abs(workspace_root, name)
    meta = wiki_store.load(wiki_dir)
    keys = list(WIKI_CONFIG_KEYS.keys())
    while True:
        print(f'\nwiki "{name}" 配置项 ({wiki_dir}/wiki_metadata.toml):')
        for i, key in enumerate(keys, 1):
            v = getattr(meta, key)
            cur = repr(v) if v else "<unset>"
            print(f"  {i}. {key}    当前: {cur}")
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

        if key == "tags":
            # 子菜单: a / r / s
            cur_tags = list(meta.tags)
            while True:
                print(f"  当前 tags: {cur_tags}")
                print("  a) 添加 tag\n  r) 移除 tag\n  s) 替换全部 tags")
                try:
                    op = input("操作 [a/r/s/q]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    break
                if op == "a":
                    t = input("新 tag: ").strip()
                    if t:
                        wiki_store.validate_tag(t)
                        if t not in cur_tags:
                            cur_tags.append(t)
                elif op == "r":
                    if not cur_tags:
                        print("(空)")
                        continue
                    for i2, t in enumerate(cur_tags):
                        print(f"  {i2 + 1}. {t}")
                    try:
                        idx2 = int(input("移除编号: ").strip()) - 1
                        if 0 <= idx2 < len(cur_tags):
                            cur_tags.pop(idx2)
                    except (ValueError, EOFError, KeyboardInterrupt):
                        pass
                elif op == "s":
                    t = input("全部 tags (逗号分隔): ").strip()
                    new_tags = [x.strip() for x in t.split(",") if x.strip()]
                    for x in new_tags:
                        wiki_store.validate_tag(x)
                    cur_tags = new_tags
                else:
                    break
            meta.tags = cur_tags
        elif key == "model":
            # model 是 registry 引用, 必须校验存在; 失败则提示重试, 不退出交互
            # （与 wiki_config_set 行为一致, 但交互式走重试而非 raise, 避免丢失已填字段）
            while True:
                try:
                    new_v = input("输入新值（回车跳过 / '-' 清空）: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break  # 跳过, 不改动 model
                if new_v == "":
                    break  # 跳过
                if new_v == "-":
                    meta.model = None
                    break
                try:
                    reg = load(workspace_root)
                except RegistryMissing:
                    print(
                        "    [校验失败] workspace 还没有 registry, 先 `llmw model add ...` 至少一条"
                    )
                    continue
                if new_v not in reg.models:
                    avail = ", ".join(reg.models) or "(空)"
                    print(
                        f"    [校验失败] model_id '{new_v}' 不在 registry 中（可用: {avail}）"
                    )
                    continue
                meta.model = new_v
                break
        else:
            # display_name / description: 自由文本, 无校验
            try:
                new_v = input("输入新值（回车跳过 / '-' 清空）: ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if new_v == "":
                pass
            elif new_v == "-":
                setattr(meta, key, "")
            else:
                setattr(meta, key, new_v)
        meta.bump()
        wiki_store.save(wiki_dir, meta)
        try:
            again = input("继续编辑？[Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if again in ("n", "no"):
            return
