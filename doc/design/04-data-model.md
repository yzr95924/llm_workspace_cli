# 04 · 数据模型

本章规范 CLI 写入与读取的两份元数据文件，以及 templates/ 目录下的模板。

---

## 4.1 `workspace.toml`

**位置**：workspace 根目录（`<workspace>/workspace.toml`）

**性质**：git 入库

### 完整 schema（Phase 1）

```toml
schema_version = 1              # int, 只读, CLI 内部维护
created_at = "2026-06-28T10:00:00Z"  # ISO8601 UTC, 只读
default_model = "MiniMax-M3"    # string, 可 set; Phase 1 元数据, 不传递给 Claude Code
templates_version = "1"         # string, 只读, CLI 内部维护

[wikis]                        # 子表: 该 workspace 注册的所有 wiki

[wikis.llm-systems]
path = "llm-systems"            # 相对 workspace 根
created_at = "2026-06-28T10:05:00Z"  # ISO8601 UTC, 只读

[wikis.reading-notes]
path = "reading-notes"
created_at = "2026-06-28T10:10:00Z"
```

### 字段表

| 字段 | 类型 | 可 set | 可 unset | 说明 |
| --- | --- | --- | --- | --- |
| `schema_version` | int | ❌ | ❌ | CLI 内部维护，标记 schema 升级版本 |
| `created_at` | ISO8601 string | ❌ | ❌ | workspace 初始化时间，由 `init` 一次性写入 |
| `default_model` | string | ✅ | ✅ | 默认模型 ID；Phase 1 仅作元数据 |
| `templates_version` | string | ❌ | ❌ | 反映 `templates/` 目录当前版本 |
| `[wikis.<name>]` | table | （通过 `wiki add` / `remove`） | — | wiki 注册表 |
| `[wikis.<name>].path` | string | ❌ | — | 相对 workspace 根的路径（与 name 同值） |
| `[wikis.<name>].created_at` | ISO8601 string | ❌ | — | wiki 注册时间 |

### name 校验

- 与 wiki_metadata.toml 的 `name` 校验一致：小写字母 / 数字 / `-` / `_`，长度 1–64
- `[wikis]` 表的 KEY 必须唯一

### Phase 2 计划增量

- 新增 `[[models]]` 表（指向 `workspace_models.toml`，或直接把模型清单 inline）
- 新增 `model_id` 字段替代 `default_model`（详见 Phase 2 设计文档）

---

## 4.2 `<wiki>/wiki_metadata.toml`

**位置**：每个 wiki 子目录下（`<wiki>/wiki_metadata.toml`）

**性质**：git 入库；可被用户手工编辑

### 完整 schema（Phase 1）

```toml
schema_version = 1                          # int, 只读
name = "llm-systems"                        # string, 只读, 与 workspace.toml key 一致
topic = "LLM Systems"                       # string, 只读, setup_wiki.py 的主题名
display_name = "LLM 系统研究"               # string, 可 set, 可 unset (变空)
description = "跟踪 LLM 系统相关论文与博客" # string, 可 set, 可 unset (变空)
tags = ["research", "llm"]                  # list of string, 可 set, 可 unset (变 [])
model = "MiniMax-M3"                        # string, 可 set, 可 unset; Phase 1 元数据
created_at = "2026-06-28T10:05:00Z"         # ISO8601 UTC, 只读
updated_at = "2026-06-28T10:15:00Z"         # ISO8601 UTC, CLI 自动 bump
```

### 字段表

| 字段 | 类型 | 可 set | 可 unset | 说明 |
| --- | --- | --- | --- | --- |
| `schema_version` | int | ❌ | ❌ | CLI 内部维护 |
| `name` | string | ❌ | ❌ | 与 workspace.toml `[wikis]` key 一致；CLI 不允许改 |
| `topic` | string | ❌ | ❌ | 传给 setup_wiki.py 的主题名；初始化后固定 |
| `display_name` | string | ✅ | ✅ | 人类可读名；unset 后留空 |
| `description` | string | ✅ | ✅ | 一句话描述；unset 后留空 |
| `tags` | list<string> | ✅（逗号分隔替换） | ✅ | 字符串列表；unset 后清空 |
| `model` | string | ✅ | ✅ | 模型 ID；unset 后留空 |
| `created_at` | ISO8601 string | ❌ | ❌ | wiki 创建时间，`add` 时一次性写入 |
| `updated_at` | ISO8601 string | ❌（自动） | ❌ | 每次 set 后由 CLI 自动 bump |

### 字段值规则

