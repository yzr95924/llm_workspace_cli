# llmw — 模型配置注册表（Models Registry）设计文档

| 字段 | 值 |
| --- | --- |
| 版本 | 0.1（设计稿，待实现后随 v2 演进） |
| 日期 | 2026-06-27 |
| 状态 | 草案，5 节均已分节确认；待实现 + 自测 |
| 仓库 | `git@github.com:yzr95924/llm_workspace_cli.git` |
| 关联设计 | `doc/design.md`（v1 CLI 设计；本文档**叠加**于其上） |
| 关联 skill | `llm-wiki-management`（与本文档无关） |

## 背景与目标

### 痛点

`llmw enter <name>` 目前把模型选择限定在 `.workspace.toml` 的 `workspace.default_model` / `wikis.<name>.model` 字段里（`doc/design.md` §2.2、§3.7）。这两个字段只是字符串 ID（如 `claude-opus-4-8`），用户实际诉求里**远不止于此**：

1. **不同 provider 用同一个 model ID**：`claude-opus-4-8` 既可走 Anthropic 官方，也可走第三方代理 / 自部署网关——仅靠字符串无法区分。
2. **不同 endpoint 需要不同 base_url + api_key**：当前没有任何机制记录或切换；用户只能手工 `export` + 在 wiki 上下文里临时切换 shell 变量。
3. **api_key 散落**：常见做法是写在 `.env` / shell rcfile / `~/.netrc`——不在仓库控制下，容易泄露到 git 或日志。

### 目标

引入一个 **workspace 级模型配置注册表**（`models.toml`），集中管理所有"模型 + provider"的完整配置档（profile），并把 `llmw enter` 的模型选择从"字符串 ID"升级为"profile 选择"。具体：

- 一个 workspace 维护 0..N 个 profile；每个 profile 含 `name` / `model_id` / `base_url` / `api_key` 四项（**全部必填**）
- workspace 有一个 **default profile**（指向某个 name）
- `enter` 时按 `--profile` > 交互菜单（仅 TTY）> workspace default 的顺序解析；**解析不到则拒绝启动**（exit 1）
- 配置文件被 `.gitignore` 屏蔽（避免 api_key 误提交）
- api_key 由 CLI 通过子进程 env 注入给 `claude`，**永不出现在任何输出里**

### 非目标

- **不**做 profile 加密（filesystem 权限 = 0600 即可；用户自行管机器访问）
- **不**做 profile 共享 / 远程同步
- **不**改 `.workspace.toml` 的 schema——现有 `workspace.default_model` / `wikis.<name>.model` 字段保留并继续校验，但 `enter` 不再读它们（变为"展示型元数据"）
- **不**做 profile 与 wiki 的绑定——一个 workspace 一个 default；具体 wiki 用哪个 profile 由 `enter` 时一次性决定（`--profile` 或菜单）

## 设计原则（与 v1 spec 一致；新增条目加粗）

1. **CLI 是给人用的入口**：本特性**新增**到 CLI 入口；CLI 仍**不**做 LLM 推理
2. **`llmw` 与 `llm-wiki-management` 解耦**：与本文档无关
3. **配置文件是 SSOT**：**新增**——`models.toml` 是 profile 的 SSOT，与 `.workspace.toml` 并列
4. **subprocess > import**：跨仓 / 跨包调脚本一律 `subprocess.run`
5. **原子写盘**：**新增**——`models.toml` 同样走 atomic write + reparse 自检
6. **secret 不上 stdout**：**新增**——`api_key` 一律经 env 注入；list / show / 错误消息全部 redact

---

## §1 数据模型：models.toml

### 1.1 文件位置

`<workspace_root>/models.toml`——与 `.workspace.toml` 同级；**不进 git**（详见 §6）。

### 1.2 schema

```toml
# workspace 当前选定的 profile 名；空串表示"未设 default"。
# 任何时候必须能解析：若 default 非空，则它必须等于某个 [[models]].name。
default = "anthropic-prod"

[[models]]
name = "anthropic-prod"
model_id = "claude-opus-4-8"
base_url = "https://api.anthropic.com"
api_key = "sk-ant-..."

[[models]]
name = "thirdparty-vertex"
model_id = "claude-opus-4-8"
base_url = "https://custom.example.com"
api_key = "..."
```

