# llmw — 模型配置注册表（Models Registry）+ Per-Wiki Profile Binding 设计文档

| 字段 | 值 |
| --- | --- |
| 版本 | 0.1（设计稿，待实现后随 v2 演进） |
| 日期 | 2026-06-27 |
| 状态 | 草案，5 节均已分节确认；profile.toml 扩展已合并入同一文档；待实现 + 自测 |
| 仓库 | `git@github.com:yzr95924/llm_workspace_cli.git` |
| 关联设计 | `doc/design.md`（v1 CLI 设计；本文档**叠加**于其上，并**清理**了部分 v1 字段） |
| 关联 skill | `llm-wiki-management`（与本文档无关） |

## 背景与目标

### 痛点

`llmw enter <name>` 目前把模型选择限定在 `.workspace.toml` 的 `workspace.default_model` / `wikis.<name>.model` 字段里（`doc/design.md` §2.2、§3.7）。这两个字段只是字符串 ID（如 `claude-opus-4-8`），用户实际诉求里**远不止于此**：

1. **不同 provider 用同一个 model ID**：`claude-opus-4-8` 既可走 Anthropic 官方，也可走第三方代理 / 自部署网关——仅靠字符串无法区分。
2. **不同 endpoint 需要不同 base_url + api_key**：当前没有任何机制记录或切换；用户只能手工 `export` + 在 wiki 上下文里临时切换 shell 变量。
3. **api_key 散落**：常见做法是写在 `.env` / shell rcfile / `~/.netrc`——不在仓库控制下，容易泄露到 git 或日志。
4. **无 per-wiki profile 绑定**：用户可能在多个 wiki 用不同 provider（如个人 wiki 用 Anthropic 官方、项目 wiki 用第三方代理），当前只能在每次 enter 前手工切换——既易错也不便。

### 目标

引入两个文件，分两层组织：

- **workspace 级**：`models.toml`——集中管理所有"模型 + provider"的完整配置档（profile）。
- **per-wiki 级**：`<wiki>/profile.toml`——每个 wiki 绑定一个 profile 名；后续可扩展（如 temperature、custom_prompt）。

`llmw enter` 的模型选择从"字符串 ID"升级为"读 profile.toml → workspace default"的两层解析。profile 绑定走 `llmw wiki config` 交互式命令（无 bind/unbind 单独命令；future 字段自然加入）。

具体行为：

- workspace 维护 0..N 个 profile；每个 profile 含 `name` / `model_id` / `base_url` / `api_key` 四项（**全部必填**）
- workspace 有一个 **default profile**（指向某个 name）——`models.toml` 的 `default` 字段
- 每个 wiki 可选地把一个 profile 绑定到自己——`<wiki>/profile.toml` 的 `model` 字段
- `enter` 解析：profile.toml 命中 → `[INFO] Using profile: X` + 启动；未命中 → `[WARN] Using workspace default: X` + 启动；两者皆空 → `error wiki-not-bound` 拒绝启动
- 两个配置文件均被 gitignore 屏蔽（避免 secret / 误提交）
- api_key 由 CLI 通过子进程 env 注入给 `claude`，**永不出现在任何输出里**

### 非目标

- **不**做 profile 加密（filesystem 权限 = 0600 即可；用户自行管机器访问）
- **不**做 profile 共享 / 远程同步
- **不**保留 v1 `.workspace.toml` 的 `workspace.default_model` / `wikis.<name>.model` 字段——直接删除（v1 未发布，无 migration）
- **不**做运行时 profile override（`enter --profile` 已被删除）——profile 绑定是 wiki 级配置，固定直至用 `wiki config` 修改
- **不**做 per-wiki credential 隔离（所有 profile credentials 集中于 `models.toml`；profile.toml 仅存名字引用）

## 设计原则（与 v1 spec 一致；新增条目加粗）

1. **CLI 是给人用的入口**：本特性**新增**到 CLI 入口；CLI 仍**不**做 LLM 推理
2. **`llmw` 与 `llm-wiki-management` 解耦**：与本文档无关
3. **配置文件是 SSOT**：**新增**——`models.toml`（workspace 级 profile SSOT）+ `profile.toml`（per-wiki 绑定 SSOT），与 `.workspace.toml` 并列
4. **subprocess > import**：跨仓 / 跨包调脚本一律 `subprocess.run`
5. **原子写盘**：**新增**——`models.toml` / `profile.toml` 同样走 atomic write + reparse 自检
6. **secret 不上 stdout**：**新增**——`api_key` 一律经 env 注入；list / show / 错误消息全部 redact
7. **per-wiki 局部配置走单独命令**：**新增**——`llmw wiki config` 是 per-wiki 局部配置（目前含 profile 绑定；后续扩 temperature 等）的统一入口；不污染 `llmw config`（后者专管 .workspace.toml 字段）

---

## §1 数据模型

### 1.1 `models.toml` 位置

`<workspace_root>/models.toml`——与 `.workspace.toml` 同级；**不进 git**（详见 §6.1）。

### 1.2 `models.toml` schema

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

### 1.3 `models.toml` 字段表

| 字段 | 层级 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `default` | top | string | ❌ | `""` | 当前 workspace 默认 profile 的 `name`；空串 = 未设 default |
| `[[models]]` | array of tables | array | ✅（可空数组） | — | profile 数组；空数组合法（"暂未配置"） |
| `name` | `[[models]]` | string | ✅ | — | profile 名；kebab-case + workspace 内唯一 |
| `model_id` | `[[models]]` | string | ✅ | — | 传给 Claude 的 `--model` 值（如 `claude-opus-4-8`） |
| `base_url` | `[[models]]` | string | ✅ | — | provider endpoint；由 `enter` 注入给 claude 子进程 |
| `api_key` | `[[models]]` | string | ✅ | — | provider 凭证；由 `enter` 注入给 claude 子进程 |

