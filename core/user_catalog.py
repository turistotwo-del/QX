import json
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


APP_ROOT = Path(__file__).resolve().parents[1]
# In a frozen installer, application resources live under _MEIPASS / Program
# Files and MUST be treated as immutable. The portable snapshot is moved to
# per-user app data instead of being silently discarded during upgrades.
if getattr(__import__('sys'), 'frozen', False) or os.environ.get('QX_PORTABLE_DATA_DIR'):
    _user_root = Path(os.environ.get('QX_DATA_DIR') or
                      (Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'QXPodborshchik'))
    PORTABLE_DATA_DIR = Path(os.environ['QX_PORTABLE_DATA_DIR']) if os.environ.get('QX_PORTABLE_DATA_DIR') else _user_root / 'QX_UserData'
else:
    PORTABLE_DATA_DIR = APP_ROOT / 'QX_UserData'
PORTABLE_DB = PORTABLE_DATA_DIR / 'QX_UserCatalog.qxdb'



def _base_dir() -> Path:
    """Stable per-user data directory that survives replacing/updating the app folder."""
    # Test/process-local override only. Normal installations keep the legacy
    # QX_Selector location so existing user databases remain compatible.
    if os.environ.get('QX_CATALOG_DIR'):
        return Path(os.environ['QX_CATALOG_DIR'])
    root = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
    if root:
        return Path(root) / 'QX_Selector'
    return Path.home() / '.qx_selector'


USER_DATA_DIR = _base_dir()
CATALOG_DB = USER_DATA_DIR / 'user_catalog.sqlite3'


_SCHEMA = '''
CREATE TABLE IF NOT EXISTS catalog_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(kind, name)
)
'''


def _ensure_schema(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # sqlite3.Connection.__enter__/__exit__ commits/rolls back but does NOT
    # close the file handle. On Windows that can keep a .qxdb/.tmp file locked.
    with closing(sqlite3.connect(str(path), timeout=10)) as conn:
        conn.execute(_SCHEMA)
        conn.commit()


def _connect() -> sqlite3.Connection:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CATALOG_DB), timeout=10)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def _rows(path: Path) -> Dict[tuple, tuple]:
    if not path.exists():
        return {}
    # Do not call _ensure_schema() here: a portable database may legitimately
    # live in a read-only folder. Reading it must still work.
    with closing(sqlite3.connect(str(path), timeout=10)) as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog_items'"
        ).fetchone()
        if not exists:
            return {}
        rows = conn.execute(
            'SELECT kind, name, data_json, created_at, updated_at FROM catalog_items'
        ).fetchall()
    return {(r[0], str(r[1]).casefold()): r for r in rows}


def _upsert_rows(path: Path, rows) -> None:
    _ensure_schema(path)
    with closing(sqlite3.connect(str(path), timeout=10)) as conn:
        for kind, name, data_json, created_at, updated_at in rows:
            conn.execute(
                '''
                INSERT INTO catalog_items(kind, name, data_json, created_at, updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(kind, name) DO UPDATE SET
                    data_json=excluded.data_json,
                    created_at=CASE
                        WHEN catalog_items.created_at < excluded.created_at THEN catalog_items.created_at
                        ELSE excluded.created_at
                    END,
                    updated_at=excluded.updated_at
                ''',
                (kind, name, data_json, created_at, updated_at),
            )
        conn.commit()


def _snapshot(src: Path, dst: Path) -> None:
    """Create a consistent standalone SQLite copy even if source uses WAL.

    Important on Windows: every sqlite connection is explicitly CLOSED before
    os.replace(). A normal ``with sqlite3.connect(...)`` does not close the
    underlying handle and caused WinError 32 (file is used by another process).
    A unique temp file is used as well, so rapid Streamlit reruns cannot fight
    over the same ``QX_UserCatalog.qxdb.tmp`` path.
    """
    if not src.exists():
        _ensure_schema(src)
    dst.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f'.{dst.name}.', suffix='.tmp', dir=str(dst.parent)
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        # Remove the zero-byte placeholder so sqlite creates a clean DB itself.
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass

        with closing(sqlite3.connect(str(src), timeout=10)) as source:
            with closing(sqlite3.connect(str(tmp), timeout=10)) as target:
                source.backup(target)
                target.commit()

        # On Windows antivirus/indexers can briefly grab the just-created file.
        # Retry a few times instead of immediately showing a scary error.
        last_exc = None
        for attempt in range(5):
            try:
                os.replace(str(tmp), str(dst))
                last_exc = None
                break
            except PermissionError as exc:
                last_exc = exc
                time.sleep(0.08 * (attempt + 1))
        if last_exc is not None:
            raise last_exc
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def _is_newer(a: tuple, b: tuple) -> bool:
    # updated_at is ISO-8601 to seconds, therefore lexical comparison is chronological.
    return str(a[4] or '') > str(b[4] or '')


def _publish_portable() -> bool:
    """Overwrite the portable snapshot from the authoritative local DB."""
    try:
        _snapshot(CATALOG_DB, PORTABLE_DB)
        return True
    except Exception:
        return False


