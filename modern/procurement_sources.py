"""Bounded public secondary procurement pages, clearly separate from official EIS.

The adapter reads a public Kontur card at its number-addressed URL. It does not
authenticate, invoke private APIs, bypass paywalls or invent attachment URLs.
Only links actually published on the exact-number page are returned. Current
live availability must be checked separately from deterministic parser tests.
"""
from __future__ import annotations

from datetime import datetime
from http.client import IncompleteRead
from http.cookiejar import CookieJar
import hashlib
import json
from pathlib import Path
import re
from time import monotonic
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPCookieProcessor

from bs4 import BeautifulSoup

from modern.notice_number import normalize_notice

KONTUR_HOST = 'zakupki.kontur.ru'
SOURCE_NAME = 'Контур.Закупки (вторичный источник)'
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_DOCUMENTS = 40
MAX_TOTAL_BYTES = 120 * 1024 * 1024
MAX_DOWNLOAD_SECONDS = 60
PUBLIC_DOCUMENT_HOSTS = frozenset({'zakupki.gov.ru', 'www.zakupki.gov.ru',
                                   KONTUR_HOST, 'files.zakupki.kontur.ru'})
FILE_SUFFIXES = ('.doc', '.docx', '.pdf', '.xls', '.xlsx', '.xlsm', '.rtf',
                 '.txt', '.xml', '.zip', '.csv', '.md', '.odt', '.rar', '.7z')


def _safe_https(url: str, hosts) -> bool:
    if not isinstance(url, str) or len(url) > 2200 or any(ord(c) < 32 for c in url):
        return False
    try:
        parsed = urlsplit(url)
        path = unquote(parsed.path)
        return bool(parsed.scheme == 'https' and parsed.hostname in hosts and
                    not parsed.username and not parsed.password and
                    parsed.port in (None, 443) and not parsed.fragment and
                    path.startswith('/') and '\\' not in path and
                    not any(piece in ('.', '..') for piece in path.split('/')))
    except (ValueError, TypeError):
        return False


def public_document_url(url: str) -> str:
    """Validate discovered attachment links without following arbitrary services."""
    if not _safe_https(url, PUBLIC_DOCUMENT_HOSTS):
        raise ValueError('Ссылка на документ не относится к поддерживаемому открытому источнику')
    return url


def kontur_page_url(number: str) -> str:
    return 'https://' + KONTUR_HOST + '/' + normalize_notice(number)


def _card_url(url: str, number: str) -> bool:
    return (_safe_https(url, {KONTUR_HOST}) and
            urlsplit(url).path.rstrip('/') == '/' + number)


class _KonturRedirects(HTTPRedirectHandler):
    def __init__(self, number):
        super().__init__()
        self.number = number

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _card_url(newurl, self.number):
            raise ValueError('Вторичный источник перенаправил на другую карточку или страницу входа')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_secondary_opener(number: str):
    return build_opener(_KonturRedirects(normalize_notice(number)), HTTPCookieProcessor(CookieJar()))


class _AttachmentRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_document_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def create_secondary_session(number: str):
    """Share public page cookies with attachments without loosening page identity."""
    jar = CookieJar()
    return SimpleNamespace(
        page=build_opener(_KonturRedirects(normalize_notice(number)), HTTPCookieProcessor(jar)),
        documents=build_opener(_AttachmentRedirects(), HTTPCookieProcessor(jar)),
    )


def _clean(value) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


LABELS = {
    'предмет закупки': 'title', 'наименование закупки': 'title',
    'наименование объекта закупки': 'title',
    'заказчик': 'customer', 'наименование заказчика': 'customer',
    'начальная цена': 'nmck', 'начальная цена контракта': 'nmck',
    'начальная (максимальная) цена контракта': 'nmck',
    'начальная (максимальная) цена договора': 'nmck', 'нмцк': 'nmck',
    'закон': 'law', 'правовая основа': 'law',
    'окончание подачи заявок': 'application_due',
    'прием заявок до': 'application_due', 'приём заявок до': 'application_due',
    'дата окончания подачи заявок': 'application_due',
    'дата и время окончания подачи заявок': 'application_due',
    'место поставки': 'supply_address', 'адрес поставки': 'supply_address',
}


