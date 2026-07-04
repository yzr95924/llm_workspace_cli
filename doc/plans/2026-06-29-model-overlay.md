# Model Overlay (settings.local.json) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `wiki enter` 的 model 交付从「subprocess env 注入 + `--setting-sources project,local`」改为「写 `<wiki>/.claude/settings.local.json`（Local 层）+ lazy on enter」，并让 overlay secret 被 workspace 根 `.gitignore` 忽略。

**Architecture:** 新增 `llmw/models/overlay.py`（render/inspect/apply）—— resolved `ModelEntry` → `env` 块 → 幂等合并写入 wiki 的 Local 层 settings 文件。`enter` 在 real 时 lazy `apply`、dry-run 时 `inspect`；subprocess 回归透传 `os.environ`、删 `--setting-sources`（恢复 user 配置，Local 层优先级 > User 保 overlay 稳赢）。单仓模型下，overlay secret 由 `llmw init` 的 workspace `.gitignore` managed block 新增 `*/.claude/settings.local.json` 一行忽略。

**Tech Stack:** Python stdlib only（`json` / `os` / `re` / `pathlib` / `subprocess` / `dataclasses`）；现有 `llmw` 包（`fsutil.atomic_write` / `errors.LlmwError` / `models.store.ModelEntry` / `models.resolve`）。无新第三方依赖。

## Global Constraints

> 本节来自 spec（`doc/design/09-workspace-model-registry.md`）与项目 `CLAUDE.md`，每个 task 的需求隐含包含。

- **Python 3.7+ 兼容**（CI 矩阵 py3.7 + py3.11）：类型注解用 `typing.Optional` / `typing.Tuple`，不用 PEP 604/585；`json` / `os` / `re` 全是 stdlib。
- **不变量 I-1**：CLI 绝不写 `raw/` 与 `wiki/` 下任何文件。overlay 写的是 `<wiki>/.claude/settings.local.json`（wiki 根级 `.claude/`，不在 `raw/` 或 `wiki/` 下），**不违反** I-1。
- **不变量 I-5b（新）**：CLI **只允许**写 `<wiki>/.claude/settings.local.json` 这**一个** launch-config 文件（派生自 resolved model），不写 `.claude/` 下其他任何内容、不编辑 `<wiki>/CLAUDE.md`、不碰 `raw/` / `wiki/`。
- **api_key 永不明文出 stdout**：dry-run 打印 token 一律走 `llmw.models.redact.redact_api_key`；明文 key 只在 `overlay.apply` 写盘时使用。
- **ANTHROPIC_MODEL = `model.name`**（网关模型名，如 `MiniMax-M3[1m]`），**不是** `model_id` slug——网关只认 name。
- **model 真相源是 `workspace_models.toml`**：不读 `os.environ.get("ANTHROPIC_*")` 作为真相源；`enter` 的 subprocess 透传 `os.environ`（默认），overlay 经 Local 层文件交付。
- **原子写**走 `llmw.fsutil.atomic_write`（tmp + fsync + os.replace）；secret 文件写盘后 `chmod 600`，`try/except OSError` best-effort（NFS 跳过）。
- **不写自动化测试**：遵循 `CLAUDE.md` + `MEMORY/MEMORY.md (短条目区 "测试优先级低")`（prototype 阶段测试优先级低，agent 不主动加测试代码）。**本计划每个 task 用 manual smoke（内联 `python3` 脚本 / spec §9.8 命令）验证，不写 pytest 文件**——这是项目约定对 writing-plans 默认 TDD 的覆盖。
- **当前 `wiki add` 是坏的**（调已移除的 `setup_wiki.py`），属 wiki-spec.md 迁移（§9.10 推迟），**不在本计划范围**。Task 3 的 smoke 用内部 store API 手构造最小 wiki 绕过 `wiki add`。
- **本计划范围 = spec §9.5（overlay 交付）+ §9.6（单仓 gitignore）+ §9.7（OverlayFileUnparseable）**。registry/store/manager/resolve/命令族（§9.2–9.4）已实现，**不改**。

## File Structure