**为什么是 `[[models]]` 数组表，而非 `[models.<name>]` 表？**

相同 `model_id` 可能由不同 provider 提供（Anthropic 官方 vs. 第三方代理），靠 name 区分；name 是 profile 的"用户友好别名"，与底层 model_id 解耦。把 name 当 table key 会让重复 model_id 跨 provider 无法表达（只能让用户把 name 编成 `<provider>-<id>`，但语义被名字绑架）。

### 1.3 字段表

| 字段 | 层级 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `default` | top | string | ❌ | `""` | 当前 workspace 默认 profile 的 `name`；空串 = 未设 default |
| `[[models]]` | array of tables | array | ✅（可空数组） | — | profile 数组；空数组合法（"暂未配置"） |
| `name` | `[[models]]` | string | ✅ | — | profile 名；kebab-case + workspace 内唯一 |
| `model_id` | `[[models]]` | string | ✅ | — | 传给 Claude 的 `--model` 值（如 `claude-opus-4-8`） |
| `base_url` | `[[models]]` | string | ✅ | — | provider endpoint；由 `enter` 注入给 claude 子进程 |
| `api_key` | `[[models]]` | string | ✅ | — | provider 凭证；由 `enter` 注入给 claude 子进程 |

**为什么四字段全部必填？** "只配 model_id 别名"的方案不够——base_url + api_key 缺失时该 profile 实际不可用；强制必填把"半成品"挡在保存之前。

### 1.4 校验规则

| 不变量 | 触发条件 | 严重度 | 错误 category |
| --- | --- | --- | --- |
| `name` 必须 kebab-case | 含大写 / 空格 / 下划线 | error | `models-validation-failed` |
| `name` workspace 内唯一 | 两个 profile 同名 | error | `models-validation-failed` |
| `model_id` 非空 | 空字符串 | error | `models-validation-failed` |
| `base_url` 非空 | 空字符串 | error | `models-validation-failed` |
| `api_key` 非空 | 空字符串 | error | `models-validation-failed` |
| `default` 必须指向现存 `name` | 引用不存在的 name | error | `models-validation-failed` |
| 未知顶层字段 / 单 profile 内字段 | 多余 key | warn | `models-validation-failed` |

**`error` 级阻断命令；`warn` 级只 `[WARN]` 不阻断**——与 `manifest.validate` 的约定一致（`doc/design.md` §2.3、§4.2）。

**`model_id` 不在白名单里不阻断**：与 v1 不同——本特性下 model_id 是 provider 端字符串，CLI 不维护白名单（白名单是 Anthropic SDK / Claude Code 的事）。`.workspace.toml` 里的 `manifest.KNOWN_MODELS` 检查**仍保留**用于既有字段（详见 §5.2）。

### 1.5 写盘时机

| 触发 | 写盘逻辑 |
| --- | --- |
| `llmw models add` | 解析参数 → 调 getpass 读 api_key → load + 校验现有 → append → atomic write + reparse |
| `llmw models remove <name>` | 读 → 删条目；若是 default 则 `default = ""` → atomic write + reparse |
| `llmw models set-default <name>` | 读 → 校验 name 存在 → 改 `default` → atomic write + reparse |
| `llmw init` | **不**创建 `models.toml`（仅 append 到 `.gitignore`）；首次 `models add` 时按需创建（原子写自动建父目录） |
| `llmw enter` / `list` / `show` / 其它 | 纯读，不写盘 |

**写盘约定**：与 `.workspace.toml` 一致——整个文件 read-modify-write；写盘前走 `atomic_write`（tmp + fsync + rename）；写盘后立刻 `tomllib.loads(content)` 重解析；失败则抛 `internal-state-corruption`（exit 3）。**额外约束**：`tempfile.mkstemp` 默认即 0600 权限，`os.replace` 保留源文件 mode，故 `models.toml` 创建后自动 0600——这是 secret 的基础防护（与 `.gitignore` 是双重保险，详见 §6）。

