import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .defaults import DEFAULT_QX_PRICES, DEFAULT_SETTINGS

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = (Path(os.environ['QX_DATA_DIR']) if os.environ.get('QX_DATA_DIR') else (Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'QXPodborshchik') if getattr(sys,'frozen',False) else ROOT / 'data')
PRICES_FILE = DATA_DIR / 'qx_prices.json'
SETTINGS_FILE = DATA_DIR / 'settings.json'


def _atomic_json_write(path: Path, data) -> None:
    """Never truncate the last good user price list on interruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix='.'+path.name+'.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            Path(temp_name).unlink(missing_ok=True)
        except OSError:
            pass


def _read_or_create(path: Path, default):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # First install: seed bundled QX defaults, not a file in Program Files.
        package_copy = ROOT / 'data' / path.name
        if package_copy.exists() and package_copy != path:
            try:
                existing = json.loads(package_copy.read_text(encoding='utf-8'))
                if isinstance(existing, dict): default = existing
            except (OSError, ValueError): pass
        _atomic_json_write(path, default)
        return json.loads(json.dumps(default))
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError('Ожидался словарь JSON')
        return value
    except (ValueError, UnicodeError) as exc:
        # A damaged JSON document may contain months of user-edited prices.
        # Never overwrite its only copy. Retain the exact bytes for recovery.
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        quarantine = path.with_name(path.name+'.corrupt-'+stamp+'-'+uuid.uuid4().hex[:8])
        try:
            os.replace(path, quarantine)
        except OSError as error:
            raise RuntimeError('Повреждённый файл QX нельзя сохранить для восстановления: '+str(path)) from error
        _atomic_json_write(path, default)
        try:
            with (DATA_DIR/'QX_DATA_RECOVERY.log').open('a',encoding='utf-8') as log:
                log.write(f'{stamp} {path.name}: сохранена повреждённая копия {quarantine.name}; '+
                          f'причина: {type(exc).__name__}\n')
        except OSError:
            pass
        return json.loads(json.dumps(default))


def normalize_prices(current):
    """Complete legacy/project price maps without destroying user-edited values.

    New QX components (notably AMD M.2 Key E adapter) were absent in older
    .qxproj files. A selection must never crash because one price key is missing.
    This function does not write to disk or mutate the supplied dictionary.
    """
    merged = json.loads(json.dumps(DEFAULT_QX_PRICES))
    if not isinstance(current, dict):
        return merged
    for key, value in current.items():
        if key in DEFAULT_QX_PRICES:
            if isinstance(value, dict):
                merged[key].update({k: v for k, v in value.items() if v is not None})
                if not str(merged[key].get('name') or '').strip():
                    merged[key]['name'] = DEFAULT_QX_PRICES[key]['name']
                try:
                    merged[key]['price'] = float(merged[key].get('price', 0))
                except (ValueError, TypeError, OverflowError):
                    merged[key]['price'] = DEFAULT_QX_PRICES[key]['price']
            # Other damaged values for known items fall back to the defaults.
        else:
            merged[key] = value
    return merged


def load_prices():
    # Add positions introduced by an update, preserving valid user overrides.
    current = _read_or_create(PRICES_FILE, DEFAULT_QX_PRICES)
    merged = normalize_prices(current)
    if merged != current:
        save_prices(merged)
    return merged


def save_prices(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_json_write(PRICES_FILE, data)


def load_settings():
    settings = _read_or_create(SETTINGS_FILE, DEFAULT_SETTINGS)
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)
    return merged


def save_settings(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_json_write(SETTINGS_FILE, data)
