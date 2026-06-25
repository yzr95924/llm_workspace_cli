# llmw — LLM Workspace CLI 设计文档

| 字段 | 值 |
| --- | --- |
| 版本 | 0.1（设计稿，待实现后随版本演进） |
| 日期 | 2026-06-26 |
| 状态 | 草案，已通过 5 节分节确认 |
| 仓库 | `git@github.com:yzr95924/llm_workspace_cli.git`（作为 submodule 挂在主 SKILL 仓） |
| 关联 skill | `llm-wiki-management`（运行期软依赖） |

## 背景与目标

### 痛点

用户当前用 `llm-wiki-management` skill 维护多个 wiki（个人研究 / 读书笔记 / 项目沉淀等），每个 wiki 是独立的 git 仓 + 独立目录。痛点：

1. 切换 wiki 时手动 `export LLM_WIKI_ROOT=~/wiki/llm-systems`，易错
2. 多个 wiki 的元数据（创建日期 / 关联笔记 / 配置）没有集中登记处
3. 想"对所有 wiki 做 lint"或"在所有 wiki 里搜一个概念"时，要写 for 循环脚本
4. 不同 wiki 可能想用不同 Claude model / session 配置，散落各处

### 目标

提供一个轻量 Python CLI `llmw`，管理一个 **workspace**（一个目录下挂多个 wiki），承担：

- workspace 与 wiki 元数据集中登记
- 单 wiki / 跨 wiki 的 deterministic 操作编排（setup / lint / 状态查询）
- 把 Claude Code 启动到指定 wiki 上下文里

## 范围

### 做

- workspace 生命周期管理（init / 列出 / 加 wiki / 删 wiki / 查 wiki / 改配置）
- 调 `llm-wiki-management` 的 `setup_wiki.py` 创建 wiki
- 把 Claude Code 启动到指定 wiki 根目录 + 注入 workspace context
- workspace / wiki 的元数据持久化（`.workspace.toml`）

### 不做（v1）

- wiki 内容编辑 / 搜索（属于 llm-wiki-management skill 的活）
- wiki 之间的内容同步 / 迁移（v2 再考虑）
- workspace 嵌套 / 跨 workspace 操作
- 自动 commit / 自动 backup（v2）
- Windows 平台支持（v1 仅 Linux + macOS）

## 设计原则

1. **CLI 是给人用的入口**：用户跑 `llmw enter foo` 后由 Claude Code（被 spawn 出来的子进程）接管 LLM 驱动的工作；CLI 本身**不**做 LLM 推理。
2. **`llmw` 与 `llm-wiki-management` 解耦**：submodule + soft dependency；任一可独立安装、独立升级。
3. **配置文件是 SSOT**：`.workspace.toml` 是 wiki 元数据的唯一来源；CLI 不维护平行数据库。
4. **subprocess > import**：跨仓 / 跨包调脚本一律 `subprocess.run`，不 `import`，避免 lock-step 升级。
5. **原子写盘**：任何改 manifest 的命令走 tmp + fsync + rename + reparse 自检。

---

## §1 架构与项目结构

### 1.1 仓库布局

`llm_workspace_cli/` 是**独立 git repo**（已作为 submodule 挂在主 SKILL 仓 `my_SKILL/llm_workspace_cli/`，URL `git@github.com:yzr95924/llm_workspace_cli.git`）。代码 + 设计文档都在这层，主仓只持有 submodule 引用，**不在主仓加 SKILL.md 包装层**（避免循环嵌套：CLI → Claude Code → SKILL → CLI）。