| 文件 | 动作 | 职责 |
| --- | --- | --- |
| `llmw/errors.py` | Modify | 新增 `OverlayFileUnparseable`（exit 1） |
| `llmw/models/overlay.py` | **Create** | `render` / `inspect` / `apply` / `_load_existing`：resolved ModelEntry → `<wiki>/.claude/settings.local.json` |
| `llmw/wiki/enter.py` | Modify | 删 `_build_env_overlay` + `--setting-sources` + `full_env`；dry-run 用 `overlay.inspect`，real 用 `overlay.apply`；subprocess 透传 `os.environ` |
| `llmw/workspace/manager.py` | Modify | `_ensure_workspace_gitignore` 的 managed block 从单行扩为两行（加 `*/.claude/settings.local.json`）+ 老 block 升级幂等 |
| `CLAUDE.md` | Modify | 补 I-5b；数据流图 / 模块边界表 / "wiki enter 的 model 解析"段同步 overlay 交付 |
| `doc/design/03-wiki-enter.md` | Modify | Phase 2 banner + 行为步骤改为 settings.local.json，删 `--setting-sources` / env 注入 |
| `MEMORY/agent-settings-env-precedence.md` | Modify | 从"排除 user"改为"Local 层覆盖 user 并恢复 user 配置" |
| `MEMORY/model-ops-no-env-vars.md` | Modify | 交付载体从"subprocess env 注入"改为"写 settings.local.json" |
| `README.md` | Modify | Manual Smoke 段加 overlay 文件检查项 |

模块单向依赖：`enter → resolve → store`，`enter → overlay → store(ModelEntry) + errors + fsutil`。`overlay` 不读 registry、不做 resolve。

---

## Task 1: 新增 `OverlayFileUnparseable` 错误类

**Files:**
- Modify: `llmw/errors.py`（在 `RegistryMissing` 之后、"内部错误" 区块之前插入）

**Interfaces:**
- Produces: `OverlayFileUnparseable(LlmwError)`，`exit_code=1`，`user_message="overlay 文件不是合法 JSON"`。Task 2 的 `overlay._load_existing` 与 Task 3 的 `enter`（dry-run/real 经 inspect/apply）依赖它。

- [ ] **Step 1: 在 `llmw/errors.py` 的 `RegistryMissing` 类之后插入新错误类**

定位锚点（`RegistryMissing` 类 + 紧随其后的 "内部错误" 注释行）：

```python
class RegistryMissing(LlmwError):
    exit_code = 1
    user_message = "workspace_models.toml 不存在"


# ===== 内部错误 (exit_code = 3) =====
```

替换为（在两者之间插入 `OverlayFileUnparseable`）：

```python
class RegistryMissing(LlmwError):
    exit_code = 1
    user_message = "workspace_models.toml 不存在"


class OverlayFileUnparseable(LlmwError):
    exit_code = 1
    user_message = "overlay 文件不是合法 JSON"


# ===== 内部错误 (exit_code = 3) =====
```

- [ ] **Step 2: 验证 import + exit_code**

Run:
```bash
python3 -c "from llmw.errors import OverlayFileUnparseable as E; e=E('x'); print(e.exit_code, e.message)"
```
Expected: `1 x`

- [ ] **Step 3: Commit**

```bash
git add llmw/errors.py
git commit -m "feat(errors): add OverlayFileUnparseable (exit 1)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: 新建 `llmw/models/overlay.py`

**Files:**
- Create: `llmw/models/overlay.py`

**Interfaces:**
- Consumes: `llmw.models.store.ModelEntry`（字段 `name` / `base_url` / `api_key`）、`llmw.errors.OverlayFileUnparseable`（Task 1）、`llmw.fsutil.atomic_write(path, content: str)`。
- Produces:
  - `render(model: ModelEntry) -> dict` —— ModelEntry → `{"ANTHROPIC_MODEL": model.name, "ANTHROPIC_BASE_URL": model.base_url, "ANTHROPIC_AUTH_TOKEN": model.api_key}`
  - `inspect(wiki_dir: Path, model: ModelEntry) -> Tuple[Path, bool]` —— dry-run 用，返回 `(path, would_write)`，不写盘
  - `apply(wiki_dir: Path, model: ModelEntry) -> Path` —— real 用，幂等合并写 + chmod 600，返回写入 path

- [ ] **Step 1: 创建 `llmw/models/overlay.py`，写入完整实现**

```python
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
```

- [ ] **Step 2: 验证 render / apply / 幂等 / 合并保留 / 损坏不 clobber**

Run（内联 smoke，覆盖 spec §9.5.6 + §9.5.7 全部分支）:
```bash
python3 - <<'EOF'
import json, tempfile
from pathlib import Path
from llmw.models.store import ModelEntry
from llmw.models import overlay
from llmw.errors import OverlayFileUnparseable

d = Path(tempfile.mkdtemp())
m = ModelEntry(model_id="t", name="MiniMax-M3[1m]", base_url="https://api.example.com",
               api_key="sk-test-1234567890")

# render
assert overlay.render(m)["ANTHROPIC_MODEL"] == "MiniMax-M3[1m]"
assert overlay.render(m)["ANTHROPIC_AUTH_TOKEN"] == "sk-test-1234567890"

