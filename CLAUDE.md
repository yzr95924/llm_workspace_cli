# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@MEMORY/MEMORY.md

## 仓库定位

`llmw`（命令同名）是一个轻量 Claude Code wrapper，管理 **一个 workspace（一个 git 仓）下的多个 wiki**：

- 一个 workspace = 一个目录 + `workspace.toml` + 多个 wiki 子目录
- 每个 wiki = 一个子目录，含 `raw/` + `wiki/` + `CLAUDE.md` + `wiki_metadata.toml`
- CLI **只**管元数据 + 启动 session；wiki 内部内容（ingest / lint / query）由 [`llm-wiki-management`](https://github.com/yzr95924/my_SKILL/tree/master/llm-wiki-management) skill 在 session 内负责

CLI 包 `llmw/` **绝不写** `raw/` 与 `wiki/` 下任何文件——这条不变量贯穿全仓。

## 常用命令

### 安装 / 卸载

```bash
./scripts/install.sh        # 生成 ~/.local/bin/llmw（PYTHONPATH 指向本仓库），按需注册 PATH
./scripts/uninstall.sh      # 逆操作：删 wrapper + 清所有候选 rc 的 PATH marker 块
```

`install.sh` 不动 `llmw/` 包本身，不碰 pip；Python 3.11+ 零第三方依赖，<3.11 需 `pip install 'tomli>=1.1'`。

### 测试 / Lint

```bash
ruff format --check .        # 格式化校验（CI lint job）
ruff check .                 # 静态检查（CI lint job）
pytest -q                    # 单元/集成测试（CI test job，矩阵 py3.7 + py3.11）

bash scripts/test/test_install_uninstall.sh
                            # install/uninstall 集成测试（用临时 HOME 隔离）
```

> **当前阶段测试优先级低**（详见 `MEMORY/test-priority-low.md`）：先做手动 smoke 跑通 prototype，再补 test。代码层面遵守可测性约束（业务与入口分离、Path 显式参数、subprocess 包装、异常类化），但**不**为"便于测试"而重构。agent 不要主动加测试代码。

> `llmw/models/` 子包已列入 `pyproject.toml` 的 `setuptools.packages`，wheel 与 editable 安装均含完整 4 子包（`llmw` / `llmw.workspace` / `llmw.wiki` / `llmw.models`）。`llmw model` 子命令 wheel 安装即可用。

### 手动 smoke 验收

完整脚本见 `README.md` 的 **Manual Smoke Test** 章节（包含 Phase 1 + Phase 2 model registry 两段）。每个命令至少跑一遍 happy path，所有 `✓` 通过 = prototype 阶段验收。

## 架构

### 顶层数据流

```
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
  │           └─▶ llmw.models.overlay (apply / inspect) → 写 <wiki>/.claude/settings.local.json (Local 层)
  │           │
  │           └─▶ subprocess(claude --add-dir + --system-prompt, 透传 os.environ)
  │
  └──▶ llmw.wiki.show / llmw.workspace.list  ──▶ resolve_for_wiki  (展示 model 来源)
```

### 关键不变量

1. **CLI 不写 wiki 内容**：不写 `raw/` / `wiki/` 下任何文件；只写 `workspace.toml`、`<wiki>/wiki_metadata.toml`、`workspace_models.toml`、以及 `init` 时建的 workspace `.gitignore`。**`<wiki>/CLAUDE.md` / `wiki/index.md` / `wiki/log.md` / `wiki/MEMORY/README.md` / `.gitignore` / 目录骨架** 由 CLI 在 `add` 时内联生成——读 SKILL 仓 `references/` 下的 `claude-md-template.md` 和 4 个 fixtures(见 I-2),按 `wiki-spec.md v0.3.0` §1-§6 渲染。
2. **CLI 内联实现 wiki 创建逻辑**(spec 0.2.0 起):原 `my_SKILL/.../scripts/setup_wiki.py` 已删除;CLI 通过 `llmw.wiki.init_wiki` 读 SKILL 仓 `references/claude-md-template.md` + `references/fixtures/{index,log,memory-readme,gitignore}.txt` 作为字节金标准,占位符替换后落盘;不复制 SKILL 运行时纪律(ingest / lint),只承担"出生形态"。SKILL 升级时 CLI 自动获益(`fixtures/README.md` 附录 A 的 `cmp -s` 比对保证字节一致)。
3. **SKILL references/ 路径固定**:SKILL 是 git submodule(`my_SKILL/llm-wiki-management/`),CLI 通过 `llmw.config.wiki_spec_templates_dir()` 定位 `references/` 目录;模块边界固定,无 env var 覆盖(对比旧 `LLMW_SKILL_SETUP_SCRIPT` 已废弃)。
4. **可执行入口位于 `bin/`**：`bin/llmw`（thin shell，调用 `python -m llmw`）是唯一入口；Python 包 `llmw/` 不放任何可执行入口。安装只复制 `bin/llmw` + 注册 `PATH`，**不动**包本身。
5. **model 真相源是 `workspace_models.toml`，不依赖环境变量**（详见 `MEMORY/model-ops-no-env-vars.md`）：wiki_metadata 用 model id 引用，`wiki enter` 把 resolved model 渲染进 `<wiki>/.claude/settings.local.json` 的 `env` 块（Local 层，优先级 > User）——这是 CLI 的主动行为（写文件），subprocess 透传 `os.environ`、不传 `--setting-sources`。**CLI 不读取 `os.environ.get("ANTHROPIC_MODEL")` 之类——overlay 交付是 CLI 主动行为，不是被动透传**。两个易错点：(a) `ANTHROPIC_MODEL` 用 `model.name`（网关模型名，如 `MiniMax-M3[1m]`），**不是 `model_id`**（内部 slug，如 `minimax-m3-1m`）——网关只认 name；(b) `enter` **不传** `--setting-sources`，依赖 Local 层（`settings.local.json`）env 块优先级 > User env 块，确保 overlay 生效（详见 `MEMORY/claude-settings-env-precedence.md`）。
6. **overlay 交付走 Local 层文件**（详见 `doc/design/09-workspace-model-registry.md` §9.5）：`wiki enter` 把 resolved model 渲染进 `<wiki>/.claude/settings.local.json` 的 `env` 块（Local 层，优先级 > User），lazy on enter。CLI **允许**写这**一个** launch-config 文件（I-5b，不放宽 I-1——仍不碰 `raw/` / `wiki/` / `CLAUDE.md`）。enter 的 subprocess 透传 `os.environ`、**不传** `--setting-sources`（恢复 user 配置；Local 层优先级高于 user env 块，overlay 稳赢）。
7. **api_key 永不明文出 stdout**：list / show / enter --dry-run 一律走 `llmw.models.redact.redact_api_key`（≤8 字符 → `***`；否则 `前3...末4`）。`workspace_models.toml` 落盘后 `chmod 600`（NFS 等不支持 chmod 的 FS best-effort 跳过）。

### 模块边界

| 子包 | 职责 | 不做什么 |
| --- | --- | --- |
| `llmw.cli` | argparse + 全局 flag + 分派 | 不含业务逻辑 |
| `llmw.config` | workspace 路径解析、SKILL 脚本路径、模板目录定位 | 不解析 workspace.toml |
| `llmw.errors` | 自定义异常（按 exit_code 1/2/3 分层） | — |
| `llmw.fsutil` | 原子写（tmp + fsync + rename）、ISO8601 时间 | — |
| `llmw._compat` | tomllib (3.11+) / tomli (<3.11) 兼容层 + 手写 toml dump | — |
| `llmw.workspace.store` | workspace.toml 读写 + schema 校验 | 不做 wiki 操作、不做 init 业务 |
| `llmw.workspace.manager` | `init` / `config` / `list` 业务；`init` 写 workspace `.gitignore` | 不写 wiki 文件、不读 wiki_metadata.toml |
| `llmw.wiki.store` | wiki_metadata.toml 读写 + schema v2 + 模板填充 | 不写 workspace.toml、不调 init_wiki |
| `llmw.wiki.init_wiki` | `render_and_write` + `check_not_initialized`：读 SKILL `references/` 模板与 fixtures,占位符替换,atomic_write 落盘 wiki 骨架(spec §1-§6) | 不写 wiki_metadata.toml、不进 wiki 业务流 |
| `llmw.wiki.git_init` | `init`：spec §7 opt-in git 初始化(前置不通过则 warn 跳过) | 不写元数据 |
| `llmw.wiki.manager` | `add` / `remove` / `show` / `config` 业务；`add` 调 init_wiki (+ `--git` 时调 git_init);校验 model_id | 不进 wiki 内部、不读 wiki/ 内容 |
| `llmw.wiki.enter` | 启动 Claude Code session：resolve model → `overlay.apply` 写 `<wiki>/.claude/settings.local.json` → `claude --add-dir [--system-prompt]`（透传 os.environ，无 --setting-sources） | 不写元数据 |
| `llmw.models.overlay` | `render`/`inspect`/`apply`：resolved ModelEntry → `<wiki>/.claude/settings.local.json` 的 env 块；幂等合并 + chmod 600 | — |
| `llmw.models.store` | workspace_models.toml 读写 + schema v2 + 字段校验 + chmod 600 | 不做 CRUD 业务、不做 resolve |
| `llmw.models.redact` | `redact_api_key` 单一脱敏出口 | — |
| `llmw.models.resolve` | `resolve_for_wiki` 单一查找入口：wiki.model 优先，否则 registry 默认 | 不做 CRUD |
| `llmw.models.manager` | `add` / `list` / `show` / `set-default` / `unset-default` / `remove` 业务；保证 `is_default` 全局唯一 | 不直接读 toml 文件（走 store.load） |

### 全局 flag 与退出码

全局 flag：`--workspace PATH` / `--json` / `--debug` / `--quiet / -q`。

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 用户错误（参数非法、wiki 不存在、registry 字段错误等） |
| 2 | 环境错误（SKILL submodule 缺失、claude 不在 PATH 等） |
| 3 | 内部错误（未捕获异常） |

错误格式化统一走 `llmw.errors.format_error`，格式 `[llmw] error: ...` / `[llmw] hint: ...`；`--debug` 加 traceback。

## 数据模型

三份元数据文件，都走原子写（`fsutil.atomic_write` = `tmp + fsync + os.replace`）：

- **`<workspace>/workspace.toml`**：schema v1；`schema_version` / `created_at` / `templates_version`（只读）+ `default_model`（可 set/unset）+ `[wikis.<name>]` 注册表
- **`<workspace>/workspace_models.toml`**（Phase 2）：schema v2；`schema_version` / `created_at` / `updated_at`（只读，CLI 自动 bump）+ `[[models]]` 数组，每条含 `model_id` / `name` / `base_url` / `api_key` / 可选 `is_default`。约束：model_id 唯一（`^[a-z0-9_-]{1,64}$`，复用 wiki NAME_RE），`is_default` 全局至多 1 条。**不入 git**——`init` 时通过 workspace `.gitignore`（带 `>>> llmw (managed by llmw) <<<` 标记段）自动排除。
- **`<wiki>/wiki_metadata.toml`**：schema v2；`schema_version` / `name` / `topic` / `created_at` / `updated_at`（只读，CLI 自动 bump）+ `display_name` / `description` / `tags` / `model`（可 set/unset）。`model` 字段存的是 registry 中的 `model_id`，不是 url / key。

完整 schema 与字段规则见 `doc/design/04-data-model.md` 与 `doc/design/09-workspace-model-registry.md`。

### `wiki enter` 的 model 解析

`llmw/wiki/enter.py` 通过 `llmw/models/resolve.py:resolve_for_wiki` 拿最终 `ModelEntry`，优先级：

1. `<wiki>/wiki_metadata.toml` 的 `model` 字段 → 必须在 registry 中存在，否则 `ModelNotInRegistry` 阻断 enter
2. 否则 registry 中 `is_default=true` 的唯一条目

`overlay.apply` 写 `<wiki>/.claude/settings.local.json` 的 env 块（Local 层，优先级 > User）：

```
ANTHROPIC_MODEL      = <model.name>    # 网关模型名（如 MiniMax-M3[1m]），非 model_id slug
ANTHROPIC_BASE_URL   = <base_url>
ANTHROPIC_AUTH_TOKEN = <api_key>
```

subprocess 透传 `os.environ`、**不传** `--setting-sources`（恢复 user 配置；Local 层 env 块优先级高于 user env 块，overlay 稳赢，见 `MEMORY/claude-settings-env-precedence.md`）。`enter --dry-run` 打印 overlay file（路径 + 是否需要更新）+ api_key 走 redact，不执行 claude、不写文件。

## 关键设计文档

- `doc/design/00-overview.md` — 顶层架构、模块边界、关键不变量（**先读**）
- `doc/design/01-workspace-management.md` — `init` / `config` / `list`
- `doc/design/02-wiki-crud.md` — `wiki add` / `remove` / `show` / `config`
- `doc/design/03-wiki-enter.md` — `wiki enter`（核心命令）
- `doc/design/04-data-model.md` — workspace.toml / wiki_metadata.toml schema
- `doc/design/05-templates-submodule.md` — SKILL `references/` 字节金标准 + `my_SKILL` 集成(spec 0.2.0 起取代原 `templates/` 章节)
- `doc/design/06-error-handling.md` — 错误场景、退出码、原子写策略
- `doc/design/07-testing.md` — 测试策略（prototype 阶段延后）
- `doc/design/08-install-uninstall.md` — install/uninstall 设计
- `doc/design/09-workspace-model-registry.md` — Phase 2 model registry

## 项目规约（MEMORY/）

仓库内 `MEMORY/` 目录是项目级"为什么 + 边界"记忆的存放点（**不写个人 memory 目录**）。索引由顶部 `@MEMORY/MEMORY.md` 自动加载；每条规则一份独立 markdown，带 frontmatter。提交进代码仓以便协作方看见 + 跟随代码历史回溯。

## 开发注意事项

- **不要写 wiki 内容**：任何对 `raw/` 或 `wiki/` 的写入都是违反不变量 I-1 的。
- **不要复活 setup_wiki.py**：spec 0.2.0 起已删除(SKILL 仓明确),wiki 骨架由 CLI 内联生成(读 SKILL `references/`);不要"为了模块化"把渲染拆回脚本。
- **不要让 model 走环境变量被读出来**：`os.environ.get("ANTHROPIC_*")` 这类读取一律禁止；model 配置完全由 `workspace_models.toml` 掌控，enter 的 overlay 交付是 CLI 主动行为（写 `<wiki>/.claude/settings.local.json`）。
- **api_key 走 redact 出口**：所有 list / show / dry-run 打印前必须过 `redact_api_key`；不要自己写 `key[:3] + "..." + key[-4:]`。
- **schema 校验全在 store 层**：manager / resolve 不重新校验字段；想加新字段就改对应 store 的 dataclass + validate 函数。
- **NFS 不安全**：原子写走 POSIX `rename`，本地 ext4 / APFS 安全；**不要在 NFS 挂载的 workspace 上跑 `llmw`**。`workspace_models.toml` 在 NFS 上 `chmod 600` 会 silently 失败，权限安全是 best-effort。
- **CI 矩阵**：lint job 跑 ruff（py3.11）；test job 跑 pytest，矩阵 py3.7 + py3.11，用官方 python 容器（不受 runner 镜像变动影响）；3.7 上不装 ruff（`pip install -e . "pytest>=7,<8" "pytest-cov>=4"`）。
