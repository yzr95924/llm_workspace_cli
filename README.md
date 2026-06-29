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

### 2. 安装命令（推荐）

```bash
./scripts/install.sh
```

生成 `~/.local/bin/llmw`（wrapper 内嵌本仓库路径，用 `PYTHONPATH` 解析 `llmw` 包，**无需 pip/venv**），并在 `~/.local/bin` 不在 `PATH` 时自动往 shell rc 注册一个 marker 块。装完按提示 `source ~/.zshrc`（或重开终端）即可。

> 全程不动 `llmw/` 包本身、不碰 pip。Python 3.11+ 零第三方依赖；<3.11 运行时需 `pip install 'tomli>=1.1'`。

卸载（只删 wrapper + PATH marker，**不删仓库、不删 workspace 数据**）：

```bash
./scripts/uninstall.sh
```

### 3. 备选：pip 安装

入口是仓库根的 `bin/llmw`（thin shell，`exec python3 -m llmw`）。若更喜欢走 pip：

```bash
pip install -e .
```

> 系统 Python（Homebrew 等 PEP 668 externally-managed）会拒绝全局 install，改用 `pip install -e . --user`、`pipx install -e .` 或先建 venv。

## 快速上手

```bash
# 初始化 workspace（默认 ~/yzr_llm_wiki_workspace）
llmw init
cd ~/yzr_llm_wiki_workspace

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

## 目录结构

```
llm_workspace_cli/                # 仓库根
├── bin/                          # 唯一可执行入口：thin shell → python -m llmw
├── llmw/                         # Python 包
│   ├── workspace/                # workspace 级：init / config / list + workspace.toml 读写
│   └── wiki/                     # wiki 级：add / remove / show / config / enter + wiki_metadata.toml 读写
├── scripts/                      # install / uninstall shell 脚本及其集成测试
├── templates/                    # wiki add 时使用的元数据模板
├── doc/                          # 设计文档（按子功能拆分）+ 实施计划
├── MEMORY/                       # 项目级"为什么 + 边界"记忆（提交进仓库）
├── my_SKILL/                     # git submodule，外部 SKILL 提供 setup_wiki.py
├── tests/                        # 当前阶段测试优先级低，先做手动 smoke（见下方）
├── .github/workflows/test.yml    # CI: ruff lint + pytest（py3.7 / py3.11）
└── pyproject.toml                # setuptools 配置
```

模块职责边界与关键不变量（CLI 不写 wiki 内容、不重写 setup_wiki 逻辑、SKILL 路径固定）见 [`doc/design/00-overview.md`](doc/design/00-overview.md)。

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

### Workspace Model Registry (Phase 2)

```bash
TMPWS=$(mktemp -d)
export LLMW_WORKSPACE="$TMPWS"

llmw init --path "$TMPWS" --no-git
test -f "$TMPWS/.gitignore" && grep -q "workspace_models.toml" "$TMPWS/.gitignore"
test -f "$TMPWS/.gitignore" && grep -q "\*/.claude/settings.local.json" "$TMPWS/.gitignore" \
  && echo "✓ gitignore: settings.local.json excluded"

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
llmw wiki --name=foo enter --dry-run | grep -q "settings.local.json" && echo "✓ dry-run: overlay file shown"
llmw wiki --name=foo enter --dry-run | grep -q "sk-...7890" && echo "✓ dry-run: api_key redacted"

# 真跑 enter 生成 overlay file（需 claude 在 PATH；这里改为手动调 overlay.apply 模拟）
# 实际场景：llmw wiki --name=foo enter  会调 overlay.apply 写 <wiki>/.claude/settings.local.json
# 验证幂等 + chmod 600
test -f "$TMPWS/foo/.claude/settings.local.json" && \
  test "$(stat -c '%a' "$TMPWS/foo/.claude/settings.local.json")" = "600" \
  && echo "✓ overlay: file exists with 600"

# 验证幂等（再跑一次 enter，内容不变、不报错）
# llmw wiki --name=foo enter --dry-run  # 状态应为 "up to date" 而非 "would update"

# 验证非法 JSON 不覆盖
echo "not valid json {{{" > "$TMPWS/foo/.claude/settings.local.json"
chmod 600 "$TMPWS/foo/.claude/settings.local.json"
llmw wiki --name=foo enter 2>&1 | grep -q "OverlayFileUnparseable" && echo "✓ overlay: corrupted file not clobbered"
test "$(cat "$TMPWS/foo/.claude/settings.local.json")" = "not valid json {{{" \
  && echo "✓ overlay: original corrupted content preserved"

rm -rf "$TMPWS"
```

## Phase 边界

| 维度 | Phase 1（当前） | Phase 2（暂未做） |
| --- | --- | --- |
| workspace / wiki 元数据 | ✅ | |
| 基础 CRUD | ✅ | |
| Claude Code session 启动 | ✅（不传 model） | |
| model registry | ❌ | ✅（`workspace_models.toml` + `llmw model` 命令） |
| ingest / lint / query 包装 | ❌（留给 SKILL session 内） | |
| install / uninstall 脚本 | ✅（`./scripts/install.sh` / `./scripts/uninstall.sh`） | |

详见 `doc/design/` 各章节。

## 并发 / 文件系统

原子写走 `tmp + fsync + rename`（POSIX 原子）。本地文件系统（ext4 / APFS）安全。
**NFS 不安全**——不要在 NFS 挂载的 workspace 上跑 `llmw`。
