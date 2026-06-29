# 09 · Workspace Model Registry（Phase 2）

> **状态**：待用户审阅
> **依赖**：`04-data-model.md`（`workspace.toml` / `wiki_metadata.toml` schema）、`03-wiki-enter.md`（`enter` 命令契约）
> **修订**：2026-06-29 §9.5 交付机制重构——overlay 从"subprocess env 注入 + `--setting-sources project,local`"改为"写 `<wiki>/.claude/settings.local.json`（Local 层）+ lazy on enter"。registry 数据模型 / `resolve_for_wiki()` / `wiki_metadata.model` 语义**不变**。
> **修订 2**：2026-06-29 §9.6 gitignore 重构——确认**单仓模型**（wiki 是 workspace 直属子目录，非嵌套独立仓），overlay secret 的 git 忽略从"per-wiki `.gitignore`（SKILL `setup_wiki.py`）"改为"workspace 根 managed block 通配行（CLI `llmw init`）"，与 wiki 创建迁移解耦。

本章设计 workspace 级 model registry：允许一个 workspace 注册多个 model 条目，每个 wiki 可选择使用其中一个；若 wiki 未指定，则 fallback 到 registry 标记为 `is_default=true` 的 model。registry 是 model 配置的**唯一真相源**；§9.5 描述 resolved model 如何**交付**给 Claude Code session。

---

## 9.0 范围与非范围

**在范围内**：

- `<workspace>/workspace_models.toml` 读写与字段校验
- `llmw model add/list/show/remove/set-default/unset-default` 命令族
- wiki→model 解析链（单一入口 `resolve.resolve_for_wiki()`）
- `wiki add --model` / `wiki config set model` 写入时校验 `model_id` 存在于 registry
- `enter` 把 resolved model 交付给 Claude Code：**写 `<wiki>/.claude/settings.local.json` 的 `env` 块**（`ANTHROPIC_MODEL`=`name` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`），lazy on enter，**不再**注入 subprocess env、**不再**传 `--setting-sources`（见 §9.5）
- 新增模块 `llmw/models/overlay.py`（`render` / `inspect` / `apply`）
- `llmw init` 的 workspace `.gitignore` managed block 扩展为两行（`workspace_models.toml` + `*/.claude/settings.local.json`）+ `chmod 600` registry 与 overlay 文件（单仓模型：`*/.claude/settings.local.json` 通配覆盖所有 wiki 的 overlay secret，**不依赖** per-wiki gitignore / wiki scaffold——见 §9.6）
- 新增错误类（见 §9.7）

**不在范围内（明确推迟）**：

- Phase 1 → Phase 2 自动迁移脚本——Phase 1 未被实际使用，字段语义调整不需迁移
- 自动化单元测试与 CI 搭建——按项目节奏（prototype 优先），功能稳定后单独起测试设计
- 凭证轮换 / 加密 / secret manager 集成——`workspace_models.toml` 本地明文 + `chmod 600` 即可
- 模型选择策略（按 tag、按 topic 路由等）——本次只做"手动选一个"
- 跨 workspace 共享 registry——registry 严格 per-workspace
- registry 文件内条目加密 / 单独 keyring——`api_key` 明文存 + 文件权限 600
- **wiki 级脱离 registry 的手编 model 配置**——registry 仍是唯一真相源，`.claude/settings.local.json` 是 resolved model 的派生产物
- **Eager 同步**（model 变更即重写所有受影响 wiki 的 overlay 文件）——只做 Lazy on enter（见 §9.5）
- **老 workspace 迁移**——工具尚未正式部署：workspace 根 `.gitignore`（`init`）新建时即写，无存量需迁移

---

## 9.1 架构与文件布局

### 文件

| 文件 | 角色 | git |
| --- | --- | --- |
| `<workspace>/workspace_models.toml` | **新增**：registry（model 条目清单 + 默认标记，唯一真相源） | **gitignored** |
| `<workspace>/.gitignore` | **新增**（由 `llmw init` 写 managed block）：含 `workspace_models.toml` + `*/.claude/settings.local.json` | 入仓 |
| `<workspace>/workspace.toml` | 现有；本设计不动字段 | 入仓 |
| `<wiki>/wiki_metadata.toml` | 现有；`model` 字段语义收敛为"registry `model_id`" | 入仓 |
| `<wiki>/.claude/settings.local.json` | **新增**：resolved model 的**派生产物**（overlay 交付文件，lazy on enter 生成） | **gitignored**（workspace 根 `.gitignore` 的 `*/.claude/settings.local.json` 忽略；wiki 是 workspace 直属子目录、单仓模型，不依赖 per-wiki gitignore） |

### 新增模块

```
llmw/
└── models/                       # 新增包, 与 llmw/workspace/、llmw/wiki/ 平级
    ├── __init__.py
    ├── store.py                  # workspace_models.toml 读写 + ModelEntry dataclass
    ├── manager.py                # add / list / show / remove / set-default / unset-default
    ├── resolve.py                # resolve_for_wiki() 单一入口
    └── overlay.py                # render/inspect/apply: resolved model → <wiki>/.claude/settings.local.json
```

调用关系：

```
llmw model <action>      → llmw.models.manager
llmw wiki add --model X  → llmw.wiki.manager → llmw.models.resolve (仅校验 X 存在)
llmw wiki config set model X
                         → llmw.wiki.manager → llmw.models.resolve (同上)
llmw wiki show           → llmw.wiki.manager → llmw.models.resolve (取展示用)
llmw list                → llmw.workspace.manager → llmw.models.resolve (按需)
llmw wiki enter          → llmw.models.resolve (拿 ModelEntry) → llmw.models.overlay.apply (写 settings.local.json)
                         → subprocess(claude --add-dir [--system-prompt])   # 透传 os.environ, 无 --setting-sources
