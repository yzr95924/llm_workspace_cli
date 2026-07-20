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

**limit = {context: 1M, output: 128K}**（`_CONTEXT_WINDOW` / `_MAX_OUTPUT`，习惯级常量，
非用户可配）：自定义 provider 不会被 models.dev 收录，opencode 无从得知模型限额，必须
显式声明才能管理上下文余量。**context 与 output 必须成对**——opencode schema 校验要求
limit 块两键齐全，缺 output 直接拒载整个配置（2026-07-20 实测：Missing key
provider.llmw.models.<name>.limit.output）。值对齐 opencode 内嵌 models.dev 数据的
MiniMax-M3（context 1e6 / output 131072）；需按模型区分时升级为 registry 字段。

**models key 剥 `[...]` 后缀**（`_gateway_model_id`）：`[1m]` 是 Claude Code 侧的 1M
context 命名约定，opencode/AI SDK 直连网关时不能照发——2026-07-20 四网关实测：
qwen / glm 400 拒带后缀名；kimi 在真实 max_tokens（32000）下 401 拒
（`other:k3[1m]`，报文自承须 `k3`；max_tokens=1 的小探针反而 200，易误诊）；
minimax 两种都收。剥后缀后四网关全 200。展示名 "name" 保留 model.name（TUI 与
registry 命名一致）；context 知识已由 limit.context 显式提供，不依赖名字后缀。
claude 路径不受影响（overlay.py 仍写原 name，k3[1m] 在 Claude Code 实测可用）。

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
# 习惯级常量（非用户可配）：自定义 provider 不在 models.dev，须显式声明限额；
# context/output 须成对（opencode schema 强制，缺 output 拒载配置）；
# 值对齐 opencode 内嵌 models.dev 的 MiniMax-M3（context 1e6 / output 131072）
_CONTEXT_WINDOW = 1_000_000
_MAX_OUTPUT = 131_072


def _gateway_model_id(name: str) -> str:
    """model.name → 线上发送的 model id：剥掉 `[...]` 后缀（k3[1m] → k3）。

    `[1m]` 是 Claude Code 侧的 1M context 命名约定；opencode/AI SDK 直连网关
    时各网关对带后缀名容忍度不一（2026-07-20 四网关实测，详见模块 docstring），
    剥后缀后全放行。opencode 的 context 知识由 limit.context 显式提供。
    """
    return name.split("[", 1)[0]


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

    models map 的 key（= 线上发送的 model id）用 `_gateway_model_id` 剥掉 `[...]`
    后缀的名字（如 k3），不是 model_id slug；展示名 "name" 保留 model.name 原样
    （如 k3[1m]，TUI 与 registry 命名一致）。baseURL 走 _ai_sdk_base_url 规范化
    （Claude Code 约定 → AI SDK 约定）。
    """
    model_id = _gateway_model_id(model.name)
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
                    model_id: {
                        "name": model.name,
                        "limit": {"context": _CONTEXT_WINDOW, "output": _MAX_OUTPUT},
                    }
                },
            }
        },
        "model": f"{_PROVIDER_ID}/{model_id}",
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
