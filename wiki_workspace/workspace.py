"""workspace 路径解析、TOML 读写、原子持久化。"""

import os
import tempfile
from datetime import date
from pathlib import Path

try:
    import tomllib  # py>=3.11
except ModuleNotFoundError:  # pragma: no cover - py<3.11 路径
    import tomli as tomllib  # type: ignore

from wiki_workspace import errors


def atomic_write(path, content):
    """tmp + fsync + 原子 rename（spec §4.3）。失败绝不写半截。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=".{}.".format(path.name), suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def load_toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_toml_str(text):
    return tomllib.loads(text)


def _toml_escape(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def dump_toml(data):
    """schema 专属序列化器。安全是因为 schema 由我们完全掌控：每个值都是带引号
    字符串或 list[str]，每个 key 都是 TOML 合法裸 key。解决缺口 #1（无 tomli_w）。"""
    lines = []
    lines.append('schema_version = "{}"'.format(_toml_escape(data["schema_version"])))
    lines.append('created = "{}"'.format(_toml_escape(data["created"])))
    lines.append("")
    ws = data.get("workspace", {})
    lines.append("[workspace]")
    lines.append(
        'default_model = "{}"'.format(_toml_escape(ws.get("default_model", "claude-sonnet-4-6")))
    )
    lines.append("")
    for name, w in data["wikis"].items():
        lines.append("[wikis.{}]".format(name))
        lines.append('path = "{}"'.format(_toml_escape(w["path"])))
        lines.append('display_name = "{}"'.format(_toml_escape(w["display_name"])))
        if w.get("description"):
            lines.append('description = "{}"'.format(_toml_escape(w["description"])))
        if w.get("model"):
            lines.append('model = "{}"'.format(_toml_escape(w["model"])))
        lines.append('created = "{}"'.format(_toml_escape(w["created"])))
        tags = w.get("tags") or []
        lines.append("tags = [" + ", ".join('"{}"'.format(_toml_escape(t)) for t in tags) + "]")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


DEFAULT_HOME_WORKSPACE = "llm_workspace"


def today_iso():
    return date.today().isoformat()


def manifest_filename():
    return ".workspace.toml"


def is_initialized(root):
    return (Path(root) / manifest_filename()).is_file()


def find_root(cli_workspace=None, env=None, cwd=None, home=None):
    """4 级优先级（spec §3.0.1）。永不抛错；兜底到 ~/llm_workspace。"""
    if env is None:
        env = os.environ
    if cwd is None:
        cwd = os.getcwd()
    if home is None:
        home = str(Path.home())

    # 1. 显式 --workspace
    if cli_workspace:
        return Path(cli_workspace).expanduser().resolve()
    # 2. $LLMW_WORKSPACE
    env_val = env.get("LLMW_WORKSPACE")
    if env_val:
        return Path(env_val).expanduser().resolve()
    # 3. 从 cwd 向上找第一个含 .workspace.toml 的目录
    cur = Path(cwd).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / manifest_filename()).is_file():
            return candidate
    # 4. 默认 ~/llm_workspace
    return (Path(home) / DEFAULT_HOME_WORKSPACE).resolve()


def manifest_path(root):
    return Path(root) / manifest_filename()


def save_manifest(workspace_root, manifest_obj):
    """原子写 + 重解析自检（spec §4.3）。若刚写完的文件重解析失败，
    抛 CommandError(EXIT_INTERNAL, 'internal-state-corruption')。"""
    from wiki_workspace import manifest as manifest_mod

    text = manifest_mod.serialize(manifest_obj)
    target = manifest_path(workspace_root)
    atomic_write(target, text)
    try:
        manifest_mod.parse(text)
    except Exception as exc:  # 重解析失败 -> 损坏
        raise errors.CommandError(
            errors.EXIT_INTERNAL,
            "internal-state-corruption",
            "写盘后重解析失败：{}".format(exc),
            hint="检查磁盘空间 / 权限；可从 .workspace.toml.bak 恢复",
        )