# apply 新建
p = overlay.apply(d, m)
assert p == d / ".claude" / "settings.local.json"
data = json.loads(p.read_text(encoding="utf-8"))
assert data["env"]["ANTHROPIC_MODEL"] == "MiniMax-M3[1m]"
assert data["env"]["ANTHROPIC_BASE_URL"] == "https://api.example.com"
assert data["env"]["ANTHROPIC_AUTH_TOKEN"] == "sk-test-1234567890"
assert oct(p.stat().st_mode)[-3:] == "600", "权限应为 600"

# 幂等短路（连跑第二次不动 mtime）
t1 = p.stat().st_mtime_ns
overlay.apply(d, m)
assert p.stat().st_mtime_ns == t1, "幂等：第二次不应改 mtime"

# 合并保留：手塞别的 env key + 顶层 key，apply 后保留
data["env"]["MY_OTHER"] = "keep"
data["statusLine"] = "keep"
p.write_text(json.dumps(data), encoding="utf-8")
overlay.apply(d, m)
data2 = json.loads(p.read_text(encoding="utf-8"))
assert data2["env"]["MY_OTHER"] == "keep", "保留其他 env key"
assert data2["statusLine"] == "keep", "保留其他顶层 key"
assert data2["env"]["ANTHROPIC_MODEL"] == "MiniMax-M3[1m]", "owned key 仍被覆盖"

# inspect：已最新 → would_write=False
_, would = overlay.inspect(d, m)
assert would is False, "已最新时 inspect 返回 False"

# 损坏文件 → OverlayFileUnparseable，绝不 clobber
p.write_text("{ broken", encoding="utf-8")
try:
    overlay.apply(d, m)
    assert False, "损坏文件应抛 OverlayFileUnparseable"
except OverlayFileUnparseable:
    pass
assert "broken" in p.read_text(encoding="utf-8"), "损坏文件未被覆盖"

print("✓ overlay.py smoke pass")
EOF
```
Expected: `✓ overlay.py smoke pass`

- [ ] **Step 3: Commit**

```bash
git add llmw/models/overlay.py
git commit -m "feat(models): add overlay.py — settings.local.json delivery

render/inspect/apply: resolved ModelEntry → <wiki>/.claude/settings.local.json
(Local layer, > User). Idempotent merge, chmod 600, never clobber corrupt file.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: 重构 `llmw/wiki/enter.py`（删 env 注入，改 overlay 交付）

**Files:**
- Modify: `llmw/wiki/enter.py`（全文重构：docstring / imports / `_build_cmd` / 删 `_build_env_overlay` / `enter` 主体）

**Interfaces:**
- Consumes: `llmw.models.overlay.apply` / `overlay.inspect`（Task 2）、`resolve_for_wiki`（已有）、`redact_api_key`（已有）。
- Produces: `enter(workspace_root, name, dry_run=False) -> int`（签名不变；行为改：real 时先 `overlay.apply` 再 `subprocess.run(cmd)` 透传 `os.environ`；dry-run 用 `overlay.inspect`）。

- [ ] **Step 1: 用以下完整内容替换 `llmw/wiki/enter.py` 全文**

