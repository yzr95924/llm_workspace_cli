"""wiki enter — 启动 Claude Code session (Phase 1 简化版: 不传 model, 不传 env)

来源: doc/design/03-wiki-enter.md。Phase 1 不读取/不解析/不传递 model 给
claude 子进程，env 完全透传（不传 env= 参数）。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from llmw.errors import ClaudeNotFound, WikiDirMissing, WikiNotFound
from llmw.workspace import store as ws_store


def _resolve_wiki_path(workspace_root: Path, name: str) -> Path:
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(
            f"wiki '{name}' 不在当前 workspace 中",
            hint="运行 `llmw list` 查看已注册 wiki",
        )
    return workspace_root / ws.wikis[name].path


def _read_system_prompt(wiki_path: Path):
    """读 CLAUDE.md 内容作为 system-prompt。

    设计 03: “cat 原样交给 claude”——直接读文件内容传给 claude 子进程，
    不走 shell 的 ``$(cat ...)``（subprocess.run 无 shell，字面量会是错的）。
    返回 (content, claude_md_path)；缺失返回 (None, path)。
    空文件返回 ("", path)——按设计空 CLAUDE.md 仍传 ``--system-prompt ""``。
    """
    claude_md = wiki_path / "CLAUDE.md"
    if not claude_md.is_file():
        return None, claude_md
    return claude_md.read_text(encoding="utf-8"), claude_md


def _build_cmd(wiki_path: Path):
    """构造 claude 子进程 argv（真实可执行版）。Phase 1 不传 model, 不传 env。

    返回 (cmd, prompt)。prompt 为 None 表示 CLAUDE.md 缺失，不传 --system-prompt。
    """
    prompt, _ = _read_system_prompt(wiki_path)
    cmd = ["claude", "--add-dir", str(wiki_path)]
    if prompt is not None:
        cmd += ["--system-prompt", prompt]
    return cmd, prompt


def enter(workspace_root: Path, name: str, dry_run: bool = False) -> int:
    wiki_path = _resolve_wiki_path(workspace_root, name)

    if not wiki_path.is_dir():
        raise WikiDirMissing(
            f"wiki 子目录不存在: {wiki_path}",
            hint="可能被外部 rm；可 `git checkout` 恢复或重新 add",
        )

    claude_md = wiki_path / "CLAUDE.md"
    meta_p = wiki_path / "wiki_metadata.toml"

    # 软警告（不阻断）
    if not claude_md.is_file():
        print(
            f"[llmw] warning: wiki '{name}' 缺少 CLAUDE.md，"
            f"session 启动后将没有 schema 上下文",
            file=sys.stderr,
        )
    if not meta_p.is_file():
        print(f"[llmw] warning: wiki '{name}' 缺少 wiki_metadata.toml", file=sys.stderr)

    # 检查 claude 在 PATH（dry-run 时跳过）
    if not dry_run and shutil.which("claude") is None:
        raise ClaudeNotFound(
            "claude 不在 PATH",
            hint="安装 Claude Code 或加到 PATH 后重试；可用 --dry-run 看命令",
        )

    cmd, prompt = _build_cmd(wiki_path)

    # 打印 dry-run 信息
    if dry_run:
        from llmw.wiki.store import load as wiki_load
        meta = None
        if meta_p.is_file():
            try:
                meta = wiki_load(wiki_path)
            except Exception:
                meta = None
        ws = ws_store.load(workspace_root)
        print(f"[llmw] workspace: {workspace_root}", file=sys.stdout)
        print(f"[llmw] wiki:      {name} ({wiki_path})", file=sys.stdout)
        if meta and meta.model:
            print(
                f"[llmw] wiki.model: {meta.model} "
                f"(note: Phase 1 不传递给 Claude Code)",
                file=sys.stdout,
            )
        elif ws.default_model:
            print(
                f"[llmw] workspace.default_model: {ws.default_model} "
                f"(note: Phase 1 不传递给 Claude Code)",
                file=sys.stdout,
            )
        if claude_md.is_file():
            print(
                f"[llmw] CLAUDE.md: ✓ found ({claude_md.stat().st_size} bytes)",
                file=sys.stdout,
            )
        else:
            print(f"[llmw] CLAUDE.md: ✗ missing", file=sys.stdout)
        # 可读展示（shell 风格），而非把整份 CLAUDE.md 内容内联打印
        if prompt is not None:
            cmd_display = (
                f'claude --add-dir {wiki_path} '
                f'--system-prompt "$(cat {claude_md})"'
            )
        else:
            cmd_display = f'claude --add-dir {wiki_path}'
        print(f"[llmw] cmd:", file=sys.stdout)
        print(f"  {cmd_display}", file=sys.stdout)
        print(f"[llmw] env: 继承当前 shell（CLI 不修改）", file=sys.stdout)
        print(f"[llmw] --dry-run: 未执行", file=sys.stdout)
        return 0

    # 真正执行：env 完全透传（不传 env= 参数）
    os.chdir(wiki_path)
    result = subprocess.run(cmd)
    return result.returncode