### 1.6 schema_version 演进

**v1 不引入 schema_version**——文件结构足够简单（顶层 `default` + 单层 `[[models]]` 表），后续若破坏式升级再加。当前规则：**任何顶层未知字段 = warn 但不阻断**。

---

## §2 命令面

### 2.1 新增 `llmw models`

四 action 子命令，复用一个 `models` 子 parser（与 `llmw config <name> <action>` 风格相似）：

```text
llmw models add                   # 交互式新增 profile
llmw models add --name <X> --model-id <Y> --base-url <Z>   # 非交互（api_key 仍走 stdin prompt）
    [--set-default]               # 同时把 default 指向新 profile
llmw models list                  # 列出所有 profile（人类可读表格）
llmw models list --json           # 结构化输出（不含 api_key）
llmw models remove <name>         # 删 profile；若是 default 则清空 default
    [--yes]                       # 跳过确认
llmw models set-default <name>    # 设 default 为指定 profile
llmw models set-default --clear   # 清空 default（default = ""）
```

### 2.2 `llmw models add`

**完整流程**：

1. 校验 `--name`（如给）kebab-case + 不与现有冲突
2. 校验 `--model-id` / `--base-url` 非空（如给）
3. **api_key 一律经 stdin 读**：`getpass.getpass("api_key: ")`——不接 CLI 参数，不进 argv history
4. 若未给 `--name` 等参数则交互式 prompt（仅 TTY；非 TTY 报错 `models-validation-failed`）
5. 若给 `--set-default`，把 default 指向新 profile（default 旧值丢失）
6. atomic write + reparse

| 维度 | 内容 |
| --- | --- |
| 失败条件 | (a) workspace 未 init → 1；(b) name 冲突 → 1；(c) 缺字段 → 1；(d) 非 TTY 且缺必填参数 → 1 |
| 副作用 | 写 `models.toml`（含 secret） |
| 退出码 | 0 / 1 / 2 / 3 |
| 依赖 | ❌（不依赖 llm-wiki-management） |

### 2.3 `llmw models list`

**默认输出**（人类可读表格，**不显示 api_key**）：

```
NAME                  MODEL_ID             BASE_URL
anthropic-prod        claude-opus-4-8       https://api.anthropic.com
thirdparty-vertex     claude-opus-4-8       https://custom.example.com

default: anthropic-prod
```

**`--json`**：输出 JSON 数组 + 顶层 `default`，**每条 entry 不含 `api_key` 字段**。客户端若需要真值须直读 `models.toml`（且仅为本机进程）。

```json
{
  "default": "anthropic-prod",
  "models": [
    {"name": "anthropic-prod", "model_id": "claude-opus-4-8", "base_url": "..."},
    {"name": "thirdparty-vertex", "model_id": "claude-opus-4-8", "base_url": "..."}
  ]
}
```

| 维度 | 内容 |
| --- | --- |
| 失败条件 | workspace 未 init → 1 |
| 副作用 | 无 |
| 退出码 | 0 / 1 |
| 依赖 | ❌ |

**关键约束**：stdout 与 stderr 任何路径都**不允许**打印 `api_key`。`--debug` 模式下亦不打印 secret，只打"profile X 含 api_key (redacted)"。

### 2.4 `llmw models remove <name>`

**完整流程**：

1. 解析 + 校验 name 存在
2. 若 `--yes` 缺失且 TTY → 确认 prompt：`Remove profile 'X'? [y/N]`
3. 删条目；若 name == default，则 `default = ""`
4. atomic write + reparse

| 维度 | 内容 |
| --- | --- |
| 失败条件 | (a) workspace 未 init → 1；(b) name 不存在 → 1；(c) `--yes` 缺失且非 TTY → 1 |
| 副作用 | 写 `models.toml` |
| 退出码 | 0 / 1 / 2 / 3 |
| 依赖 | ❌ |

### 2.5 `llmw models set-default <name|--clear>`

`<name>`：把 default 指向该 profile；profile 必须存在。
`--clear`：把 default 置为 `""`（"未设 default" 状态；`enter` 将因此拒绝启动）。

