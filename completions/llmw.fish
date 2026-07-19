# fish completion for llmw
# Install: 由 scripts/install.sh 自动 cp 到
#   ~/.config/fish/completions/llmw.fish
# fish 自动加载，无需 source。

# 参数风格：带值 flag 一律 `--flag=<value>`（= 连接；CLI 拒绝空格分隔的 --flag value）。
# 带值 flag 补全分两类（核心：fish 对带值 long option 生成 `--flag=` 候选的条件是「有 -a 值候选
# 且无 -r」——-r 会让 fish 走空格分隔语义，既不给 = 形式、又与 CLI 的 = 要求冲突）：
#   A 类（有动态值，如 --name/--model-id/--model）：`-l flag -a "(vals)"`（无 -r），
#       fish 原生同时给 --flag 与 --flag=；= 后 <Tab> 补动态值。
#   B 类（free-form 无动态值，如 --topic/--base-url）：`-a "--flag="`（直接给 = 候选），值手敲。

# 通用: workspace 路径（--workspace= 值 或 $LLMW_WORKSPACE 或默认）
function __llmw_workspace
    set -l ws ""
    for w in (commandline -opc)
        switch "$w"
            case '--workspace=*'
                set ws (string replace -- '--workspace=' '' -- "$w")
        end
    end
    if test -z "$ws"
        if set -q LLMW_WORKSPACE
            set ws "$LLMW_WORKSPACE"
        else
            set ws "$HOME/yzr_llm_wiki_workspace"
        end
    end
    echo "$ws"
end

# 动态: 当前 workspace 的 wiki 名（直读 workspace.toml，不依赖 llmw 可执行文件；未初始化返回空）
function __llmw_wikis
    set -l ws (__llmw_workspace)
    [ -f "$ws/workspace.toml" ]; or return 0
    grep -oE '^\[wikis\.[a-z0-9_-]+\]' "$ws/workspace.toml" 2>/dev/null \
        | sed 's/^\[wikis\.//; s/\]$//'
end

# 动态: 当前 workspace 的 model_id（直读 workspace_models.toml，不依赖 llmw 可执行文件；未初始化返回空）
function __llmw_model_ids
    set -l ws (__llmw_workspace)
    [ -f "$ws/workspace_models.toml" ]; or return 0
    grep -oE '^model_id[[:space:]]*=[[:space:]]*"[^"]+"' "$ws/workspace_models.toml" 2>/dev/null \
        | sed -E 's/.*"([^"]+)".*/\1/'
end

# 已见某个 subcommand？
function __llmw_seen
    argparse 'h/help' 'workspace=' 'json' 'debug' 'quiet/q' -- (commandline -opc) 2>/dev/null
    set -l cmds (string match -rv '^-' -- (commandline -opc))
    set -l found 0
    for c in $cmds
        if contains -- "$c" $argv
            set found 1
            break
        end
    end
    return (math "1 - $found")
end

# 精确：commandline 含 $argv[1]（sub）且含 $argv[2..]（action 任一）
# 避免 __fish_seen_subcommand_from SUB ACT 的 OR 语义泄露（wiki add 与 model add 都含 "add"）
function __llmw_subact
    __fish_seen_subcommand_from $argv[1]; and __fish_seen_subcommand_from $argv[2..-1]
end

# 通用 / 顶级
set -l COMMON -l workspace -l json -l debug -l quiet -s q
set -l TOP_CMDS init config list model wiki -l help -l version

# ===== 顶层 =====
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "init"     -d '初始化 workspace'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "config"   -d 'workspace.toml 读写'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "list"     -d '列出 wiki'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "model"    -d 'workspace model registry'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "wiki"     -d 'wiki 子命令'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -l help         -d '显示帮助'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -l version      -d '显示版本'

# 全局 flag（任何位置）
# --workspace 用 A 类（-l workspace + 动态 -a）+ __fish_complete_directories：
#   fish 自动生成 --workspace= 候选 + Tab 触发目录补全，与 bash compgen -d / zsh _directories 对齐
complete -c llmw -l workspace -f -a "(__fish_complete_directories)" -d 'workspace 根路径'
complete -c llmw -l json      -d '输出 JSON 格式'
complete -c llmw -l debug     -d '打印 traceback'
complete -c llmw -l quiet -s q -d '抑制 INFO'