**为什么四字段全部必填？** "只配 model_id 别名"的方案不够——base_url + api_key 缺失时该 profile 实际不可用；强制必填把"半成品"挡在保存之前。

### 1.4 `models.toml` 校验规则

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

**`model_id` 不在白名单里不阻断**：CLI 不维护白名单（白名单是 Anthropic SDK / Claude Code 的事）。注意：v1 `manifest.KNOWN_MODELS` 也被一并删除（详见 §1.8），所以本特性后 CLI 完全不检查 model_id 白名单。

### 1.5 `models.toml` 写盘时机

| 触发 | 写盘逻辑 |
| --- | --- |
| `llmw models add` | 解析参数 → 调 getpass 读 api_key → load + 校验现有 → append → atomic write + reparse |
| `llmw models remove <name>` | 读 → 删条目；若是 default 则 `default = ""` → atomic write + reparse |
| `llmw models set-default <name>` | 读 → 校验 name 存在 → 改 `default` → atomic write + reparse |
| `llmw init` | **不**创建 `models.toml`（仅 append 到 workspace `.gitignore`）；首次 `models add` 时按需创建（原子写自动建父目录） |
| `llmw enter` / `list` / `show` / `wiki config` / 其它 | 纯读，不写盘 |

**写盘约定**：与 `.workspace.toml` 一致——整个文件 read-modify-write；写盘前走 `atomic_write`（tmp + fsync + rename）；写盘后立刻 `tomllib.loads(content)` 重解析；失败则抛 `internal-state-corruption`（exit 3）。**额外约束**：`tempfile.mkstemp` 默认即 0600 权限，`os.replace` 保留源文件 mode，故 `models.toml` 创建后自动 0600——这是 secret 的基础防护（与 `.gitignore` 是双重保险，详见 §6）。

### 1.6 `models.toml` schema_version 演进

**v1 不引入 schema_version**——文件结构足够简单（顶层 `default` + 单层 `[[models]]` 表），后续若破坏式升级再加。当前规则：**任何顶层未知字段 = warn 但不阻断**。

### 1.7 `profile.toml`（per-wiki 绑定）—— 新增

**位置**：`<wiki_root>/profile.toml`——每个 wiki 子目录下，与 wiki 自己的 `.gitignore` 同级；**不进** wiki 的 git 历史（详见 §6.1）。

**schema（v1 — 最简版）**：

```toml
model = "anthropic-prod"
```

**字段表**：

| 字段 | 层级 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `model` | top | string | ✅ | 引用的 **profile 名**（models.toml 中某个 `[[models]].name`）；**不是** model_id |

**为什么键名是 `model` 而不是 `profile`？** profile 是概念（一份完整 provider 配置），model 是字段（"这个 wiki 用哪个 model"）。`profile.toml` 整体是 wiki 的 profile 配置块，里面第一个字段叫 `model`（与"profile 名"建立绑定关系）。后续扩展字段（`temperature`、`custom_prompt` 等）与 `model` 平级——`llmw wiki config` 提示序列会自动扩展。

**校验规则**：

| 不变量 | 触发 | 严重度 | category |
| --- | --- | --- | --- |
| TOML 语法正确 | 解析失败 | error (exit 2) | `profile-file-parse-failed` |
| `model` 键存在 | 文件存在但缺 `model` 键 | error | `profile-validation-failed` |
| `model` 非空字符串 | `model = ""` | error | `profile-validation-failed` |
| `model` 引用现存的 profile 名 | models.toml 中无此 name | error | `profile-validation-failed` |
| 未知顶层字段 | 多余 key | warn | `profile-validation-failed` |

**校验时机**：每次 `enter` 读 profile.toml 时跑一次；`wiki config` 写入时也校验一次（绑定到不存在的 profile 名 → 重提示同字段，不前进）。

**写盘时机**：

| 触发 | 写盘逻辑 |
| --- | --- |
| `llmw wiki config` | 交互式收集字段 → 校验全部通过 → atomic write + reparse |
| `llmw add` | **不**创建 profile.toml（仅 append `profile.toml` 到 wiki 的 `.gitignore`）；profile 绑定由用户后续 `wiki config` 设置 |
| `llmw enter` / `list` / `show` / 其它 | 纯读，不写盘 |

**`profile.toml` 文件权限**：0600（与 models.toml 同档——profile 不含 secret 但 wiki 局部配置仍按 0600 防御性保护）。

### 1.8 `.workspace.toml` 清理（删除 v1 字段）

按"完全删除 model 字段"决策：

**移除的字段**：

- `[workspace].default_model`——删除
- `[wikis.<name>].model`——删除

**`manifest.py` 同步清理**：

| 删除 | 说明 |
| --- | --- |
| `WikiEntry.model` 属性 | wiki 不再存 model_id 字符串 |
| `WikiEntry.effective_model()` 方法 | 无 caller |
| `Manifest.default_model` 属性 | workspace 不再有 default_model 字段 |
| `KNOWN_MODELS` 常量 | 无 caller |
| `SETTABLE_KEYS["model"]` | `config set model` 不再允许 |

**`workspace.dump_toml` 同步清理**：不再写 `default_model` / wiki `model` 字段。

**`manifest.parse` 同步清理**：不再读这两个字段（遗留字段被静默忽略——tomllib 解析时多余 key 不会报错，且 validate 不检查）。

