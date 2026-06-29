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
| `--topic TOPIC` | = `--name` 值 | 主题名；占位符替换进 CLAUDE.md / index.md / log.md / MEMORY/README.md |
| `--display-name NAME` | — | 人类可读名；交互提示时作为预填值 |
| `--description TEXT` | — | 一句话描述；交互提示时作为预填值 |
| `--tag TAG` | `[]` | 标签（可重复）；交互提示时作为预填列表 |
| `--model MODEL` | — | 模型 ID；交互提示时作为预填值 |
| `--git` | `false` | opt-in：初始化 git 仓（spec §7）；默认不碰 git |

> **设计原则**：所有 metadata 字段（topic / display_name / description / tags / model）
> 既支持 flag 形式预填，也支持在 TTY 下走交互提示。`--git` 是结构性选项，**仅**以 flag 形式提供。
> wiki 骨架落盘不可跳过（spec §8 拒绝条件强约束）——旧版 `--no-setup` 已删除。

### name 校验

- 仅允许：小写字母 / 数字 / `-` / `_`
- 长度 1–64
- 不允许与 workspace 已有 wiki 同名（`workspace.toml [wikis]` 表查重）

### 行为步骤

1. **校验 workspace**（同 01 章）；不存在则 `WorkspaceNotFound`
2. **校验 `--name` 格式与唯一性**；冲突 → `WikiExists`
3. **spec §8 文件级拒绝**：若 `<workspace>/<name>/CLAUDE.md` 或 `<wiki>/index.md` 已存在 → `WikiAlreadyInitialized`（exit 1）
4. **创建子目录**：`mkdir <workspace>/<name>`
5. **调 `llmw.wiki.init_wiki.render_and_write`**（CLI 内联实现）：
   - 读 `my_SKILL/.../references/claude-md-template.md` + 4 个 fixtures（`index.md.txt` / `log.md.txt` / `memory-readme.txt` / `gitignore.txt`）
   - 替换 4 占位符：`{{TOPIC_NAME}}` / `{{SETUP_DATE}}` / `{{WIKI_SPEC_VERSION}}` / `{{CLI_VERSION}}`
   - 创建 8 个子目录（`raw/{articles,assets}` + 5 个内容页子目录 + `wiki/MEMORY`）+ atomic_write 5 份字面量产物
   - 失败 → `SetupFailed`（exit 2）
6. **生成 `wiki_metadata.toml` 骨架**：
   - 写入 `name`、`topic`、`schema_version`、`created_at`/`updated_at`（UTC ISO8601）
   - metadata 字段（display_name / description / tags / model）暂为空，待交互补充
   - 原子写入 `<workspace>/<name>/wiki_metadata.toml`
7. **交互式收集 metadata**（TTY 下；非 TTY 见边界）：
   - 依次提示 display_name / description / tags / model
   - 每个提示的默认值：若 flag 已传则用 flag 值，否则当前值（空）
   - 用户可直接回车跳过（保留当前值）
   - tags 子菜单：a 添加 / r 移除（按编号）/ s 替换全部 / d 完成
8. **更新 `workspace.toml [wikis]` 表**：追加 `{ name = "<name>", path = "<name>", created_at = "<now>" }`，原子写
9. **（若 `--git`）调 `llmw.wiki.git_init.init`**：
   - 前置：`which git` + 不在已有仓内 → 任一不满足则 warn 跳过、不阻断
   - 通过：`git init` → 默认 main → local user.email/name → 5 个 `.gitkeep` → `git add .` → `git commit`
10. **提示用户**：
    - "wiki 已创建：<name>（<workspace>/<name>）"
    - 若启用 git："已 git init + commit（分支 main，消息：Initial wiki scaffold）"
    - 否则："未启用 git：如需跟踪，手动 `git init && git add . && git commit -m 'Initial wiki scaffold'`；或下次 add 时加 `--git`"
11. 退出码 0

### 交互提示示例

