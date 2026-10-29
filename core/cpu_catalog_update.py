from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
EXTERNAL_FILE = BASE_DIR / 'data' / 'cpu_catalog_external.json'
BUILDCURES_ZIPS = [
    'https://codeload.github.com/buildcores/buildcores-open-db/zip/refs/heads/main',
    'https://github.com/buildcores/buildcores-open-db/archive/refs/heads/main.zip',
]


def _number(value, default=0.0):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r'-?\d+(?:[\.,]\d+)?', str(value))
    return float(m.group(0).replace(',', '.')) if m else default


def _clock(obj, which):
    clocks = obj.get('clocks') or {}
    perf = clocks.get('performance') or {}
    val = perf.get(which)
    if val is None:
        val = clocks.get(which)
    return _number(val, 0.0)


def _normalize(raw: dict):
    meta = raw.get('metadata') or {}
    maker = str(meta.get('manufacturer') or '').strip()
    if maker.lower() not in ('intel', 'amd'):
        return None
    name = str(meta.get('name') or '').strip()
    if not name:
        return None
    cores = int(_number((raw.get('cores') or {}).get('total'), 0))
    threads = int(_number((raw.get('cores') or {}).get('threads'), cores))
    if not cores or not threads:
        return None
    socket = str(raw.get('socket') or '').strip()
    sn = re.sub(r'\s+', '', socket).upper()
    if maker.lower() == 'intel' and 'LGA1700' in sn:
        platform = 'intel'
    elif maker.lower() == 'amd' and 'AM4' in sn:
        platform = 'amd'
    else:
        platform = 'other'
    specs = raw.get('specifications') or {}
    igpu_obj = specs.get('integratedGraphics')
    # OpenDB often stores integratedGraphics as an object even when model='None'.
    # Treat only a real non-empty model as an iGPU.
    if isinstance(igpu_obj, dict):
        igpu_model = str(igpu_obj.get('model') or '').strip().lower()
        igpu = bool(igpu_model and igpu_model not in ('none', 'no', 'n/a', 'null'))
    else:
        igpu_model = str(igpu_obj or '').strip().lower()
        igpu = bool(igpu_model and igpu_model not in ('none', 'no', 'n/a', 'null'))
    mem = specs.get('memory') or {}
    memtypes = mem.get('types') or []
    if isinstance(memtypes, str):
        memtypes = [memtypes]
    cache = raw.get('cache') or {}
    l3 = int(round(_number(cache.get('l3'), 0)))
    tdp = int(round(_number(specs.get('tdp'), 0)))
    return {
        'model': name,
        'manufacturer': maker,
        'platform': platform,
        'socket': socket,
        'cores': cores,
        'threads': threads,
        'base_ghz': _clock(raw, 'base'),
        'boost_ghz': _clock(raw, 'boost'),
        'l3_mb': l3,
        'igpu': igpu,
        'tdp_w': tdp,
        'memory_types': [str(x) for x in memtypes],
        'source': 'BuildCores OpenDB',
    }


def update_from_buildcores(path: str | Path | None = None, timeout: int = 45) -> dict:
    target = Path(path) if path else EXTERNAL_FILE
    last_error = None
    r = None
    for url in BUILDCURES_ZIPS:
        try:
            candidate = requests.get(url, timeout=timeout, headers={'User-Agent':'QX-Selector/1.5'})
            candidate.raise_for_status()
            r = candidate
            break
        except Exception as exc:
            last_error = exc
    if r is None:
        raise RuntimeError(f'Не удалось скачать BuildCores OpenDB: {last_error}')
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    rows = []
    seen = set()
    for name in zf.namelist():
        if '/open-db/CPU/' not in name or not name.lower().endswith('.json'):
            continue
        try:
            raw = json.loads(zf.read(name).decode('utf-8'))
            item = _normalize(raw)
        except Exception:
            continue
        if not item:
            continue
        key = item['model'].lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(item)
    rows.sort(key=lambda x: (x['manufacturer'], x['model']))
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'source': 'BuildCores OpenDB',
        'source_url': 'https://github.com/buildcores/buildcores-open-db',
        'license': 'ODC Attribution License (ODC-By) v1.0',
        'count': len(rows),
        'cpus': rows,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return payload
