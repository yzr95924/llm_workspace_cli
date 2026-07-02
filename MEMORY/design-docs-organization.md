---
name: design-docs-organization
description: 设计文档统一放在 doc/ 下，按子功能拆成多个 markdown 文件（不是单一长文）
metadata:
  type: project
---

本仓库的设计文档统一放在 `doc/` 目录下，**按子功能拆成多个 markdown 文件**，而不是把所有内容塞进一篇长文。

**Why:** 子功能边界一旦清晰（命令、模块、流程等），单文件设计文档会迅速膨胀、可读性下降；拆文件后可以按子功能独立审阅、独立演化，也方便后续按模块挑出单独看。源头是 2026-06-28 设计 wiki workspace CLI 时确立的项目规约。

**How to apply:** 当需要为本仓库写设计文档（spec / design / 计划等）时：

- 默认放 `doc/` 下，按子功能分子目录或前缀编号；常用结构：`doc/design/`、`doc/specs/`
- 一份文档聚焦一个子功能或一个子主题；超过 ~300 行考虑再拆
- 在 `doc/` 下放一份 README.md（或 doc/design/README.md）作为索引，列出所有设计文档及其覆盖的子功能
- 同时遵守设计文档自身的格式约束（如走 `design-doc-edit` skill 的骨架时，骨架顺序不拆散——拆的是"主题"，不是"骨架内的小节"）

关联 [[memory-persistence-policy]]（MEMORY/ 是设计文档体系在"为什么 + 边界"层的延伸）