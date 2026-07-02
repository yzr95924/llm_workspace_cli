---
name: memory-entry-conventions
description: MEMORY 条目形式判别（完整 vs 短）+ 索引格式 + 写入纪律 + 与 Claude 会话级 memory 关系；新建任何 MEMORY 条目前必读
metadata:
  type: project
---

MEMORY 条目形式（完整 vs 短）的判别 + 写入纪律的权威约定。对齐 [`my_SKILL/llm-wiki-management` SKILL.md §4 Memory](https://github.com/yzr95924/my_SKILL/blob/master/llm-wiki-management/SKILL.md) 的"判别条目形式"规则，结合本仓特点做精简。

**Why:** `MEMORY/MEMORY.md` 被 `<workspace-root>/CLAUDE.md` 用 `@MEMORY/MEMORY.md` import 会话常驻——每条都进上下文。**裸行承载一句话事实**比让 agent 跳去 `Read` 整个 `<slug>.md` 文件快得多也省得多；但"将来怎么用 / 如何避免"等需要完整上下文的，短行承载不下。两类条目按颗粒度选，写错形式要么冗长占用上下文、要么太短丢失关键信息。此外，会话级 memory 副本（`~/.claude/projects/.../memory/`）随代码仓迁移 / 协作会失同步——所有项目级规则必须**只**放在本仓 `MEMORY/`，会话 memory 只留指针。

**How to apply:**

**判别两类条目**（按事实本身颗粒度选）：

| 形式 | 何时用 | 物理形态 |
| --- | --- | --- |
| **完整条目** | 需要解释"为什么这么做"或"将来怎么用"——含上下文 / 设计决策 / 跨文件关系 / 操作步骤 | `MEMORY/<slug>.md` 含 frontmatter + 正文；`MEMORY/MEMORY.md` 加 `[Title](slug.md) — 一句话` 指针 |
| **短条目** | 一句话能讲清的纯事实 / 单一偏好 / 无需 why+how 的 reminder | 直接在 `MEMORY/MEMORY.md` 索引区以 `- **<短名>** — <一句事实>` 承载，不单独建 `.md` |

**判别尺度**：能否在 30 字内独立表达"为什么"或"将来怎么用"——能 → 短条目（直接挂索引）；不能 → 完整条目（建 `.md`，正文用 **Why:** + **How to apply:** 三段式）。

**本仓实例**：
- 完整：`memory-persistence-policy`（讲"为什么写仓库内 / 为什么不止个人 memory"——需要展开）
- 短：`用中文交流`（"全程中文，含回答里的小标题"——一句话够了）；`测试优先级低`（"prototype 阶段不写自动化测试，跑通后补"——一句话够了）
- **判别反例**：曾以完整条目形式存在的 `test-priority-low.md`（含 **Why:** + **How to apply:** 5 bullet），收敛为短条目后删除 body——30 字内可独立表达 why+how 时不必保留 `.md`

**索引条目格式**（在 `MEMORY/MEMORY.md` 顶部声明）：

```
### 完整条目（带 .md 正文）
- [Title](<slug>.md) — <一句话摘要>  # 摘要取自 frontmatter.description

### 短条目（reminder）
- **<短名>** — <一句话事实>
```

**写入纪律**：

- **追加末尾**——`MEMORY/MEMORY.md` 与新建 `.md` 都按时间追加（git 历史即可回溯）；不打乱既有顺序
- **不删除既有条目**——踩坑与决策沉淀下来；如果内容错了，**追加新条目驳正**，不动原文（保留 git 历史）
- **frontmatter 三项必填**：`name`（kebab-case，与文件名一致）/ `description`（单行 ≤ 1 句）/ `metadata.type`（`project` / `feedback` / `reference` / `user` 四选一）
- **完整条目正文**走 **Why:** + **How to apply:** 三段式（与本条、与其他既有完整条目一致）；reference / 频查文档用 `## 背景 / ## 判别 / ## 写入纪律` sub-section 也可，但 default 是三段式
- **cross-link 用 `[[slug]]`** 表达"1 跳之内的紧密主题相关"；不凑数、不加孤儿链

**与 Claude 会话级 memory 的关系**：本仓 `MEMORY/MEMORY.md` 是项目级规则**唯一**真源；Claude 会话级 memory（`~/.claude/projects/.../memory/`）只放指向本文件的指针（如 `MEMORY rules → /root/llm_workspace_cli/MEMORY/MEMORY.md`），不再持有内容副本。如果 agent 在个人 memory 目录发现内容副本，应主动删副本、改留指针。

关联 [[memory-persistence-policy]]。
