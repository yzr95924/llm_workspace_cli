# 00 · 顶层架构与模块边界

## 定位

CLI（内部包名 `llmw`，对外命令 `llmw`）是 `@my_SKILL/llm-wiki-management` skill 的
**轻量 Claude Code wrapper**：

- **不**实现 wiki 内容管理（ingest / lint / query）
- **只**做 workspace 与 wiki 元数据管理 + 启动 Claude Code session

Skill 负责 wiki 内部的"复利累积"（raw → wiki 摘要 → log），CLI 负责 wiki 集合的
"目录与启动"。两者职责严格分离。

## 关键不变量（贯穿全 CLI）

### I-1：CLI 不写 wiki 内容

- **不**写 `raw/` 下任何文件
- **不**写 `wiki/` 下任何文件（source / entity / concept / comparison / synthesis 都不写）
- **只**写 CLI 自己的元数据：`workspace.toml` 与 `<wiki>/wiki_metadata.toml`

> 例外：`<wiki>/CLAUDE.md` 由 `setup_wiki.py` 在 `add` 时创建——CLI 不参与该文件的任何写入或编辑。

### I-2：CLI 不实现 wiki 创建逻辑

- `add` 的 wiki 目录结构（`raw/`、`wiki/` 子目录、初始 `CLAUDE.md`）**必须**由
  `my_SKILL/llm-wiki-management/scripts/setup_wiki.py` 创建
- CLI 不复制 setup_wiki.py 的逻辑、不假设 raw/ 与 wiki/ 的存在形式
- 这是为了在 SKILL 升级时（如 CLAUDE.md 模板调整、新增初始目录）CLI 自动获益

### I-3：SKILL 路径固定

- SKILL 是 CLI 仓库的 **git submodule**（位于 `my_SKILL/llm-wiki-management/`）
- setup_wiki.py 的路径相对 CLI 包内位置**固定**——不需要环境变量配置
- 唯一可覆盖路径：环境变量 `LLMW_SKILL_SETUP_SCRIPT`（手动指定场景）

### I-4：可执行入口位于 `bin/`，与 Python 包分离

- CLI 唯一可执行入口是仓库根目录下的 `bin/llmw`（thin shell，调用 `python -m llmw`）
- Python 包 `llmw/` 不放任何可执行入口；`bin/llmw` 是包外引导文件
- 安装到用户环境只动 `bin/llmw` 的复制与 `PATH` 注册，**不动** `llmw/` 包本身
- 卸载只需删除 `bin/llmw` 副本与 `PATH` 条目，仓库其余文件可保留

## 模块边界

```
llmw/
├── __main__.py            # python -m llmw 入口
├── cli.py                 # argparse 顶层 + 分派
├── config.py              # 全局配置（环境变量、默认 workspace 路径）
├── errors.py              # 自定义异常
│
├── workspace/
│   ├── store.py           # workspace.toml 读写 + 默认路径解析 + git 状态探测
│   └── manager.py         # init / config / list 业务
│
└── wiki/
    ├── store.py           # wiki_metadata.toml 读写 + schema 校验
    ├── manager.py         # add / remove / show / config 业务
    └── enter.py           # 启动 Claude Code session
```

| 子包 | 职责 | 不做什么 |
| --- | --- | --- |
| `llmw.workspace.store` | `workspace.toml` 读写、默认路径解析、git 状态探测 | 不做 wiki 操作、不做 init 业务 |
| `llmw.workspace.manager` | `init` / `config` / `list` 业务 | 不写 wiki 文件、不读 wiki_metadata.toml |
| `llmw.wiki.store` | `wiki_metadata.toml` 读写 + schema 校验 | 不调 setup_wiki.py、不写 workspace.toml |
| `llmw.wiki.manager` | `add` / `remove` / `show` / `config` 业务 | 不进 wiki 内部、不读 wiki/ 内容 |
| `llmw.wiki.enter` | 启动 Claude Code session（cd + claude 命令构造 + 执行） | 不写元数据 |
| `llmw.config` | 全局配置（环境变量 + 默认 workspace 路径） | 不解析 workspace.toml |
| `llmw.cli` | argparse + 分派 + 全局 flag | 不含业务逻辑 |
| `llmw.errors` | 自定义异常 | — |

## 数据流（高层视角）

```
用户
  │
  ▼
llmw.cli (argparse + 分派)
  │
  ├──▶ llmw.workspace.manager  ──▶ llmw.workspace.store  ──▶ workspace.toml
  │
  ├──▶ llmw.wiki.manager       ──▶ llmw.wiki.store       ──▶ <wiki>/wiki_metadata.toml
  │           │
  │           └─(add)──▶ my_SKILL/.../setup_wiki.py ──▶ <wiki>/raw/, <wiki>/wiki/, <wiki>/CLAUDE.md
  │
  └──▶ llmw.wiki.enter        ──▶ subprocess(claude + --add-dir + --system-prompt)
                                          ▲
                                          │
                                  <wiki>/CLAUDE.md (cat 原样注入)
```

## Phase 边界

| 维度 | Phase 1（本批） | Phase 2（暂不在本批） |
| --- | --- | --- |
| workspace 元数据 | ✅ | |
| wiki CRUD | ✅ | |
| Claude Code session 启动 | ✅ | |
| ingest / lint / query 包装 | ❌（留给 SKILL） | |
| 跨 wiki status / search | ❌ | ✅ |
| model registry | ❌ | ✅ |
| install / uninstall 脚本 | ❌ | ✅（依赖 model registry 设计收敛） |

详见各子功能章节。

## Build & Install（延后）

- 本批设计不包含 install / uninstall 脚本
- 未来设计该脚本时需覆盖：
  - `bin/llmw` 复制到用户环境（典型位置：`~/.local/bin/llmw`）
  - `PATH` 注册（追加到 shell rc：`.bashrc` / `.zshrc` 等）
  - 卸载时反向操作（删副本、清理 `PATH` 条目）
- 详细设计见 [`08-install-uninstall.md`](08-install-uninstall.md)