- **string 字段**：UTF-8 任意字符；允许为空字符串（视为 unset）
- **tags 元素**：小写字母 / 数字 / `-` / `_`，长度 1–32；逗号分隔输入、去重、保留顺序
- **model 字段**：字符串；Phase 1 不做格式校验（任何字符串都接受），Phase 2 引入 registry 后会校验是否在 `workspace_models.toml` 中存在
- **ISO8601 时间**：UTC + `Z` 后缀，秒精度（如 `"2026-06-28T10:05:00Z"`）

### 自动 bump 规则

- 任何 `set` 操作成功后，`updated_at` 立即设为当前 UTC ISO8601
- `unset` 不 bump（删除字段不视为内容变更）
- 用户手工编辑该文件时，CLI 不主动干预 `updated_at`（用户可手工改）

### Phase 2 计划增量

- `model` 字段重命名为 `model_id`
- 新增校验：值必须在 `workspace_models.toml` 中存在

---

## 4.3 `templates/` 目录

**位置**：CLI 仓库根目录下

**性质**：git 入库

```
templates/
├── wiki_metadata.toml.template
└── CLAUDE.md.template          # 可选, Phase 1 不消费
```

### `wiki_metadata.toml.template`

初始模板，`wiki add` 时拷出实例后填充：

```toml
schema_version = 1
name = "__NAME__"
topic = "__TOPIC__"
display_name = ""
description = ""
tags = []
model = ""
created_at = "__NOW_ISO8601__"
updated_at = "__NOW_ISO8601__"
```

模板替换占位符：

| 占位符 | 替换为 |
| --- | --- |
| `__NAME__` | wiki 名（来自 `--name` flag） |
| `__TOPIC__` | 主题名（来自 `--topic` flag 或 fallback 到 `--name`） |
| `__NOW_ISO8601__` | 当前 UTC ISO8601 时间 |

### ~~`CLAUDE.md.template`~~（已废弃，spec 0.2.0+ 移除）

> spec 0.2.0 起，CLI 不再消费本仓 `templates/` 下的 CLAUDE.md 模板——CLI 直接读 SKILL submodule 下的
> `references/claude-md-template.md`（wiki 仓）与 `workspace-claude-md-template.md`（workspace 仓）字节拷。
> 详情见 [05-templates-submodule §5.2 / §5.5](05-templates-submodule.md)。
> 本文件如仍存在是历史残留。

---

## 4.4 schema_version 演进策略

### 兼容规则

- CLI 读取 schema_version = N 的文件时：若 N > CLI 支持的最高版本，报错 `SchemaTooNew`
- CLI 读取 schema_version = N 的文件时：若 N < CLI 支持的最低版本，**自动迁移**到当前版本
- 写入时：始终写当前 CLI 版本的 schema_version

### Phase 1 当前策略

- 只支持 `schema_version = 1`
- 读到的文件若不是 1，报错 `SchemaVersionUnsupported`
- **不**做版本迁移——Phase 1 是首个 schema，未来升级到 v2 时再补迁移代码

### 未来升级示例

当 schema 升级到 v2 时：

1. CLI 检测到 v1 文件，调用 `_migrate_v1_to_v2()`
2. 迁移函数完成字段重命名 / 结构调整
3. 写回时 schema_version = 2

---

## 4.5 原子写策略

所有 CLI 写入的元数据文件（workspace.toml / wiki_metadata.toml）走**统一原子写**：

```python
tmp_path = file_path + f".tmp.{os.getpid()}"
with open(tmp_path, "w", encoding="utf-8") as f:
    f.write(content)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp_path, file_path)  # POSIX atomic
```

- 失败时清理 tmp 文件
- 同一进程多次写入用不同 pid 后缀，避免冲突
- 写完后 fsync，确保断电也不丢失

---

## 4.6 文件引用清单

| 文件 | 由谁写 | 由谁读 | 备份建议 |
| --- | --- | --- | --- |
| `workspace.toml` | `llmw init` / `wiki add` / `wiki remove` / `llmw config` | 所有 workspace / wiki 命令 | git 入库 |
| `<wiki>/wiki_metadata.toml` | `wiki add` / `wiki config` | `wiki show` / `wiki config` / `wiki enter`（仅元数据展示） | git 入库 |
| `<wiki>/CLAUDE.md` | CLI `wiki add`（按 `claude-md-template.md` 拷） | `wiki show`（仅 frontmatter）/ `wiki enter`（cat 注入）/ Claude Code 会话 | git 入库（用户宪法） |
| `<workspace>/CLAUDE.md` | CLI `init`（按 `workspace-claude-md-template.md` 拷） | Claude Code 会话 | git 入库（用户宪法） |
| `templates/wiki_metadata.toml.template` | CLI 仓库维护 | `wiki add` | git 入库（CLI 仓库） |