def sync_catalogs() -> Dict[str, object]:
    """
    Merge the stable local database and the portable copy next to the program.

    Same-PC updates keep working through LOCALAPPDATA. Copying the whole program folder to
    another PC carries QX_UserData/QX_UserCatalog.qxdb; at startup it is merged automatically.
    Newer duplicate records win by updated_at.
    """
    _ensure_schema(CATALOG_DB)
    portable_ok = True
    imported = 0
    exported = False

    try:
        if PORTABLE_DB.exists():
            local_rows = _rows(CATALOG_DB)
            portable_rows = _rows(PORTABLE_DB)
            to_local = []
            for key, prow in portable_rows.items():
                lrow = local_rows.get(key)
                if lrow is None or _is_newer(prow, lrow):
                    to_local.append(prow)
            if to_local:
                _upsert_rows(CATALOG_DB, to_local)
                imported = len(to_local)

        # Always refresh the portable copy from the now-merged local catalog.
        exported = _publish_portable()
        if not exported:
            portable_ok = False
    except Exception:
        # The app may live in a read-only location. Local AppData remains fully functional.
        portable_ok = False

    return {
        'local_path': str(CATALOG_DB),
        'portable_path': str(PORTABLE_DB),
        'portable_ok': portable_ok,
        'imported': imported,
        'exported': exported,
    }


def catalog_path() -> str:
    return str(CATALOG_DB)


def portable_catalog_path() -> str:
    return str(PORTABLE_DB)


def catalog_status() -> Dict[str, object]:
    return sync_catalogs()


def list_items(kind: str) -> List[Dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            'SELECT name, data_json, created_at, updated_at FROM catalog_items WHERE kind=? ORDER BY name COLLATE NOCASE',
            (kind,),
        ).fetchall()
    out = []
    for name, data_json, created_at, updated_at in rows:
        try:
            data = json.loads(data_json)
        except Exception:
            data = {}
        out.append({'name': name, 'data': data, 'created_at': created_at, 'updated_at': updated_at})
    return out


def get_item(kind: str, name: str) -> Optional[Dict]:
    if not str(name or '').strip():
        return None
    with closing(_connect()) as conn:
        row = conn.execute(
            'SELECT name, data_json, created_at, updated_at FROM catalog_items WHERE kind=? AND name=? COLLATE NOCASE',
            (kind, str(name).strip()),
        ).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row[1])
    except Exception:
        data = {}
    return {'name': row[0], 'data': data, 'created_at': row[2], 'updated_at': row[3]}


def save_item(kind: str, name: str, data: Dict) -> None:
    name = str(name or '').strip()
    if not name:
        raise ValueError('Название не может быть пустым.')
    now = datetime.now().isoformat(timespec='seconds')
    payload = json.dumps(dict(data or {}), ensure_ascii=False, sort_keys=True)
    with closing(_connect()) as conn:
        conn.execute(
            '''
            INSERT INTO catalog_items(kind, name, data_json, created_at, updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(kind, name) DO UPDATE SET
                data_json=excluded.data_json,
                updated_at=excluded.updated_at
            ''',
            (kind, name, payload, now, now),
        )
        conn.commit()
    _publish_portable()


def delete_item(kind: str, name: str) -> bool:
    with closing(_connect()) as conn:
        cur = conn.execute(
            'DELETE FROM catalog_items WHERE kind=? AND name=? COLLATE NOCASE',
            (kind, str(name or '').strip()),
        )
        conn.commit()
        changed = cur.rowcount > 0
    if changed:
        _publish_portable()
    return changed


def export_catalog_bytes() -> bytes:
    """Return a fresh consistent .qxdb snapshot independent of app-folder access.

    Export must work even when the program itself lives in Program Files, a
    read-only network folder, or the portable copy is temporarily locked.
    """
    _ensure_schema(CATALOG_DB)
    with tempfile.TemporaryDirectory(prefix='qx_catalog_export_') as td:
        p = Path(td) / 'QX_UserCatalog.qxdb'
        _snapshot(CATALOG_DB, p)
        return p.read_bytes()


def _validate_db(path: Path) -> None:
    with closing(sqlite3.connect(str(path), timeout=10)) as conn:
        integrity = conn.execute('PRAGMA integrity_check').fetchone()
        if not integrity or str(integrity[0]).lower() != 'ok':
            raise ValueError('Файл базы повреждён: integrity_check не пройден.')
        cols = [r[1] for r in conn.execute('PRAGMA table_info(catalog_items)').fetchall()]
        required = {'kind', 'name', 'data_json', 'created_at', 'updated_at'}
        if not required.issubset(set(cols)):
            raise ValueError('Это не база пользовательского каталога QX или формат слишком старый.')


def import_catalog_bytes(blob: bytes) -> int:
    """Merge an exported .qxdb into the local database. Newer records win."""
    if not blob:
        raise ValueError('Пустой файл базы.')
    with tempfile.TemporaryDirectory(prefix='qx_import_') as td:
        incoming = Path(td) / 'incoming.qxdb'
        incoming.write_bytes(blob)
        _validate_db(incoming)
        incoming_rows = _rows(incoming)

    local_rows = _rows(CATALOG_DB)
    to_local = []
    for key, row in incoming_rows.items():
        current = local_rows.get(key)
        if current is None or _is_newer(row, current) or row[2] != current[2]:
            # If timestamps are equal but payload differs, prefer explicit import.
            to_local.append(row)
    if to_local:
        _upsert_rows(CATALOG_DB, to_local)
    _publish_portable()
    return len(to_local)
