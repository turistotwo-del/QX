from __future__ import annotations

import base64
import json
from datetime import datetime

PROJECT_FORMAT = 'QX_SELECTOR_PROJECT'
PROJECT_SCHEMA = 2


def dump_project(*, reqs, plans, source_text='', qx_prices=None, project_meta=None, settings_snapshot=None,
                 source_filename='', source_docx_bytes=None, tender_overrides=None, tender_characteristics=None, tz_documents=None) -> bytes:
    payload = {
        'format': PROJECT_FORMAT,
        'schema': PROJECT_SCHEMA,
        'saved_at': datetime.now().isoformat(timespec='seconds'),
        'reqs': reqs or [],
        'plans': plans or [],
        'source_text': source_text or '',
        'source_filename': source_filename or '',
        'source_docx_base64': base64.b64encode(source_docx_bytes).decode('ascii') if source_docx_bytes else '',
        'tender_overrides': tender_overrides or {},
        'tender_characteristics': tender_characteristics or [],
        'tz_documents': tz_documents or [],
        'qx_prices': qx_prices or {},
        'project_meta': project_meta or {},
        'settings_snapshot': settings_snapshot or {},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')


def load_project(data: bytes | str) -> dict:
    if isinstance(data, bytes):
        text = data.decode('utf-8-sig')
    else:
        text = str(data)
    obj = json.loads(text)
    if not isinstance(obj, dict) or obj.get('format') != PROJECT_FORMAT:
        raise ValueError('Это не файл проекта QX Подборщика')
    if int(obj.get('schema') or 0) > PROJECT_SCHEMA:
        raise ValueError('Файл создан более новой версией QX Подборщика')
    if not isinstance(obj.get('reqs'), list) or not isinstance(obj.get('plans'), list):
        raise ValueError('Файл проекта повреждён: нет расчёта')
    raw = obj.get('source_docx_base64') or ''
    if raw:
        try:
            obj['source_docx_bytes'] = base64.b64decode(raw)
        except Exception:
            obj['source_docx_bytes'] = None
    else:
        obj['source_docx_bytes'] = None
    obj.setdefault('source_filename', '')
    obj.setdefault('tender_overrides', {})
    obj.setdefault('tender_characteristics', [])
    obj.setdefault('tz_documents', [])
    return obj


def validate_quantities(reqs) -> list[str]:
    errors = []
    for i, req in enumerate(reqs or []):
        qty = int((req or {}).get('quantity') or 0)
        if qty <= 0:
            title = (req or {}).get('title') or f'Позиция {i+1}'
            errors.append(f'{title}: укажи количество больше нуля')
    return errors
