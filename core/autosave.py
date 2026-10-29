from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from .user_catalog import USER_DATA_DIR, PORTABLE_DATA_DIR

LOCAL_AUTOSAVE = USER_DATA_DIR / 'autosave.qxproj'
PORTABLE_AUTOSAVE = PORTABLE_DATA_DIR / 'autosave.qxproj'


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(data)
    os.replace(str(tmp), str(path))


def save_autosave(data: bytes) -> dict:
    if not data:
        return {'local': False, 'portable': False}
    local_ok = portable_ok = False
    try:
        _atomic_write(LOCAL_AUTOSAVE, data)
        local_ok = True
    except Exception:
        pass
    try:
        _atomic_write(PORTABLE_AUTOSAVE, data)
        portable_ok = True
    except Exception:
        pass
    return {'local': local_ok, 'portable': portable_ok}


def _best_path() -> Path | None:
    candidates = [p for p in (LOCAL_AUTOSAVE, PORTABLE_AUTOSAVE) if p.exists() and p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def autosave_info() -> dict | None:
    path = _best_path()
    if not path:
        return None
    stat = path.stat()
    return {
        'path': str(path),
        'size': int(stat.st_size),
        'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
    }


def load_autosave() -> bytes | None:
    path = _best_path()
    if not path:
        return None
    try:
        return path.read_bytes()
    except Exception:
        return None


def delete_autosave() -> None:
    for path in (LOCAL_AUTOSAVE, PORTABLE_AUTOSAVE):
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
