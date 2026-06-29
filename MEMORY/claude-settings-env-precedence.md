---
name: claude-settings-env-precedence
description: Claude Code ~/.claude/settings.json 的 env 块优先级高于 subprocess 继承的进程 env；llmw enter 用 Local 层（settings.local.json）覆盖 user env 块，并恢复 user 配置
metadata:
  type: project
---

Claude Code 启动时，会把它自己的 `~/.claude/settings.json` 的 `env` 块**盖到子进程继承的进程环境变量之上**（settings env 块优先级高于 `subprocess.run(env=...)` 传入的 env）。官方 settings 优先级：Managed > CLI args(--settings) > Local > Project > User；`env` 块属于 settings 层，会重新应用到 session。**Local 层（`settings.local.json`）优先级 > User 层**——这是 `llmw wiki enter` 能赢 user env 块覆盖的关键。

**Why:** 2026-06-29 排查「wiki 配了 minimax 却跑 glm」时发现：早期 `llmw wiki enter` 通过 `subprocess.run(env=full_env)` 把 `ANTHROPIC_MODEL=minimax...` 注入子进程（OS 级正确），但 claude 内部又用 `~/.claude/settings.json` 的 `env` 块（全局 `glm-5.2[1m]`）盖回去了。Phase 2 改为：把 resolved model 渲染进 `<wiki>/.claude/settings.local.json` 的 `env` 块（Local 层），让 claude 加载——Local 层优先级 > User 层，overlay 稳赢；subprocess 透传 `os.environ` + **不传** `--setting-sources`，恢复 user 配置（`enabledPlugins` / `theme` / `statusLine` 等不受影响）。

**How to apply:**

- `llmw wiki enter` 把 resolved model 渲染进 `<wiki>/.claude/settings.local.json` 的 `env` 块（Local 层，优先级 > User）——`overlay.apply` 写文件、幂等合并、chmod 600
- subprocess 透传 `os.environ`、**不传** `--setting-sources`（恢复 user 配置；Local 层 env 块优先级高于 user env 块，overlay 稳赢）
- **`ANTHROPIC_MODEL` 用 `model.name`（网关模型名，如 `MiniMax-M3[1m]`），不是 `model_id`（内部 slug，如 `minimax-m3-1m`）**——网关只认 name；slug 受 `^[a-z0-9_-]+$` 正则限制，根本存不下网关名（含 `.` `[`）
- project 级 MCP/plugin（`.mcp.json` / `.claude/settings.json`）靠 cwd（wiki 子目录）加载，可用 symlink 把 workspace 级共享配置投进各 wiki 子目录

关联 [[model-ops-no-env-vars]]。
