"""wiki_metadata.toml 读写 + schema 校验 + 模板填充"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from llmw._compat import toml_loads, toml_dump
from llmw.config import templates_dir
from llmw.errors import InvalidTagValue, InvalidWikiName, SchemaVersionUnsupported
from llmw.fsutil import atomic_write, now_iso8601

SCHEMA_VERSION_SUPPORTED = 1
NAME_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
TAG_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


@dataclass
class WikiMetadata:
    schema_version: int
    name: str
    topic: str
    created_at: str
    updated_at: str
    display_name: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    model: Optional[str] = None

    def bump(self):
        """任何 set 后调用，更新 updated_at"""
        self.updated_at = now_iso8601()


def validate_name(name: str) -> None:
    if not NAME_RE.match(name):
        raise InvalidWikiName(
            f"wiki 名 '{name}' 非法: 仅允许小写字母 / 数字 / '-' / '_'，长度 1-64",
        )


def validate_tag(tag: str) -> None:
    if not TAG_RE.match(tag):
        raise InvalidTagValue(
            f"tag '{tag}' 非法: 仅允许小写字母 / 数字 / '-' / '_'，长度 1-32",
        )


def load(wiki_dir: Path) -> WikiMetadata:
    """从 <wiki_dir>/wiki_metadata.toml 加载并校验"""
    toml_path = wiki_dir / "wiki_metadata.toml"
    with open(toml_path, "rb") as f:
        raw = toml_loads(f.read().decode("utf-8"))

    sv = raw.get("schema_version")
    if sv != SCHEMA_VERSION_SUPPORTED:
        raise SchemaVersionUnsupported(
            f"wiki_metadata.toml schema_version={sv} 不被支持 (当前 CLI 仅支持 v{SCHEMA_VERSION_SUPPORTED})",
            hint="升级 CLI 或手动迁移",
        )
    return WikiMetadata(
        schema_version=sv,
        name=raw["name"],
        topic=raw["topic"],
        created_at=raw["created_at"],
        updated_at=raw["updated_at"],
        display_name=raw.get("display_name", ""),
        description=raw.get("description", ""),
        tags=list(raw.get("tags", [])),
        model=raw.get("model") or None,
    )


def save(wiki_dir: Path, meta: WikiMetadata) -> None:
    """原子写回 wiki_metadata.toml"""
    toml_path = wiki_dir / "wiki_metadata.toml"
    data = {
        "schema_version": meta.schema_version,
        "name": meta.name,
        "topic": meta.topic,
        "created_at": meta.created_at,
        "updated_at": meta.updated_at,
        "display_name": meta.display_name,
        "description": meta.description,
        "tags": meta.tags,
    }
    if meta.model is not None:
        data["model"] = meta.model

    import io
    buf = io.StringIO()
    toml_dump(data, buf)
    atomic_write(toml_path, buf.getvalue())


def create_skeleton(wiki_dir: Path, name: str, topic: str) -> WikiMetadata:
    """add 时调用：从 templates/wiki_metadata.toml.template 拷出实例"""
    template_path = templates_dir() / "wiki_metadata.toml.template"
    template = template_path.read_text(encoding="utf-8")
    now = now_iso8601()
    text = (template
            .replace("__NAME__", name)
            .replace("__TOPIC__", topic)
            .replace("__NOW_ISO8601__", now))

    toml_path = wiki_dir / "wiki_metadata.toml"
    atomic_write(toml_path, text)

    return load(wiki_dir)