```
llm_workspace_cli/                            # 独立 git repo（submodule）
├── README.md                                 # 给人的快速上手
├── LICENSE
├── .gitignore
├── pyproject.toml                            # PEP 621；[project.scripts] llmw = "wiki_workspace.cli:main"
├── doc/
│   └── design.md                             # 本文档
├── wiki_workspace/
│   ├── __init__.py
│   ├── __main__.py                           # python -m wiki_workspace 入口
│   ├── cli.py                                # argparse 分派
│   ├── workspace.py                          # workspace 路径解析 + .workspace.toml 读写
│   ├── manifest.py                           # 单 wiki 配置的读写 / 校验
│   ├── _compat.py                            # 从 llm-wiki-management/scripts 软导入工具
│   └── commands/
│       ├── __init__.py
│       ├── init_cmd.py
│       ├── list_cmd.py
│       ├── add_cmd.py
│       ├── remove_cmd.py
│       ├── show_cmd.py
│       ├── config_cmd.py
│       └── enter_cmd.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_workspace.py
    ├── test_manifest.py
    ├── test_compat.py
    ├── test_cli.py
    ├── test_init_cmd.py
    ├── test_list_cmd.py
    ├── test_add_cmd.py
    ├── test_remove_cmd.py
    ├── test_show_cmd.py
    ├── test_config_cmd.py
    ├── test_enter_cmd.py
    └── fixtures/
```

### 1.2 跨仓交互

| 调用方向 | 形态 |
| --- | --- |
| `llmw` → `llm-wiki-management` | 通过 `subprocess.run` 调 `setup_wiki.py`（在 `add_cmd`）；**不 import** |
| `llmw` → Claude Code | 通过 `subprocess.run(["claude", ...])` 启动交互式 REPL（`enter_cmd`） |
| `llm-wiki-management` → `llmw` | **单向**——SKILL 内不直接调 CLI |

### 1.3 关键约束

| 维度 | 选择 |
| --- | --- |
| 包名（PyPI / import） | `wiki-workspace` |
| Python 模块 | `wiki_workspace` |
| CLI 命令名 | `llmw` |
| Python 版本 | `requires-python = ">=3.6"`；`target-version = "py37"`（与本仓根 `pyproject.toml` 一致；守 PEP 604/585 / 海象 / `capture_output+text` 等 3.7+ 写法） |
| 依赖 | 仅 `tomli`（py<3.11，py≥3.11 用内置 `tomllib`）；不引入 click / rich |
| 与 llm-wiki-management 的耦合 | **软**：按命令分级（详见 §1.4） |

### 1.4 llm-wiki-management 依赖分级

| 命令 | 是否需要 llm-wiki-management | 缺失时行为 |
| --- | --- | --- |
| `init` | ❌ | 正常执行 |
| `list` | ❌ | 正常执行 |
| `config` | ❌ | 正常执行 |
| `remove` | ❌ | 正常执行 |
| `show` | △ 可选 | 缺失时显示元数据 + warn |
| `add` | ✅ 必需（调 setup_wiki.py） | **硬错误**：打印安装指引 + 退出码 2 |
| `enter` | ✅ 强烈推荐 | **启动 Claude Code 之前 + 之后** 各打一次 warn，**仍然启动** |

**检测顺序**（按优先级）：

1. 环境变量 `LLM_WIKI_MANAGEMENT_PATH`（用户显式指定）
2. workspace 同级的 `../llm-wiki-management/SKILL.md`（典型布局）
3. `~/.claude/skills/llm-wiki-management/SKILL.md`（Claude Code 已装为 skill）
4. 全部未命中 → 视为缺失

### 1.5 模块边界

| 模块 | 职责 | 不做 |
| --- | --- | --- |
| `workspace.py` | workspace 根路径解析 + `.workspace.toml` 读写 + 发现 wiki 子目录 | 不调任何外部脚本；不感知具体命令 |
| `manifest.py` | 单 wiki 配置的 in-memory 操作 + 字段校验 | 不写文件（写盘由 `workspace.py` 负责） |
| `commands/*_cmd.py` | 每个子命令一个文件；签名统一 `def run(args: argparse.Namespace) -> int` | 不直接调 argparse |
| `cli.py` | argparse 顶层 + 子命令分派 + 错误处理 | 不写业务逻辑 |
| `_compat.py` | 软导入 `llm-wiki-management` 的 `slugify` / `parse_frontmatter_simple`；失败时 fallback stub | 不修改 llm-wiki-management 任何文件 |

---

## §2 `.workspace.toml` 数据模型

### 2.1 整体结构

