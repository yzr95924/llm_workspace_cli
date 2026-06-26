"""对 llm-wiki-management 的软依赖。

持有 4 级 skill 根探测（spec §1.4），软导入 ``slugify``（来自 scripts/setup_wiki.py）
与 ``parse_frontmatter_simple``（来自 scripts/ingest_diff.py）。两个源模块都只依赖
stdlib，所以用 importlib 加载是零依赖的。任何失败都回退到内置 stub，
后者复刻相同输出。叶子纯模块：不 import 任何内部模块。
"""

import importlib.util
import os
import re
from pathlib import Path
from typing import Dict, Optional

_SKILL_DIR_NAME = "llm-wiki-management"
# 测试里会被 patch；真实默认惰性计算
_HOME_SKILL_PATH = Path.home() / ".claude" / "skills" / _SKILL_DIR_NAME

_cache: Dict[str, object] = {}


def find_skill_root(workspace_root=None) -> Optional[Path]:
    """4 级优先级探测。返回 skill 绝对目录或 None。"""
    env_path = os.environ.get("LLM_WIKI_MANAGEMENT_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path).expanduser())
    if workspace_root:
        candidates.append(Path(workspace_root).resolve().parent / _SKILL_DIR_NAME)
    candidates.append(_HOME_SKILL_PATH)
    for c in candidates:
        if (c / "SKILL.md").is_file():
            return c.resolve()
    return None


def _load_module(module_name, file_path):
    """用 importlib 把独立脚本当模块加载。返回模块或 None。"""
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


# --- stub（与真函数行为一致）----------------------------------------------
def _slugify_stub(name):
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "wiki"


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def _parse_frontmatter_simple_stub(text):
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    result: Dict[str, object] = {}
    cur_key = None
    cur_items = []
    for raw in m.group(1).splitlines():
        line = raw.rstrip()
        if not line:
            continue
        lm = re.match(r"^\s+-\s+(.+?)\s*$", line)
        if lm and cur_key is not None:
            cur_items.append(lm.group(1).strip())
            continue
        if cur_key is not None:
            result[cur_key] = cur_items
            cur_key = None
            cur_items = []
        kv = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if not kv:
            continue
        key, val = kv.group(1), kv.group(2).strip()
        if val == "" or val == "[]":
            result[key] = []
            cur_key = key
            cur_items = []
        elif val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            result[key] = [x.strip().strip("\"'") for x in inner.split(",")] if inner else []
        else:
            result[key] = val.strip("\"'")
    if cur_key is not None:
        result[cur_key] = cur_items
    return result


def configure(skill_root):
    """为给定 skill_root（或 None 走 stub）解析并缓存软导入。"""
    _cache.clear()
    if skill_root is None:
        _cache["slugify"] = _slugify_stub
        _cache["parse_frontmatter_simple"] = _parse_frontmatter_simple_stub
        return
    scripts = skill_root / "scripts"
    setup_mod = _load_module("llwm_setup_compat", scripts / "setup_wiki.py")
    ingest_mod = _load_module("llwm_ingest_compat", scripts / "ingest_diff.py")
    _cache["slugify"] = getattr(setup_mod, "slugify", None) or _slugify_stub
    _cache["parse_frontmatter_simple"] = (
        getattr(ingest_mod, "parse_frontmatter_simple", None) or _parse_frontmatter_simple_stub
    )


def slugify(name):
    if "slugify" not in _cache:
        configure(find_skill_root())
    return _cache["slugify"](name)  # type: ignore


def parse_frontmatter_simple(text):
    if "parse_frontmatter_simple" not in _cache:
        configure(find_skill_root())
    return _cache["parse_frontmatter_simple"](text)  # type: ignore
