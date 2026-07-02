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

> 参数风格约定：**带值 flag 统一用 `--flag=VALUE`**；bool flag（无值，如 `--json` `--purge` `--yes` `--git` `--dry-run`）保持位置写法；位置参数（`config KEY VALUE`）不变。

```bash
# 初始化 workspace（默认 ~/yzr_llm_wiki_workspace；init 不碰 git）
llmw init
cd ~/yzr_llm_wiki_workspace

# 先把要用的 model 注册到 workspace（Phase 2；--default 设默认 model）
llmw model add \
  --model-id=minimax-m3-1m \
  --name="MiniMax-M3[1m]" \
  --base-url="https://api.example.com" \
  --api-key="sk-xxxxxxxx" \
  --default

# 新建一个 wiki（非 TTY 需全 flag；--model 必须是 registry 里的 model_id）
llmw wiki --name=llm-systems add \
  --topic="LLM Systems" \
  --display-name="LLM 系统研究" \
  --description="跟踪 LLM 系统相关论文与博客" \
  --tag=research --tag=llm \
  --model=minimax-m3-1m

# 查看
llmw list
llmw wiki --name=llm-systems show

# 编辑 metadata（交互模式）
llmw wiki --name=llm-systems config

# 启动 Claude Code session（核心命令；overlay 写 <wiki>/.claude/settings.local.json）
llmw wiki --name=llm-systems enter
# 先看命令再跑:
llmw wiki --name=llm-systems enter --dry-run

# 移除 wiki
llmw wiki --name=llm-systems remove                   # 仅取消注册
llmw wiki --name=llm-systems remove --purge --yes     # 默认先备份到 .llmw-trash/
llmw wiki --name=llm-systems remove --purge --no-backup --yes  # 跳过备份，直接 rmtree
```

## 命令清单

### 全局 flag

`--workspace=PATH` / `--json` / `--debug` / `--quiet` / `-q`（可写子命令前，也可写子命令后）。

### workspace 级

| 命令 | 作用 |
| --- | --- |
| `llmw init [--path=PATH] [--display-name=NAME]` | 初始化 workspace；默认 PATH `~/yzr_llm_wiki_workspace`，不碰 git（允许在已有 git 空仓上 init） |
| `llmw config [get\|set\|unset] [KEY] [VALUE]` | 读写 `workspace.toml`；无参数 + TTY 进交互模式，非 TTY 打印字段列表退出 0 |
| `llmw list [--tag=TAG]...` | 列出 wiki（`--tag` 可重复，AND 关系） |

`llmw config` 合法 KEY（写于 `llmw/workspace/manager.py:CONFIG_KEYS`）：

| KEY | set | unset | 说明 |
| --- | :-: | :-: | --- |
| `default_model` | ✓ | ✓ | workspace 级兜底 model（Phase 2 后真正生效的是 registry 的 `is_default=true` 条目） |
| `templates_version` | ✗ | ✗ | 只读，编码双 spec 版本 |
| `created_at` | ✗ | ✗ | 只读 |
| `schema_version` | ✗ | ✗ | 只读 |

### model registry（Phase 2，源数据 `workspace_models.toml`，不入 git）

| 命令 | 作用 |
| --- | --- |
| `llmw model add --model-id=ID --name=NAME --base-url=URL --api-key=KEY [--default]` | 新增 model；`--default` 同时标记为默认（全局唯一） |
| `llmw model list [--json]` | 列出所有 model（api_key 自动 redact） |
| `llmw model show --model-id=ID [--json]` | 查看单条 model |
| `llmw model set-default --model-id=ID` | 把已有条目标记为默认 |
| `llmw model unset-default` | 清空默认标记 |
| `llmw model remove --model-id=ID [--yes\|-y]` | 删除 model 条目 |

### wiki 级

