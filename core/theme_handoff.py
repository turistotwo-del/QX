from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

HANDOFF_FORMAT = 'QX_THEME_HANDOFF'
HANDOFF_SCHEMA = 1


def save_handoff(path: Path | str, *, target_theme: str, project_bytes: bytes, ui_state: Dict[str, Any] | None = None) -> None:
    """Atomically write a short-lived UI/project snapshot used only while switching theme."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'format': HANDOFF_FORMAT,
        'schema': HANDOFF_SCHEMA,
        'created_at_epoch': time.time(),
        'target_theme': 'light' if str(target_theme).lower() == 'light' else 'dark',
        'project_base64': base64.b64encode(project_bytes or b'').decode('ascii'),
        'ui_state': dict(ui_state or {}),
    }
    tmp = p.with_name(p.name + f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, p)


def load_handoff(path: Path | str, *, current_theme: str | None = None, max_age_seconds: float = 300.0,
                 consume: bool = True) -> Optional[Dict[str, Any]]:
    """Read a handoff only for the target theme. Stale/corrupt handoffs are discarded."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(obj, dict) or obj.get('format') != HANDOFF_FORMAT:
            raise ValueError('bad handoff format')
        if int(obj.get('schema') or 0) > HANDOFF_SCHEMA:
            raise ValueError('unsupported handoff schema')
        age = max(0.0, time.time() - float(obj.get('created_at_epoch') or 0.0))
        if age > float(max_age_seconds):
            if consume:
                p.unlink(missing_ok=True)
            return None
        target = 'light' if str(obj.get('target_theme')).lower() == 'light' else 'dark'
        if current_theme is not None:
            current = 'light' if str(current_theme).lower() == 'light' else 'dark'
            if current != target:
                return None
        raw = base64.b64decode(str(obj.get('project_base64') or ''))
        result = {
            'target_theme': target,
            'project_bytes': raw,
            'ui_state': dict(obj.get('ui_state') or {}),
            'age_seconds': age,
        }
        if consume:
            p.unlink(missing_ok=True)
        return result
    except Exception:
        try:
            if consume:
                p.unlink(missing_ok=True)
        except Exception:
            pass
        return None
