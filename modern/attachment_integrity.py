"""On-demand, offline SHA-256 audit of every tender attachment.

The normal Settings health check intentionally looks only for missing files.
A full audit is user-triggered because hashing many contracts can be expensive.
The API never returns filenames, tender IDs, paths or document content.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path
import re

EXTENSIONS = {'.pdf', '.docx', '.xlsx', '.xlsm', '.txt', '.md', '.csv', '.xml', '.qxproj', '.doc', '.xls', '.rtf', '.rar', '.7z'}
MAX_ATTACHMENT = 30 * 1024 * 1024
_DIGEST = re.compile(r'[0-9a-f]{64}\Z')


class CorruptAttachment(ValueError):
    """Attachment was missing, altered or outside QX-managed storage."""


def _safe_path(path: Path, digest: str, managed_dir: Path) -> bool:
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        return False
    if path.suffix.lower() not in EXTENSIONS or path.name != digest + path.suffix.lower():
        return False
    # Check link itself *and* managed directory. Never follow a symlink to
    # read unrelated files from outside the QX attachment store.
    try:
        return (not path.is_symlink() and path.parent.resolve() == managed_dir.resolve() and
                not managed_dir.is_symlink())
    except (OSError, RuntimeError):
        return False


def checked_attachment(path: Path, digest: str, managed_dir: Path) -> bytes:
    """Read bounded bytes, checking storage path and hash before use/export."""
    if not _safe_path(path, digest, managed_dir):
        raise CorruptAttachment('Недопустимое расположение или имя вложения QX')
    try:
        if not path.is_file():
            raise CorruptAttachment('Вложение отсутствует в папке QX')
        if path.stat().st_size > MAX_ATTACHMENT:
            raise CorruptAttachment('Вложение превышает допустимый размер')
        data = path.read_bytes()
    except OSError as exc:
        raise CorruptAttachment('Не удалось прочитать вложение QX') from exc
    if sha256(data).hexdigest() != digest:
        raise CorruptAttachment('Контрольная сумма SHA-256 вложения не совпадает')
    return data


def audit_attachments() -> dict:
    """Check *all* distinct references, with a privacy-preserving aggregate."""
    from modern import tender_store as store
    store.initialize()
    with store.connection() as db:
        rows = db.execute('SELECT sha256, file_path FROM tender_documents').fetchall()
    distinct = {(str(row['sha256']), str(row['file_path'])) for row in rows}
    counts: Counter[str] = Counter()
    for digest, raw_path in distinct:
        path = Path(raw_path)
        if not _safe_path(path, digest, store.DOCUMENTS):
            counts['unsafe'] += 1
        elif not path.is_file():
            counts['missing'] += 1
        else:
            try:
                if path.stat().st_size > MAX_ATTACHMENT:
                    counts['oversized'] += 1
                    continue
                actual = sha256()
                with path.open('rb') as f:
                    for block in iter(lambda: f.read(1024 * 1024), b''):
                        actual.update(block)
                if actual.hexdigest() == digest:
                    counts['valid'] += 1
                else:
                    counts['modified'] += 1
            except (OSError, RuntimeError):
                counts['unreadable'] += 1
    invalid = sum(counts[k] for k in ('missing', 'modified', 'unsafe', 'oversized', 'unreadable'))
    return {
        'status': 'error' if invalid else 'ok',
        'linked': len(rows), 'unique': len(distinct),
        **{k: counts[k] for k in ('valid', 'missing', 'modified', 'unsafe', 'oversized', 'unreadable')},
        'note': ('Обнаружены проблемы целостности. Вложения не изменены; восстановите данные из проверенной резервной копии.'
                 if invalid else 'Все проверенные вложения совпадают с сохранёнными контрольными суммами SHA-256.'),
        'privacy': 'Названия документов, закупки, пути к файлам и текст документов не передаются в отчёте.',
    }