def _label_value_pairs(soup):
    # Semantic definition/table rows survive visual redesigns and do not require
    # a hidden API or executing scripts from the external page.
    for label in soup.find_all(['dt', 'th']):
        sibling = label.find_next_sibling(['dd', 'td'])
        if sibling:
            yield label.get_text(' ', strip=True), sibling.get_text(' ', strip=True)
    # Common public card layouts also use a short span/div label beside its value.
    for label in soup.find_all(['span', 'div', 'label', 'strong']):
        if label.find(['div', 'dt', 'dd', 'table', 'section']):
            continue
        key = _clean(label.get_text(' ', strip=True)).strip(' :').lower()
        if key not in LABELS:
            continue
        sibling = label.find_next_sibling()
        if sibling:
            yield key, sibling.get_text(' ', strip=True)


def _meaningful_title(value: str, number: str) -> str:
    value = _clean(value)
    value = re.sub(r'\s*[|—–]\s*Контур[.\s]*Закупки.*$', '', value, flags=re.I)
    value = re.sub(r'^(?:закупка|тендер|извещение)\s*[№#]?\s*' + number + r'\s*[:—–-]?\s*', '', value, flags=re.I)
    if (not value or len(value) < 5 or re.fullmatch(r'[№#\s:—–-]*' + number, value) or
            value.lower() in ('контур.закупки', 'авторизация', 'вход', 'доступ ограничен', 'страница не найдена')):
        return ''
    return value[:1000]


def _structured_cards(soup, number):
    """Read standard public JSON-LD, never execute JS or assume a private schema."""
    for script in soup.find_all('script', attrs={'type':'application/ld+json'}):
        raw = script.string or script.get_text()
        if not raw or len(raw) > MAX_PAGE_BYTES:
            continue
        try:
            decoded = json.loads(raw)
        except (ValueError, TypeError, RecursionError):
            continue
        candidates = decoded if isinstance(decoded, list) else [decoded]
        for candidate in candidates[:100]:
            if not isinstance(candidate, dict):
                continue
            expanded = candidate.get('@graph', []) if '@graph' in candidate else [candidate]
            if not isinstance(expanded, list):
                continue
            for item in expanded[:100]:
                if not isinstance(item, dict):
                    continue
                kind = item.get('@type')
                if kind not in ('Product', 'CreativeWork', 'Dataset', 'Article'):
                    continue
                identifier = item.get('identifier') or item.get('sku')
                if isinstance(identifier, dict): identifier = identifier.get('value')
                if str(identifier or '') == number:
                    yield item


