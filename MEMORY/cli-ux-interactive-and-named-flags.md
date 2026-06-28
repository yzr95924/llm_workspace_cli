---
name: cli-ux-interactive-and-named-flags
description: CLI 参数传递约定——配置类命令优先做成交互式；需用户指定的参数用命名 flag（--xxx=…）而非裸位置参数
metadata:
  type: project
---

`llmw` CLI 的参数传递遵循两条 UX 约定（用户 2026-06-28 确立）：

1. **配置类命令优先做成交互式**：`config` 这类需要用户逐项填值的命令，应提供交互模式（TTY 下无子动作即进入），让用户逐项输入，而不是逼用户记住一堆 flag。
2. **需用户指定的参数，用命名 flag 传递**：`--flag=value`（或 `--flag value`），不要用裸位置参数 `<value>`。命名 flag 自明、顺序无关、可读；位置参数的含义靠位置隐式推断，易错。

**Why:** 交互式降低用户记忆负担（配置项多时尤甚）；命名 flag 让命令行自文档化（`--model-id=m2` 比 `m2` 清晰）、顺序无关、便于脚本化与可读。用户在讨论 `wiki config set model` 的传值方式时确立：与其纠结位置参数 vs flag，配置类直接走交互式；必须命令行传值时一律命名 flag。

**How to apply:**

- 新增配置类子命令时，默认带交互模式（无子动作 + TTY → 进入交互逐项填）
- 命令行传值一律 `--flag value`；项目惯例 flag 名用 kebab-case（`--model-id`，`dest=model_id`），与现有 `llmw model add --model-id ...` 一致
- 历史遗留的位置参数传值（如 `config set <key> <value>` 的 value）暂保留，改造时优先转交互式或命名 flag
- `get` / `unset` 等只需 KEY、不需要用户填自由值的操作不受此约束

关联 [[memory-persistence-policy]] [[model-ops-no-env-vars]]。
