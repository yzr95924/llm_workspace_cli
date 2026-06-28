"""llmw model <action> 业务层"""

import json
import sys
from pathlib import Path
from typing import Optional

from llmw.errors import (
    MissingRequiredFlag,
    ModelIdConflict,
    ModelIsDefault,
    ModelNotInRegistry,
    PurgeRequiresConfirmation,
)
from llmw._compat import toml_loads
from llmw.models.redact import redact_api_key
from llmw.models.store import (
    ModelEntry,
    Registry,
    RegistryMissing,
    create_skeleton,
    load,
    save,
    validate_api_key,
    validate_base_url,
    validate_model_id,
    validate_name,
)


# ===== set_default（manager 层唯一保证 is_default 唯一的入口）=====


def set_default(reg: Registry, model_id: str) -> None:
    """保证 is_default 全局唯一。add --default 与 set-default 都走这里。"""
    if model_id not in reg.models:
        raise ModelNotInRegistry(
            f"model_id '{model_id}' 不在 registry 中",
            hint=f"可用: {', '.join(reg.models.keys()) or '(空)'}",
        )
    for m in reg.models.values():
        m.is_default = False
    reg.models[model_id].is_default = True
    reg.bump()


# ===== _load_lenient =====


def _load_lenient(workspace_root: Path) -> Registry:
    """manager 层用：容忍 load() 的 ModelDefaultNotSet（"有 models 但无 default"）。

    当 registry 因 is_default 计数不合规被 load 拒绝时，手动从 TOML 读出
    models（视为全部 is_default=False），构造等价的 Registry 对象返回。

    其他错误（RegistryMissing / SchemaVersionUnsupported / InvalidModelField /
    ModelIdConflict / ModelDefaultAmbiguous）仍由 load() 直接抛——这些是结构性
    问题，不应被 lenient 吞掉。
    """
    from llmw.errors import ModelDefaultNotSet

    try:
        return load(workspace_root)
    except ModelDefaultNotSet:
        # 重新读 TOML，构造等价的 Registry（is_default 全 False）
        toml_path = workspace_root / "workspace_models.toml"
        with open(toml_path, "rb") as f:
            raw = toml_loads(f.read().decode("utf-8"))
        models = {}
        for entry in raw.get("models", []):
            models[entry["model_id"]] = ModelEntry(
                model_id=entry["model_id"],
                name=entry["name"],
                base_url=entry["base_url"],
                api_key=entry["api_key"],
                is_default=False,
            )
        return Registry(
            schema_version=raw["schema_version"],
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            models=models,
        )


# ===== model_add =====


def model_add(
    workspace_root: Path,
    model_id: Optional[str] = None,
    name: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    as_default: bool = False,
) -> None:
    """新增 model 条目。字段校验 + 重复 model_id 检测。
    --default 时自动取消旧默认（走 set_default）。
    TTY 下缺 flag → 交互提示；非 TTY → MissingRequiredFlag。
    """
    # 字段预校验（一次性给出所有错误）
    if model_id is not None:
        validate_model_id(model_id)
    if name is not None:
        validate_name(name)
    if base_url is not None:
        validate_base_url(base_url)
    if api_key is not None:
        validate_api_key(api_key)

    # TTY 交互模式
    if sys.stdin.isatty():

        def ask(label, cur, validator):
            suffix = f" [当前: {cur!r}]" if cur else " [当前: <未设置>]"
            while True:
                try:
                    v = input(f"  {label}{suffix}: ").strip()
                except (EOFError, KeyboardInterrupt):
                    raise
                if v == "" and cur:
                    return cur
                try:
                    validator(v) if v else None
                    return v or None
                except Exception as e:
                    print(f"    [校验失败] {e.message}")
                    continue

        if model_id is None:
            model_id = ask("model_id", "", validate_model_id)
        if name is None:
            name = ask("name", "", validate_name)
        if base_url is None:
            base_url = ask("base_url", "", validate_base_url)
        if api_key is None:
            api_key = ask("api_key", "", validate_api_key)
    else:
        missing = []
        if not model_id:
            missing.append("--model-id")
        if not name:
            missing.append("--name")
        if not base_url:
            missing.append("--base-url")
        if not api_key:
            missing.append("--api-key")
        if missing:
            raise MissingRequiredFlag(
                f"非 TTY 下 model add 缺 flag: {', '.join(missing)}",
                hint="补齐 flag 重试，或在 TTY 下用交互模式",
            )

    # 加载现有 registry；不存在 → 初始化
    try:
        reg = load(workspace_root)
    except RegistryMissing:
        reg = create_skeleton(workspace_root)

    # 重复检测
    if model_id in reg.models:
        raise ModelIdConflict(
            f"model_id '{model_id}' 已存在",
            hint="换一个 model_id，或先 `llmw model remove --model-id <ID>`",
        )

    reg.models[model_id] = ModelEntry(
        model_id=model_id,
        name=name,
        base_url=base_url,
        api_key=api_key,
        is_default=False,
    )
    if as_default:
        set_default(reg, model_id)
    else:
        reg.bump()
    save(workspace_root, reg)
    print(f"✓ model '{model_id}' 已添加", file=sys.stdout)