def parse_secondary_page(data: bytes, number: str, page_url: str | None = None) -> dict:
    """Extract only labelled values and actual links from one exact-number card."""
    number = normalize_notice(number)
    page_url = page_url or kontur_page_url(number)
    if not _card_url(page_url, number):
        raise ValueError('Ответ вторичного источника относится к другой карточке')
    if not data or len(data) > MAX_PAGE_BYTES:
        raise ValueError('Пустой или слишком большой ответ вторичного источника')
    soup = BeautifulSoup(data, 'html.parser')
    og_title = soup.find('meta', attrs={'property':'og:title'})
    structured = list(_structured_cards(soup, number))
    for script in soup(['script', 'style', 'noscript']):
        script.decompose()
    visible = soup.get_text(' ', strip=True)
    if not re.search(r'(?<![0-9])' + number + r'(?![0-9])', visible) and not structured:
        raise ValueError('Номер закупки не подтверждён на странице вторичного источника')
    values = {}
    for label, value in _label_value_pairs(soup):
        field = LABELS.get(_clean(label).strip(' :').lower())
        value = _clean(value)
        if field and value:
            values.setdefault(field, set()).add(value)
    for item in structured:
        if isinstance(item.get('name'), str) and _meaningful_title(item['name'], number):
            values.setdefault('title', set()).add(_meaningful_title(item['name'], number))
        # Product.offers.price can mean an offer or awarded price, not НМЦК.
        # Only an explicitly labelled public PropertyValue has that meaning.
        properties = item.get('additionalProperty') or []
        if isinstance(properties, dict): properties = [properties]
        if not isinstance(properties, list): continue
        for prop in properties[:100]:
            if not isinstance(prop, dict): continue
            field = LABELS.get(_clean(prop.get('name')).strip(' :').lower())
            value = prop.get('value')
            if field and isinstance(value, (str, int, float)) and not isinstance(value, bool):
                values.setdefault(field, set()).add(_clean(value))
    # H1 is the public card's own title. Never replace an explicit ambiguous
    # subject with an unrelated sidebar title or a marketing description.
    if 'title' not in values:
        headlines = [_meaningful_title(h.get_text(' ', strip=True), number) for h in soup.find_all('h1')]
        headlines = {h for h in headlines if h}
        if len(headlines) == 1:
            values['title'] = headlines
        elif not headlines and og_title:
            headline = _meaningful_title(og_title.get('content') or '', number)
            if headline:
                values['title'] = {headline}
    notice = {'number':number, 'verified':True,
              'verification':'exact_number_secondary', 'source_kind':'secondary'}
    for field, candidates in values.items():
        if len(candidates) != 1:
            continue
        value = next(iter(candidates))
        if field == 'nmck':
            money = re.fullmatch(r'([0-9][0-9\s]*(?:[,.][0-9]{1,2})?)\s*(?:₽|руб\.?|RUB|российский рубль)?', value, re.I)
            if money:
                notice[field] = re.sub(r'\s+', '', money[1]).replace(',', '.')
        elif field == 'application_due':
            when = re.fullmatch(r'([0-9]{2}\.[0-9]{2}\.[0-9]{4})(?:\s+([0-9]{2}:[0-9]{2}))?(?:\s*\(МСК(?:[+-][0-9]+)?\))?', value, re.I)
            if when:
                try:
                    parsed = datetime.strptime(when[1] + (' ' + when[2] if when[2] else ''),
                                               '%d.%m.%Y %H:%M' if when[2] else '%d.%m.%Y')
                    notice['application_due_on'] = parsed.date().isoformat()
                    if when[2] and 'МСК' not in value.upper():
                        notice['application_due_time'] = when[2]
                except ValueError:
                    pass
        elif field == 'law':
            law = re.fullmatch(r'(44|223)\s*[-–]?\s*ФЗ', value, re.I)
            if law:
                notice[field] = law[1] + '-ФЗ'
        else:
            notice[field] = value[:1000]
    notice['fields_fetched'] = [key for key in LABELS.values() if key in notice]
    if 'application_due_on' in notice:
        notice['fields_fetched'].append('application_due_on')
        if 'application_due_time' in notice: notice['fields_fetched'].append('application_due_time')
    notice['fields_fetched'] = list(dict.fromkeys(notice['fields_fetched']))
    documents, seen = [], set()
    candidates = [(a['href'], a.get_text(' ', strip=True) or a.get('download'), a.has_attr('download'))
                  for a in soup.find_all('a', href=True)]
    for item in structured:
        media = item.get('associatedMedia') or item.get('encoding') or []
        if isinstance(media, dict): media = [media]
        if not isinstance(media, list): continue
        for entry in media[:MAX_DOCUMENTS + 1]:
            if isinstance(entry, dict) and isinstance(entry.get('contentUrl'), str):
                candidates.append((entry['contentUrl'], entry.get('name'), True))
    for href, title, explicit_download in candidates:
        link = urljoin(page_url, href)
        if not _safe_https(link, PUBLIC_DOCUMENT_HOSTS):
            continue
        path = unquote(urlsplit(link).path).lower()
        if not (path.endswith(FILE_SUFFIXES) or explicit_download or
                any(part in path for part in ('/filestore/', '/download/', '/downloadfile', '/document/download', '/fileview'))):
            continue
        if link in seen:
            continue
        seen.add(link)
        documents.append({'url':link, 'title':_clean(title)[:200] or 'Документ закупки',
                          'source_page':page_url, 'source_name':SOURCE_NAME})
    return {'notice':notice if notice['fields_fetched'] else None,
            'documents':documents[:MAX_DOCUMENTS], 'found':len(documents),
            'limit_reached':len(documents) > MAX_DOCUMENTS,
            'available':bool(notice['fields_fetched'] or documents),
            'source_url':page_url, 'source_name':SOURCE_NAME, 'source_kind':'secondary'}


