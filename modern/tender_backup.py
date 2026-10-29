"""Verify and restore QX tender archives without untrusted ZIP extraction.

An explicit user confirmation is required by the frontend for replacement. A full
snapshot of the current state is written before the live SQLite database changes.
Only SHA-256-named documents are imported, and DB document paths are rewritten.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
from io import BytesIO
from pathlib import Path
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
import zipfile

from modern import tender_store as store

BACKUP_LOCK = threading.Lock()
MAX_ARCHIVE = 150 * 1024 * 1024
MAX_DB = 120 * 1024 * 1024
MAX_FILE = 30 * 1024 * 1024
MAX_TOTAL = 700 * 1024 * 1024
MAX_MEMBERS = 10000
DOC_RE = re.compile(r'^documents/([0-9a-f]{64})(\.(?:docx|pdf|xlsx|xlsm|txt|md|csv|xml|qxproj|doc|xls|rtf))$')
REQUIRED_TABLES = {'tenders', 'tender_projects', 'tender_documents', 'tender_comments', 'organizations', 'tender_shipments', 'tender_events'}


def _check_zip(blob: bytes):
    if not blob or len(blob) > MAX_ARCHIVE:
        raise ValueError('Резервная копия слишком большая или пуста (лимит 150 МБ)')
    try:
        z = zipfile.ZipFile(BytesIO(blob))
        infos = z.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError('Слишком много файлов в архиве')
        seen = set()
        uncompressed = 0
        for entry in infos:
            name = entry.filename
            if name in seen or '\\' in name or '..' in Path(name).parts or name.startswith('/'):
                raise ValueError('Небезопасные или повторяющиеся имена в архиве')
            seen.add(name)
            if name not in ('tenders.sqlite3', 'README.txt', 'manifest.json') and not DOC_RE.fullmatch(name):
                raise ValueError('Неизвестный файл в архиве: ' + name[:110])
            if entry.is_dir():
                raise ValueError('Неожиданная папка внутри архива')
            cap = MAX_DB if name == 'tenders.sqlite3' else MAX_FILE if name.startswith('documents/') else 2 * 1024 * 1024
            if entry.file_size > cap:
                raise ValueError('Недопустимый размер элемента: ' + name[:100])
            uncompressed += entry.file_size
            if uncompressed > MAX_TOTAL:
                raise ValueError('Суммарный размер файлов архива слишком велик')
        if 'tenders.sqlite3' not in seen:
            raise ValueError('В архиве отсутствует база tenders.sqlite3')
        bad = z.testzip()  # CRC check only after size/path limits.
        if bad:
            raise ValueError('Повреждён файл архива: ' + bad[:120])
        if 'manifest.json' in seen:
            try:
                manifest = json.loads(z.read('manifest.json'))
                if manifest.get('format') != 'QX-Tenders-Backup' or manifest.get('version') != 1:
                    raise ValueError('Неизвестный формат резервной копии')
                if manifest.get('db_sha256') != hashlib.sha256(z.read('tenders.sqlite3')).hexdigest():
                    raise ValueError('Контрольная сумма базы не совпадает')
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, TypeError) as exc:
                raise ValueError('Повреждён файл описания архива') from exc
        return z
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError('Это не ZIP-архив резервной копии QX') from exc


def _inspect(blob: bytes, directory: Path):
    z = _check_zip(blob)
    dbfile = directory / 'incoming.sqlite3'
    with z.open('tenders.sqlite3') as src, dbfile.open('wb') as dst:
        import shutil
        shutil.copyfileobj(src, dst)
    # SQLite is read-only until all validation is complete.
    uri = dbfile.resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as con:
        if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('Проверка целостности SQLite не пройдена')
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED_TABLES <= tables:
            raise ValueError('База не соответствует структуре QX Тендеры')
        cols = {r[1] for r in con.execute('PRAGMA table_info(tender_documents)')}
        if not {'filename', 'sha256', 'file_path'} <= cols:
            raise ValueError('Отсутствуют сведения о вложениях')
        if con.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Нарушены связи закупок и вложений')
        # Check compatibility during PREVIEW, before even attempting a safety
        # snapshot or writing any attachment. A newer QX schema must never be
        # silently installed into an older desktop application.
        try:
            schema_version = store._read_schema_version(con)
        except (RuntimeError, sqlite3.DatabaseError) as exc:
            raise ValueError('Не удалось определить версию базы в архиве') from exc
        if schema_version > store.SCHEMA_VERSION:
            raise ValueError('Резервная копия создана более новой версией QX. Обновите программу перед восстановлением.')
        refs = con.execute('SELECT sha256, file_path FROM tender_documents').fetchall()
        validnames = {i.filename for i in z.infolist()}
        for digest, source_path in refs:
            if not re.fullmatch('[a-f0-9]{64}', str(digest)):
                raise ValueError('Некорректный идентификатор документа')
            ext = Path(source_path).suffix.lower()
            name = f'documents/{digest}{ext}'
            if not DOC_RE.fullmatch(name) or name not in validnames:
                raise ValueError('В архиве отсутствует вложение '+digest[:10])
            with z.open(name) as f:
                h = hashlib.sha256()
                for chunk in iter(lambda: f.read(1024*1024), b''):
                    h.update(chunk)
            if h.hexdigest() != digest:
                raise ValueError('Повреждено содержимое документа: '+digest[:10])
            from modern.attachment_formats import RAW_EXTENSIONS, validate_raw_document
            if ext in RAW_EXTENSIONS:
                with z.open(name) as raw_source:
                    validate_raw_document(name, raw_source.read(512))
        names={r[0] for r in con.execute('SELECT name FROM organizations')}
        count=con.execute('SELECT count(*) FROM tenders').fetchone()[0]
        return z, dbfile, refs, {'tenders':count,'organizations':len(names),'documents':len(refs),'schema_version':schema_version,'compressed_bytes':len(blob)}


def preview_archive(blob: bytes):
    with tempfile.TemporaryDirectory(prefix='qx_restore_check_') as tmp:
        z, _, _, report = _inspect(blob, Path(tmp))
        z.close()
        return report




def _document_repair_plan(archive: zipfile.ZipFile):
    """Select only corrupt/missing managed attachments also present in the backup.

    This does not use the backup's SQLite state to replace or merge tenders.
    Every destination is an already-existing reference in the *current* DB.
    """
    from modern.attachment_integrity import _safe_path, checked_attachment, CorruptAttachment
    store.initialize()
    with store.connection() as con:
        references = {(str(r['sha256']), str(r['file_path'])) for r in con.execute(
            'SELECT sha256, file_path FROM tender_documents')}
    available = set(archive.namelist())
    plan = []
    stats = {'total': len(references), 'intact': 0, 'repairable': 0,
             'not_in_backup': 0, 'unsafe': 0}
    for digest, source in sorted(references):
        path = Path(source)
        if not _safe_path(path, digest, store.DOCUMENTS):
            stats['unsafe'] += 1
            continue
        try:
            checked_attachment(path, digest, store.DOCUMENTS)
            stats['intact'] += 1
            continue
        except CorruptAttachment:
            pass
        member = 'documents/' + path.name
        if member not in available:
            stats['not_in_backup'] += 1
            continue
        # Do not trust unreferenced extra members in a ZIP: validate bytes now.
        with archive.open(member) as stream:
            h = hashlib.sha256()
            size = 0
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                size += len(block)
                if size > MAX_FILE:
                    raise ValueError('В архиве найден слишком большой документ')
                h.update(block)
        if h.hexdigest() != digest:
            raise ValueError('SHA-256 документа в резервной копии не совпадает')
        plan.append((path, member, digest))
        stats['repairable'] += 1
    return plan, stats


def preview_document_repair(blob: bytes):
    """Read-only preview: never modify current tenders or attachments."""
    with tempfile.TemporaryDirectory(prefix='qx_repair_preview_') as tmp:
        archive, _, _, _ = _inspect(blob, Path(tmp))
        try:
            _, report = _document_repair_plan(archive)
            report['changes_to_database'] = False
            return report
        finally:
            archive.close()


def repair_documents(blob: bytes):
    """Restore matching SHA-256 blobs, without replacing or rolling back SQLite.

    Damaged originals are retained in an isolated local directory. Stage and
    verify *all* replacement bytes before the first destination is changed.
    On an I/O exception, attempt to undo every replacement in reverse order.
    """
    from modern.attachment_integrity import _safe_path, checked_attachment, CorruptAttachment
    if not BACKUP_LOCK.acquire(blocking=False):
        raise ValueError('Уже выполняется восстановление данных')
    try:
        with tempfile.TemporaryDirectory(prefix='qx_repair_') as tmp:
            archive, _, _, _ = _inspect(blob, Path(tmp))
            try:
                plan, report = _document_repair_plan(archive)
                if not plan:
                    return {'repaired': 0, 'preview': report, 'database_unchanged': True}
                # Verify and stage *every* document before modifying user files.
                stage_dir = Path(tmp) / 'staged'
                stage_dir.mkdir()
                for index, (dest, member, digest) in enumerate(plan):
                    staged = stage_dir / str(index)
                    with archive.open(member) as source, staged.open('wb') as output:
                        import shutil
                        shutil.copyfileobj(source, output, 1024 * 1024)
                    if hashlib.sha256(staged.read_bytes()).hexdigest() != digest:
                        raise ValueError('Неверная контрольная сумма восстановленного файла')

                # Keep the original bytes even if they are damaged. This folder
                # is never overwritten on subsequent repairs.
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                quarantine = store.APP_DATA / 'repair_snapshots' / timestamp
                quarantine.mkdir(parents=True, exist_ok=False)
                applied = []
                import shutil
                try:
                    for index, (dest, member, digest) in enumerate(plan):
                        # Refuse suspicious file replacements, including symlinks
                        # introduced while preparing the repair.
                        if not _safe_path(dest, digest, store.DOCUMENTS):
                            raise ValueError('Расположение вложения изменилось во время восстановления')
                        had_original = dest.exists()
                        original = quarantine / str(index)
                        if had_original:
                            if not dest.is_file() or dest.stat().st_size > MAX_FILE:
                                raise ValueError('Исходный файл невозможно безопасно сохранить')
                            shutil.copy2(dest, original)
                        # Atomic replacement on the SAME volume as the destination.
                        tmp_dest = store.DOCUMENTS / (digest + '.qxrepair-' + os.urandom(8).hex())
                        try:
                            shutil.copyfile(stage_dir / str(index), tmp_dest)
                            os.replace(tmp_dest, dest)
                        finally:
                            tmp_dest.unlink(missing_ok=True)
                        applied.append((dest, original if had_original else None))
                    # All replacements pass the same check as normal file reads.
                    for dest, _, digest in plan:
                        checked_attachment(dest, digest, store.DOCUMENTS)
                except Exception:
                    for dest, original in reversed(applied):
                        try:
                            if original is not None:
                                shutil.copyfile(original, dest)
                            else:
                                dest.unlink(missing_ok=True)
                        except OSError:
                            # Quarantined originals remain available if disk I/O
                            # prevents an automatic rollback.
                            pass
                    raise
                return {'repaired': len(applied), 'preview': report,
                        'database_unchanged': True,
                        'note': 'База закупок не заменялась. Повреждённые оригиналы сохранены локально.'}
            finally:
                archive.close()
    finally:
        BACKUP_LOCK.release()


def restore_archive(blob: bytes):
    if not BACKUP_LOCK.acquire(blocking=False):
        raise ValueError('Уже выполняется восстановление')
    try:
        store.initialize()
        with tempfile.TemporaryDirectory(prefix='qx_restore_') as tmp:
            z, source, refs, info = _inspect(blob, Path(tmp))
            try:
                # Snapshot BEFORE replacing any files. If current attachments
                # are corrupt, stop here and use targeted document repair first.
                # A failed safety snapshot must not change even a single file.
                archive_dir=store.APP_DATA / 'restore_snapshots'
                archive_dir.mkdir(parents=True, exist_ok=True)
                stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                previous=archive_dir/f'QX_Before_Restore_{stamp}.zip'
                snapshot=store.backup_archive()
                # Write the safety snapshot atomically. An interrupted/disk-full
                # write must never leave a truncated ZIP with a convincing
                # QX_Before_Restore_*.zip name. No user data is changed yet.
                snapshot_partial=archive_dir/f'QX_Before_Restore_{stamp}.zip.partial'
                try:
                    with snapshot_partial.open('wb') as target:
                        target.write(snapshot)
                        target.flush()
                        os.fsync(target.fileno())
                    os.replace(snapshot_partial, previous)
                finally:
                    snapshot_partial.unlink(missing_ok=True)
                safety_snapshot_path = previous
                # The incoming archive was fully checked. Stage the normalized
                # database before changing a single user file, then track every
                # replaced/new attachment for a possible rollback. Otherwise a
                # failed SQLite migration could leave newly imported files in
                # place and overwrite a previously unlinked (but user-owned) blob.
                with closing(sqlite3.connect(str(source))) as con:
                    con.executemany('UPDATE tender_documents SET file_path=? WHERE sha256=? AND file_path=?',
                        [(str(store.DOCUMENTS/(digest+Path(path).suffix.lower())), digest, path)
                         for digest,path in refs])
                    con.commit()
                    if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise ValueError('База повреждена перед восстановлением')

                stage = Path(tmp) / 'staged_documents'
                stage.mkdir()
                required = {}
                for digest, original in refs:
                    ext = Path(original).suffix.lower()
                    required[digest + ext] = f'documents/{digest}{ext}'
                for name, member in required.items():
                    with z.open(member) as src, (stage / name).open('wb') as out:
                        import shutil
                        shutil.copyfileobj(src, out, 1024 * 1024)
                    if hashlib.sha256((stage / name).read_bytes()).hexdigest() != name[:64]:
                        raise ValueError('Ошибка проверки подготовленного вложения')

                store.DOCUMENTS.mkdir(parents=True, exist_ok=True)
                if store.DOCUMENTS.is_symlink():
                    raise ValueError('Папка вложений не должна быть символической ссылкой')
                original_files = Path(tmp) / 'before_documents'
                original_files.mkdir()
                changed = []
                database_started = False
                try:
                    for name in required:
                        dest = store.DOCUMENTS / name
                        if dest.is_symlink() or (dest.exists() and not dest.is_file()):
                            raise ValueError('Небезопасное расположение вложения при восстановлении')
                        if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == name[:64]:
                            continue
                        previous = original_files / name
                        if dest.exists():
                            if dest.stat().st_size > MAX_FILE:
                                raise ValueError('Невозможно безопасно сохранить предыдущую версию файла')
                            import shutil
                            shutil.copy2(dest, previous)
                        temp_dest = store.DOCUMENTS / (name + '.qx-restoring-' + os.urandom(8).hex())
                        try:
                            import shutil
                            shutil.copyfile(stage / name, temp_dest)
                            os.replace(temp_dest, dest)
                        finally:
                            temp_dest.unlink(missing_ok=True)
                        changed.append((dest, previous if previous.exists() else None))

                    # Replace the SQLite database only after all incoming
                    # attachments are in place. If this or a migration fails,
                    # both DB and attachment changes are rolled back.
                    database_started = True
                    with closing(sqlite3.connect(str(source))) as src, store.connection() as dst:
                        src.backup(dst)
                    store._INITIALIZED = False
                    store.initialize()
                except Exception:
                    rollback_errors = []
                    if database_started:
                        try:
                            with tempfile.TemporaryDirectory(prefix='qx_rollback_') as rollback:
                                rz, rp, _, _ = _inspect(snapshot, Path(rollback))
                                try:
                                    with closing(sqlite3.connect(str(rp))) as src, store.connection() as dst:
                                        src.backup(dst)
                                finally:
                                    rz.close()
                            store._INITIALIZED = False
                            store.initialize()
                        except Exception as rollback_exc:
                            rollback_errors.append('База SQLite: ' + str(rollback_exc)[:140])
                    for dest, original in reversed(changed):
                        try:
                            if original is not None:
                                os.replace(original, dest)
                            else:
                                dest.unlink(missing_ok=True)
                        except OSError as rollback_exc:
                            rollback_errors.append('Вложение: ' + str(rollback_exc)[:140])
                    if rollback_errors:
                        raise RuntimeError('Восстановление прервалось, автоматический откат частично не удался. '
                                           'Сохранена защитная ZIP-копия: ' + str(safety_snapshot_path) + '. '
                                           + '; '.join(rollback_errors))
                    raise
                return {'restored':info,'snapshot':str(safety_snapshot_path),'restart_recommended':True}
            finally:
                z.close()
    finally:
        BACKUP_LOCK.release()
