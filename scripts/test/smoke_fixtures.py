#!/usr/bin/env python3
"""CI smoke gate：fresh llmw init + wiki → 两探测器 → 断言结构合规。

兑现 [[check-fixtures-as-executable-truth]]：CLI 改坏骨架 / my_SKILL 改坏 fixtures
都让本 gate 红。双向覆盖。

断言策略：两探测器所有 error 级 check passed=True（允许 skipped/null）。
版本常量已对齐（CLI ``*_SPEC_VERSION`` = my_SKILL frontmatter），故**不忽略任何
check**——版本漂移（CLI 忘 bump / my_SKILL 先 bump）也会被 gate 抓住，强制跨仓协调。

standalone，Python 3.7+（与项目最低支持版本对齐）。用法：``python3 scripts/test/smoke_fixtures.py``
"""

# pylint: disable=missing-docstring

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "my_SKILL"
WS_CHECK = (
    SKILL / "yzr-llm-workspace-management" / "scripts" / "check_workspace_fixtures.py"
)
WIKI_CHECK = SKILL / "yzr-llm-wiki-management" / "scripts" / "check_wiki_fixtures.py"


def _llmw(args):
    """跑 ``python -m llmw <args>``，失败即抛（gate 红）。"""
    env = dict(os.environ, PYTHONPATH=str(REPO))
    proc = subprocess.run(
        [sys.executable, "-m", "llmw", *args],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(
            "FAIL: llmw {} exit={}".format(" ".join(args), proc.returncode)
        )
    return proc


def _detector_json(script, root):
    """跑探测器 --json，返回解析后的 dict。探测器 exit≠0（有 error check）仍返回 JSON。"""
    env = dict(os.environ, PYTHONPATH=str(REPO))
    proc = subprocess.run(
        [sys.executable, str(script), str(root), "--json"],
        env=env,
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(proc.stdout)
    except ValueError:
        sys.stderr.write("探测器 JSON 解析失败 (exit={}):\n".format(proc.returncode))
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(1)


def _assert_all_error_pass(script, root, label):
    """断言探测器所有 error 级 check passed=True（允许 skipped/null）。

    fail → 列出 fail 的 check id（诊断）+ exit 1；返回解析后的 JSON dict。
    """
    data = _detector_json(script, root)
    failed = [
        "{} ({})".format(c["id"], c.get("file", "?"))
        for c in data["checks"]
        if c.get("severity") == "error" and c.get("passed") is False
    ]
    if failed:
        sys.stderr.write("FAIL: {} 探测器 error check fail: {}\n".format(label, failed))
        sys.stderr.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        raise SystemExit(1)
    print("[OK] {} 探测器：所有 error check pass".format(label))
    return data


def main():
    if not WS_CHECK.exists() or not WIKI_CHECK.exists():
        raise SystemExit(
            "FAIL: my_SKILL 探测器缺失（{} / {}）——CI 未拉 submodule？".format(
                WS_CHECK, WIKI_CHECK
            )
        )

    with tempfile.TemporaryDirectory(prefix="llmw-smoke-") as tmp:
        ws = Path(tmp) / "ws"

        _llmw(["init", "--path=" + str(ws)])
        _llmw(
            [
                "--workspace=" + str(ws),
                "model",
                "add",
                "--model-id=m1",
                "--name=T",
                "--base-url=https://x.com",
                "--api-key=k",
                "--default",
            ]
        )
        _llmw(
            [
                "--workspace=" + str(ws),
                "wiki",
                "--name=w",
                "add",
                "--topic=T",
                "--display-name=T",
                "--description=d",
                "--tag=x",
                "--model=m1",
            ]
        )

        ws_data = _assert_all_error_pass(WS_CHECK, ws, "workspace")
        wiki_data = _assert_all_error_pass(WIKI_CHECK, ws / "w", "wiki")

        # 显式确认两条读取契约 check（E1/E2）落地且 pass——SKILL 读取契约自洽对接
        for check_id, data in [
            ("workspace-toml-reads-satisfied", ws_data),
            ("wiki-metadata-reads-satisfied", wiki_data),
        ]:
            ids = {c["id"]: c.get("passed") for c in data["checks"]}
            if ids.get(check_id) is not True:
                raise SystemExit(
                    "FAIL: {} check 未 pass/缺失: {}".format(check_id, ids)
                )
        print("[OK] 读取契约 check（E1/E2）passed=True")

    print("\nsmoke gate PASS")


if __name__ == "__main__":
    main()
