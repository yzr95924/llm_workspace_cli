"""manifest 内存模型 + parse/serialize。纯模块：不碰文件系统、不碰 errors。"""

import re
from pathlib import Path
from typing import Dict, List

DEFAULT_MODEL = "claude-sonnet-4-6"
SCHEMA_VERSION = "1"


class WikiEntry:
    def __init__(self, name, path, display_name, created, description="", model=None, tags=None):
        self.name = name
        self.path = path
        self.display_name = display_name
        self.description = description or ""
        self.model = model  # None => 继承 workspace.default_model
        self.created = created
        self.tags = list(tags or [])

    def effective_model(self, default_model):
        return self.model if self.model else default_model

    def to_dict(self):
        d = {
            "path": self.path,
            "display_name": self.display_name,
            "created": self.created,
            "tags": list(self.tags),
        }
        if self.description:
            d["description"] = self.description
        if self.model:
            d["model"] = self.model
        return d


class Manifest:
    def __init__(self, schema_version, created, default_model, wikis):
        self.schema_version = schema_version
        self.created = created
        self.default_model = default_model
        self.wikis = wikis  # Dict[str, WikiEntry]（保持插入顺序）

    def to_dict(self):
        return {
            "schema_version": self.schema_version,
            "created": self.created,
            "workspace": {"default_model": self.default_model},
            "wikis": {name: w.to_dict() for name, w in self.wikis.items()},
        }


def empty_manifest(created, default_model=DEFAULT_MODEL):
    return Manifest(SCHEMA_VERSION, created, default_model, {})


def parse(text):
    """把 TOML 文本解析成 Manifest。语法错误时抛 tomllib.TOMLDecodeError
    （调用方映射为 manifest-parse-failed）。未知字段在此忽略；
    语义校验放在 validate()。"""
    try:
        import tomllib  # py>=3.11
    except ModuleNotFoundError:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    data = tomllib.loads(text)

    ws = data.get("workspace", {})
    default_model = ws.get("default_model", DEFAULT_MODEL)

    wikis: Dict[str, WikiEntry] = {}
    for name, w in data.get("wikis", {}).items():
        wikis[name] = WikiEntry(
            name=name,
            path=w.get("path", ""),
            display_name=w.get("display_name", name),
            created=w.get("created", ""),
            description=w.get("description", ""),
            model=w.get("model"),
            tags=w.get("tags", []),
        )
    return Manifest(
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        created=data.get("created", ""),
        default_model=default_model,
        wikis=wikis,
    )


def serialize(m):
    """把 Manifest 转 TOML，经 workspace.dump_toml（惰性 import，保持 manifest
    在 import 期为纯模块——无环，因为 workspace 只 import errors）。"""
    from wiki_workspace.workspace import dump_toml

    return dump_toml(m.to_dict())


KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 缺口 #5 —— 软集合；可自由扩充
KNOWN_MODELS = {
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
}

# 可经 `llmw config <name> set <key> <value>` 设置（spec §3.6）
SETTABLE_KEYS = {"display_name", "description", "model", "tags"}
REQUIRED_KEYS = {"path", "display_name", "created"}  # 不可 unset


class Issue:
    def __init__(self, severity, category, message, field=None):
        self.severity = severity  # "error" | "warn"
        self.category = category
        self.message = message
        self.field = field


def _path_is_safe(path_str):
    p = Path(path_str)
    if p.is_absolute():
        return False
    if ".." in p.parts:
        return False
    return True


def validate(m, workspace_root):
    """返回 list[Issue]。'error' 会阻断命令；'warn' 不会。"""
    issues: List[Issue] = []
    seen = set()
    for name, w in m.wikis.items():
        # 名字 kebab + 唯一
        if not KEBAB_RE.match(name):
            issues.append(
                Issue(
                    "error",
                    "manifest-validation-failed",
                    "wiki 名 '{}' 必须 kebab-case".format(name),
                )
            )
        if name in seen:
            issues.append(
                Issue(
                    "error",
                    "manifest-validation-failed",
                    "wikis.{} 重复".format(name),
                )
            )
        seen.add(name)
        # path 安全 + 位于 workspace 内
        if not _path_is_safe(w.path):
            issues.append(
                Issue(
                    "error",
                    "manifest-validation-failed",
                    "wikis.{}.path '{}' 必须位于 workspace 内".format(name, w.path),
                )
            )
        else:
            full = Path(workspace_root) / w.path
            if not full.is_dir():
                issues.append(
                    Issue(
                        "error",
                        "manifest-validation-failed",
                        "wikis.{}.path '{}' 不存在".format(name, w.path),
                    )
                )
            elif not (full / "CLAUDE.md").is_file():
                issues.append(
                    Issue(
                        "error",
                        "manifest-validation-failed",
                        "wikis.{}.path '{}' 不是合法 wiki（缺 CLAUDE.md）".format(name, w.path),
                    )
                )
        # 日期
        if not DATE_RE.match(w.created):
            issues.append(
                Issue(
                    "error",
                    "manifest-validation-failed",
                    "wikis.{}.created '{}' 不是 YYYY-MM-DD".format(name, w.created),
                )
            )
        # model（仅 warn）
        if w.model and w.model not in KNOWN_MODELS:
            issues.append(
                Issue(
                    "warn",
                    "manifest-validation-failed",
                    "wikis.{}.model '{}' 未知；将继续".format(name, w.model),
                )
            )
    return issues


def load_and_validate(text, workspace_root):
    """解析 + 校验。语法错误时抛 tomllib 解析异常（调用方映射为 manifest-parse-failed）。
    返回 (Manifest, list[Issue])。"""
    m = parse(text)
    return m, validate(m, workspace_root)
