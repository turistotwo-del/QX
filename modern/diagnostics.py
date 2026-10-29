"""Explicit, read-only QX health report for Settings / post-install checks.

Do not include contents of TЗ, contracts, comments, tokens or document excerpts.
Never download models, query EIS or fetch the CBR during a health check.
"""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
import tempfile

from modern.release_info import RELEASE_LABEL


def run_diagnostics():
    from modern import tender_store as store
    from modern import local_ai
    checks=[]

    def record(name, status, detail):
        checks.append({'name':name,'status':status,'detail':str(detail)[:400]})

    directory=store.APP_DATA
    try:
        directory.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix='.qx_health_', dir=directory, delete=True) as tmp:
            tmp.write(b'qx-health')
            tmp.flush()
        record('Папка данных','ok','Доступна для записи; находится вне установочной папки.')
    except (OSError, ValueError) as exc:
        record('Папка данных','error',f'Нет доступа к пользовательским данным: {type(exc).__name__}')

    try:
        store.initialize()
        # sqlite3 performs its own lock management.  No full database copy on
        # a simple health check and no private data is returned to the UI.
        with store.connection() as db:
            health=db.execute('PRAGMA quick_check').fetchone()[0]
            if health != 'ok':
                record('База закупок','error','SQLite сообщает о нарушении целостности.')
            else:
                tenders=int(db.execute('SELECT COUNT(*) FROM tenders').fetchone()[0])
                attachments=int(db.execute('SELECT COUNT(*) FROM tender_documents').fetchone()[0])
                record('База закупок','ok',f'Целостность подтверждена; закупок: {tenders}, вложений: {attachments}.')
            refs=db.execute('SELECT file_path FROM tender_documents LIMIT 201').fetchall()
        missing=sum(1 for row in refs[:200] if not Path(row[0]).is_file())
        if missing:
            record('Файлы договоров','error',f'Отсутствуют вложения: {missing} из проверенных {min(len(refs),200)}.')
        elif len(refs)>200:
            record('Файлы договоров','warning','Проверены первые 200 вложений; полный аудит не выполнялся.')
        else:
            record('Файлы договоров','ok',f'Найдено {len(refs)} из {len(refs)} проверенных вложений.')
    except (OSError, sqlite3.DatabaseError, ValueError, RuntimeError) as exc:
        record('База закупок','error',f'Не удалось проверить базу: {type(exc).__name__}: {str(exc)[:130]}')

    try:
        free=shutil.disk_usage(str(directory)).free
        if free<512*1024*1024:
            record('Свободное место','warning',f'{free//(1024*1024)} МБ. Для документов и резервных копий желательно хотя бы 512 МБ.')
        else:
            record('Свободное место','ok',f'{free//(1024*1024)} МБ доступно в пользовательской папке.')
    except OSError:
        record('Свободное место','warning','Не удалось определить свободное место на диске.')

    try:
        enabled=local_ai.gguf_runtime_available()
        model_dir=local_ai.gguf_model_dir()
        models=list(model_dir.glob('*.gguf'))[:100] if model_dir.exists() else []
        models=[p for p in models if p.is_file() and not p.is_symlink()]
        if not enabled:
            record('Локальный AI','warning','GGUF-движок не установлен; поиск по документам без нейросети доступен.')
        elif not models:
            record('Локальный AI','warning','GGUF-движок есть, модель не найдена; её можно установить отдельно по кнопке.')
        else:
            record('Локальный AI','ok',f'Движок доступен; найдено файлов моделей: {len(models)}. SHA-256 здесь не проверяется.')
    except (OSError, RuntimeError, ImportError, ValueError):
        record('Локальный AI','warning','Не удалось проверить локальный GGUF-движок.')

    return {
        'version':RELEASE_LABEL,
        'os':platform.system()+' '+platform.release(),
        'python':platform.python_version(),
        'packaged':bool(getattr(sys,'frozen',False)),
        'data_directory':str(directory),
        'checks':checks,
        'overall':'error' if any(c['status']=='error' for c in checks) else
                  'warning' if any(c['status']=='warning' for c in checks) else 'ok',
        'privacy':'Проверка выполняется локально. Документы, номера закупок и содержимое баз в отчёт не включаются.'
    }