```
$ llmw wiki --name=llm-systems add
✓ 子目录已创建：/home/user/yzr_llm_wiki_workspace/llm-systems
✓ wiki 骨架已落盘（CLAUDE.md / .gitignore / wiki/{index,log,MEMORY/README}.md + raw/ + 5 内容页子目录）
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
- **spec §8 拒绝条件**：若目标 `<wiki-root>` 已含 `CLAUDE.md` 或 `wiki/index.md` → `WikiAlreadyInitialized`（exit 1），不覆盖；用户必须先备份 + 删除
- **CLI 不做半成品回滚**：与旧版不同，`render_and_write` 失败时仅 raise `SetupFailed`；目录骨架已部分落盘（spec §6 期望落地状态）。CLI 不主动 rm wiki 目录，由用户决定是否保留部分产物
- **目标目录非空但不含 `CLAUDE.md` / `wiki/index.md`**：`mkdir(exist_ok=True)` 允许继续；CLI 不主动拒绝半成品目录。spec §8 拒绝条件**只**针对 CLAUDE.md / wiki/index.md 两个文件(不针对目录本身)。若目录已有 `raw/articles/foo.pdf` 等用户数据,CLI 写盘 5 个固定文件(`CLAUDE.md` / `.gitignore` / `wiki/index.md` / `wiki/log.md` / `wiki/MEMORY/README.md`)时**不覆盖**已有文件 — `atomic_write` 会失败而非静默替换(用户需手动处理)
- `--name` 与子目录路径一致；用户无法指定不同的 `path`
- 交互中 `q` / `Ctrl-D` / `Ctrl-C` 视为"跳过剩余 metadata"——已收集的写入文件，未填的留空
- `--git` 前置不通过（git 缺失 / 已在仓内）→ warn 至 stderr 跳过，不阻断落盘（spec §7）

---

## 2.2 `llmw wiki --name=<name> remove`

**作用**：从 workspace 中移除一个 wiki（默认仅取消注册；可选删除子目录）。

### 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--name NAME`（必填） | — | 要移除的 wiki 名 |
| `--purge` | `false` | 同时删除 `<workspace>/<name>` 子目录(默认先备份到 `.llmw-trash/`) |
| `--no-backup` | `false` | 跳过 `--purge` 的备份步骤,直接 `rm -rf`(CI / 脚本场景;对应 wiki-spec.md "delete 带备份" 的 escape hatch) |
| `--yes` / `-y` | `false` | 跳过二次确认 |

### 行为步骤

1. **校验 workspace**；不存在 → `WorkspaceNotFound`
2. **校验 `--name` 在 `[wikis]` 中存在**；不存在 → `WikiNotFound`
3. **（若 `--purge` 且无 `--yes`）二次确认**：
   - 交互提示（TTY）："将删除 <workspace>/<name> 子目录及所有内容，确认？[y/N]"
   - 非 TTY + 无 `--yes` → 报错 `PurgeRequiresConfirmation`
4. **从 `workspace.toml [wikis]` 删除条目**，原子写
5. **（若 `--purge`）默认走备份路径**：
   - 先确保 workspace `.gitignore` 含 `.llmw-trash/`(managed block 升级;老 workspace 2 行 block 自动替换为 3 行)
   - `mv` `<workspace>/<name>` 到 `<workspace>/.llmw-trash/<name>-<ISO8601>/`(POSIX rename 原子;同一 FS 下)
   - 失败 → `BackupFailed`(exit 2),不删 wiki
   - 加 `--no-backup` → 跳过备份,直接 `safe_rmtree(wiki_path)`
6. 打印路径(`[llmw] 备份: <path>` 或 `[llmw] --no-backup: 直接删除 <path>`)
7. 退出码 0

### 边界

- 默认（不带 `--purge`）只是"取消注册"——子目录、`raw/`、`wiki/`、`CLAUDE.md`、`wiki_metadata.toml` **全部保留**
- `--purge` 默认先备份到 `<workspace>/.llmw-trash/<name>-<ISO8601>/`,**不可恢复性 = 用户手动 `rm -rf` 该备份**(CLI 不自动清理 trash)
- `--purge --no-backup`:跳过备份,直接 `rm -rf`(对应 wiki-spec.md:14 "delete 带备份" 的 escape hatch)
- 备份失败 → `BackupFailed` 阻断,不删 wiki
- `.llmw-trash/` 已加入 workspace `.gitignore` managed block(与 `workspace_models.toml` + `*/.claude/settings.local.json` 同行)
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