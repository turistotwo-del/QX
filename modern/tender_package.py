"""Offline import of a user-provided tender documentation ZIP bundle.

ZIP contents are untrusted. Never extract archive paths to disk. This is not a
live EIS integration, and no field in the tender card is silently overwritten.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from modern.tender_analysis import document_segments
from modern import tender_store as store
from modern.attachment_formats import RAW_EXTENSIONS, RAW_WARNING, validate_raw_document

MAX_ARCHIVE = 50 * 1024 * 1024
MAX_DOCUMENT = 30 * 1024 * 1024
MAX_UNCOMPRESSED = 120 * 1024 * 1024
MAX_ENTRIES = 80
ACCEPTED = {'.docx', '.pdf', '.xlsx', '.xlsm', '.txt', '.csv', '.md', '.xml'} | RAW_EXTENSIONS


def import_package(tender_id: str, payload: bytes) -> dict:
    """Validate an entire ZIP first, then store documents in one SQLite transaction.

    Returns a transparent list of ignored files and existing duplicates. No
    executable files, nested ZIPs, or private local paths are extracted.
    """
    if not store.get(tender_id):
        raise KeyError('Закупка не найдена')
    if not payload or len(payload) > MAX_ARCHIVE:
        raise ValueError('ZIP должен быть не больше 50 МБ')
    staged: list[tuple[str, bytes, str]] = []
    ignored: list[dict] = []
    warnings: list[dict] = []
    accumulated = 0
    try:
        with ZipFile(BytesIO(payload)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                raise ValueError('Слишком много файлов в архиве (не более 80 записей)')
            for entry in infos:
                path = entry.filename.replace('\\', '/')
                components = path.split('/')
                if (not path or path.startswith('/') or any(part in ('.', '..') for part in components)
                        or ':' in path or '\x00' in path or any(ord(c) < 32 for c in path)
                        or entry.flag_bits & 0x1 or ((entry.external_attr >> 16) & 0o170000) == 0o120000):
                    raise ValueError('Архив содержит небезопасные пути или зашифрованные файлы')
                if entry.is_dir() or path.startswith('__MACOSX/'):
                    continue
                suffix = Path(path).suffix.lower()
                if suffix not in ACCEPTED:
                    ignored.append({'name':path[:220], 'reason':'Формат не поддерживается'})
                    continue
                if entry.file_size > MAX_DOCUMENT:
                    raise ValueError('Документ слишком большой: ' + path[:150])
                accumulated += entry.file_size
                if accumulated > MAX_UNCOMPRESSED:
                    raise ValueError('Содержимое ZIP превышает 120 МБ')
                if entry.file_size and entry.file_size / max(1, entry.compress_size) > 300:
                    raise ValueError('Обнаружен потенциально опасный коэффициент сжатия ZIP')
                with archive.open(entry) as source:
                    data = source.read(MAX_DOCUMENT + 1)
                if len(data) != entry.file_size or len(data) > MAX_DOCUMENT:
                    raise ValueError('Нарушена длина документа в архиве: ' + path[:150])
                basename = Path(path).name[:220]
                try:
                    if suffix in RAW_EXTENSIONS:
                        validate_raw_document(basename, data)
                        warnings.append({'name':path[:220], 'reason':RAW_WARNING})
                        staged.append((basename,data,''))
                        continue
                    chunks = document_segments(basename, data, limit=3500)
                    if not chunks:
                        # A scanned PDF may contain images with no embedded text.
                        # Retain the original document for manual review.
                        warnings.append({'name':path[:220], 'reason':'Текст не извлечён; проверьте документ вручную'})
                    excerpt = '\n'.join(x['text'] for x in chunks)[:30000]
                except Exception:
                    ignored.append({'name':path[:220], 'reason':'Не удалось прочитать документ'})
                    continue
                staged.append((basename, data, excerpt))
    except BadZipFile as exc:
        raise ValueError('Недействительный ZIP-архив') from exc

    if not staged:
        raise ValueError('В архиве нет читаемых PDF, Word, Excel, XML или текстовых документов')
    result = store.add_documents_batch(tender_id, staged)
    return {
        'imported':result['imported'],
        'duplicates':result['duplicates'],
        'ignored':ignored,
        'warnings':warnings,
        'total_entries':len(staged) + len(ignored),
        'documents':store.detail(tender_id)['documents'],
        'message':'Документы сохранены локально. Условия контракта не менялись; запустите анализ вручную.',
    }