```toml
schema_version = "1"
created = "2026-06-26"

[workspace]
default_model = "claude-sonnet-4-6"

[wikis.llm-systems]
path = "llm-systems"
display_name = "LLM Systems"
description = "LLM 架构 / 训练 / 推理研究"
model = "claude-opus-4-8"
created = "2026-06-26"
tags = ["research", "papers"]

[wikis.recipes]
path = "recipes"
display_name = "Family Recipes"
description = "家庭菜谱沉淀"
created = "2026-06-20"
tags = ["cooking", "personal"]
```

用 `[wikis.<name>]` 表（**非** `[[wikis]]` 数组）—— wiki 名作为 key 天然唯一，且与 CLI 子命令的 `<name>` 位置参数对齐。

### 2.2 字段表

| 字段 | 层级 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `schema_version` | top | string | ✅ | — | 当前固定 `"1"`；schema 升级时改这个 + 加迁移路径 |
| `created` | top | ISO date | ✅ | — | workspace 创建日 |
| `[workspace]` | section | table | ✅ | — | workspace 级配置 |
| `default_model` | `[workspace]` | string | ❌ | `"claude-sonnet-4-6"` | wiki 未指定 model 时的兜底 |
| `[wikis.<name>]` | section | table | ✅（每个 wiki） | — | wiki 名是 key（kebab-case + 唯一） |
| `path` | `[wikis.<name>]` | string | ✅ | — | 相对 workspace 根；硬约束：必须实际存在 + 含 CLAUDE.md + raw/ + wiki/ |
| `display_name` | `[wikis.<name>]` | string | ✅ | — | 人类可读标题 |
| `description` | `[wikis.<name>]` | string | ❌ | `""` | 一句话目的 |
| `model` | `[wikis.<name>]` | string | ❌ | 继承 `workspace.default_model` | `llmw enter` 时传给 `claude --model <X>` |
| `created` | `[wikis.<name>]` | ISO date | ✅ | — | wiki 创建日 |
| `tags` | `[wikis.<name>]` | string array | ❌ | `[]` | 用于 `llmw list --tag=...` 过滤 |

### 2.3 校验规则

| 不变量 | 触发条件 | 错误信息 |
| --- | --- | --- |
| wiki 目录必须存在 | `path` 指向不存在目录 | `[ERROR] wikis.<name>.path '<X>' 不存在` |
| wiki 目录必须含 CLAUDE.md | 缺 CLAUDE.md | `[ERROR] wikis.<name>.path '<X>' 不是合法 wiki（缺 CLAUDE.md）` |
| wiki 名必须 kebab-case | `name` 含大写 / 空格 / 下划线 | `[ERROR] wiki 名 '<X>' 必须 kebab-case` |
| wiki 名必须唯一 | 重复 key | `[ERROR] wikis.<X> 重复` |
| path 必须相对 workspace 根且不含 `..` | 路径逃逸 | `[ERROR] wikis.<name>.path '<X>' 必须位于 workspace 内` |
| model 必须是已知 Claude 模型 ID | 拼错 | `[WARN] wikis.<name>.model '<X>' 未知；将继续` |
| created 必须 ISO 日期 | 格式错 | `[ERROR] wikis.<name>.created '<X>' 不是 YYYY-MM-DD` |
| 未知字段 | 多余 key | `[WARN] wikis.<name>.<field> 未知字段；忽略` |

校验时机：每个命令启动时（不光是 `add`）；早 fail。

### 2.4 写盘时机

| 写盘触发 | 写盘逻辑 |
| --- | --- |
| `llmw init` | 创建空骨架 |
| `llmw add <name>` | 在 `[wikis]` 段追加一个 `<name>` 表 |
| `llmw remove <name>` | 删 `[wikis.<name>]` 段（**不**删 wiki 目录——除非 `--purge`） |
| `llmw config <name> set <key> <val>` | 更新 `[wikis.<name>.<key>]` 字段 |
| `enter` / `list` / `show` | 纯读，不写盘 |

**写盘约定**：整个文件 read-modify-write；写盘前先 atomic write（详见 §4.3）；写盘后跑一次 `tomli.load` 重新解析，确认未损坏。

### 2.5 schema_version 演进

`schema_version = "1"`。未来加字段：

- **不破坏**：新字段全 optional + 默认值（向后兼容）
- **破坏**：需要迁移脚本 `llmw migrate 1→2`，自动备份 `.workspace.toml.bak`

