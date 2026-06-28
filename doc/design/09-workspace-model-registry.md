# 09 · Workspace Model Registry（Phase 2）

> **状态**：待用户审阅
> **依赖**：`04-data-model.md`（`workspace.toml` / `wiki_metadata.toml` schema）、`03-wiki-enter.md`（`enter` 命令契约）

本章设计 workspace 级 model registry：允许一个 workspace 注册多个 model 条目，每个 wiki 可选择使用其中一个；若 wiki 未指定，则 fallback 到 registry 标记为 `is_default=true` 的 model。

---

## 9.0 范围与非范围

**在范围内**：

- `<workspace>/workspace_models.toml` 读写与字段校验
- `llmw model add/list/show/remove/set-default/unset-default` 命令族
- wiki→model 解析链（单一入口 `resolve.resolve_for_wiki()`）
- `wiki add --model` / `wiki config set model` 写入时校验 `model_id` 存在于 registry
- `enter` 在启动 claude 子进程时通过 `env=` 注入 `ANTHROPIC_MODEL` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`
- `llmw init` 在 workspace 内写 `.gitignore` 片段 + `chmod 600` registry 文件
- 新增错误类（见 §9.7）

**不在范围内（明确推迟）**：

- Phase 1 → Phase 2 自动迁移脚本——Phase 1 未被实际使用，字段语义调整不需迁移
- 自动化单元测试与 CI 搭建——按项目节奏（prototype 优先），功能稳定后单独起测试设计
- 凭证轮换 / 加密 / secret manager 集成——`workspace_models.toml` 本地明文 + `chmod 600` 即可
- 模型选择策略（按 tag、按 topic 路由等）——本次只做"手动选一个"
- 跨 workspace 共享 registry——registry 严格 per-workspace
- registry 文件内条目加密 / 单独 keyring——`api_key` 明文存 + 文件权限 600

---

## 9.1 架构与文件布局

### 文件

| 文件 | 角色 | git |
| --- | --- | --- |
| `<workspace>/workspace_models.toml` | **新增**：registry（model 条目清单 + 默认标记） | **gitignored** |
| `<workspace>/.gitignore` | **新增**（由 `llmw init` 写入模板）：包含 `workspace_models.toml` 行 | 入仓 |
| `<workspace>/workspace.toml` | 现有；本设计不动字段 | 入仓 |
| `<wiki>/wiki_metadata.toml` | 现有；`model` 字段语义收敛为"registry `model_id`" | 入仓 |

### 新增模块

```
llmw/
└── models/                       # 新增包, 与 llmw/workspace/、llmw/wiki/ 平级
    ├── __init__.py
    ├── store.py                  # workspace_models.toml 读写 + ModelEntry dataclass
    ├── manager.py                # add / list / show / remove / set-default / unset-default
    └── resolve.py                # resolve_for_wiki() 单一入口
```

调用关系：

```
llmw model <action>      → llmw.models.manager
llmw wiki add --model X  → llmw.wiki.manager → llmw.models.resolve (仅校验 X 存在)
llmw wiki config set model X
                         → llmw.wiki.manager → llmw.models.resolve (同上)
llmw wiki show           → llmw.wiki.manager → llmw.models.resolve (取展示用)
llmw list                → llmw.workspace.manager → llmw.models.resolve (按需)
llmw wiki enter          → llmw.wiki.enter → llmw.models.resolve → env overlay
```

`resolve.py` 是 wiki→最终 model 的唯一查找入口，`enter` / `show` / `list` 全部走它。

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

[[models]]
model_id  = "minimax-m3"
name      = "MiniMax M3"
base_url  = "https://api.example.com"
api_key   = "sk-..."
is_default = true

[[models]]
model_id  = "claude-sonnet-4-6"
name      = "Claude Sonnet 4.6"
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
| `models[].name` | ✅ | string | UTF-8，1-128 字符，人类可读展示名 |
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

`json` 输出字段名保持 `api_key`，但值为脱敏后字符串；调用方若需明文 key，仅在 `enter` 内部 env overlay 里使用，从不打印。

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
| `enter()` | `_resolve_model()` → 失败直接抛，阻断 enter |
| `show()` | 取 `model` + `name` + `base_url`（脱敏）展示 |
| `list()` | 取 `model` + `name` 展示；非 TTY 表格加 `MODEL` 列 |
| `enter --dry-run` | 额外打印 `registry source: wiki override | registry default` |

---

## 9.5 `enter` 集成

### 当前契约（Phase 1，来自 `03-wiki-enter.md`）

> "subprocess 不传 `env`" + "不传 model"

### Phase 2 契约变化

env 不再完全透明——CLI 现在会注入 `ANTHROPIC_MODEL` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`。为贴近"CLI 不动用户 env"的原则，**只显式设置这三个 key**，其他全部从 `os.environ` 透传。

### 实现

```python
def _build_cmd_and_env(wiki_path: Path, ws_root: Path, name: str):
    model = resolve.resolve_for_wiki(ws_root, name)  # 抛 ModelNotInRegistry / ModelDefaultNotSet
    cmd = ["claude", "--add-dir", str(wiki_path)]
    prompt = _read_system_prompt(wiki_path)
    if prompt is not None:
        cmd += ["--system-prompt", prompt]
    env_overlay = {
        "ANTHROPIC_MODEL":      model.model_id,
        "ANTHROPIC_BASE_URL":   model.base_url,
        "ANTHROPIC_AUTH_TOKEN": model.api_key,
    }
    full_env = {**os.environ, **env_overlay}
    return cmd, full_env, model
```

