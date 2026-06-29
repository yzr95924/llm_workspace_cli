"""resolved ModelEntry → <wiki>/.claude/settings.local.json（Local 层 overlay 交付）

设计 §9.5。overlay 不读 registry、不做 resolve——只接收一个已解析好的 ModelEntry，
渲染成 env 块并幂等合并写盘。enter(real) 调 apply()，enter(dry-run) 调 inspect()。

交付走 Claude Code 的 Local 层（<wiki>/.claude/settings.local.json），优先级 > User：
overlay 稳赢，且 user 配置（~/.claude/settings.json）正常加载。取代早期 subprocess
env 注入（优先级最低，会被 user env 块盖掉，曾靠 --setting-sources project,local 排除
user 来规避，代价是丢 user 配置）。
"""

import json
import os
from pathlib import Path
from typing import Optional, Tuple

from llmw.errors import OverlayFileUnparseable
from llmw.fsutil import atomic_write
from llmw.models.store import ModelEntry

# overlay 拥有（可覆盖）的 env key——其余 env key 与所有其他顶层 key 一律保留
_OWNED = ("ANTHROPIC_MODEL", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN")


def render(model: ModelEntry) -> dict:
    """ModelEntry → overlay env 块。

    ANTHROPIC_MODEL 用 model.name（网关模型名，如 MiniMax-M3[1m]），不是 model_id
    slug——网关只认 name。
    """
    return {
        "ANTHROPIC_MODEL": model.name,
        "ANTHROPIC_BASE_URL": model.base_url,
        "ANTHROPIC_AUTH_TOKEN": model.api_key,
    }


def _load_existing(path: Path) -> Optional[dict]:
    """读现有 settings.local.json。不存在 → None；JSON 非法 → OverlayFileUnparseable。

    绝不 clobber 损坏文件：解析失败直接抛，调用方阻断，由用户手动修复。
    """
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise OverlayFileUnparseable(
            f"{path} 不是合法 JSON: {e}",
            hint="手动修复或删除该文件后重试；CLI 不会覆盖损坏文件",
        )


def _is_up_to_date(data: Optional[dict], expected: dict) -> bool:
    """3 个 owned key 是否已全部 == expected（文件已是最新）。"""
    if not data:
        return False
    env = data.get("env") or {}
    return all(env.get(k) == v for k, v in expected.items())


def inspect(wiki_dir: Path, model: ModelEntry) -> Tuple[Path, bool]:
    """dry-run 用：返回 (path, would_write)。不写盘。

    would_write=True 当且仅当文件不存在或 3 个 owned key 不全等于 expected。
    损坏文件（JSON 非法）→ OverlayFileUnparseable（与 apply 一致，绝不 clobber）。
    """
    path = wiki_dir / ".claude" / "settings.local.json"
    expected = render(model)
    data = _load_existing(path)
    return path, not _is_up_to_date(data, expected)


def apply(wiki_dir: Path, model: ModelEntry) -> Path:
    """real enter 用：幂等合并写 + chmod 600。返回写入 path。

    - 只覆盖 3 个 owned key，保留 env 内其他 key + 所有其他顶层 key（如 statusLine）
    - 3 个 owned key 已一致 → 不写、不动 mtime（幂等短路）
    - JSON 非法 → OverlayFileUnparseable，绝不 clobber
    """
    path = wiki_dir / ".claude" / "settings.local.json"
    expected = render(model)

    data = _load_existing(path) or {}
    if _is_up_to_date(data, expected):
        return path  # 幂等短路

    env = dict(data.get("env") or {})
    env.update(expected)
    data["env"] = env

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # NFS 等不支持 chmod，best-effort（同 registry）
    return path