v1 不实现 migrate。

---

## §3 命令面与子命令语义

### 3.0 全局参数

所有子命令共享：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--workspace <PATH>` / `-w` | path | 见 §3.0.1 | 显式指定 workspace 根 |
| `--json` | flag | off | 部分命令支持结构化输出 |
| `--quiet` / `-q` | flag | off | 抑制 WARN 输出，只打 ERROR + 命令结果 |

#### 3.0.1 workspace 解析优先级

| 优先级 | 来源 | 备注 |
| --- | --- | --- |
| 1（最高） | `--workspace <PATH>` / `-w` | 显式 CLI 标志 |
| 2 | `$LLMW_WORKSPACE` 环境变量 | shell 级覆盖 |
| 3 | 从 cwd 向上找第一个含 `.workspace.toml` 的目录 | 在 workspace 子目录里跑命令时方便 |
| 4（最低） | `~/llm_workspace/` | 默认值 |

不报错"找不到 workspace"——所有命令都 fallback 到 `~/llm_workspace/`；只有当 `.workspace.toml` 不存在**且**用户跑的是 `init` 以外的命令时，才报错 `workspace-not-initialized`。

### 3.1 `llmw init`

```text
llmw init [--workspace <PATH>] [--default-model <ID>]
```

**默认行为**：`llmw init`（无参数）→ 在 `~/llm_workspace/` 创建 workspace（`mkdir -p` + 写 `.workspace.toml` + 写 `CLAUDE.md`）。

**完整流程**：

1. 解析目标 workspace 路径
2. `mkdir -p <target>`
3. 检查 `<target>/.workspace.toml` 不存在 → 否则错误退出 1
4. 写入 `.workspace.toml`（最小骨架）
5. **写入 `CLAUDE.md`**（替代 README.md，让 Claude Code 在 workspace 根启动时自动加载）
6. 若 `<target>/.git/` 存在 → 提示 `git add .workspace.toml CLAUDE.md && git commit`；否则建议 `git init`
7. stdout 打印初始化成功 + 下一步提示

**CLAUDE.md 内容模板**：

```markdown
# llmw Workspace