```python
def enter(workspace_root: Path, name: str, dry_run: bool = False) -> int:
    # ... 既有校验（路径、CLAUDE.md 软警告、claude 在 PATH）...
    cmd, full_env, model = _build_cmd_and_env(wiki_path, workspace_root, name)

    if dry_run:
        # ... 既有 dry-run 打印 ...
        print(f"[llmw] resolved model: {model.name} ({model.model_id})", file=sys.stdout)
        source = "wiki override" if meta and meta.model else "registry default"
        print(f"[llmw] source: {source}", file=sys.stdout)
        print(f"[llmw] ANTHROPIC_MODEL      = {model.model_id}", file=sys.stdout)
        print(f"[llmw] ANTHROPIC_BASE_URL   = {model.base_url}", file=sys.stdout)
        print(f"[llmw] ANTHROPIC_AUTH_TOKEN = {redact_api_key(model.api_key)}", file=sys.stdout)
        # ... 既有 cmd / env 描述 ...
        return 0

    os.chdir(wiki_path)
    result = subprocess.run(cmd, env=full_env)
    return result.returncode
```

### 不破坏 Phase 1 软警告

`CLAUDE.md` 缺失、`wiki_metadata.toml` 缺失、子目录空——继续走软警告，不阻断。model 解析失败**会阻断**（与 Phase 1 一致：`WikiDirMissing` 等错误也是阻断的）。

### dry-run 输出示例（Phase 2）

```
$ llmw wiki --name=llm-systems enter --dry-run
[llmw] workspace: /home/user/yzr_llm_workspace
[llmw] wiki:      llm-systems (/home/user/yzr_llm_workspace/llm-systems)
[llmw] resolved model: MiniMax M3 (minimax-m3)
[llmw] source: registry default
[llmw] ANTHROPIC_MODEL      = minimax-m3
[llmw] ANTHROPIC_BASE_URL   = https://api.example.com
[llmw] ANTHROPIC_AUTH_TOKEN = sk-...XYZW
[llmw] CLAUDE.md: ✓ found (3042 bytes)
[llmw] cmd:
  claude --add-dir /home/user/yzr_llm_workspace/llm-systems --system-prompt "$(cat ...)"
[llmw] --dry-run: 未执行
```

---

## 9.6 `.gitignore` 与文件权限

`llmw init` 在 workspace 根创建以下 `.gitignore`（workspace 本身就是 git 仓——参见 `01-workspace-management.md`）：

```gitignore
# llmw: machine-local files
workspace_models.toml
```

这一份 gitignore 已经覆盖 workspace 根路径下的 `workspace_models.toml`，不需要用户额外配置。命名上不再区分"顶层"与"workspace 级"——只有一个文件，由 CLI 维护。

如果用户的 workspace 嵌在更大 monorepo 里（非 `llmw init --git` 默认行为），workspace 级 `.gitignore` 仍然有效（git 自下而上匹配 `.gitignore`）。

### `chmod 600`

registry 文件创建 / 写入时（`atomic_write` 之后）：

```python
os.chmod(toml_path, 0o600)
```

`atomic_write` 已有（`llmw/fsutil.py`），可在 `models/store.py` 的 `save()` 里追加 chmod 调用，或在 `init_skeleton()` 中显式调用。

### 安全姿态总结

| 风险 | 缓解 |
| --- | --- |
| API key 推到公网 git | workspace_models.toml gitignored；顶层 + workspace 级双重 `.gitignore` |
| 本机其他用户读 key | 文件权限 600（仅 owner 可读写） |
| 误将 registry 文件 cp 到别处 | 不在本设计范围内（提醒用户即可） |
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

`RegistryMissing`（registry 文件不存在）由 `resolve.py` 内部捕获，转化为 `ModelDefaultNotSet`（带特殊 hint）。**不直接抛 `RegistryMissing` 给用户**——避免用户看到一个新错误类名不知道做什么。

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
test -f "$TMPWS/.gitignore" && grep -q "workspace_models.toml" "$TMPWS/.gitignore" && echo "✓ init 写入 .gitignore"
test ! -e "$TMPWS/workspace_models.toml" && echo "✓ init 不创建 registry"

# 2. model add --default
llmw model add --model-id minimax-m3 --name "MiniMax M3" --base-url "https://api.example.com" --api-key "sk-test-1234567890" --default
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

# 8. enter --dry-run 展示 env overlay
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter --dry-run | grep -q "ANTHROPIC_MODEL" && echo "✓ enter dry-run 展示 env"
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter --dry-run | grep -q "sk-..." && echo "✓ api_key 脱敏"

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

---

## 9.9 后续阶段（明确推迟，不在本设计）

- 自动化单元测试（`tests/test_models_*`）与集成测试（mock `subprocess.run` 校验 env 注入）
- CI 配置（GitHub Actions：lint + smoke test）
- 测试覆盖率指标
- 凭证轮换 / secret manager 集成
- 模型选择策略（按 tag / topic 自动路由）
- 跨 workspace 共享 registry

以上每一项独立起一份设计文档。