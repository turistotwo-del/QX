"""Opt-in migration of QX 3.3.x portable price/settings files.

A ZIP is treated as untrusted input.  Only two JSON resources are read, never
extracted. The running project, tender SQLite and equipment catalog are not
modified. Import is explicitly confirmed and original target bytes are saved
before replacement. Roll back both files if an individual replacement fails.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json
import os
import re
import tempfile
import threading
import uuid
import zipfile

from core import storage
from modern import tender_store

MAX_ZIP_SIZE = 60 * 1024 * 1024
MAX_ENTRIES = 3500
MAX_JSON = 512 * 1024
MIGRATE = {'prices': 'qx_prices.json', 'settings': 'settings.json'}
_LOCK = threading.Lock()


def _read_json(source: bytes, label: str) -> dict:
    if not source or len(source) > MAX_JSON:
        raise ValueError(f'{label}: размер файла превышает 512 КБ или файл пуст')
    try:
        value = json.loads(source.decode('utf-8-sig'),
                           parse_constant=lambda v: (_ for _ in ()).throw(ValueError('Некорректное число: '+v)))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f'{label}: неверный формат JSON') from exc
    if not isinstance(value, dict):
        raise ValueError(f'{label}: ожидался объект JSON')
    if len(value) > 1500:
        raise ValueError(f'{label}: слишком много параметров')
    # Must be serializable to a strict JSON document (not special floats).
    json.dumps(value, ensure_ascii=False, allow_nan=False)
    if label == 'prices':
        if not value or not all(isinstance(v, dict) and isinstance(v.get('price', 0), (int,float,str))
                                for v in value.values()):
            raise ValueError('Прайс не похож на файл QX: ожидаются позиции с параметрами')
        if not any(key in value for key in storage.DEFAULT_QX_PRICES):
            raise ValueError('В архиве не распознаны позиции прайса QX')
    else:
        if not any(k in value for k in storage.DEFAULT_SETTINGS):
            raise ValueError('Не распознаны настройки QX')
    return value


def _extract(zip_data: bytes) -> dict[str, dict]:
    if not zip_data or len(zip_data) > MAX_ZIP_SIZE:
        raise ValueError('ZIP старой версии QX пуст или превышает 60 МБ')
    try:
        with zipfile.ZipFile(BytesIO(zip_data)) as z:
            if len(z.infolist()) > MAX_ENTRIES:
                raise ValueError('В ZIP слишком много файлов')
            found: dict[str, str] = {}
            seen: set[str] = set()
            for info in z.infolist():
                name = info.filename.replace('\\', '/')
                if info.filename != name or name.startswith('/') or any(p in ('.','..') for p in name.split('/')):
                    raise ValueError('В архиве небезопасные пути')
                if name in seen:
                    raise ValueError('В архиве повторяются имена файлов')
                seen.add(name)
                # Portable QX source ZIP may have a single enclosing directory.
                # Match only data/<name>, never another folder named data deeper
                # inside an arbitrary nested distribution.
                parts = name.split('/')
                if len(parts) in (2,3) and parts[-2] == 'data' and parts[-1] in MIGRATE.values():
                    key = 'prices' if parts[-1] == MIGRATE['prices'] else 'settings'
                    if key in found:
                        raise ValueError(f'Найдено несколько файлов {MIGRATE[key]}; выбор неоднозначен')
                    if info.is_dir() or info.file_size > MAX_JSON or info.file_size == 0:
                        raise ValueError(f'{parts[-1]}: файл слишком большой или пуст')
                    found[key] = info.filename
            if not found:
                raise ValueError('В ZIP не найдены data/qx_prices.json или data/settings.json')
            return {key: _read_json(z.read(name), key) for key, name in found.items()}
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError('Не удалось прочитать ZIP старого QX') from exc


def _preview_changes(path: Path, imported: dict) -> dict:
    # Read-only comparison: do NOT call load_prices/load_settings here because
    # legacy storage creates or quarantines files as a side effect.
    if not path.is_file():
        return {'changed':len(imported),'comparison':'Нет текущего файла'}
    try:
        current=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(current,dict):raise ValueError('Invalid file')
        return {'changed':sum(1 for k,v in imported.items() if current.get(k)!=v),
                'comparison':'По текущему файлу'}
    except (ValueError,UnicodeError,OSError):
        return {'changed':None,'comparison':'Текущий файл не удалось сравнить; исходник будет сохранён'}


def preview_legacy(zip_data: bytes) -> dict:
    old = _extract(zip_data)
    return {
        'prices': {'found': 'prices' in old, 'positions': len(old.get('prices', {})),
                   'target_exists': storage.PRICES_FILE.exists(),
                   **(_preview_changes(storage.PRICES_FILE,old['prices']) if 'prices' in old else {})},
        'settings': {'found': 'settings' in old, 'parameters': len(old.get('settings', {})),
                     'target_exists': storage.SETTINGS_FILE.exists(),
                     **(_preview_changes(storage.SETTINGS_FILE,old['settings']) if 'settings' in old else {})},
        'warning': ('Перенос заменяет только прайс и настройки. Закупки, текущий расчёт и базы оборудования '
                    'не меняются. Для пользовательского каталога QX 3.3.7 используется прежняя папка QX_Selector.'),
    }


def _atomic_raw(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.'+path.name+'.', suffix='.importing', dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)


def import_legacy(zip_data: bytes) -> dict:
    if not _LOCK.acquire(blocking=False):
        raise ValueError('Импорт предыдущей версии уже выполняется')
    try:
        values = _extract(zip_data)  # Validate everything before modifying data.
        paths = {'prices': storage.PRICES_FILE, 'settings': storage.SETTINGS_FILE}
        # Convert to canonical UTF-8 strict JSON. Keep unknown legacy keys in the
        # source archive but import only recognised settings; price maps are merged
        # with new QX positions to keep the application usable after migration.
        replacement = {}
        if 'prices' in values:
            merged = storage.normalize_prices(values['prices'])
            replacement['prices'] = json.dumps(merged, ensure_ascii=False, indent=2,
                                              allow_nan=False).encode('utf-8')
        if 'settings' in values:
            merged = dict(storage.DEFAULT_SETTINGS)
            merged.update({k:v for k,v in values['settings'].items() if k in merged})
            replacement['settings'] = json.dumps(merged, ensure_ascii=False, indent=2,
                                                allow_nan=False).encode('utf-8')
        for k in replacement:
            if paths[k].is_symlink():
                raise ValueError('Целевой файл является символической ссылкой: импорт остановлен')
        directory = tender_store.APP_DATA / 'legacy_import_snapshots'
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        snapshot = directory / f'QX_Legacy_Import_{stamp}_{uuid.uuid4().hex[:8]}'
        snapshot.mkdir()
        originals = {k: (paths[k].read_bytes() if paths[k].exists() else None) for k in replacement}
        try:
            # Backups are written and fsynced before any destination changes.
            for k, original in originals.items():
                if original is not None:
                    _atomic_raw(snapshot / MIGRATE[k], original)
            # Marker lets support distinguish "there was no prior target" from
            # an incomplete snapshot; no client data values go into it.
            _atomic_raw(snapshot/'manifest.json',json.dumps({
                'format':'QX-Legacy-Import-Snapshot','created_utc':stamp,
                'previous_files':[MIGRATE[k] for k,v in originals.items() if v is not None],
                'created_files':[MIGRATE[k] for k,v in originals.items() if v is None],
            },ensure_ascii=False,indent=2).encode('utf-8'))
            changed = []
            try:
                for key, contents in replacement.items():
                    _atomic_raw(paths[key], contents)
                    changed.append(key)
            except Exception:
                for key in reversed(changed):
                    if originals[key] is None:
                        paths[key].unlink(missing_ok=True)
                    else:
                        _atomic_raw(paths[key], originals[key])
                raise
        except Exception:
            # Do not delete any potentially useful snapshot on failure.
            raise
        return {'imported':list(replacement), 'snapshot':str(snapshot),
                'positions':len(values.get('prices',{})),
                'settings':len(values.get('settings',{}))}
    finally:
        _LOCK.release()