This directory is managed by [llmw](https://github.com/yzr95924/llm_workspace_cli).
- `llmw list` — list wikis
- `llmw add <name>` — create a new wiki
- `llmw enter <name>` — launch Claude Code inside a wiki (auto-loads this CLAUDE.md)
```

| 维度 | 内容 |
| --- | --- |
| 失败条件 | (a) `--workspace` 已含 `.workspace.toml` → 退出 1；(b) 父目录链上已有其它 workspace → warn 但允许嵌套 |
| 副作用 | 创建 `.workspace.toml` + `CLAUDE.md`；git 仓时提示 add（不自动 commit） |
| 退出码 | 0 / 1 / 2 |
| 依赖 | ❌ 不依赖 llm-wiki-management |

### 3.2 `llmw list`

```text
llmw list [--tag <TAG>] [--json]
```

**默认输出**（人类可读表格）：

```
NAME              PATH                MODEL                TAGS              CREATED
llm-systems       llm-systems/        claude-opus-4-8      research,papers   2026-06-26
recipes           recipes/            claude-sonnet-4-6    cooking,personal  2026-06-20
```

**`--json`**：输出 JSON 数组，每项含 name / path / model / tags / created。

| 维度 | 内容 |
| --- | --- |
| 失败条件 | workspace 不存在 → 退出 2 |
| 副作用 | 无 |
| 退出码 | 0 / 2 |
| 依赖 | ❌ |

### 3.3 `llmw add <name>`

```text
llmw add <name>
    [--display-name <STR>]
    [--description <STR>]
    [--model <ID>]
    [--tag <TAG>]...
    [--topic <STR>]      # 透传给 setup_wiki.py（CLAUDE.md {{TOPIC_NAME}}）
    [--no-git]           # 不调 setup_wiki.py 的 git init 步骤
```

**完整流程**：

1. 校验 `<name>` 是 kebab-case
2. 加载 + 校验 `.workspace.toml`
3. 检查 `[wikis.<name>]` 不存在
4. 检查 `<workspace>/<name>/` 不存在或为空
5. **检测 llm-wiki-management**（按 §1.4 优先级）；未命中 → 硬错误退出 2
6. **subprocess 调 setup_wiki.py**：`subprocess.run([sys.executable, setup_script, topic, wiki_root])`
7. **追加 manifest 条目**（atomic write）
8. stdout 打印创建成功 + `llmw enter <name>` 提示

**依赖缺失错误**：

```
[ERROR] llm-wiki-management not found at any of:
  - $LLM_WIKI_MANAGEMENT_PATH
  - ../llm-wiki-management/SKILL.md
  - ~/.claude/skills/llm-wiki-management/SKILL.md

Cannot run `llmw add` without it.
Install from: https://github.com/yzr95924/llm-wiki-management
Or set LLM_WIKI_MANAGEMENT_PATH=/path/to/llm-wiki-management
```

| 维度 | 内容 |
| --- | --- |
| 失败条件 | (a) wiki 名冲突 → 1；(b) 目录已存在非空 → 1；(c) 依赖缺失 → 2；(d) setup_wiki.py 失败 → 2 |
| 副作用 | (1) 调 setup_wiki.py；(2) 写 manifest |
| 退出码 | 0 / 1 / 2 |
| 依赖 | ✅ 必需 |

### 3.4 `llmw remove <name>`

```text
llmw remove <name> [--purge] [--yes]
```

| 维度 | 内容 |
| --- | --- |
| 默认行为 | 只从 manifest 删 `[wikis.<name>]`；**不动** wiki 目录 |
| `--purge` | 同时 `rm -rf <workspace>/<path>/`（危险；要求 `--yes`） |
| `--yes` / `-y` | 跳过确认 prompt |

**确认 prompt**：

```
About to remove wiki 'recipes' from .workspace.toml.
Wiki directory at recipes/ will NOT be deleted (use --purge to remove).
Continue? [y/N]
```

| 失败条件 | wiki 不存在 → 1 |
| 副作用 | 改 manifest；`--purge` 时删目录 |
| 退出码 | 0 / 1 / 2 |
| 依赖 | ❌ |

### 3.5 `llmw show <name>`

```text
llmw show <name> [--json]
```

**默认输出**：

```
Wiki: llm-systems
Path:        /home/user/llm_workspace/llm-systems/
Display:     LLM Systems
Description: LLM 架构 / 训练 / 推理研究
Model:       claude-opus-4-8 (from wikis.llm-systems.model)
Created:     2026-06-26
Tags:        research, papers

─── Recent log entries ───
## [2026-06-25] ingest | Attention Is All You Need
## [2026-06-25] query  | Transformer vs Mamba
## [2026-06-24] setup  | Initial scaffold by llm-wiki-management

─── Git status ───
On branch main
nothing to commit, working tree clean

─── Sources / Concepts / Entities counts ───
sources: 12   concepts: 8   entities: 4   comparisons: 1   syntheses: 1
```

| 维度 | 内容 |
| --- | --- |
| 失败条件 | wiki 不存在 → 1 |
| 副作用 | 无（纯读） |
| 退出码 | 0 / 1 |
| 依赖 | △ 可选——读 `wiki/log.md` / `wiki/index.md` 用 `_compat.parse_frontmatter_simple`；缺失时跳过这些 section + warn |

### 3.6 `llmw config <name>`

```text
llmw config <name> show                    # 默认；显示所有字段
llmw config <name> get <key>               # 取单个字段
llmw config <name> set <key> <value>       # 设单个字段
llmw config <name> unset <key>             # 移除字段（仅 optional 字段生效）
```

**可 set 的 key**：

| key | 类型 | unset 允许 |
| --- | --- | --- |
| `display_name` | string | ❌（必填） |
| `description` | string | ✅ |
| `model` | string | ✅（继承 workspace.default_model） |
| `tags` | string array | ✅ |

**不可 set 的 key**：`name`（key 本身）、`path`（改路径是 `remove` + `add`）、`created`（审计字段）。

| 维度 | 内容 |
| --- | --- |
| 失败条件 | (a) wiki 不存在 → 1；(b) key 非法 → 2；(c) value 类型不匹配 → 2 |
| 副作用 | `set` / `unset` 时改 manifest（atomic write） |
| 退出码 | 0 / 1 / 2 |
| 依赖 | ❌ |

### 3.7 `llmw enter <name>`

```text
llmw enter <name>
    [--model <ID>]
    [--claude-md-check=warn|fail|skip]  # 默认 warn
    [--dry-run]
```

**完整流程**：

1. 加载 + 校验 manifest
2. 解析 `wiki_root = workspace_root / wikis[name].path`
3. 检测 llm-wiki-management（按 §1.4 优先级）
4. 根据 `--claude-md-check` 决定缺失时是否继续
5. 构造 claude CLI 调用：

```python
cmd = ["claude"]
if model:
    cmd += ["--model", model]
# 两个 add-dir：workspace 根（注入 workspace CLAUDE.md）+ wiki 根（注入 wiki CLAUDE.md）
cmd += ["--add-dir", str(workspace_root)]
cmd += ["--add-dir", str(wiki_root)]
cmd += ["--system-prompt", SYSTEM_PROMPT_TEMPLATE.format(...)]
```

> **前提**：Claude Code 的 `--add-dir` 会顺带把该目录的 CLAUDE.md 注入到 system context。**实现阶段需验证**；若不成立，workspace CLAUDE.md 仅在用户从 `~/llm_workspace/` 直接跑 `claude` 时生效。

6. `--dry-run`：只打印 cmd + 退出 0
7. 正常：`subprocess.run(cmd, cwd=str(wiki_root), check=False)`——把 stdin/stdout/stderr 透传给用户
8. 退出码跟随 claude 子进程退出码

**system prompt template**：

```text
You are operating inside an llmw-managed workspace:

  workspace root: {workspace_root}
  wiki name:      {wiki_name}
  wiki root:      {wiki_root}
  skill:          {llm_wiki_management_path}

The llm-wiki-management skill is available (or should be installed).
Use it for ingest / query / lint operations on this wiki.
The wiki's CLAUDE.md ({wiki_root}/CLAUDE.md) contains its schema — read it first
before any write operation.
```

| 维度 | 内容 |
| --- | --- |
| 失败条件 | (a) wiki 不存在 → 1；(b) `claude` 不在 PATH → 2 |
| 副作用 | spawn 子进程；无本地文件改动 |
| 退出码 | 跟随 `claude` 子进程退出码 |
| 依赖 | △ 检测，缺失时 warn 不 fail |

### 3.8 命令总览

| 命令 | 依赖 llm-wiki-management | 副作用 |
| --- | --- | --- |
| `init` | ❌ | 创建 `.workspace.toml` + `CLAUDE.md` |
| `list` | ❌ | 无 |
| `add` | ✅ 必需 | 调 setup_wiki.py + 写 manifest |
| `remove` | ❌ | 改 manifest（`--purge` 加删目录） |
| `show` | △ 可选 | 无 |
| `config` | ❌ | 改 manifest |
| `enter` | △ 检测，缺失 warn | spawn claude 子进程 |

---

## §4 错误处理、退出码、日志约定

### 4.1 退出码表

| 退出码 | 语义 | 触发场景 |
| --- | --- | --- |
| 0 | 成功 | 所有 happy path |
| 1 | 用户错误（语义冲突 / 输入非法 / 资源不存在） | `add foo` 时已存在；`show bar` 不存在；非法 wiki 名；`config set name bar` |
| 2 | 环境错误（依赖缺失 / 配置损坏 / 子进程失败） | llm-wiki-management 三处探测全 miss；TOML 解析失败；setup_wiki.py 退出非零；`claude` 不在 PATH |
| 3 | 内部错误（不该发生的 bug） | atomic write 后 reparse 失败；race condition |
| 其它 | 透传子进程退出码 | `enter foo` → claude 退出 137 → llmw 也退出 137 |

边界：**1 vs 2 = 用户改输入能修 vs 用户得装东西 / 改环境能修**。3 = 修不了、得报 issue。

### 4.2 错误消息格式

**人类可读模式**（默认）：

```
[ERROR] <category>: <具体描述>
[ERROR] <category>: <具体描述>     # 多行错误按行打印
<提示 1: 该怎么修>
<提示 2: 更多信息指向>
```

`<category>` 是机器可解析的 kebab-case 标签：`wiki-not-found` / `wiki-already-exists` / `invalid-wiki-name` / `path-not-in-workspace` / `workspace-not-initialized` / `manifest-parse-failed` / `manifest-validation-failed` / `dep-not-found` / `setup-script-failed` / `claude-not-in-path` / `internal-state-corruption`。

**`--json` 模式**：

```json
{
  "exit_code": 1,
  "errors": [
    {
      "category": "invalid-wiki-name",
      "message": "'Recipes' 必须 kebab-case",
      "hint": "llmw add recipes"
    }
  ]
}
```

### 4.3 原子写盘

任何改 `.workspace.toml` 或 `CLAUDE.md` 的命令走 atomic write：

```python
import os
import tempfile

def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)  # POSIX atomic rename
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise
```

**自检**：写盘后立刻 `tomli.loads(content)` 重解析——失败则抛 `internal-state-corruption`（退出码 3）。

### 4.4 stdout vs stderr

| 流 | 内容 | 原因 |
| --- | --- | --- |
| stdout | 命令的**结果数据**（表格 / 单值 / JSON 对象） | 可被 shell pipe / 重定向消费 |
| stderr | 进度信息 + WARN + ERROR + 日志噪音 | 不污染 stdout 的可解析性 |

```bash
$ llmw add llm-systems 2>add.log
Created wiki 'llm-systems' at /home/zryang/llm_workspace/llm-systems