**CLI 同步清理**：

| 命令 / flag | 处置 |
| --- | --- |
| `llmw init --default-model <ID>` | 删除 flag |
| `llmw add --model <ID>` | 删除 flag |
| `llmw add --profile <P>` | 删除 flag（profile 绑定走 `wiki config`） |
| `llmw enter --model <ID>` | 删除 flag |
| `llmw enter --profile <NAME>` | 删除 flag（profile 走 `wiki config`；`enter` 不再支持运行时 override） |
| `llmw config set <wiki> model <ID>` / `unset model` | 拒绝——`SETTABLE_KEYS` 不再含 `model` |

**Migration**：**无**。v1 未发布（commit history 显示项目仍在 active 开发），现有 workspace.toml 如含遗留字段将被静默忽略；不报错、不自动删、不写 `llmw migrate` 命令。

---

## §2 命令面

### 2.1 `llmw models` 子命令组（不变）

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

### 2.6 `llmw wiki config --name=<wiki>` —— 新增（交互式）

**完整签名**：

```text
llmw wiki config --name <wiki>     # 交互式配置该 wiki 的 profile.toml
llmw wiki config --name <wiki> --show   # 只显示当前 profile.toml 内容，不进入交互
```

**交互式流程**（默认）：

```
[INFO] Wiki: <wiki>
[INFO] Current profile.toml:
       model = "anthropic-prod"   (← 当前值；首次配置则显示 "(unset)")

Configure each field (press Enter to keep current value):
  model [<profile name> or 'clear' to unset]: ___
```

- 输入 `clear` → 把 `model` 字段标记为"unset"（**实现选择**：删除 profile.toml 文件 vs 留空——见 §6.3 实现细节；推荐**删除文件**避免空文件歧义）
- 输入 `q` / Ctrl-C → 不保存退出（profile.toml 完全不动）
- 校验失败（profile 名不存在等）→ 重提示同一字段，不前进
- 全部字段通过校验 → atomic write + reparse + 打印成功

**v1 字段范围**：仅 `model`（profile 名引用）。未来字段（`temperature`、`custom_prompt` 等）自然加入提示序列——`wiki config` 是 per-wiki 局部配置的**统一入口**，无需新命令。

**`--show`**：仅打印当前 profile.toml 的 `model = "X"`（或 "(unset)"），不进入交互。便于脚本快速查询。

| 维度 | 内容 |
| --- | --- |
| 失败条件 | (a) workspace 未 init → 1；(b) wiki 不存在 → 1；(c) 非 TTY 且无 `--show` → 1；(d) `models.toml` 缺失或解析失败 → 2（无法校验 profile 名引用） |
| 副作用 | 交互式确认后写 `profile.toml`；`--show` 模式无副作用 |
| 退出码 | 0 / 1 / 2 / 3 |
| 依赖 | ❌（不依赖 llm-wiki-management） |

**为什么不放成多个子命令（`wiki bind/unbind/show`）？** `wiki config` 是 per-wiki 局部配置的**通用入口**——future 字段（temperature 等）只需在交互提示序列加一行，无需新命令；命令面保持精简。

### 2.7 `llmw enter <name>` —— 彻底简化

**新签名**：

```text
llmw enter <name>
    [--claude-md-check=warn|fail|skip]
    [--dry-run]
# --model <ID>    被移除
# --profile <NAME> 被移除
```

**profile 解析流程**（无 CLI override、无菜单，纯静态）：

```
profile.toml 存在?
  YES → 读 `model` 字段:
    X 引用现存 profile:
      [INFO] Using profile: X
      进入 claude（env 注入 X 的 base_url + api_key）
    X 引用不存在 / `model` 键缺失 / `model = ""`:
      error profile-validation-failed, exit 1
  NO → 读 models.toml:
    default = "Y" 且 Y 存在:
      [WARN] No profile bound for '<wiki>'; using workspace default: Y
      进入 claude（env 注入 Y）
    default = "" / 文件缺失:
      error wiki-not-bound, exit 1
```

**关键变化**：

- 不再接受 `--profile` flag（profile 绑定走 `wiki config`，`enter` 不再支持运行时 override）
- 不再有交互式菜单（profile 是 wiki 级固定配置，不应在 launch 时改）
- 新错误 category `wiki-not-bound` 替换之前的 `no-default-model`（语义更准确——"wiki 未绑定任何 profile 也无 fallback"）
- `[INFO]` / `[WARN]` 用 `errors.emit_info` / `errors.emit_warn`（即 stderr）；stdout 仍只承载最终结果数据

**spawn 代码**：

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
| 失败条件 | (a) wiki 不存在 → 1；(b) `models.toml` / `profile.toml` 解析失败 → 2；(c) profile.toml 引用不存在 / `wiki-not-bound` → 1；(d) `claude` 不在 PATH → 2 |
| 副作用 | spawn 子进程；无本地文件改动 |
| 退出码 | 0 / 1 / 2 / 3 / 跟随 claude |
| 依赖 | △ 检测 llm-wiki-management（与 v1 相同——保留 warn 不 fail） |

### 2.8 命令总览更新（叠加到 v1 §3.8）