| 维度 | 内容 |
| --- | --- |
| 失败条件 | (a) workspace 未 init → 1；(b) name 不存在 → 1 |
| 副作用 | 写 `models.toml` |
| 退出码 | 0 / 1 / 2 / 3 |
| 依赖 | ❌ |

### 2.6 `llmw enter <name>` 改动

**新签名**：

```text
llmw enter <name>
    [--profile <NAME>]              # 新增；显式选 profile
    [--claude-md-check=warn|fail|skip]
    [--dry-run]
# --model <ID>  被移除
```

**profile 解析优先级**（与 `--workspace` / `--default-model` 风格一致）：

| 优先级 | 来源 | 备注 |
| --- | --- | --- |
| 1 | `--profile <NAME>` | 显式 CLI 标志；不存在 → 立即报错 exit 1 |
| 2 | 交互式菜单（仅 `sys.stdin.isatty()`） | 列出所有 profile 名 + `default: <X>` 标注；用户输入编号或名；非 TTY 时跳过本步 |
| 3 | `models.toml` 的 `default` | 非空时使用 |
| 4 | — | **无 default** + 非 TTY / Ctrl-C → **拒绝启动**：emit error `no-default-model`，退出码 1 |

**为什么交互菜单放第 2 级而不是"error 前最后一次确认"？** 与 spec §3.0.1"workspace 解析"一致——隐式但有 fallback；菜单比直接拒绝更友好。

**spawn 改动**：

```python
cmd = ["claude"]
cmd += ["--model", profile.model_id]
cmd += ["--add-dir", str(root), "--add-dir", str(wiki_root)]
cmd += ["--system-prompt", prompt]

# env 注入（user-invisible；不进 stdout）
proc_env = os.environ.copy()
proc_env["ANTHROPIC_BASE_URL"] = profile.base_url   # 占位名：实现时核对 Claude Code / Anthropic SDK 的环境变量名
proc_env["ANTHROPIC_AUTH_TOKEN"] = profile.api_key  # 占位名：同上

proc = subprocess.run(cmd, cwd=str(wiki_root), env=proc_env, check=False)
```

**占位说明**：`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` 是 Claude Code / Anthropic SDK 当前惯用的环境变量名；**实现阶段需 verify**（与 `doc/design.md` §3.7"前提"风格一致）。若变量名错误，`enter --dry-run` 可观察子进程实际接收的 env 而定位。

| 维度 | 内容 |
| --- | --- |
| 失败条件 | (a) wiki 不存在 → 1；(b) `models.toml` 缺失或解析失败 → 2；(c) profile 解析到第 4 步仍无结果 → 1 (`no-default-model`)；(d) `claude` 不在 PATH → 2 |
| 副作用 | spawn 子进程；无本地文件改动 |
| 退出码 | 0 / 1 / 2 / 3 / 跟随 claude |
| 依赖 | △ 检测 llm-wiki-management（与 v1 相同——保留 warn 不 fail） |

### 2.7 命令总览更新（叠加到 v1 §3.8）

| 命令 | 依赖 llm-wiki-management | 副作用 |
| --- | --- | --- |
| `init` | ❌ | 创建 `.workspace.toml` + `CLAUDE.md` + append `.gitignore` |
| `list` | ❌ | 无 |
| `add` | ✅ 必需 | 调 setup_wiki.py + 写 manifest |
| `remove` | ❌ | 改 manifest（`--purge` 加删目录） |
| `show` | △ 可选 | 无 |
| `config` | ❌ | 改 manifest |
| **`models add`** | ❌ | **写 `models.toml`（含 secret）** |
| **`models list`** | ❌ | **无** |
| **`models remove`** | ❌ | **写 `models.toml`** |
| **`models set-default`** | ❌ | **写 `models.toml`** |
| `enter` | △ 检测，缺失 warn | spawn claude 子进程（**env 注入 profile**） |

---

## §3 模块边界

### 3.1 与 v1 spec §1.5 的关系

完全沿用四层模型 + DAG 约束（`doc/design.md` §1.5），**不引入新的依赖环**。具体增改：