$ llmw list --json 2>/dev/null | jq '.[0].name'
"llm-systems"
```

### 4.5 日志级别

| 级别 | 标记 | 何时打 |
| --- | --- | --- |
| ERROR | `[ERROR]` | 命令失败，必须让用户看到 |
| WARN | `[WARN]` | 可继续但用户应知道 |
| INFO | `[INFO]` | 进度（仅 `--verbose` 或 stderr 默认 ON） |
| DEBUG | `[DEBUG]` | 仅 `--debug` |

`--quiet` / `-q` 关闭 WARN + INFO，只保留 ERROR。

### 4.6 错误恢复策略

| 失败点 | 恢复行为 |
| --- | --- |
| manifest 解析失败 | 不修改任何文件；提示备份 + 修 TOML |
| setup_wiki.py 失败 | 不写 manifest；提示用户手动 `rm -rf <path>` 或重试 |
| atomic write 后 reparse 失败 | 抛 `internal-state-corruption`；尝试从 `.workspace.toml.bak` 恢复 |
| `claude` 启动失败 | 退出码 2 + 安装指引；workspace 状态无变化 |
| 用户 Ctrl+C 在 `enter_cmd` 中途 | 透传给 claude 子进程；不主动 kill；退出码跟随 claude |
| 并发写盘 | **不防护**——MVP 不加锁；worst case 后写覆盖前写，atomic write 保证不会写半截 |

### 4.7 调试模式

```bash
llmw --debug add foo
LLMW_DEBUG=1 llmw list
```

`--debug` 额外打：

- 所有 subprocess 的完整 cmd 数组 + cwd + env（敏感字段用 `***` 遮）
- 所有文件读写的绝对路径
- workspace 解析的最终结果（4 级优先级哪一级命中）
- manifest 的 in-memory 表示（pretty-print TOML）

---

## §5 测试策略

### 5.1 测试栈

| 维度 | 选择 |
| --- | --- |
| 框架 | pytest |
| Mock | 标准库 `unittest.mock`（不引入 pytest-mock） |
| 临时目录 | pytest 内置 `tmp_path` |
| 覆盖率 | `pytest-cov`（仅 dev 依赖） |
| CI | GitHub Actions 矩阵 py3.6 + py3.11 |

### 5.2 目录结构

```
tests/
├── conftest.py              # 全局 fixtures
├── test_workspace.py
├── test_manifest.py
├── test_compat.py
├── test_cli.py
├── test_init_cmd.py
├── test_list_cmd.py
├── test_add_cmd.py
├── test_remove_cmd.py
├── test_show_cmd.py
├── test_config_cmd.py
├── test_enter_cmd.py
└── fixtures/
    ├── sample-workspace/    # 完整示例 workspace
    ├── bad-toml/             # TOML 损坏的 workspace
    └── empty-workspace/      # 只有 .workspace.toml