| 命令 | 依赖 llm-wiki-management | 副作用 |
| --- | --- | --- |
| `init` | ❌ | 创建 `.workspace.toml`（无 model 字段）+ `CLAUDE.md` + append workspace `.gitignore` |
| `list` | ❌ | 无 |
| `add` | ✅ 必需 | 调 setup_wiki.py + 写 manifest + append wiki `.gitignore` |
| `remove` | ❌ | 改 manifest（`--purge` 加删目录） |
| `show` | △ 可选 | 无 |
| `config` | ❌ | 改 manifest（`model` key 不再可 set） |
| `models add` | ❌ | 写 `models.toml`（含 secret） |
| `models list` | ❌ | 无 |
| `models remove` | ❌ | 写 `models.toml` |
| `models set-default` | ❌ | 写 `models.toml` |
| **`wiki config`** | ❌ | **写 `profile.toml`** |
| `enter` | △ 检测，缺失 warn | spawn claude 子进程（**env 注入 profile；echo/warn**） |

---

## §3 模块边界

### 3.1 与 v1 spec §1.5 的关系

完全沿用四层模型 + DAG 约束（`doc/design.md` §1.5），**不引入新的依赖环**。具体增改：

| 模块 | 改动 |
| --- | --- |
| `wiki_workspace/models.py` | **新增**——纯叶子模块（镜像 `manifest.py`） |
| `wiki_workspace/profile.py` | **新增**——纯叶子模块（镜像 `models.py` / `manifest.py`） |
| `wiki_workspace/commands/models_cmd.py` | **新增**——`run(args)` 分派 4 个 action |
| `wiki_workspace/commands/wiki_config_cmd.py` | **新增**——`run(args)` 实现 `llmw wiki config` 交互式 |
| `wiki_workspace/workspace.py` | **扩展**——加 `models_file_path` / `load_models` / `save_models` / `dump_models_toml` + `profile_path` / `load_profile` / `save_profile` / `dump_profile_toml` |
| `wiki_workspace/cli.py` | **扩展**——加 `models` / `wiki` 子 parser；移除 `--model` / `--default-model` / `--profile` |
| `wiki_workspace/commands/_common.py` | **扩展**——加 `load_models(args)` + `load_profile(wiki_root)`（与 `load_manifest(args)` 对称） |
| `wiki_workspace/commands/enter_cmd.py` | **重写** profile 解析逻辑；实现 echo / warn / refuse 三路径 |
| `wiki_workspace/commands/add_cmd.py` | **清理 + 扩展**——移除 `--model` / `--profile` flag；**新增**：wiki 创建后 append `profile.toml` 到 wiki 的 `.gitignore`（幂等） |
| `wiki_workspace/commands/init_cmd.py` | **清理 + 扩展**——移除 `default_model` arg；append `models.toml` 到 workspace `.gitignore` |
| `wiki_workspace/commands/config_cmd.py` | **清理**——`SETTABLE_KEYS` 不再含 `"model"` |
| `wiki_workspace/manifest.py` | **清理**——删除 `WikiEntry.model` / `effective_model` / `Manifest.default_model` / `KNOWN_MODELS` / `SETTABLE_KEYS["model"]`；`parse` / `validate` / `to_dict` 同步 |
| `wiki_workspace/errors.py` | **不变**——新错误 category 是自由字符串，沿用既有约定 |
| `wiki_workspace/_compat.py` | **不变** |

### 3.2 `models.py` / `profile.py`（新）—— 纯叶子模块

完全镜像 `manifest.py` 的结构与约定：

```python
# models.py
class ModelEntry:
    def __init__(self, name, model_id, base_url, api_key): ...

class ModelRegistry:
    """default + Dict[str, ModelEntry]"""
    def __init__(self, default, models): ...

def parse(text): ...         # tomllib.loads → ModelRegistry
def validate(reg): ...        # 返回 list[Issue]；error 阻断 / warn 不阻断
def serialize(reg): ...       # 经 workspace.dump_models_toml（惰性 import，保持 models 无环）
```

```python
# profile.py
class Profile:
    """per-wiki profile 绑定；v1 仅 model 一个字段"""
    def __init__(self, model): ...        # model: str（profile 名）

def parse(text): ...         # tomllib.loads → Profile（缺 model 键 → raise）
def validate(profile, models_registry): ...  # 校验 model 引用现存 profile 名
def serialize(profile): ...  # 经 workspace.dump_profile_toml（惰性 import）
```

**约束**：`models.py` / `profile.py` 都**不** import `errors`、**不** import `workspace`（顶部），与 `manifest.py` 一致。`profile.validate` 静态依赖 models 模块的 `ModelRegistry` 类型——但 import 在函数体内惰性发生，保持顶部 import 表干净。

### 3.3 `workspace.py` 的扩展

新增 8 个函数，与 v1 的 `manifest_path` / `load_toml` / `dump_toml` / `save_manifest` 对称：

```python
# models.toml 接口
def models_filename(): return "models.toml"
def models_file_path(root): return Path(root) / models_filename()
def load_models(root): ...        # 读 + 解析；缺失文件返回空 registry（default="", models={}），不报错
def save_models(root, registry): ...  # atomic write + reparse 自检 → 失败抛 internal-state-corruption
def dump_models_toml(data): ...    # schema 专属序列化器（与 dump_toml 同模式；安全因 schema 全受控）

# profile.toml 接口
def profile_filename(): return "profile.toml"
def profile_path(wiki_root): return Path(wiki_root) / profile_filename()
def load_profile(wiki_root): ...    # 读 + 解析；缺失文件返回 None（不是 raise）
def save_profile(wiki_root, profile): ...  # atomic write + reparse 自检
def dump_profile_toml(profile): ...    # schema 专属序列化器
```

**为什么 `load_models` 缺失文件 = 空 registry，`load_profile` 缺失文件 = `None`？** `models.toml` 是 workspace 级（缺失 = "暂未配置"，合法状态）；`profile.toml` 是 per-wiki（缺失 = "该 wiki 未绑定"，由 `enter` 走 workspace default fallback；返回 None 让 caller 区分）。