# ===== model_list =====


def model_list(workspace_root: Path, as_json: bool = False) -> int:
    reg = load(workspace_root)
    if as_json:
        out = [
            {
                "model_id": m.model_id,
                "name": m.name,
                "base_url": m.base_url,
                "api_key": redact_api_key(m.api_key),
                "is_default": m.is_default,
            }
            for m in reg.models.values()
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if not reg.models:
        print("# (no models registered)")
        return 0
    print(f"{'MODEL_ID'.ljust(20)}  {'NAME'.ljust(20)}  DEFAULT  BASE_URL  API_KEY")
    for m in sorted(reg.models.values(), key=lambda x: (not x.is_default, x.model_id)):
        star = "✓" if m.is_default else " "
        print(
            f"{m.model_id.ljust(20)}  {m.name[:20].ljust(20)}  {star}      {m.base_url}  {redact_api_key(m.api_key)}"
        )
    return 0


# ===== model_show =====


def model_show(workspace_root: Path, model_id: str, as_json: bool = False) -> None:
    reg = load(workspace_root)
    if model_id not in reg.models:
        raise ModelNotInRegistry(
            f"model_id '{model_id}' 不在 registry 中",
            hint=f"可用: {', '.join(reg.models.keys()) or '(空)'}",
        )
    m = reg.models[model_id]
    if as_json:
        out = {
            "model_id": m.model_id,
            "name": m.name,
            "base_url": m.base_url,
            "api_key": redact_api_key(m.api_key),
            "is_default": m.is_default,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"MODEL_ID      {m.model_id}")
    print(f"NAME          {m.name}")
    print(f"BASE_URL      {m.base_url}")
    print(f"API_KEY       {redact_api_key(m.api_key)}")
    print(f"IS_DEFAULT    {m.is_default}")
    print(f"SCHEMA        v{reg.schema_version}")
    print(f"CREATED_AT    {reg.created_at}")
    print(f"UPDATED_AT    {reg.updated_at}")


# ===== model_set_default =====


def model_set_default(workspace_root: Path, model_id: str) -> None:
    reg = _load_lenient(workspace_root)  # 容忍 ModelDefaultNotSet（unset-default 后再 set-default）
    set_default(reg, model_id)
    save(workspace_root, reg)
    print(f"✓ '{model_id}' 设为默认（旧的自动取消）", file=sys.stdout)


# ===== model_unset_default =====


def model_unset_default(workspace_root: Path) -> None:
    reg = _load_lenient(workspace_root)  # 容忍 ModelDefaultNotSet
    any_unset = False
    for m in reg.models.values():
        if m.is_default:
            m.is_default = False
            any_unset = True
    if not any_unset:
        print("[llmw] 当前没有默认 model", file=sys.stdout)
        return
    reg.bump()
    save(workspace_root, reg)
    print("✓ 默认已清空（之后 enter 会报 ModelDefaultNotSet）", file=sys.stdout)


# ===== model_remove =====


def model_remove(workspace_root: Path, model_id: str, yes: bool = False) -> None:
    reg = _load_lenient(workspace_root)  # 容忍 ModelDefaultNotSet
    if model_id not in reg.models:
        raise ModelNotInRegistry(
            f"model_id '{model_id}' 不在 registry 中",
            hint=f"可用: {', '.join(reg.models.keys()) or '(空)'}",
        )
    target = reg.models[model_id]
    if target.is_default:
        raise ModelIsDefault(
            f"model '{model_id}' 是默认, 不能直接 remove",
            hint="先 `llmw model set-default --model-id <其他>` 或 `llmw model unset-default`",
        )

    # 非 TTY 下需要 --yes
    if not sys.stdin.isatty():
        if not yes:
            raise PurgeRequiresConfirmation(
                "非 TTY 下 model remove 需要 --yes 确认",
                hint="加 --yes 或在 TTY 下手动确认",
            )
    else:
        if not yes:
            try:
                ans = input(f"将删除 model '{model_id}', 确认？[y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                ans = "n"
            if ans not in ("y", "yes"):
                print("[llmw] 取消")
                return

    del reg.models[model_id]
    reg.bump()
    save(workspace_root, reg)
    print(f"✓ model '{model_id}' 已删除", file=sys.stdout)
    if not reg.models:
        # registry 变空 → 删除文件（避免空文件留在 .gitignore 列表里）
        path = workspace_root / "workspace_models.toml"
        if path.is_file():
            path.unlink()
        print("[llmw] registry 已清空, 移除 workspace_models.toml", file=sys.stdout)
