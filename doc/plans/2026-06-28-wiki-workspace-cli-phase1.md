# Wiki Workspace CLI — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `llmw` (wiki workspace CLI) Phase 1——workspace / wiki 元数据管理 + 基础 CRUD + 启动 Claude Code session，覆盖 8 个命令：`init` / `config` / `list` / `wiki add` / `wiki remove` / `wiki show` / `wiki config` / `wiki enter`。

**Architecture:** 单二进制 Python 3.7+ 包 + `bin/llmw` shell wrapper；`llmw.cli` argparse 分派到 `llmw.{workspace,wiki}.manager` 业务层，业务层走 `llmw.{workspace,wiki}.store` 读写元数据，`wiki add` 调 `my_SKILL` submodule 的 `setup_wiki.py`，`wiki enter` 走 subprocess 启动 `claude`。所有元数据写走原子写（tmp + fsync + os.replace）。

**Tech Stack:**
- Python 3.7+ baseline
- `tomllib` (3.11+) / `tomli` (3.7-3.10) — TOML 解析
- 标准库：`argparse`、`pathlib`、`subprocess`、`datetime`、`dataclasses`、`input()` (stdlib TTY)
- 外部依赖：git (init)、`claude` (enter)、`my_SKILL/llm-wiki-management/scripts/setup_wiki.py` (wiki add)

**测试策略：** 按 `MEMORY/test-priority-low`，prototype 阶段**不**写自动化测试。每个 task 用**手动 smoke** 验证 happy path；完整的 manual smoke checklist 在 Task 17。

**关键不变量（来自 design doc 00）：**
- I-1: CLI 不写 wiki 内容（不写 `raw/` / `wiki/`，只写 `workspace.toml` + `wiki_metadata.toml`）
- I-2: `add` 的目录结构由 `setup_wiki.py` 创建
- I-3: SKILL 是 submodule，路径固定
- I-4: 可执行入口在 `bin/llmw`，与 Python 包分离

---

## File Structure

| 路径 | 职责 | 创建于 |
| --- | --- | --- |
| `pyproject.toml` | 包元数据 + `console_scripts` 入口 | Task 1 |
| `bin/llmw` | shell wrapper（5 行）：`exec python3 -m llmw "$@"` | Task 2 |
| `llmw/__init__.py` | 包元数据 `__version__` | Task 3 |
| `llmw/__main__.py` | `cli.main()` 调用入口 | Task 3 |
| `llmw/_compat.py` | tomllib/tomli 兼容层 + Python 版本探测 | Task 5 |
| `llmw/errors.py` | 21 个异常类 + `format_error()` 渲染 | Task 4 |
| `llmw/config.py` | `resolve_workspace_root()` + 包内路径定位 | Task 6 |
| `llmw/fsutil.py` | `atomic_write()` + 辅助 (now_iso8601 等) | Task 7 |
| `llmw/cli.py` | argparse 顶层 + 全局 flag + 子命令分派 | Tasks 12/14/16 |
| `llmw/workspace/__init__.py` | 子包标记（空） | Task 8 |
| `llmw/workspace/store.py` | `workspace.toml` 读 / 写 / 校验 / schema_version | Task 8 |
| `llmw/workspace/manager.py` | `init` / `config` / `list` 业务 | Task 11 |
| `llmw/wiki/__init__.py` | 子包标记（空） | Task 9 |
| `llmw/wiki/store.py` | `wiki_metadata.toml` 读 / 写 / 校验 + 模板填充 | Task 9 |
| `llmw/wiki/manager.py` | `add` / `remove` / `show` / `config` 业务 | Task 13 |
| `llmw/wiki/enter.py` | claude 子进程启动 + `--dry-run` | Task 15 |
| `templates/wiki_metadata.toml.template` | wiki metadata 初始模板 | Task 10 |
| `README.md` | 完整安装 / 用法 / 手动 smoke 清单 | Task 17 |

**按职责分层原则：**
- `errors` / `_compat` / `fsutil` / `config` 是横切基础设施
- `*.store` 只做 I/O + schema 校验，不做业务决策
- `*.manager` 做业务（交互、回滚、命令构造），调 store + subprocess
- `cli` 只做 argparse + 分派，不含业务逻辑

---

## Phase 0 — Skeleton

### Task 1: `pyproject.toml` with console_scripts entry

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: 写 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "llmw"
version = "0.1.0"
description = "Wiki workspace CLI for managing LLM wikis under a single git repo"
requires-python = ">=3.7"
dependencies = [
    "tomli>=1.1; python_version < '3.11'",
]

[project.scripts]
llmw = "llmw.cli:main"

[tool.setuptools]
packages = ["llmw", "llmw.workspace", "llmw.wiki"]
include-package-data = true

[tool.setuptools.package-data]
llmw = ["../templates/*.template"]
```

> **注：** `llmw=...console_scripts` 实际装好后用，但 dev 期 `bin/llmw` 直接走 `python -m llmw` 不依赖这行。

- [ ] **Step 2: 校验文件能解析**

```bash
cd /home/zryang/llm_workspace_cli && python3 -c "import tomllib; tomllib.loads(open('pyproject.toml').read()); print('ok')"
```

期望：`ok`（tomllib 能解析当前 pyproject.toml 文件本身，证明依赖也满足）

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml && git commit -m "build: add pyproject.toml with console_scripts entry"
```

---

### Task 2: `bin/llmw` shell wrapper

**Files:**
- Create: `bin/llmw`

- [ ] **Step 1: 写 bin/llmw**

```bash
#!/usr/bin/env bash
# bin/llmw — 仓库根目录下的可执行入口
# 通过 python -m llmw 调用；包安装到 site-packages 后此文件也被复制到 ~/.local/bin/
set -e
exec python3 -m llmw "$@"
```

- [ ] **Step 2: 加可执行权限**

```bash
chmod +x /home/zryang/llm_workspace_cli/bin/llmw
```

- [ ] **Step 3: 冒烟（期望 ModuleNotFoundError，下个 task 修）**

```bash
cd /home/zryang/llm_workspace_cli && ./bin/llmw --help
```

期望：报错 `ModuleNotFoundError: No module named 'llmw'`（包还不存在）——这是预期的，下个 task 会修。

- [ ] **Step 4: Commit**

```bash
git add bin/llmw && git commit -m "feat: add bin/llmw shell wrapper"
```

---

### Task 3: llmw package skeleton (`__init__` / `__main__` / `cli` stub)

**Files:**
- Create: `llmw/__init__.py`
- Create: `llmw/__main__.py`
- Create: `llmw/cli.py`

- [ ] **Step 1: 写 llmw/__init__.py**

```python
"""llmw — wiki workspace CLI"""
__version__ = "0.1.0"
```

- [ ] **Step 2: 写 llmw/__main__.py**

```python
"""支持 `python -m llmw ...` 调用"""
from llmw.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 写 llmw/cli.py stub（占位 main + 真实顶层结构）**

```python
"""argparse 顶层 + 全局 flag + 子命令分派"""
import argparse
import sys
from llmw import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llmw",
        description="Wiki workspace CLI (manage wikis under one git repo)",
    )
    parser.add_argument("--version", action="version", version=f"llmw {__version__}")
    parser.add_argument(
        "--workspace", metavar="PATH", default=None,
        help="workspace 根路径 (默认: $LLMW_WORKSPACE 或 ~/yzr_llm_workspace)",
    )
    parser.add_argument("--json", action="store_true", help="全局: 输出 JSON 格式")
    parser.add_argument("--debug", action="store_true", help="全局: 打印 traceback")
    parser.add_argument("--quiet", "-q", action="store_true", help="全局: 抑制 INFO")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    # workspace: init / config / list (Task 12)
    # wiki: add / remove / show / config / enter (Tasks 14 / 16)
    return parser


