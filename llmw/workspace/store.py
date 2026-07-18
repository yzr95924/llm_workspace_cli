"""workspace.toml 读写 + schema 校验"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from llmw import WORKSPACE_SPEC_VERSION, WIKI_SPEC_VERSION
from llmw._compat import toml_loads, toml_dump
from llmw.errors import SchemaVersionUnsupported
from llmw.fsutil import atomic_write, now_iso8601

SCHEMA_VERSION_SUPPORTED = 1


@dataclass
class WikiEntry:
    """workspace.toml [wikis.<name>] 表项"""

    name: str
    path: str
    created_at: str


@dataclass
class WorkspaceToml:
    """workspace.toml 解析结果 (Phase 1 schema)"""

    schema_version: int
    created_at: str
    templates_version: str = "1"
    default_model: Optional[str] = None
    enter_cli: Optional[str] = None  # "claude" (默认) | "qodercli" | "opencode"
    wikis: Dict[str, WikiEntry] = field(default_factory=dict)

    @property
    def toml_path(self) -> Path:
        # 注意: 实例化时由 load() 注入；这里仅占位
        raise NotImplementedError("use load()/save() instead of constructing directly")


def load(workspace_root: Path) -> WorkspaceToml:
    """从 <workspace_root>/workspace.toml 加载并校验"""
    toml_path = workspace_root / "workspace.toml"
    with open(toml_path, "rb") as f:
        raw = toml_loads(f.read().decode("utf-8"))

    sv = raw.get("schema_version")
    if sv != SCHEMA_VERSION_SUPPORTED:
        raise SchemaVersionUnsupported(
            f"workspace.toml schema_version={sv} 不被支持 (当前 CLI 仅支持 v{SCHEMA_VERSION_SUPPORTED})",
            hint="升级 CLI 或手动迁移 schema_version",
        )

    wikis: Dict[str, WikiEntry] = {}
    for name, info in raw.get("wikis", {}).items():
        wikis[name] = WikiEntry(
            name=name,
            path=info["path"],
            created_at=info["created_at"],
        )

    return WorkspaceToml(
        schema_version=sv,
        created_at=raw["created_at"],
        templates_version=raw.get("templates_version", "1"),
        default_model=raw.get("default_model"),
        enter_cli=raw.get("enter_cli"),
        wikis=wikis,
    )


def save(workspace_root: Path, ws: WorkspaceToml) -> None:
    """写回 <workspace_root>/workspace.toml (原子写)"""
    toml_path = workspace_root / "workspace.toml"
    data = {
        "schema_version": ws.schema_version,
        "created_at": ws.created_at,
        "templates_version": ws.templates_version,
    }
    if ws.default_model is not None:
        data["default_model"] = ws.default_model
    if ws.enter_cli is not None and ws.enter_cli != "claude":
        data["enter_cli"] = ws.enter_cli

    if ws.wikis:
        wiki_table = {}
        for name, entry in ws.wikis.items():
            wiki_table[name] = {
                "path": entry.path,
                "created_at": entry.created_at,
            }
        data["wikis"] = wiki_table

    import io

    buf = io.StringIO()
    toml_dump(data, buf)
    atomic_write(toml_path, buf.getvalue())


def create_skeleton(workspace_root: Path) -> WorkspaceToml:
    """init 时调用：生成空 workspace.toml

    templates_version 编码双 spec 版本(spec §14)，供 skill scan 前比对：
    形如 ``workspace_spec=0.2.0; wiki_spec=0.5.0``。
    """
    ws = WorkspaceToml(
        schema_version=SCHEMA_VERSION_SUPPORTED,
        created_at=now_iso8601(),
        templates_version=(
            f"workspace_spec={WORKSPACE_SPEC_VERSION}; wiki_spec={WIKI_SPEC_VERSION}"
        ),
    )
    save(workspace_root, ws)
    return ws
