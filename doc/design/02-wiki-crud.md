# 02 · Wiki CRUD 命令

本章覆盖五个 wiki 级命令：`llmw wiki add` / `remove` / `show` / `config` / `enter`。

## 命令格式统一约定

**所有 wiki 命令**采用 `llmw wiki --name=<name> <action> [flags...]` 形式：

- `--name` 是前置 flag，标识目标 wiki
- `<action>` 是子命令：`add` / `remove` / `show` / `config` / `enter`
- 各 action 自己的 flag 跟在 action 之后

示例：

```
llmw wiki --name=llm-systems add --no-setup
llmw wiki --name=llm-systems remove --purge --yes
llmw wiki --name=llm-systems show --json
llmw wiki --name=llm-systems config set display_name "LLM 系统研究"
llmw wiki --name=llm-systems config          # TTY → 交互模式
llmw wiki --name=llm-systems enter --dry-run
```

> 与 workspace 级命令的关系：所有 wiki 命令运行前必须先解析 workspace 根（同 `01` 章
> 的"默认路径解析"）；workspace 根不存在则直接报错，不进入 wiki 操作。

---

## 2.1 `llmw wiki --name=<name> add`

**作用**：在当前 workspace 下新建一个 wiki 子目录并注册。

### 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--name NAME`（必填） | — | wiki 名称（小写、字母数字与 `-` / `_`），同时作为子目录名 |
| `--topic TOPIC` | = `--name` 值 | 传给 `setup_wiki.py` 的主题名；交互提示时作为预填值 |
| `--display-name NAME` | — | 人类可读名；交互提示时作为预填值 |
| `--description TEXT` | — | 一句话描述；交互提示时作为预填值 |
| `--tag TAG` | `[]` | 标签（可重复）；交互提示时作为预填列表 |
| `--model MODEL` | — | 模型 ID；交互提示时作为预填值 |
| `--no-setup` | `false` | 仅注册已有子目录，不调 `setup_wiki.py` |

> **设计原则**：所有 metadata 字段（topic / display_name / description / tags / model）
> 既支持 flag 形式预填，也支持在 TTY 下走交互提示。`--no-setup` 是结构性选项，**仅**以 flag 形式提供。

### name 校验

- 仅允许：小写字母 / 数字 / `-` / `_`
- 长度 1–64
- 不允许与 workspace 已有 wiki 同名（`workspace.toml [wikis]` 表查重）

### 行为步骤

1. **校验 workspace**（同 01 章）；不存在则 `WorkspaceNotFound`
2. **校验 `--name` 格式与唯一性**；冲突 → `WikiExists`
3. **创建子目录**：`mkdir <workspace>/<name>`
4. **（若非 `--no-setup`）调用 `setup_wiki.py`**：
   - 命令构造：`python <skill-path>/setup_wiki.py <topic>`（cwd 设为 `<workspace>/<name>`）
   - 期望返回 0；非零 → 回滚（删除子目录）并抛 `SetupFailed`
5. **从 `templates/wiki_metadata.toml.template` 生成 `wiki_metadata.toml` 骨架**：
   - 写入 `name`、`topic`、`schema_version`、`created_at`/`updated_at`（UTC ISO8601）
   - metadata 字段（display_name / description / tags / model）暂为空，待交互补充
   - 原子写入 `<workspace>/<name>/wiki_metadata.toml`
6. **交互式收集 metadata**（TTY 下；非 TTY 见边界）：
   - 依次提示 display_name / description / tags / model
   - 每个提示的默认值：若 flag 已传则用 flag 值，否则当前值（空）
   - 用户可直接回车跳过（保留当前值）
   - tags 子菜单：a 添加 / r 移除（按编号）/ s 替换全部 / d 完成
7. **更新 `workspace.toml [wikis]` 表**：追加 `{ name = "<name>", path = "<name>", created_at = "<now>" }`，原子写
8. **提示用户**：
   - "wiki 已创建：<name>（<workspace>/<name>）"
   - "请 git add + commit 跟踪（建议 commit message: `wiki: add <name>`）"
9. 退出码 0

### 交互提示示例

```
$ llmw wiki --name=llm-systems add
✓ 子目录已创建：/home/user/yzr_llm_wiki_workspace/llm-systems
✓ setup_wiki.py 已完成
✓ wiki_metadata.toml 已生成

请填写 wiki 元数据（直接回车保留当前值 / q 跳过全部）:

  display_name        [当前: <未设置>]      : LLM 系统研究
  description         [当前: <未设置>]      : 跟踪 LLM 系统相关论文与博客
  tags                [当前: []]            : <进入子菜单>
    操作 [a 添加 / r 移除 / s 替换 / d 完成]: a
    新 tag: research
    操作 [a 添加 / r 移除 / s 替换 / d 完成]: a
    新 tag: llm
    操作 [a 添加 / r 移除 / s 替换 / d 完成]: d
  model               [当前: <未设置>]      : <回车跳过，使用 workspace.default_model>

✓ metadata 已写入 wiki_metadata.toml
✓ 已注册到 workspace.toml
```

