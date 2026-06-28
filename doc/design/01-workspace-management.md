# 01 · Workspace 管理命令

本章覆盖三个 workspace 级命令：`llmw init` / `llmw config` / `llmw list`。

## 默认路径解析

所有 workspace 级命令运行前需要解析"当前 workspace 根"：

| 来源 | 说明 |
| --- | --- |
| `--workspace PATH`（全局 flag） | 用户显式指定，最高优先级 |
| `$LLMW_WORKSPACE` 环境变量 | 用户通过 env 配置 |
| `~/yzr_llm_wiki_workspace`（默认） | 硬编码兜底 |

解析逻辑由 `llmw.config.resolve_workspace_root()` 统一负责；任一命令运行前
调用一次，失败抛 `WorkspaceNotFound`（详见 `06-error-handling.md`）。

---

## 1.1 `llmw init`

**作用**：初始化一个 workspace。

### 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--path PATH` | 解析后的默认路径（见上） | workspace 根目录绝对路径 |
| `--git` / `--no-git` | `--git` | 是否在该目录执行 `git init` |

### 行为步骤

1. **校验**：若 `PATH` 已存在：
   - 目录非空 → 报错 `WorkspaceExists`，保留现场
   - 目录为空 → 继续
2. **创建目录**：`mkdir -p PATH`
3. **（若 `--git`）**：`git init PATH`（非交互，失败抛 `GitUnavailable`）
4. **写 `workspace.toml` 骨架**：
   ```toml
   schema_version = 1
   created_at = "<UTC ISO8601>"
   templates_version = "1"

   [wikis]
   ```
   > 注意：`default_model` **不写入**——init 只搭骨架，模型配置走 `llmw config set`（见 1.2）。
5. **提示用户**（stdout，非 stderr）：
   - "workspace 已初始化于 <PATH>"
   - "cd <PATH> 后可用 `llmw wiki add <name>` 新建第一个 wiki"
   - "可用 `llmw config set default_model <model-id>` 配置默认模型"
6. **退出码 0**

### 边界

- `--path` 必须解析为绝对路径；若用户给了相对路径，CLI 自动 `os.path.abspath`
- `PATH` 与默认路径不一致时（如 `--path /opt/foo`），仍正常初始化，不影响后续 PATH 解析
- init **不**自动 cd 进去（用户后续自行 `cd`）
- init **不**写 `default_model`——该字段在 `wiki add` 时若 wiki 未指定 model 才被 fallback 读取；为空时 wiki 必须自配 model

---

## 1.2 `llmw config`

**作用**：读写 `workspace.toml` 中的 workspace 级配置。

### 参数

```
llmw config get KEY                # 取值（无 KEY 时打印整个 toml）
llmw config set KEY VALUE          # 写入
llmw config unset KEY              # 删除（仅允许删除可空字段）
```

### KEY 白名单

| KEY | 可 set？ | 可 unset？ | 说明 |
| --- | --- | --- | --- |
| `default_model` | ✅ | ❌ | 兜底模型；为空时 wiki 必须自配 |
| `templates_version` | ❌（只读） | ❌ | 反映 templates/ 目录当前版本，由 CLI 内部维护 |
| `created_at` | ❌（只读） | ❌ | workspace 创建时间，永久记录 |
| 其他 | ❌ | ❌ | 报错 `InvalidConfigKey` |

> 注：`[wikis]` 表不是单个 KEY，而是结构化字段——通过 `llmw wiki add/remove/config`
> 操作，不走 `llmw config`。

### 行为步骤（set）

1. 解析 KEY 是否在白名单且可 set
2. 读现有 `workspace.toml`
3. 更新对应字段
4. **原子写**：
   - 临时文件 `<workspace.toml>.tmp.<pid>`
   - `os.replace(tmp, workspace.toml)`（POSIX 原子）
   - 失败时清理 tmp 文件，不留垃圾
5. 退出码 0

### 行为步骤（unset）

- 仅当 KEY 在白名单且"可 unset"列标记 ✅ 时执行
- 否则报错 `KeyNotUnsettable`

