---
name: overlay-habit-template
description: overlay 的 habit template 机制——非用户可配的"习惯级" env key 写在代码常量里, 随 wiki enter 一并写入 settings.local.json
metadata:
  type: project
---

# Overlay Habit Template

`llmw/models/overlay.py:_HABIT_TEMPLATE` 是**代码内常量**的"习惯级" env key 集合,
随 `wiki enter` 一并写入 `<wiki>/.claude/settings.local.json`。**不**通过 CLI 配置、
**不**入 `workspace_models.toml`、**不**入 toml schema。

初始条目:
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`(关闭非必要流量 / 遥测)
- `CLAUDE_CODE_ATTRIBUTION_HEADER=llmw`(API 侧识别 llmw 启动的 session)

**Why:** registry 的本职是 "model 元数据 + 凭证",把"全 CLI 行为约定"(隐私开关、
attribution 标记)塞进去会污染 schema;放 per-workspace toml 又会让"统一风格"裂开
成 N 份配置。代码内常量是最佳载体——增删改 = 改一行,升级随 CLI 版本走,跨 wiki
风格一致。

**How to apply:**

- **加新 key**:在 `_HABIT_TEMPLATE` 字典加一行 `"{KEY}": "{value}"`,带注释说明意图。
  下次 `wiki enter` 自动同步到所有 wiki;老 wiki 因 `_is_up_to_date=False` 自动补齐。
- **改 value**:同上,直接改字典值。下次 enter 自动覆盖老值(与 ANTHROPIC_* reset
  行为一致)。
- **删 key**:从字典里删。下次 enter 自动从 settings.local.json 删除(因不在 `_OWNED`)。
- **想做 per-workspace 配置**:停下来——这违背模板初衷。要么改全局默认值,要么
  走 `wiki/.claude/settings.local.json` 的 `env` 块里手加(CLI 不动非 owned key)。
- **想加 CLI flag / toml schema**:同上,停下来。template 是"非用户可配"语义。

**所有权与 reset**:habit template key 与 ANTHROPIC_* 一同被 `_OWNED` 收编。用户
手改 template key 会被下次 enter reset 回常量值——这是"强制习惯",非"建议"。

关联 [[model-ops-no-env-vars]] [[agent-settings-env-precedence]]。