### 3.4 `manifest.py` 清理（删除 v1 model 字段）

按 §1.8 决策执行。具体删除项：

- `WikiEntry.__init__` 移除 `model=None` 参数
- `WikiEntry.model` 属性 / `effective_model()` 方法删除
- `WikiEntry.to_dict()` 不再 emit `model` 键
- `Manifest.__init__` 移除 `default_model` 参数；`Manifest.default_model` 属性删除
- `Manifest.to_dict()` 不再 emit `workspace.default_model`
- `empty_manifest(created, default_model=...)` → `empty_manifest(created)`（参数删除）
- `parse()` 不再读 `workspace.default_model` / `wikis.<name>.model`
- `validate()` 删除"未知 model → warn"分支（无 caller）
- `KNOWN_MODELS` 常量删除
- `SETTABLE_KEYS` 移除 `"model"`

**`dump_toml`（workspace.py）**：

- 不再 emit `[workspace].default_model`
- 不再 emit `[wikis.<name>].model`

**测试同步清理**：`test_manifest.py` 删除相关 case；`test_cli.py` 验证 init/add/enter 不再有 `--model` / `--default-model` / `--profile` flag。

### 3.5 依赖 DAG（更新）

```
errors ← workspace ← {commands, manifest.serialize, models.serialize, profile.serialize}
        ↑ （manifest.parse / models.parse / profile.parse 不 import workspace）
errors ← commands ← cli
manifest.parse / manifest.validate ← commands（_common.load_manifest）
models.parse / models.validate ← commands（_common.load_models）
profile.parse / profile.validate ← commands（_common.load_profile / wiki_config_cmd）
_compat ← commands（add / show / enter 软探测）
```

**关键不变量**：`manifest.py` / `models.py` / `profile.py` 都是纯叶子（顶部仅 stdlib），互不依赖；`workspace.py` 是中间层；`commands/*` 在顶层并 import `errors` / `workspace` / `manifest` / `models` / `profile` / `_compat`。`profile.validate` 函数体内惰性 import `models` 以校验引用——但 `profile.py` 模块顶部仍干净。

---

## §4 错误、退出码、日志

### 4.1 新错误 category（叠加到 v1 §4.2）

| category | 触发场景 | 退出码 | 严重度 |
| --- | --- | --- | --- |
| `model-already-exists` | `models add --name <X>`，X 已存在 | 1 | error |
| `model-not-found` | `models remove <X>` / `models set-default <X>`，X 不存在 | 1 | error |
| `wiki-not-bound` | `enter` 时 profile.toml 缺失 + models.toml default 为空 / 缺文件 | 1 | error |
| `models-file-parse-failed` | `models.toml` TOML 语法错误 | 2 | error |
| `models-validation-failed` | `models validate` 阻断（name 冲突 / 字段缺失 / default 引用不存在 / 非 TTY 缺参） | 1 | error |
| `profile-file-parse-failed` | `profile.toml` TOML 语法错误 | 2 | error |
| `profile-validation-failed` | `profile validate` 阻断（缺 `model` / `model=""` / `model` 引用不存在） | 1 | error |
| `wiki-not-found` | `wiki config --name=X` 但 wiki 不存在 | 1 | error |

**约定**：category 是稳定的机器契约（kebab-case），保持英文；`message` / `hint` 一律中文。

**复用既有 category**：

- `workspace-not-initialized`——`models *` / `wiki config` 在 workspace 未 init 时复用（exit 1）
- `internal-state-corruption`——`save_models` / `save_profile` 重解析失败时复用（exit 3）

**移除**：

- `unknown-profile`（之前的 `--profile X` 未知）——`--profile` flag 已删除
- `no-default-model`——重命名为 `wiki-not-bound`（语义更准确）

### 4.2 退出码总览（叠加到 v1 §4.1）

不变。**新增触发场景**：

| 退出码 | 新触发 |
| --- | --- |
| 1 | `model-already-exists` / `model-not-found` / `wiki-not-bound` / `models-validation-failed` / `profile-validation-failed` / `wiki-not-found` |
| 2 | `models-file-parse-failed` / `profile-file-parse-failed` |
| 3 | `save_models` / `save_profile` atomic-write 后 reparse 失败（既有 `internal-state-corruption` 路径） |

### 4.3 stdout vs stderr

完全沿用 v1 §4.4。新约束：**任何输出（stdout / stderr / 错误 message / `--json` 响应 / `--debug` 日志）都不打印 `api_key` 明文**。实现上由两类机制兜底：

1. `models list` / `models list --json`：序列化时跳过 `api_key` 字段
2. `--debug` 路径：profile 引用时打 `name=X model_id=Y base_url=Z api_key=***`（遮 8 字符 + ellipsis）

### 4.4 日志

完全沿用 v1 §4.5。新增消息文案（占位，落地时由实现者润色）：

- `[INFO] 已添加 profile '<X>'`（models add 成功）
- `[INFO] 已删除 profile '<X>'`（models remove 成功）
- `[INFO] default 已指向 '<X>'` / `[INFO] default 已清空`（set-default 成功 / clear）
- `[INFO] Using profile: <X>`（enter 命中 profile.toml 时回显）
- `[WARN] No profile bound for '<wiki>'; using workspace default: <Y>`（enter fallback 到 workspace default 时提示）
- `[INFO] profile.toml 已更新`（wiki config 成功）

---

## §5 测试策略

### 5.1 测试栈（沿用 v1 §5.1）

