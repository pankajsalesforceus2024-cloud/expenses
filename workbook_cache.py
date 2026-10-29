from __future__ import annotations

import threading
from pathlib import Path

import pandas as pd

_lock = threading.Lock()
_cache: dict[str, tuple[tuple[int, int], dict[str, pd.DataFrame]]] = {}


def cached_sheets(workbook: Path) -> dict[str, pd.DataFrame]:
    """Parse every sheet once per file version; the key changes whenever the file is saved."""
    stat = workbook.stat()
    version = (stat.st_mtime_ns, stat.st_size)
    key = str(workbook)
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == version:
            return hit[1]
        sheets = pd.read_excel(workbook, sheet_name=None, header=None)
        _cache.clear()
        _cache[key] = (version, sheets)
        return sheets
