# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

> **薄壳声明**：项目上下文的**单一真源是 `AGENTS.md`**——本文件用 `@AGENTS.md` 引入全部共用内容。
> 改内容请改 `AGENTS.md`；本文件只承载 Claude 专属、无法泛化的逃生舱内容（见下方），勿在此编辑共用部分。

@AGENTS.md

<!-- Claude Code 专属（以下为无法泛化为工具无关的内容，AGENTS.md 不含此部分） -->

- `llmw/wiki/enter.py` 启动 Claude Code 子进程：`subprocess.run(["claude", "--add-dir", str(wiki_dir),
  "--system-prompt", str(prompt_file)], env=os.environ)`；**不传** `--setting-sources`（依赖 Local 层
  `env` 块优先级 > User 层稳赢，详 [[agent-settings-env-precedence]]）。
- Overlay 文件落地路径：`<wiki>/.claude/settings.local.json`（Local 层）；写入由
  `llmw/models/overlay.py:apply()` 负责（render → inspect → atomic_write + chmod 600）。
- `ANTHROPIC_MODEL` 字段用 `model.name`（网关模型名，如 `MiniMax-M3[1m]`），**不是** `model_id` slug——
  网关只认 name；`model_id` 受 `^[a-z0-9_-]+$` 限制存不下网关名的 `.` `[`。