pytest + `unittest.mock` + `tmp_path` + `pytest-cov`；CI 矩阵不变。

### 5.2 新测试文件 / 扩展

```
tests/
├── test_models.py                  # 新（100% 覆盖目标）
├── test_profile.py                 # 新（100% 覆盖目标）
├── test_models_cmd.py              # 新
├── test_wiki_config_cmd.py         # 新（交互式流程：monkeypatch input + capsys）
├── test_workspace.py               # 扩展（dump_models_toml + dump_profile_toml + load/save round-trip）
├── test_common.py                  # 扩展（load_models / load_profile helpers）
├── test_enter_cmd.py               # 重写 profile 解析：echo / warn / refuse 三路径
├── test_add_cmd.py                 # 清理 --model/--profile 测试；扩展 wiki .gitignore append
├── test_init_cmd.py                # 清理 --default-model 测试；保留 .gitignore append 测试
├── test_config_cmd.py              # 清理 model key 测试
├── test_manifest.py                # 清理 WikiEntry.model / KNOWN_MODELS 相关测试
├── test_cli.py                     # 扩展（models / wiki 子 parser；init/add/enter 无 model flag）
└── test_e2e_smoke.py               # 扩展（init → models add → wiki config → enter leg）
```

### 5.3 关键测试用例清单

**models.py（必须 100% 覆盖）**：

- `parse`：合法 / `default` 缺失（→ `""`）/ 空 `models` 数组 / 缺字段（→ validate 阻断）/ 重复 name（→ validate 阻断）/ `default` 引用不存在（→ validate 阻断）/ 未知顶层字段（→ validate warn）
- `serialize`：round-trip（parse → serialize → parse，值相等）/ 空 registry 序列化
- `validate`：error / warn 级别区分；与 `manifest.validate` 同一份 `Issue` 类

**profile.py（必须 100% 覆盖）**：

- `parse`：合法 / 缺 `model` 键（→ raise）/ `model=""`（→ raise）/ TOML 语法错误（→ raise）/ 未知字段（warn）
- `validate`：model 引用现存 profile 名（pass）/ 引用不存在（fail）
- `serialize`：round-trip

**models_cmd.py（每 action 5-8 个 case）**：

- `add`：全交互 / 全参数 / `--set-default` / name 冲突 / 非 TTY 缺参（→ 报错）/ `getpass` 模拟
- `list`：表格输出 / `--json` / 表格中**绝不**含 `api_key` / `--json` 输出**绝不**含 `api_key` / 无 profile（空表 + `default: (unset)`）
- `remove`：存在 / 不存在 / 默认 profile 被删（→ `default = ""`）/ `--yes` / 非 TTY 缺 `--yes`（→ 报错）
- `set-default`：合法 / 不存在 / `--clear`

**wiki_config_cmd.py（每 case 5-8 个）**：

- 首次配置：profile.toml 不存在 → 创建
- 改绑：profile.toml 存在 → 更新
- 解除绑定：输入 `clear` → 删除 profile.toml（或留空——实现决定）
- 引用不存在：重提示同字段，不前进
- 全部接受当前值（直接 Enter）：幂等
- 中途 Ctrl-C / `q` 退出：不写盘
- 非 TTY 且无 `--show` → 报错
- `--show`：只读不写

**workspace.py 扩展**：

- `dump_models_toml`：round-trip / 空 registry / 多个 profile 顺序保持 / api_key 内的引号 / 反斜杠转义
- `load_models`：文件存在 / 文件缺失（→ 空 registry，不报错）
- `save_models`：atomic / reparse 失败（→ 抛 `internal-state-corruption`）/ 权限 0600（断言 `stat().st_mode & 0o777 == 0o600`）
- `models_file_path`：路径正确
- `dump_profile_toml`：round-trip / `model` 字段引号转义
- `load_profile`：文件存在 / 文件缺失（→ `None`，不报错）
- `save_profile`：atomic / reparse 失败 / 权限 0600
- `profile_path`：路径正确

**enter_cmd.py 重写**：

- profile.toml 有有效 `model=X`：mock `subprocess.run`，断言 cmd 含 `--model X.model_id`、env 含 `ANTHROPIC_BASE_URL=X.base_url` 与 `ANTHROPIC_AUTH_TOKEN=X.api_key`（环境变量名待实现 verify；若变更，断言同步更新）；assert stderr 含 `[INFO] Using profile: X`
- profile.toml 有失效 `model=X`（X 不存在）：emit `profile-validation-failed`，exit 1，**不** spawn
- profile.toml 缺 model / 空字符串：emit `profile-validation-failed`，exit 1，**不** spawn
- profile.toml 缺失 + models.toml default 有：assert stderr 含 `[WARN] No profile bound for ...; using workspace default: X`，spawn 用 X
- profile.toml 缺失 + default 为空：emit `wiki-not-bound`，exit 1，**不** spawn
- profile.toml 缺失 + models.toml 文件不存在：emit `wiki-not-bound`，exit 1（语义等价 default 为空）
- `--dry-run`：打印 cmd + env（env 里 `api_key` 必须 `***`），**不** spawn
- 任意成功 / 失败 / fallback / 拒绝路径：**stdout / stderr / 异常消息 / debug 日志里均不出现** `api_key` 明文
- `--debug` + models / enter：stderr `[DEBUG]` 行里 `api_key` 必须以 `***` 出现（profile dump 时按 `name=X model_id=Y base_url=Z api_key=***` 格式）

**add_cmd.py 扩展**：

