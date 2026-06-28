# 03 · `enter` 命令（核心）

> **Phase 2 已上线（现行契约以此为准）**：`enter` 现在 (1) 通过 `resolve_for_wiki()` 解析最终 model；(2) 显式注入 `ANTHROPIC_MODEL`/`ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN` env；(3) 给 claude 传 `--setting-sources project,local`（不加载 user 源，否则 `~/.claude/settings.json` 的 `env` 块会盖掉 overlay）；(4) `ANTHROPIC_MODEL` 用 `model.name`（网关模型名）而非 `model_id`。**本文其余"Phase 1 简化版"描述（env 完全透传、不传 model）为历史设计**，Phase 2 现行实现以 [`09-workspace-model-registry.md`](09-workspace-model-registry.md) §9.5 为准。

## 3.0 `llmw wiki --name=<name> enter`

**作用**：在指定 wiki 上下文里启动一个 Claude Code session。

这是 CLI 的**核心命令**——前面的 `add` / `remove` / `show` / `config` 都是为了这个命令铺路：
让用户能在一个"已经被注册、被描述、被配置"过的 wiki 目录里，直接和 Claude Code 对话，
且 Claude Code 自动获得该 wiki 的 schema（CLAUDE.md）。

### 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--name NAME`（必填） | — | 要进入的 wiki 名 |
| `--dry-run` | `false` | 只打印将执行的命令，不真正调用 claude |

> **`enter` 不接受 `--model` flag**——模型选择完全由 wiki / workspace 配置决定。
> 如需临时切换，先用 `llmw wiki --name=<name> config set model <id>` 写入 wiki 元数据，
> 退出后再 `unset`。

### model 处理（Phase 1 简化版）

Phase 1 阶段 model 字段是**元数据 / 审计字段**，**不主动传递给 Claude Code**：

- `workspace.default_model` 与 `wiki.model` 字段保留（供 `show` / `config` 等命令展示）
- `enter` 不读取、不解析、不传递 model 给 Claude Code 子进程
- Claude Code 使用**自己的默认 model**（用户在 Claude Code 侧配置，或 `ANTHROPIC_MODEL` 环境变量自行设置——CLI 不介入）
- 报错 `NoModelConfigured` **移除**——既然 model 不传递给 Claude Code，配置缺失不再阻断 `enter`

**Phase 2 升级路径**：

- 引入 `workspace_models.toml`（model 注册表，由 `llmw model` 命令族管理）
- 引入明确的"将 model 通知给 Claude Code"机制（候选方案：写入 `<wiki>/.claude/settings.json`、或在 `enter` 时通过其他配置通道）
- 设计细节见 [`09-workspace-model-registry.md`](09-workspace-model-registry.md)（Phase 2 已落地：通过 `enter` 的 env overlay + `--setting-sources` 实现，不走 `.claude/settings.json`）

### 行为步骤

1. **解析 workspace 根**（同 01 章）；不存在 → `WorkspaceNotFound`
2. **校验 `--name` 在 `[wikis]` 中存在**；不存在 → `WikiNotFound`
3. **定位 wiki 绝对路径**：`wiki_abs = <workspace>/<path>`
4. **校验 wiki 目录存在**；缺失 → `WikiDirMissing`
5. **（软警告，不阻断）**校验 `<wiki>/CLAUDE.md` 存在：
   - 缺失：stderr 输出 ⚠ "wiki <name> 缺少 CLAUDE.md，session 启动后将没有 schema 上下文"
6. **（软警告，不阻断）**校验 `<wiki>/wiki_metadata.toml` 存在：
   - 缺失：stderr 输出 ⚠ "wiki <name> 缺少 wiki_metadata.toml"
7. **构造 claude 命令**：
   ```
   claude \
     --add-dir <wiki_abs> \
     --system-prompt "$(cat <wiki_abs>/CLAUDE.md)"
   ```
   - 若 CLAUDE.md 缺失，`--system-prompt` 不传（避免命令错）
   - `--add-dir` 必须传——让 Claude Code 把 wiki 视为合法工作目录
   - **不传 model 相关 flag 或 env**（Phase 1 简化版）
8. **切换 cwd**：`os.chdir(wiki_abs)`
9. **执行**：
   - `--dry-run`：仅打印命令与解析后的参数，退出码 0
   - 否则：`subprocess.run(["claude", ...])`，透传 stdout/stderr，退出码取自 claude 子进程
   - 子进程 env 完全继承 `os.environ`（CLI 不修改任何 env）

