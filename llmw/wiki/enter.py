"""wiki enter — 启动 Claude Code session (Phase 2: 通过 resolve 拿 model, env overlay 注入 ANTHROPIC_*)

来源: doc/design/03-wiki-enter.md + 09-workspace-model-registry.md §9.5。
Phase 2 契约：env 不再完全透明——显式注入 ANTHROPIC_MODEL/BASE_URL/AUTH_TOKEN，其他从 os.environ 透传。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from llmw._compat import TOMLDecodeError
from llmw.errors import ClaudeNotFound, SchemaVersionUnsupported, WikiDirMissing, WikiNotFound
from llmw.models.redact import redact_api_key
from llmw.models.resolve import resolve_for_wiki
from llmw.models.store import ModelEntry
from llmw.wiki.store import load as wiki_load
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
    缺失返回 (None, path)。空文件返回 ("", path)——按设计空 CLAUDE.md 仍传 ``--system-prompt ""``。

    为什么读全文而不是 ``--system-prompt "$(cat CLAUDE.md)"``？
    subprocess.run 不走 shell，$() 会作为字面量传给 claude；只能预先读出。
    """
    claude_md = wiki_path / "CLAUDE.md"
    if not claude_md.is_file():
        return None, claude_md
    return claude_md.read_text(encoding="utf-8"), claude_md


def _build_cmd(wiki_path: Path):
    """构造 claude 子进程 argv。

    --add-dir + 可选 --system-prompt 不变。
    --setting-sources project,local：不加载 user 源（~/.claude/settings.json）。否则其 env 块
    （如全局固定的 ANTHROPIC_MODEL/BASE_URL/AUTH_TOKEN）会在 claude 启动时盖掉本命令注入的
    per-wiki env overlay（见 _build_env_overlay）——Claude Code 的 settings env 块优先级高于
    继承的进程环境变量。wiki 会话共享的 project 级配置（.mcp.json / .claude/settings.json）仍从
    cwd（wiki 子目录）加载。
    """
    prompt, _ = _read_system_prompt(wiki_path)
    cmd = ["claude", "--add-dir", str(wiki_path), "--setting-sources", "project,local"]
    if prompt is not None:
        cmd += ["--system-prompt", prompt]
    return cmd, prompt


def _build_env_overlay(model: ModelEntry) -> dict:
    """Phase 2：显式注入 3 个 ANTHROPIC_* env（其他 key 从 os.environ 透传）。

    ANTHROPIC_MODEL 用 model.name（网关模型名，如 "MiniMax-M3[1m]" / "glm-5.2[1m]"），
    不是 model_id（registry 内部 slug，如 minimax-m3-1m）——网关只认 name，slug 它不识别。
    """
    return {
        "ANTHROPIC_MODEL":      model.name,
        "ANTHROPIC_BASE_URL":   model.base_url,
        "ANTHROPIC_AUTH_TOKEN": model.api_key,
    }


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

    # Phase 2：通过 resolve 拿最终 model（失败会阻断 enter）
    model = resolve_for_wiki(workspace_root, name)

    cmd, prompt = _build_cmd(wiki_path)
    full_env = {**os.environ, **_build_env_overlay(model)}

    # dry-run
    if dry_run:
        meta = None
        if meta_p.is_file():
            try:
                meta = wiki_load(wiki_path)
            except (OSError, TOMLDecodeError, SchemaVersionUnsupported) as e:
                # 文件存在但读失败 / TOML 解析失败 / schema 不支持 → 软降级
                # resolve 已经捕过 SchemaVersionUnsupported；这里再捕是为了让 dry-run
                # 还能打印 resolved model / env overlay（schema 错误不该阻断预览）
                print(
                    f"[llmw] warning: 无法读取 wiki_metadata.toml: {type(e).__name__}: {e}",
                    file=sys.stderr,
                )
                meta = None
        print(f"[llmw] workspace: {workspace_root}", file=sys.stdout)
        print(f"[llmw] wiki:      {name} ({wiki_path})", file=sys.stdout)
        print(
            f"[llmw] resolved model: {model.name} ({model.model_id})",
            file=sys.stdout,
        )
        source = "wiki override" if (meta and meta.model) else "registry default"
        print(f"[llmw] source: {source}", file=sys.stdout)
        print(f"[llmw] ANTHROPIC_MODEL      = {model.name}", file=sys.stdout)
        print(f"[llmw] ANTHROPIC_BASE_URL   = {model.base_url}", file=sys.stdout)
        print(f"[llmw] ANTHROPIC_AUTH_TOKEN = {redact_api_key(model.api_key)}", file=sys.stdout)
        if claude_md.is_file():
            print(
                f"[llmw] CLAUDE.md: ✓ found ({claude_md.stat().st_size} bytes)",
                file=sys.stdout,
            )
        else:
            print(f"[llmw] CLAUDE.md: ✗ missing", file=sys.stdout)
        if prompt is not None:
            cmd_display = (
                f'claude --add-dir {wiki_path} --setting-sources project,local '
                f'--system-prompt "$(cat {claude_md})"'
            )
        else:
            cmd_display = f'claude --add-dir {wiki_path} --setting-sources project,local'
        print(f"[llmw] cmd:", file=sys.stdout)
        print(f"  {cmd_display}", file=sys.stdout)
        print(f"[llmw] env overlay: ANTHROPIC_MODEL/BASE_URL/AUTH_TOKEN（其他透传 os.environ）",
              file=sys.stdout)
        print(f"[llmw] --dry-run: 未执行", file=sys.stdout)
        return 0

    # 真正执行
    os.chdir(wiki_path)
    result = subprocess.run(cmd, env=full_env)
    return result.returncode
