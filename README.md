# llmw — Wiki Workspace CLI

管理一个由 [`yzr-llm-wiki-management`](https://github.com/yzr95924/my_SKILL/tree/master/yzr-llm-wiki-management) skill 创建的 wiki 集合（一个 workspace = 一个 git 仓，含多个 wiki 子目录）。

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

卸载（只删 wrapper + PATH marker + 已装 completion，**不删仓库、不删 workspace 数据**）：

```bash
./scripts/uninstall.sh
```

### 3. 备选：pip 安装

入口是仓库根的 `bin/llmw`（thin shell，`exec python3 -m llmw`）。若更喜欢走 pip：

```bash
pip install -e .
```

> 系统 Python（Homebrew 等 PEP 668 externally-managed）会拒绝全局 install，改用 `pip install -e . --user`、`pipx install -e .` 或先建 venv。

## Shell Completion

`./scripts/install.sh` 会按当前 `$SHELL`（bash / fish / zsh）自动装一份 shell completion：

| Shell | 装到 | 加载机制 |
|---|---|---|
| bash | `~/.local/share/bash-completion/completions/llmw`（受 `XDG_DATA_HOME` 覆写） | bash-completion ≥2.0 自动接管，无需 source |
| fish | `~/.config/fish/completions/llmw.fish` | fish 自动接管，无需 source |
| zsh   | `~/.local/share/zsh/site-functions/_llmw` | 自动在 `~/.zshrc` prepend `fpath`（带 marker 块幂等），需 `source ~/.zshrc` 或重开终端 |

补全覆盖：

- **静态**：所有顶层子命令、`wiki`/`model` 子动作、`config` get/set/unset、全部 bool / 带值 flag
- **动态**：`--name=<Tab>` 补当前 workspace 的 wiki 名（spawn `llmw --json list` 拿 JSON 抽 `name` 字段）；`--model-id=<Tab>` 同理（走 `llmw model --json list`）
- **边界**：未初始化 workspace 时动态项静默返回（仅补静态）

卸载（与 `uninstall.sh` 同包，幂等）：

```bash
rm -f ~/.local/share/bash-completion/completions/llmw
rm -f ~/.config/fish/completions/llmw.fish
rm -f ~/.local/share/zsh/site-functions/_llmw
# zsh 还需手动删 ~/.zshrc 里的 fpath marker 块：
#   # >>> llmw completion (managed by install.sh) >>>
```

手动 source（不走 install.sh 的场景）：

```bash
# bash
source completions/llmw.bash
# fish (复制到 fish 路径即可自动加载)
cp completions/llmw.fish ~/.config/fish/completions/
# zsh (需 fpath 已含仓库 completions/，或直接 source)
fpath=(completions $fpath); autoload -U compinit && compinit
```

## 快速上手

> 参数风格约定：**带值 flag 一律用 `--flag=VALUE`**（`=` 连接，严谨无歧义；空格分隔的 `--flag VALUE` 会被拒绝并提示 `SpaceFormNotAllowed`）；前缀缩写（`--pref`）也已禁用，请用完整 flag 名。bool flag（无值，如 `--json` `--purge` `--yes` `--git` `--dry-run`）与位置参数（`config KEY VALUE`）不受影响。

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

# 启动 AI agent session（核心命令；默认 claude 走 overlay 写 <wiki>/.claude/settings.local.json；workspace.toml#enter_cli 可切 qodercli/opencode；enter_byobu=true 时改在 byobu session 开窗口）
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
| `enter_cli` | ✓ | ✓ | 选 `wiki enter` 启动的 agent CLI；`claude` (默认) \| `qodercli` \| `opencode`。详见 [切换 agent CLI](#切换-agent-cli) |
| `enter_byobu` | ✓ | ✓ | `true` 时 `wiki enter` 在 byobu 固定 session `llm_workspace` 按 wiki 名开窗口（已有同名窗口则复用）；unset/false = 阻塞直启。详见 [byobu 窗口模式](#byobu-窗口模式) |
| `templates_version` | ✗ | ✗ | 只读，编码双 spec 版本 |
| `created_at` | ✗ | ✗ | 只读 |
| `schema_version` | ✗ | ✗ | 只读 |

### 切换 agent CLI

`wiki enter` 默认走 Claude Code（`claude`），可通过 `workspace.toml#enter_cli`
切换为 `qodercli` / `opencode` 等其它 agent CLI。配置项存于 workspace 根的
`workspace.toml`，是 workspace 级开关——同一 workspace 下所有 wiki 共用。

```bash
# 切到 qodercli（不再走 Claude Code；不解析 model、不写 overlay）
llmw config set enter_cli qodercli
llmw config get enter_cli
# qodercli

# 之后所有 wiki enter 都走 qodercli：
llmw wiki --name=<wiki> enter --dry-run   # 看到 backend: qodercli / qodercli --add-dir <wiki>
llmw wiki --name=<wiki> enter

# 切到 opencode（仍解析 model；overlay 写 <wiki>/opencode.json）
llmw config set enter_cli opencode
llmw wiki --name=<wiki> enter --dry-run   # 看到 backend: opencode / opencode <wiki>
llmw wiki --name=<wiki> enter

# 回退默认
llmw config unset enter_cli
```

字段语义与行为差异：

| `enter_cli` | 命令 | model 解析 | overlay 交付 |
| --- | --- | --- | --- |
| `claude`（默认） | `claude --add-dir <wiki>` | ✓ resolve_for_wiki | `<wiki>/.claude/settings.local.json`（Local 层，env 块含 `ANTHROPIC_*` + habit template） |
| `opencode` | `opencode <wiki>` | ✓ resolve_for_wiki | `<wiki>/opencode.json`（项目级，`provider.llmw` + 顶层 `model`；无 habit template） |
| `qodercli` | `qodercli --add-dir <wiki>` | ✗ 跳过 | ✗ |

> 三个 backend 都不显式注入 system prompt / 上下文文件——agent 从 cwd=wiki 自读
> （claude 读 `<wiki>/CLAUDE.md`；opencode / qodercli 读 `<wiki>/AGENTS.md`）。
>
> qodercli 路径完全跳过 `llmw/models/overlay.py` 与
> `llmw/models/resolve.py`：agent 自己处理模型配置与 schema 上下文。
> `overlay-habit-template`（Claude-Code-specific habit env）与
> `agent-settings-env-precedence`（Local > User settings 优先级）不适用于 qodercli。
>
> opencode 路径走 `llmw/models/overlay_opencode.py`（不经过 overlay.py）：apiKey 明文写
> `<wiki>/opencode.json` + chmod 600，由 workspace `.gitignore` managed block 的
> `**/opencode.json` 行排除出 git（与 `settings*.json` 同一安全模型）；npm 包固定
> `@ai-sdk/anthropic`（registry 的 base_url 与 `ANTHROPIC_BASE_URL` 同源，即 Anthropic
> 协议网关），且渲染时 baseURL 自动补 `/v1` 段（registry 存的是 Claude Code 约定
> `{base}/v1/messages`，AI SDK 约定 `{baseURL}/messages`）。
> `overlay-habit-template` 与 `agent-settings-env-precedence` 同样不适用
> （那是 Claude Code settings 机制）。

合法取值（白名单写在 `llmw/workspace/manager.py:_ENTER_CLI_WHITELIST`）：
`claude` / `qodercli` / `opencode`。其它值 `config set` 时会被挡掉，提示
`可选: claude, opencode, qodercli`，退出码 1。

### byobu 窗口模式

`wiki enter` 默认阻塞直启（agent 的 TUI 占住当前终端，退出码来自 agent）。
开 `enter_byobu` 后，所有 `wiki enter` 改为在 byobu **固定 session `llm_workspace`**
里按 wiki 名开窗口跑 agent——fire-and-forget：窗口建成 llmw 即返回 0，不等 agent
退出、退出码不来自 agent。与 `enter_cli` 正交：claude / qodercli / opencode 三
backend 通用（model resolve + overlay 落盘逻辑不变，只换最终 spawn 方式）。

```bash
llmw config set enter_byobu true
llmw wiki --name=<wiki> enter --dry-run   # 看到 spawn: byobu + 将执行的 byobu-tmux 命令
llmw wiki --name=<wiki> enter             # 立即返回 0；窗口在 llm_workspace session 里
byobu attach -t llm_workspace             # 查看（llmw 若跑在该 session 内则已自动切焦）
llmw config unset enter_byobu             # 回退阻塞直启
```

行为细则：

- **session 名固定 `llm_workspace`**（代码常量 `llmw/wiki/byobu.py:_BYOBU_SESSION`，
  不可配）；不存在则自动创建（`new-session -d` 与首个窗口一步建成，不留裸 shell 窗口）。
- **窗口名 == wiki 名**；同一 wiki 重复 `enter` 时已有同名窗口 → `select-window`
  切过去**复用，不新建**（agent 退出窗口自动关，届时再 enter 即重建）。
- 复用时 overlay 文件照常刷新落盘，但**运行中的 agent 不会重读**——改了 model
  想生效，先退出该窗口里的 agent 再 re-enter。
- 窗口环境：`cwd = <wiki>`（`new-window -c`），`LLM_WIKI_ROOT` 经 `-e` 注入
  （tmux server 环境不继承 llmw 进程 env）；agent 二进制先解析为绝对路径再下窗
  （tmux server 的 PATH 可能不含 `~/.local/bin`）。
- 引导提示：llmw 跑在 `llm_workspace` session 内 → 自动切焦；跑在其它 tmux
  session 内 → 提示 `byobu-tmux switch-client -t llm_workspace`；不在 tmux 内 →
  提示 `byobu attach -t llm_workspace`。

已知限制：

- 仅支持 byobu 的 tmux backend（调用走 `byobu-tmux`，经 argv[0] 强制
  `BYOBU_BACKEND=tmux`）；screen backend 不支持。
- session 名全局固定：多个 workspace 的同名 wiki 会共用窗口（复用判定只看窗口名）。
- `wiki remove` 不清对应 byobu 窗口——被删 wiki 的窗口里 agent 若还在跑，需手动关。
- 并发 double-enter 竞争不上锁：极端情况会产生同名双窗口（tmux 允许共存，下次
  enter 复用第一个），属良性。

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
| `llmw wiki --name=NAME add [--topic=TOPIC] [--display-name=DISPLAY_NAME] [--description=DESC] [--tag=TAG]... [--model=MODEL_ID] [--git]` | 新建 wiki；非 TTY 下 metadata flag 全必填；`--model` 必须在 registry 中；`--git` 为 vestigial flag（spec §7 0.16.0+：git 操作全部由用户手动，CLI 不碰 git；落盘后打印手动 hint） |
| `llmw wiki --name=NAME remove [--purge] [--no-backup] [--yes\|-y]` | 移除 wiki；`--purge` 同时删子目录（默认先备份到 `.llmw-trash/<name>-<ISO8601>/`）；`--no-backup` 跳过备份直接 rmtree |
| `llmw wiki rename --old=OLD --new=NEW [--json] [--quiet]` | 重命名 wiki：3 处同步（`workspace.toml [wikis.<old>]`→`[wikis.<new>]`、`<workspace>/<old>/`→`<workspace>/<new>/`、`wiki_metadata.toml#name`）；若 `topic == OLD`（add 默认值）则同步改 `topic`；4 阶段原子，原目录直至切换前不动；冲突硬阻挡（`WikiExists` / `InvalidWikiName`） |
| `llmw wiki --name=NAME show [--json]` | 查看 wiki 详情（resolved model 来源 + api_key redact） |
| `llmw wiki --name=NAME config [get\|set\|unset] [KEY] [VALUE]` | 读写 `wiki_metadata.toml`；无参数 + TTY 进交互模式 |
| `llmw wiki --name=NAME enter [--dry-run]` | 按 `workspace.toml#enter_cli` 选 agent CLI 启动 session；`claude`（默认）走 overlay + Local 层 settings.local.json 交付 model；`opencode` 走 overlay + 项目级 opencode.json 交付 model；`qodercli` 不读 `.claude/`，不交付 model（详见 [切换 agent CLI](#切换-agent-cli)）；`enter_byobu=true` 时改为在 byobu 固定 session 按 wiki 名开窗口（fire-and-forget，详见 [byobu 窗口模式](#byobu-窗口模式)） |

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
├── MEMORY/                       # 项目级"为什么 + 边界"记忆（提交进仓库）
├── my_SKILL/                     # git submodule：wiki / workspace 两仓 SKILL 的 references/ 是 wiki 内容字节金标准
├── tests/                        # 当前阶段测试优先级低，先做手动 smoke（见下方）
├── .github/workflows/test.yml    # CI: ruff lint + pytest（py3.7 / py3.11）
└── pyproject.toml                # setuptools 配置（packages 含 llmw.models）
```

> `templates/` 现在**只**承载 `wiki_metadata.toml.template`（实例化 `wiki add` 的初始 metadata）；wiki 内容骨架（`raw/`、`wiki/`、`<wiki>/CLAUDE.md`）由 `llmw/wiki/init_wiki.py` 读 `my_SKILL/yzr-llm-wiki-management/references/` 下的模板与 fixtures 渲染落盘（spec 0.2.0 起取代原 SKILL `setup_wiki.py`，spec 0.10.0/0.3.0 当前）。

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
LLMW_WORKSPACE="$TMPWS" llmw config set enter_cli qodercli
LLMW_WORKSPACE="$TMPWS" llmw config get enter_cli
LLMW_WORKSPACE="$TMPWS" llmw config set enter_cli opencode
LLMW_WORKSPACE="$TMPWS" llmw config get enter_cli
LLMW_WORKSPACE="$TMPWS" llmw config unset enter_cli

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

# enter --dry-run（opencode backend：resolve 生效，overlay 目标是 <wiki>/opencode.json）
LLMW_WORKSPACE="$TMPWS" llmw config set enter_cli opencode
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter --dry-run
LLMW_WORKSPACE="$TMPWS" llmw config unset enter_cli

# byobu 窗口模式（fire-and-forget；真实 enter 需 claude 在 PATH——窗口里会起真 agent，
# 验证完 kill-session 一并清理）
LLMW_WORKSPACE="$TMPWS" llmw config set enter_byobu true
LLMW_WORKSPACE="$TMPWS" llmw config get enter_byobu    # true
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter --dry-run   # spawn: byobu + byobu-tmux 决策树
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter     # 立即返回 0
byobu-tmux list-windows -t llm_workspace -F '#W' | grep -q '^foo$' && echo "✓ byobu: window created"
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter >/dev/null  # 再 enter → 复用不新建
test "$(byobu-tmux list-windows -t llm_workspace -F '#W' | grep -c '^foo$')" = "1" \
  && echo "✓ byobu: reuse (no dup)"
byobu-tmux kill-session -t llm_workspace   # 清理（连窗口里的 agent 一起杀）
LLMW_WORKSPACE="$TMPWS" llmw config unset enter_byobu

# remove（--purge / --yes / --no-backup 都是 bool flag）
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo remove --purge --yes
test ! -d "$TMPWS/foo" && echo "✓ remove --purge"
test -d "$TMPWS/.llmw-trash" && echo "✓ remove backup landed"

rm -rf "$TMPWS"
```

#### wiki rename

```bash
TMPWS=$(mktemp -d)
export LLMW_WORKSPACE="$TMPWS"

llmw init --path="$TMPWS"

# 准备: 建一个 wiki foo(topic 默认 == name)
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo add \
  --topic=foo \
  --display-name=Foo \
  --description=demo \
  --tag=demo \
  --model=demo-model
# (model=demo-model 需先在 registry 注册;走 model registry happy path 后此处才能过)

# happy path: foo → bar
LLMW_WORKSPACE="$TMPWS" llmw wiki rename --old=foo --new=bar
test ! -d "$TMPWS/foo" && echo "✓ rename: 旧目录清理"
test -d "$TMPWS/bar" && echo "✓ rename: 新目录就位"
grep -q '\[wikis\.bar\]' "$TMPWS/workspace.toml" && echo "✓ rename: workspace.toml 切换"
! grep -q '\[wikis\.foo\]' "$TMPWS/workspace.toml" && echo "✓ rename: 旧 key 注销"
grep -q '^name = "bar"' "$TMPWS/bar/wiki_metadata.toml" && echo "✓ rename: metadata name 改写"
grep -q '^topic = "bar"' "$TMPWS/bar/wiki_metadata.toml" && echo "✓ rename: topic 默认值同步"

# --json 输出
LLMW_WORKSPACE="$TMPWS" llmw wiki rename --old=bar --new=baz --json | grep -q '"topic_changed": true' \
  && echo "✓ rename --json"

# 错误路径: new 已在 registry
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=baz add \
  --topic=baz \
  --display-name=Baz \
  --description=demo \
  --tag=demo \
  --model=demo-model
! LLMW_WORKSPACE="$TMPWS" llmw wiki rename --old=baz --new=foo 2>/dev/null \
  && echo "✓ rename: new 冲突硬阻挡 (foo 早被重命名注销,但残留名占位由 WikiExists 触发)"

# 错误路径: old == new
! LLMW_WORKSPACE="$TMPWS" llmw wiki rename --old=baz --new=baz 2>/dev/null \
  && echo "✓ rename: old == new 拒绝"

# 错误路径: NAME_RE 非法
! LLMW_WORKSPACE="$TMPWS" llmw wiki rename --old=baz --new=BAD 2>/dev/null \
  && echo "✓ rename: NAME_RE 拒绝大写"

# 错误路径: old 不存在
! LLMW_WORKSPACE="$TMPWS" llmw wiki rename --old=nope --new=qux 2>/dev/null \
  && echo "✓ rename: old 不存在拒绝"

# 清理: trash 留作记录不强行 rm
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

## 并发 / 文件系统

原子写走 `tmp + fsync + rename`（POSIX 原子）。本地文件系统（ext4 / APFS）安全。
**NFS 不安全**——不要在 NFS 挂载的 workspace 上跑 `llmw`。
