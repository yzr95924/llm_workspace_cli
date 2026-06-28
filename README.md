# llmw — Wiki Workspace CLI

管理一个由 [`llm-wiki-management`](https://github.com/yzr95924/my_SKILL/tree/master/llm-wiki-management) skill 创建的 wiki 集合（一个 workspace = 一个 git 仓，含多个 wiki 子目录）。

## 安装

### 1. 克隆仓库（含 submodule）

```bash
git clone https://github.com/yzr95924/llm_workspace_cli.git
cd llm_workspace_cli
git submodule update --init --recursive
```

> ⚠ `git submodule update` 必须跑，否则 `wiki add` 报 `SkillMissing`。

### 2. 安装 Python 包（开发模式）

```bash
pip install -e .
```

需要 Python 3.7+。3.10 及以下需 `pip install tomli`。

### 3. 加 `bin/llmw` 到 PATH

```bash
export PATH="$(pwd)/bin:$PATH"
```

> Phase 2 会做正式 install/uninstall 脚本（自动加 `~/.local/bin/llmw` + PATH 注册）。

## 快速上手

```bash
# 初始化 workspace（默认 ~/yzr_llm_workspace）
llmw init
cd ~/yzr_llm_workspace

# 新建一个 wiki（非 TTY 需全 flag）
llmw wiki --name=llm-systems add \
  --topic "LLM Systems" \
  --display-name "LLM 系统研究" \
  --description "跟踪 LLM 系统相关论文与博客" \
  --tag research --tag llm \
  --model claude-sonnet-4-6

# 查看
llmw list
llmw wiki --name=llm-systems show

# 编辑 metadata（交互模式）
llmw wiki --name=llm-systems config

# 配置 workspace 级默认 model
llmw config set default_model claude-sonnet-4-6

# 启动 Claude Code session（核心命令）
llmw wiki --name=llm-systems enter
# 先看命令再跑:
llmw wiki --name=llm-systems enter --dry-run

# 移除 wiki
llmw wiki --name=llm-systems remove          # 仅取消注册
llmw wiki --name=llm-systems remove --purge --yes   # 同时删子目录
```

## 命令清单

| 命令 | 作用 |
| --- | --- |
| `llmw init [--path DIR] [--no-git]` | 初始化 workspace |
| `llmw config [get\|set\|unset] KEY [VALUE]` | 读写 `workspace.toml`；无参数 + TTY 进交互模式 |
| `llmw list [--tag TAG]...` | 列出 wiki（`--json` 输出 JSON） |
| `llmw wiki --name=X add [--topic ...] [--display-name ...] [--description ...] [--tag ...] [--model ...] [--no-setup]` | 新建 wiki |
| `llmw wiki --name=X remove [--purge] [--yes]` | 移除 wiki |
| `llmw wiki --name=X show` | 查看 wiki 详情 |
| `llmw wiki --name=X config [get\|set\|unset] KEY [VALUE]` | 读写 `wiki_metadata.toml`；无参数默认交互模式 |
| `llmw wiki --name=X enter [--dry-run]` | 启动 Claude Code session（Phase 1 不传 model） |

全局 flag：`--workspace PATH` / `--json` / `--debug` / `--quiet` / `-q`。

## 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 用户错误（参数非法、wiki 不存在等） |
| 2 | 环境错误（SKILL submodule 缺失、claude 不在 PATH 等） |
| 3 | 内部错误（未捕获异常） |

## Manual Smoke Test（prototype 阶段验收清单）

每个命令至少跑一遍 happy path：

```bash
# 准备临时 workspace
TMPWS=$(mktemp -d)

# init
llmw init --path "$TMPWS" --no-git
test -f "$TMPWS/workspace.toml" && echo "✓ init"

# config (非 TTY 自动打印字段列表后退出 0)
LLMW_WORKSPACE="$TMPWS" llmw config
LLMW_WORKSPACE="$TMPWS" llmw config set default_model claude-sonnet-4-6
LLMW_WORKSPACE="$TMPWS" llmw config get default_model
LLMW_WORKSPACE="$TMPWS" llmw config unset default_model

# list (空)
LLMW_WORKSPACE="$TMPWS" llmw list

# add (非 TTY 全 flag)
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo add \
  --topic "Foo" --display-name "Foo" --description "x" \
  --tag a --tag b --model claude-sonnet-4-6
test -d "$TMPWS/foo/raw" -a -d "$TMPWS/foo/wiki" -a -f "$TMPWS/foo/CLAUDE.md" -a -f "$TMPWS/foo/wiki_metadata.toml" \
  && echo "✓ add (files ok)"

# list (有 wiki)
LLMW_WORKSPACE="$TMPWS" llmw list
LLMW_WORKSPACE="$TMPWS" llmw list --json
LLMW_WORKSPACE="$TMPWS" llmw list --tag a

# show
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo show
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo show --json

# config set/get
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo config set tags alpha,beta
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo config get tags

# enter --dry-run
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter --dry-run

# remove
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo remove --purge --yes
test ! -d "$TMPWS/foo" && echo "✓ remove --purge"

rm -rf "$TMPWS"
```

每个 echo 出现 = 该步 happy path 通过。所有 `✓` 步骤都通过 = prototype 阶段验收。

## Phase 边界

| 维度 | Phase 1（当前） | Phase 2（暂未做） |
| --- | --- | --- |
| workspace / wiki 元数据 | ✅ | |
| 基础 CRUD | ✅ | |
| Claude Code session 启动 | ✅（不传 model） | |
| model registry | ❌ | ✅（`workspace_models.toml` + `llmw model` 命令） |
| ingest / lint / query 包装 | ❌（留给 SKILL session 内） | |
| install / uninstall 脚本 | ❌（手动加 PATH） | ✅ |

详见 `doc/design/` 各章节。

## 并发 / 文件系统

原子写走 `tmp + fsync + rename`（POSIX 原子）。本地文件系统（ext4 / APFS）安全。
**NFS 不安全**——不要在 NFS 挂载的 workspace 上跑 `llmw`。
