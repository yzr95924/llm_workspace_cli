"""resolved ModelEntry → <wiki>/opencode.json（opencode 项目级 overlay 交付）

与 overlay.py（claude 路径）平行：opencode 不读 .claude/settings.local.json，其项目级
配置是 <wiki>/opencode.json（opencode 官方文档：项目级 > OPENCODE_CONFIG > 全局
~/.config/opencode，项目级稳赢）。enter(real) 调 apply()，enter(dry-run) 调 inspect()。

owned key（CLI 拥有，每次 enter 幂等对齐）：

- ``provider.llmw``  整对象（npm / options.baseURL / options.apiKey / models）
- ``model``          顶层默认模型 ``llmw/<model.name>``

其余顶层 key（agent / mcp / permission / instructions ...）与其他 provider 一律保留。
apiKey 明文落盘 + chmod 600，由 workspace .gitignore managed block 的
``**/opencode.json`` 行排除出 git（与 .claude/settings.local.json 同一安全模型）。

**无 habit template**：那是 Claude-Code-specific 的 CLAUDE_CODE_* env key（见
overlay.py:_HABIT_TEMPLATE），opencode 无对应机制，不写入。

**npm 包 = @ai-sdk/anthropic**：registry 的 base_url 与 claude 路径 ANTHROPIC_BASE_URL
同源——网关说 Anthropic 协议（/v1/messages）。若网关改走 OpenAI 协议，把 _NPM_PACKAGE
一行常量换成 @ai-sdk/openai-compatible。

**limit.context = 1M**（`_CONTEXT_WINDOW`，习惯级常量，非用户可配）：自定义 provider
不会被 models.dev 收录，opencode 无从得知 context window，必须显式声明才能管理上下文
余量。只设 context 不设 output——output 缺省时 opencode 不下发 max_tokens 上限、走
服务端默认；将来需要再加。若需按模型区分 context window，升级为 registry 字段。

**baseURL 需要 +/v1 规范化**（`_ai_sdk_base_url`，2026-07-19 对 MiniMax 网关实测）：
registry 存的是 Claude Code 约定——请求 URL = ``{base_url}/v1/messages``（Claude Code
自己拼 /v1）；AI SDK @ai-sdk/anthropic 的约定是请求 URL = ``{baseURL}/messages``。
两者相差一个 /v1 段，直填 registry 原值会 404（已实测复现）。render 时对不以 /v1
结尾的 base_url 追加 /v1；已带 /v1 的原样保留。网关协议、认证（x-api-key）、
MiniMax-M3[1m] 推理均已对真实 gateway 端到端验证通过。

**只写严格 JSON**：opencode 自身支持 JSONC，但 llmw 用 json 模块读写——用户手写过带
注释的 opencode.json 会在 _load_existing 抛 OverlayFileUnparseable，绝不 clobber。
"""

import json
import os
from pathlib import Path
from typing import Optional, Tuple

from llmw.errors import OverlayFileUnparseable
from llmw.fsutil import atomic_write
from llmw.models.store import ModelEntry

# provider id / npm 包 / $schema：代码内常量（非用户可配），增删改一律改这里
_PROVIDER_ID = "llmw"
_NPM_PACKAGE = (
    "@ai-sdk/anthropic"  # 网关 = Anthropic 协议（与 ANTHROPIC_BASE_URL 同源）
)
_SCHEMA_URL = "https://opencode.ai/config.json"
# 习惯级常量（非用户可配）：自定义 provider 不在 models.dev，须显式声明 context window
_CONTEXT_WINDOW = 1_000_000


def _ai_sdk_base_url(base_url: str) -> str:
    """registry base_url（Claude Code 约定）→ AI SDK baseURL。

    Claude Code 请求 {base_url}/v1/messages；AI SDK @ai-sdk/anthropic 请求
    {baseURL}/messages。registry 存前者（与 claude 路径 ANTHROPIC_BASE_URL 同源），
    渲染给 AI SDK 时必须补 /v1 段，否则 404（MiniMax 网关实测复现）。
    已是 /v1 结尾则原样保留（幂等，不双重追加）。
    """
    b = base_url.rstrip("/")
    return b if b.endswith("/v1") else b + "/v1"


def render(model: ModelEntry) -> dict:
    """ModelEntry → owned 片段：provider.llmw 整对象 + 顶层 model key。

    models map 的 key 用 model.name（网关模型名，如 MiniMax-M3[1m]），不是 model_id
    slug——与 claude 路径 ANTHROPIC_MODEL 同源，网关只认 name。
    baseURL 走 _ai_sdk_base_url 规范化（Claude Code 约定 → AI SDK 约定）。
    """
    return {
        "provider": {
            _PROVIDER_ID: {
                "npm": _NPM_PACKAGE,
                "name": "llmw registry",
                "options": {
                    "baseURL": _ai_sdk_base_url(model.base_url),
                    "apiKey": model.api_key,
                },
                "models": {
                    model.name: {
                        "name": model.name,
                        "limit": {"context": _CONTEXT_WINDOW},
                    }
                },
            }
        },
        "model": f"{_PROVIDER_ID}/{model.name}",
    }


def _load_existing(path: Path) -> Optional[dict]:
    """读现有 opencode.json。不存在 → None；JSON 非法 → OverlayFileUnparseable。

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
            hint="手动修复或删除该文件后重试；CLI 不会覆盖损坏文件（注意 llmw 只读写严格 JSON，不支持 JSONC 注释）",
        )


def _is_up_to_date(data: Optional[dict], expected: dict) -> bool:
    """owned 部分（provider.llmw 整对象 + 顶层 model）是否已全部 == expected。"""
    if not data:
        return False
    provider = data.get("provider")
    if not isinstance(provider, dict):
        return False
    return (
        provider.get(_PROVIDER_ID) == expected["provider"][_PROVIDER_ID]
        and data.get("model") == expected["model"]
    )


def inspect(wiki_dir: Path, model: ModelEntry) -> Tuple[Path, bool]:
    """dry-run 用：返回 (path, would_write)。不写盘。

    would_write=True 当且仅当文件不存在或 owned 部分 != expected。
    损坏文件（JSON 非法）→ OverlayFileUnparseable（与 apply 一致，绝不 clobber）。
    """
    path = wiki_dir / "opencode.json"
    expected = render(model)
    data = _load_existing(path)
    return path, not _is_up_to_date(data, expected)


def apply(wiki_dir: Path, model: ModelEntry) -> Path:
    """real enter 用：幂等合并写 + chmod 600。返回写入 path。

    - 只覆盖 owned 部分（provider.llmw 整对象 + 顶层 model），保留其他 provider、
      env 外所有其他顶层 key（如 agent / mcp / permission）
    - owned 部分已一致 → 不写、不动 mtime（幂等短路）
    - JSON 非法 → OverlayFileUnparseable，绝不 clobber
    """
    path = wiki_dir / "opencode.json"
    expected = render(model)

    data = _load_existing(path) or {}
    if _is_up_to_date(data, expected):
        return path  # 幂等短路

    data.setdefault("$schema", _SCHEMA_URL)
    provider = data.get("provider")
    if not isinstance(provider, dict):
        provider = {}
    provider[_PROVIDER_ID] = expected["provider"][_PROVIDER_ID]
    data["provider"] = provider
    data["model"] = expected["model"]

    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # NFS 等不支持 chmod，best-effort（同 registry）
    return path