---

## 4.7 非内容页索引产物（CLI init 时刻落盘，spec 0.10.0 / 0.3.0 同步对齐）

> 以下 5 类**不是** wiki 内容页（不参与 5 类内容页 frontmatter 5 必填 lint），
> 是 CLI 在 init 时刻写一次的"索引 / 元数据"层文件，被上级 CLAUDE.md 用 `@<path>` import 会话常驻。
> 详细字段约定与跨 skill 纪律见对应 spec §：
> - wiki 三类 → [wiki-spec §5.1 (MEMORY.md)](../../my_SKILL/llm-wiki-management/references/wiki-spec.md#51-memorymemorymd索引) / [§9.1 (tags.md)](../../my_SKILL/llm-wiki-management/references/wiki-spec.md#91-tag-白名单来源080) / [§14 (SCRIPTS.md)](../../my_SKILL/llm-wiki-management/references/wiki-spec.md#14-scripts本-wiki-仓扩展脚本目录090)
> - workspace 两类 → [workspace-spec §5 (INDEX.md)](../../my_SKILL/llm-workspace-management/references/workspace-spec.md#5-indexmdskill-维护) / [§9.1 (MEMORY.md)](../../my_SKILL/llm-workspace-management/references/workspace-spec.md#91-memorymemorymd索引)

### 4.7.1 不可变约束（强约束）

| 文件 | 维护方（init 之后） | 维护方变更约束 |
| --- | --- | --- |
| `<wiki>/MEMORY/MEMORY.md` | LLM agent | 同步追加索引行；spec §5.2 每条 `*.md` 必须在此列出一行 |
| `<wiki>/wiki/tags.md` | LLM agent | 裸 bullet，直接追加新 tag 或删除误判项 |
| `<wiki>/scripts/SCRIPTS.md` | 用户 + LLM agent | 添加 / 修改 / 删除脚本与同步索引段是原子动作 |
| `<workspace>/MEMORY/MEMORY.md` | LLM agent（跨 wiki） | 同步追加索引行；spec §9.2 同 wiki 形态 |
| `<workspace>/INDEX.md` | skill（`llm-workspace-management`） | CLI 不参与 |

> **CLI 不覆盖**：spec §8 + §12 拒绝条件的精神——5 类产物任一已存在即拒绝（详 [10-spec-alignment §10.3 D1](10-spec-alignment-2026-07.md#d1-check_not_initialized-拒绝条件扩-5-个)）。

### 4.7.2 形态约定

- **无 frontmatter**：5 类均为 plain markdown；与 `wiki/index.md` / `wiki/log.md` 等内容页形态不同
- **不会被 lint 5 必填校验**：`scripts/lint_wiki.py` 的 `find_md_files` 自然不递归 `MEMORY/` / `wiki/tags.md` / `scripts/`——三类索引文件不参与内容页 schema 校验
- **命名**：`<wiki>/MEMORY/` 大写、`<wiki>/wiki/tags.md` 小写、`<wiki>/scripts/SCRIPTS.md` 大写混排（与目录名同 source）
- **占位符渲染**：4 份 fixture 均为无占位符少数派（与 `index.md.txt` / `log.md.txt` / `claude-md-template.md` 不同；详 [10-spec-alignment §10.3 D3](10-spec-alignment-2026-07.md#d3-scriptsmd-落盘流程2026-07-02-复核后修订)）

### 4.7.3 CLI 生成时刻

| 文件 | CLI 落盘命令 | fixture 来源 |
| --- | --- | --- |
| `<wiki>/MEMORY/MEMORY.md` | `wiki add` | `my_SKILL/llm-wiki-management/references/fixtures/memory-index.txt` |
| `<wiki>/wiki/tags.md` | `wiki add` | `my_SKILL/llm-wiki-management/references/fixtures/tags.md.txt` |
| `<wiki>/scripts/SCRIPTS.md` | `wiki add` | `my_SKILL/llm-wiki-management/references/fixtures/scripts.md.txt` |
| `<workspace>/MEMORY/MEMORY.md` | `init`（幂等：已存在跳过） | `my_SKILL/llm-workspace-management/references/fixtures/memory-index.txt` |
| `<workspace>/INDEX.md` | **无**（CLI 不参与；skill 在 `scan` 时按需创建） | — |