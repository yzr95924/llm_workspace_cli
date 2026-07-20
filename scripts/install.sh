#!/usr/bin/env bash
# scripts/install.sh — 把生成的 llmw wrapper 装进 ~/.local/bin（Phase 2），
# 同时装全部三套 shell completion（bash / fish / zsh）+ 给三套 shell 的 rc 注册
# ~/.local/bin PATH，均与 uninstall.sh 全量清理对称。
set -euo pipefail

usage() {
  cat <<'USG'
usage: ./scripts/install.sh
  生成 ~/.local/bin/llmw（PYTHONPATH 指向本仓库），
  装全部三套 shell completion（bash / fish / zsh），
  并给三套 shell 的 rc 注册 ~/.local/bin PATH（marker 块幂等）。
  卸载用 ./scripts/uninstall.sh。
USG
}

# 装单套 completion（由下方循环对 bash/fish/zsh 各调一次）；不识别 shell 静默跳过
# 输出到 stderr: 提示文案（install 反馈）
_install_completion() {
  local shell_name="$1"
  local src_dir="$repo_root/completions"
  case "$shell_name" in
    bash)
      local dest_dir="${XDG_DATA_HOME:-$HOME/.local/share}/bash-completion/completions"
      mkdir -p "$dest_dir"
      cp "$src_dir/llmw.bash" "$dest_dir/llmw"
      echo "已安装 bash completion -> $dest_dir/llmw"
      # Debian 默认 ~/.bashrc 第 97-98 行 source bash-completion 的代码被注释掉了。
      # 如果用户没启用，completion 文件不会被加载——主动检测并补一个 source 块。
      _install_bash_completion_loader "$dest_dir"
      ;;
    fish)
      local dest_dir="$HOME/.config/fish/completions"
      mkdir -p "$dest_dir"
      cp "$src_dir/llmw.fish" "$dest_dir/llmw.fish"
      echo "已安装 fish completion -> $dest_dir/llmw.fish"
      ;;
    zsh)
      local dest_dir="$HOME/.local/share/zsh/site-functions"
      mkdir -p "$dest_dir"
      cp "$src_dir/_llmw" "$dest_dir/_llmw"
      echo "已安装 zsh completion -> $dest_dir/_llmw"
      # 在 ~/.zshrc prepend fpath 到 site-functions（带 marker 块幂等）
      local zshrc="$HOME/.zshrc"
      local marker='# >>> llmw completion (managed by install.sh) >>>'
      if [ ! -f "$zshrc" ] || ! grep -qxF "$marker" "$zshrc"; then
        mkdir -p "$(dirname "$zshrc")"
        cat >> "$zshrc" <<'ZSH_BLOCK'
# >>> llmw completion (managed by install.sh) >>>
fpath=("$HOME/.local/share/zsh/site-functions" $fpath)
# <<< llmw completion <<<
ZSH_BLOCK
        echo "已写入 zsh fpath 到 ${zshrc}；请运行 source ${zshrc} 或重开终端使其生效。"
      fi
      ;;
  esac
}

# 检测 ~/.bashrc 是否已经 source bash-completion；若没，追加 source 块（带 marker 幂等）。
# 策略: 双保险——
#   1. 若 bash-completion 包存在，. 它的主脚本（启用 complete -D -F _completion_loader 默认补全机制）
#   2. 显式 source 我们的 llmw.bash（绕过 bash-completion 的 lazy load，直接注册 _llmw）
# 即使 bash-completion 不可用，至少 (2) 还能让 llmw 补全生效。
_install_bash_completion_loader() {
  local bashrc="$HOME/.bashrc"
  local marker='# >>> llmw (bash-completion loader, managed by install.sh) >>>'
  # 已有 marker -> 跳过
  if [ -f "$bashrc" ] && grep -qxF "$marker" "$bashrc"; then
    return 0
  fi
  # 找系统装的 bash_completion 脚本（Debian 路径优先，再试旧路径）
  local bc_path=""
  for p in /usr/share/bash-completion/bash_completion /etc/bash_completion; do
    [ -f "$p" ] && bc_path="$p" && break
  done
  # 装 completion 的位置（XDG-aware）
  local dest_file="${XDG_DATA_HOME:-$HOME/.local/share}/bash-completion/completions/llmw"
  mkdir -p "$(dirname "$bashrc")"
  {
    echo "$marker"
    if [ -n "$bc_path" ]; then
      echo "# 加载 bash-completion 框架 (它会注册 complete -D -F _completion_loader 默认补全)"
      echo "[ -f $bc_path ] && ! shopt -oq posix && . $bc_path"
    fi
    echo "# 直接 source 我们的 completion (绕过 bash-completion lazy load, 确保 _llmw 立即可用)"
    echo "[ -f $dest_file ] && . $dest_file"
    echo "# <<< llmw bash-completion loader <<<"
  } >> "$bashrc"
  if [ -z "$bc_path" ]; then
    echo "install.sh: 未找到 bash-completion 包，已 fallback 为直接 source llmw.bash。" >&2
    echo "        如需 description 等高级补全特性, 请 apt install bash-completion 后重跑。" >&2
  fi
  echo "已写入 bash completion loader 到 ${bashrc}；请运行 source ${bashrc} 或重开终端使其生效。"
}