### 边界

- **`claude` 不在 PATH**：`--dry-run` 仍可用；否则报错 `ClaudeNotFound`，提示安装 Claude Code
- **CLAUDE.md 为空文件**：`--system-prompt ""` 仍传给 claude（不视为缺失）；CLI 不警告
- **CLAUDE.md 不存在**：`--system-prompt` 不传；stderr 给 ⚠ 警告但继续启动
- **多层软警告**：`CLAUDE.md` 缺失、`wiki_metadata.toml` 缺失、子目录空，都**不阻断**——让用户能进 wiki 修
- **model 配置缺失不阻断**：Phase 1 不主动传 model；Claude Code 用默认
- **subprocess 透传**：claude 子进程的退出码即为 CLI 退出码；不重新包装错误
- **env 完全透传**：CLI 不修改任何 env——`ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_MODEL` 等用户自行在 shell 配置的 env 全部继承
- **不会自动 git commit**：用户在 claude session 里做的修改由用户决定 commit 时机

### 为什么这样构造

- **`os.chdir` + `--add-dir` 双重保险**：
  - `os.chdir` 让 session 的"当前目录"等于 wiki 根——用户后续在 shell 里 `cd` 不会跑出 wiki
  - `--add-dir` 让 Claude Code 把 wiki 当作合法工作目录——即使 cwd 被外部修改也不影响
- **`--system-prompt` 注入 CLAUDE.md**：
  - 默认情况下 Claude Code 在 cwd 下会自动加载 `CLAUDE.md`，但**只对启动时的 cwd 生效**
  - 用 `--system-prompt` 兜底，从其他目录启动也能拿到 schema
  - CLI **不解析 CLAUDE.md 内容**——直接 `cat` 原样交给 claude，保证"所见即所得"
- **不传 model**（Phase 1 简化版）：
  - model 字段作为元数据保留（`show` / `config` 可查）
  - CLI 不向 claude 子进程注入任何 model 信息
  - Claude Code 用自己的默认 model（或用户在 Claude Code 侧 / shell env 配置）
  - Phase 2 已落地（见上文 banner + 09 §9.5）：`enter` 通过 env overlay 注入 `ANTHROPIC_*` + `--setting-sources project,local` 将 model 通知 Claude Code
- **subprocess 不传 `env`**：让 Claude Code 子进程继承完整的 shell env（包括用户自行配置的 `ANTHROPIC_MODEL` 等），CLI 不做干预
- **不直接 `os.execvp`**：用 `subprocess.run` 保留 Python 进程层，方便将来加 pre/post 钩子

### dry-run 输出示例

```
$ llmw wiki --name=llm-systems enter --dry-run
[llmw] workspace: /home/user/yzr_llm_wiki_workspace
[llmw] wiki:      llm-systems (/home/user/yzr_llm_wiki_workspace/llm-systems)
[llmw] wiki.model: MiniMax-M3 (note: Phase 1 不传递给 Claude Code)
[llmw] CLAUDE.md: ✓ found (3042 bytes)
[llmw] cmd:
  claude \
    --add-dir /home/user/yzr_llm_wiki_workspace/llm-systems \
    --system-prompt "$(cat /home/user/yzr_llm_wiki_workspace/llm-systems/CLAUDE.md)"
[llmw] env: 继承当前 shell（CLI 不修改）
[llmw] --dry-run: 未执行
```

> dry-run 标注 `wiki.model` 字段供参考，但明确说明 Phase 1 不传递给 Claude Code。
> Phase 2 引入 model registry 后此行会变成实际生效信息。

### 后续钩子位（预留，不在 Phase 1）

为不阻塞 Phase 1，`enter` 设计**预留**以下钩子位（未来可加，Phase 1 不实现）：

- `pre-enter`：进入前自动跑 `git pull` / `git status` 检查
- `post-enter`：session 退出后自动跑 `git add` 暂存
- `--claude-md-check` 选项：`warn`（默认）/ `fail` / `skip`，控制 CLAUDE.md 缺失时的行为
- **Phase 2（已落地）**：通过 `workspace_models.toml` + `llmw model` 管理 model，`enter` 通过 env overlay（`ANTHROPIC_*`）+ `--setting-sources project,local` 将 model 通知 Claude Code（见 09 §9.5）

这些位 Phase 2 / Phase 3 再启。