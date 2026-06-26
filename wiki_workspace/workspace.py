"""workspace 路径解析、TOML 读写、原子持久化。"""

import os
import tempfile
from pathlib import Path


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