# init 子命令 flag（path / display-name，均 free-form → B 类）
complete -c llmw -n "__fish_seen_subcommand_from init" -a "--path="         -f -d 'workspace 路径'
complete -c llmw -n "__fish_seen_subcommand_from init" -a "--display-name=" -f -d 'workspace 显示名'

# list 子命令 flag（--tag free-form → B 类）
complete -c llmw -n "__fish_seen_subcommand_from list" -a "--tag=" -f -d '仅列出含此 tag (可重复, AND 关系)'

# ===== config 子命令 =====
complete -c llmw -n "__fish_seen_subcommand_from config; and not __fish_seen_subcommand_from get set unset" -f -a "get"    -d '取值'
complete -c llmw -n "__fish_seen_subcommand_from config; and not __fish_seen_subcommand_from get set unset" -f -a "set"    -d '设值'
complete -c llmw -n "__fish_seen_subcommand_from config; and not __fish_seen_subcommand_from get set unset" -f -a "unset"  -d '清值'

complete -c llmw -n "__fish_seen_subcommand_from config get unset" -f -a "default_model"        -d '默认 model_id'
complete -c llmw -n "__fish_seen_subcommand_from config get unset" -f -a "enter_cli"           -d 'agent CLI (claude|qodercli|opencode)'
complete -c llmw -n "__fish_seen_subcommand_from config get unset" -f -a "enter_byobu"         -d 'byobu 窗口模式 (true|false)'
complete -c llmw -n "__fish_seen_subcommand_from config get unset" -f -a "templates_version"    -d 'templates 版本(只读)'
complete -c llmw -n "__fish_seen_subcommand_from config get unset" -f -a "created_at"           -d '创建时间(只读)'
complete -c llmw -n "__fish_seen_subcommand_from config get unset" -f -a "schema_version"       -d 'schema 版本(只读)'
complete -c llmw -n "__fish_seen_subcommand_from config set"       -f -a "default_model"        -d '默认 model_id'
complete -c llmw -n "__fish_seen_subcommand_from config set"       -f -a "enter_cli"           -d 'agent CLI (claude|qodercli|opencode)'
complete -c llmw -n "__fish_seen_subcommand_from config set"       -f -a "enter_byobu"         -d 'byobu 窗口模式 (true|false)'

# ===== model 子命令 =====
set -l MODEL_ACTS add list show set-default unset-default remove
complete -c llmw -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from $MODEL_ACTS" -f -a "add"             -d '新增 model 条目'
complete -c llmw -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from $MODEL_ACTS" -f -a "list"            -d '列出所有 model 条目'
complete -c llmw -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from $MODEL_ACTS" -f -a "show"            -d '查看单条 model'
complete -c llmw -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from $MODEL_ACTS" -f -a "set-default"     -d '标记默认 model'
complete -c llmw -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from $MODEL_ACTS" -f -a "unset-default"   -d '清空默认标记'
complete -c llmw -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from $MODEL_ACTS" -f -a "remove"          -d '删除 model 条目'

# model list / unset-default（无专属 flag；显式 scope 声明，与 bash line 148-150 / zsh line 185-187 对齐；
# 全局 --workspace=/--json/--debug/--quiet/-q 由 line 82-85 兜底）
complete -c llmw -n "__llmw_subact model list"            -f -d '列出所有 model 条目'
complete -c llmw -n "__llmw_subact model unset-default"   -f -d '清空默认标记'

# model add（全 free-form → B 类；--default 是 bool flag）
complete -c llmw -n "__llmw_subact model add" -a "--model-id=" -f -d 'registry slug'
complete -c llmw -n "__llmw_subact model add" -a "--name="     -f -d '网关模型名'
complete -c llmw -n "__llmw_subact model add" -a "--base-url=" -f -d 'API base URL'
complete -c llmw -n "__llmw_subact model add" -a "--api-key="  -f -d 'API key'
complete -c llmw -n "__llmw_subact model add" -l default  -d '标记为默认'