| 模块 | 改动 |
| --- | --- |
| `wiki_workspace/models.py` | **新增**——纯叶子模块（镜像 `manifest.py`） |
| `wiki_workspace/commands/models_cmd.py` | **新增**——`run(args)` 分派 4 个 action |
| `wiki_workspace/workspace.py` | **扩展**——加 `models_file_path` / `load_models` / `save_models` / `dump_models_toml` |
| `wiki_workspace/cli.py` | **扩展**——加 `models` 子 parser；`enter` 的 `--model` 替换为 `--profile` |
| `wiki_workspace/commands/_common.py` | **扩展**——加 `load_models(args)`（与 `load_manifest(args)` 对称） |
| `wiki_workspace/commands/enter_cmd.py` | **扩展**——加 profile 解析 / 菜单 / env 注入 / 拒绝逻辑 |
| `wiki_workspace/commands/init_cmd.py` | **扩展**——append `models.toml` 到 `.gitignore` |
| `wiki_workspace/manifest.py` | **不变** |
| `wiki_workspace/errors.py` | **不变**——新错误 category 是自由字符串，沿用既有约定 |
| `wiki_workspace/_compat.py` | **不变** |

### 3.2 `models.py`（新）——纯叶子模块

完全镜像 `manifest.py` 的结构与约定：

```python
class ModelEntry:
    def __init__(self, name, model_id, base_url, api_key): ...

class ModelRegistry:
    """default + Dict[str, ModelEntry]"""
    def __init__(self, default, models): ...

def parse(text): ...         # tomllib.loads → ModelRegistry
def validate(reg): ...        # 返回 list[Issue]；error 阻断 / warn 不阻断
def serialize(reg): ...       # 经 workspace.dump_models_toml（惰性 import，保持 models 无环）
```

**约束**：`models.py` 不 import `errors`、不 import `workspace`（顶部），与 `manifest.py` 一致。

### 3.3 `workspace.py` 的扩展

新增 4 个函数，与 v1 的 `manifest_path` / `load_toml` / `dump_toml` / `save_manifest` 对称：

```python
def models_filename(): return "models.toml"
def models_file_path(root): return Path(root) / models_filename()

def load_models(root): ...        # 读 + 解析；缺失文件返回空 registry（default="", models={}），不报错
def save_models(root, registry): ...  # atomic write + reparse 自检 → 失败抛 internal-state-corruption
def dump_models_toml(data): ...    # schema 专属序列化器（与 dump_toml 同模式；安全因 schema 全受控）
```

**为什么 `load_models` 缺失文件 = 空 registry？** `models.toml` 是按需创建（init 时不创建）。与 `load_manifest` 缺失文件 → 报错 `workspace-not-initialized` 行为不同——前者"workspace 已 init 但 model 配置不存在"是合法状态（用户尚未配置）。

### 3.4 依赖 DAG（更新）

```
errors ← workspace ← {commands, manifest.serialize, models.serialize}
        ↑ （manifest.parse 不 import workspace）
errors ← commands ← cli
manifest.parse / manifest.validate ← commands（_common.load_manifest）
models.parse / models.validate ← commands（_common.load_models）
_compat ← commands（add / show / enter 软探测）
```

**关键不变量**：`manifest.py` / `models.py` 都是纯叶子（顶部仅 stdlib），互不依赖；`workspace.py` 是中间层；`commands/*` 在顶层并 import `errors` / `workspace` / `manifest` / `models` / `_compat`。

---

## §4 错误、退出码、日志

### 4.1 新错误 category（叠加到 v1 §4.2）

| category | 触发场景 | 退出码 | 严重度 |
| --- | --- | --- | --- |
| `unknown-profile` | `enter --profile <X>`，X 不存在 | 1 | error |
| `model-already-exists` | `models add --name <X>`，X 已存在 | 1 | error |
| `model-not-found` | `models remove <X>` / `models set-default <X>`，X 不存在 | 1 | error |
| `no-default-model` | `enter` 解析到第 4 步仍无 profile 可用 | 1 | error |
| `models-file-parse-failed` | `models.toml` TOML 语法错误 | 2 | error |
| `models-validation-failed` | `models validate` 阻断（name 冲突 / 字段缺失 / default 引用不存在 / 非 TTY 缺参） | 1 | error |

