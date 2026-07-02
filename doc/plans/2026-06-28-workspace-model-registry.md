# Workspace Model Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 workspace 增加 model registry（`workspace_models.toml`），让 wiki 可选择使用注册过的 model，未选则 fallback 到 workspace 默认 model；`wiki enter` 通过 env overlay 启动 claude。

**Architecture:** 新增 `llmw/models/` 包（`store.py` / `manager.py` / `resolve.py`），与 `workspace/`、`wiki/` 平级。`resolve.resolve_for_wiki()` 是 wiki→最终 ModelEntry 的唯一查找入口，被 `enter` / `show` / `list` / wiki config 校验共同消费。registry 文件不入仓（workspace 级 `.gitignore` 由 `llmw init` 写入），文件权限 600。Phase 1 旧契约（不传 model/env）改为 Phase 2 新契约（注入 3 个 ANTHROPIC_* env，其他透传）。

**Tech Stack:** Python 3.11+，标准库（`tomllib` / `tomli` 兼容层、dataclass、`subprocess`、`os.chmod`）；无第三方依赖。

**项目节奏**：按 `MEMORY/MEMORY.md (短条目区 "测试优先级低")`，本阶段不写单元测试，每个 task 的"测试步骤"由 `README.md` 末的 Manual Smoke 统一覆盖；本 plan 的步骤使用「实现 → smoke 跑通 → commit」模式替换 TDD 步骤。

**Spec 来源**：`doc/design/09-workspace-model-registry.md`

---

## File Structure

| 文件 | 职责 |
| --- | --- |
| `llmw/models/__init__.py` | 新建包；导出公共 API |
| `llmw/models/store.py` | `ModelEntry` / `Registry` dataclass；`workspace_models.toml` 的 load/save + 字段校验 + load-time 一致性校验；save 后 `chmod 600` |
| `llmw/models/resolve.py` | `resolve_for_wiki()` 单一入口（wiki→ModelEntry） |
| `llmw/models/manager.py` | `model_add` / `model_list` / `model_show` / `model_set_default` / `model_unset_default` / `model_remove` + TTY 交互 |
| `llmw/errors.py` | 新增 7 个错误类（`ModelNotInRegistry` / `ModelDefaultNotSet` / `ModelDefaultAmbiguous` / `ModelIdConflict` / `ModelIsDefault` / `InvalidModelField` / `RegistryMissing`） |
| `llmw/cli.py` | 注册 `llmw model <add/list/show/set-default/unset-default/remove>` 子命令 |
| `llmw/workspace/manager.py` | `init` 写 workspace 级 `.gitignore` 模板；`list_wikis` 通过 resolve 拿 model 来源 |
| `llmw/wiki/store.py` | `SCHEMA_VERSION_SUPPORTED` 升到 2（语义：model 字段是 registry `model_id`） |
| `llmw/wiki/manager.py` | `wiki_add` / `wiki_config_set` 校验 `model` 字段存在于 registry；`wiki_show` 用 resolve |
| `llmw/wiki/enter.py` | 通过 resolve 拿 ModelEntry；构造 env overlay（`ANTHROPIC_MODEL` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`）；subprocess 显式 `env=`；dry-run 输出新格式 |
| `README.md` | 在「Manual Smoke Test」一节末尾追加 model registry 验收脚本片段 |

---

## Task 1: 错误类扩展

**Files:**
- Modify: `llmw/errors.py`（追加 7 个错误类）

- [ ] **Step 1: 在 `llmw/errors.py` 中追加 model 相关错误类**

在文件末尾（`format_error` 函数前）追加以下类。注意：所有 `exit_code = 1`（用户错误）。

```python
# ===== model registry 错误 (exit_code = 1) =====

class ModelNotInRegistry(LlmwError):
    exit_code = 1
    user_message = "wiki 引用了不存在的 model_id"


class ModelDefaultNotSet(LlmwError):
    exit_code = 1
    user_message = "workspace 没有默认 model"


class ModelDefaultAmbiguous(LlmwError):
    exit_code = 1
    user_message = "registry 存在多条 is_default=true, 数据损坏"


class ModelIdConflict(LlmwError):
    exit_code = 1
    user_message = "model_id 已存在"


class ModelIsDefault(LlmwError):
    exit_code = 1
    user_message = "目标 model 是默认, 不能直接 remove"


class InvalidModelField(LlmwError):
    exit_code = 1
    user_message = "model 字段值非法"


class RegistryMissing(LlmwError):
    exit_code = 1
    user_message = "workspace_models.toml 不存在"
