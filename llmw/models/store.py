"""workspace_models.toml 读写 + 字段校验 + chmod 600"""

import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from llmw._compat import toml_loads, toml_dump
from llmw.errors import (
    InvalidModelField,
    ModelDefaultAmbiguous,
    ModelDefaultNotSet,
    ModelIdConflict,
    RegistryMissing,
    SchemaVersionUnsupported,
)
from llmw.fsutil import atomic_write, now_iso8601
from llmw.wiki.store import NAME_RE  # 复用 ^[a-z0-9_-]{1,64}$

SCHEMA_VERSION_SUPPORTED = 2
NAME_MAX_LEN = 128


@dataclass
class ModelEntry:
    """[[models]] 单条"""

    model_id: str
    name: str
    base_url: str
    api_key: str
    is_default: bool = False


@dataclass
class Registry:
    schema_version: int
    created_at: str
    updated_at: str
    models: Dict[str, ModelEntry] = field(default_factory=dict)

    def bump(self):
        self.updated_at = now_iso8601()


# ===== 字段校验 =====


def validate_model_id(model_id: str) -> None:
    if not NAME_RE.match(model_id):
        raise InvalidModelField(
            f"model_id '{model_id}' 非法: 仅允许小写字母 / 数字 / '-' / '_'，长度 1-64",
        )


def validate_name(name: str) -> None:
    if not (1 <= len(name) <= NAME_MAX_LEN):
        raise InvalidModelField(
            f"name 长度非法: '{name}' (长度 {len(name)}, 要求 1-{NAME_MAX_LEN})",
        )


def validate_base_url(url: str) -> None:
    if not (url.startswith("http://") or url.startswith("https://")):
        raise InvalidModelField(
            f"base_url 非法: '{url}' (必须以 http:// 或 https:// 开头)",
        )


def validate_api_key(key: str) -> None:
    if not key:
        raise InvalidModelField("api_key 不能为空")


# ===== load =====


def load(workspace_root: Path) -> Registry:
    """从 <workspace_root>/workspace_models.toml 加载并校验。
    文件不存在 → RegistryMissing。
    """
    toml_path = workspace_root / "workspace_models.toml"
    if not toml_path.is_file():
        raise RegistryMissing(
            f"workspace_models.toml 不存在: {toml_path}",
            hint="运行 `llmw model add --model-id ... --name ... --base-url ... --api-key ... --default` 初始化",
        )

    with open(toml_path, "rb") as f:
        raw = toml_loads(f.read().decode("utf-8"))

    sv = raw.get("schema_version")
    if sv != SCHEMA_VERSION_SUPPORTED:
        raise SchemaVersionUnsupported(
            f"workspace_models.toml schema_version={sv} 不被支持 (当前 CLI 仅支持 v{SCHEMA_VERSION_SUPPORTED})",
            hint="升级 CLI 或手动迁移 schema_version",
        )

    models: Dict[str, ModelEntry] = {}
    for entry in raw.get("models", []):
        m = ModelEntry(
            model_id=entry["model_id"],
            name=entry["name"],
            base_url=entry["base_url"],
            api_key=entry["api_key"],
            is_default=bool(entry.get("is_default", False)),
        )
        # 字段校验（抛 InvalidModelField）
        validate_model_id(m.model_id)
        validate_name(m.name)
        validate_base_url(m.base_url)
        validate_api_key(m.api_key)
        # 唯一性
        if m.model_id in models:
            raise ModelIdConflict(
                f"workspace_models.toml 中 model_id '{m.model_id}' 重复",
            )
        models[m.model_id] = m

    # is_default 计数（一致性校验）
    defaults = [mid for mid, e in models.items() if e.is_default]
    if len(defaults) > 1:
        raise ModelDefaultAmbiguous(
            f"workspace_models.toml 中存在 {len(defaults)} 条 is_default=true: {defaults}",
            hint="运行 `llmw model set-default --model-id <ID>` 修复唯一性",
        )
    if not defaults and models:
        # 有 models 但无 default → ModelDefaultNotSet
        raise ModelDefaultNotSet(
            "workspace_models.toml 中没有 is_default=true 的条目",
            hint="运行 `llmw model set-default --model-id <ID>` 标记默认",
        )

    return Registry(
        schema_version=sv,
        created_at=raw["created_at"],
        updated_at=raw["updated_at"],
        models=models,
    )


# ===== save =====


def save(workspace_root: Path, reg: Registry) -> None:
    """原子写回 + chmod 600。save 不重复校验 is_default 唯一性（约束在 manager 层 set_default()）。"""
    toml_path = workspace_root / "workspace_models.toml"
    data = {
        "schema_version": reg.schema_version,
        "created_at": reg.created_at,
        "updated_at": reg.updated_at,
    }
    models_list = []
    for m in reg.models.values():
        d = {
            "model_id": m.model_id,
            "name": m.name,
            "base_url": m.base_url,
            "api_key": m.api_key,
        }
        if m.is_default:
            d["is_default"] = True
        models_list.append(d)
    if models_list:
        data["models"] = models_list

    buf = io.StringIO()
    toml_dump(data, buf)
    atomic_write(toml_path, buf.getvalue())
    # 安全：registry 含 api_key，强制 600
    try:
        os.chmod(toml_path, 0o600)
    except OSError:
        # NFS / 某些 FS 不支持 chmod；best-effort
        pass


# ===== 初始化 / 创建 =====


def create_skeleton(workspace_root: Path) -> Registry:
    """init 时不创建 registry；提供空 Registry 初始化函数供 manager.add 用。"""
    now = now_iso8601()
    return Registry(
        schema_version=SCHEMA_VERSION_SUPPORTED,
        created_at=now,
        updated_at=now,
    )