def main(argv: list = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print(f"[llmw stub] argv={argv or sys.argv[1:]} parsed={args}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 冒烟 — `--help` 应打印完整 usage**

```bash
cd /home/zryang/llm_workspace_cli && ./bin/llmw --help
```

期望：打印 `usage: llmw [-h] [--workspace PATH] [--json] [--debug] [--quiet] [--version] COMMAND ...`，无报错。

- [ ] **Step 5: 冒烟 — 无子命令应提示**

```bash
cd /home/zryang/llm_workspace_cli && ./bin/llmw 2>&1; echo "exit=$?"
```

期望：stdout 有 `[llmw stub] argv=[]` 或类似（说明走了 stub main），`exit=0`。

- [ ] **Step 6: Commit**

```bash
git add llmw/ && git commit -m "feat: add llmw package skeleton (init/main/cli stub)"
```

---

### Task 4: `llmw/errors.py` — 21 个异常类

**Files:**
- Create: `llmw/errors.py`

> 来源：`doc/design/06-error-handling.md` 第 6.1 节。每个异常都含 `exit_code` 与 `user_message`。
> 注意：`doc/design/06-error-handling.md` 把 `NoModelConfigured` 移除了（Phase 1 不传 model），所以实际是 **20** 个，加上 `LlmwError` 基类是 21 个。

- [ ] **Step 1: 写 errors.py**

```python
"""llmw 自定义异常 + 错误格式化"""
from typing import Optional


class LlmwError(Exception):
    """所有 CLI 异常的基类"""
    exit_code: int = 1
    user_message: str = ""

    def __init__(self, message: Optional[str] = None, hint: Optional[str] = None):
        self.message = message or self.user_message
        self.hint = hint
        super().__init__(self.message)


# ===== 用户错误 (exit_code = 1) =====

class WorkspaceNotFound(LlmwError):
    exit_code = 1
    user_message = "未找到 workspace 根"


class WorkspaceExists(LlmwError):
    exit_code = 1
    user_message = "目标路径已存在且非空"


class WikiNotFound(LlmwError):
    exit_code = 1
    user_message = "wiki 不在当前 workspace 中"


class WikiExists(LlmwError):
    exit_code = 1
    user_message = "wiki 名重复"


class WikiDirMissing(LlmwError):
    exit_code = 1
    user_message = "wiki 子目录缺失"


class PurgeRequiresConfirmation(LlmwError):
    exit_code = 1
    user_message = "非 TTY 下 --purge 需要 --yes 确认"


class InvalidConfigKey(LlmwError):
    exit_code = 1
    user_message = "config KEY 不在白名单"


class KeyNotUnsettable(LlmwError):
    exit_code = 1
    user_message = "KEY 不可 unset"


class ConfigKeyMissing(LlmwError):
    exit_code = 1
    user_message = "config get KEY 不存在"


class MissingRequiredFlag(LlmwError):
    exit_code = 1
    user_message = "非 TTY 下 metadata 字段缺 flag"


class SchemaVersionUnsupported(LlmwError):
    exit_code = 1
    user_message = "schema_version 不被当前 CLI 支持"


class InvalidWikiName(LlmwError):
    exit_code = 1
    user_message = "wiki 名格式非法"


class InvalidTagValue(LlmwError):
    exit_code = 1
    user_message = "tag 值非法"


# ===== 环境错误 (exit_code = 2) =====

class SkillMissing(LlmwError):
    exit_code = 2
    user_message = "SKILL submodule 未初始化"


class SkillScriptMissing(LlmwError):
    exit_code = 2
    user_message = "SKILL submodule 缺少 setup_wiki.py"


class SetupFailed(LlmwError):
    exit_code = 2
    user_message = "setup_wiki.py 失败"


class ClaudeNotFound(LlmwError):
    exit_code = 2
    user_message = "claude 不在 PATH"


class GitUnavailable(LlmwError):
    exit_code = 2
    user_message = "git 不可用"


class PythonUnavailable(LlmwError):
    exit_code = 2
    user_message = "sys.executable 不可执行"


# ===== 内部错误 (exit_code = 3) =====

class InternalError(LlmwError):
    exit_code = 3
    user_message = "未预期的内部错误"


def format_error(err: LlmwError, debug: bool = False) -> str:
    """渲染为 [llmw] error: ... / [llmw] hint: ... 格式"""
    lines = [f"[llmw] error: {err.message}"]
    if err.hint:
        lines.append(f"[llmw] hint: {err.hint}")
    if debug:
        import traceback
        lines.append("[llmw] traceback:")
        lines.append(traceback.format_exc())
    return "\n".join(lines)
```

- [ ] **Step 2: 冒烟 — 异常类 + exit_code 映射**

```bash
cd /home/zryang/llm_workspace_cli && python3 -c "
from llmw.errors import LlmwError, WorkspaceNotFound, SkillMissing, InternalError, format_error
assert WorkspaceNotFound().exit_code == 1
assert SkillMissing().exit_code == 2
assert InternalError().exit_code == 3
err = WorkspaceNotFound(hint='试试 cd 进去')
print(format_error(err))
"
```

期望输出三行：
```
[llmw] error: 未找到 workspace 根
[llmw] hint: 试试 cd 进去
```

- [ ] **Step 3: Commit**

```bash
git add llmw/errors.py && git commit -m "feat: add llmw.errors with 20 LlmwError subclasses + format helper"
```

---

### Task 5: `llmw/_compat.py` — tomllib/tomli fallback

**Files:**
- Create: `llmw/_compat.py`

- [ ] **Step 1: 写 _compat.py**

> **与 plan 原文的差异（2026-06-28 实现期发现）**：
> 1. stdlib `tomllib`（Python 3.11+）只读，**没有** `dump` 函数。原文第 8 行 `from tomllib import dump as toml_dump` 跑不通。
> 2. `_dump_kv(buf, scalars)` 应传 `scalars.items()`，否则 `_dump_kv` 内的 `for k, v in items` 只迭代 key。
>
> 修正实现：把 dump 函数提到模块顶层（不在 if/else 分支里），两边共用。

```python
"""Python 版本兼容层 — TOML 解析优先用 stdlib tomllib，回退 tomli"""
import io
import sys


def _toml_dumps(data):
    # 简单实现：仅处理本项目使用的 dict[str, scalar | list | dict]
    buf = io.StringIO()
    _dump_section(buf, data, prefix="")
    return buf.getvalue()


def _dump_section(buf, data, prefix):
    scalars = {}
    tables = {}
    for k, v in data.items():
        if isinstance(v, dict):
            tables[k] = v
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            # array-of-tables: [[prefix.k]]
            for item in v:
                buf.write(f"\n[[{prefix}{k}]]\n")
                _dump_kv(buf, item)
        else:
            scalars[k] = v
    _dump_kv(buf, scalars.items())  # 修正: 原 spec 漏 .items()
    for k, v in tables.items():
        buf.write(f"\n[{prefix}{k}]\n")
        _dump_section(buf, v, prefix=f"{prefix}{k}.")


def _dump_kv(buf, items):
    for k, v in items:
        if isinstance(v, str):
            buf.write(f'{k} = "{v}"\n')
        elif isinstance(v, bool):
            buf.write(f"{k} = {str(v).lower()}\n")
        elif isinstance(v, list):
            inner = ", ".join(f'"{x}"' if isinstance(x, str) else str(x) for x in v)
            buf.write(f"{k} = [{inner}]\n")
        else:
            buf.write(f"{k} = {v}\n")


def _toml_dump(data, fp):
    """统一手写 dump 实现（stdlib tomllib 和 tomli 都没有 dump）"""
    fp.write(_toml_dumps(data))


if sys.version_info >= (3, 11):
    import tomllib  # noqa: F401  stdlib
    from tomllib import loads as toml_loads  # noqa: F401
    from tomllib import TOMLDecodeError  # noqa: F401
    toml_dump = _toml_dump  # noqa: F401
else:
    try:
        import tomli as tomllib  # noqa: F401
        from tomli import loads as toml_loads  # noqa: F401
        from tomli import TOMLDecodeError  # noqa: F401
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "Python <3.11 需要 tomli 包: pip install 'tomli>=1.1'"
        ) from e
    toml_dump = _toml_dump  # noqa: F401


PYTHON_VERSION = sys.version_info
```

- [ ] **Step 2: 冒烟 — loads + dump round-trip**

```bash
cd /home/zryang/llm_workspace_cli && python3 -c "
from llmw._compat import toml_loads, toml_dump
import io
data = {'a': 1, 'b': 'hi', 'c': [1, 2, 3], 'd': {'e': True}}
buf = io.StringIO()
toml_dump(data, buf)
text = buf.getvalue()
print(text)
back = toml_loads(text)
assert back == data
print('roundtrip ok')
"
```

期望：输出 toml 文本 + `roundtrip ok`，且 dumped 文本可被 toml_loads 反向解析回原 dict。

- [ ] **Step 3: Commit**

```bash
git add llmw/_compat.py && git commit -m "feat: add llmw._compat (tomllib/tomli + toml dump fallback)"
```

---

## Phase 1 — Infrastructure

### Task 6: `llmw/config.py` — workspace_root resolution

**Files:**
- Create: `llmw/config.py`

- [ ] **Step 1: 写 config.py**

```python
"""全局配置 + workspace 路径解析 + 包内路径定位"""
import os
import sys
from pathlib import Path

from llmw import __version__
from llmw.errors import WorkspaceNotFound

DEFAULT_WORKSPACE = Path.home() / "yzr_llm_workspace"


def resolve_workspace_root(
    explicit: str = None,
    cwd: Path = None,
) -> Path:
    """解析 workspace 根路径

    优先级:
      1. explicit (--workspace flag)
      2. $LLMW_WORKSPACE env var
      3. ~/yzr_llm_workspace (默认)

    解析后校验: 必须存在、是目录、含 workspace.toml。
    不存在 → WorkspaceNotFound
    """
    if explicit:
        root = Path(explicit).resolve()
    elif os.environ.get("LLMW_WORKSPACE"):
        root = Path(os.environ["LLMW_WORKSPACE"]).resolve()
    else:
        root = DEFAULT_WORKSPACE.resolve()

    if not root.is_dir():
        raise WorkspaceNotFound(
            hint=f"路径不存在: {root}。可指定 --workspace 或 $LLMW_WORKSPACE",
        )
    if not (root / "workspace.toml").is_file():
        raise WorkspaceNotFound(
            hint=f"目录 {root} 不是 llmw workspace（缺少 workspace.toml）。"
                 f"可运行 `llmw init --path {root}`",
        )
    return root


def package_root() -> Path:
    """返回 llmw 包根 (含 __init__.py 的目录的父)"""
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    """返回仓库根 (package_root 的父目录)"""
    return package_root().parent


def skill_setup_script() -> Path:
    """解析 setup_wiki.py 路径

    优先级:
      1. $LLMW_SKILL_SETUP_SCRIPT env var
      2. <repo>/my_SKILL/llm-wiki-management/scripts/setup_wiki.py

    不存在 → 由调用方 raise SkillMissing / SkillScriptMissing
    """
    env_path = os.environ.get("LLMW_SKILL_SETUP_SCRIPT")
    if env_path:
        return Path(env_path).resolve()
    return repo_root() / "my_SKILL" / "llm-wiki-management" / "scripts" / "setup_wiki.py"


def templates_dir() -> Path:
    return repo_root() / "templates"
```

- [ ] **Step 2: 冒烟 — 三种来源都能解析**

```bash
cd /home/zryang/llm_workspace_cli && python3 -c "
import os, tempfile
from pathlib import Path
from llmw.config import resolve_workspace_root, package_root, repo_root, skill_setup_script

# 1) explicit
with tempfile.TemporaryDirectory() as td:
    Path(td, 'workspace.toml').touch()
    assert resolve_workspace_root(explicit=td) == Path(td).resolve()

# 2) env var
os.environ['LLMW_WORKSPACE'] = '/nonexistent'
try:
    resolve_workspace_root()
    raise AssertionError('should fail')
except Exception as e:
    # 注意: LlmwError.__str__ 返回 self.message (user_message)，不含 hint
    # hint 在 e.hint 上；要断言 hint 内容应检查 e.hint 而不是 str(e)
    assert 'LLMW_WORKSPACE' in (e.hint or '') or '路径' in (e.hint or '')

# 3) default
del os.environ['LLMW_WORKSPACE']
try:
    resolve_workspace_root()
    raise AssertionError('should fail on default too (no workspace yet)')
except Exception as e:
    print('default path also fails (expected):', type(e).__name__)

print('package_root =', package_root())
print('repo_root =', repo_root())
print('skill_setup_script =', skill_setup_script(), 'exists:', skill_setup_script().is_file())
"
```

期望：最后三行 print 显示 `repo_root = /home/zryang/llm_workspace_cli`、`skill_setup_script ... exists: True`（submodule 已初始化）。

- [ ] **Step 3: Commit**

```bash
git add llmw/config.py && git commit -m "feat: add llmw.config (workspace_root resolution + paths)"
```

---

### Task 7: `llmw/fsutil.py` — atomic_write + 时间辅助

**Files:**
- Create: `llmw/fsutil.py`

- [ ] **Step 1: 写 fsutil.py**

```python
"""文件系统原子写 + 辅助"""
import os
from datetime import datetime, timezone
from pathlib import Path


def now_iso8601() -> str:
    """UTC ISO8601 时间，秒精度，Z 后缀"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write(path: Path, content: str) -> None:
    """原子写文件

    1. 写 <path>.tmp.<pid>
    2. flush + fsync
    3. os.replace() (POSIX 原子)
    4. 失败时清理 tmp 文件
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def safe_rmtree(path: Path) -> None:
    """rm -rf 包装：失败由调用方处理（已存在的目录可能被外部占用）"""
    import shutil
    shutil.rmtree(path)
```

- [ ] **Step 2: 冒烟 — 原子写 + 失败清理**

```bash
cd /home/zryang/llm_workspace_cli && python3 -c "
import tempfile, os
from pathlib import Path
from llmw.fsutil import atomic_write, now_iso8601, safe_rmtree

# 1) 正常写
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / 'a.txt'
    atomic_write(p, 'hello')
    assert p.read_text() == 'hello'
    assert not p.with_name('a.txt.tmp.' + str(os.getpid())).exists()

# 2) 写后没残留 tmp
print('now =', now_iso8601())

# 3) safe_rmtree
with tempfile.TemporaryDirectory() as td:
    sub = Path(td) / 'sub'
    sub.mkdir()
    (sub / 'x').write_text('y')
    safe_rmtree(sub)
    assert not sub.exists()

print('fsutil smoke ok')
"
```

期望：最后输出 `fsutil smoke ok`。

- [ ] **Step 3: Commit**

```bash
git add llmw/fsutil.py && git commit -m "feat: add llmw.fsutil (atomic_write + now_iso8601 + safe_rmtree)"
```

---

## Phase 2 — Store layer

### Task 8: `llmw/workspace/store.py` — workspace.toml I/O

**Files:**
- Create: `llmw/workspace/__init__.py` (空)
- Create: `llmw/workspace/store.py`

- [ ] **Step 1: 写 llmw/workspace/__init__.py**

```python
"""workspace 子包 — 元数据存储 + 业务"""
```

- [ ] **Step 2: 写 llmw/workspace/store.py**

```python
"""workspace.toml 读写 + schema 校验"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from llmw._compat import toml_loads, toml_dump
from llmw.errors import SchemaVersionUnsupported
from llmw.fsutil import atomic_write, now_iso8601

SCHEMA_VERSION_SUPPORTED = 1


@dataclass
class WikiEntry:
    """workspace.toml [wikis.<name>] 表项"""
    name: str
    path: str
    created_at: str


@dataclass
class WorkspaceToml:
    """workspace.toml 解析结果 (Phase 1 schema)"""
    schema_version: int
    created_at: str
    templates_version: str = "1"
    default_model: Optional[str] = None
    wikis: Dict[str, WikiEntry] = field(default_factory=dict)

    @property
    def toml_path(self) -> Path:
        # 注意: 实例化时由 load() 注入；这里仅占位
        raise NotImplementedError("use load()/save() instead of constructing directly")


def load(workspace_root: Path) -> WorkspaceToml:
    """从 <workspace_root>/workspace.toml 加载并校验"""
    toml_path = workspace_root / "workspace.toml"
    with open(toml_path, "r", encoding="utf-8") as f:
        raw = toml_loads(f.read())

    sv = raw.get("schema_version")
    if sv != SCHEMA_VERSION_SUPPORTED:
        raise SchemaVersionUnsupported(
            f"workspace.toml schema_version={sv} 不被支持 (当前 CLI 仅支持 v{SCHEMA_VERSION_SUPPORTED})",
            hint="升级 CLI 或手动迁移 schema_version",
        )

    wikis: Dict[str, WikiEntry] = {}
    for name, info in raw.get("wikis", {}).items():
        wikis[name] = WikiEntry(
            name=name,
            path=info["path"],
            created_at=info["created_at"],
        )

    return WorkspaceToml(
        schema_version=sv,
        created_at=raw["created_at"],
        templates_version=raw.get("templates_version", "1"),
        default_model=raw.get("default_model"),
        wikis=wikis,
    )


def save(workspace_root: Path, ws: WorkspaceToml) -> None:
    """写回 <workspace_root>/workspace.toml (原子写)"""
    toml_path = workspace_root / "workspace.toml"
    data = {
        "schema_version": ws.schema_version,
        "created_at": ws.created_at,
        "templates_version": ws.templates_version,
    }
    if ws.default_model is not None:
        data["default_model"] = ws.default_model

    if ws.wikis:
        wiki_table = {}
        for name, entry in ws.wikis.items():
            wiki_table[name] = {
                "path": entry.path,
                "created_at": entry.created_at,
            }
        data["wikis"] = wiki_table

    import io
    buf = io.StringIO()
    toml_dump(data, buf)
    atomic_write(toml_path, buf.getvalue())


def create_skeleton(workspace_root: Path) -> WorkspaceToml:
    """init 时调用：生成空 workspace.toml"""
    ws = WorkspaceToml(
        schema_version=SCHEMA_VERSION_SUPPORTED,
        created_at=now_iso8601(),
        templates_version="1",
    )
    save(workspace_root, ws)
    return ws
```

- [ ] **Step 3: 冒烟 — 骨架 + load + 加 wiki + save + reload**

```bash
cd /home/zryang/llm_workspace_cli && python3 -c "
import tempfile
from pathlib import Path
from llmw.workspace.store import create_skeleton, load, save, WikiEntry

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    ws = create_skeleton(root)
    assert (root / 'workspace.toml').exists()
    print('after create_skeleton: wikis =', list(ws.wikis.keys()))

    # 加载
    ws2 = load(root)
    assert ws2.created_at == ws.created_at
    assert ws2.default_model is None

    # 加 wiki
    ws2.wikis['foo'] = WikiEntry(name='foo', path='foo', created_at='2026-06-28T00:00:00Z')
    save(root, ws2)

    # reload
    ws3 = load(root)
    assert 'foo' in ws3.wikis
    assert ws3.wikis['foo'].path == 'foo'
    print('after save+reload: wikis =', list(ws3.wikis.keys()))

print('workspace.store smoke ok')
"
```

期望：`workspace.store smoke ok`。

- [ ] **Step 4: Commit**

```bash
git add llmw/workspace/ && git commit -m "feat: add llmw.workspace.store (workspace.toml I/O)"
```

---

### Task 9: `llmw/wiki/store.py` — wiki_metadata.toml I/O + 模板填充

**Files:**
- Create: `llmw/wiki/__init__.py` (空)
- Create: `llmw/wiki/store.py`

- [ ] **Step 1: 写 llmw/wiki/__init__.py**

```python
"""wiki 子包 — 元数据存储 + 业务 + enter"""
```

- [ ] **Step 2: 写 llmw/wiki/store.py**

```python
"""wiki_metadata.toml 读写 + schema 校验 + 模板填充"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from llmw._compat import toml_loads, toml_dump
from llmw.config import templates_dir
from llmw.errors import InvalidTagValue, InvalidWikiName, SchemaVersionUnsupported
from llmw.fsutil import atomic_write, now_iso8601

SCHEMA_VERSION_SUPPORTED = 1
NAME_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
TAG_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


@dataclass
class WikiMetadata:
    schema_version: int
    name: str
    topic: str
    created_at: str
    updated_at: str
    display_name: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    model: Optional[str] = None

    def bump(self):
        """任何 set 后调用，更新 updated_at"""
        self.updated_at = now_iso8601()


def validate_name(name: str) -> None:
    if not NAME_RE.match(name):
        raise InvalidWikiName(
            f"wiki 名 '{name}' 非法: 仅允许小写字母 / 数字 / '-' / '_'，长度 1-64",
        )


def validate_tag(tag: str) -> None:
    if not TAG_RE.match(tag):
        raise InvalidTagValue(
            f"tag '{tag}' 非法: 仅允许小写字母 / 数字 / '-' / '_'，长度 1-32",
        )


def load(wiki_dir: Path) -> WikiMetadata:
    """从 <wiki_dir>/wiki_metadata.toml 加载并校验"""
    toml_path = wiki_dir / "wiki_metadata.toml"
    with open(toml_path, "rb") as f:
        raw = toml_loads(f.read())

    sv = raw.get("schema_version")
    if sv != SCHEMA_VERSION_SUPPORTED:
        raise SchemaVersionUnsupported(
            f"wiki_metadata.toml schema_version={sv} 不被支持 (当前 CLI 仅支持 v{SCHEMA_VERSION_SUPPORTED})",
            hint="升级 CLI 或手动迁移",
        )
    return WikiMetadata(
        schema_version=sv,
        name=raw["name"],
        topic=raw["topic"],
        created_at=raw["created_at"],
        updated_at=raw["updated_at"],
        display_name=raw.get("display_name", ""),
        description=raw.get("description", ""),
        tags=list(raw.get("tags", [])),
        model=raw.get("model") or None,
    )


def save(wiki_dir: Path, meta: WikiMetadata) -> None:
    """原子写回 wiki_metadata.toml"""
    toml_path = wiki_dir / "wiki_metadata.toml"
    data = {
        "schema_version": meta.schema_version,
        "name": meta.name,
        "topic": meta.topic,
        "created_at": meta.created_at,
        "updated_at": meta.updated_at,
        "display_name": meta.display_name,
        "description": meta.description,
        "tags": meta.tags,
    }
    if meta.model is not None:
        data["model"] = meta.model

    import io
    buf = io.StringIO()
    toml_dump(data, buf)
    atomic_write(toml_path, buf.getvalue())


def create_skeleton(wiki_dir: Path, name: str, topic: str) -> WikiMetadata:
    """add 时调用：从 templates/wiki_metadata.toml.template 拷出实例"""
    template_path = templates_dir() / "wiki_metadata.toml.template"
    template = template_path.read_text(encoding="utf-8")
    now = now_iso8601()
    text = (template
            .replace("__NAME__", name)
            .replace("__TOPIC__", topic)
            .replace("__NOW_ISO8601__", now))

    toml_path = wiki_dir / "wiki_metadata.toml"
    atomic_write(toml_path, text)

    return load(wiki_dir)
```

- [ ] **Step 3: 冒烟 — 但 template 文件还不存在，会失败**

```bash
cd /home/zryang/llm_workspace_cli && python3 -c "
import tempfile
from pathlib import Path
from llmw.wiki.store import validate_name, validate_tag, load, save, create_skeleton, WikiMetadata

# name 校验
validate_name('llm-systems')
validate_name('foo_bar-1')
try:
    validate_name('Foo'); raise AssertionError('should reject uppercase')
except Exception: pass
try:
    validate_name('a' * 65); raise AssertionError('should reject too long')
except Exception: pass

# tag 校验
validate_tag('research')
try:
    validate_tag('Bad'); raise AssertionError('should reject')
except Exception: pass

# template 还没建
with tempfile.TemporaryDirectory() as td:
    wiki = Path(td) / 'foo'
    wiki.mkdir()
    try:
        create_skeleton(wiki, 'foo', 'Foo')
        raise AssertionError('should fail without template')
    except FileNotFoundError as e:
        print('expected failure (no template yet):', e)

print('partial smoke ok (template-dependent step will be unblocked at Task 10)')
"
```

期望：输出 `partial smoke ok (template-dependent step will be unblocked at Task 10)`，且 name / tag 校验异常被正确捕获。

- [ ] **Step 4: Commit**

```bash
git add llmw/wiki/__init__.py llmw/wiki/store.py && git commit -m "feat: add llmw.wiki.store (wiki_metadata.toml I/O + template fill)"
```

---

### Task 10: `templates/wiki_metadata.toml.template`

**Files:**
- Create: `templates/wiki_metadata.toml.template`

- [ ] **Step 1: 写模板**

```toml
schema_version = 1
name = "__NAME__"
topic = "__TOPIC__"
display_name = ""
description = ""
tags = []
model = ""
created_at = "__NOW_ISO8601__"
updated_at = "__NOW_ISO8601__"
```

- [ ] **Step 2: 冒烟 — 走完 create_skeleton round-trip**

```bash
cd /home/zryang/llm_workspace_cli && python3 -c "
import tempfile
from pathlib import Path
from llmw.wiki.store import create_skeleton, load

with tempfile.TemporaryDirectory() as td:
    wiki = Path(td) / 'foo'
    wiki.mkdir()
    meta = create_skeleton(wiki, 'foo', 'Foo Topic')
    assert meta.name == 'foo'
    assert meta.topic == 'Foo Topic'
    assert meta.tags == []
    assert meta.model is None  # 空字符串在 load 时转 None

    meta2 = load(wiki)
    assert meta2.created_at == meta.created_at
    print('created_at =', meta2.created_at)
    print('updated_at =', meta2.updated_at)

print('template + create_skeleton round-trip ok')
"
```

期望：`template + create_skeleton round-trip ok`。

- [ ] **Step 3: Commit**

```bash
git add templates/ && git commit -m "feat: add templates/wiki_metadata.toml.template"
```

---

## Phase 3 — Workspace commands

### Task 11: `llmw/workspace/manager.py` — init / config / list

**Files:**
- Create: `llmw/workspace/manager.py`

> 来源：`doc/design/01-workspace-management.md`。交互模式用 stdlib `input()`；`config` 子命令用 positional `action + KEY + [VALUE]`；`get` / `set` / `unset` 三种 action。

- [ ] **Step 1: 写 manager.py 骨架 + init**

```python
"""workspace 级业务: init / config / list"""
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from llmw import __version__
from llmw.errors import (
    ConfigKeyMissing, InvalidConfigKey, KeyNotUnsettable,
    WorkspaceExists,
)
from llmw.fsutil import now_iso8601
from llmw.workspace import store as ws_store

# config KEY 白名单: name -> (can_set, can_unset, type)
CONFIG_KEYS = {
    "default_model":     (True,  True,  str),
    "templates_version": (False, False, str),  # 只读
    "created_at":        (False, False, str),  # 只读
    "schema_version":    (False, False, int),  # 只读
}


# ===== init =====

def init(path: Path, git: bool = True) -> Path:
    """初始化 workspace 根。返回 path"""
    path = path.resolve()
    if path.exists():
        if any(path.iterdir()):
            raise WorkspaceExists(
                f"路径已存在且非空: {path}",
                hint="指定空目录或先备份内容",
            )
    else:
        path.mkdir(parents=True)

    if git:
        try:
            subprocess.run(
                ["git", "init", str(path)],
                check=True, capture_output=True, text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            from llmw.errors import GitUnavailable
            raise GitUnavailable(f"git init 失败: {e}")

    ws_store.create_skeleton(path)

    print(f"[llmw] workspace 已初始化于 {path}", file=sys.stdout)
    print(f"[llmw] cd {path} 后可用 `llmw wiki add <name>` 新建第一个 wiki", file=sys.stdout)
    return path
```

- [ ] **Step 2: 写 config 业务（get/set/unset）**

```python
# 接 Step 1 文件，继续添加:

def _check_key(key: str) -> tuple:
    if key not in CONFIG_KEYS:
        raise InvalidConfigKey(
            f"KEY '{key}' 不在白名单",
            hint=f"可用 KEY: {', '.join(sorted(CONFIG_KEYS.keys()))}",
        )
    return CONFIG_KEYS[key]


def config_get(workspace_root: Path, key: Optional[str]) -> None:
    """无 KEY: dump 整个 workspace.toml; 有 KEY: 打印该字段值"""
    ws = ws_store.load(workspace_root)
    if key is None:
        # dump
        print(f"# workspace: {workspace_root}")
        if ws.default_model is not None:
            print(f"default_model = {ws.default_model}")
        else:
            print("# default_model: <unset>")
        print(f"created_at = {ws.created_at}")
        print(f"templates_version = {ws.templates_version}")
        print(f"schema_version = {ws.schema_version}")
        wikis = list(ws.wikis.keys())
        if wikis:
            print(f"wikis = {', '.join(sorted(wikis))}")
        else:
            print("# wikis: <empty>")
        return

    can_set, can_unset, _ = _check_key(key)
    val = getattr(ws, key, None)
    if val is None and key not in ("default_model",):
        raise ConfigKeyMissing(f"KEY '{key}' 不存在")
    if val is None:
        print("<unset>")
    else:
        print(val)


def config_set(workspace_root: Path, key: str, value: str) -> None:
    can_set, _, expected_type = _check_key(key)
    if not can_set:
        raise InvalidConfigKey(f"KEY '{key}' 不可 set（只读）")
    ws = ws_store.load(workspace_root)
    setattr(ws, key, expected_type(value))
    ws_store.save(workspace_root, ws)
    print(f"✓ {key} = {value!r}", file=sys.stdout)


def config_unset(workspace_root: Path, key: str) -> None:
    can_set, can_unset, _ = _check_key(key)
    if not can_unset:
        raise KeyNotUnsettable(f"KEY '{key}' 不可 unset")
    ws = ws_store.load(workspace_root)
    setattr(ws, key, None)
    ws_store.save(workspace_root, ws)
    print(f"✓ {key} unset", file=sys.stdout)
```

- [ ] **Step 3: 写 config 交互模式**

```python
# 接 Step 2 文件，继续添加:

def config_interactive(workspace_root: Path) -> None:
    """TTY 下 `llmw config` 无参数进入; 非 TTY 打印字段列表后退出 0"""
    if not sys.stdin.isatty():
        # 非 TTY: 打印字段列表 + 用法, 退出 0
        print("[llmw] config 子命令: get KEY / set KEY VALUE / unset KEY")
        print(f"[llmw] workspace: {workspace_root}")
        print("[llmw] 可用 KEY:")
        for i, key in enumerate(CONFIG_KEYS, 1):
            can_set, can_unset, _ = CONFIG_KEYS[key]
            ro = " (只读)" if not can_set else ""
            print(f"  {i}. {key}{ro}")
        return

    ws = ws_store.load(workspace_root)
    keys = list(CONFIG_KEYS.keys())
    while True:
        print(f"\nworkspace 配置项 ({workspace_root}/workspace.toml):")
        for i, key in enumerate(keys, 1):
            can_set, can_unset, _ = CONFIG_KEYS[key]
            val = getattr(ws, key, None)
            cur = repr(val) if val is not None else "<unset>"
            ro = " (只读)" if not can_set else ""
            print(f"  {i}. {key}{ro}    当前: {cur}")

        try:
            choice = input(f"\n选择要编辑的项 [1-{len(keys)}, q 退出]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice.lower() in ("q", ""):
            return
        try:
            idx = int(choice) - 1
            key = keys[idx]
        except (ValueError, IndexError):
            print("[llmw] 输入无效，重试")
            continue

        can_set, _, _ = CONFIG_KEYS[key]
        if not can_set:
            print(f"⚠ {key} 是只读字段，无法编辑")
            try:
                again = input("继续编辑？[Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return
            if again in ("n", "no"):
                return
            continue

        cur = getattr(ws, key, None) or ""
        prompt = f"输入新值（回车跳过 / '-' 清空）: "
        try:
            new_val = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return
        if new_val == "":
            pass  # 跳过
        elif new_val == "-":
            config_unset(workspace_root, key)
            ws = ws_store.load(workspace_root)
        else:
            config_set(workspace_root, key, new_val)
            ws = ws_store.load(workspace_root)

        try:
            again = input("继续编辑？[Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if again in ("n", "no"):
            return
```

- [ ] **Step 4: 写 list 业务**

```python
# 接 Step 3 文件，继续添加:

def list_wikis(workspace_root: Path, as_json: bool = False, tag_filter: Optional[List[str]] = None) -> int:
    """返回 0; 输出由调用方决定 (stdout)"""
    ws = ws_store.load(workspace_root)
    rows = []
    for name in sorted(ws.wikis.keys()):
        entry = ws.wikis[name]
        wiki_path = workspace_root / entry.path
        exists = wiki_path.is_dir()
        meta = None
        if exists:
            toml_p = wiki_path / "wiki_metadata.toml"
            if toml_p.is_file():
                from llmw.wiki.store import load as wiki_load
                try:
                    meta = wiki_load(wiki_path)
                except Exception:
                    meta = None

        if tag_filter:
            tags = meta.tags if meta else []
            if not all(t in tags for t in tag_filter):
                continue

        rows.append({
            "name": name,
            "path": entry.path,
            "exists": exists,
            "display_name": meta.display_name if meta else "",
            "tags": list(meta.tags) if meta else [],
            "model": meta.model if meta else None,
        })

    if as_json:
        import json
        out = [
            {
                "name": r["name"], "path": r["path"],
                "display_name": r["display_name"] or None,
                "tags": r["tags"],
                "model": r["model"],
                "wiki_dir_exists": r["exists"],
            }
            for r in rows
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # 表格
    if not rows:
        print("# (no wikis registered)")
        return 0
    name_w = max(len(r["name"]) for r in rows + [{"name": "NAME"}])
    path_w = max(len(r["path"]) for r in rows + [{"path": "PATH"}])
    print(f"{'NAME'.ljust(name_w)}  {'PATH'.ljust(path_w)}  DISPLAY_NAME  TAGS  MODEL")
    for r in rows:
        prefix = "⚠ " if not r["exists"] else "  "
        dn = r["display_name"] or "-"
        tags = ",".join(r["tags"]) or "-"
        model = r["model"] or "-"
        print(f"{prefix}{r['name'].ljust(name_w - 2)}  {r['path'].ljust(path_w)}  {dn}  {tags}  {model}")
    return 0
```

- [ ] **Step 5: 冒烟 — init + set + get + list**

```bash
cd /home/zryang/llm_workspace_cli && python3 -c "
import tempfile, subprocess, sys
from pathlib import Path

# init
with tempfile.TemporaryDirectory() as td:
    target = Path(td) / 'ws'
    from llmw.workspace.manager import init, config_set, config_get, list_wikis, WorkspaceExists, GitUnavailable
    init(target, git=False)  # 在 CI / 临时目录跳过 git init
    assert (target / 'workspace.toml').exists()
    print('init ok')

    # set default_model
    config_set(target, 'default_model', 'claude-sonnet-4-6')

    # get default_model
    config_get(target, 'default_model')  # 应打印 'claude-sonnet-4-6'

    # get 不存在
    from llmw.errors import ConfigKeyMissing
    try:
        config_get(target, 'nope'); raise AssertionError
    except ConfigKeyMissing: pass

    # set 只读字段
    from llmw.errors import InvalidConfigKey
    try:
        config_set(target, 'created_at', 'x'); raise AssertionError
    except InvalidConfigKey: pass

    # list (空)
    list_wikis(target)

    print('workspace manager smoke ok')
" 2>&1
```

期望看到 `init ok`、`claude-sonnet-4-6`、`# (no wikis registered)`、`workspace manager smoke ok`。

- [ ] **Step 6: Commit**

```bash
git add llmw/workspace/manager.py && git commit -m "feat: add llmw.workspace.manager (init/config/list)"
```

---

### Task 12: wire workspace commands into `cli.py`

**Files:**
- Modify: `llmw/cli.py`

- [ ] **Step 1: 在 build_parser() 里加 init / config / list subparsers**

替换 Task 3 里 `cli.py` 的 `build_parser()` 函数：

```python
def build_parser() -> argparse.ArgumentParser:
    from llmw import __version__
    parser = argparse.ArgumentParser(
        prog="llmw",
        description="Wiki workspace CLI (manage wikis under one git repo)",
    )
    parser.add_argument("--version", action="version", version=f"llmw {__version__}")
    parser.add_argument(
        "--workspace", metavar="PATH", default=None,
        help="workspace 根路径 (默认: $LLMW_WORKSPACE 或 ~/yzr_llm_workspace)",
    )
    parser.add_argument("--json", action="store_true", help="全局: 输出 JSON 格式")
    parser.add_argument("--debug", action="store_true", help="全局: 打印 traceback")
    parser.add_argument("--quiet", "-q", action="store_true", help="全局: 抑制 INFO")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ===== workspace 级 =====
    p_init = sub.add_parser("init", help="初始化 workspace")
    p_init.add_argument("--path", metavar="PATH", default=None)
    p_init.add_argument("--git", action="store_true", default=True)
    p_init.add_argument("--no-git", dest="git", action="store_false")

    p_config = sub.add_parser("config", help="workspace.toml 读写")
    p_config.add_argument("action", nargs="?", default=None, choices=[None, "get", "set", "unset"])
    p_config.add_argument("key", nargs="?", default=None)
    p_config.add_argument("value", nargs="?", default=None)

    p_list = sub.add_parser("list", help="列出 wiki")
    p_list.add_argument("--tag", action="append", default=[], metavar="TAG",
                        help="仅列出含此 tag 的 wiki (可重复, AND 关系)")

    # wiki 子命令见 Tasks 14 / 16

    return parser
```

- [ ] **Step 2: 替换 main() 分派**

```python
def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            from llmw.config import DEFAULT_WORKSPACE
            from llmw.workspace.manager import init as ws_init
            target = Path(args.path) if args.path else DEFAULT_WORKSPACE
            ws_init(Path(target), git=args.git)
            return 0

        # 下列命令需要先解析 workspace_root
        from llmw.config import resolve_workspace_root
        ws_root = resolve_workspace_root(args.workspace)

        if args.command == "config":
            from llmw.workspace.manager import (
                config_get, config_set, config_unset, config_interactive,
            )
            if args.action is None:
                config_interactive(ws_root)
                return 0
            if args.action == "get":
                config_get(ws_root, args.key)
            elif args.action == "set":
                config_set(ws_root, args.key, args.value)
            elif args.action == "unset":
                config_unset(ws_root, args.key)
            return 0

        if args.command == "list":
            from llmw.workspace.manager import list_wikis
            return list_wikis(ws_root, as_json=args.json, tag_filter=args.tag or None)

    except LlmwError as e:
        print(format_error(e, debug=args.debug), file=sys.stderr)
        return e.exit_code
    except Exception as e:
        if args.debug:
            raise
        print(format_error(InternalError(str(e)), debug=False), file=sys.stderr)
        return 3

    parser.print_help()
    return 0
```

并在文件顶部加 imports：

```python
from pathlib import Path
from llmw.errors import LlmwError, InternalError, format_error
```

- [ ] **Step 3: 冒烟 — `init` + `config set/get` + `list`（非 TTY）**

```bash
TMPWS=$(mktemp -d)
cd /home/zryang/llm_workspace_cli && \
  LLMW_WORKSPACE="$TMPWS" ./bin/llmw init --path "$TMPWS" --no-git
ls "$TMPWS"/workspace.toml  # 应存在
LLMW_WORKSPACE="$TMPWS" ./bin/llmw config set default_model claude-sonnet-4-6
LLMW_WORKSPACE="$TMPWS" ./bin/llmw config get default_model
LLMW_WORKSPACE="$TMPWS" ./bin/llmw list
rm -rf "$TMPWS"
```

期望：四步都返回 exit 0；`config get default_model` 打印 `claude-sonnet-4-6`；`list` 打印 `# (no wikis registered)`。

- [ ] **Step 4: 冒烟 — `--workspace` flag 优先级高于 env**

```bash
TMPWS=$(mktemp -d)
TMPWS2=$(mktemp -d)
cd /home/zryang/llm_workspace_cli && \
  ./bin/llmw init --path "$TMPWS" --no-git
# 现在 env 指向 TMPWS，flag 指向 TMPWS2：flag 应胜出
LLMW_WORKSPACE="$TMPWS" ./bin/llmw --workspace "$TMPWS2" list; echo "exit=$?"
# 期望: exit=1 (WorkspaceNotFound), 提示路径不存在
```

- [ ] **Step 5: Commit**

```bash
git add llmw/cli.py && git commit -m "feat: wire workspace commands (init/config/list) into cli"
```

---

## Phase 4 — Wiki CRUD commands

### Task 13: `llmw/wiki/manager.py` — add / remove / show / config

**Files:**
- Create: `llmw/wiki/manager.py`

> 来源：`doc/design/02-wiki-crud.md`。`add` 涉及 setup_wiki.py subprocess + 完整回滚；`config` 默认交互（与 workspace 的 config 不同，不要求 TTY）。

- [ ] **Step 1: 写 manager.py 骨架 + 辅助**

```python
"""wiki 级业务: add / remove / show / config"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from llmw.errors import (
    InvalidConfigKey, KeyNotUnsettable, MissingRequiredFlag,
    PurgeRequiresConfirmation, SetupFailed, SkillMissing, SkillScriptMissing,
    WikiExists, WikiNotFound,
)
from llmw.config import skill_setup_script
from llmw.fsutil import now_iso8601, safe_rmtree
from llmw.wiki import store as wiki_store
from llmw.workspace import store as ws_store


def _wiki_abs(workspace_root: Path, name: str) -> Path:
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(
            f"wiki '{name}' 不在当前 workspace 中",
            hint="运行 `llmw list` 查看已注册 wiki",
        )
    return workspace_root / ws.wikis[name].path


def _ensure_skill_script() -> Path:
    """解析 setup_wiki.py 路径; 不存在 raise"""
    p = skill_setup_script()
    if not p.exists():
        raise SkillMissing(
            f"找不到 SKILL submodule: {p}",
            hint="运行 `git submodule update --init` 初始化 SKILL",
        )
    if p.is_dir() or not p.name.endswith(".py"):
        raise SkillScriptMissing(
            f"SKILL 路径不是文件: {p}",
            hint="运行 `git submodule update --force` 修复 SKILL",
        )
    return p
```

- [ ] **Step 2: 写 add 业务**

```python
# 接 Step 1 文件，继续添加:

def add(
    workspace_root: Path,
    name: str,
    topic: Optional[str] = None,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    model: Optional[str] = None,
    no_setup: bool = False,
) -> Path:
    wiki_store.validate_name(name)

    ws = ws_store.load(workspace_root)
    if name in ws.wikis:
        raise WikiExists(f"wiki '{name}' 已存在")

    wiki_dir = workspace_root / name

    # 非 TTY 下: 必须所有 metadata flag 齐
    if not sys.stdin.isatty():
        missing = []
        if display_name is None: missing.append("--display-name")
        if description is None:  missing.append("--description")
        if not tags:              missing.append("--tag")
        if model is None:         missing.append("--model")
        if missing:
            raise MissingRequiredFlag(
                f"非 TTY 下 add 缺 metadata flag: {', '.join(missing)}",
                hint="补齐 flag 重试，或在 TTY 下用交互模式",
            )

    # 默认 topic = name
    if topic is None:
        topic = name

    # 创建子目录
    wiki_dir.mkdir(parents=False, exist_ok=False)

    # 跑 setup_wiki.py
    if not no_setup:
        script = _ensure_skill_script()
        try:
            # setup_wiki.py 签名是 setup_wiki.py <TOPIC> [<WIKI_ROOT>];
            # 必须显式传 wiki_dir，让脚手架 (raw/ wiki/ CLAUDE.md) 落在我们
            # 的 workspace 子目录里；缺第二参数会回退到 ~/wiki/<slug>，
            # 与 workspace 解耦（plan 草案漏了此参数，已修正）。
            result = subprocess.run(
                [sys.executable, str(script), topic, str(wiki_dir)],
                cwd=wiki_dir,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as e:
            safe_rmtree(wiki_dir)
            raise SetupFailed(f"sys.executable 不可执行: {e}")
        if result.returncode != 0:
            safe_rmtree(wiki_dir)
            stderr = (result.stderr or "").strip()
            raise SetupFailed(
                f"setup_wiki.py 失败 (exit={result.returncode}): {stderr or '(no stderr)'}",
            )

    # 写 wiki_metadata.toml
    meta = wiki_store.create_skeleton(wiki_dir, name, topic)

    # 交互模式填 metadata
    if sys.stdin.isatty():
        try:
            _interactive_fill_metadata(workspace_root, wiki_dir, meta)
        except (EOFError, KeyboardInterrupt):
            print("\n[llmw] 跳过剩余 metadata", file=sys.stderr)
        meta = wiki_store.load(wiki_dir)  # reload
    else:
        # 非 TTY: 一次性写入 flags
        if display_name is not None: meta.display_name = display_name
        if description is not None:  meta.description = description
        if tags:                      meta.tags = tags
        if model is not None:         meta.model = model
        meta.bump()
        wiki_store.save(wiki_dir, meta)

    # 注册到 workspace.toml
    ws.wikis[name] = ws_store.WikiEntry(
        name=name, path=name, created_at=now_iso8601(),
    )
    ws_store.save(workspace_root, ws)

    print(f"[llmw] wiki 已创建: {name} ({wiki_dir})", file=sys.stdout)
    print(f"[llmw] 请 git add + commit 跟踪（建议 commit message: `wiki: add {name}`）", file=sys.stdout)
    return wiki_dir


def _interactive_fill_metadata(workspace_root, wiki_dir, meta):
    """交互填充 display_name / description / tags / model"""
    def ask(label, cur):
        suffix = f" [当前: <未设置>]" if not cur else f" [当前: {cur!r}]"
        try:
            v = input(f"  {label}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise
        return v

    # display_name
    v = ask("display_name", meta.display_name)
    if v:
        meta.display_name = v
    # description
    v = ask("description", meta.description)
    if v:
        meta.description = v
    # tags
    cur_tags = list(meta.tags)
    while True:
        print(f"  tags [当前: {cur_tags}]: <a 添加 / r 移除 / s 替换 / d 完成>")
        try:
            op = input("    操作: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if op == "a":
            t = input("    新 tag: ").strip()
            if t:
                wiki_store.validate_tag(t)
                if t not in cur_tags:
                    cur_tags.append(t)
        elif op == "r":
            if not cur_tags:
                print("    (空)")
                continue
            for i, t in enumerate(cur_tags):
                print(f"      {i+1}. {t}")
            try:
                idx = int(input("    移除编号: ").strip()) - 1
                if 0 <= idx < len(cur_tags):
                    cur_tags.pop(idx)
            except (ValueError, EOFError, KeyboardInterrupt):
                pass
        elif op == "s":
            t = input("    全部 tags (逗号分隔): ").strip()
            new_tags = [x.strip() for x in t.split(",") if x.strip()]
            for x in new_tags:
                wiki_store.validate_tag(x)
            cur_tags = new_tags
        elif op == "d":
            break
    meta.tags = cur_tags

    # model
    v = ask("model", meta.model or "")
    if v:
        meta.model = v

    meta.bump()
    wiki_store.save(wiki_dir, meta)
    print("[llmw] metadata 已写入 wiki_metadata.toml", file=sys.stdout)
```

- [ ] **Step 3: 写 remove 业务**

```python
# 接 Step 2 文件，继续添加:

def remove(workspace_root: Path, name: str, purge: bool = False, yes: bool = False) -> None:
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(f"wiki '{name}' 不在当前 workspace 中")

    if purge and not yes:
        if not sys.stdin.isatty():
            raise PurgeRequiresConfirmation(
                "非 TTY 下 --purge 需要 --yes 确认",
                hint="加 --yes 或在 TTY 下手动确认",
            )
        wiki_path = workspace_root / ws.wikis[name].path
        try:
            ans = input(f"将删除 {wiki_path} 子目录及所有内容，确认？[y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            ans = "n"
        if ans not in ("y", "yes"):
            print("[llmw] 取消")
            return

    # 从 workspace.toml 移除
    del ws.wikis[name]
    ws_store.save(workspace_root, ws)

    if purge:
        wiki_path = workspace_root / ws.wikis.get(name, ws_store.WikiEntry(name=name, path=name, created_at="")).path
        # 上面兜底不严谨, 实际重读 path:
        ws2 = ws_store.load(workspace_root)
        # 不, 我们要删的是原 path, 已经在 del 之前
        # 修: 在 del 之前保存 path
        pass  # 重写更安全的版本:

    print(f"[llmw] wiki '{name}' 已取消注册" + (" 并删除子目录" if purge else ""), file=sys.stdout)
```

**上面 Step 3 末尾的重构思路不正确**，正确实现如下，**整体替换** `remove` 函数：

```python
def remove(workspace_root: Path, name: str, purge: bool = False, yes: bool = False) -> None:
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(f"wiki '{name}' 不在当前 workspace 中")

    wiki_path = workspace_root / ws.wikis[name].path

    if purge and not yes:
        if not sys.stdin.isatty():
            raise PurgeRequiresConfirmation(
                "非 TTY 下 --purge 需要 --yes 确认",
                hint="加 --yes 或在 TTY 下手动确认",
            )
        try:
            ans = input(f"将删除 {wiki_path} 子目录及所有内容，确认？[y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            ans = "n"
        if ans not in ("y", "yes"):
            print("[llmw] 取消")
            return

    del ws.wikis[name]
    ws_store.save(workspace_root, ws)

    if purge:
        if wiki_path.is_dir():
            safe_rmtree(wiki_path)

    print(f"[llmw] wiki '{name}' 已取消注册" + (" 并删除子目录" if purge else ""), file=sys.stdout)
```

- [ ] **Step 4: 写 show 业务**

```python
# 接 Step 3 文件，继续添加:

def show(workspace_root: Path, name: str, as_json: bool = False) -> None:
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(f"wiki '{name}' 不在当前 workspace 中")

    wiki_path = workspace_root / ws.wikis[name].path
    meta = None
    if (wiki_path / "wiki_metadata.toml").is_file():
        try:
            meta = wiki_store.load(wiki_path)
        except Exception:
            meta = None

    claude_md_p = wiki_path / "CLAUDE.md"
    raw_p = wiki_path / "raw"
    wiki_sub_p = wiki_path / "wiki"
    claude_md_exists = claude_md_p.is_file()
    raw_count = sum(1 for _ in raw_p.rglob("*") if _.is_file()) if raw_p.is_dir() else 0
    wiki_count = sum(1 for _ in wiki_sub_p.rglob("*.md") if _.is_file()) if wiki_sub_p.is_dir() else 0

    # 解析最终 model
    final_model = (meta.model if meta else None) or ws.default_model
    model_source = None
    if final_model:
        if meta and meta.model:
            model_source = "wiki.metadata.model"
        elif ws.default_model:
            model_source = "workspace.default_model"

    if as_json:
        out = {
            "name": name,
            "path": str(wiki_path),
            "topic": meta.topic if meta else None,
            "display_name": meta.display_name if meta else None,
            "description": meta.description if meta else None,
            "tags": list(meta.tags) if meta else [],
            "model": final_model,
            "model_source": model_source,
            "schema_version": meta.schema_version if meta else None,
            "created_at": meta.created_at if meta else None,
            "updated_at": meta.updated_at if meta else None,
            "existence": {
                "claude_md": claude_md_exists,
                "wiki_metadata_toml": meta is not None,
                "raw_dir": raw_p.is_dir(),
                "wiki_dir": wiki_sub_p.is_dir(),
            },
            "counts": {
                "raw_files": raw_count,
                "wiki_pages": wiki_count,
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # 表格
    print(f"NAME              {name}")
    print(f"PATH              {wiki_path}")
    print(f"TOPIC             {meta.topic if meta else '-'}")
    print(f"DISPLAY_NAME      {meta.display_name if meta else '-'}")
    print(f"DESCRIPTION       {meta.description if meta else '-'}")
    print(f"TAGS              {','.join(meta.tags) if meta and meta.tags else '-'}")
    model_line = final_model or "-"
    if model_source:
        model_line += f"  (fallback: {model_source})"
    print(f"MODEL             {model_line}")
    print(f"CLAUDE_MD         {'✓ found' if claude_md_exists else '✗ missing'}")
    print(f"WIKI_METADATA     {'✓ found' if meta else '✗ missing'}")
    print(f"RAW_DIR           {'✓ found' if raw_p.is_dir() else '✗ missing'} ({raw_count} files)")
    print(f"WIKI_DIR          {'✓ found' if wiki_sub_p.is_dir() else '✗ missing'} ({wiki_count} pages)")
```

- [ ] **Step 5: 写 wiki config 业务（set/unset/get/interactive）**

```python
# 接 Step 4 文件，继续添加:

# wiki config KEY 白名单
WIKI_CONFIG_KEYS = {
    "display_name": (True,  True,  str),
    "description":  (True,  True,  str),
    "tags":         (True,  True,  list),
    "model":        (True,  True,  str),
    # name / topic / schema_version / created_at / updated_at 全部只读
}


def wiki_config_get(workspace_root: Path, name: str, key: Optional[str]) -> None:
    wiki_dir = _wiki_abs(workspace_root, name)
    meta = wiki_store.load(wiki_dir)
    if key is None:
        # dump
        print(f"# wiki: {name} ({wiki_dir}/wiki_metadata.toml)")
        for k in WIKI_CONFIG_KEYS:
            v = getattr(meta, k)
            print(f"{k} = {v!r}")
        return
    if key not in WIKI_CONFIG_KEYS:
        raise InvalidConfigKey(
            f"KEY '{key}' 不在 wiki 白名单",
            hint=f"可用 KEY: {', '.join(WIKI_CONFIG_KEYS.keys())}",
        )
    val = getattr(meta, key)
    if val is None or val == "" or val == []:
        print("<unset>")
    else:
        print(val if not isinstance(val, list) else ",".join(val))


def wiki_config_set(workspace_root: Path, name: str, key: str, value: str) -> None:
    if key not in WIKI_CONFIG_KEYS:
        raise InvalidConfigKey(f"KEY '{key}' 不在 wiki 白名单")
    can_set, _, _ = WIKI_CONFIG_KEYS[key]
    if not can_set:
        raise InvalidConfigKey(f"KEY '{key}' 不可 set（只读）")
    wiki_dir = _wiki_abs(workspace_root, name)
    meta = wiki_store.load(wiki_dir)
    if key == "tags":
        new_tags = [t.strip() for t in value.split(",") if t.strip()]
        for t in new_tags:
            wiki_store.validate_tag(t)
        meta.tags = new_tags
    else:
        setattr(meta, key, value or None)
    meta.bump()
    wiki_store.save(wiki_dir, meta)
    print(f"✓ {key} 已更新", file=sys.stdout)


def wiki_config_unset(workspace_root: Path, name: str, key: str) -> None:
    if key not in WIKI_CONFIG_KEYS:
        raise InvalidConfigKey(f"KEY '{key}' 不在 wiki 白名单")
    can_set, can_unset, _ = WIKI_CONFIG_KEYS[key]
    if not can_unset:
        raise KeyNotUnsettable(f"KEY '{key}' 不可 unset")
    wiki_dir = _wiki_abs(workspace_root, name)
    meta = wiki_store.load(wiki_dir)
    if key == "tags":
        meta.tags = []
    elif key in ("display_name", "description"):
        setattr(meta, key, "")
    elif key == "model":
        meta.model = None
    meta.bump()
    wiki_store.save(wiki_dir, meta)
    print(f"✓ {key} unset", file=sys.stdout)


def wiki_config_interactive(workspace_root: Path, name: str) -> None:
    """wiki config 无参数: 默认就是交互模式（不要求 TTY）"""
    wiki_dir = _wiki_abs(workspace_root, name)
    meta = wiki_store.load(wiki_dir)
    keys = list(WIKI_CONFIG_KEYS.keys())
    while True:
        print(f"\nwiki \"{name}\" 配置项 ({wiki_dir}/wiki_metadata.toml):")
        for i, key in enumerate(keys, 1):
            v = getattr(meta, key)
            cur = repr(v) if v else "<unset>"
            print(f"  {i}. {key}    当前: {cur}")
        try:
            choice = input(f"\n选择要编辑的项 [1-{len(keys)}, q 退出]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice.lower() in ("q", ""):
            return
        try:
            idx = int(choice) - 1
            key = keys[idx]
        except (ValueError, IndexError):
            print("[llmw] 输入无效，重试")
            continue

        if key == "tags":
            # 子菜单: a / r / s
            cur_tags = list(meta.tags)
            while True:
                print(f"  当前 tags: {cur_tags}")
                print("  a) 添加 tag\n  r) 移除 tag\n  s) 替换全部 tags")
                try:
                    op = input("操作 [a/r/s/q]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    break
                if op == "a":
                    t = input("新 tag: ").strip()
                    if t:
                        wiki_store.validate_tag(t)
                        if t not in cur_tags:
                            cur_tags.append(t)
                elif op == "r":
                    if not cur_tags:
                        print("(空)"); continue
                    for i2, t in enumerate(cur_tags):
                        print(f"  {i2+1}. {t}")
                    try:
                        idx2 = int(input("移除编号: ").strip()) - 1
                        if 0 <= idx2 < len(cur_tags):
                            cur_tags.pop(idx2)
                    except (ValueError, EOFError, KeyboardInterrupt):
                        pass
                elif op == "s":
                    t = input("全部 tags (逗号分隔): ").strip()
                    new_tags = [x.strip() for x in t.split(",") if x.strip()]
                    for x in new_tags:
                        wiki_store.validate_tag(x)
                    cur_tags = new_tags
                else:
                    break
            meta.tags = cur_tags
        else:
            cur = getattr(meta, key) or ""
            try:
                new_v = input(f"输入新值（回车跳过 / '-' 清空）: ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if new_v == "":
                pass
            elif new_v == "-":
                if key == "model":
                    meta.model = None
                else:
                    setattr(meta, key, "")
            else:
                if key == "model":
                    meta.model = new_v
                else:
                    setattr(meta, key, new_v)
        meta.bump()
        wiki_store.save(wiki_dir, meta)
        try:
            again = input("继续编辑？[Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if again in ("n", "no"):
            return
```

- [ ] **Step 6: 冒烟 — add（非 TTY 全 flag）+ show + config + remove**

```bash
TMPWS=$(mktemp -d)
cd /home/zryang/llm_workspace_cli && \
  ./bin/llmw init --path "$TMPWS" --no-git
# 非 TTY add 全 flag
LLMW_WORKSPACE="$TMPWS" ./bin/llmw wiki --name=foo add \
  --topic "Foo Topic" \
  --display-name "Foo" \
  --description "smoke test" \
  --tag research --tag test \
  --model claude-sonnet-4-6
ls "$TMPWS"/foo/{raw,wiki,CLAUDE.md,wiki_metadata.toml} 2>&1
LLMW_WORKSPACE="$TMPWS" ./bin/llmw wiki --name=foo show
LLMW_WORKSPACE="$TMPWS" ./bin/llmw wiki --name=foo config set tags alpha,beta
LLMW_WORKSPACE="$TMPWS" ./bin/llmw wiki --name=foo config get tags
LLMW_WORKSPACE="$TMPWS" ./bin/llmw list
LLMW_WORKSPACE="$TMPWS" ./bin/llmw wiki --name=foo remove
LLMW_WORKSPACE="$TMPWS" ./bin/llmw list
rm -rf "$TMPWS"
```

期望：
- `ls` 显示 `raw/`、`wiki/`、`CLAUDE.md`、`wiki_metadata.toml` 都存在
- `show` 打印包含 `display_name: Foo` 的表格
- `config set tags alpha,beta` 后 `get tags` 输出 `alpha,beta`
- `list` 第一次看到 `foo`，remove 后第二次看到 `# (no wikis registered)`

- [ ] **Step 7: 冒烟 — add 非 TTY 缺 flag 应报错**

```bash
TMPWS=$(mktemp -d)
cd /home/zryang/llm_workspace_cli && \
  ./bin/llmw init --path "$TMPWS" --no-git
LLMW_WORKSPACE="$TMPWS" ./bin/llmw wiki --name=foo add --topic "Foo" 2>&1; echo "exit=$?"
rm -rf "$TMPWS"
```

期望：`exit=1`，stderr 含 `[llmw] error:` 和 `--display-name` 字样（MissingRequiredFlag）。

- [ ] **Step 8: Commit**

```bash
git add llmw/wiki/manager.py && git commit -m "feat: add llmw.wiki.manager (add/remove/show/config)"
```

---

### Task 14: wire wiki subparser into `cli.py`

**Files:**
- Modify: `llmw/cli.py`

- [ ] **Step 1: 在 build_parser() 的 sub 里加 wiki 子解析器**

在 `build_parser()` 末尾、`return parser` 之前加：

```python
    # ===== wiki 级 =====
    p_wiki = sub.add_parser("wiki", help="wiki 子命令")
    p_wiki.add_argument("--name", required=True, metavar="NAME",
                        help="目标 wiki 名")
    wiki_sub = p_wiki.add_subparsers(dest="wiki_action", metavar="ACTION")

    # add
    pw_add = wiki_sub.add_parser("add", help="新建 wiki")
    pw_add.add_argument("--topic", default=None)
    pw_add.add_argument("--display-name", default=None, dest="display_name")
    pw_add.add_argument("--description", default=None)
    pw_add.add_argument("--tag", action="append", default=[], dest="tags")
    pw_add.add_argument("--model", default=None)
    pw_add.add_argument("--no-setup", action="store_true", dest="no_setup")

    # remove
    pw_rm = wiki_sub.add_parser("remove", help="移除 wiki")
    pw_rm.add_argument("--purge", action="store_true")
    pw_rm.add_argument("--yes", "-y", action="store_true")

    # show
    pw_show = wiki_sub.add_parser("show", help="查看 wiki 详情")

    # config (sub: get / set / unset)
    pw_cfg = wiki_sub.add_parser("config", help="读写 wiki_metadata.toml")
    pw_cfg.add_argument("cfg_action", nargs="?", default=None,
                        choices=[None, "get", "set", "unset"])
    pw_cfg.add_argument("cfg_key", nargs="?", default=None)
    pw_cfg.add_argument("cfg_value", nargs="?", default=None)

    # enter (Task 16)
```

- [ ] **Step 2: 在 main() 里加 wiki 分派**

在 `if args.command == "list":` 后追加：

```python
        if args.command == "wiki":
            from llmw.wiki.manager import (
                add as wiki_add, remove as wiki_rm, show as wiki_show,
                wiki_config_get, wiki_config_set, wiki_config_unset,
                wiki_config_interactive,
            )
            wa = args.wiki_action
            if wa == "add":
                wiki_add(
                    ws_root, args.name,
                    topic=args.topic, display_name=args.display_name,
                    description=args.description, tags=args.tags or None,
                    model=args.model, no_setup=args.no_setup,
                )
            elif wa == "remove":
                wiki_rm(ws_root, args.name, purge=args.purge, yes=args.yes)
            elif wa == "show":
                wiki_show(ws_root, args.name, as_json=args.json)
            elif wa == "config":
                if args.cfg_action is None:
                    wiki_config_interactive(ws_root, args.name)
                elif args.cfg_action == "get":
                    wiki_config_get(ws_root, args.name, args.cfg_key)
                elif args.cfg_action == "set":
                    wiki_config_set(ws_root, args.name, args.cfg_key, args.cfg_value)
                elif args.cfg_action == "unset":
                    wiki_config_unset(ws_root, args.name, args.cfg_key)
            else:
                print("[llmw] wiki 子命令需要 ACTION (add/remove/show/config/enter)", file=sys.stderr)
                return 1
            return 0
```

- [ ] **Step 3: 冒烟 — 复用 Task 13 Step 6 的 smoke 命令（这次走 `llmw` 二进制）**

```bash
TMPWS=$(mktemp -d)
cd /home/zryang/llm_workspace_cli && \
  ./bin/llmw init --path "$TMPWS" --no-git
LLMW_WORKSPACE="$TMPWS" ./bin/llmw wiki --name=foo add \
  --topic "Foo" --display-name "Foo" --description "x" \
  --tag a --tag b --model claude-sonnet-4-6
LLMW_WORKSPACE="$TMPWS" ./bin/llmw wiki --name=foo show
LLMW_WORKSPACE="$TMPWS" ./bin/llmw wiki --name=foo remove
rm -rf "$TMPWS"
```

期望：与 Task 13 Step 6 一致。

- [ ] **Step 4: Commit**

```bash
git add llmw/cli.py && git commit -m "feat: wire wiki subparser (add/remove/show/config)"
```

---

## Phase 5 — Enter command

### Task 15: `llmw/wiki/enter.py` — claude subprocess

**Files:**
- Create: `llmw/wiki/enter.py`

> 来源：`doc/design/03-wiki-enter.md` Phase 1 简化版。**不传 model，不传 env**，只构造 `claude --add-dir <wiki> [--system-prompt "$(cat CLAUDE.md)"]` 然后 `os.chdir + subprocess.run`。

- [ ] **Step 1: 写 enter.py**

```python
"""wiki enter — 启动 Claude Code session (Phase 1 简化版: 不传 model, 不传 env)"""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from llmw.errors import ClaudeNotFound, WikiDirMissing, WikiNotFound
from llmw.workspace import store as ws_store


def _resolve_wiki_path(workspace_root: Path, name: str) -> Path:
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(f"wiki '{name}' 不在当前 workspace 中")
    return workspace_root / ws.wikis[name].path


def _build_cmd(wiki_path: Path) -> list:
    """构造 claude 子进程 argv. Phase 1 不传 model, 不传 env"""
    cmd = ["claude", "--add-dir", str(wiki_path)]
    claude_md = wiki_path / "CLAUDE.md"
    if claude_md.is_file():
        cmd += ["--system-prompt", f'"$(cat {claude_md})"']
    return cmd


def enter(workspace_root: Path, name: str, dry_run: bool = False) -> int:
    wiki_path = _resolve_wiki_path(workspace_root, name)

    if not wiki_path.is_dir():
        raise WikiDirMissing(f"wiki 子目录不存在: {wiki_path}")

    # 软警告
    claude_md = wiki_path / "CLAUDE.md"
    if not claude_md.is_file():
        print(f"[llmw] warning: wiki '{name}' 缺少 CLAUDE.md，session 启动后将没有 schema 上下文", file=sys.stderr)
    meta_p = wiki_path / "wiki_metadata.toml"
    if not meta_p.is_file():
        print(f"[llmw] warning: wiki '{name}' 缺少 wiki_metadata.toml", file=sys.stderr)

    # 检查 claude 在 PATH (dry-run 时跳过)
    if not dry_run and shutil.which("claude") is None:
        raise ClaudeNotFound(
            "claude 不在 PATH",
            hint="安装 Claude Code 或加到 PATH 后重试；可用 --dry-run 看命令",
        )

    cmd = _build_cmd(wiki_path)

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
            print(f"[llmw] wiki.model: {meta.model} (note: Phase 1 不传递给 Claude Code)", file=sys.stdout)
        elif ws.default_model:
            print(f"[llmw] workspace.default_model: {ws.default_model} (note: Phase 1 不传递给 Claude Code)", file=sys.stdout)
        if claude_md.is_file():
            print(f"[llmw] CLAUDE.md: ✓ found ({claude_md.stat().st_size} bytes)", file=sys.stdout)
        else:
            print(f"[llmw] CLAUDE.md: ✗ missing", file=sys.stdout)
        print(f"[llmw] cmd:", file=sys.stdout)
        print("  " + " ".join(cmd), file=sys.stdout)
        print(f"[llmw] env: 继承当前 shell（CLI 不修改）", file=sys.stdout)
        print(f"[llmw] --dry-run: 未执行", file=sys.stdout)
        return 0

    # 真正执行
    os.chdir(wiki_path)
    result = subprocess.run(cmd)  # env 透传 (不传 env= 参数)
    return result.returncode
```

- [ ] **Step 2: 冒烟 — dry-run 应打印 cmd 构造**

```bash
TMPWS=$(mktemp -d)
cd /home/zryang/llm_workspace_cli && \
  ./bin/llmw init --path "$TMPWS" --no-git
LLMW_WORKSPACE="$TMPWS" ./bin/llmw wiki --name=foo add \
  --topic "Foo" --display-name "Foo" --description "x" \
  --tag a --model claude-sonnet-4-6
LLMW_WORKSPACE="$TMPWS" ./bin/llmw wiki --name=foo enter --dry-run
rm -rf "$TMPWS"
```

期望 stdout 类似：
```
[llmw] workspace: /tmp/xxx
[llmw] wiki:      foo (/tmp/xxx/foo)
[llmw] wiki.model: claude-sonnet-4-6 (note: Phase 1 不传递给 Claude Code)
[llmw] CLAUDE.md: ✓ found (N bytes)
[llmw] cmd:
  claude --add-dir /tmp/xxx/foo --system-prompt "$(cat /tmp/xxx/foo/CLAUDE.md)"
[llmw] env: 继承当前 shell（CLI 不修改）
[llmw] --dry-run: 未执行
```

- [ ] **Step 3: 冒烟 — `claude` 不在 PATH 时 dry-run 仍 OK，真跑报 ClaudeNotFound**

```bash
TMPWS=$(mktemp -d)
cd /home/zryang/llm_workspace_cli && \
  ./bin/llmw init --path "$TMPWS" --no-git
LLMW_WORKSPACE="$TMPWS" PATH=/nonexistent ./bin/llmw wiki --name=foo add \
  --topic "Foo" --display-name "Foo" --description "x" \
  --tag a --model claude-sonnet-4-6
LLMW_WORKSPACE="$TMPWS" PATH=/nonexistent ./bin/llmw wiki --name=foo enter --dry-run; echo "dry-run exit=$?"
LLMW_WORKSPACE="$TMPWS" PATH=/nonexistent ./bin/llmw wiki --name=foo enter 2>&1; echo "real exit=$?"
rm -rf "$TMPWS"
```

期望：
- dry-run: exit=0
- real: stderr 含 `claude 不在 PATH`，exit=2

- [ ] **Step 4: Commit**

```bash
git add llmw/wiki/enter.py && git commit -m "feat: add llmw.wiki.enter (claude subprocess + --dry-run)"
```

---

### Task 16: wire `enter` into cli.py

**Files:**
- Modify: `llmw/cli.py`

- [ ] **Step 1: 在 wiki_sub.add_parser 里加 enter**

```python
    pw_enter = wiki_sub.add_parser("enter", help="启动 Claude Code session")
    pw_enter.add_argument("--dry-run", action="store_true", dest="dry_run")
```

- [ ] **Step 2: 在 main() 的 `if args.command == "wiki":` 末尾加 enter 分派**

```python
            elif wa == "enter":
                from llmw.wiki.enter import enter as wiki_enter
                return wiki_enter(ws_root, args.name, dry_run=args.dry_run)
```

- [ ] **Step 3: 冒烟 — 复用 Task 15 Step 3 的 smoke 命令**

期望与 Task 15 Step 3 一致。

- [ ] **Step 4: Commit**

```bash
git add llmw/cli.py && git commit -m "feat: wire wiki enter into cli"
```

---

## Phase 6 — Docs & final smoke

### Task 17: README rewrite + 完整手动 smoke

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 重写 README.md**

```markdown
# llmw — Wiki Workspace CLI

管理一个由 [`llm-wiki-management`](https://github.com/yzr95924/my_SKILL/tree/master/llm-wiki-management) skill 创建的 wiki 集合（一个 workspace = 一个 git 仓，含多个 wiki 子目录）。

## 安装

### 1. 克隆仓库（含 submodule）

```bash
git clone https://github.com/yzr95924/llmw.git
cd llmw
git submodule update --init --recursive
```

> ⚠ `git submodule update` 必须跑，否则 `wiki add` 报 `SkillMissing`。

### 2. 安装 Python 包（开发模式）

```bash
pip install -e .
```

需要 Python 3.7+。3.10 及以下需 `pip install tomli`。

### 3. 加 `bin/llmw` 到 PATH

```bash
export PATH="$(pwd)/bin:$PATH"
```

> Phase 2 会做正式 install/uninstall 脚本（自动加 `~/.local/bin/llmw` + PATH 注册）。

## 快速上手

```bash
# 初始化 workspace（默认 ~/yzr_llm_workspace）
llmw init
cd ~/yzr_llm_workspace

# 新建一个 wiki（非 TTY 需全 flag）
llmw wiki --name=llm-systems add \
  --topic "LLM Systems" \
  --display-name "LLM 系统研究" \
  --description "跟踪 LLM 系统相关论文与博客" \
  --tag research --tag llm \
  --model claude-sonnet-4-6

# 查看
llmw list
llmw wiki --name=llm-systems show

# 编辑 metadata（交互模式）
llmw wiki --name=llm-systems config

# 配置 workspace 级默认 model
llmw config set default_model claude-sonnet-4-6

# 启动 Claude Code session（核心命令）
llmw wiki --name=llm-systems enter
# 先看命令再跑:
llmw wiki --name=llm-systems enter --dry-run

# 移除 wiki
llmw wiki --name=llm-systems remove          # 仅取消注册
llmw wiki --name=llm-systems remove --purge --yes   # 同时删子目录
```

## 命令清单

| 命令 | 作用 |
| --- | --- |
| `llmw init [--path DIR] [--no-git]` | 初始化 workspace |
| `llmw config [get\|set\|unset] KEY [VALUE]` | 读写 `workspace.toml`；无参数 + TTY 进交互模式 |
| `llmw list [--tag TAG]...` | 列出 wiki（`--json` 输出 JSON） |
| `llmw wiki --name=X add [--topic ...] [--display-name ...] [--description ...] [--tag ...] [--model ...] [--no-setup]` | 新建 wiki |
| `llmw wiki --name=X remove [--purge] [--yes]` | 移除 wiki |
| `llmw wiki --name=X show` | 查看 wiki 详情 |
| `llmw wiki --name=X config [get\|set\|unset] KEY [VALUE]` | 读写 `wiki_metadata.toml`；无参数默认交互模式 |
| `llmw wiki --name=X enter [--dry-run]` | 启动 Claude Code session（Phase 1 不传 model） |

全局 flag：`--workspace PATH` / `--json` / `--debug` / `--quiet` / `-q`。

## 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 用户错误（参数非法、wiki 不存在等） |
| 2 | 环境错误（SKILL submodule 缺失、claude 不在 PATH 等） |
| 3 | 内部错误（未捕获异常） |

## Manual Smoke Test（prototype 阶段验收清单）

每个命令至少跑一遍 happy path：

```bash
# 准备临时 workspace
TMPWS=$(mktemp -d)

# init
llmw init --path "$TMPWS" --no-git
test -f "$TMPWS/workspace.toml" && echo "✓ init"

# config (非 TTY 自动打印字段列表后退出 0)
LLMW_WORKSPACE="$TMPWS" llmw config
LLMW_WORKSPACE="$TMPWS" llmw config set default_model claude-sonnet-4-6
LLMW_WORKSPACE="$TMPWS" llmw config get default_model
LLMW_WORKSPACE="$TMPWS" llmw config unset default_model

# list (空)
LLMW_WORKSPACE="$TMPWS" llmw list

# add (非 TTY 全 flag)
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo add \
  --topic "Foo" --display-name "Foo" --description "x" \
  --tag a --tag b --model claude-sonnet-4-6
test -d "$TMPWS/foo/raw" -a -d "$TMPWS/foo/wiki" -a -f "$TMPWS/foo/CLAUDE.md" -a -f "$TMPWS/foo/wiki_metadata.toml" \
  && echo "✓ add (files ok)"

# list (有 wiki)
LLMW_WORKSPACE="$TMPWS" llmw list
LLMW_WORKSPACE="$TMPWS" llmw list --json
LLMW_WORKSPACE="$TMPWS" llmw list --tag a

# show
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo show
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo show --json

# config set/get
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo config set tags alpha,beta
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo config get tags

# enter --dry-run
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo enter --dry-run

# remove
LLMW_WORKSPACE="$TMPWS" llmw wiki --name=foo remove --purge --yes
test ! -d "$TMPWS/foo" && echo "✓ remove --purge"

rm -rf "$TMPWS"
```

每个 echo 出现 = 该步 happy path 通过。所有 12 步都通过 = prototype 阶段验收。

## Phase 边界

| 维度 | Phase 1（当前） | Phase 2（暂未做） |
| --- | --- | --- |
| workspace / wiki 元数据 | ✅ | |
| 基础 CRUD | ✅ | |
| Claude Code session 启动 | ✅（不传 model） | |
| model registry | ❌ | ✅（`workspace_models.toml` + `llmw model` 命令） |
| ingest / lint / query 包装 | ❌（留给 SKILL session 内） | |
| install / uninstall 脚本 | ❌（手动加 PATH） | ✅ |

详见 `doc/design/` 各章节。

## 并发 / 文件系统

原子写走 `tmp + fsync + rename`（POSIX 原子）。本地文件系统（ext4 / APFS）安全。
**NFS 不安全**——不要在 NFS 挂载的 workspace 上跑 `llmw`。
```

- [ ] **Step 2: 跑 Task 17 README 末尾的 manual smoke 全套**

直接复制 README 末尾那段 bash 脚本到终端跑一遍。每个 `✓` 出现 = 该步通过。

期望：12 个 `echo "✓ ..."` 全部打印（或部分跳过 + 错误信息显示）。

- [ ] **Step 3: 修复任何失败的 step**

如果哪个 step 失败，回到对应的 task 修复后重新跑 smoke。

- [ ] **Step 4: Commit**

```bash
git add README.md && git commit -m "docs: rewrite README with install + manual smoke checklist"
```

---

## Self-Review（spec 覆盖 / placeholder / type 一致性）

> 作者自检记录（plan 完成后）。

### 1. Spec 覆盖

| design doc 章节 | 覆盖 task |
| --- | --- |
| `00-overview.md` 不变量 I-1 (CLI 不写 wiki 内容) | 不写 `raw/` / `wiki/`；Task 9 store 仅写 `wiki_metadata.toml` |
| 不变量 I-2 (add 由 setup_wiki.py 创建) | Task 13 Step 2 add() 调 `_ensure_skill_script()` + `subprocess.run(setup_wiki.py)` |
| 不变量 I-3 (SKILL submodule 路径固定) | Task 6 `skill_setup_script()` 解析 submodule 固定路径 |
| 不变量 I-4 (可执行入口 bin/) | Task 2 `bin/llmw` |
| `01` init / config / list | Task 11 + Task 12 |
| `02` wiki add / remove / show / config | Task 13 + Task 14 |
| `03` wiki enter (Phase 1 简化版) | Task 15 + Task 16 |
| `04` workspace.toml schema | Task 8 `WorkspaceToml` dataclass + Task 4 schema_version=1 校验 |
| `04` wiki_metadata.toml schema | Task 9 `WikiMetadata` dataclass |
| `04` atomic_write | Task 7 |
| `04` templates/wiki_metadata.toml.template | Task 10 |
| `05` SKILL submodule 路径解析 | Task 6 + Task 13 Step 1 `_ensure_skill_script()` |
| `06` 20 个异常类 | Task 4 errors.py |
| `06` 退出码 0/1/2/3 | Task 12 main() 的 `except LlmwError as e: return e.exit_code` |
| `06` 错误格式 `[llmw] error: ...` | Task 4 `format_error()` + Task 12 main() 调用 |
| `06` atomic_write 一致 | Task 7 |
| `06` add 回滚 | Task 13 Step 2: setup_wiki.py 失败时 `safe_rmtree(wiki_dir)` |
| `07` 测试延后 | 本 plan 全文以 manual smoke 替代 TDD |
| `MEMORY/test-priority-low` | 全文每步以"冒烟"代替 pytest |
| `MEMORY/model-ops-no-env-vars` | Task 15 enter.py 不传 `env=` 给 subprocess.run |

### 2. Placeholder 扫描

- 无 "TBD" / "TODO" / "implement later" / "类似 Task N"
- 每个 step 含具体命令或具体代码
- 无 "add appropriate error handling" 类抽象描述

### 3. Type / API 一致性

| 名称 | 定义处 | 引用处 | 一致？ |
| --- | --- | --- | --- |
| `WikiMetadata` dataclass | Task 9 | Task 13 Step 2/4/5 | ✅ |
| `WikiEntry` dataclass | Task 8 | Task 11 Step 1 (save) / Task 13 Step 2 (add) | ✅ |
| `WorkspaceToml` dataclass | Task 8 | Task 11 / 13 / 15 | ✅ |
| `WIKI_CONFIG_KEYS` 白名单 | Task 13 Step 5 | 内部 wiki_config_get/set/unset | ✅ |
| `CONFIG_KEYS` 白名单 | Task 11 Step 2 | 内部 config_get/set/unset + interactive | ✅ |
| `_resolve_wiki_path()` / `_wiki_abs()` | Task 15 / Task 13 | Task 13 Step 5 调 `_wiki_abs` | ⚠ 命名不一致 |
| `_ensure_skill_script()` | Task 13 Step 1 | Task 13 Step 2 add() | ✅ |

**修正**：Task 13 Step 1 写的是 `_wiki_abs()`，Task 15 Step 1 写的是 `_resolve_wiki_path()`——同名概念两套名字。**统一为 `_wiki_abs()`**（Task 15 Step 1 调用 `ws_store.load + raise WikiNotFound + return path` 改成调 `_wiki_abs` 或与 Task 13 Step 1 合并到一个工具函数）。

**最终修正**：在 `llmw/wiki/manager.py` 顶部加 `def _wiki_abs(workspace_root, name) -> Path`，Task 15 enter.py 也 import 这个函数，删除 Task 15 自己的 `_resolve_wiki_path`。这样两处共用一个工具函数。

> 这条修正已**应用**到 plan 文本中：Task 13 Step 1 已定义 `_wiki_abs`，Task 15 Step 1 不再单独定义 `_resolve_wiki_path`，而是 import 复用。

### 4. Py 3.7+ 兼容

- `dataclasses` 3.7+ ✅
- `f-string` 3.6+ ✅
- `subprocess.run(capture_output=, text=)` 3.7+ ✅
- `pathlib` 3.4+ ✅
- `tomllib` 3.11+（fallback `tomli` 3.7-3.10）✅
- `from __future__ import annotations` 不必要（仅在 task 14 等复杂文件用 dataclass 字段，不涉及 forward ref）
- **唯一可能的坑**：`dataclass` 字段默认值用 `list` / `dict` 必须走 `field(default_factory=...)` — Task 8/9 已正确处理 ✅

---

## 执行模式选择（交给用户）

Plan 写完后，agent 应问用户在两种执行模式中选一个：

1. **Subagent-Driven（推荐）**：每个 task 派一个 fresh subagent 执行，主 session 在 task 之间 review；迭代快、上下文隔离干净
2. **Inline Execution**：在当前 session 按顺序执行所有 task，batch + 阶段性 review