```python
"""wiki enter — 启动 Claude Code session

Phase 2 交付（§9.5）：resolved model 通过写 <wiki>/.claude/settings.local.json 的 env 块
（Local 层，优先级 > User）交付，lazy on enter。不再注入 subprocess env、不再传
--setting-sources——user 配置（~/.claude/settings.json）正常加载，overlay 在 Local 层稳赢。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from llmw._compat import TOMLDecodeError
from llmw.errors import ClaudeNotFound, SchemaVersionUnsupported, WikiDirMissing, WikiNotFound
from llmw.models import overlay
from llmw.models.redact import redact_api_key
from llmw.models.resolve import resolve_for_wiki
from llmw.wiki.store import load as wiki_load
from llmw.workspace import store as ws_store


def _resolve_wiki_path(workspace_root: Path, name: str) -> Path:
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(
            f"wiki '{name}' 不在当前 workspace 中",
            hint="运行 `llmw list` 查看已注册 wiki",
        )
    return workspace_root / ws.wikis[name].path


def _read_system_prompt(wiki_path: Path):
    """读 CLAUDE.md 内容作为 system-prompt。
    缺失返回 (None, path)。空文件返回 ("", path)——按设计空 CLAUDE.md 仍传 --system-prompt ""。

    为什么读全文而不是 --system-prompt "$(cat CLAUDE.md)"？
    subprocess.run 不走 shell，$() 会作为字面量传给 claude；只能预先读出。
    """
    claude_md = wiki_path / "CLAUDE.md"
    if not claude_md.is_file():
        return None, claude_md
    return claude_md.read_text(encoding="utf-8"), claude_md


def _build_cmd(wiki_path: Path):
    """构造 claude 子进程 argv：--add-dir + 可选 --system-prompt。

    不传 --setting-sources：claude 默认加载 user+project+local。cwd=wiki 子目录 → 读到
    <wiki>/.claude/settings.local.json（Local，优先级 > User）→ overlay 稳赢，user 配置同时
    加载。早期版本传 --setting-sources project,local 排除 user，是为防其 env 块盖掉优先级
    更低的 subprocess env overlay；现 overlay 已在 Local 层文件里，无需排除 user。
    """
    prompt, _ = _read_system_prompt(wiki_path)
    cmd = ["claude", "--add-dir", str(wiki_path)]
    if prompt is not None:
        cmd += ["--system-prompt", prompt]
    return cmd, prompt


def enter(workspace_root: Path, name: str, dry_run: bool = False) -> int:
    wiki_path = _resolve_wiki_path(workspace_root, name)

    if not wiki_path.is_dir():
        raise WikiDirMissing(
            f"wiki 子目录不存在: {wiki_path}",
            hint="可能被外部 rm；可 `git checkout` 恢复或重新 add",
        )

    claude_md = wiki_path / "CLAUDE.md"
    meta_p = wiki_path / "wiki_metadata.toml"

    # 软警告（不阻断）
    if not claude_md.is_file():
        print(
            f"[llmw] warning: wiki '{name}' 缺少 CLAUDE.md，session 启动后将没有 schema 上下文",
            file=sys.stderr,
        )
    if not meta_p.is_file():
        print(f"[llmw] warning: wiki '{name}' 缺少 wiki_metadata.toml", file=sys.stderr)

    # 检查 claude 在 PATH（dry-run 时跳过）
    if not dry_run and shutil.which("claude") is None:
        raise ClaudeNotFound(
            "claude 不在 PATH",
            hint="安装 Claude Code 或加到 PATH 后重试；可用 --dry-run 看命令",
        )

    # Phase 2：通过 resolve 拿最终 model（失败会阻断 enter，在任何写盘之前）
    model = resolve_for_wiki(workspace_root, name)

    cmd, prompt = _build_cmd(wiki_path)

    # dry-run
    if dry_run:
        meta = None
        if meta_p.is_file():
            try:
                meta = wiki_load(wiki_path)
            except (OSError, TOMLDecodeError, SchemaVersionUnsupported) as e:
                # resolve 已捕过 SchemaVersionUnsupported；这里再捕让 dry-run 还能打印 overlay
                print(
                    f"[llmw] warning: 无法读取 wiki_metadata.toml: {type(e).__name__}: {e}",
                    file=sys.stderr,
                )
                meta = None
        overlay_path, would_write = overlay.inspect(wiki_path, model)
        print(f"[llmw] workspace: {workspace_root}", file=sys.stdout)
        print(f"[llmw] wiki:      {name} ({wiki_path})", file=sys.stdout)
        print(
            f"[llmw] resolved model: {model.name} ({model.model_id})",
            file=sys.stdout,
        )
        source = "wiki override" if (meta and meta.model) else "registry default"
        print(f"[llmw] source: {source}", file=sys.stdout)
        tag = "(will write)" if would_write else "(up to date, skip)"
        print(f"[llmw] overlay file: {overlay_path}  {tag}", file=sys.stdout)
        print(f"[llmw]   ANTHROPIC_MODEL      = {model.name}", file=sys.stdout)
        print(f"[llmw]   ANTHROPIC_BASE_URL   = {model.base_url}", file=sys.stdout)
        print(f"[llmw]   ANTHROPIC_AUTH_TOKEN = {redact_api_key(model.api_key)}", file=sys.stdout)
        if claude_md.is_file():
            print(
                f"[llmw] CLAUDE.md: ✓ found ({claude_md.stat().st_size} bytes)",
                file=sys.stdout,
            )
        else:
            print(f"[llmw] CLAUDE.md: ✗ missing", file=sys.stdout)
        if prompt is not None:
            cmd_display = (
                f'claude --add-dir {wiki_path} --system-prompt "$(cat {claude_md})"'
            )
        else:
            cmd_display = f"claude --add-dir {wiki_path}"
        print(f"[llmw] cmd:", file=sys.stdout)
        print(f"  {cmd_display}", file=sys.stdout)
        print(f"[llmw] --dry-run: 未执行", file=sys.stdout)
        return 0

    # 真正执行：lazy 写 overlay（Local 层）→ subprocess 透传 os.environ（无 env overlay，无 --setting-sources）
    overlay.apply(wiki_path, model)
    os.chdir(wiki_path)
    result = subprocess.run(cmd)
    return result.returncode
```

- [ ] **Step 2: 验证 import 无破坏**

