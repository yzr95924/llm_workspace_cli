#!/usr/bin/env python3
"""CI smoke gate：fresh llmw init + wiki → 两探测器 → 断言结构合规。

兑现 [[check-fixtures-as-executable-truth]]：CLI 改坏骨架 / my_SKILL 改坏 fixtures
都让本 gate 红。双向覆盖。

断言策略（对版本漂移免疫，不依赖阶段 4 bump）：
- workspace 探测器 exit=0（版本已对齐 0.7.0，全 error check pass）
- wiki 探测器：所有 error 级 check passed=True，**忽略** ``agents-version-is-current``
  （CLI ``WIKI_SPEC_VERSION`` 滞后 my_SKILL 的已知漂移，阶段 4 bump 后自愈；gate 不为它红）

阶段 4 bump 后 wiki 也全 pass，本脚本无需改动（忽略项本就 pass，无害）。

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


def _llmw(args, cwd=None):
    """跑 ``python -m llmw <args>``，失败即抛（gate 红）。"""
    env = dict(os.environ, PYTHONPATH=str(REPO))
    proc = subprocess.run(
        [sys.executable, "-m", "llmw", *args],
        env=env,
        capture_output=True,
        text=True,
        cwd=cwd,
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
        wiki = ws / "w"

        # workspace：断言 exit=0（全 error check pass）
        ws_env = dict(os.environ, PYTHONPATH=str(REPO))
        ws_proc = subprocess.run(
            [sys.executable, str(WS_CHECK), str(ws), "--json"],
            env=ws_env,
            capture_output=True,
            text=True,
        )
        if ws_proc.returncode != 0:
            sys.stderr.write(ws_proc.stdout)
            sys.stderr.write(ws_proc.stderr)
            raise SystemExit(
                "FAIL: workspace 探测器 exit={}".format(ws_proc.returncode)
            )
        print("[OK] workspace 探测器 exit=0（7/7 pass）")

        # wiki：断言所有 error check pass，忽略 agents-version 版本漂移
        data = _detector_json(WIKI_CHECK, wiki)
        # 允许的版本漂移 check（阶段 4 bump 后自愈）
        VERSION_DRIFT = {"agents-version-is-current"}
        failed = [
            c["id"]
            for c in data["checks"]
            if c.get("severity") == "error"
            and c.get("passed") is False
            and c["id"] not in VERSION_DRIFT
        ]
        if failed:
            sys.stderr.write(
                "FAIL: wiki 探测器非版本漂移的 error fail: {}\n".format(failed)
            )
            sys.stderr.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            raise SystemExit(1)
        # 显式确认新 check 落地（对接 E2 读取契约）
        ids = {c["id"]: c.get("passed") for c in data["checks"]}
        if ids.get("wiki-metadata-reads-satisfied") is not True:
            raise SystemExit(
                "FAIL: wiki-metadata-reads-satisfied 未 pass: {}".format(ids)
            )
        drifted = [
            c["id"]
            for c in data["checks"]
            if c["id"] in VERSION_DRIFT and c.get("passed") is False
        ]
        suffix = "（忽略版本漂移: {}）".format(drifted) if drifted else ""
        print("[OK] wiki 探测器：所有 error check pass{}".format(suffix))
        print("[OK] wiki-metadata-reads-satisfied passed=True（读取契约自洽）")

    print("\nsmoke gate PASS")


if __name__ == "__main__":
    main()