**约定**：category 是稳定的机器契约（kebab-case），保持英文；`message` / `hint` 一律中文。

**复用既有 category**：

- `workspace-not-initialized`——`models *` 在 workspace 未 init 时复用（exit 1）
- `internal-state-corruption`——`save_models` 重解析失败时复用（exit 3）

### 4.2 退出码总览（叠加到 v1 §4.1）

不变。**新增触发场景**：

| 退出码 | 新触发 |
| --- | --- |
| 1 | `unknown-profile` / `model-already-exists` / `model-not-found` / `no-default-model` / `models-validation-failed` |
| 2 | `models-file-parse-failed` |
| 3 | `save_models` atomic-write 后 reparse 失败（既有 `internal-state-corruption` 路径） |

### 4.3 stdout vs stderr

完全沿用 v1 §4.4。新约束：**任何输出（stdout / stderr / 错误 message / `--json` 响应 / `--debug` 日志）都不打印 `api_key` 明文**。实现上由两类机制兜底：

1. `models list` / `models list --json`：序列化时跳过 `api_key` 字段
2. `--debug` 路径：profile 引用时打 `name=X model_id=Y base_url=Z api_key=***`（遮 8 字符 + ellipsis）

### 4.4 日志

完全沿用 v1 §4.5。新增消息文案（占位，落地时由实现者润色）：

- `[INFO] 已添加 profile '<X>'`（models add 成功）
- `[INFO] 已删除 profile '<X>'`（models remove 成功）
- `[INFO] default 已指向 '<X>'` / `[INFO] default 已清空`（set-default 成功 / clear）

---

## §5 测试策略

### 5.1 测试栈（沿用 v1 §5.1）

pytest + `unittest.mock` + `tmp_path` + `pytest-cov`；CI 矩阵不变。

### 5.2 新测试文件

```
tests/
├── test_models.py                  # 新（100% 覆盖目标）
├── test_models_cmd.py              # 新
├── test_workspace.py               # 扩展（dump_models_toml + load/save round-trip）
├── test_common.py                  # 扩展（load_models helper）
├── test_enter_cmd.py               # 扩展（profile 解析 / 菜单 / env 注入 / 拒绝）
├── test_init_cmd.py                # 扩展（.gitignore append + 无 git 跳过）
├── test_cli.py                     # 扩展（models 子 parser + enter --profile）
└── test_e2e_smoke.py               # 扩展（init → models add → enter --profile --dry-run leg）
```

### 5.3 关键测试用例清单

**models.py（必须 100% 覆盖）**：

- `parse`：合法 / `default` 缺失（→ `""`）/ 空 `models` 数组 / 缺字段（→ validate 阻断）/ 重复 name（→ validate 阻断）/ `default` 引用不存在（→ validate 阻断）/ 未知顶层字段（→ validate warn）
- `serialize`：round-trip（parse → serialize → parse，值相等）/ 空 registry 序列化
- `validate`：error / warn 级别区分；与 `manifest.validate` 同一份 `Issue` 类

**models_cmd.py（每 action 5-8 个 case）**：

- `add`：全交互 / 全参数 / `--set-default` / name 冲突 / 非 TTY 缺参（→ 报错）/ `getpass` 模拟
- `list`：表格输出 / `--json` / 表格中**绝不**含 `api_key` / `--json` 输出**绝不**含 `api_key` / 无 profile（空表 + `default: (unset)`）
- `remove`：存在 / 不存在 / 默认 profile 被删（→ `default = ""`）/ `--yes` / 非 TTY 缺 `--yes`（→ 报错）
- `set-default`：合法 / 不存在 / `--clear`

**workspace.py 扩展**：

- `dump_models_toml`：round-trip / 空 registry / 多个 profile 顺序保持 / api_key 内的引号 / 反斜杠转义
- `load_models`：文件存在 / 文件缺失（→ 空 registry，不报错）
- `save_models`：atomic / reparse 失败（→ 抛 `internal-state-corruption`）/ 权限 0600（断言 stat().st_mode & 0o777 == 0o600）
- `models_file_path`：路径正确