### 行为步骤（get）

- 无 KEY：完整 dump `workspace.toml`（保留 TOML 格式）
- 有 KEY：仅打印该字段值（不含 KEY 名）
- 不存在的 KEY → 报错 `ConfigKeyMissing`

### 交互模式（自动启动）

`llmw config` 无任何参数运行时，若 `sys.stdin.isatty()` 为 true（标准 TTY），
**自动进入交互模式**。非 TTY（管道 / 重定向 / CI）下无参数运行则打印字段列表 + 用法后退出 0，**不阻塞**。

```
$ llmw config

workspace 配置项 (/home/user/yzr_llm_wiki_workspace/workspace.toml):

  1. default_model         (str, 当前: <unset>)
  2. templates_version     (str, 只读, 当前: "1")
  3. created_at            (str, 只读, 当前: "2026-06-28T10:00:00Z")

选择要编辑的项 [1-3, q 退出]: 1
当前 default_model: <unset>
输入新值（回车跳过 / '-' 清空）: claude-sonnet-4-6
✓ default_model = "claude-sonnet-4-6"

继续编辑？[Y/n]: y
选择要编辑的项 [1-3, q 退出]: 2
⚠ templates_version 是只读字段，无法编辑

继续编辑？[Y/n]: n
```

**实现约束**：

- 仅使用 Python 标准库（`input()` + ANSI escape），不引入第三方 TUI 库
- 只读字段（`templates_version` / `created_at`）在交互列表中显示但标"只读"，选中时报错并跳回选择
- 每次 set 后立即原子写、不缓冲——断电/ctrl-c 也不留半成品文件
- `q` / `Ctrl-D` / `Ctrl-C` 都视为"正常退出"，退出码 0

---

## 1.3 `llmw list`

**作用**：列出当前 workspace 中的所有 wiki。

### 参数

| 参数 | 说明 |
| --- | --- |
| `--json` | 输出结构化 JSON，便于脚本消费 |
| `--tag TAG` | 仅列出 tags 含 TAG 的 wiki（可重复，多个 tag 是 AND 关系） |

> 注：`--json` 是全局 flag（与 `llmw list --json` 等同 `llmw --json list`），
> 由 `llmw.cli` 统一处理。本表只列该命令专属 flag。

### 表格输出（默认）

列：NAME / PATH / DISPLAY_NAME / TAGS / MODEL

```
NAME              PATH                DISPLAY_NAME       TAGS              MODEL
llm-systems       llm-systems         LLM 系统研究       research,llm      claude-sonnet-4-6
reading-notes     reading-notes       读书笔记           books             -
⚠ missing-wiki    missing-wiki        -                  -                 -
```

- `-` 表示字段未设置
- `⚠` 前缀表示 `workspace.toml` 中有记录但子目录不存在（被外部 `rm`）

### JSON 输出（`--json`）

```json
[
  {
    "name": "llm-systems",
    "path": "llm-systems",
    "display_name": "LLM 系统研究",
    "tags": ["research", "llm"],
    "model": "claude-sonnet-4-6",
    "wiki_dir_exists": true
  },
  {
    "name": "missing-wiki",
    "path": "missing-wiki",
    "display_name": null,
    "tags": [],
    "model": null,
    "wiki_dir_exists": false
  }
]
```

### 行为步骤

1. 解析 workspace 根（见上）
2. 读 `workspace.toml` 的 `[wikis]` 表
3. 对每条记录：
   - 检查 `<workspace>/<path>` 是否存在
   - 读 `<wiki>/wiki_metadata.toml`（若存在）以填 display_name / tags / model
4. 按 name 字母序排序
5. 格式化输出（表格或 JSON）
6. 退出码 0

### 边界

- workspace 中无 wiki 时：表格输出表头 + 空体；JSON 输出 `[]`
- `wiki_metadata.toml` 缺失（仅 `[wikis]` 表里有记录）：表格对应字段填 `-`；不报错
- 不递归扫描子目录去"发现未注册的 wiki"——list 只反映 `workspace.toml` 登记情况