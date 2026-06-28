#!/usr/bin/env bash
# install/uninstall 脚本测试套件。用临时 HOME 跑，绝不碰真实环境。
set -u

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
INSTALL="$REPO/scripts/install.sh"
UNINSTALL="$REPO/scripts/uninstall.sh"

PASS=0
FAIL=0
TMPHOME=""
PYDIR=""

setup() {
  TMPHOME="$(mktemp -d)"
  PYDIR="$(dirname "$(command -v python3 2>/dev/null || command -v python 2>/dev/null)")"
  [ -n "$PYDIR" ] || PYDIR="/usr/bin"
}

teardown() {
  [ -n "$TMPHOME" ] && rm -rf "$TMPHOME"
}
trap teardown EXIT

# 断言（在子 shell 里跑测试，失败 exit 1 只结束该子 shell）
assert_exists()       { [ -e "$1" ]      || { echo "    assert_exists FAIL: $1"; exit 1; }; }
assert_not_exists()   { [ ! -e "$1" ]    || { echo "    assert_not_exists FAIL: $1 存在"; exit 1; }; }
assert_executable()   { [ -x "$1" ]      || { echo "    assert_executable FAIL: $1"; exit 1; }; }
assert_contains()     { grep -qF "$2" "$1" 2>/dev/null || { echo "    assert_contains FAIL: '$2' 不在 $1"; exit 1; }; }
assert_not_contains() { ! grep -qF "$2" "$1" 2>/dev/null || { echo "    assert_not_contains FAIL: '$2' 在 $1"; exit 1; }; }
assert_count()        { local n; n="$(grep -cF "$2" "$1" 2>/dev/null || true)"; [ "$n" = "$3" ] || { echo "    assert_count FAIL: $1 有 $n 个 '$2'，期望 $3"; exit 1; }; }

# 受控环境跑 install/uninstall/wrapper，退出码存入全局
run_install() {
  HOME="$TMPHOME" SHELL="${1:-/bin/zsh}" PATH="${2:-$PYDIR:/usr/bin:/bin}" \
    bash "$INSTALL" >"$TMPHOME/inst.out" 2>&1
  INST_CODE=$?
}
run_uninstall() {
  HOME="$TMPHOME" PATH="${1:-$PYDIR:/usr/bin:/bin}" \
    bash "$UNINSTALL" >"$TMPHOME/uninst.out" 2>&1
  UNINST_CODE=$?
}
run_llmw() {
  HOME="$TMPHOME" PATH="$PYDIR:/usr/bin:/bin" "$TMPHOME/.local/bin/llmw" "$@" >"$TMPHOME/llmw.out" 2>&1
  LLMW_CODE=$?
}

# ---- 测试用例 ----
test_install_creates_wrapper() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  assert_exists "$TMPHOME/.local/bin/llmw"
  assert_executable "$TMPHOME/.local/bin/llmw"
}
test_wrapper_runs_help() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  run_llmw --help
  [ "$LLMW_CODE" = 0 ] || { echo "      llmw --help 退出码 $LLMW_CODE"; cat "$TMPHOME/llmw.out"; exit 1; }
}
test_wrapper_embeds_repo() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  assert_contains "$TMPHOME/.local/bin/llmw" "PYTHONPATH="
  assert_contains "$TMPHOME/.local/bin/llmw" "python3 -m llmw"
}

# ---- runner ----
TESTS=(
  test_install_creates_wrapper
  test_wrapper_runs_help
  test_wrapper_embeds_repo
)

run_test() {
  local name="$1"
  ( "$name" ) >"$TMPHOME/test.out" 2>&1
  local code=$?
  if [ "$code" = 0 ]; then echo "PASS  $name"; PASS=$((PASS+1));
  else echo "FAIL  $name"; sed 's/^/      /' "$TMPHOME/test.out"; FAIL=$((FAIL+1)); fi
}

main() {
  local tests=("$@")
  [ "${#tests[@]}" -gt 0 ] || tests=("${TESTS[@]}")
  local t
  for t in "${tests[@]}"; do setup; run_test "$t"; teardown; done
  echo "----"
  echo "PASS=$PASS FAIL=$FAIL"
  [ "$FAIL" = 0 ]
}
main "$@"