```

- [ ] **Step 2: 手工 smoke**

```bash
cd /home/zryang/llm_workspace_cli
python -c "from llmw.errors import ModelNotInRegistry, ModelDefaultNotSet, ModelDefaultAmbiguous, ModelIdConflict, ModelIsDefault, InvalidModelField, RegistryMissing; print('ok')"
```

期望输出 `ok`，无 ImportError。

- [ ] **Step 3: Commit**

```bash
git add llmw/errors.py
git commit -m "feat(errors): add 7 model-registry error classes"
```

---

## Task 2: llmw/models/ 包骨架 + api_key 脱敏

**Files:**
- Create: `llmw/models/__init__.py`
- Create: `llmw/models/redact.py`

- [ ] **Step 1: 创建 `llmw/models/__init__.py`**

```python
"""workspace model registry: workspace_models.toml + llmw model 命令族"""
from llmw.models.redact import redact_api_key

__all__ = ["redact_api_key"]
```

- [ ] **Step 2: 创建 `llmw/models/redact.py`**

```python
"""api_key 展示脱敏（任何 list / show / dry-run 出口必须走这里）"""

def redact_api_key(key: str) -> str:
    """统一脱敏规则。设计 §9.3：
    len <= 8 → '***'；否则 '前3...末4'（例：sk-...XYZW）。
    """
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}...{key[-4:]}"
```

- [ ] **Step 3: 手工 smoke**

```bash
cd /home/zryang/llm_workspace_cli
python -c "from llmw.models import redact_api_key; assert redact_api_key('sk-ant-abc1234XYZ9') == 'sk-...XYZ9'; assert redact_api_key('short') == '***'; assert redact_api_key('') == ''; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add llmw/models/__init__.py llmw/models/redact.py
git commit -m "feat(models): scaffold llmw/models/ package + api_key redact"
```

---

## Task 3: llmw/models/store.py（dataclass + load/save + 校验 + chmod）

**Files:**
- Create: `llmw/models/store.py`

- [ ] **Step 1: 创建 `llmw/models/store.py`**

完整内容（dataclass + 校验 + load/save + chmod）：

```python
"""workspace_models.toml 读写 + 字段校验 + chmod 600"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from llmw._compat import toml_loads, toml_dump
from llmw.errors import (
    InvalidModelField, ModelDefaultAmbiguous, ModelDefaultNotSet,
    ModelIdConflict, RegistryMissing, SchemaVersionUnsupported,
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

    import io
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
```

- [ ] **Step 2: 手工 smoke**

```bash
cd /home/zryang/llm_workspace_cli
TMP=$(mktemp -d)
python -c "
from pathlib import Path
from llmw.models.store import Registry, ModelEntry, save, load, create_skeleton

reg = create_skeleton(Path('$TMP'))
reg.models['m1'] = ModelEntry(model_id='m1', name='M1', base_url='https://api.example.com', api_key='sk-abc1234567890', is_default=True)
save(Path('$TMP'), reg)

# load 回来
reg2 = load(Path('$TMP'))
assert 'm1' in reg2.models
assert reg2.models['m1'].is_default
print('load ok')

# chmod 检查
import stat
mode = stat.S_IMODE(Path('$TMP')/ 'workspace_models.toml'.replace('m1','workspace_models.toml').__class__(('$TMP/workspace_models.toml')).stat().st_mode)
assert oct(mode)[-3:] == '600', f'mode={oct(mode)}'
print('chmod 600 ok')
"
rm -rf "$TMP"
```

期望输出 `load ok` 和 `chmod 600 ok`。

- [ ] **Step 3: Commit**

```bash
git add llmw/models/store.py
git commit -m "feat(models): add store.py with ModelEntry/Registry + load/save + chmod 600"
```

---

## Task 4: llmw/models/resolve.py

**Files:**
- Create: `llmw/models/resolve.py`

- [ ] **Step 1: 创建 `llmw/models/resolve.py`**

```python
"""wiki → 最终 ModelEntry 单一查找入口

