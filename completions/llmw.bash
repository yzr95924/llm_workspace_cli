# bash completion for llmw
# Install: 由 scripts/install.sh 自动 cp 到
#   ~/.local/share/bash-completion/completions/llmw
# 由 bash-completion ≥2.0 自动加载，无需 source。
#
# 参数风格：带值 flag 一律 `--flag=<value>`（= 连接；CLI 拒绝空格分隔的 --flag value）。
# 带值 flag 敲到 flag 名后 <Tab> 补 `=`，再 <Tab> 触发动态值补全（--name=*/--model-id=* 等）。

_llmw() {
    local cur prev i n wi ws sub sub_action
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # COMP_WORDBREAKS 默认含 `=`：readline 把 `--flag=` 在 = 处拆成 `--flag` + `=`（光标在
    # = 后，COMP_WORDS[COMP_CWORD] 是 "="）。规范化 cur 回 `--flag=` 形式以复用下方 --flag=*
    # 分支（返回裸 value，readline 自动附加到 = 后）。仅对带值 flag 触发，避免误伤 bool flag。
    case "$prev" in
        --name|--model|--model-id|--workspace|--path|--topic|--display-name|--description|--tag|--base-url|--api-key)
            case "$cur" in
                "=") cur="${prev}=" ;;
                =*)  cur="${prev}${cur}" ;;
            esac
            ;;
    esac

    # 1. 抽取 --workspace 的值（用于动态补全）
    ws=""
    for wi in "${COMP_WORDS[@]}"; do
        case "$wi" in
            --workspace=*) ws="${wi#--workspace=}" ;;
        esac
    done
    [ -z "$ws" ] && ws="${LLMW_WORKSPACE:-$HOME/yzr_llm_wiki_workspace}"

    # 2. 抽前序 sub / sub_action（跳过 flag 及其值）
    sub=""
    sub_action=""
    i=1
    while [ "$i" -lt "$COMP_CWORD" ]; do
        wi="${COMP_WORDS[$i]}"
        case "$wi" in
            -*) ;;  # flag (--flag 或 --flag=value) 本身不算 sub
            *)
                if [ -z "$sub" ]; then sub="$wi"
                elif [ -z "$sub_action" ]; then sub_action="$wi"
                fi
                ;;
        esac
        i=$((i + 1))
    done

    # 3. 动态候选：直读 workspace toml（真相源；不依赖 llmw 可执行文件在 PATH——
    #    避免 spawn llmw 失败被 2>/dev/null 静默吞成空候选的坑）
    _llmw_wikis() {
        [ -f "$ws/workspace.toml" ] || return 0
        grep -oE '^\[wikis\.[a-z0-9_-]+\]' "$ws/workspace.toml" 2>/dev/null \
            | sed 's/^\[wikis\.//; s/\]$//'
    }
    _llmw_model_ids() {
        [ -f "$ws/workspace_models.toml" ] || return 0
        grep -oE '^model_id[[:space:]]*=[[:space:]]*"[^"]+"' "$ws/workspace_models.toml" 2>/dev/null \
            | sed -E 's/.*"([^"]+)".*/\1/'
    }

    # 带值 flag 的 --x= 候选：补全后不加空格（= 后还要补值 / 路径）
    _llmw_nospace_if_eq() {
        local r
        for r in "${COMPREPLY[@]}"; do
            case "$r" in *=) compopt -o nospace 2>/dev/null; return 0 ;; esac
        done
    }

    local COMMON="--workspace= --json --debug --quiet -q"
    local TOP="init config list model wiki"
    local WIKI_ACTS="add remove show config enter"
    local MODEL_ACTS="add list show set-default unset-default remove"
    local CFG_KEYS="default_model templates_version created_at schema_version"

    COMPREPLY=()

    # 4. cur 是 `--flag=value` 形式：bash readline 对含 `=` 的 cur 会自动把候选作为 value
    #    附加到 `=` 后（pty 实测：候选须是裸 value；带 `--flag=` 前缀会补成 `--name=--name=x`）。
    #    与 fish/zsh 一致——三套候选都返回裸 value，由各 shell 的 `=` 机制附加。
    case "$cur" in
        --name=*)
            COMPREPLY=($(compgen -W "$(_llmw_wikis)" -- "${cur#--name=}"))
            return 0
            ;;
        --model=*)
            COMPREPLY=($(compgen -W "$(_llmw_model_ids)" -- "${cur#--model=}"))
            return 0
            ;;
        --model-id=*)
            COMPREPLY=($(compgen -W "$(_llmw_model_ids)" -- "${cur#--model-id=}"))
            return 0
            ;;
        --workspace=*|--path=*)
            COMPREPLY=($(compgen -d -- "${cur#*=}"))
            return 0
            ;;
        --topic=*|--display-name=*|--description=*|--tag=*|--base-url=*|--api-key=*)
            # 带值 flag 但值是 free-form；无候选
            COMPREPLY=()
            return 0
            ;;
    esac

    # 5. 顶层
    if [ -z "$sub" ]; then
        COMPREPLY=($(compgen -W "$TOP $COMMON" -- "$cur"))
        _llmw_nospace_if_eq
        return 0
    fi

    # 6. 根据 sub / sub_action 分派
    case "$sub" in
        init)
            COMPREPLY=($(compgen -W "--path= --display-name= $COMMON" -- "$cur"))
            ;;
        list)
            COMPREPLY=($(compgen -W "--tag= $COMMON" -- "$cur"))
            ;;
        config)
            if [ -z "$sub_action" ]; then
                COMPREPLY=($(compgen -W "get set unset $COMMON" -- "$cur"))
            else
                case "$sub_action" in
                    get|unset)
                        COMPREPLY=($(compgen -W "$CFG_KEYS" -- "$cur"))
                        ;;
                    set)
                        # set <key> <value>: cword=2 -> key, cword=3 -> value (不补)
                        if [ "$COMP_CWORD" -eq 2 ]; then
                            COMPREPLY=($(compgen -W "default_model" -- "$cur"))
                        fi
                        ;;
                esac
            fi
            ;;
        model)
            if [ -z "$sub_action" ]; then
                COMPREPLY=($(compgen -W "$MODEL_ACTS $COMMON" -- "$cur"))
            else
                case "$sub_action" in
                    add)
                        COMPREPLY=($(compgen -W "--model-id= --name= --base-url= --api-key= --default $COMMON" -- "$cur"))
                        ;;
                    list|unset-default)
                        COMPREPLY=($(compgen -W "$COMMON" -- "$cur"))
                        ;;
                    show|set-default|remove)
                        # 看 --model-id= 已传否（= 形式；空格形式被 CLI 拒，不认）
                        local mid_seen=0
                        i=1
                        while [ "$i" -lt "$COMP_CWORD" ]; do
                            case "${COMP_WORDS[$i]}" in
                                --model-id=*) mid_seen=1 ;;
                            esac
                            i=$((i + 1))
                        done
                        if [ "$mid_seen" -eq 1 ]; then
                            COMPREPLY=($(compgen -W "$COMMON" -- "$cur"))
                        else
                            COMPREPLY=($(compgen -W "--model-id= -y --yes $COMMON" -- "$cur"))
                        fi
                        ;;
                esac
            fi
            ;;
        wiki)
            if [ -z "$sub_action" ]; then
                COMPREPLY=($(compgen -W "--name= $WIKI_ACTS $COMMON" -- "$cur"))
            else
                case "$sub_action" in
                    add)
                        COMPREPLY=($(compgen -W "--topic= --display-name= --description= --tag= --model= --git $COMMON" -- "$cur"))
                        ;;
                    remove)
                        COMPREPLY=($(compgen -W "--purge --no-backup -y --yes $COMMON" -- "$cur"))
                        ;;
                    show)
                        # 检测 --name= 已传否（= 形式；空格形式被 CLI 拒，不认）
                        local name_seen=0
                        i=1
                        while [ "$i" -lt "$COMP_CWORD" ]; do
                            case "${COMP_WORDS[$i]}" in
                                --name=*) name_seen=1 ;;
                            esac
                            i=$((i + 1))
                        done
                        if [ "$name_seen" -eq 1 ]; then
                            COMPREPLY=($(compgen -W "$COMMON" -- "$cur"))
                        else
                            COMPREPLY=($(compgen -W "--name= $COMMON" -- "$cur"))
                        fi
                        ;;
                    config)
                        # wiki config 三段式：cfg_action (get/set/unset) + cfg_key + cfg_value
                        # 收集位置参数到 wiki_pos：[0]=wiki [1]=config [2]=cfg_action [3]=cfg_key
                        local WIKI_CFG_KEYS="display_name description tags model"
                        local name_seen=0
                        local -a wiki_pos=()
                        i=1
                        while [ "$i" -lt "$COMP_CWORD" ]; do
                            w="${COMP_WORDS[$i]}"
                            case "$w" in
                                --name=*) name_seen=1 ;;
                            esac
                            case "$w" in
                                --*=*|-*) ;;
                                *) wiki_pos+=("$w") ;;
                            esac
                            i=$((i + 1))
                        done
                        if [ "$name_seen" -eq 0 ]; then
                            COMPREPLY=($(compgen -W "--name= $COMMON" -- "$cur"))
                        elif [ -z "${wiki_pos[2]:-}" ]; then
                            COMPREPLY=($(compgen -W "get set unset $COMMON" -- "$cur"))
                        elif [ -z "${wiki_pos[3]:-}" ]; then
                            COMPREPLY=($(compgen -W "$WIKI_CFG_KEYS $COMMON" -- "$cur"))
                        else
                            # cfg_value 自由文本，不补
                            COMPREPLY=($(compgen -W "$COMMON" -- "$cur"))
                        fi
                        ;;
                    enter)
                        # 检测 --name= 已传否（= 形式；空格形式被 CLI 拒，不认）
                        local name_seen=0
                        i=1
                        while [ "$i" -lt "$COMP_CWORD" ]; do
                            case "${COMP_WORDS[$i]}" in
                                --name=*) name_seen=1 ;;
                            esac
                            i=$((i + 1))
                        done
                        if [ "$name_seen" -eq 1 ]; then
                            COMPREPLY=($(compgen -W "--dry-run $COMMON" -- "$cur"))
                        else
                            COMPREPLY=($(compgen -W "--name= --dry-run $COMMON" -- "$cur"))
                        fi
                        ;;
                esac
            fi
            ;;
    esac

    # 带值 flag 的 = 候选：补全后不加空格（= 后还要补值 / 路径）
    _llmw_nospace_if_eq
    return 0
}

complete -F _llmw llmw