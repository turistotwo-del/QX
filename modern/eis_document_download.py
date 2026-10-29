"""Bounded downloads from explicit links or public EIS notice discovery.

The address and redirects are restricted to the official HTTPS hostname.
HTML/captcha pages are rejected; contract terms are never inferred from files.
"""
from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
import re
import zipfile
import hashlib
from contextvars import ContextVar
from time import monotonic

from modern import tender_store
from modern.tender_package import import_package, MAX_ARCHIVE, ACCEPTED
from modern.tender_analysis import document_segments
from modern.attachment_formats import RAW_EXTENSIONS, RAW_WARNING, validate_raw_document

HOSTS = {'zakupki.gov.ru'}
MAX_FILE = 30 * 1024 * 1024
MAX_NETWORK = MAX_ARCHIVE
CONTENT_MIMES_REJECT = ('text/html', 'application/xhtml+xml', 'image/', 'application/javascript')
FILENAME_RE = re.compile(r'filename\*?\s*=\s*(?:UTF-8\'\')?"?([^";]+)', re.I)
MAX_BATCH_BYTES = 120 * 1024 * 1024
MAX_BATCH_SECONDS = 60
_DOWNLOAD_BUDGET = ContextVar('qx_eis_download_budget', default=None)


def validate_document_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2200 or any(ord(c) < 32 for c in url):
        raise ValueError('Некорректная ссылка на документ ЕИС')
    try:
        p = urlsplit(url)
        if (p.scheme != 'https' or p.hostname not in HOSTS or p.username is not None or
                p.password is not None or p.port not in (None, 443) or p.fragment or
                not p.path.startswith('/') or '\\' in p.path):
            raise ValueError('Разрешены только прямые HTTPS-ссылки zakupki.gov.ru')
        # Encoded traversal and backslashes are rejected before making a request.
        path = unquote(p.path)
        if '\\' in path or any(x in ('.', '..') for x in path.split('/')):
            raise ValueError('Недопустимый путь в ссылке ЕИС')
    except (TypeError, ValueError) as exc:
        raise ValueError('Разрешены только прямые HTTPS-ссылки zakupki.gov.ru') from exc
    return url


class OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_document_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _filename(response, url: str) -> str:
    headers = response.headers
    disp = headers.get('Content-Disposition', '')
    match = FILENAME_RE.search(disp)
    if match:
        name = unquote(match.group(1).strip().strip('"'))
    else:
        name = unquote(Path(urlsplit(url).path).name)
    name = Path(name.replace('\\', '/')).name[:200]
    if not name or name in ('.', '..') or any(ord(c) < 32 for c in name):
        raise ValueError('Невозможно определить имя документа. Скачайте файл вручную и прикрепите в QX.')
    return name


def fetch_official_document(url: str, opener=None) -> tuple[str, bytes]:
    """Bounded network retrieval; `opener` injection is for offline tests only."""
    url = validate_document_url(url)
    opener = opener or build_opener(OfficialRedirects())
    request = Request(url, headers={
        'User-Agent': 'QXPodborshchik/4.0 (manual official-document download)',
        'Accept': 'application/zip, application/pdf, application/xml, application/octet-stream, */*',
        'Accept-Encoding': 'identity',
    })
    try:
        budget = _DOWNLOAD_BUDGET.get()
        remaining = min(14, budget['deadline'] - monotonic()) if budget else 14
        if remaining <= 0:
            raise ValueError('Достигнут лимит времени загрузки. Повторите импорт оставшихся файлов.')
        with opener.open(request, timeout=remaining) as response:
            final_url = response.geturl()
            validate_document_url(final_url)
            mime = str(response.headers.get('Content-Type', '')).split(';')[0].lower().strip()
            if any(mime.startswith(prefix) for prefix in CONTENT_MIMES_REJECT):
                raise ValueError('ЕИС вернула страницу вместо документа. Откройте ссылку в браузере.')
            name = _filename(response, final_url)
            suffix = Path(name).suffix.lower()
            if suffix not in ACCEPTED | {'.zip'}:
                raise ValueError('Ссылка не указывает на поддерживаемый файл. Скачайте документ вручную.')
            length = response.headers.get('Content-Length')
            if length:
                try:
                    if int(length) < 0:
                        raise ValueError('Некорректная длина ответа ЕИС')
                    if int(length) > (MAX_NETWORK if suffix == '.zip' else MAX_FILE):
                        raise ValueError('Документ ЕИС слишком большой')
                except (TypeError, ValueError) as exc:
                    if str(exc) == 'Документ ЕИС слишком большой':
                        raise
                    raise ValueError('Некорректная длина ответа ЕИС') from exc
            max_bytes = MAX_NETWORK if suffix == '.zip' else MAX_FILE
            chunks, total = [], 0
            while True:
                if budget and monotonic() >= budget['deadline']:
                    raise ValueError('Достигнут лимит времени загрузки. Повторите импорт оставшихся файлов.')
                piece = response.read(min(1024 * 1024, max_bytes + 1 - total))
                if not piece:
                    break
                chunks.append(piece)
                total += len(piece)
                if budget:
                    budget['bytes'] += len(piece)
                    if budget['bytes'] > MAX_BATCH_BYTES:
                        raise ValueError('Достигнут общий лимит загрузки 120 МБ. Повторите импорт оставшихся файлов.')
                if total > max_bytes:
                    raise ValueError('Документ ЕИС превышает допустимый размер')
            payload = b''.join(chunks)
            if not payload:
                raise ValueError('ЕИС вернула пустой файл')
            prefix = payload[:1024].lstrip(b'\xef\xbb\xbf \t\r\n').lower()
            prefix = re.sub(br'^<\?xml[^>]*\?>\s*', b'', prefix)
            if prefix.startswith((b'<!doctype html', b'<html', b'<head', b'<body')):
                raise ValueError('ЕИС вернула страницу вместо документа ' + suffix.upper().lstrip('.') + '. Откройте ссылку в браузере.')
            if suffix == '.zip':
                if not zipfile.is_zipfile(__import__('io').BytesIO(payload)):
                    raise ValueError('Полученный файл не является ZIP-архивом')
            elif suffix == '.pdf' and not payload.startswith(b'%PDF-'):
                raise ValueError('Полученный файл не является PDF')
            elif suffix in ('.docx', '.xlsx', '.xlsm') and not zipfile.is_zipfile(__import__('io').BytesIO(payload)):
                raise ValueError('Полученный файл не является документом Office')
            elif suffix in RAW_EXTENSIONS:
                validate_raw_document(name,payload)
            return name, payload
    except (HTTPError, URLError, OSError) as exc:
        raise ValueError('ЕИС не выдала файл. Проверьте доступность ссылки в браузере; возможно, требуется вход или капча.') from exc


