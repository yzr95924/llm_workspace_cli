---
name: claude-settings-env-precedence
description: Claude Code ~/.claude/settings.json 的 env 块优先级高于 subprocess 继承的进程 env；llmw enter 用 --setting-sources project,local 规避，且 ANTHROPIC_MODEL 用 model.name 非 model_id
metadata:
  type: project
---

Claude Code 启动时，会把它自己的 `~/.claude/settings.json` 的 `env` 块**盖到子进程继承的进程环境变量之上**（settings env 块优先级高于 `subprocess.run(env=...)` 传入的 env）。官方 settings 优先级：Managed > CLI args(--settings) > Local > Project > User；`env` 块属于 settings 层，会重新应用到 session。

**Why:** 2026-06-29 排查「wiki 配了 minimax 却跑 glm」时发现：`llmw wiki enter` 已通过 `subprocess.run(env=full_env)` 把 `ANTHROPIC_MODEL=minimax...` 注入子进程（OS 级正确），但 claude 内部又用 `~/.claude/settings.json` 的 `env` 块（全局 `glm-5.2[1m]`）盖回去了。所以「覆盖子进程 env」这条路本身赢不了——必须让 claude 不加载 user 那层 env。

**How to apply:**

- `llmw wiki enter` 启动 claude 时**必须带 `--setting-sources project,local`**（不加载 user 源），否则 per-wiki 的 env overlay 会被用户全局 `~/.claude/settings.json` 的 `env` 块盖掉
- 代价：wiki 会话丢掉 user 级配置（`enabledPlugins` / `theme` / `statusLine`）；项目级 MCP/plugin（`.mcp.json` / `.claude/settings.json`）靠 cwd（wiki 子目录）加载，可用 symlink 把 workspace 级共享配置投进各 wiki 子目录
- **`ANTHROPIC_MODEL` 用 `model.name`（网关模型名，如 `MiniMax-M3[1m]`），不是 `model_id`（内部 slug，如 `minimax-m3-1m`）**——网关只认 name；slug 受 `^[a-z0-9_-]+$` 正则限制，根本存不下网关名（含 `.` `[`）
- `--setting-sources` 合法值：`user` / `project` / `local`（claude `--help`）；排除 `user` 即不加载 `~/.claude/settings.json`

关联 [[model-ops-no-env-vars]]。
