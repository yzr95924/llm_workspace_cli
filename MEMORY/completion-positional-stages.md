---
name: completion-positional-stages
description: CLI 子命令有多段位置参数（action → key → value）时，bash / fish / zsh 三套 completion 都需按 token 位置分多阶段补全；漏任一段则 Tab 断档
metadata:
  type: project
---

`llmw` CLI 有多段位置参数子命令（典型：`wiki config {get,set,unset} <key> <value>`），
completion **必须按 token 位置分多阶段补全**——漏任一段则 Tab 断档。

**Why:** `--flag=` 形式的 completion 有现成模式（见 [[cli-ux-interactive-and-named-flags]]
末尾「新增带值 flag 同步」段）。但**多段位置参数**更复杂——用户依次输入
`wiki config get display_name foo` 时，需要：
- `wiki config` 后 → 候选 `get / set / unset`（cfg_action 位置）
- `wiki config get` 后 → 候选 `display_name / description / tags / model`（cfg_key 位置）
- `wiki config get display_name` 后 → **不补**（cfg_value 自由文本）

三套 shell 都要做，且实现差异显著（bash 数组下标 / fish `__fish_seen_subcommand_from`
AND-OR 组合 / zsh `_describe` + `_arguments`）。本轮（2026-07-05）发现 `list --tag=` 在
bash/fish/zsh 全漏、`wiki config` 在三套 shell 都没有 cfg_action / cfg_key 补全——cli.py
定义早已有 `p_list.add_argument("--tag", action="append", ...)` 与
`pw_cfg.add_argument("cfg_action", "cfg_key", "cfg_value", ...)`，但手写 completion
脚本漏同步。

**How to apply:**

新增多段位置参数子命令时（cli.py `add_argument("cfg_action", ...)` + `cfg_key` + `cfg_value`，
或任意 N 段 `nargs="?"` 位置参数），三套 completion 都要同步加多阶段：

- **bash**（`completions/llmw.bash`）：
  - 收集位置参数到 `wiki_pos` 数组：`local -a wiki_pos=()` + 循环 `case "$w" in --*=*|-*) ;; *) wiki_pos+=("$w") ;; esac`
  - 下标约定：`[0]=wiki [1]=config [2]=cfg_action [3]=cfg_key`
  - 分支：`[ -z "${wiki_pos[2]:-}" ]` → cfg_action 三选一；
    `[ -z "${wiki_pos[3]:-}" ]` → cfg_key 白名单；
    否则 → cfg_value 不补，只返 `$COMMON`
- **fish**（`completions/llmw.fish`）：
  - cfg_action 位置：`__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and not __fish_seen_subcommand_from get set unset`
  - cfg_key 位置：`__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and __fish_seen_subcommand_from get set unset`
  - 注意 fish 的 `__fish_seen_subcommand_from a b c` 是 OR（任一见即真）；
    "未选 action" 用 `; and not __fish_seen_subcommand_from get set unset` 表达
- **zsh**（`completions/_llmw`）：
  - 同样用 `wiki_pos` 数组收集（脚本模式与 bash 一致）
  - cfg_action 用 `local -a CFG_ACTS=('get:取值' ...)` + `_describe -t actions 'wiki config action' CFG_ACTS` + `_arguments "${COMMON_OPTS[@]}"`（**先 describe 再 arguments**）
  - cfg_key 用 `local -a WIKI_CFG_KEYS=('display_name:显示名' ...)` + `_describe -t keys 'wiki config key' WIKI_CFG_KEYS`
  - cfg_value 不补，只 `_arguments "${COMMON_OPTS[@]}"`

**验证（bash 最容易）：** source `completions/llmw.bash` 后手动设
`COMP_WORDS=("$@" "")` + `COMP_CWORD=$((${#COMP_WORDS[@]} - 1))` 调 `_llmw`，
输出 `COMPREPLY`——这是 **mock COMP_WORDS** 路径，**只验证函数逻辑**（不走真实 readline，
因此**不能验证 wordbreaks**，但能验证分支覆盖，详见 [[bash-completion-wordbreaks]]）。
wordbreaks 必须用 pty 实测真实 readline。

**fish / zsh 验证约束：** `_arguments` / `_describe` 强制要求 completion context，
python pty 难拿回显。zsh 走 `zsh -n` 语法检查 + 对照 bash 已通过的算法
（同 `wiki_pos` 下标 + 同样的 cfg_action / cfg_key 分支）；fish 走 `fish -n` +
`complete -c llmw` 内省（看 `-n` 条件和 `-a` 候选注册是否到位）。

**典型反例（漏写代价）：** `wiki config <TAB>` 不补 `get/set/unset`，
`wiki config get <TAB>` 不补 `display_name/...`——用户只能盲敲，违反 [[cli-ux-interactive-and-named-flags]]
「CLI 自文档化」初衷。

关联 [[cli-ux-interactive-and-named-flags]]（带值 flag 的 completion 同步），
[[bash-completion-wordbreaks]]（pty 验证方法与 wordbreaks 坑）。