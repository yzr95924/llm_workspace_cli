#!/usr/bin/env bash
# 启用仓库内 git hooks：把 core.hooksPath 指向 scripts/git-hooks（纳入版本控制、
# 协作方可复现）。逆操作见 scripts/uninstall-hooks.sh。
set -euo pipefail

repo_root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$repo_root"

hooks_dir="scripts/git-hooks"
chmod +x "$hooks_dir"/pre-push 2>/dev/null || true

git config core.hooksPath "$hooks_dir"
echo "[install-hooks] core.hooksPath = $hooks_dir"
echo "[install-hooks] 已启用 hooks：$(find "$hooks_dir" -maxdepth 1 -type f ! -name '*.md' -printf '%f ' 2>/dev/null)"