### 边界

- **非 TTY 下运行 `llmw wiki --name=<name> add`**：要求所有 metadata 字段以 flag 形式传齐（`--display-name`、`--description`、`--tag`、`--model`）；缺任何一项 → 报错 `MissingRequiredFlag`
- **`--no-setup` 场景**：CLI 不创建 `raw/`、`wiki/`、`CLAUDE.md`；仅写 `wiki_metadata.toml` + 在 `[wikis]` 注册。前提条件：`<workspace>/<name>` 已存在且用户已自己跑过 `setup_wiki.py`（CLI 不验证子目录内部结构）
- setup_wiki.py 失败时**完整回滚**（删除子目录、不写 workspace.toml、删 wiki_metadata.toml）；不保留半成品
- `--name` 与子目录路径一致；用户无法指定不同的 `path`
- 交互中 `q` / `Ctrl-D` / `Ctrl-C` 视为"跳过剩余 metadata"——已收集的写入文件，未填的留空

---

## 2.2 `llmw wiki --name=<name> remove`

**作用**：从 workspace 中移除一个 wiki（默认仅取消注册；可选删除子目录）。

### 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--name NAME`（必填） | — | 要移除的 wiki 名 |
| `--purge` | `false` | 同时删除 `<workspace>/<name>` 子目录 |
| `--yes` / `-y` | `false` | 跳过二次确认 |

### 行为步骤

1. **校验 workspace**；不存在 → `WorkspaceNotFound`
2. **校验 `--name` 在 `[wikis]` 中存在**；不存在 → `WikiNotFound`
3. **（若 `--purge` 且无 `--yes`）二次确认**：
   - 交互提示（TTY）："将删除 <workspace>/<name> 子目录及所有内容，确认？[y/N]"
   - 非 TTY + 无 `--yes` → 报错 `PurgeRequiresConfirmation`
4. **从 `workspace.toml [wikis]` 删除条目**，原子写
5. **（若 `--purge`）`rm -rf <workspace>/<name>`**
6. 退出码 0

### 边界

- 默认（不带 `--purge`）只是"取消注册"——子目录、`raw/`、`wiki/`、`CLAUDE.md`、`wiki_metadata.toml` **全部保留**
- `--purge` 删除整个子目录，不可恢复（除非从 git 恢复）
- 不删除外部引用（如用户在 wiki 内容里写的跨 wiki 链接）——这属于 lint 阶段，Phase 2

---

## 2.3 `llmw wiki --name=<name> show`

**作用**：显示单个 wiki 的详情。

### 参数

| 参数 | 说明 |
| --- | --- |
| `--name NAME`（必填） | wiki 名 |
| `--json` | 输出 JSON（全局 flag） |

### 表格输出（默认）

```
NAME              llm-systems
PATH              /home/user/yzr_llm_wiki_workspace/llm-systems
TOPIC             LLM Systems
DISPLAY_NAME      LLM 系统研究
DESCRIPTION       跟踪 LLM 系统相关论文与博客
TAGS              research, llm
MODEL             claude-sonnet-4-6  (fallback: workspace.default_model)
CLAUDE_MD         ✓ found  (last modified: 2026-06-28 10:05:00)
WIKI_METADATA     ✓ found
RAW_DIR           ✓ found (12 files)
WIKI_DIR          ✓ found (47 pages)
```

- `MODEL` 后的 "(fallback: ...)" 表示：wiki.model 为空，使用了 workspace 的 default_model
- `✓ found` 后括号里给最后修改时间 / 文件数；缺失则 `✗ missing`

### JSON 输出

```json
{
  "name": "llm-systems",
  "path": "/home/user/yzr_llm_wiki_workspace/llm-systems",
  "topic": "LLM Systems",
  "display_name": "LLM 系统研究",
  "description": "跟踪 LLM 系统相关论文与博客",
  "tags": ["research", "llm"],
  "model": "claude-sonnet-4-6",
  "model_source": "workspace.default_model",
  "schema_version": 1,
  "created_at": "2026-06-28T10:05:00Z",
  "updated_at": "2026-06-28T10:05:00Z",
  "existence": {
    "claude_md": true,
    "wiki_metadata_toml": true,
    "raw_dir": true,
    "wiki_dir": true
  },
  "counts": {
    "raw_files": 12,
    "wiki_pages": 47
  }
}
```