**enter_cmd.py 扩展**：

- `--profile X` 命中：mock `subprocess.run`，断言 cmd 含 `--model X.model_id`、env 含 `ANTHROPIC_BASE_URL=X.base_url` 与 `ANTHROPIC_AUTH_TOKEN=X.api_key`（环境变量名待实现 verify；若变更，断言同步更新）
- `--profile X` 未知：emit `unknown-profile` + exit 1（**不** spawn claude）
- 交互菜单（mock `input()` + `sys.stdin.isatty=True`）：用户选第 1 项 → spawn 时用对应 profile
- 非 TTY 且无 `--profile`：跳过菜单，直接用 default
- 非 TTY 且 default 为空：emit `no-default-model` + exit 1（**不** spawn claude）
- TTY 且 default 为空：mock `input()` 返回空（Ctrl-C 模拟）：emit `no-default-model` + exit 1
- `--dry-run`：打印 cmd + env（env 里 `api_key` 必须 `***`），**不** spawn
- 任意成功 / 失败 / 菜单 / 拒绝路径：**stdout / stderr / 异常消息 / debug 日志里均不出现** `api_key` 明文
- `--debug` + models / enter：stderr `[DEBUG]` 行里 `api_key` 必须以 `***` 出现（profile dump 时按 `name=X model_id=Y base_url=Z api_key=***` 格式）

**init_cmd.py 扩展**（注意：v1 §3.1 中 `init` 在 `.workspace.toml` 已存在时直接拒绝——故 `.gitignore` append 路径只跑一次，但实现仍按幂等写，便于提取的 helper 函数被独立复用 + 测试）：

- workspace 含 `.git/` + `.gitignore` 含 `models.toml` 行：helper 跑完无任何变更（幂等）
- workspace 含 `.git/` + `.gitignore` 不含 `models.toml`：在末尾追加精确一行 `models.toml`，保留其它内容（处理无尾换行）
- workspace 含 `.git/` + 无 `.gitignore`：创建 `.gitignore` 并写入 `models.toml\n`
- workspace 无 `.git/`：helper 直接 return；不创建 `.gitignore`，不报错
- `init` 整体流程：现有 `.workspace.toml` 存在 → 报错 `workspace-already-exists` 退出 1（与 v1 §3.1 一致），不进 gitignore 路径

**cli.py 扩展**：

- `llmw models --help`：列出 4 个 subaction
- `llmw enter --help`：**不含** `--model`，**含** `--profile`
- `llmw models list --json` 走 `--json` 全局 flag

**e2e smoke 扩展**：

```
init → models add (profile "p1") → enter <wiki> --profile p1 --dry-run
```

### 5.4 覆盖率目标

整体 `--cov-fail-under=85`（沿用 v1）。`models.py` 100%（与 `manifest.py` 同档）；`models_cmd.py` 80%+；其它扩展模块保持既有目标。

### 5.5 安全断言（必加）

至少在 `test_models_cmd.py::test_list_redacts_api_key` 与 `test_enter_cmd.py::test_*` 的每个 case 里：

- `capsys.readouterr().out` 不含 `api_key` 明文
- `capsys.readouterr().err` 不含 `api_key` 明文
- mock 异常的 `str(exc)` 不含 `api_key` 明文（profile 在 raise 时若被 repr 出来，必须先 redact）

### 5.6 不测的（沿用 v1 §5.6 + 新增）

| 不测项 | 理由 |
| --- | --- |
| `claude` 子进程真实接收 env 的端到端验证 | 集成测试范围；`enter --dry-run` 即可观察 |
| 模型 ID 是否在 Anthropic 端真实可用 | provider 服务端的事 |
| `getpass` 真终端隐藏 | 跨平台；monkeypatch `getpass.getpass` 即可 |
| Windows 文件权限 0600 | v1 仅 Linux + macOS；Windows 用 ACL 不是 mode bits |

---

## §6 安全：gitignore 与文件权限

### 6.1 `.gitignore` 处理

`init` 在检测到 `<workspace_root>/.git/` 存在时，往 `<workspace_root>/.gitignore` 追加：

```
models.toml
```