设计 §9.4。被 enter / show / list / wiki config 校验共同消费。
"""
from pathlib import Path

from llmw.errors import (
    ModelDefaultNotSet, ModelNotInRegistry, WikiDirMissing, WikiNotFound,
)
from llmw.models import store as models_store
from llmw.models.store import ModelEntry, RegistryMissing
from llmw.wiki import store as wiki_store
from llmw.workspace import store as ws_store


def resolve_for_wiki(workspace_root: Path, wiki_name: str) -> ModelEntry:
    """返回 enter 时该 wiki 实际使用的 ModelEntry。

    优先级：
      1. wiki_metadata.model （若存在）→ 必须在 registry 中
      2. registry 中 is_default=true 的唯一条目

    异常：
      WikiNotFound:        wiki 不在 workspace.toml 中
      WikiDirMissing:      wiki 子目录缺失
      RegistryMissing:     registry 文件不存在（被内部转换为 ModelDefaultNotSet）
      ModelNotInRegistry:  wiki.model 引用了 registry 中不存在的 model_id
      ModelDefaultNotSet:  registry 空或无 is_default=true
      ModelDefaultAmbiguous: 多条 is_default=true（数据损坏, load 时抛）
    """
    ws = ws_store.load(workspace_root)
    if wiki_name not in ws.wikis:
        raise WikiNotFound(
            f"wiki '{wiki_name}' 不在当前 workspace 中",
            hint="运行 `llmw list` 查看已注册 wiki",
        )

    wiki_dir = workspace_root / ws.wikis[wiki_name].path
    if not wiki_dir.is_dir():
        raise WikiDirMissing(
            f"wiki 子目录不存在: {wiki_dir}",
            hint="可能被外部 rm；可 `git checkout` 恢复或重新 add",
        )

    meta = None
    if (wiki_dir / "wiki_metadata.toml").is_file():
        meta = wiki_store.load(wiki_dir)

    try:
        reg = models_store.load(workspace_root)
    except RegistryMissing as e:
        # 用户体验：直接说 ModelDefaultNotSet，不要暴露 RegistryMissing
        raise ModelDefaultNotSet(
            str(e.message),
            hint="运行 `llmw model add --model-id ... --name ... --base-url ... --api-key ... --default` 初始化 registry",
        )

    # wiki 指定了 model → 必须存在
    if meta is not None and meta.model:
        if meta.model not in reg.models:
            raise ModelNotInRegistry(
                f"wiki '{wiki_name}' 引用了不存在的 model_id '{meta.model}'",
                hint="运行 `llmw model list` 查看可用 model_id, 或用 `llmw wiki --name=<name> config unset model` 走默认",
            )
        return reg.models[meta.model]

    # fallback 到默认（load 时已保证 0/1 条）
    defaults = [m for m in reg.models.values() if m.is_default]
    if not defaults:
        raise ModelDefaultNotSet(
            "registry 中没有 is_default=true 的条目",
            hint="运行 `llmw model set-default --model-id <ID>` 标记默认",
        )
    return defaults[0]
```

- [ ] **Step 2: 手工 smoke**

```bash
cd /home/zryang/llm_workspace_cli
TMP=$(mktemp -d)
# 建空 workspace
python -c "
from pathlib import Path
from llmw.workspace.store import create_skeleton
create_skeleton(Path('$TMP'))
"
# 此时 registry 不存在 → resolve 应抛 ModelDefaultNotSet
python -c "
from pathlib import Path
from llmw.models.resolve import resolve_for_wiki
from llmw.errors import ModelDefaultNotSet
try:
    resolve_for_wiki(Path('$TMP'), 'foo')
except ModelDefaultNotSet as e:
    print('ok:', e.message[:30])
" 2>&1 | tail -1
rm -rf "$TMP"
```

期望输出 `ok: workspace_models.toml 不存在`（前缀）。

- [ ] **Step 3: Commit**

```bash
git add llmw/models/resolve.py
git commit -m "feat(models): resolve_for_wiki single entry point"
```

---

## Task 5: llmw/models/manager.py — set_default + add

**Files:**
- Create: `llmw/models/manager.py`（先建骨架 + set_default + add + TTY 交互 + list/show/remove 全部）

- [ ] **Step 1: 创建 `llmw/models/manager.py` 完整版**

```python
"""llmw model <action> 业务层"""
import json
import sys
from pathlib import Path
from typing import Optional

from llmw.errors import (
    InvalidModelField, MissingRequiredFlag, ModelIdConflict, ModelIsDefault,
    ModelNotInRegistry, PurgeRequiresConfirmation,
)
from llmw.fsutil import safe_rmtree
from llmw.models import store as models_store
from llmw.models.redact import redact_api_key
from llmw.models.store import (
    ModelEntry, Registry, create_skeleton, load, save,
    validate_api_key, validate_base_url, validate_model_id, validate_name,
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
    if model_id is not None:   validate_model_id(model_id)
    if name is not None:       validate_name(name)
    if base_url is not None:   validate_base_url(base_url)
    if api_key is not None:    validate_api_key(api_key)

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
        if not model_id: missing.append("--model-id")
        if not name: missing.append("--name")
        if not base_url: missing.append("--base-url")
        if not api_key: missing.append("--api-key")
        if missing:
            raise MissingRequiredFlag(
                f"非 TTY 下 model add 缺 flag: {', '.join(missing)}",
                hint="补齐 flag 重试，或在 TTY 下用交互模式",
            )

    # 加载现有 registry；不存在 → 初始化
    from llmw.models.store import RegistryMissing
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
        model_id=model_id, name=name, base_url=base_url,
        api_key=api_key, is_default=False,
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
        print(f"{m.model_id.ljust(20)}  {m.name[:20].ljust(20)}  {star}      {m.base_url}  {redact_api_key(m.api_key)}")
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
    reg = load(workspace_root)
    set_default(reg, model_id)
    save(workspace_root, reg)
    print(f"✓ '{model_id}' 设为默认（旧的自动取消）", file=sys.stdout)


# ===== model_unset_default =====

def model_unset_default(workspace_root: Path) -> None:
    reg = load(workspace_root)
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
    reg = load(workspace_root)
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
```

- [ ] **Step 2: 手工 smoke**

```bash
cd /home/zryang/llm_workspace_cli
TMP=$(mktemp -d)
export LLMW_WORKSPACE="$TMP"
llmw init --path "$TMP" --no-git

# add
llmw model add --model-id m1 --name "M1" --base-url "https://api.example.com" --api-key "sk-test-1234567890" --default
test -f "$TMP/workspace_models.toml" && echo "✓ registry 创建"

# list / show
llmw model list
llmw model list --json
llmw model show --model-id m1

# 重复 add → ModelIdConflict
llmw model add --model-id m1 --name "Dup" --base-url "https://x" --api-key "sk-dup" 2>&1 | grep -q "ModelIdConflict" && echo "✓ 重复拦截"

# remove 默认 → ModelIsDefault
llmw model remove --model-id m1 2>&1 | grep -q "ModelIsDefault" && echo "✓ 默认拦截"

unset LLMW_WORKSPACE
rm -rf "$TMP"
```

期望所有 ✓ 通过。

- [ ] **Step 3: Commit**

```bash
git add llmw/models/manager.py
git commit -m "feat(models): manager.py with add/list/show/set-default/unset-default/remove"
```

---

## Task 6: cli.py 注册 model 子命令

**Files:**
- Modify: `llmw/cli.py`（新增 `model` subparser 块 + main 分派）

- [ ] **Step 1: 在 `cli.py` 的 build_parser 中 `wiki` subparser 前插入 `model` subparser**

定位：在 `# ===== workspace 级 =====` 注释与 `# ===== wiki 级 =====` 注释之间。插入：

```python
    # ===== model registry =====
    p_model = sub.add_parser("model", help="workspace model registry", parents=[common])
    model_sub = p_model.add_subparsers(dest="model_action", metavar="ACTION")

    pm_add = model_sub.add_parser("add", help="新增 model 条目", parents=[common])
    pm_add.add_argument("--model-id",  default=None, dest="model_id")
    pm_add.add_argument("--name",      default=None)
    pm_add.add_argument("--base-url",  default=None, dest="base_url")
    pm_add.add_argument("--api-key",   default=None, dest="api_key")
    pm_add.add_argument("--default",   action="store_true", dest="as_default")

    pm_list = model_sub.add_parser("list", help="列出所有 model 条目", parents=[common])

    pm_show = model_sub.add_parser("show", help="查看单条 model", parents=[common])
    pm_show.add_argument("--model-id", required=True, dest="model_id")

    pm_sd = model_sub.add_parser("set-default", help="标记默认 model", parents=[common])
    pm_sd.add_argument("--model-id", required=True, dest="model_id")

    pm_usd = model_sub.add_parser("unset-default", help="清空默认标记", parents=[common])

    pm_rm = model_sub.add_parser("remove", help="删除 model 条目", parents=[common])
    pm_rm.add_argument("--model-id", required=True, dest="model_id")
    pm_rm.add_argument("--yes", "-y", action="store_true")
```

- [ ] **Step 2: 在 `cli.py` 的 main 分派中 `if args.command == "list":` 之前插入 `model` 分派**

插入位置：`if args.command == "list":` 之前（即 init 后、config 前）。插入：

```python
        if args.command == "model":
            from llmw.models.manager import (
                model_add, model_list, model_show, model_set_default,
                model_unset_default, model_remove,
            )
            ma = args.model_action
            if ma == "add":
                model_add(
                    ws_root,
                    model_id=args.model_id, name=args.name,
                    base_url=args.base_url, api_key=args.api_key,
                    as_default=args.as_default,
                )
            elif ma == "list":
                return model_list(ws_root, as_json=getattr(args, "json", False))
            elif ma == "show":
                model_show(ws_root, args.model_id, as_json=getattr(args, "json", False))
            elif ma == "set-default":
                model_set_default(ws_root, args.model_id)
            elif ma == "unset-default":
                model_unset_default(ws_root)
            elif ma == "remove":
                model_remove(ws_root, args.model_id, yes=args.yes)
            else:
                print("[llmw] model 子命令需要 ACTION (add/list/show/set-default/unset-default/remove)",
                      file=sys.stderr)
                return 1
            return 0
```

- [ ] **Step 3: 手工 smoke**

```bash
cd /home/zryang/llm_workspace_cli
TMP=$(mktemp -d)
export LLMW_WORKSPACE="$TMP"
llmw init --path "$TMP" --no-git
llmw model add --model-id m1 --name "M1" --base-url "https://api.example.com" --api-key "sk-test-1234567890" --default
llmw model list --json
unset LLMW_WORKSPACE
rm -rf "$TMP"
```

期望 JSON 数组含一条 `model_id="m1"`，`api_key` 为脱敏的 `sk-...7890`，`is_default=true`。

- [ ] **Step 4: Commit**

```bash
git add llmw/cli.py
git commit -m "feat(cli): register `llmw model` subcommand family"
```

---

## Task 7: workspace init 写 .gitignore + list_wikis 用 resolve

**Files:**
- Modify: `llmw/workspace/manager.py`（init 末尾追加 .gitignore；list_wikis 改用 resolve）

- [ ] **Step 1: 在 `init` 函数 `ws_store.create_skeleton(path)` 之后追加 .gitignore 写入**

定位：`llmw/workspace/manager.py` 的 `init` 函数。修改后：

```python
    ws_store.create_skeleton(path)

    # 写 workspace 级 .gitignore（workspace 本身就是 git 仓）
    _ensure_workspace_gitignore(path)

    print(f"[llmw] workspace 已初始化于 {path}", file=sys.stdout)
    print(f"[llmw] cd {path} 后可用 `llmw wiki add <name>` 新建第一个 wiki", file=sys.stdout)
    return path
```

并在 `init` 之前定义 helper：

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
        # 在文件末尾追加 marker 段
        addition = f"\n{marker_start}\n{GITIGNORE_LINE}\n{marker_end}\n"
        from llmw.fsutil import atomic_write
        atomic_write(gitignore, text + addition)
    else:
        content = f"{marker_start}\n{GITIGNORE_LINE}\n{marker_end}\n"
        from llmw.fsutil import atomic_write
        atomic_write(gitignore, content)
```

- [ ] **Step 2: 修改 `list_wikis` 使用 resolve**

定位：`list_wikis` 函数。当前从 `meta.model` + `ws.default_model` 推断 model 来源——改为走 `resolve.resolve_for_wiki` 拿完整信息（含 model_id / name / source）。

替换 `list_wikis` 中 `rows.append({...})` 之前的 model 计算块：

```python
        # 通过 resolve 拿 model 来源（若失败则不阻断 list, 标为 <unresolved>）
        model_info = None
        try:
            from llmw.models.resolve import resolve_for_wiki
            entry_obj = resolve_for_wiki(workspace_root, name)
            model_info = {
                "model_id": entry_obj.model_id,
                "name": entry_obj.name,
                "source": "wiki override" if (meta and meta.model) else "registry default",
            }
        except Exception:
            model_info = None
```

并修改 rows.append：

```python
        rows.append({
            "name": name,
            "path": entry.path,
            "exists": exists,
            "display_name": meta.display_name if meta else "",
            "tags": list(meta.tags) if meta else [],
            "model": model_info["model_id"] if model_info else (meta.model if meta else None),
            "model_source": model_info["source"] if model_info else None,
        })
```

同时修改 as_json 输出与表格 MODEL 列。as_json 输出块：

```python
    if as_json:
        import json
        out = [
            {
                "name": r["name"], "path": r["path"],
                "display_name": r["display_name"] or None,
                "tags": r["tags"],
                "model": r["model"],
                "model_source": r["model_source"],
                "wiki_dir_exists": r["exists"],
            }
            for r in rows
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
```

表格输出块（保留列定义 + 模型列加 source 后缀）：

```python
    if not rows:
        print("# (no wikis registered)")
        return 0
    name_w = max(len(r["name"]) for r in rows + [{"name": "NAME"}])
    path_w = max(len(r["path"]) for r in rows + [{"path": "PATH"}])
    print(f"{'NAME'.ljust(name_w)}  {'PATH'.ljust(path_w)}  DISPLAY_NAME  TAGS  MODEL")
    for r in rows:
        prefix = "⚠ " if not r["exists"] else "  "
        dn = r["display_name"] or "-"
        tags = ",".join(r["tags"]) or "-"
        if r["model"]:
            model_cell = r["model"]
            if r["model_source"]:
                model_cell += f" ({r['model_source']})"
        else:
            model_cell = "-"
        print(f"{prefix}{r['name'].ljust(name_w - 2)}  {r['path'].ljust(path_w)}  {dn}  {tags}  {model_cell}")
    return 0
```

- [ ] **Step 3: 手工 smoke**

```bash
cd /home/zryang/llm_workspace_cli
TMP=$(mktemp -d)
export LLMW_WORKSPACE="$TMP"
llmw init --path "$TMP" --no-git
grep -q "workspace_models.toml" "$TMP/.gitignore" && echo "✓ .gitignore 写入"
unset LLMW_WORKSPACE
rm -rf "$TMP"
```

期望输出 `✓ .gitignore 写入`。

- [ ] **Step 4: Commit**

```bash
git add llmw/workspace/manager.py
git commit -m "feat(workspace): init writes .gitignore; list_wikis uses resolve"
```

---

## Task 8: wiki schema_version=2 + wiki add/config 校验 + show 用 resolve

**Files:**
- Modify: `llmw/wiki/store.py`（`SCHEMA_VERSION_SUPPORTED` 改为 2）
- Modify: `llmw/wiki/manager.py`（`add` 校验 model；`wiki_config_set` 校验 model；`show` 用 resolve）

- [ ] **Step 1: `llmw/wiki/store.py` 升 schema_version 到 2**

将 `SCHEMA_VERSION_SUPPORTED = 1` 改为 `SCHEMA_VERSION_SUPPORTED = 2`。

- [ ] **Step 2: `llmw/wiki/manager.py` 中 `add` 在非 TTY 检查之前插入 model_id 校验**

定位：`add` 函数内，紧跟 `ws = ws_store.load(workspace_root)` 之后、`if name in ws.wikis:` 之前。插入：

```python
    # Phase 2: 校验 model_id 存在于 registry
    if model is not None:
        from llmw.models.resolve import resolve_for_wiki
        try:
            # resolve_for_wiki 自身会校验；这里只用 registry check 部分。
            # 直接走 store.load + 在场校验更轻：
            from llmw.models.store import load as models_load, RegistryMissing
            try:
                reg = models_load(workspace_root)
            except RegistryMissing:
                from llmw.errors import ModelDefaultNotSet
                raise ModelDefaultNotSet(
                    "workspace 还没有 registry, 无法校验 model",
                    hint="先跑 `llmw model add --model-id ... --name ... --base-url ... --api-key ... --default` 至少一条",
                )
            if model not in reg.models:
                from llmw.errors import ModelNotInRegistry
                raise ModelNotInRegistry(
                    f"model_id '{model}' 不在 registry 中",
                    hint="运行 `llmw model list` 查看可用 model_id",
                )
        except ImportError:
            # models 包未实现（极端情况）——静默允许
            pass
```

- [ ] **Step 3: `llmw/wiki/manager.py` 中 `wiki_config_set` 在 `setattr` 前插入 model 校验**

定位：`wiki_config_set` 函数内 `if key == "tags":` 之后、`else:` 之前。插入：

```python
    if key == "model":
        from llmw.models.store import load as models_load, RegistryMissing
        from llmw.errors import ModelNotInRegistry, ModelDefaultNotSet
        try:
            reg = models_load(workspace_root)
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
```

并把原来的 `else: setattr(meta, key, value or None)` 改为保持原样（`model` 字段也走 `setattr(meta, key, value or None)`，但 model 校验已通过）。

- [ ] **Step 4: `llmw/wiki/manager.py` 中 `show` 改用 resolve**

定位：`show` 函数内的 `final_model = ...` 块。替换为：

```python
    # 通过 resolve 拿最终 model + 来源
    final_model = None
    model_source = None
    try:
        from llmw.models.resolve import resolve_for_wiki
        m = resolve_for_wiki(workspace_root, name)
        final_model = m.model_id
        model_source = "wiki override" if (meta and meta.model) else "registry default"
    except Exception:
        # resolve 失败 → 维持向后兼容：旧逻辑
        final_model = (meta.model if meta else None) or ws.default_model
        if final_model:
            if meta and meta.model:
                model_source = "wiki.metadata.model"
            elif ws.default_model:
                model_source = "workspace.default_model"
```

- [ ] **Step 5: 手工 smoke**

```bash
cd /home/zryang/llm_workspace_cli
TMP=$(mktemp -d)
export LLMW_WORKSPACE="$TMP"
llmw init --path "$TMP" --no-git
llmw model add --model-id m1 --name "M1" --base-url "https://api.example.com" --api-key "sk-test-1234567890" --default

# 创建 schema_version=2 的 wiki（setup_wiki.py 需要 SKILL，可能不可用）
# 跳过 setup，直接手动 mock 一个 wiki dir：
mkdir -p "$TMP/foo/raw" "$TMP/foo/wiki"
cat > "$TMP/foo/wiki_metadata.toml" <<EOF
schema_version = 2
name = "foo"
topic = "Foo"
created_at = "2026-06-28T10:00:00Z"
updated_at = "2026-06-28T10:00:00Z"
display_name = ""
description = ""
tags = []
EOF

# wiki add --model 不存在的 id 应被拦（注意：完整 add 会跑 setup_wiki.py，需 SKILL）
# 这里只验证 config set / show
llmw wiki --name=foo config set model bogus 2>&1 | grep -q "ModelNotInRegistry" && echo "✓ config 校验拦截"

llmw wiki --name=foo config set model m1 && echo "✓ config 接受合法 id"

llmw wiki --name=foo show 2>&1 | grep -q "m1" && echo "✓ show 展示 model"

unset LLMW_WORKSPACE
rm -rf "$TMP"
```

期望三个 ✓ 通过。

- [ ] **Step 6: Commit**

```bash
git add llmw/wiki/store.py llmw/wiki/manager.py
git commit -m "feat(wiki): schema v2 + add/config set validate model_id; show uses resolve"
```

---

## Task 9: wiki enter.py — resolve + env overlay + dry-run 新格式

**Files:**
- Modify: `llmw/wiki/enter.py`

- [ ] **Step 1: 重写 `llmw/wiki/enter.py`**

完整替换文件内容：

```python
"""wiki enter — 启动 Claude Code session (Phase 2: 通过 resolve 拿 model, env overlay 注入 ANTHROPIC_*)