| 命令 | 作用 |
| --- | --- |
| `llmw wiki --name=X add [--topic=...] [--display-name=...] [--description=...] [--tag=TAG]... [--model=MODEL_ID] [--git]` | 新建 wiki；非 TTY 下 metadata flag 全必填；`--model` 必须在 registry 中；`--git` opt-in 初始化 wiki 子目录 git 仓（spec §7） |
| `llmw wiki --name=X remove [--purge] [--no-backup] [--yes\|-y]` | 移除 wiki；`--purge` 同时删子目录（默认先备份到 `.llmw-trash/<name>-<ISO8601>/`）；`--no-backup` 跳过备份直接 rmtree |
| `llmw wiki --name=X show [--json]` | 查看 wiki 详情（resolved model 来源 + api_key redact） |
| `llmw wiki --name=X config [get\|set\|unset] [KEY] [VALUE]` | 读写 `wiki_metadata.toml`；无参数 + TTY 进交互模式 |
| `llmw wiki --name=X enter [--dry-run]` | resolve_for_wiki → overlay.apply 写 `<wiki>/.claude/settings.local.json` → `claude --add-dir [--system-prompt]`（透传 `os.environ`，不传 `--setting-sources`） |

`llmw wiki --name=X config` 合法 KEY（`llmw/wiki/manager.py:WIKI_CONFIG_KEYS`）：

| KEY | set | unset | 说明 |
| --- | :-: | :-: | --- |
| `display_name` | ✓ | ✓ | 显示名 |
| `description` | ✓ | ✓ | 描述 |
| `tags` | ✓ | ✓ | tag 列表（`set` 走逗号分隔字符串或重复 `--tag`） |
| `model` | ✓ | ✓ | 指向 registry 中的 `model_id`（必须存在） |
| `name` / `topic` / `schema_version` / `created_at` / `updated_at` | ✗ | ✗ | 全部只读 |

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
├── llmw/                         # Python 包（4 子包，pyproject.toml 已列）
│   ├── cli.py                    # argparse 顶层 + 全局 flag + 分派
│   ├── config.py                 # 路径解析 + SKILL 模板目录定位
│   ├── workspace/                # init / config / list + workspace.toml 读写
│   ├── wiki/                     # add / remove / show / config / enter + wiki_metadata.toml 读写 + init_wiki + enter
│   └── models/                   # registry (workspace_models.toml) + overlay + redact + resolve
├── scripts/                      # install / uninstall shell 脚本及其集成测试
├── templates/                    # 仅承载 wiki_metadata.toml.template（wiki add 时实例化）
├── doc/                          # 设计文档（按子功能拆分）+ 实施计划
├── MEMORY/                       # 项目级"为什么 + 边界"记忆（提交进仓库）
├── my_SKILL/                     # git submodule：wiki / workspace 两仓 SKILL 的 references/ 是 wiki 内容字节金标准
├── tests/                        # 当前阶段测试优先级低，先做手动 smoke（见下方）
├── .github/workflows/test.yml    # CI: ruff lint + pytest（py3.7 / py3.11）
└── pyproject.toml                # setuptools 配置（packages 含 llmw.models）
```

> `templates/` 现在**只**承载 `wiki_metadata.toml.template`（实例化 `wiki add` 的初始 metadata）；wiki 内容骨架（`raw/`、`wiki/`、`<wiki>/CLAUDE.md`）由 `llmw/wiki/init_wiki.py` 读 `my_SKILL/llm-wiki-management/references/` 下的模板与 fixtures 渲染落盘（spec 0.2.0 起取代原 SKILL `setup_wiki.py`，spec 0.10.0/0.3.0 当前）。

模块职责边界与关键不变量（CLI 不写 wiki 内容、不重写 setup_wiki 逻辑、SKILL 路径固定）见 [`doc/design/00-overview.md`](doc/design/00-overview.md)。

## Manual Smoke Test（prototype 阶段验收清单）

每个命令至少跑一遍 happy path：

```bash
# 准备临时 workspace
TMPWS=$(mktemp -d)

