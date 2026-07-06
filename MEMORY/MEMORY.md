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
- **workspace SKILL.md MEMORY 路径陈旧** — `my_SKILL/llm-workspace-management/SKILL.md` 5 处沿用 `<wiki>/wiki/MEMORY/>` 旧路径（行 161/169/237/335/369），应改 `<wiki>/MEMORY/>`（wiki-spec v0.10.0+）；llmw 按 wiki-spec §5 落盘不受影响，但 workspace `scan` / lint `memory-not-indexed` 会扫空目录——待 SKILL 维护方修

## 维护规则

- **追加末尾**——新条目按 git 时间序追加
- **不删既有**——踩坑沉淀；内容有误用追加驳正方式，不动原文
- **frontmatter 三项必填**：`name` / `description` / `metadata.type`（值 ∈ `project | feedback | reference | user`）
- **条目之间用 `[[slug]]` 互链**——读一条可跟随关联链接定位相关记忆

完整约定见 [memory-entry-conventions](memory-entry-conventions.md)；持久化策略见 [memory-persistence-policy](memory-persistence-policy.md)。