```

`resolve.py` 是 wiki→最终 model 的唯一查找入口，`enter` / `show` / `list` 全部走它。`overlay.py` 不读 registry、不做 resolve——只接收一个已解析好的 `ModelEntry`，渲染成 `env` 块并合并写盘。模块单向依赖：`enter → resolve → store`，`enter → overlay`。

### Schema 版本

| 文件 | Phase 1 | Phase 2 |
| --- | --- | --- |
| `workspace.toml` | `schema_version = 1` | `schema_version = 1`（不变） |
| `<wiki>/wiki_metadata.toml` | `schema_version = 1` | `schema_version = 2`（语义：model 字段是 registry `model_id`） |
| `workspace_models.toml` | 不存在 | `schema_version = 2`（新增） |

`workspace_metadata.toml` 升到 2 是为了明确"wiki.model 字段须在 registry 中存在"——读取时强制校验，避免 Phase 1 残留的字符串无校验通过。

---

## 9.2 数据模型：`workspace_models.toml`

### Schema

```toml
schema_version = 2
created_at = "2026-06-28T10:00:00Z"
updated_at = "2026-06-28T10:15:00Z"

# name = 网关模型名（注入 ANTHROPIC_MODEL 的值，网关只认这个），兼作显示
[[models]]
model_id  = "minimax-m3"
name      = "MiniMax-M3[1m]"
base_url  = "https://api.example.com"
api_key   = "sk-..."
is_default = true