def lookup_secondary(number: str, opener=None) -> dict:
    """Attempt the public secondary card once. Never ask for site credentials."""
    number = normalize_notice(number)
    url = kontur_page_url(number)
    opener = opener or build_secondary_opener(number)
    try:
        request = Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; QXDesktop/4.0)',
                                       'Accept':'text/html,application/xhtml+xml', 'Accept-Encoding':'identity'})
        with opener.open(request, timeout=8) as response:
            final_url = response.geturl()
            if not _card_url(final_url, number):
                raise ValueError('Вторичный источник перенаправил на другую карточку или страницу входа')
            mime = str(response.headers.get('Content-Type', '')).lower()
            if mime and 'html' not in mime:
                raise ValueError('Вторичный источник вернул не страницу закупки')
            payload = response.read(MAX_PAGE_BYTES + 1)
        result = parse_secondary_page(payload, number, final_url)
        result['message'] = ('Получены сведения из вторичного источника Контур.Закупки. Сверьте их с ЕИС; условия контракта не подтверждены.'
                             if result['available'] else 'Вторичный источник не предоставил доступных подписанных полей или документов.')
        return result
    except (HTTPError, URLError, OSError, ValueError, TimeoutError, IncompleteRead) as error:
        return {'available':False, 'notice':None, 'documents':[], 'found':0,
                'source_url':url, 'source_name':SOURCE_NAME, 'source_kind':'secondary',
                'error_type':type(error).__name__, 'http_status':getattr(error, 'code', None),
                'message':'Вторичный источник недоступен или не предоставил проверяемую открытую карточку. Закрытые документы и страницы входа не загружаются.'}


def _fetch_secondary_document(url, opener, budget):
    """Retrieve bounded bytes; shared storage validates the actual file format."""
    from modern.eis_document_download import _filename, _infer_suffix, MAX_FILE, MAX_NETWORK
    from modern.tender_package import ACCEPTED
    url = public_document_url(url)
    timeout = min(14, budget['deadline'] - monotonic())
    if timeout <= 0 or budget['bytes'] >= MAX_TOTAL_BYTES:
        raise ValueError('Достигнут общий лимит загрузки документов вторичного источника')
    request = Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; QXDesktop/4.0)',
                                   'Accept':'application/octet-stream,application/zip,application/pdf,*/*',
                                   'Accept-Encoding':'identity'})
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = public_document_url(response.geturl())
            mime = str(response.headers.get('Content-Type', '')).split(';')[0].lower().strip()
            if mime in ('text/html', 'application/xhtml+xml') or mime.startswith(('image/', 'application/javascript')):
                raise ValueError('Источник вернул страницу входа или HTML вместо документа')
            name = _filename(response, final_url)
            suffix = Path(name).suffix.lower()
            infer_name = suffix in ('', '.html', '.htm')
            if not infer_name and suffix not in ACCEPTED | {'.zip'}:
                raise ValueError('Формат документа вторичного источника не поддерживается')
            maximum = MAX_NETWORK if suffix == '.zip' or infer_name else MAX_FILE
            length = response.headers.get('Content-Length')
            if length:
                try: declared = int(length)
                except (TypeError, ValueError): raise ValueError('Некорректный размер ответа вторичного источника')
                if declared < 0 or declared > maximum:
                    raise ValueError('Документ вторичного источника превышает допустимый размер')
                if declared > MAX_TOTAL_BYTES - budget['bytes']:
                    raise ValueError('Достигнут общий лимит загрузки документов вторичного источника')
            chunks, total = [], 0
            while True:
                if monotonic() >= budget['deadline']:
                    raise ValueError('Достигнут лимит времени загрузки документов вторичного источника')
                piece = response.read(min(1024 * 1024, maximum + 1 - total,
                                          MAX_TOTAL_BYTES + 1 - budget['bytes']))
                if not piece:
                    break
                total += len(piece)
                budget['bytes'] += len(piece)
                if total > maximum:
                    raise ValueError('Документ вторичного источника превышает допустимый размер')
                if budget['bytes'] > MAX_TOTAL_BYTES:
                    raise ValueError('Достигнут общий лимит загрузки документов вторичного источника')
                chunks.append(piece)
            payload = b''.join(chunks)
            if not payload:
                raise ValueError('Вторичный источник вернул пустой файл')
            if infer_name:
                suffix = _infer_suffix(payload, mime)
                if not suffix:
                    raise ValueError('Формат документа вторичного источника определить безопасно не удалось')
                name = 'Документ_Контур_' + hashlib.sha256(payload).hexdigest()[:12] + suffix
            if suffix != '.zip' and len(payload) > MAX_FILE:
                raise ValueError('Документ вторичного источника больше 30 МБ')
            return name, payload
    except (HTTPError, URLError, OSError, TimeoutError, IncompleteRead) as error:
        raise ValueError('Источник не выдал открытый файл; возможно, требуется вход или доступ по подписке') from error


