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
