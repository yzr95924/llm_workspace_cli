"""wiki 级业务: add / remove / show / config"""

import json
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from llmw import WIKI_SPEC_VERSION, __version__
from llmw.errors import (
    BackupFailed, InvalidConfigKey, KeyNotUnsettable, MissingRequiredFlag,
    ModelDefaultAmbiguous, ModelDefaultNotSet, ModelNotInRegistry,
    PurgeRequiresConfirmation, SchemaVersionUnsupported,
    WikiDirMissing, WikiExists, WikiNotFound,
)
from llmw._compat import TOMLDecodeError
from llmw.models.resolve import resolve_for_wiki
from llmw.models.store import RegistryMissing, load
from llmw.fsutil import now_iso8601, safe_rmtree
from llmw.wiki import git_init, init_wiki
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
    git: bool = False,
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
                hint="先跑 `llmw model add --model-id ... --name ... --base-url ... --api-key ... --default` 至少一条",
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

    # 创建子目录(exist_ok=True: 允许目标目录已存在, 此时 --git 由 git_init 内部走
    # is-inside-work-tree 检查跳过; spec §8 已在更早 check_not_initialized 阻断
    # CLAUDE.md / wiki/index.md 已存在的覆盖场景)
    wiki_dir.mkdir(parents=False, exist_ok=True)

    # CLI 内联实现 wiki 骨架(spec 0.2.0 起取代原 setup_wiki.py subprocess)
    init_wiki.render_and_write(
        wiki_dir, topic, date.today().isoformat(),
        cli_version=__version__, spec_version=WIKI_SPEC_VERSION,
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

    # opt-in git(spec §7); 前置不通过由 git_init 内部 warn 跳过,不阻断
    git_applied = False
    if git:
        git_applied = git_init.init(wiki_dir)

    print(f"[llmw] wiki 已创建: {name} ({wiki_dir})", file=sys.stdout)
<<<<<<< HEAD
    print(
        f"[llmw] 请 git add + commit 跟踪（建议 commit message: `wiki: add {name}`）",
        file=sys.stdout,
    )
    return wiki_dir


def remove(
    workspace_root: Path, name: str, purge: bool = False, yes: bool = False
=======
    if git and git_applied:
        print(
            f"[llmw] 已 git init + commit (分支 main, 消息: Initial wiki scaffold)",
            file=sys.stdout,
        )
    elif git and not git_applied:
        # 前置不通过(git 缺失 / 已在仓内),已在 stderr 警告
        pass
    else:
        print(
            f"[llmw] 未启用 git: 如需跟踪,手动 `git init && git add . && git commit "
            f"-m 'Initial wiki scaffold'`;或下次 add 时加 --git",
            file=sys.stdout,
        )
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
    # 1. 确保 .llmw-trash/ 在 workspace .gitignore(managed block 升级)
    # 老 workspace 只有 2 行 block 时,会自动替换为新 3 行 block。
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
>>>>>>> ccdffdeb8507da8e3d1b54baf18bfd965ba92a90
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

<<<<<<< HEAD
    print(
        f"[llmw] wiki '{name}' 已取消注册" + (" 并删除子目录" if purge else ""),
        file=sys.stdout,
    )
=======
    suffix = " 并删除子目录" if purge else ""
    print(f"[llmw] wiki '{name}' 已取消注册{suffix}", file=sys.stdout)
>>>>>>> ccdffdeb8507da8e3d1b54baf18bfd965ba92a90


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
            "updated_at": meta.updated_at if meta else None,
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

    # 表格
    print(f"NAME              {name}")
    print(f"PATH              {wiki_path}")
    print(f"TOPIC             {meta.topic if meta else '-'}")
    print(f"DISPLAY_NAME      {meta.display_name if meta else '-'}")
    print(f"DESCRIPTION       {meta.description if meta else '-'}")
    print(f"TAGS              {','.join(meta.tags) if meta and meta.tags else '-'}")
    model_line = final_model or "-"
    if model_source:
        model_line += f"  (fallback: {model_source})"
    print(f"MODEL             {model_line}")
    print(f"CLAUDE_MD         {'✓ found' if claude_md_exists else '✗ missing'}")
    print(f"WIKI_METADATA     {'✓ found' if meta else '✗ missing'}")
    print(
        f"RAW_DIR           {'✓ found' if raw_p.is_dir() else '✗ missing'} ({raw_count} files)"
    )
    print(
        f"WIKI_DIR          {'✓ found' if wiki_sub_p.is_dir() else '✗ missing'} ({wiki_count} pages)"
    )


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
