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
    arrays = []
    tables = {}
    for k, v in data.items():
        if isinstance(v, dict):
            tables[k] = v
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            # array-of-tables: [[prefix.k]]
            arrays.append((k, v))
        else:
            scalars[k] = v
    # 先写 scalars，再写 array-of-tables，最后写 tables（保持正确 TOML 解析顺序）
    _dump_kv(buf, scalars.items())
    for k, items in arrays:
        for item in items:
            buf.write(f"\n[[{prefix}{k}]]\n")
            _dump_kv(buf, item.items())
    for k, v in tables.items():
        buf.write(f"\n[{prefix}{k}]\n")
        _dump_section(buf, v, prefix=f"{prefix}{k}.")


# TOML basic string 必要转义: 反斜杠 / 双引号 / 控制字符。
# 手写 dump 必须转义, 否则含 \ 或 " 的值会产出非法 TOML, 紧接着的 load 即炸
# (TOMLDecodeError: Unescaped '\' in a string)。
_BASIC_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",  # U+0008
    "\t": "\\t",  # U+0009
    "\n": "\\n",  # U+000A
    "\f": "\\f",  # U+000C
    "\r": "\\r",  # U+000D
}


def _toml_escape_str(s: str) -> str:
    """转义为合法 TOML basic string 内容（不含两侧双引号）。
    逐字符处理, 天然避免二次转义; 其余控制字符 (U+0000..U+001F 除已列举) 用 \\uXXXX。
    """
    out = []
    for ch in s:
        if ch in _BASIC_ESCAPES:
            out.append(_BASIC_ESCAPES[ch])
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def _dump_kv(buf, items):
    for k, v in items:
        if isinstance(v, str):
            buf.write(f'{k} = "{_toml_escape_str(v)}"\n')
        elif isinstance(v, bool):
            buf.write(f"{k} = {str(v).lower()}\n")
        elif isinstance(v, list):
            inner = ", ".join(
                f'"{_toml_escape_str(x)}"'
                if isinstance(x, str)
                else (str(x).lower() if isinstance(x, bool) else str(x))
                for x in v
            )
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
        raise ImportError("Python <3.11 需要 tomli 包: pip install 'tomli>=1.1'") from e
    toml_dump = _toml_dump  # noqa: F401


PYTHON_VERSION = sys.version_info