# --- PATH 注册（与 completion 三套对称：bash/fish/zsh 各自 rc + 各自语法）---
# marker 块幂等：rc 内已含 marker 行则跳过；以 rc 文件状态为准（不看 install 进程 PATH，
# 避免非交互 PATH 误判漏写）。uninstall.sh 按 marker 全量清理。

# bash / zsh 通用 POSIX 语法 PATH marker
_write_path_posix() {
  local rc="$1"
  local marker='# >>> llmw (managed by install.sh) >>>'
  mkdir -p "$(dirname "$rc")"
  if [ -f "$rc" ] && grep -qxF "$marker" "$rc"; then
    echo "  $rc 已有 PATH marker，跳过"
    return 0
  fi
  cat >> "$rc" <<'BLOCK'
# >>> llmw (managed by install.sh) >>>
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) PATH="$HOME/.local/bin:$PATH"; export PATH ;;
esac
# <<< llmw <<<
BLOCK
  echo "已注册 ~/.local/bin PATH -> $rc"
}

# fish 语法 PATH marker（contains 守卫 + set -gx；兼容旧 fish，不用 fish_add_path）
_write_path_fish() {
  local rc="$1"
  local marker='# >>> llmw (managed by install.sh) >>>'
  mkdir -p "$(dirname "$rc")"
  if [ -f "$rc" ] && grep -qxF "$marker" "$rc"; then
    echo "  $rc 已有 PATH marker，跳过"
    return 0
  fi
  cat >> "$rc" <<'BLOCK'
# >>> llmw (managed by install.sh) >>>
if not contains -- $HOME/.local/bin $PATH
    set -gx PATH $HOME/.local/bin $PATH
end
# <<< llmw <<<
BLOCK
  echo "已注册 ~/.local/bin PATH -> $rc"
}

# 脚本在 scripts/，仓库根是其上一级；不依赖 readlink -f（兼容 macOS bash 3.2）
repo_root="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "install.sh: 未找到 python3（需要 Python 3.7+）。请先安装 python3 再重试。" >&2
  exit 1
fi

# Python < 3.11 运行时需要 tomli；只提示，不自动安装
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
  echo "install.sh: 注意 Python < 3.11，运行时可能需要 tomli（pip install 'tomli>=1.1'）。继续安装。" >&2
fi

bin_dir="$HOME/.local/bin"

mkdir -p "$bin_dir"

cat > "$bin_dir/llmw" <<EOF
#!/usr/bin/env bash
# llmw launcher — generated by install.sh. Repo: $repo_root
# 仓库被挪走会失效；重跑 ./scripts/install.sh 即可修复。
# python3 -B：禁用 .pyc 字节码缓存——源码 bump 后陈旧 pyc 会让版本常量滞后
# （实测：WIKI_SPEC_VERSION 源码 0.27.1 但旧 pyc 仍读 0.27.0，fresh wiki 版本行写错）。
REPO="$repo_root"
if [ ! -d "\$REPO" ]; then
  echo "llmw: 仓库目录不存在: \${REPO}（可能被移动或删除，请重跑 ./scripts/install.sh）" >&2
  exit 1
fi
export PYTHONPATH="\$REPO:\$PYTHONPATH"
exec python3 -B -m llmw "\$@"
EOF
chmod +x "$bin_dir/llmw"

# --- 装全部三套 completion（bash/fish/zsh），与 uninstall.sh 全量清理对称 ---
# 各 shell 的 rc 改动（bash loader / zsh fpath）均带 marker 块幂等；用户不用某 shell 时
# 其 rc 块不会被加载，无害。fish 零侵入（自动加载 completions 目录，无需改 rc）。
for _sh in bash fish zsh; do
  _install_completion "$_sh"
done

# --- 给所有候选 shell 注册 ~/.local/bin PATH（与 completion 三套对称）---
# 各 shell 用各自语法：bash/zsh 用 POSIX case/export（macOS bash 走 .bash_profile），
# fish 用 contains 守卫的 set -gx。marker 块幂等（rc 内已有则跳过）。
for _sh in bash fish zsh; do
  case "$_sh" in
    bash)
      if [ "$(uname)" = "Darwin" ]; then _write_path_posix "$HOME/.bash_profile"
      else _write_path_posix "$HOME/.bashrc"; fi
      ;;
    fish) _write_path_fish "$HOME/.config/fish/config.fish" ;;
    zsh)   _write_path_posix "$HOME/.zshrc" ;;
  esac
done

echo "已安装 llmw -> $bin_dir/llmw"
echo "PATH marker 若为新写入，请 source 对应 rc 或重开终端使其生效。"