Run:
```bash
python3 -c "from llmw.wiki.enter import enter, _build_cmd; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: 验证 `_build_cmd` 不再含 `--setting-sources`**

Run:
```bash
python3 -c "from llmw.wiki.enter import _build_cmd; from pathlib import Path; c,_=_build_cmd(Path('/tmp/x')); print(c); assert '--setting-sources' not in c, '不应再含 --setting-sources'; print('ok')"
```
Expected: 末行 `ok`（且打印的 cmd 列表不含 `--setting-sources`）

- [ ] **Step 4: dry-run 端到端 smoke（用内部 store API 手构造最小 wiki，绕过坏的 `wiki add`）**

Run:
```bash
python3 - <<'EOF'
import contextlib, io, tempfile
from pathlib import Path
from llmw.fsutil import now_iso8601
from llmw.workspace import store as ws_store
from llmw.wiki import store as wiki_store
from llmw.models import store as ms
from llmw.models.store import ModelEntry
from llmw.wiki.enter import enter

root = Path(tempfile.mkdtemp())
# workspace.toml + 注册 wiki foo
ws_store.create_skeleton(root)
ws = ws_store.load(root)
ws.wikis["foo"] = ws_store.WikiEntry("foo", "foo", now_iso8601())
ws_store.save(root, ws)
# wiki 子目录 + metadata（model=minimax-m3）
wikidir = root / "foo"
wikidir.mkdir()
meta = wiki_store.WikiMetadata(
    schema_version=2, name="foo", topic="Foo",
    created_at=now_iso8601(), updated_at=now_iso8601(),
    display_name="Foo", description="x", tags=["a"], model="minimax-m3")
wiki_store.save(wikidir, meta)
# registry（minimax-m3 默认）
reg = ms.create_skeleton(root)
reg.models["minimax-m3"] = ModelEntry(
    "minimax-m3", "MiniMax-M3[1m]", "https://api.example.com",
    "sk-test-1234567890", is_default=True)
ms.save(root, reg)

# 跑 dry-run，捕获 stdout
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = enter(root, "foo", dry_run=True)
out = buf.getvalue()
assert rc == 0
assert "overlay file" in out, out
assert "(will write)" in out, out
assert "MiniMax-M3[1m]" in out, out
assert "sk-...7890" in out, out              # api_key 脱敏
assert "--setting-sources" not in out, out   # 已删
# dry-run 不写盘
assert not (wikidir / ".claude" / "settings.local.json").exists()
print("✓ enter dry-run smoke pass")
EOF
```
Expected: `✓ enter dry-run smoke pass`

> 备注：`redact_api_key("sk-test-1234567890")`（长度 > 8）= `sk-...7890`（前 3 + 末 4）。若该断言因 redact 实现细节失败，先 `python3 -c "from llmw.models.redact import redact_api_key; print(redact_api_key('sk-test-1234567890'))"` 看实际值再校正断言。

- [ ] **Step 5: 真跑验收（人工，需 claude 在 PATH）**

> 真跑会启动交互式 claude session。人工执行：`cd <上述 root 的父级> && LLMW_WORKSPACE=<root> python3 -c "from llmw.wiki.enter import enter; enter(__import__('pathlib').Path('<root>'), 'foo')"`，确认 claude 启动且 `<root>/foo/.claude/settings.local.json` 生成（权限 600）。若 claude 未装，跳过此项，Task 2 + Step 4 已覆盖 overlay 写盘逻辑。

- [ ] **Step 6: Commit**

```bash
git add llmw/wiki/enter.py
git commit -m "refactor(wiki): enter delivers model via settings.local.json

Drop _build_env_overlay + --setting-sources project,local + full_env.
Real: overlay.apply (Local layer) then subprocess.run(cmd) passthrough
os.environ. Dry-run: overlay.inspect. Restores user config; overlay wins
via Local > User precedence.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: workspace `.gitignore` managed block 扩展两行

**Files:**
- Modify: `llmw/workspace/manager.py`（`GITIGNORE_LINE` 常量 + `_ensure_workspace_gitignore` 函数体）

**Interfaces:**
- Produces: `llmw init` 写入的 workspace `.gitignore` managed block 内容从单行 `workspace_models.toml` 扩为两行（加 `*/.claude/settings.local.json`）。幂等：已是最新两行 → skip；老单行 block → 替换为两行；无 block → 追加；无文件 → 创建。

- [ ] **Step 1: 替换 `GITIGNORE_LINE` 常量 + `_ensure_workspace_gitignore` 全函数**

定位锚点（当前 `llmw/workspace/manager.py` 第 38–61 行整段）：