- wiki 创建后 append `profile.toml` 到 wiki 的 `.gitignore`（断言单行精确 `profile.toml`）
- wiki .gitignore 已含 `profile.toml`：幂等（不重复）
- wiki 无 .git/：跳过（不创建 .gitignore，不报错）
- 现有 --model / --profile flag 不存在：argparse 测试

**init_cmd.py 清理 + 扩展**：

- 删除 --default-model 相关测试
- 保留 workspace `.gitignore` models.toml 行追加（既有 700a85e 设计）

**config_cmd.py 清理**：删除 `set model` / `unset model` 测试；`SETTABLE_KEYS` 不再含 `model` 的断言。

**manifest.py 清理测试**：

- `WikiEntry` 不再有 `.model` 属性（assert not hasattr）
- `Manifest` 不再有 `.default_model` 属性
- `KNOWN_MODELS` 常量已删除（`hasattr` 断言）
- `SETTABLE_KEYS` 不含 `"model"`

**cli.py 扩展**：

- `llmw models --help`：列出 4 个 subaction
- `llmw wiki --help`：列出 `config` subaction
- `llmw wiki config --help`：列出 `--name` + `--show` flag
- `llmw enter --help`：**不含** `--model`，**不含** `--profile`
- `llmw add --help`：**不含** `--model`，**不含** `--profile`
- `llmw init --help`：**不含** `--default-model`
- `llmw models list --json` 走 `--json` 全局 flag

**e2e smoke 扩展**：

```
init → models add (profile "p1") → wiki config --name=<wiki> (input "p1")
       → enter <wiki> (mock subprocess) → assert 使用 p1
```

### 5.4 覆盖率目标

整体 `--cov-fail-under=85`（沿用 v1）。`models.py` 100%（与 `manifest.py` 同档）；`profile.py` 100%；`models_cmd.py` 80%+；`wiki_config_cmd.py` 80%+；其它扩展模块保持既有目标。

### 5.5 安全断言（必加）

至少在 `test_models_cmd.py::test_list_redacts_api_key` 与 `test_enter_cmd.py::test_*` 的每个 case 里：

- `capsys.readouterr().out` 不含 `api_key` 明文
- `capsys.readouterr().err` 不含 `api_key` 明文
- mock 异常的 `str(exc)` 不含 `api_key` 明文（profile 在 raise 时若被 repr 出来，必须先 redact）

profile.toml 的 `model` 字段是 profile 名（非 secret），无 redact 需求；`--debug` 路径打印 profile 时也不暴露 secret。

### 5.6 不测的（沿用 v1 §5.6 + 新增）

| 不测项 | 理由 |
| --- | --- |
| `claude` 子进程真实接收 env 的端到端验证 | 集成测试范围；`enter --dry-run` 即可观察 |
| 模型 ID 是否在 Anthropic 端真实可用 | provider 服务端的事 |
| `getpass` 真终端隐藏 | 跨平台；monkeypatch `getpass.getpass` 即可 |
| Windows 文件权限 0600 | v1 仅 Linux + macOS；Windows 用 ACL 不是 mode bits |
| `llmw wiki config` 真 TUI 视觉布局 | 仅 mock `input()` 验证逻辑；非 curses，故无视觉测试 |

---

## §6 安全：gitignore 与文件权限

### 6.1 `.gitignore` 处理（两处独立 append）

`init` 在检测到 `<workspace_root>/.git/` 存在时，往 `<workspace_root>/.gitignore` 追加：

```
models.toml
```

`add` 在 wiki 创建后（setup_wiki.py 已跑），往 `<wiki_root>/.gitignore` 追加：

```
profile.toml
```

**两处约定一致**：

- 一行精确为文件名（无前缀、无注释）
- **幂等**：若 `.gitignore` 已含该行，不重复（用全行匹配而非子串）
- 保留其它既有内容（包括无尾换行的尾行——追加前先确保有换行符）
- 父 `.git/` 不存在 → 跳过；不创建 `.gitignore`，不报错
- `models add` / `wiki config` 等后续命令**不**再次追加

**为什么不放进顶层 `llm_workspace_cli` 仓的 `.gitignore`？** workspace 是独立仓；models.toml 在 workspace 仓内，profile.toml 在每个 wiki 仓内；gitignore 必须在各自仓。

### 6.2 文件权限

- `tempfile.mkstemp` 默认权限 0600（仅 owner 可读写）
- `os.replace(tmp, target)` 保留源文件 mode——故 `models.toml` / `profile.toml` 创建后即 0600
- **不**对既有非 0600 文件做 chmod（尊重用户显式调整；警告但不强制）

### 6.3 防护层级

| 层级 | 防什么 | 不防什么 |
| --- | --- | --- |
| 文件 mode 0600 | 同机其它用户读 | 同机 root / 已获 owner 权的进程 / 备份泄露 |
| workspace `.gitignore` 含 `models.toml` | workspace 仓误提交 | `git add -f` 强制 / 已存在历史 commit |
| wiki `.gitignore` 含 `profile.toml` | wiki 仓误提交 | 同上 |
| 输出 redact | stdout / stderr / 日志泄露 | 内存 dump / 调试器 attach / 子进程 env（api_key 本来就要进子进程——这是设计内） |

**明文**：以上都是降低意外泄露概率的纵深防御，**不替代**用户对机器本身的访问控制。

### 6.4 实现细节 / 待决项