### 行为步骤

1. 解析 workspace、定位 `<workspace>/<name>`
2. 读 `workspace.toml [wikis.<name>]` 拿 path
3. 读 `<wiki>/wiki_metadata.toml` 拿详情字段
4. 读 `<wiki>/CLAUDE.md` frontmatter（仅 frontmatter，不读正文）
5. 探测 `<wiki>/raw/` 与 `<wiki>/wiki/` 存在性 + 文件 / 页面计数
6. 解析最终 model：`<wiki>.model or workspace.default_model`
7. 格式化输出

### 边界

- 子目录缺失：`existence.*` 全 false，路径仍打印（绝对路径）
- `wiki_metadata.toml` 缺失：除该文件相关字段外其余仍能展示，标 `✗ missing`
- `CLAUDE.md` 缺失：同上
- 不读 `raw/` 与 `wiki/` 下的具体内容——只数文件 / 页面

---

## 2.4 `llmw wiki --name=<name> config`

**作用**：读写 `<wiki>/wiki_metadata.toml`。

### 参数

```
llmw wiki --name=<name> config get KEY
llmw wiki --name=<name> config set KEY VALUE
llmw wiki --name=<name> config unset KEY
llmw wiki --name=<name> config                # 无参数 + TTY → 交互模式（默认）
```

### KEY 白名单

| KEY | 可 set | 可 unset | 说明 |
| --- | --- | --- | --- |
| `display_name` | ✅ | ✅ | 人类可读名 |
| `description` | ✅ | ✅ | 一句话描述 |
| `tags` | ✅（逗号分隔替换） | ✅ | 字符串列表 |
| `model` | ✅ | ✅（fallback 到 workspace.default_model） | 模型 ID |
| `name` | ❌ | ❌ | 只读 |
| `topic` | ❌ | ❌ | 只读 |
| `schema_version` | ❌ | ❌ | 只读 |
| `created_at` | ❌ | ❌ | 只读 |
| `updated_at` | ❌ | ❌ | 由 CLI 内部维护（每次 set 后自动 bump） |

### tags 的特殊语义

- `set tags a,b,c`：**替换**整个列表为 `[a, b, c]`（逗号分隔输入、去重、保留顺序）
- `unset tags`：清空列表（`[]`）
- tags 元素校验：与 `name` 同样的字符集（小写字母 / 数字 / `-` / `_`），长度 1–32

### 行为步骤（set）

1. 校验 KEY 在白名单且可 set
2. 校验 VALUE 格式（如 tags 元素校验）
3. 读 `wiki_metadata.toml`
4. 更新目标字段
5. **自动 bump** `updated_at = <UTC ISO8601 now>`
6. 原子写
7. 退出码 0

### 交互模式（默认启动）

`llmw wiki --name=<name> config` 无 KEY 参数运行时，**默认就是交互模式**（不要求 TTY 检测）：
所有可写 KEY 列出，编号选择，进入对应编辑子流程。`get` / `set` / `unset` 子命令形式保留供脚本场景使用。

> 设计差异：与 `llmw config`（workspace 级）需要 TTY 检测不同，wiki 级 config **默认交互**，
> 因为 wiki 通常由人手逐个编辑，脚本场景少见。

```
$ llmw wiki --name=llm-systems config

wiki "llm-systems" 配置项 (/home/user/yzr_llm_wiki_workspace/llm-systems/wiki_metadata.toml):

  1. display_name      (str, 当前: "LLM 系统研究")
  2. description        (str, 当前: "跟踪 LLM 系统相关论文与博客")
  3. tags               (list, 当前: ["research", "llm"])
  4. model              (str, 当前: <unset>)

选择要编辑的项 [1-4, q 退出]: 3
当前 tags: research, llm
  a) 添加 tag
  r) 移除 tag
  s) 替换全部 tags
操作 [a/r/s/q]: a
新 tag: alignment
✓ tags = ["research", "llm", "alignment"]

继续编辑？[Y/n]: n
```

### 边界

- 非 TTY 下运行 `llmw wiki --name=<name> config` 无参数：仍走交互模式（`input()` 会失败，需脚本使用子命令形式）
- 选 `q` / `Ctrl-D` / `Ctrl-C` 视为正常退出，退出码 0
- `unset model` 后，该 wiki 重新 fallback 到 `workspace.default_model`；若 workspace 也未设，show 中 model 字段显示 `✗ no model configured`