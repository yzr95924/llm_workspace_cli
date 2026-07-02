#!/usr/bin/env bash
# 逆操作：移除 core.hooksPath，恢复 git 默认 .git/hooks。
set -euo pipefail

repo_root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$repo_root"

if git config --get core.hooksPath >/dev/null 2>&1; then
  git config --unset core.hooksPath
  echo "[uninstall-hooks] 已移除 core.hooksPath，恢复默认 .git/hooks"
else
  echo "[uninstall-hooks] core.hooksPath 未设置，无需处理"
fi