# init（init 不碰 git；想要 git 仓在外部自己 git init）
llmw init --path="$TMPWS"
test -f "$TMPWS/workspace.toml" && echo "✓ init"
test -f "$TMPWS/.gitignore" && echo "✓ gitignore (managed block)"

# config (非 TTY 自动打印字段列表后退出 0)
LLMW_WORKSPACE="$TMPWS" llmw config
LLMW_WORKSPACE="$TMPWS" llmw config set default_model minimax-m3-1m
LLMW_WORKSPACE="$TMPWS" llmw config get default_model
LLMW_WORKSPACE="$TMPWS" llmw config unset default_model

# list (空)
LLMW_WORKSPACE="$TMPWS" llmw list

# model add (Phase 2: wiki add 的 --model 必须在 registry 中)
LLMW_WORKSPACE="$TMPWS" llmw model add \
  --model-id=minimax-m3-1m --name="MiniMax-M3[1m]" \
  --base-url="https://api.example.com" --api-key="sk-test-1234567890" --default
test "$(stat -c '%a' "$TMPWS/workspace_models.toml")" = "600" && echo "✓ model add (chmod 600)"

# add (非 TTY 全 flag；--model 必须是 registry 里的 model_id)
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo add \
  --topic="Foo" --display-name="Foo" --description="x" \
  --tag=a --tag=b --model=minimax-m3-1m
test -d "$TMPWS/foo/raw" -a -d "$TMPWS/foo/wiki" -a -f "$TMPWS/foo/CLAUDE.md" -a -f "$TMPWS/foo/wiki_metadata.toml" \
  && echo "✓ add (files ok)"

# list (有 wiki)
LLMW_WORKSPACE="$TMPWS" llmw list
LLMW_WORKSPACE="$TMPWS" llmw list --json
LLMW_WORKSPACE="$TMPWS" llmw list --tag=a

# show
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo show
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo show --json

# config set/get（位置参数 KEY VALUE，不走 flag= 风格）
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo config set tags alpha,beta
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo config get tags

# enter --dry-run（bool flag 无值）
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter --dry-run

# remove（--purge / --yes / --no-backup 都是 bool flag）
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo remove --purge --yes
test ! -d "$TMPWS/foo" && echo "✓ remove --purge"
test -d "$TMPWS/.llmw-trash" && echo "✓ remove backup landed"

rm -rf "$TMPWS"
```

### Workspace Model Registry (Phase 2)

```bash
TMPWS=$(mktemp -d)
export LLMW_WORKSPACE="$TMPWS"

llmw init --path="$TMPWS"
test -f "$TMPWS/.gitignore" && grep -q "workspace_models.toml" "$TMPWS/.gitignore"
test -f "$TMPWS/.gitignore" && grep -q "\*/.claude/settings.local.json" "$TMPWS/.gitignore" \
  && echo "✓ gitignore: settings.local.json excluded"

llmw model add \
    --model-id=minimax-m3-1m --name="MiniMax-M3[1m]" \
    --base-url="https://api.example.com" --api-key="sk-test-1234567890" --default
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
model = "minimax-m3-1m"
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

| 维度 | Phase 1 | Phase 2（当前） |
| --- | :-: | :-: |
| workspace / wiki 元数据 | ✅ | |
| 基础 CRUD | ✅ | |
| Claude Code session 启动 | ✅（无 model overlay） | ✅（写 `<wiki>/.claude/settings.local.json` 的 Local 层 env 块） |
| model registry | ❌ | ✅（`workspace_models.toml` + `llmw model` 全套 + `enter` overlay） |
| ingest / lint / query 包装 | 留给 SKILL session 内（`llmw-wiki-management`） | |
| install / uninstall 脚本 | ✅（`./scripts/install.sh` / `./scripts/uninstall.sh`） | |

详见 `doc/design/` 各章节。

## 并发 / 文件系统

原子写走 `tmp + fsync + rename`（POSIX 原子）。本地文件系统（ext4 / APFS）安全。
**NFS 不安全**——不要在 NFS 挂载的 workspace 上跑 `llmw`。
