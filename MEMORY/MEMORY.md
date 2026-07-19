# MEMORY 索引

跨会话需要持久化的"为什么 + 边界"规则。本目录每个文件承载一条独立记忆。

> **本文件是项目级规则的唯一真源。** Claude 会话级 memory（`~/.claude/projects/.../memory/`）
> 只放指向本文件的指针，不再持有内容副本——避免随代码仓迁移 / 协作时失同步。

> **新建条目先读 [memory-entry-conventions](memory-entry-conventions.md)。** 索引区按"完整条目
> （带 `.md` 正文） / 短条目（裸行 reminder）"两类分区：建条目时先按颗粒度判别形式，再决定是否
> 单独建 `<slug>.md`。

## 项目规则

### 完整条目（带 .md 正文）

按主题分组：

**MEMORY 元规则**（管理本仓 `MEMORY/` 自身）

- [MEMORY 条目约定](memory-entry-conventions.md) — 判别两类条目 / 索引格式 / 写入纪律 / 与个人 memory 关系；建新条目必读
- [记忆持久化策略](memory-persistence-policy.md) — 项目级记忆写仓库内 `MEMORY/`，跟随代码仓演进，不写个人 memory 目录

**CLI 参数与开发节奏**

- [CLI 参数传递约定](cli-ux-interactive-and-named-flags.md) — 配置类命令优先交互式；需用户指定的参数用命名 flag（`--xxx=`），不用裸位置参数
- [bash 补全 COMP_WORDBREAKS 坑](bash-completion-wordbreaks.md) — 调试须 pty 实测真实 readline（手动设 COMP_WORDS 不经分词，会假通过）；COMP_WORDBREAKS 含 = 拆 --flag=，补全函数须规范化 cur
- [completion 多段位置参数补全](completion-positional-stages.md) — 子命令有多段位置参数（如 `wiki config {get,set,unset} <key> <value>`）时，bash / fish / zsh 三套都需按 token 位置分阶段补全；漏段 Tab 断档

**AI agent 集成**

- [Agent settings env 优先级](agent-settings-env-precedence.md) — settings.json 的 `env` 块盖过
  subprocess env；`enter` 用 Local 层（`settings.local.json`）覆盖 user env 块；
  `ANTHROPIC_MODEL` 用 `name` 非 `model_id`
- [model 操作不走环境变量](model-ops-no-env-vars.md) — model 配置只从 `workspace_models.toml` 读（绝不读 `os.environ` 当真相源）；`enter` 通过 Local 层（`settings.local.json`）交付 `ANTHROPIC_*`（值来自 registry）
- [Overlay habit template](overlay-habit-template.md) — `llmw/models/overlay.py:_HABIT_TEMPLATE` 是代码内常量的"习惯级" env key（非用户可配），随 enter 一并写入 settings.local.json；加新 key = 改一行常量

### 短条目（reminder，无需 why+how 展开）

无需独立文件：

