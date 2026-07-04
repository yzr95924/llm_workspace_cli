# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

@MEMORY/MEMORY.md

## 项目定位

`llmw`（命令同名）是一个轻量 AI agent 调起的 wrapper，管理 **一个 workspace（一个 git 仓）下的多个 wiki**：

- 一个 workspace = 一个目录 + `workspace.toml` + 多个 wiki 子目录
- 每个 wiki = 一个子目录，含 `raw/` + `wiki/` + `CLAUDE.md` + `wiki_metadata.toml`
- CLI **只**管元数据 + 启动 session；wiki 内部内容（ingest / lint / query）由
  [`llm-wiki-management`](https://github.com/yzr95924/my_SKILL/tree/master/llm-wiki-management)
  skill 在 session 内负责
- CLI 包 `llmw/` **绝不写** `raw/` 与 `wiki/` 下任何文件——这条不变量贯穿全仓

## 常用命令

### 安装 / 卸载

```bash
./scripts/install.sh        # 生成 ~/.local/bin/llmw（PYTHONPATH 指向本仓库），按需注册 PATH
./scripts/uninstall.sh      # 逆操作：删 wrapper + 清所有候选 rc 的 PATH marker 块
```

`install.sh` 不动 `llmw/` 包本身，不碰 pip；Python 3.11+ 零第三方依赖，<3.11 需
`pip install 'tomli>=1.1'`。

### 测试 / Lint

```bash
ruff format --check .        # 格式化校验（CI lint job）
ruff check .                 # 静态检查（CI lint job）
pytest -q                    # 单元/集成测试（CI test job，矩阵 py3.7 + py3.11）

bash scripts/test/test_install_uninstall.sh
                            # install/uninstall 集成测试（用临时 HOME 隔离）
```

> **当前阶段测试优先级低**（短条目，详见 `MEMORY/MEMORY.md` 短条目区）：先做手动 smoke 跑通 prototype，再补
> test。代码层面遵守可测性约束（业务与入口分离、Path 显式参数、subprocess 包装、异常类化），但**不**
> 为"便于测试"而重构。agent 不要主动加测试代码。
> `llmw/models/` 子包已列入 `pyproject.toml` 的 `setuptools.packages`，wheel 与 editable 安装均含完整
> 4 子包（`llmw` / `llmw.workspace` / `llmw.wiki` / `llmw.models`）。`llmw model` 子命令 wheel
> 安装即可用。
>

### 手动 smoke 验收

完整脚本见 `README.md` 的 **Manual Smoke Test** 章节（包含 Phase 1 + Phase 2 model registry 两段）。
每个命令至少跑一遍 happy path，所有 `✓` 通过 = prototype 阶段验收。

## 架构

### 顶层数据流

```text
用户
  │
  ▼
llmw.cli (argparse + 分派)
  │
  ├──▶ llmw.workspace.manager  ──▶ llmw.workspace.store  ──▶ workspace.toml
  │            │
  │            └─(init)─▶ workspace/.gitignore (含 workspace_models.toml 行)
  │
  ├──▶ llmw.wiki.manager       ──▶ llmw.wiki.store       ──▶ <wiki>/wiki_metadata.toml
  │           │
  │           ├─(add)──▶ llmw.wiki.init_wiki ──▶ <wiki>/raw/, <wiki>/wiki/, <wiki>/CLAUDE.md
  │           │           (读 my_SKILL/.../references/ 下的模板与 fixtures)
  │           │
  │           └─(add --git)──▶ llmw.wiki.git_init ──▶ git init + .gitkeep + commit (spec §7)
  │
  ├──▶ llmw.models.manager     ──▶ llmw.models.store     ──▶ workspace_models.toml
  │           │                          │
  │           └─(add)──▶ chmod 600       └─▶ redact.api_key (list/show 输出)
  │
  ├──▶ llmw.wiki.enter         ──▶ llmw.models.resolve (wiki → ModelEntry)
  │           │
  │           └─▶ llmw.models.overlay (apply / inspect) → 写 wiki 启动配置（Local 层）
  │           │
  │           └─▶ subprocess(agent CLI 命令，透传 os.environ)
  │
  └──▶ llmw.wiki.show / llmw.workspace.list  ──▶ resolve_for_wiki  (展示 model 来源)
```

> 启动配置文件路径与 agent CLI 精确启动命令属于工具绑定内容——其它 agent 实现可能不同；详见
> `CLAUDE.md` 薄壳逃生舱。

### 关键不变量（核心 3 条）

完整 7 条不变量维护在原 `CLAUDE.md`（迁移备份 `.migration-backup/CLAUDE.md.original`）。
此处只列核心 3 条 + 指向 MEMORY 详述：

1. **CLI 不写 wiki 内容**——只写 `workspace.toml` / `<wiki>/wiki_metadata.toml` /
   `workspace_models.toml` + workspace `.gitignore`。`<wiki>/CLAUDE.md` / `wiki/index.md` /
   `wiki/log.md` / `wiki/MEMORY/README.md` / `.gitignore` / 目录骨架 由 CLI 在 `add` 时内联生成——
   读 SKILL 仓 `references/` 下的 `claude-md-template.md` 和 4 个 fixtures，按 `wiki-spec.md v0.3.0`
   §1-§6 渲染。
2. **CLI 内联实现 wiki 创建**（spec 0.2.0 起）：原 `my_SKILL/.../scripts/setup_wiki.py` 已删除；
   CLI 通过 `llmw.wiki.init_wiki` 读 SKILL 仓 `references/claude-md-template.md` +
   `references/fixtures/{index,log,memory-readme,gitignore}.txt` 作为字节金标准，占位符替换后落盘；
   不复制 SKILL 运行时纪律（ingest / lint），只承担"出生形态"。SKILL 升级时 CLI 自动获益
   （`fixtures/README.md` 附录 A 的 `cmp -s` 比对保证字节一致）。
3. **overlay 交付走 Local 层文件**——model 真相源是 `workspace_models.toml`，不依赖环境变量
   （[[model-ops-no-env-vars]]）；wiki enter 渲染 resolved model 进 Local 层 `settings.local.json`
   的 `env` 块（Local 层优先级 > User 层），lazy on enter。`ANTHROPIC_MODEL` 用 `model.name`
   （网关模型名，如 `MiniMax-M3[1m]`），不是 `model_id` slug；启动时透传 `os.environ`、依赖
   Local 层 `env` 块优先级稳赢（[[agent-settings-env-precedence]]）。
   - 详细见 [[overlay-habit-template]]（习惯级 env key 常量）

剩余 4 条（SKILL references/ 路径固定 / 可执行入口在 `bin/` / api_key 永不明文出 stdout /
CLI 内联 wiki 骨架的字节一致性保证）见设计文档与备份 CLAUDE.md。

### 模块边界

| 子包 | 职责 | 不做什么 |
| --- | --- | --- |
| `llmw.cli` | argparse + 全局 flag + 分派 | 不含业务逻辑 |
| `llmw.config` | workspace 路径解析、SKILL 脚本路径、模板目录定位 | 不解析 workspace.toml |
| `llmw.errors` | 自定义异常（按 exit_code 1/2/3 分层） | — |
| `llmw.fsutil` | 原子写（tmp + fsync + rename）、ISO8601 时间 | — |
| `llmw._compat` | tomllib (3.11+) / tomli (<3.11) 兼容层 + 手写 toml dump | — |
| `llmw.workspace.store` | workspace.toml 读写 + schema 校验 | 不做 wiki 操作、不做 init 业务 |
| `llmw.workspace.manager` | init/config/list 业务；init 写 workspace `.gitignore` | 不写 wiki 文件、不读 wiki_metadata.toml |
| `llmw.wiki.store` | wiki_metadata.toml 读写 + schema v2 + 模板填充 | 不写 workspace.toml、不调 init_wiki |
| `llmw.wiki.init_wiki` | 渲染骨架（spec §1-§6）；读 references/fixtures → atomic_write | 不写 wiki_metadata.toml、不进 wiki 业务流 |
| `llmw.wiki.git_init` | `init`：spec §7 opt-in git 初始化（前置不通过则 warn 跳过） | 不写元数据 |
| `llmw.wiki.manager` | add/remove/show/config 业务；add 调 init_wiki 与 git_init；校验 model_id | 不进 wiki 内部、不读 wiki/ 内容 |
| `llmw.wiki.enter` | 启动 session：resolve model → `overlay.apply` 写启动配置 → agent CLI 子进程（透传 os.environ） | 不写元数据 |
| `llmw.models.overlay` | `render`/`inspect`/`apply`：resolved ModelEntry → 启动配置 `env` 块；幂等合并 + chmod 600 | — |
| `llmw.models.store` | workspace_models.toml 读写 + schema v2 + 字段校验 + chmod 600 | 不做 CRUD 业务、不做 resolve |
| `llmw.models.redact` | `redact_api_key` 单一脱敏出口 | — |
| `llmw.models.resolve` | `resolve_for_wiki` 单一查找入口：wiki.model 优先，否则 registry 默认 | 不做 CRUD |
| `llmw.models.manager` | CRUD + set/unset-default 业务；保证 `is_default` 全局唯一 | 不直接读 toml 文件（走 store.load） |

### 全局 flag 与退出码

全局 flag：`--workspace PATH` / `--json` / `--debug` / `--quiet / -q`。

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 用户错误（参数非法、wiki 不存在、registry 字段错误等） |
| 2 | 环境错误（SKILL submodule 缺失、agent CLI 不在 PATH 等） |
| 3 | 内部错误（未捕获异常） |

错误格式化统一走 `llmw.errors.format_error`，格式 `[llmw] error: ...` / `[llmw] hint: ...`；
`--debug` 加 traceback。

## 数据模型

三份元数据文件，都走原子写（`fsutil.atomic_write` = `tmp + fsync + os.replace`）：

- **`<workspace>/workspace.toml`**：schema v1；`schema_version` / `created_at` / `templates_version`
  （只读）+ `default_model`（可 set/unset）+ `[wikis.<name>]` 注册表
- **`<workspace>/workspace_models.toml`**（Phase 2）：schema v2；`schema_version` / `created_at` /
  `updated_at`（只读，CLI 自动 bump）+ `[[models]]` 数组，每条含 `model_id` / `name` / `base_url` /
  `api_key` / 可选 `is_default`。约束：model_id 唯一（`^[a-z0-9_-]{1,64}$`，复用 wiki NAME_RE），
  `is_default` 全局至多 1 条。**不入 git**——`init` 时通过 workspace `.gitignore`（带
  `>>> llmw (managed by llmw) <<<` 标记段）自动排除。
- **`<wiki>/wiki_metadata.toml`**：schema v2；`schema_version` / `name` / `topic` / `created_at` /
  `updated_at`（只读，CLI 自动 bump）+ `display_name` / `description` / `tags` / `model`（可
  set/unset）。`model` 字段存的是 registry 中的 `model_id`，不是 url / key。

完整 schema 与字段规则见 `MEMORY/` 内对应模块的边界条目。

### `wiki enter` 的 model 解析

`llmw/wiki/enter.py` 通过 `llmw/models/resolve.py:resolve_for_wiki` 拿最终 `ModelEntry`，优先级：

1. `<wiki>/wiki_metadata.toml` 的 `model` 字段 → 必须在 registry 中存在，否则
   `ModelNotInRegistry` 阻断 enter
2. 否则 registry 中 `is_default=true` 的唯一条目

`overlay.apply` 写 wiki 启动配置 `env` 块（Local 层，优先级 > User）：

```text
ANTHROPIC_MODEL      = <model.name>    # 网关模型名（如 MiniMax-M3[1m]），非 model_id slug
ANTHROPIC_BASE_URL   = <base_url>
ANTHROPIC_AUTH_TOKEN = <api_key>
```

agent CLI 子进程透传 `os.environ`、依赖 Local 层 `env` 块优先级稳赢（[[agent-settings-env-precedence]]）。
`enter --dry-run` 打印 overlay file（路径 + 是否需要更新）+ api_key 走 redact，不执行 agent CLI、
不写文件。

## 项目规约（MEMORY/）

仓库内 `MEMORY/` 目录是项目级"为什么 + 边界"记忆的存放点（**不写个人 memory 目录**）。索引由顶部
`@MEMORY/MEMORY.md` 自动加载；每条规则一份独立 markdown，带 frontmatter。提交进代码仓以便协作方看见
并跟随代码历史回溯。

**`@MEMORY/MEMORY.md` 是项目级规则的唯一真源**——agent 会话级 memory（具体路径因 agent 而异）只放
指向本仓 `MEMORY/MEMORY.md` 的指针，不再持有内容副本，避免随代码仓迁移 / 协作时失同步。

**两类条目形式（按颗粒度选，写新条目前必读 [[memory-entry-conventions]]）**：

- **完整 memory**——含设计决策 / 工作流约束 / 跨文件关系，需要展开"为什么"或"将来怎么用" →
  建 `MEMORY/<slug>.md`（含 frontmatter + 正文），索引里以 `[Title](<slug>.md) — 一句话`
  指针指向
- **短 memory**——一句话能讲清的纯事实 / 单一偏好 / 无需 why+how 的 reminder → 直接在
  `MEMORY/MEMORY.md` 索引区以 `- **<短名>** — <一句事实>` 承载，不单独建 `.md`

**判别尺度**：能否在 30 字内独立表达"为什么"或"将来怎么用"——能 → 短条目；不能 → 完整条目。
纪律（追加末尾 / 不删既有 / frontmatter 三项必填 / `[[slug]]` 互链）见 [[memory-entry-conventions]]
与 [[memory-persistence-policy]]。

## 开发注意事项

- **不要写 wiki 内容**：任何对 `raw/` 或 `wiki/` 的写入都是违反不变量 I-1 的。
- **不要复活 setup_wiki.py**：spec 0.2.0 起已删除（SKILL 仓明确），wiki 骨架由 CLI 内联生成
  （读 SKILL `references/`）；不要"为了模块化"把渲染拆回脚本。
- **不要让 model 走环境变量被读出来**：`os.environ.get("ANTHROPIC_*")` 这类读取一律禁止；
  model 配置完全由 `workspace_models.toml` 掌控，enter 的 overlay 交付是 CLI 主动行为
  （写启动配置）。详 [[model-ops-no-env-vars]]。
- **api_key 走 redact 出口**：所有 list / show / dry-run 打印前必须过 `redact_api_key`；
  不要自己写 `key[:3] + "..." + key[-4:]`。
- **schema 校验全在 store 层**：manager / resolve 不重新校验字段；想加新字段就改对应 store
  的 dataclass + validate 函数。
- **NFS 不安全**：原子写走 POSIX `rename`，本地 ext4 / APFS 安全；**不要在 NFS 挂载的 workspace
  上跑 `llmw`**。`workspace_models.toml` 在 NFS 上 `chmod 600` 会 silently 失败，权限安全是
  best-effort。
- **CI 矩阵**：lint job 跑 ruff（py3.11）；test job 跑 pytest，矩阵 py3.7 + py3.11，用官方
  python 容器（不受 runner 镜像变动影响）；3.7 上不装 ruff
  （`pip install -e . "pytest>=7,<8" "pytest-cov>=4"`）。