def import_official_document(tender_id: str, url: str, *, opener=None) -> dict:
    if not tender_store.get(tender_id):
        raise KeyError('Закупка не найдена')
    name, data = fetch_official_document(url, opener=opener)
    if name.lower().endswith('.zip'):
        result = import_package(tender_id, data)
        result['source'] = 'zakupki.gov.ru (ссылка пользователя)'
        tender_store.record_official_document_source(tender_id, name, len(result['imported']))
        return result
    # Files without embedded text (e.g. PDF scans) are kept with a warning.
    raw_original = Path(name).suffix.lower() in RAW_EXTENSIONS
    try:
        if raw_original:
            validate_raw_document(name,data)
            segments = []
        else:
            segments = document_segments(name, data, limit=3500)
    except Exception as exc:
        raise ValueError('Скачанный документ повреждён или не читается: '+name) from exc
    excerpt = '\n'.join(part['text'] for part in segments)[:30000]
    digest = hashlib.sha256(data).hexdigest()
    duplicate = any(d.get('sha256') == digest for d in tender_store.detail(tender_id)['documents'])
    document_id = tender_store.add_document(tender_id, name, data, excerpt)
    tender_store.record_official_document_source(tender_id, name, 1)
    return {
        'imported': [] if duplicate else [name], 'duplicates': [name] if duplicate else [], 'document_id': document_id,
        'warnings': [] if segments else [{'name': name, 'reason': RAW_WARNING if raw_original else 'Скан без текстового слоя; нужен ручной просмотр'}],
        'documents': tender_store.detail(tender_id)['documents'],
        'source': 'zakupki.gov.ru (ссылка пользователя)',
        'message': 'Документ загружен с официального сайта и сохранён. Сведения карточки не изменялись.',
    }


def import_official_documents(tender_id: str, urls: list[str], *, opener=None, max_urls=10) -> dict:
    """Import up to ten user-supplied direct EIS links in one action.

    All links are validated *before* fetching. Individual network failures are
    reported per line and never silently turned into success. Successful items
    are retained if later ones fail; this is deliberately NOT an atomic batch.
    Signed/token-bearing URLs are never echoed back or entered into audit logs.
    """
    if not tender_store.get(tender_id):
        raise KeyError('Закупка не найдена')
    if max_urls not in (10, 40) or not isinstance(urls, list) or not 1 <= len(urls) <= max_urls:
        raise ValueError(f'Укажите от 1 до {max_urls} прямых ссылок на документы ЕИС')
    checked = []
    for url in urls:
        checked.append(validate_document_url(url.strip() if isinstance(url, str) else url))
    if len(set(checked)) != len(checked):
        raise ValueError('В списке есть повторяющиеся ссылки')
    imported, duplicates, warnings, failures, ignored = [], [], [], [], []
    successful = 0
    budget = {'bytes':0, 'deadline':monotonic() + MAX_BATCH_SECONDS}
    token = _DOWNLOAD_BUDGET.set(budget)
    limit_reached = False
    try:
        for index, url in enumerate(checked, 1):
            if monotonic() >= budget['deadline'] or budget['bytes'] >= MAX_BATCH_BYTES:
                limit_reached = True
                failures.extend({'line':line, 'reason':'Достигнут общий лимит загрузки. Повторите импорт оставшихся файлов.'}
                                for line in range(index,len(checked)+1))
                break
            try:
                result = import_official_document(tender_id, url, opener=opener)
                successful += 1
                imported.extend(result.get('imported') or [])
                duplicates.extend(result.get('duplicates') or [])
                warnings.extend(result.get('warnings') or [])
                ignored.extend(result.get('ignored') or [])
            except (ValueError, OSError) as exc:
                # Do not expose URL query strings, which may contain access tokens.
                message = str(exc)
                if url in message or 'http://' in message or 'https://' in message:
                    message = 'Не удалось обработать ссылку на документ; проверьте её в браузере'
                failures.append({'line': index, 'reason': message[:230]})
                if monotonic() >= budget['deadline'] or budget['bytes'] >= MAX_BATCH_BYTES:
                    limit_reached = True
    finally:
        _DOWNLOAD_BUDGET.reset(token)
    return {
        'imported': imported, 'duplicates': duplicates, 'warnings': warnings, 'ignored':ignored,
        'success_count': successful, 'failed_count': len(failures), 'failures': failures,
        'limit_reached':limit_reached,
        'documents': tender_store.detail(tender_id)['documents'],
        'source': 'zakupki.gov.ru (ссылки пользователя)',
        'message': 'Импорт завершён. Частичные ошибки перечислены по строкам; карточка закупки не изменялась.'
    }
