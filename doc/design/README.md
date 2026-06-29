# 设计文档索引

本目录按子功能拆分，存放 `wiki-workspace-cli`（CLI 名称：`llmw`）的设计文档。
每一份聚焦一个子主题，可独立审阅、独立演化。

> 项目背景：本 CLI 是 `@my_SKILL/llm-wiki-management` skill 的轻量 wrapper，
> 用于管理一个 workspace（一个 git 仓）下的多个 wiki（每个 wiki 是一个子目录，含 `raw/` + `wiki/` + `CLAUDE.md`）。
> Phase 1 范围：workspace / wiki 元数据管理 + 基础 CRUD + 启动 Claude Code session。
> Phase 2：model registry + model overlay 交付（见 [09-workspace-model-registry.md](09-workspace-model-registry.md)）。

## 子功能拆分

| 文档 | 子功能 | 章节定位 |
| --- | --- | --- |
| [00-overview.md](00-overview.md) | 顶层架构、模块边界、关键不变量 | 先读 |
| [01-workspace-management.md](01-workspace-management.md) | `llmw init` / `llmw config` / `llmw list` | workspace 级操作 |
| [02-wiki-crud.md](02-wiki-crud.md) | `llmw wiki add` / `remove` / `show` / `config` | wiki 级 CRUD |
| [03-wiki-enter.md](03-wiki-enter.md) | `llmw wiki enter` | 核心命令（启动 Claude Code session） |
| [04-data-model.md](04-data-model.md) | `workspace.toml` 与 `wiki_metadata.toml` 的 schema | 数据模型 |
| [05-templates-submodule.md](05-templates-submodule.md) | `templates/` 目录与 `my_SKILL` submodule 集成 | 外部依赖 |
| [06-error-handling.md](06-error-handling.md) | 错误场景、退出码、原子写策略 | 可靠性 |
| [07-testing.md](07-testing.md) | 测试策略（prototype 阶段延后） | 质量保证 |
| [08-install-uninstall.md](08-install-uninstall.md) | `scripts/install.sh` / `uninstall.sh` 安装机制 | 安装 |
| [09-workspace-model-registry.md](09-workspace-model-registry.md) | `llmw model` 命令族 + `workspace_models.toml` + resolve + overlay 交付 | model registry（Phase 2） |

## 范围与非范围

**Phase 1 在范围内**：

- workspace 初始化与配置
- wiki 子目录创建 / 注册 / 展示 / 移除 / 配置
- Claude Code session 启动（核心）

**Phase 1 不做**：

- ingest / lint / query——这些留给 Claude Code session 内的 SKILL 脚本
- 跨 wiki 聚合操作（status / search）——Phase 2
- model registry——Phase 2

## 阅读建议

1. 先读 `00-overview.md` 建立全局观
2. 按需查阅子功能章节
3. `04-data-model.md` 与 `05-templates-submodule.md` 是落地时必读