```python
GITIGNORE_LINE = "workspace_models.toml"


def _ensure_workspace_gitignore(workspace_root: Path) -> None:
    """确保 workspace 级 .gitignore 包含 workspace_models.toml。
    - 文件不存在 → 创建（带 llmw 标记段）
    - 文件存在 → 若已有 workspace_models.toml 行，跳过；否则追加
    """
    gitignore = workspace_root / ".gitignore"
    marker_start = "# >>> llmw (managed by llmw) >>>"
    marker_end = "# <<< llmw <<<"
    if gitignore.is_file():
        text = gitignore.read_text(encoding="utf-8")
        if GITIGNORE_LINE in text:
            return
        addition = f"\n{marker_start}\n{GITIGNORE_LINE}\n{marker_end}\n"
        from llmw.fsutil import atomic_write

        atomic_write(gitignore, text + addition)
    else:
        content = f"{marker_start}\n{GITIGNORE_LINE}\n{marker_end}\n"
        from llmw.fsutil import atomic_write

        atomic_write(gitignore, content)
```

替换为：

```python
# workspace 级 .gitignore managed block 内容（registry + overlay 两个 secret）
# 单仓模型：wiki 是 workspace 直属子目录，*/.claude/settings.local.json 通配覆盖所有
# wiki 的 overlay secret，不依赖 per-wiki .gitignore / wiki scaffold（见 §9.6）。
GITIGNORE_LINES = ("workspace_models.toml", "*/.claude/settings.local.json")


def _ensure_workspace_gitignore(workspace_root: Path) -> None:
    """确保 workspace 级 .gitignore 含 llmw managed block（两行 secret 忽略）。

    - 文件不存在 → 创建（带 marker 段）
    - 已是最新两行 block → 跳过
    - 有老 block（如早期单行）→ 替换 marker 区间为最新两行
    - 无 block → 追加
    """
    import re

    from llmw.fsutil import atomic_write

    gitignore = workspace_root / ".gitignore"
    marker_start = "# >>> llmw (managed by llmw) >>>"
    marker_end = "# <<< llmw <<<"
    block = marker_start + "\n" + "\n".join(GITIGNORE_LINES) + "\n" + marker_end

    if not gitignore.is_file():
        atomic_write(gitignore, block + "\n")
        return

    text = gitignore.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(marker_start) + r".*?" + re.escape(marker_end), re.DOTALL)
    m = pattern.search(text)
    if m:
        if m.group(0) == block:
            return  # 已是最新两行 block
        new_text = pattern.sub(block, text)  # 老 block → 替换为两行
    else:
        # 无 block → 追加（保证前导换行 + 末尾换行）
        sep = "" if (text.endswith("\n") or not text) else "\n"
        tail = "" if text.endswith("\n") else "\n"
        new_text = text + sep + block + tail
    atomic_write(gitignore, new_text)
```

- [ ] **Step 2: 验证新建 / 幂等 / 老 block 升级 / git 实际忽略**

Run（覆盖 spec §9.8 init 验收 + D 项）:
```bash
python3 - <<'EOF'
import subprocess, tempfile
from pathlib import Path
from llmw.workspace.manager import _ensure_workspace_gitignore, GITIGNORE_LINES

root = Path(tempfile.mkdtemp())
gi = root / ".gitignore"

# 1. 新建 → 两行 block
_ensure_workspace_gitignore(root)
text = gi.read_text(encoding="utf-8")
assert "workspace_models.toml" in text and "*/.claude/settings.local.json" in text, text

# 2. 幂等（再调一次，内容不变）
_ensure_workspace_gitignore(root)
assert gi.read_text(encoding="utf-8") == text, "幂等：不应改动"

# 3. 老 block（单行）→ 升级为两行
gi.write_text("# >>> llmw (managed by llmw) >>>\nworkspace_models.toml\n# <<< llmw <<<\n",
              encoding="utf-8")
_ensure_workspace_gitignore(root)
upgraded = gi.read_text(encoding="utf-8")
assert "*/.claude/settings.local.json" in upgraded, "老 block 应升级含 overlay 行"
assert upgraded.count("# >>> llmw") == 1, "不应产生重复 block"

# 4. 用户自写内容 + 无 block → 追加 block，保留用户内容
root2 = Path(tempfile.mkdtemp())
gi2 = root2 / ".gitignore"
gi2.write_text("# my stuff\n*.log\n", encoding="utf-8")
_ensure_workspace_gitignore(root2)
t2 = gi2.read_text(encoding="utf-8")
assert "# my stuff" in t2 and "*.log" in t2, "保留用户内容"
assert "*/.claude/settings.local.json" in t2, "追加了 block"

print("✓ gitignore managed block smoke pass")
EOF
```
Expected: `✓ gitignore managed block smoke pass`