# model show / set-default / remove（--model-id 有动态值 → A 类，无 -r）
complete -c llmw -n "__llmw_subact model show set-default remove" -l model-id -f -a "(__llmw_model_ids)" -d 'model_id'
complete -c llmw -n "__llmw_subact model remove" -l yes -s y -d '跳过确认'

# ===== wiki 子命令 =====
set -l WIKI_ACTS add remove rename show config enter
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "add"      -d '新建 wiki'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "remove"   -d '移除 wiki'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "rename"   -d '重命名 wiki (目录 + 索引 + metadata)'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "show"     -d '查看 wiki 详情'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "config"   -d '读写 wiki_metadata.toml'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "enter"    -d '启动 AI agent session'

# wiki --name（wiki 但未选 action 时；有动态值 → A 类，无 -r）
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -l name -f -a "(__llmw_wikis)" -d '目标 wiki 名'

# wiki add（topic/display-name/description/tag free-form → B 类；--model 有动态值 → A 类；--git 是 bool）
complete -c llmw -n "__llmw_subact wiki add" -a "--topic="        -f -d 'wiki 主题'
complete -c llmw -n "__llmw_subact wiki add" -a "--display-name=" -f -d '显示名'
complete -c llmw -n "__llmw_subact wiki add" -a "--description="  -f -d '描述'
complete -c llmw -n "__llmw_subact wiki add" -a "--tag="          -f -d 'tag (可重复)'
complete -c llmw -n "__llmw_subact wiki add" -l model -f -a "(__llmw_model_ids)" -d '绑定的 model_id'
complete -c llmw -n "__llmw_subact wiki add" -l git -d 'opt-in: 初始化 git 仓'

# wiki remove
complete -c llmw -n "__llmw_subact wiki remove" -l purge       -d '同时删除 wiki 子目录'
complete -c llmw -n "__llmw_subact wiki remove" -l no-backup   -d '跳过 --purge 的备份步骤'
complete -c llmw -n "__llmw_subact wiki remove" -l yes -s y    -d '跳过确认'

# wiki rename（--old 有动态值 → A 类，无 -r；--new free-form → B 类，无 -r）
complete -c llmw -n "__llmw_subact wiki rename" -l old -f -a "(__llmw_wikis)" -d '当前 wiki 名'
complete -c llmw -n "__llmw_subact wiki rename" -a "--new=" -f -d '新 wiki 名 (须符合 NAME_RE)'

# wiki show（--name 有动态值 → A 类，无 -r）
complete -c llmw -n "__llmw_subact wiki show" -l name -f -a "(__llmw_wikis)" -d '目标 wiki 名'

# wiki config（--name 有动态值 → A 类，无 -r）
complete -c llmw -n "__llmw_subact wiki config" -l name -f -a "(__llmw_wikis)" -d '目标 wiki 名'

# wiki config cfg_action（get/set/unset 三选一）
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and not __fish_seen_subcommand_from get set unset" -f -a "get"   -d '取值'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and not __fish_seen_subcommand_from get set unset" -f -a "set"   -d '设值'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and not __fish_seen_subcommand_from get set unset" -f -a "unset" -d '清值'

# wiki config cfg_key（display_name / description / tags / model；cfg_action 之后）
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and __fish_seen_subcommand_from get set unset" -f -a "display_name" -d '显示名'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and __fish_seen_subcommand_from get set unset" -f -a "description"  -d '描述'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and __fish_seen_subcommand_from get set unset" -f -a "tags"         -d 'tags (可重复)'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and __fish_seen_subcommand_from get set unset" -f -a "model"        -d '绑定的 model_id'

# wiki enter（--name 有动态值 → A 类，无 -r；--dry-run 是 bool）
complete -c llmw -n "__llmw_subact wiki enter" -l name -f -a "(__llmw_wikis)" -d '目标 wiki 名'
complete -c llmw -n "__llmw_subact wiki enter" -l dry-run -d '仅打印 overlay 不启动 claude'