来源: doc/design/03-wiki-enter.md + 09-workspace-model-registry.md §9.5。
Phase 2 契约：env 不再完全透明——显式注入 ANTHROPIC_MODEL/BASE_URL/AUTH_TOKEN，其他从 os.environ 透传。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from llmw.errors import ClaudeNotFound, WikiDirMissing, WikiNotFound
from llmw.models.redact import redact_api_key
from llmw.models.resolve import resolve_for_wiki
from llmw.models.store import ModelEntry
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
    缺失返回 (None, path)。空文件返回 ("", path)——按设计空 CLAUDE.md 仍传 ``--system-prompt ""``。
    """
    claude_md = wiki_path / "CLAUDE.md"
    if not claude_md.is_file():
        return None, claude_md
    return claude_md.read_text(encoding="utf-8"), claude_md


def _build_cmd(wiki_path: Path):
    """构造 claude 子进程 argv。Phase 2 不变：--add-dir + 可选 --system-prompt。"""
    prompt, _ = _read_system_prompt(wiki_path)
    cmd = ["claude", "--add-dir", str(wiki_path)]
    if prompt is not None:
        cmd += ["--system-prompt", prompt]
    return cmd, prompt


def _build_env_overlay(model: ModelEntry) -> dict:
    """Phase 2：显式注入 3 个 ANTHROPIC_* env（其他 key 从 os.environ 透传）。"""
    return {
        "ANTHROPIC_MODEL":      model.model_id,
        "ANTHROPIC_BASE_URL":   model.base_url,
        "ANTHROPIC_AUTH_TOKEN": model.api_key,
    }


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
            f"[llmw] warning: wiki '{name}' 缺少 CLAUDE.md，"
            f"session 启动后将没有 schema 上下文",
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

    # Phase 2：通过 resolve 拿最终 model（失败会阻断 enter）
    model = resolve_for_wiki(workspace_root, name)

    cmd, prompt = _build_cmd(wiki_path)
    full_env = {**os.environ, **_build_env_overlay(model)}

    # dry-run
    if dry_run:
        from llmw.wiki.store import load as wiki_load
        meta = None
        if meta_p.is_file():
            try:
                meta = wiki_load(wiki_path)
            except Exception:
                meta = None
        ws = ws_store.load(workspace_root)
        print(f"[llmw] workspace: {workspace_root}", file=sys.stdout)
        print(f"[llmw] wiki:      {name} ({wiki_path})", file=sys.stdout)
        print(
            f"[llmw] resolved model: {model.name} ({model.model_id})",
            file=sys.stdout,
        )
        source = "wiki override" if (meta and meta.model) else "registry default"
        print(f"[llmw] source: {source}", file=sys.stdout)
        print(f"[llmw] ANTHROPIC_MODEL      = {model.model_id}", file=sys.stdout)
        print(f"[llmw] ANTHROPIC_BASE_URL   = {model.base_url}", file=sys.stdout)
        print(f"[llmw] ANTHROPIC_AUTH_TOKEN = {redact_api_key(model.api_key)}", file=sys.stdout)
        if claude_md.is_file():
            print(
                f"[llmw] CLAUDE.md: ✓ found ({claude_md.stat().st_size} bytes)",
                file=sys.stdout,
            )
        else:
            print(f"[llmw] CLAUDE.md: ✗ missing", file=sys.stdout)
        if prompt is not None:
            cmd_display = (
                f'claude --add-dir {wiki_path} '
                f'--system-prompt "$(cat {claude_md})"'
            )
        else:
            cmd_display = f'claude --add-dir {wiki_path}'
        print(f"[llmw] cmd:", file=sys.stdout)
        print(f"  {cmd_display}", file=sys.stdout)
        print(f"[llmw] env overlay: ANTHROPIC_MODEL/BASE_URL/AUTH_TOKEN（其他透传 os.environ）",
              file=sys.stdout)
        print(f"[llmw] --dry-run: 未执行", file=sys.stdout)
        return 0

    # 真正执行
    os.chdir(wiki_path)
    result = subprocess.run(cmd, env=full_env)
    return result.returncode
```

- [ ] **Step 2: 手工 smoke**

```bash
cd /home/zryang/llm_workspace_cli
TMP=$(mktemp -d)
export LLMW_WORKSPACE="$TMP"
llmw init --path "$TMP" --no-git
llmw model add --model-id m1 --name "M1" --base-url "https://api.example.com" --api-key "sk-test-1234567890" --default

# mock wiki
mkdir -p "$TMP/foo"
echo "# schema" > "$TMP/foo/CLAUDE.md"
cat > "$TMP/foo/wiki_metadata.toml" <<EOF
schema_version = 2
name = "foo"
topic = "Foo"
created_at = "2026-06-28T10:00:00Z"
updated_at = "2026-06-28T10:00:00Z"
display_name = ""
description = ""
tags = []
EOF
# 手动注册到 workspace.toml
python -c "
import re
p = '$TMP/workspace.toml'
text = open(p).read()
text += '''
[wikis.foo]
path = \"foo\"
created_at = \"2026-06-28T10:00:00Z\"
'''
open(p, 'w').write(text)
"

# dry-run
llmw wiki --name=foo enter --dry-run 2>&1 | grep -q "ANTHROPIC_MODEL" && echo "✓ env overlay 输出"
llmw wiki --name=foo enter --dry-run 2>&1 | grep -q "sk-...7890" && echo "✓ api_key 脱敏"
llmw wiki --name=foo enter --dry-run 2>&1 | grep -q "resolved model: M1" && echo "✓ resolved model 展示"

# unset default → enter 阻断
llmw model unset-default
llmw wiki --name=foo enter --dry-run 2>&1 | grep -q "ModelDefaultNotSet" && echo "✓ 无默认阻断"

# 恢复
llmw model set-default --model-id m1
llmw wiki --name=foo enter --dry-run >/dev/null 2>&1 && echo "✓ 恢复后正常"

unset LLMW_WORKSPACE
rm -rf "$TMP"
```

期望所有 ✓ 通过。

- [ ] **Step 3: Commit**

```bash
git add llmw/wiki/enter.py
git commit -m "feat(wiki): enter Phase 2 — resolve + ANTHROPIC_* env overlay + dry-run rewrite"
```

---

## Task 10: README 更新 + 端到端 Manual Smoke

**Files:**
- Modify: `README.md`（在 Manual Smoke Test 节末尾追加 model registry 验收脚本片段）
- Run: 端到端 smoke（验收整个 feature）

- [ ] **Step 1: 在 `README.md` 末尾追加 model registry smoke 脚本**

定位：`README.md` 的「Manual Smoke Test」节末尾。追加：

````markdown

### Workspace Model Registry (Phase 2)

```bash
TMPWS=$(mktemp -d)
export LLMW_WORKSPACE="$TMPWS"

llmw init --path "$TMPWS" --no-git
test -f "$TMPWS/.gitignore" && grep -q "workspace_models.toml" "$TMPWS/.gitignore"

llmw model add --model-id minimax-m3 --name "MiniMax M3" \
    --base-url "https://api.example.com" --api-key "sk-test-1234567890" --default
test "$(stat -c '%a' "$TMPWS/workspace_models.toml")" = "600"

llmw model list
llmw model list --json | grep -q "sk-...7890"

mkdir -p "$TMPWS/foo"
echo "# schema" > "$TMPWS/foo/CLAUDE.md"
cat > "$TMPWS/foo/wiki_metadata.toml" <<EOF
schema_version = 2
name = "foo"
topic = "Foo"
created_at = "2026-06-28T10:00:00Z"
updated_at = "2026-06-28T10:00:00Z"
display_name = ""
description = ""
tags = []
EOF
# 注册到 workspace.toml (实际用 llmw wiki add，这里 dry-run 校验)
llmw wiki --name=foo enter --dry-run | grep -q "ANTHROPIC_MODEL"

rm -rf "$TMPWS"
```
````

- [ ] **Step 2: 端到端 smoke 全跑一遍**

跑 §9.8 验收清单中的 11 条 happy path + 上方 README smoke。期望所有 `✓` 通过、exit code 为 0。

```bash
cd /home/zryang/llm_workspace_cli
# 完整脚本见 doc/design/09-workspace-model-registry.md §9.8
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: append model-registry smoke to README"
```

---

## Self-Review Checklist（执行前自检）

- [ ] **Spec coverage**：§9.1 模块 → Task 2-5；§9.2 schema → Task 3；§9.3 命令族 → Task 5+6；§9.4 resolve → Task 4；§9.5 enter 集成 → Task 9；§9.6 .gitignore + chmod → Task 3+7；§9.7 错误类 → Task 1
- [ ] **Placeholder scan**：所有 task 含完整代码块（无 "TBD" / "类似 Task N" / "fill in"）
- [ ] **Type consistency**：`ModelEntry` 字段（model_id / name / base_url / api_key / is_default）跨 Task 3/4/5 一致；`Registry.bump()` / `Registry.created_at` / `updated_at` 一致；`resolve_for_wiki(workspace_root, wiki_name)` 签名跨 Task 4/7/8/9 一致
- [ ] **错误类引用一致性**：`ModelNotInRegistry` / `ModelDefaultNotSet` / `ModelDefaultAmbiguous` / `ModelIdConflict` / `ModelIsDefault` / `InvalidModelField` / `RegistryMissing` 在 Task 1 定义、在后续 task import 使用一致
- [ ] **schema_version 一致性**：workspace_models.toml = 2（Task 3）；wiki_metadata.toml 升到 2（Task 8）
- [ ] **chmod 600 一致性**：Task 3 save 中 chmod；Task 5 manager.remove 后删空文件——空文件删除后再 add 时会走 create_skeleton，无权限遗留
- [ ] **prototype 节奏**：每个 task 用「实现 → 手工 smoke → commit」替换 TDD「写测试 → 失败 → 实现 → 通过」，符合 [[project-prototype-first]]