**约定**：

- 一行精确为 `models.toml`（无前缀、无注释）
- **幂等**：若 `.gitignore` 已含该行，不重复（用全行匹配而非子串）
- 保留其它既有内容（包括无尾换行的尾行——追加前先确保有换行符）
- `<workspace_root>/.git/` 不存在 → 跳过；不创建 `.gitignore`，不报错
- `models add` 等后续命令**不**再次追加

**为什么不放进顶层 `llm_workspace_cli` 仓的 `.gitignore`？** workspace 是独立仓；models.toml 在每个 workspace 仓内都有，gitignore 必须在 workspace 仓。

### 6.2 文件权限

- `tempfile.mkstemp` 默认权限 0600（仅 owner 可读写）
- `os.replace(tmp, target)` 保留源文件 mode——故 `models.toml` 创建后即 0600
- **不**对既有非 0600 文件做 chmod（尊重用户显式调整；警告但不强制）

### 6.3 防护层级

| 层级 | 防什么 | 不防什么 |
| --- | --- | --- |
| 文件 mode 0600 | 同机其它用户读 | 同机 root / 已获 owner 权的进程 / 备份泄露 |
| `.gitignore` 行 | `git add . && git commit` 误提交 | `git add -f` 强制 / 已存在历史 commit / 第三方工具不读 gitignore |
| 输出 redact | stdout / stderr / 日志泄露 | 内存 dump / 调试器 attach / 子进程 env（api_key 本来就要进子进程——这是设计内） |

**明文**：以上都是降低意外泄露概率的纵深防御，**不替代**用户对机器本身的访问控制。

---

## 附录 A：与 v1 的兼容矩阵

| 既有行为 | 本特性后 |
| --- | --- |
| `workspace.default_model` / `wikis.<name>.model` 字段存在并校验 | 字段保留；`manifest.validate` 继续 warn 未知 model |
| `enter --model <ID>` 显式 ID | **移除**——统一改用 `--profile <NAME>` |
| `add --model <ID>` 把 ID 写进 manifest | 保留（不影响）；用户后续可改用 profile |
| `config set <name> model <ID>` | 保留；与 profile 不冲突，profile 用于 `enter` |
| `list` / `show` 输出 MODEL 列 | 保留（从 manifest 读）；若 workspace 配置了 default profile，可在标题加 `(profile: <X>)` 标注（**可选增强**，非必须） |

## 附录 B：风险与未决项

| 风险 / 未决项 | 影响 | 缓解 |
| --- | --- | --- |
| Claude Code / Anthropic SDK 的环境变量名不一定是 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` | 子进程拿不到 profile | 实现时跑 `claude --help` + 翻 Anthropic SDK 源码确认；`enter --dry-run` 暴露 env 便于诊断 |
| `models add` 在非 TTY 环境下无法工作（getpass 失败 / 交互 prompt 失败） | CI / 脚本无法配 profile | `models add` 已要求**所有参数必填**才不靠 prompt；非 TTY 缺任何参数 → 报错退出 1。若 CI 真要自动化：实现一个薄封装脚本（用 `wiki_workspace.workspace.save_models` 直接写），不进 `llmw` 主 CLI——这是**用户自选**的扩展点，不在 `llmw` 范围。**故意不**为 api_key 加环境变量兜底入口：与用户"所有配置不依赖环境变量，全部以配置文件的形式存储"的指令相悖。 |
| 用户在同一 workspace 多次 `init` | `.gitignore` 重复追加 | 幂等检查（§6.1） |
| 跨 workspace profile 共享需求 | 用户可能在多个 workspace 配同样的 profile | 不在 v1 范围；用户可手工 `cp models.toml` |
| `models.toml` 损坏但 manifest 完好 | `enter` 解析失败 | exit 2 + 提示手动修；与 manifest-parse-failed 同档处理 |
| `models add` 时 TTY 不可用 + 用户已 `--set-default` 但新 profile 校验失败 | 旧 default 丢失？ | 顺序：先 append + 校验通过后才改 default；新 entry 校验失败则**不**改 default；实现时把 default 改动放在 atomic write 之前的状态合并里 |