- **用中文交流** — 全程中文，含回答里的小标题；别英文标题配中文正文的混排（术语/命令保留英文，如 `pre-push`）
- **测试优先级低** — prototype 阶段不写自动化测试，跑通后补；agent 不主动加测试代码
- **`enter_cli` 选 agent CLI** — workspace.toml 的 `enter_cli = "qodercli"` 走 qodercli（不写 overlay、不解析 model）；默认 `claude` 与现状一致
- **my_SKILL 是 submodule** — 不要直接修改 `my_SKILL/` 目录，本地改动会被 `git submodule update` 覆盖；要改 upstream 去 `my_SKILL` 仓
- **enter 不传 --system-prompt** — claude/qodercli 都靠 `--add-dir` + cwd=wiki 让 agent 自读 `<wiki>/CLAUDE.md`（或 AGENTS.md）；不显式注入避免双计入 + 两 backend 行为对齐
- **workspace .gitignore managed block 多 1 行** — 实现 `_ensure_workspace_gitignore` 实际写 3 行（`workspace_models.toml` + `*/.claude/settings.local.json` + `.llmw-trash/`），spec §10 字面仅前 2 行；多出的 `.llmw-trash/` 是 `wiki remove --purge` 备份目录排除，spec 升级时一并对照
- **workspace init 拒绝条件比 §12 字面更严** — `init` 对非空目录一律 `WorkspaceExists`（超集覆盖 §12 "workspace.toml 已存在"）；`wiki add` 对已存在目录走文件级 `check_not_initialized` 兜底（行为等价，路径不同）。功能更安全，spec 不变可接受
- **workspace SKILL.md MEMORY 路径陈旧** — `my_SKILL/yzr-llm-workspace-management/SKILL.md` 5 处沿用 `<wiki>/wiki/MEMORY/>` 旧路径（行 161/169/237/335/369），应改 `<wiki>/MEMORY/>`（wiki-spec v0.10.0+）；llmw 按 wiki-spec §5 落盘不受影响，但 workspace `scan` / lint `memory-not-indexed` 会扫空目录——待 SKILL 维护方修
- **wiki check_not_initialized 比 §8 字面多检 3 文件** — `init_wiki.py:check_not_initialized` 校验 6 文件（AGENTS.md / CLAUDE.md / wiki/index.md + MEMORY.md / tags.md / SCRIPTS.md），spec §8 字面仅前 3；多检属主动加严（`init_wiki.py:48` 注释自承「§8 总段『绝不允许覆盖已有 wiki』的精神扩展」），lint 不会误判
- **wiki-spec.md §6 vs §13.4 内部不一致** — spec §6 字面写 `!raw/external/**/.symlink-anchor.json`（0.16.0- 老 JSON 形态），§13.4 写 `!raw/external/.symlink-anchor.toml`（0.17.0+ 新 TOML 形态）；llmw `fixtures/gitignore.txt` 选 §13.4 形态与 0.20.0 changelog 一致——待 SKILL owner 把 §6 改齐
- **workspace .gitignore 驳正（2026-07-08 / spec 0.5.0）** — 驳正上一条"managed block 多 1 行"条目：spec workspace-spec.md §10 v0.5.0 (2026-07-08) 已扩为 3 行模板（在原 2 行后追加 `*/.qoder/settings.local.json`，Qoder IDE 项目级 settings），原条目"spec §10 字面仅前 2 行"已过时。本仓 `_ensure_workspace_gitignore` 现写 4 行：spec 3 行 + `.llmw-trash/`（llmw 自有扩展，wiki remove --purge 备份目录，spec §10 字面未列但允许"至少包含"语义下保留）。老 workspace 升级：函数检测到旧 block 会替换为新 4 行。原条目按"不删既有"保留，仅追加驳正
- **workspace .gitignore 驳正（2026-07-08 / spec 0.5.0 + 0.6.0 + 0.6.1）** — 驳正上一条 0.5.0 驳正（**且**纠正其不准确）：上一条 0.5.0 驳正说"现写 4 行：spec 3 行 + `.llmw-trash/`"——但**实际上 0.5.0 同步时漏了 `.qoder` 行**（git 历史 `llmw/workspace/manager.py` 当时的 `GITIGNORE_LINES` 只 3 行：registry + `.claude` + `.llmw-trash`，缺 spec §10 v0.5.0 要求的 `.qoder`）。本次合并三段变更：(a) **补 0.5.0 漏的 `.qoder` 行**——`**/.qoder/settings*.json`；(b) spec 0.6.0 把 `*/.x/settings.local.json` 改成 `**/.x/settings.local.json`（补 workspace 根级覆盖）；(c) spec 0.6.1 把 `settings.local.json` 加宽到 `settings*.json`（覆盖 `settings.json` / `settings.local.json` / `settings.<env>.json` 等所有变体——非 local 版也可能含 MCP token）。本仓 `GITIGNORE_LINES` 现 4 行：spec §10 v0.6.1 3 行（`workspace_models.toml` + `**/.claude/settings*.json` + `**/.qoder/settings*.json`）+ llmw 自有 `.llmw-trash/`（`llmw/workspace/manager.py:62-66`）。老 workspace 升级同前：`_ensure_workspace_gitignore` 比对 block 字符串不等就替换（单步合并三段变更，无需用户手动改 .gitignore）。同时 `WORKSPACE_SPEC_VERSION` 从 0.4.0 升到 0.6.1（`llmw/__init__.py:4`），`workspace.toml.templates_version` 编码 + `<workspace>/AGENTS.md` 顶部 `{{WORKSPACE_SPEC_VERSION}}` 占位符同步生效。前两条驳正条目（"managed block 多 1 行" + "0.5.0 驳正"）按"不删既有"保留——历史错误也属踩坑沉淀
- **enter_cli 增 opencode（2026-07-19）** — 追加到上条 `enter_cli` 短条目（其只列 claude/qodercli）：白名单现 3 值，`opencode` 走 **resolve + overlay**（与 claude 同族，非 qodercli 裸启动）——`llmw/models/overlay_opencode.py` 渲染 `<wiki>/opencode.json`（own `provider.llmw` 整对象 + 顶层 `model` key，apiKey 明文 + chmod 600），npm 包固定 `@ai-sdk/anthropic`（registry base_url 与 ANTHROPIC_BASE_URL 同源 = Anthropic 协议网关；OpenAI 协议网关改 `_NPM_PACKAGE` 一行）；**baseURL 必须 +`/v1` 规范化**（`_ai_sdk_base_url`：registry 存 Claude Code 约定 = `{base}/v1/messages`，AI SDK 约定 = `{baseURL}/messages`，直填原值 404——已对 MiniMax 网关实测复现并验证修复后推理通）；无 habit template（CLAUDE_CODE_* 为 claude 专属，见 [[overlay-habit-template]]）。cmd 是 `opencode <wiki_dir>`（位置参数，不传 -m）；opencode 自读 AGENTS.md。同时 workspace .gitignore `GITIGNORE_LINES` 4 行 → 5 行（加 `**/opencode.json`，llmw 自有扩展，上面 gitignore 驳正链再 +1）；老 workspace 的 managed block 在 `enter`(opencode) 写 secret 前自动升级（`enter.py` 调 `_ensure_workspace_gitignore`，与 `wiki remove --purge` 同一先例）
- **enter_byobu 走 byobu 窗口（2026-07-19）** — workspace.toml#enter_byobu=true（bool 型 config 首列：`_parse_bool` 严格小写 true/false，`bool("false") is True` 是 Python 陷阱；store 读时 `isinstance(v, bool)` 严格吃真 TOML 布尔）后所有 `wiki enter` 在 byobu **固定 session `llm_workspace`**（`llmw/wiki/byobu.py:_BYOBU_SESSION` 代码常量不可配）按 wiki 名开窗口——**fire-and-forget**：窗口建成即返回 0，退出码不来自 agent；已有同名窗口 → select-window 复用不新建（overlay 照写但运行中 agent 不重读）。实现要点：一律调 `byobu-tmux`（byobu 脚本经 argv[0] 强制 tmux backend，带参调用 `exec tmux ... "$@"` 全透传）；窗口 target 用 `#{window_id}`（@N，防纯数字 wiki 名的 name/index 歧义）；agent argv[0] 先 `shutil.which` 解析绝对路径（tmux server 的 PATH 可能不含 agent 目录）；`new-window -n` 命名即锁窗口名（tmux 对显式命名窗口自动关 automatic-rename）；`LLM_WIKI_ROOT` 走 `-e` 注入（server env 不继承调用进程）；无 session 时 `new-session -d` 一步带首窗（不留裸 shell window 0）；竞争线性降级 ≤3 步不上锁。引导提示三分支：同 session 自动切焦 / 异 session `switch-client`（tmux 拒嵌套 attach）/ 不在 tmux `byobu attach`。已知限制：仅 tmux backend；`wiki remove` 不清窗口；多 workspace 同名 wiki 共用窗口。最终 spawn 统一收口在 `enter.py:_spawn`（三 backend 共用）

## 维护规则

- **追加末尾**——新条目按 git 时间序追加
- **不删既有**——踩坑沉淀；内容有误用追加驳正方式，不动原文
- **frontmatter 三项必填**：`name` / `description` / `metadata.type`（值 ∈ `project | feedback | reference | user`）
- **条目之间用 `[[slug]]` 互链**——读一条可跟随关联链接定位相关记忆

完整约定见 [memory-entry-conventions](memory-entry-conventions.md)；持久化策略见 [memory-persistence-policy](memory-persistence-policy.md)。