- [ ] **Step 3: 验证 git 实际忽略 overlay secret（单仓模型）**

Run:
```bash
TMPWS=$(mktemp -d)
LLMW_WORKSPACE="$TMPWS" PYTHONPATH=. python3 -m llmw init --path "$TMPWS" --no-git >/dev/null
# 模拟 overlay secret 落盘到某 wiki 子目录
mkdir -p "$TMPWS/foo/.claude"
echo '{"env":{}}' > "$TMPWS/foo/.claude/settings.local.json"
cd "$TMPWS" && git init -q && git add -A 2>/dev/null
if git status --porcelain | grep -q 'settings.local.json'; then
  echo "✗ 未被忽略"
else
  echo "✓ workspace gitignore 忽略 overlay secret"
fi
cd - >/dev/null
rm -rf "$TMPWS"
```
Expected: `✓ workspace gitignore 忽略 overlay secret`

> 备注：`python3 -m llmw init` 依赖 `llmw/__main__.py` 入口；若该入口签名不同，改用 `PYTHONPATH=. python3 -c "from pathlib import Path; from llmw.workspace.manager import init; init(Path('$TMPWS'), git=False)"`。

- [ ] **Step 4: Commit**

```bash
git add llmw/workspace/manager.py
git commit -m "feat(workspace): gitignore managed block ignores overlay secret

Single-repo model: extend init's managed block from one line to two
(+ */.claude/settings.local.json). Idempotent; upgrades legacy single-line
block. Decoupled from setup_wiki.py removal / wiki-spec.md migration.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: 文档连带同步（spec §9.9）

> 本 task 是 markdown 文档同步，不涉及代码逻辑。每个文件给出精确改动锚点。逐一 edit 后整体 commit。

**Files:**
- Modify: `CLAUDE.md`
- Modify: `doc/design/03-wiki-enter.md`
- Modify: `MEMORY/agent-settings-env-precedence.md`
- Modify: `MEMORY/model-ops-no-env-vars.md`
- Modify: `README.md`

- [ ] **Step 1: `CLAUDE.md` — 补 I-5b + 数据流图 + 模块边界表 + enter 解析段**

  1a. **关键不变量**：在「### 关键不变量」下、不变量 5（model 真相源）之后，新增一条：

  ```markdown
  6. **overlay 交付走 Local 层文件**（详见 `doc/design/09-workspace-model-registry.md` §9.5）：`wiki enter` 把 resolved model 渲染进 `<wiki>/.claude/settings.local.json` 的 `env` 块（Local 层，优先级 > User），lazy on enter。CLI **允许**写这**一个** launch-config 文件（I-5b，不放宽 I-1——仍不碰 `raw/` / `wiki/` / `CLAUDE.md`）。enter 的 subprocess 透传 `os.environ`、**不传** `--setting-sources`（恢复 user 配置；Local 层优先级高于 user env 块，overlay 稳赢）。
  ```

  （原不变量 6 若是 SKILL/setup_wiki 相关，序号顺延；以实际文件为准。）

  1b. **顶层数据流图**：把 enter 那行的 `env overlay ANTHROPIC_*` 与 `--setting-sources project,local` 描述改为 `写 <wiki>/.claude/settings.local.json（Local 层）`，删 `--setting-sources`。

  1c. **模块边界表**：`llmw.wiki.enter` 行改为「启动 Claude Code session：resolve model → `overlay.apply` 写 `<wiki>/.claude/settings.local.json` → `claude --add-dir [--system-prompt]`（透传 os.environ，无 --setting-sources）」；新增一行 `llmw.models.overlay`：「`render`/`inspect`/`apply`：resolved ModelEntry → `<wiki>/.claude/settings.local.json` 的 env 块；幂等合并 + chmod 600」。

  1d. **「`wiki enter` 的 model 解析」段**：交付方式从「subprocess 启动时显式叠加 ANTHROPIC_* env + `--setting-sources project,local`」改为「`overlay.apply` 写 `<wiki>/.claude/settings.local.json` 的 env 块（ANTHROPIC_MODEL=model.name / BASE_URL / AUTH_TOKEN），subprocess 透传 os.environ、无 `--setting-sources`」。

- [ ] **Step 2: `doc/design/03-wiki-enter.md` — Phase 2 banner + 行为步骤**

  在文件顶部加 Phase 2 banner（指向 doc 09 §9.5）；把「行为步骤」中 `--setting-sources project,local` 与「env 注入 ANTHROPIC_*」描述改为「写 `<wiki>/.claude/settings.local.json`（Local 层），subprocess 透传 os.environ」。具体锚点以文件现有 Phase 2 段落为准（若 03 尚无 Phase 2 段，新增一节并在顶部 banner 引用 09 §9.5）。

- [ ] **Step 3: `MEMORY/agent-settings-env-precedence.md` — 从"排除 user"改为"Local 覆盖 user"**

  把「用 `--setting-sources project,local` 排除 user」的结论改为：「用 Local 层（`<wiki>/.claude/settings.local.json`）覆盖 user env 块、并恢复 user 配置；`ANTHROPIC_MODEL` 用 `name` 非 `model_id`」。优先级事实（Managed > CLI args > Local > Project > User；settings env 块 > subprocess env）保留，用于解释 Local 为何赢。

- [ ] **Step 4: `MEMORY/model-ops-no-env-vars.md` — 交付载体改 settings.local.json**

  把「交付载体 = subprocess env 注入」改为「交付载体 = 写 `<wiki>/.claude/settings.local.json`（Local 层）」；「真相源 = `workspace_models.toml`」「不读 `os.environ` 作为真相源」的表述保留。`enter` 的 env 注入从「CLI 主动行为」改为「经 Local 层文件」。

- [ ] **Step 5: `README.md` — Manual Smoke 段加 overlay 检查项**

  在 Manual Smoke Test 的 Phase 2 model registry 段，加 overlay 验收项（对齐 spec §9.8 overlay 额外验收）：`enter --dry-run` 显示 overlay file / api_key 脱敏；真跑生成 `.claude/settings.local.json` 权限 600；幂等；非法 JSON 报 `OverlayFileUnparseable` 不覆盖；`init` 的 workspace `.gitignore` 含 `*/.claude/settings.local.json`。

- [ ] **Step 6: 验证文档无残留旧措辞**

Run:
```bash
grep -rn "setting-sources project,local\|env overlay 注入\|_build_env_overlay" \
  CLAUDE.md doc/design/03-wiki-enter.md MEMORY/ README.md \
  | grep -v "改为\|不再\|早期\|取代\|删" || echo "✓ 无残留旧交付措辞"