[[models]]
model_id  = "claude-sonnet-4-6"
name      = "claude-sonnet-4-6"   # 官方 Anthropic 端点：name 即模型 id 本身
base_url  = "https://api.anthropic.com"
api_key   = "sk-ant-..."
is_default = false
```

### 字段

| 字段 | 必填 | 类型 | 规则 |
| --- | --- | --- | --- |
| `schema_version` | ✅ | int | 固定为 2 |
| `created_at` | ✅ | ISO8601 string | 文件首次创建时间，CLI 维护，只读 |
| `updated_at` | ✅ | ISO8601 string | 任何 `save()` 后自动 bump |
| `[[models]]` | — | array of table | 可为空（空 registry 视作 `ModelDefaultNotSet`） |
| `models[].model_id` | ✅ | string | 小写字母 / 数字 / `-` / `_`，长度 1-64；全文件唯一 |
| `models[].name` | ✅ | string | UTF-8，1-128 字符；**网关模型名**（注入 `ANTHROPIC_MODEL` 的值，如 `MiniMax-M3[1m]`），兼作显示名。受 `model_id` 的 `^[a-z0-9_-]+$` 正则限制，含 `.`/`[` 等的网关名只能存这里 |
| `models[].base_url` | ✅ | string | 必须以 `http://` 或 `https://` 开头 |
| `models[].api_key` | ✅ | string | 非空，不校验格式（不透明串） |
| `models[].is_default` | 隐式 `false` | bool | 同时最多一条为 `true` |

### `model_id` 校验

复用 `llmw.wiki.store.NAME_RE = ^[a-z0-9_-]{1,64}$`，抽出到 `llmw/models/store.py` 的 `MODEL_ID_RE`（或直接 `from llmw.wiki.store import NAME_RE as MODEL_ID_RE`——后者更省事）。

### `base_url` 校验

```python
def validate_base_url(url: str) -> None:
    if not (url.startswith("http://") or url.startswith("https://")):
        raise InvalidModelField(...)
```

### 加载时整体校验

```python
def load(workspace_root: Path) -> Registry:
    # 1. 读 toml
    # 2. schema_version == 2，否则 SchemaVersionUnsupported
    # 3. 遍历 [[models]]，逐字段校验（见上表）
    # 4. 全文件唯一性：model_id 不重复 → ModelIdConflict
    # 5. is_default 计数：
    #    - 0 条 → ModelDefaultNotSet
    #    - >=2 条 → ModelDefaultAmbiguous
    #    - 1 条   → 通过
    # 6. 返回 Registry dataclass
```

### 写时不变量（`save` 不重复校验）

调用方可以在内存中构造任意 `Registry` 对象；`save()` 只做序列化，不重复校验 `is_default` 唯一性——避免每次 `save` 多余扫描。该约束由两个集中入口保证：

```python
def set_default(reg: Registry, model_id: str) -> None:
    """manager 层暴露的统一函数：保证 is_default 全局唯一。
    add --default 与 set-default 都走它，避免双入口状态不一致。"""
    if model_id not in reg.models:
        raise ModelNotInRegistry(...)
    for m in reg.models.values():
        m.is_default = False
    reg.models[model_id].is_default = True
    reg.bump()
```

`add --default` 流程：先 `model_add(reg, ...)`（仅做"无此 id" + 字段校验 + 追加到 dict）→ 再 `set_default(reg, model_id)`（保证唯一性 + bump）。两步都通过后才 `save()`。

### 缺失 registry 文件

`workspace_models.toml` 不存在 → `load()` 抛 `RegistryMissing`；`resolve.resolve_for_wiki()` 捕获后转化为 `ModelDefaultNotSet`，hint：`运行 \`llmw model add --default\` 初始化 registry`。

---

## 9.3 CLI 命令族：`llmw model <action>`

### 命令清单

| 命令 | 必填 flag | 可选 flag | 说明 |
| --- | --- | --- | --- |
| `llmw model add` | `--model-id ID --name NAME --base-url URL --api-key KEY` | `--default` | 新增条目；`--default` 时自动 unset 其他默认 |
| `llmw model list` | — | `--json` | 列出所有条目（`api_key` 脱敏） |
| `llmw model show` | `--model-id ID` | `--json` | 展示单条详情（`api_key` 脱敏） |
| `llmw model set-default` | `--model-id ID` | — | 把指定条目设为默认（旧默认自动取消） |
| `llmw model unset-default` | — | — | 把所有 `is_default` 清为 `false`（边界场景，之后 `enter` 会报 `ModelDefaultNotSet`） |
| `llmw model remove` | `--model-id ID` | `--yes`（非 TTY 必需） | 删除条目；若目标条目 `is_default=true` → 报 `ModelIsDefault`，先 `set-default` 别的或 `unset-default` |

### TTY / 非 TTY 行为

沿用 `wiki add` 现有模式：

- **TTY**：`add` 缺 flag → 交互提示输入；`remove` 缺 `--yes` → 确认 prompt
- **非 TTY**：`add` 缺任一必填 flag → `MissingRequiredFlag`；`remove` 缺 `--yes` → `PurgeRequiresConfirmation`（复用现有错误类，hint 调整）

### `api_key` 展示规则

任何输出（`list` 表格、`show` 表格、`--json` 输出、`enter --dry-run` 展示）一律脱敏：

```python
def redact_api_key(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}...{key[-4:]}"  # 例: sk-...XYZW
```

`json` 输出字段名保持 `api_key`，但值为脱敏后字符串；调用方若需明文 key，仅在 `enter` 内部 overlay 写盘时使用，从不打印。

### 现有 `wiki config` 的交互调整

`llmw wiki --name=X config set model <id>` 写入时：

```python
def wiki_config_set(workspace_root, name, key, value):
    ...
    if key == "model":
        # 校验 value 存在于 registry
        try:
            models_store.load(workspace_root)  # 触发 RegistryMissing → ModelDefaultNotSet
        except RegistryMissing:
            raise ModelDefaultNotSet(
                f"workspace 还没有 registry, 无法校验 model '{value}'",
                hint="先跑 `llmw model add ...` 至少一条",
            )
        # 校验 value 是某个 model_id
        reg = models_store.load(workspace_root)
        if value not in reg.models:
            raise ModelNotInRegistry(
                f"model_id '{value}' 不在 registry 中",
                hint=f"运行 `llmw model list` 查看可用 model_id",
            )
    ...
```

类似的校验加到 `wiki add --model`。

---

## 9.4 解析链：`resolve.py`

### 单一入口

```python
def resolve_for_wiki(workspace_root: Path, wiki_name: str) -> ModelEntry:
    """返回 enter 时该 wiki 实际使用的 ModelEntry。

    异常:
      WikiNotFound:         wiki 不在 workspace.toml 中
      WikiDirMissing:       wiki 子目录缺失（其他命令也会抛）
      ModelNotInRegistry:   wiki.model 已设但 registry 中无此 model_id
      ModelDefaultNotSet:   registry 为空或无 is_default=true
      ModelDefaultAmbiguous: 多条 is_default=true（数据损坏）
    """
    ws = ws_store.load(workspace_root)
    if wiki_name not in ws.wikis:
        raise WikiNotFound(...)

    wiki_dir = workspace_root / ws.wikis[wiki_name].path
    if not wiki_dir.is_dir():
        raise WikiDirMissing(...)

    meta = wiki_store.load(wiki_dir) if (wiki_dir / "wiki_metadata.toml").is_file() else None

    try:
        reg = models_store.load(workspace_root)
    except RegistryMissing:
        raise ModelDefaultNotSet(
            "workspace_models.toml 不存在, 没有可用的 model",
            hint="运行 `llmw model add --model-id ... --name ... --base-url ... --api-key ... --default` 初始化 registry",
        )

    # 查找
    if meta is not None and meta.model:
        if meta.model not in reg.models:
            raise ModelNotInRegistry(
                f"wiki '{wiki_name}' 引用了不存在的 model_id '{meta.model}'",
                hint="运行 `llmw model list` 查看可用 model_id, 或用 `llmw wiki --name=<name> config unset model` 走默认",
            )
        return reg.models[meta.model]

    # fallback 到默认
    defaults = [m for m in reg.models.values() if m.is_default]
    if not defaults:
        raise ModelDefaultNotSet(
            "registry 中没有 is_default=true 的条目",
            hint="运行 `llmw model set-default --model-id <ID>` 标记默认, 或 `llmw model add ... --default` 新增并设默认",
        )
    if len(defaults) > 1:
        raise ModelDefaultAmbiguous(
            f"registry 中存在 {len(defaults)} 条 is_default=true, 数据损坏",
            hint="运行 `llmw model set-default --model-id <ID>` 修复唯一性",
        )
    return defaults[0]
```

### 调用方

| 调用方 | 用法 |
| --- | --- |
| `enter()` | `resolve_for_wiki()` → 失败直接抛，阻断 enter（在 overlay 写盘之前）→ 成功则交 `overlay.apply()` |
| `show()` | 取 `model` + `name` + `base_url`（脱敏）展示 |
| `list()` | 取 `model` + `name` 展示；非 TTY 表格加 `MODEL` 列 |
| `enter --dry-run` | 额外打印 `registry source: wiki override | registry default` + overlay 文件预览（见 §9.5） |

---

## 9.5 `enter` 集成：overlay 交付（settings.local.json）

> 本节描述 resolved model 如何**送达** Claude Code。registry / resolve（§9.2–9.4）不变。

### 9.5.1 为什么不用 subprocess env

Claude Code 的 settings 优先级（高 → 低）：**Managed > CLI args(--settings) > Local > Project > User**。`env` 块属于 settings 层，会重新应用到 session，而**子进程继承的 env 优先级低于所有 settings 层**。

因此早期"用 `subprocess.run(env=full_env)` 注入 `ANTHROPIC_*`"的方案，会被用户 `~/.claude/settings.json` 的 `env` 块盖掉，只能靠 `--setting-sources project,local` 把 **User 层整个排除**来规避——代价是 wiki 会话丢掉 User 级配置（`enabledPlugins` / `theme` / `statusLine`）。

**本设计的做法**：把 overlay 放进 **Local 层**（`<wiki>/.claude/settings.local.json` 的 `env` 块）。Local 优先级 **高于 User** → overlay 稳赢，**且可以正常加载 User 层** → user 配置回来。同时 overlay 从"临时 env"变成"持久文件"，可 cat/grep/审计，`enter` 也少一个 `--setting-sources` 特例（详见 `MEMORY/claude-settings-env-precedence.md`）。

### 9.5.2 核心改变

| 维度 | 早期（被取代） | 本设计 |
| --- | --- | --- |
| overlay 载体 | subprocess env（最低优先级） | `<wiki>/.claude/settings.local.json` 的 `env` 块（Local 层，> User） |
| `--setting-sources` | `project,local`（排除 user） | **删除**（加载默认 user+project+local） |
| subprocess env | `{**os.environ, **overlay}` | 透传 `os.environ`（默认） |
| user 配置 | 丢失 | **恢复** |
| 可审计性 | 临时 env，不可见 | 持久文件 |
| 真相源 | `workspace_models.toml` | **不变** |

### 9.5.3 新增不变量 I-5b（澄清，不放宽 I-1）

> CLI **允许**写 `<wiki>/.claude/settings.local.json` 这**一个**文件，作为 session-launch config（派生自 registry 的 resolved model）。它**不属于** wiki 内容：CLI 仍**不碰** `raw/` / `wiki/` 下的任何文件，也不编辑 `<wiki>/CLAUDE.md`；也**不写** `.claude/` 下该文件以外的任何内容。

`enter` 现在会写这一个 launch-config 文件——但这**不是**"写元数据"（`wiki_metadata.toml` 仍由 `wiki config` 等命令管），而是"为本次启动渲染一份交付配置"。`enter` 模块边界从"不写元数据"细化为"**只写**这一个 launch-config 文件，不写元数据"。

### 9.5.4 新 `enter` 流程

```
enter(workspace_root, name, dry_run)
  │
  ├─ resolve_wiki_path / wiki dir 校验 / CLAUDE.md·meta 软警告 / claude-in-PATH
  │
  ├─ model = resolve_for_wiki(workspace_root, name)   ← 失败则阻断（在任何写盘之前）
  │
  ├─ [dry-run]  path, would_write = overlay.inspect(wiki_path, model)
  │             打印 overlay path / would_write / render(model)(token 脱敏) / cmd(无 --setting-sources)
  │             return 0                                ← 不写盘
  │
  ├─ [real]     path = overlay.apply(wiki_path, model) ← lazy 幂等合并写（见 §9.5.6）
  │
  ├─ cmd = ["claude", "--add-dir", str(wiki_path)]
  │        prompt = read CLAUDE.md; 非缺失则 cmd += ["--system-prompt", prompt]
  │
  ├─ os.chdir(wiki_path)
  └─ subprocess.run(cmd)                                ← 透传 os.environ（默认），无 env overlay，无 --setting-sources
```

关键点：

- **resolve 在 apply 之前**：解析失败（`ModelNotInRegistry` / `ModelDefaultNotSet` 等）时 enter 直接阻断，**不会写坏** overlay 文件。
- **subprocess 回到 Phase 1 的"env 透传"**：overlay 已在 Local 层文件里，`subprocess.run(cmd)` 默认继承 `os.environ`；不再有 `_build_env_overlay()` / `full_env`。
- **`--setting-sources` 删除**：claude 默认加载 user+project+local；cwd=wiki 子目录 → 读到 `<wiki>/.claude/settings.local.json`（Local，> User）→ overlay 稳赢，user 配置同时加载。
- **CLAUDE.md 缺失 / 子目录空 / `wiki_metadata.toml` 缺失** 继续走软警告，不阻断；model 解析失败**会**阻断（与既有 `WikiDirMissing` 等一致）。

### 9.5.4b Habit template 机制

> **新增于 2026-06-29**：overlay 不只写 model 字段，还随 `wiki enter` 一并写入一份
> **代码内常量**的"习惯级" env。这些 key 不通过 CLI 配、不能 per-workspace 改、
> 不能 per-wiki 关闭——目的是跨 session / 跨 wiki 保持**风格一致**。

**为什么需要**

不是所有 env 都该走 registry 真相源。`workspace_models.toml` 的本职是"model 元数据 +
凭证"——把 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`（隐私开关）这种**全 CLI 行为
约定**塞进去，是污染 schema；放 per-workspace toml 又会让"统一风格"裂开成 N 份配置。
最佳载体是**代码内常量**：

- 增删改 = 改一行 `llmw/models/overlay.py:_HABIT_TEMPLATE`
- 升级随 CLI 版本走（老 wiki 在下次 enter 自动同步）
- 不进 toml schema / 不进 CLI flag / 不进 registry

**结构**

```python
# llmw/models/overlay.py
_HABIT_TEMPLATE: dict[str, str] = {
    # 隐私: 关闭非必要流量（无遥测）
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    # 标记: API 侧可识别 llmw 启动的 session
    "CLAUDE_CODE_ATTRIBUTION_HEADER": "llmw",
}

_OWNED = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    *_HABIT_TEMPLATE.keys(),   # 自动跟随
)
```

`render(model)` = `{**_model_env(model), **_HABIT_TEMPLATE}`，把 model 字段与
habit template 合并成 flat dict。`inspect` / `apply` / `_is_up_to_date` 全部基于
`expected.items()` 迭代，**无需改算法**——加新 template key 自动生效。

**所有权与 reset 行为**

habit template key 与 `ANTHROPIC_*` 一同被 `_OWNED` 收编：CLI 是 owner，**用户手改
template key 会被下次 enter reset 回常量值**。这与 model 字段行为一致——避免
"模板"裂成"建议"。

**显式不做**

- **不**提供 per-workspace 模板配置（`workspace_template.toml` 之类）——会让"统一
  风格"裂成多份，违背初衷
- **不**提供 `llmw overlay set-habit` CLI 命令——同样违背"非用户可配"语义
- **不**提供 per-wiki opt-out——所有 wiki 共享同一套 habit

**扩展示例**

要加新 key（如 `CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192`）：在 `_HABIT_TEMPLATE` 加一行。
下次 `wiki enter` 自动同步到所有 wiki 的 `settings.local.json`；老 wiki 在 enter 时
因 `_is_up_to_date=False` 自动补齐。

**dry-run** 会在 model 字段后打印 `(habit template)` 标签 + 各 key 值（详见 §9.5.9），
让用户看到 enter 时会写入哪些 template key。

### 9.5.5 文件格式

`<wiki>/.claude/settings.local.json`：

```json
{
  "env": {
    "ANTHROPIC_MODEL": "MiniMax-M3[1m]",
    "ANTHROPIC_BASE_URL": "https://api.example.com",
    "ANTHROPIC_AUTH_TOKEN": "sk-..."
  }
}
```

- `ANTHROPIC_MODEL` 用 `model.name`（网关模型名，如 `MiniMax-M3[1m]`），**非 `model_id`** slug——网关只认 name。
- 不设原生 `model` settings 字段，保持 env-only（已被现行设计验证可用，避免与 env 在 claude 内部打架）。

### 9.5.6 `overlay.apply(wiki_dir, model)` 算法

```python
_HABIT_TEMPLATE: dict[str, str] = {
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "CLAUDE_CODE_ATTRIBUTION_HEADER": "llmw",
}

_OWNED = (
    "ANTHROPIC_MODEL", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN",
    *_HABIT_TEMPLATE.keys(),   # 自动跟随
)

def _model_env(model: ModelEntry) -> dict:
    return {
        "ANTHROPIC_MODEL":      model.name,       # 网关模型名, 非 model_id
        "ANTHROPIC_BASE_URL":   model.base_url,
        "ANTHROPIC_AUTH_TOKEN": model.api_key,
    }

def render(model: ModelEntry) -> dict:
    """ModelEntry + habit template → overlay env 块。"""
    return {**_model_env(model), **_HABIT_TEMPLATE}

def inspect(wiki_dir: Path, model: ModelEntry) -> tuple[Path, bool]:
    """dry-run 用: 返回 (path, would_write)。不写盘。损坏文件 → OverlayFileUnparseable。"""
    path = wiki_dir / ".claude" / "settings.local.json"
    expected = render(model)
    data = _load_existing(path)            # None / dict; 非法 JSON 抛 OverlayFileUnparseable
    env = (data or {}).get("env", {})
    stale = any(env.get(k) != v for k, v in expected.items())
    return path, (data is None) or stale

def apply(wiki_dir: Path, model: ModelEntry) -> Path:
    """real enter 用: 幂等合并写 + chmod 600。返回写入 path。"""
    path = wiki_dir / ".claude" / "settings.local.json"
    expected = render(model)

    # 1. 读现有文件（若存在）
    data = _load_existing(path) or {}      # 非法 JSON → OverlayFileUnparseable (绝不 clobber)

    # 2. 幂等短路: 所有 owned key (ANTHROPIC_* + habit template) 已全部 == expected → 不写
    env = dict(data.get("env") or {})
    if all(env.get(k) == v for k, v in expected.items()):
        return path

    # 3. 合并: 只覆盖 owned key, 保留 env 内其他 key + 所有其他顶层 key
    env.update(expected)
    data["env"] = env

    # 4. 原子写 + chmod 600
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass            # NFS 等不支持 chmod, best-effort
    return path
```

合并语义（关键安全保证）：

- **只拥有 `_OWNED` key 集**：覆盖这些（3 个 `ANTHROPIC_*` + 全部 habit template），
  保留 `env` 内其他 key（用户自设的别的 env）。
- **保留所有其他顶层 key**：如 `statusLine` / `enabledMcpjsonServers` / 用户手加的任意字段。
- **幂等**：所有 owned key 已一致 → 不写、不动 mtime（连跑两次 enter 第二次 no-op）。
- **绝不 clobber 损坏文件**：JSON 解析失败 → `OverlayFileUnparseable` 阻断，hint 手动修复。

### 9.5.7 边界

| 场景 | 行为 |
| --- | --- |
| 文件不存在 | 新建（含 `.claude/` 目录），写 env 块（ANTHROPIC_* + 全部 habit template） |
| 文件存在、无 `env` 块 | 加 `env` 块，保留其他顶层 key |
| 文件存在、`env` 有其他 key | 保留，只覆盖 `_OWNED`（ANTHROPIC_* + habit template） |
| 所有 owned key 已一致 | 幂等短路，不写 |
| 老文件只含 3 个 ANTHROPIC_*（无 habit template） | 下次 enter 自动补齐全部 habit template key（视为"stale"，触发重写） |
| 用户手动改了 habit template key | 下次 enter reset 回常量值（与 ANTHROPIC_* 行为一致；template 是"强制习惯"非"建议"） |
| 文件存在但 JSON 非法 | `OverlayFileUnparseable`（exit 1），不覆盖 |
| `.claude/` 是文件而非目录 / mkdir 失败 | OSError → 内部错误（exit 3） |
| NFS chmod 失败 | 静默跳过（best-effort，同 registry） |
| 文件是 symlink | `atomic_write`（tmp+rename）会替换成普通文件——可接受；如需保留 symlink 后续再议 |

### 9.5.8 Lazy 契约

**生成时机**：**仅** `wiki enter`（real）时调 `apply()`；`inspect()` 仅供 dry-run 预览。

**不主动重写的操作**（下次 enter 自愈）：`model add` / `set-default` / `unset-default` / `remove`；`wiki config set model` / `unset model`。

**一致性口径**：

- ✅ **enter 启动那一刻**：overlay 文件 100% 与 resolved model 一致（enter 刚重写过）。
- ⚠️ **两次 enter 之间**：磁盘文件可能"过时"——wiki 走 registry 默认，事后改了默认或轮换了某 model 的 api_key 但**还没重新 enter 该 wiki**：文件仍是旧值。下次 `enter` 一进即自动对齐。

这是 Lazy on enter 的既定行为。若需"磁盘永远实时一致"则要 Eager-on-mutation，本设计明确不做。

### 9.5.9 dry-run 输出示例

```
$ llmw wiki --name=llm-systems enter --dry-run
[llmw] workspace: /home/u/yzr_llm_wiki_workspace
[llmw] wiki:      llm-systems (...)
[llmw] resolved model: MiniMax-M3[1m] (minimax-m3)
[llmw] source: registry default
[llmw] overlay file: .../llm-systems/.claude/settings.local.json  (will write)
[llmw]   ANTHROPIC_MODEL      = MiniMax-M3[1m]
[llmw]   ANTHROPIC_BASE_URL   = https://api.example.com
[llmw]   ANTHROPIC_AUTH_TOKEN = sk-...XYZW
[llmw]   (habit template)
[llmw]     CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = 1
[llmw]     CLAUDE_CODE_ATTRIBUTION_HEADER          = llmw
[llmw] CLAUDE.md: ✓ found (3042 bytes)
[llmw] cmd:
  claude --add-dir .../llm-systems --system-prompt "$(cat .../CLAUDE.md)"
[llmw] --dry-run: 未执行
```

> `(will write)` 在文件已与 resolved model 一致时显示 `(up to date, skip)`。
> habit template key 在 model 字段下方以 `(habit template)` 标签分组,缩进 +2
> 视觉上与 model 字段区分;value 列在组内按最长 key 对齐。

---

## 9.6 `.gitignore` 与文件权限

**单层 gitignore（workspace 根 managed block 管两个 secret）**：本 CLI 是**单仓模型**——workspace 是唯一 git 仓，每个 wiki 是其直属子目录，**不是**嵌套独立仓。因此两个 secret 文件（registry 的 `workspace_models.toml`、overlay 的 `<wiki>/.claude/settings.local.json`）都由**同一个仓**管辖，统一在 workspace 根 `.gitignore` 忽略，**无需 per-wiki `.gitignore`、不依赖 wiki scaffold / `setup_wiki.py` 迁移**。

`llmw init` 的 managed 段（marker `# >>> llmw (managed by llmw) >>>` … `# <<< llmw <<<`）从单行扩展为两行：

```gitignore
# >>> llmw (managed by llmw) >>>
workspace_models.toml
*/.claude/settings.local.json
# <<< llmw <<<
```

- `*/.claude/settings.local.json` 匹配任意 workspace 直属子目录（即任意 wiki）下的 overlay secret；`*/` 只下钻一级，不误伤 workspace 根自身可能存在的 `.claude/`。
- overlay 是 **lazy on enter** 生成，gitignore 是 **init 时预埋**的通配规则——规则提前在、secret 文件后生成，永远不会被误提交；即便某 wiki 从未 `enter`，规则也已覆盖将来。
- 这是纯 **CLI 仓改动**（`llmw/workspace/manager.py:_ensure_workspace_gitignore` 的 managed block 内容常量），不涉及 SKILL submodule、不依赖 `setup_wiki.py`（后者已被 SKILL 移除，wiki 创建迁移属下一步单独设计——见 §9.10）。

### per-wiki `.gitignore` 的说明

wiki-spec.md §6 要求每个 wiki 根有一份 `.gitignore`（OS / 编辑器 / Obsidian / 临时文件）。在单仓模型下，这份文件（若由将来的 wiki 创建逻辑生成）对 workspace 仓也生效（git 自下而上认各级 `.gitignore`），但**与本设计无关**——overlay secret 的忽略已由 workspace 根的通配行保证，不要求 per-wiki `.gitignore` 存在。

### `chmod 600`

registry 文件与 overlay 文件创建 / 写入时（`atomic_write` 之后）：

```python
os.chmod(path, 0o600)
```

`atomic_write` 已有（`llmw/fsutil.py`），`models/store.py` 的 `save()` 与 `models/overlay.py` 的 `apply()` 各自追加 chmod 调用。

### 安全姿态总结

| 风险 | 缓解 |
| --- | --- |
| API key 推到公网 git | workspace 根 `.gitignore`（`llmw init` managed block）同时忽略 `workspace_models.toml`（registry）与 `*/.claude/settings.local.json`（overlay，单仓通配） |
| 本机其他用户读 key | 两个文件均 `chmod 600`（仅 owner 可读写；NFS best-effort） |
| 密钥副本增多 | overlay 文件使 api_key 从"registry 1 份"变为"每个 wiki 1 份"——既定代价，保护级别与 registry 一致 |
| 明文出 stdout | list / show / dry-run 一律走 `redact_api_key`；overlay 在 dry-run 预览时 token 脱敏 |
| 物理磁盘失窃 | 不在本设计范围内（建议用户使用 FileVault / LUKS） |

---

## 9.7 错误处理

在 `llmw/errors.py` 中新增（沿用现有 `LlmwError` 子类模式）：

| 错误类 | 退出码 | 触发场景 | 默认 hint |
| --- | --- | --- | --- |
| `ModelNotInRegistry` | 1 | wiki.model 引用不存在的 model_id | 运行 `llmw model list` 查看可用 |
| `ModelDefaultNotSet` | 1 | registry 空 / 无 is_default=true | 跑 `llmw model add --default ...` 或 `llmw model set-default --model-id X` |
| `ModelDefaultAmbiguous` | 1 | 多条 is_default=true（数据损坏） | 跑 `llmw model set-default --model-id X` 修复 |
| `ModelIdConflict` | 1 | add / set-default 引用已存在的 model_id | 换个 model_id 或先 remove 旧的 |
| `ModelIsDefault` | 1 | remove 试图删除 `is_default=true` 的条目 | 先 `set-default` 别的，或 `unset-default` 后再 remove |
| `InvalidModelField` | 1 | 字段校验失败（`model_id` 正则 / `name` 长度 / `base_url` 协议 / `api_key` 非空） | 见具体 message，message 内含字段名与规则 |
| `OverlayFileUnparseable`（**新**） | 1 | `<wiki>/.claude/settings.local.json` 存在但 JSON 非法 | 手动修复或删除该文件后重试；CLI 不会覆盖损坏文件 |

`RegistryMissing`（registry 文件不存在）由 `resolve.py` 内部捕获，转化为 `ModelDefaultNotSet`（带特殊 hint）。**不直接抛 `RegistryMissing` 给用户**——避免用户看到一个新错误类名不知道做什么。

`OSError`（overlay 的 `mkdir` / 写盘失败：磁盘满 / 只读 / `.claude` 是文件）→ 内部错误（exit 3），`--debug` 看 traceback。

### 现有错误类的复用

- `MissingRequiredFlag`——非 TTY `model add` 缺 flag
- `PurgeRequiresConfirmation`——非 TTY `model remove` 缺 `--yes`
- `InvalidConfigKey`——若未来 `model config` 子命令接收未知 key
- `WikiNotFound` / `WikiDirMissing`——`resolve_for_wiki` 中复用

---

## 9.8 验收清单（Manual Smoke，prototype 阶段）

> 按项目节奏（prototype 优先），本设计不展开自动化测试。下述清单是 prototype 阶段的最低人工验收。

每条 happy path 至少跑一遍：

```bash
TMPWS=$(mktemp -d)
LLMW_WORKSPACE="$TMPWS"

# 1. init（含 workspace 级 .gitignore）
llmw init --path "$TMPWS" --no-git
test -f "$TMPWS/.gitignore" && grep -q "workspace_models.toml" "$TMPWS/.gitignore" && echo "✓ init 写入 registry gitignore"
grep -q '\*/\.claude/settings.local.json' "$TMPWS/.gitignore" && echo "✓ init 写入 overlay gitignore 通配行"
test ! -e "$TMPWS/workspace_models.toml" && echo "✓ init 不创建 registry"

# 2. model add --default
llmw model add --model-id minimax-m3 --name "MiniMax-M3[1m]" --base-url "https://api.example.com" --api-key "sk-test-1234567890" --default
test -f "$TMPWS/workspace_models.toml" && echo "✓ add 创建 registry"
stat -c '%a' "$TMPWS/workspace_models.toml" | grep -q '^600$' && echo "✓ registry 权限 600"

# 3. model list / show
llmw model list
llmw model list --json
llmw model show --model-id minimax-m3
llmw model show --model-id minimax-m3 --json

# 4. wiki add --model 校验
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo add \
    --topic "Foo" --display-name "Foo" --description "x" \
    --tag a --model minimax-m3
test -f "$TMPWS/foo/wiki_metadata.toml" && echo "✓ wiki add --model 写入成功"

# 5. wiki add --model 不存在的 id → ModelNotInRegistry
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=bar add \
    --topic "Bar" --display-name "Bar" --description "x" \
    --tag a --model bogus 2>&1 | grep -q "ModelNotInRegistry" && echo "✓ 非法 model_id 被拦"

# 6. model add 重复 id → ModelIdConflict
LLMW_WORKSPACE="$TMPWS" llmw model add \
    --model-id minimax-m3 --name "Dup" --base-url "https://x" --api-key "sk-dup" 2>&1 \
    | grep -q "ModelIdConflict" && echo "✓ 重复 model_id 被拦"

# 7. model set-default 切换默认（旧默认自动 unset）
LLMW_WORKSPACE="$TMPWS" llmw model add \
    --model-id claude-sonnet --name "Claude" --base-url "https://api.anthropic.com" --api-key "sk-ant-test"
LLMW_WORKSPACE="$TMPWS" llmw model set-default --model-id claude-sonnet
LLMW_WORKSPACE="$TMPWS" llmw model show --model-id minimax-m3 --json | grep -q '"is_default": false' && echo "✓ 旧默认自动 unset"
LLMW_WORKSPACE="$TMPWS" llmw model show --model-id claude-sonnet --json | grep -q '"is_default": true' && echo "✓ 新默认生效"

# 8. enter --dry-run 展示 overlay（不写盘）
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter --dry-run | grep -q "overlay file" && echo "✓ enter dry-run 显示 overlay path"
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter --dry-run | grep -q "will write" && echo "✓ enter dry-run 标注 will write"
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter --dry-run | grep -q "sk-\.\.\." && echo "✓ api_key 脱敏"
test ! -e "$TMPWS/foo/.claude/settings.local.json" && echo "✓ dry-run 未写盘"

# 9. unset-default → enter 阻断
LLMW_WORKSPACE="$TMPWS" llmw model unset-default
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter --dry-run 2>&1 | grep -q "ModelDefaultNotSet" && echo "✓ 无默认时 enter 阻断"

# 10. 重新 set-default 后恢复
LLMW_WORKSPACE="$TMPWS" llmw model set-default --model-id claude-sonnet
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter --dry-run >/dev/null 2>&1 && echo "✓ 恢复后 enter 正常"

# 11. 移除 wiki & registry 清理
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo remove --purge --yes
rm -rf "$TMPWS"
```

### overlay 文件额外验收（需真跑交互式 claude，人工执行标"人工"的项）

```bash
TMPWS=$(mktemp -d); export LLMW_WORKSPACE="$TMPWS"
llmw init --path "$TMPWS" --no-git
llmw model add --model-id minimax-m3 --name "MiniMax-M3[1m]" \
    --base-url "https://api.example.com" --api-key "sk-test-1234567890" --default
llmw wiki --name=foo add --topic Foo --display-name Foo --description x --tag a --model minimax-m3

# A. 真跑 → 文件生成 + 600
# 人工: llmw wiki --name=foo enter
stat -c '%a' "$TMPWS/foo/.claude/settings.local.json" | grep -q '^600$' && echo "✓ overlay 权限 600"

# B. 幂等短路（连跑两次第二次 no-op）
T1=$(stat -c '%Y' "$TMPWS/foo/.claude/settings.local.json"); sleep 2
# 人工: llmw wiki --name=foo enter
T2=$(stat -c '%Y' "$TMPWS/foo/.claude/settings.local.json")
[ "$T1" = "$T2" ] && echo "✓ 幂等: 第二次未改 mtime"

# C. 合并保留：手塞别的 key，enter 后保留
python3 -c "import json; p='$TMPWS/foo/.claude/settings.local.json'; d=json.load(open(p)); d.setdefault('env',{})['MY_OTHER']='x'; d['statusLine']='keep'; json.dump(d,open(p,'w'),indent=2)"
# 人工: llmw wiki --name=foo enter
grep -q 'MY_OTHER' "$TMPWS/foo/.claude/settings.local.json" && echo "✓ 保留其他 env key"
grep -q 'statusLine' "$TMPWS/foo/.claude/settings.local.json" && echo "✓ 保留其他顶层 key"

# D. workspace 根 gitignore 通配行忽略 overlay 文件（单仓模型）
grep -q '\*/\.claude/settings.local.json' "$TMPWS/.gitignore" && echo "✓ workspace gitignore 含 overlay 通配行"
cd "$TMPWS" && git init -q && git add -A && git status --porcelain | grep -q 'settings.local.json' \
    && echo "✗ 未被忽略" || echo "✓ workspace gitignore 忽略 overlay 文件"

# E. 非法 JSON → 阻断且不覆盖
echo "{ broken" > "$TMPWS/foo/.claude/settings.local.json"
llmw wiki --name=foo enter --dry-run 2>&1 | grep -q "OverlayFileUnparseable" && echo "✓ 非法 JSON 被拦"
grep -q "broken" "$TMPWS/foo/.claude/settings.local.json" && echo "✓ 损坏文件未被覆盖"

# F. user 配置恢复（手动确认：有 ~/.claude/settings.json theme/plugin 时 enter 后 session 仍带）
rm -rf "$TMPWS"
```

---

## 9.9 实现时的连带改动（文档 / MEMORY）

实现代码时一并修改（属本设计交付物）：

- **`CLAUDE.md`**：不变量 I-1 措辞补 **I-5b**；顶层数据流图把 enter 的 `env overlay ANTHROPIC_*` 改为 `写 <wiki>/.claude/settings.local.json`、删 `--setting-sources`；模块边界表加 `llmw.models.overlay` 行、`enter` 行改"只写 launch-config 文件，不写元数据"；"`wiki enter` 的 model 解析"段交付方式改为 settings.local.json；"`init` 写 workspace `.gitignore`"相关描述更新为 managed block 两行（加 `*/.claude/settings.local.json`）。
- **`doc/design/03-wiki-enter.md`**：Phase 2 banner + §行为步骤 改为 settings.local.json 交付，删 `--setting-sources project,local` 与 env 注入描述。
- **`MEMORY/claude-settings-env-precedence.md`**：从"用 `--setting-sources project,local` 排除 user"改为"用 Local 层覆盖 user、并恢复 user 配置"；优先级事实保留（解释 Local 为何赢）。
- **`MEMORY/model-ops-no-env-vars.md`**：交付载体从"subprocess env 注入"改为"写 settings.local.json"；真相源不变的表述保留。
- **`llmw/workspace/manager.py`**：`_ensure_workspace_gitignore` 的 managed block 内容常量从单行 `workspace_models.toml` 扩展为两行（加 `*/.claude/settings.local.json`）——纯 CLI 仓改动，不涉及 SKILL submodule。
- **`README.md`**：Manual Smoke Test 段同步（加 overlay 文件检查项）。

---

## 9.10 后续阶段（明确推迟，不在本设计）

- **wiki 创建迁移**：CLI 按 `my_SKILL/llm-wiki-management/references/wiki-spec.md` 端到端生成 wiki（目录结构 / CLAUDE.md 模板逐字拷贝 + 占位符替换 / `index.md`·`log.md`·`MEMORY/README.md` 按 fixtures 逐字落盘 / `.gitignore` / git 处理 / 拒绝条件 / 版本钉死），替换当前已失效的 `setup_wiki.py` 子进程调用（SKILL 已移除该脚本，`wiki add` 当前不可用）；单仓模型下 wiki 是否 `git init`、per-wiki `.gitignore` 归属等在此设计内定——独立起一份设计文档
- 自动化单元测试（`tests/test_overlay_*`：mock FS 校验 merge / 幂等 / 损坏文件处理）与集成测试（mock `subprocess.run` 校验 cmd 不再带 `--setting-sources`）
- CI 配置（GitHub Actions：lint + smoke test）
- 测试覆盖率指标
- 凭证轮换 / secret manager 集成
- 模型选择策略（按 tag / topic 自动路由）
- 跨 workspace 共享 registry
- Eager 同步（model 变更重写所有受影响 wiki 的 overlay 文件）
- 保留 symlink overlay 文件（当前 `atomic_write` 会替换为普通文件）

以上每一项独立起一份设计文档。