1. **`wiki config clear` 的语义**：profile.toml 文件**删除** vs 留空文件。**推荐删除**（避免空文件歧义：空文件是"未配置"还是"配置为空"？）。`enter` 区分：文件不存在 → fallback to default；文件存在但 model 缺/空 → error。
2. **wiki .gitignore append 时机**：在 `add` 流程的最后一步（manifest 写入之后），因为 wiki 目录此时已创建（setup_wiki.py 已跑）。若 wiki 无 .git/（`--no-git` 场景），跳过。
3. **workspace .gitignore 与 wiki .gitignore 分工**：workspace .gitignore → `models.toml`；wiki .gitignore → `profile.toml`。两处独立 append，互不影响。
4. **`profile.toml` 文件权限**：0600（与 models.toml 同档——profile 不含 secret 但 wiki 局部配置仍按 0600 防御性保护）；`tempfile.mkstemp` 默认即满足。
5. **`llmw wiki config` 失败时的 profile.toml 状态**：写入失败 → 文件保持旧值（atomic write 保证）；校验失败 → 不写盘，profile.toml 完全不动。
6. **`models.toml` 中 profile 被删后绑定到该 profile 的 wiki**：`enter` 时检测到 `profile.toml` 引用已不存在的 profile 名 → emit `profile-validation-failed` exit 1；用户用 `wiki config` 重新绑定或恢复 profile。

---

## 附录 A：与 v1 的兼容矩阵（彻底清理版）

| 既有 v1 行为 | 本特性后 |
| --- | --- |
| `workspace.default_model` 字段 | **删除**——不再写入；遗留字段被静默忽略；`init` 不再支持 `--default-model` |
| `wikis.<name>.model` 字段 | **删除**——同上；`add` 不再支持 `--model`；`enter` 不再读 |
| `manifest.KNOWN_MODELS` warn 检查 | **删除**——`manifest.validate` 不再检查 model_id 白名单（CLI 完全不维护白名单） |
| `enter --model <ID>` 显式 ID | **删除**——`enter` 只读 profile.toml + workspace default |
| `add --model <ID>` | **删除**——profile 绑定走 `wiki config` |
| `config set <wiki> model <ID>` / `unset model` | **拒绝**——`SETTABLE_KEYS` 不再含 `model` |
| `list` / `show` 输出 MODEL 列 | **删除**——这两个命令不再读 model 字段（manifest 不再有 model）；若需要看 wiki 当前 profile，走 `llmw wiki config --name=<wiki> --show` |

**Migration**：**无**。v1 未发布，无用户数据需要迁移；遗留 `.workspace.toml` 文件含 `default_model` / `model` 字段时被静默忽略（tomllib 解析多余 key 不报错，validate 不检查）。

## 附录 B：风险与未决项

| 风险 / 未决项 | 影响 | 缓解 |
| --- | --- | --- |
| Claude Code / Anthropic SDK 的环境变量名不一定是 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` | 子进程拿不到 profile | 实现时跑 `claude --help` + 翻 Anthropic SDK 源码确认；`enter --dry-run` 暴露 env 便于诊断 |
| `models add` 在非 TTY 环境下无法工作（getpass 失败 / 交互 prompt 失败） | CI / 脚本无法配 profile | `models add` 已要求**所有参数必填**才不靠 prompt；非 TTY 缺任何参数 → 报错退出 1。若 CI 真要自动化：实现一个薄封装脚本（用 `wiki_workspace.workspace.save_models` 直接写），不进 `llmw` 主 CLI——这是**用户自选**的扩展点，不在 `llmw` 范围。**故意不**为 api_key 加环境变量兜底入口：与用户"所有配置不依赖环境变量，全部以配置文件的形式存储"的指令相悖。 |
| `llmw wiki config` 在非 TTY 环境下无法工作 | CI / 脚本无法配 profile 绑定 | `wiki config` 默认交互式；非 TTY 下要求 `--show`（纯查询），否则报错退出 1。脚本配置走手工 vi profile.toml 或用户自选扩展点（同上）。**故意不**为 wiki config 加非交互 flag——保持 v1 简洁；future 字段加入时再评估。 |
| `profile.toml` 中 profile 名引用了 `models.toml` 中已删除的 profile | `enter` 启动失败 | `enter` 时检测 → emit `profile-validation-failed` exit 1；用户 `wiki config` 重新绑定或 `models add` 恢复 profile |
| 用户在同一 workspace 多次 `init` | workspace `.gitignore` 重复追加 | 幂等检查（§6.1） |
| 跨 workspace profile 共享需求 | 用户可能在多个 workspace 配同样的 profile | 不在 v1 范围；用户可手工 `cp models.toml` |
| `models.toml` / `profile.toml` 损坏 | `enter` / `wiki config` 解析失败 | exit 2 + 提示手动修；与 manifest-parse-failed 同档处理 |
| `wiki config clear` 语义 | 是删文件还是留空 | 推荐删（§6.4 实现细节 #1）；实现时二选一 |
| 多个 wiki 绑定同一 profile + 该 profile 含共享 api_key | profile 集中轮换的便利 | 这是设计目标（共享 credentials）；不算风险——若用户想隔离需手工拆 profile |
| `models add` 时 TTY 不可用 + 用户已 `--set-default` 但新 profile 校验失败 | 旧 default 丢失？ | 顺序：先 append + 校验通过后才改 default；新 entry 校验失败则**不**改 default；实现时把 default 改动放在 atomic write 之前的状态合并里 |
| `wiki config` 中输入 `clear` 但用户本意是字面字符串"clear"作为 profile 名 | 误删绑定 | `models.toml` 的 profile 名校验规则已约束：必须 kebab-case；"clear" 不符合（v1 起追加的合法 profile 名规则由实现时细化）→ `clear` 永远不可能是合法 profile 名，**不会歧义** |