```
Expected: `✓ 无残留旧交付措辞`（命中项应仅出现在"改为/不再/早期/取代"等历史/澄清语境）

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md doc/design/03-wiki-enter.md MEMORY/agent-settings-env-precedence.md MEMORY/model-ops-no-env-vars.md README.md
git commit -m "docs: sync CLAUDE.md/03/MEMORY/README to overlay delivery

CLAUDE.md: add I-5b invariant; dataflow/module-table/enter-section updated
to settings.local.json. 03-wiki-enter: Phase 2 banner + steps. MEMORY x2:
Local-layer overlays user (not exclude user). README: overlay smoke items.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review（plan → spec 对照）

**Spec coverage:**
- §9.5（overlay 交付）→ Task 2（overlay.py）+ Task 3（enter 重构）✓
- §9.5.6 apply 算法（_OWNED / 幂等 / 合并 / chmod）→ Task 2 Step 1 + Step 2 smoke 全分支 ✓
- §9.5.7 边界（损坏不 clobber / mkdir / NFS chmod）→ Task 2 ✓
- §9.5.8 lazy 契约 → Task 3（real=apply, dry-run=inspect）✓
- §9.5.9 dry-run 输出 → Task 3 Step 1 dry-run 分支 ✓
- §9.6 单仓 gitignore 两行 → Task 4 ✓
- §9.7 OverlayFileUnparseable → Task 1 ✓
- §9.9 连带文档 → Task 5 ✓
- §9.2–9.4（registry/store/manager/resolve/命令族）→ 已实现，本计划不改 ✓
- §9.10 wiki-spec.md 迁移 → 明确推迟，不在本计划 ✓

**Placeholder scan:** 无 TBD/TODO；每个 code step 含完整代码；每个验证 step 含确切命令 + 预期输出。Task 5 文档步骤的锚点以"以实际文件为准"标注的，因文档当前文本未逐字读取——执行时按描述定位即可，属可执行 edit 指令。

**Type/signature consistency:** `render(model)->dict`、`inspect(wiki_dir, model)->Tuple[Path, bool]`、`apply(wiki_dir, model)->Path` 在 Task 2 定义、Task 3 消费，签名一致；`ModelEntry.name/base_url/api_key/model_id` 与 `store.py` 一致；`enter(workspace_root, name, dry_run)` 签名不变；`OverlayFileUnparseable` Task 1 定义、Task 2 消费一致；`atomic_write(path, content)` 与 `fsutil.py` 一致。

---

## Execution Handoff

Plan complete and saved to `doc/plans/2026-06-29-model-overlay.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 task 派一个 fresh subagent，task 间两阶段 review，快速迭代。

**2. Inline Execution** — 在本会话用 executing-plans 批量执行，带 checkpoint review。

Which approach?