def import_secondary_documents(tender_id: str, documents: list[dict], opener=None) -> dict:
    """Import actual links previously discovered on this tender's secondary page.

    Not exposed as a generic URL download API. Both source-page identity and
    destination host are checked again. Signed URLs are never included in audit
    records or failure messages. Successfully saved files survive later failures.
    """
    from modern import tender_store as store
    from modern.eis_document_download import (
        import_downloaded_document, fetch_official_document, build_official_opener, _DOWNLOAD_BUDGET,
    )
    tender = store.get(tender_id)
    if not tender: raise KeyError('Закупка не найдена')
    number = normalize_notice(tender.get('number') or '')
    if not isinstance(documents, list):
        raise ValueError('Некорректный список документов вторичного источника')
    secondary_opener = opener or build_opener(_AttachmentRedirects(), HTTPCookieProcessor(CookieJar()))
    official_opener = opener or build_official_opener()
    budget = {'bytes':0, 'deadline':monotonic() + MAX_DOWNLOAD_SECONDS}
    token = _DOWNLOAD_BUDGET.set(budget)
    imported, duplicates, warnings, ignored, failures = [], [], [], [], []
    seen, successful = set(), 0
    limit_reached = len(documents) > MAX_DOCUMENTS
    try:
        for index, item in enumerate(documents[:MAX_DOCUMENTS], 1):
            if monotonic() >= budget['deadline'] or budget['bytes'] >= MAX_TOTAL_BYTES:
                limit_reached = True
                failures.extend({'line':line, 'reason':'Достигнут общий лимит загрузки вторичного источника'}
                                for line in range(index, min(len(documents), MAX_DOCUMENTS) + 1))
                break
            try:
                if not isinstance(item, dict) or not _card_url(item.get('source_page') or '', number):
                    raise ValueError('Документ не подтверждён на странице выбранной закупки')
                url = public_document_url(item.get('url'))
                if url in seen:
                    continue
                seen.add(url)
                if urlsplit(url).hostname == 'zakupki.gov.ru':
                    name, payload = fetch_official_document(url, opener=official_opener)
                    source = SOURCE_NAME + ' — ссылка на файл ЕИС'
                else:
                    name, payload = _fetch_secondary_document(url, secondary_opener, budget)
                    source = SOURCE_NAME
                result = import_downloaded_document(tender_id, name, payload, source_label=source)
                imported.extend(result.get('imported') or [])
                duplicates.extend(result.get('duplicates') or [])
                warnings.extend(result.get('warnings') or [])
                ignored.extend(result.get('ignored') or [])
                successful += 1
            except (ValueError, OSError, TypeError, IncompleteRead) as error:
                reason = str(error)
                if 'http://' in reason or 'https://' in reason:
                    reason = 'Не удалось обработать открытый документ вторичного источника'
                failures.append({'line':index, 'reason':reason[:230]})
                if monotonic() >= budget['deadline'] or budget['bytes'] >= MAX_TOTAL_BYTES:
                    limit_reached = True
    finally:
        _DOWNLOAD_BUDGET.reset(token)
    return {'imported':imported, 'duplicates':duplicates, 'warnings':warnings,
            'ignored':ignored, 'failures':failures, 'failed_count':len(failures),
            'success_count':successful, 'found':len(documents),
            'limit_reached':limit_reached,
            'complete':bool(documents) and not failures and not ignored and not limit_reached,
            'documents':store.detail(tender_id)['documents'], 'source':SOURCE_NAME,
            'message':'Загрузка из вторичного источника завершена. Подлинность условий сверяйте с ЕИС.'}
