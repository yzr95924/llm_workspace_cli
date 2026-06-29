# MEMORY 索引

跨会话需要持久化的"为什么 + 边界"规则，正文与索引同级。

## 项目规则

- [设计文档组织](design-docs-organization.md) — 设计文档统一放 `doc/`，按子功能拆成多份 markdown（不是单篇长文）
- [记忆持久化策略](memory-persistence-policy.md) — 项目级记忆写仓库内 `MEMORY/`，跟随代码仓演进，不写个人 memory 目录
- [model 操作不走环境变量](model-ops-no-env-vars.md) — model 配置只从 `workspace_models.toml` 读（绝不读 `os.environ` 当真相源）；`enter` 通过 Local 层（`settings.local.json`）交付 ANTHROPIC_*（值来自 registry）
- [Claude Code settings env 优先级](claude-settings-env-precedence.md) — settings.json 的 `env` 块盖过 subprocess env；`enter` 用 Local 层（`settings.local.json`）覆盖 user env 块；ANTHROPIC_MODEL 用 `name` 非 `model_id`
- [Overlay habit template](overlay-habit-template.md) — `llmw/models/overlay.py:_HABIT_TEMPLATE` 是代码内常量的"习惯级" env key(非用户可配),随 enter 一并写入 settings.local.json;加新 key = 改一行常量
- [测试优先级低](test-priority-low.md) — 当前阶段不写自动化测试，先跑通 prototype + 设计复核，prototype 跑通后再补 test
- [CLI 参数传递约定](cli-ux-interactive-and-named-flags.md) — 配置类命令优先交互式；需用户指定的参数用命名 flag（`--xxx=`），不用裸位置参数