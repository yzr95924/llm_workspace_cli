---
name: model-ops-no-env-vars
description: model 配置不以环境变量为真相源（只从 workspace_models.toml 读，绝不读 os.environ）；wiki enter 向子进程注入 ANTHROPIC_* env 是主动输出（值来自 registry）
metadata:
  type: project
---

本仓库 wiki-workspace-cli 涉及 model 的配置**不以环境变量为真相源**——model_id / base_url / api_key 一律来自 `workspace_models.toml`，CLI **绝不**从 `os.environ` 读取 model 配置。

但「不依赖环境变量」**不等于**「不向子进程注入 env」：Phase 2 起 `wiki enter` 会向 claude 子进程注入 `ANTHROPIC_MODEL`/`ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`——这是 CLI 的**主动输出**（值来自 registry 的 ModelEntry），不是从父进程 env 读出来当真相。

**Why:** 环境变量是进程级的、易被外部覆盖、用户 shell 环境不可控；model 配置必须由 CLI 100% 掌控（来自 registry 文件），确保审计可追、跨环境一致。这是用户 2026-06-28 在设计阶段确立的硬约束。禁止的是「读 env 当真相源」，不是「向子进程注入 env」。

**How to apply:**

- `workspace_models.toml` 是 model 的唯一真相源；`llmw model` 系列命令管理该文件；wiki_metadata.toml 用 model_id 字段引用
- **绝不**在任何代码路径读取 `os.environ.get("ANTHROPIC_MODEL")` 或类似 pattern（读取 = 把 env 当真相源，禁止）
- `wiki enter` 向子进程**注入**（写入）env 是允许的——值来自 registry，非从父进程 env 读出
- 注入的 `ANTHROPIC_MODEL` 用 `model.name`（网关模型名），不是 `model_id`；且需配 `--setting-sources project,local` 才不被 `~/.claude/settings.json` 盖掉（详见 [[claude-settings-env-precedence]]）

关联 [[memory-persistence-policy]] [[design-docs-organization]] [[claude-settings-env-precedence]]。