```

### 5.3 关键测试用例清单

**manifest.py（必须 100% 覆盖）**：合法 / 缺 path / 非法 kebab / path 越界 / path 不存在 / 重复名 / 非法日期 / 未知 model（warn 不 fail）/ 未知字段（warn 不 fail）/ 空 wikis 段。

**workspace.py（关键路径全覆盖）**：

- `find_root` 4 级优先级 + 优先级竞争
- `atomic_write` 创建 / 覆盖 / 中途失败回滚 / reparse 失败

**_compat.py（100% 覆盖）**：

- 真实 import 路径走真函数
- 软导入失败路径走 stub，相同输入相同输出
- 无 frontmatter 输入返回 `{}`

**commands（每命令 5-8 个 case）**：

- `init`：空目录 / 已存在 / `--workspace` 路径 / 含 git 仓
- `add`：**最重要**——mock subprocess 三态（成功 / 失败 / 依赖缺失）/ 冲突 / 目录已存在 / `--topic` 透传 / atomic write 失败
- `enter`：mock subprocess / `--dry-run` / claude 缺失 / system prompt 注入内容 / `--claude-md-check` 三档
- `config`：show / get / set / unset（必填字段拒绝 unset）
- 端到端 smoke：init → add → list → show → config set → remove

### 5.4 覆盖率目标

| 模块 | 目标 |
| --- | --- |
| `manifest.py` | 100% |
| `workspace.py` | 95%+ |
| `_compat.py` | 100% |
| `commands/*_cmd.py` | 80%+ |
| `cli.py` | 70%+ |

整体 `--cov-fail-under=85`。

### 5.5 CI 配置

`.github/workflows/test.yml`：

```yaml
name: test
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        python-version: ["3.6", "3.11"]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: ruff format --check .
      - run: ruff check .
      - run: pytest --cov=wiki_workspace --cov-fail-under=85
```

### 5.6 不测的（明确写出）

| 不测项 | 理由 |
| --- | --- |
| `llmw enter` 真启 Claude Code | 交互式 REPL，无 headless 模式 |
| 并发 `llmw add` / `config set` | MVP 不加锁 |
| 实际 `setup_wiki.py` 跑通 | 那是 llm-wiki-management skill 的测试范围 |
| Windows 路径 | v1 仅 Linux + macOS |

---

## 附录 A：风险与未决项

| 风险 / 未决项 | 影响 | 缓解 / 下一步 |
| --- | --- | --- |
| Claude Code `--add-dir` 是否加载 CLAUDE.md | workspace CLAUDE.md 是否在 `enter` 流程里生效 | 实现阶段 verify；若不成立，移除 `--add-dir <workspace_root>` |
| `setup_wiki.py` 当前不接受 `--no-git` flag | `add --no-git` 透传会失败 | 给 llm-wiki-management 提 issue / PR；或先不支持 `--no-git` |
| 多 wiki 同名 git remote 冲突 | 同一 workspace 内多个 wiki 用相同 git remote 时 push 冲突 | 不在 v1 解决；让用户各自管理 remote |
| workspace 跨文件系统（macOS APFS / Linux ext4） | atomic write 在 NFS 等不支持 rename 语义的 FS 上可能不安全 | 在 README 加 warning；测试覆盖本地 FS |

## 附录 B：依赖矩阵

| 依赖 | 用途 | 必需 | 备注 |
| --- | --- | --- | --- |
| `tomli` (py<3.11) / `tomllib` (py≥3.11) | 解析 .workspace.toml | ✅ | 标准库 / 单依赖 |
| `unittest.mock` | 测试 mock | ✅ | 标准库 |
| `pytest` | 测试框架 | dev-only | |
| `pytest-cov` | 覆盖率 | dev-only | |
| `ruff` | format + lint | dev-only | |
| llm-wiki-management | `add` / `show` 时调用 | 软 | 见 §1.4 |
| claude (Claude Code CLI) | `enter` 时 spawn | 软 | 见 §3.7 |