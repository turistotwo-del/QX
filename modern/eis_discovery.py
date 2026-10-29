"""Conservative, user-initiated discovery of public EIS files by notice number.

No credentials/captcha bypass, no unofficial mirror crawling, no forged direct links.
Never silently edits contract fields: only imports bounded and verified attachments.
"""
from __future__ import annotations

from bs4 import BeautifulSoup
from urllib.request import Request, build_opener
from urllib.parse import urljoin, urlsplit, parse_qs, urlencode
from urllib.error import HTTPError, URLError
import re
from time import monotonic

from modern.eis_public import validate_notice, official_search_url, lookup_notice, network_error_type
from modern.eis_document_download import validate_document_url, OfficialRedirects, import_official_documents, document_source_label
from modern import tender_store
from modern.eis_resolver import is_notice_context, resolve_notice_pages, official_https_url

ROOT = 'https://zakupki.gov.ru'
MAX_PAGE = 2 * 1024 * 1024
MAX_PAGES = 4
MAX_DOCS = 40
MAX_DISCOVERY_SECONDS = 24


def _is_notice_context(url: str, number: str, bound_urls=()) -> bool:
    """Only follow official notice/document pages referring to exact purchase number."""
    return is_notice_context(url, number, bound_urls)


def _is_file_candidate(url: str, label: str) -> bool:
    """Not every link is a file: accept actual file links or download endpoints."""
    p = urlsplit(url)
    path = p.path.lower()
    query = p.query.lower()
    if any(path.endswith(ext) for ext in ('.doc', '.docx', '.pdf', '.xlsx', '.xls', '.xlsm', '.xml', '.odt', '.rtf', '.txt', '.zip', '.rar', '.7z')):
        return True
    return (any(key in path for key in ('/filestore/', '/download/', '/downloadfile', '/getfile', '/filedownload', '/file/download'))
            or (path.endswith('/file.html') and 'uid' in parse_qs(p.query))
            or path.endswith('/printform/viewxml.html')
            or ('download' in path and ('file' in path or 'document' in path)))


def extract_page_links(page: bytes, base_url: str, notice_number: str) -> tuple[list[dict], list[str]]:
    """Parse only conventional public anchor links; do not evaluate page scripts."""
    notice_number = validate_notice(notice_number)
    soup = BeautifulSoup(page, 'html.parser')
    links, next_pages = [], []
    for a in soup.select('a[href], [data-url], [data-href], [data-download-url]'):
        href = (a.get('data-download-url') or a.get('data-url') or a.get('data-href') or a.get('href') or '').strip()
        if not href or href.startswith(('#', 'javascript:', 'data:')):
            continue
        try:
            url = official_https_url(href,base_url)
        except (ValueError,TypeError):
            continue
        text = ' '.join(a.stripped_strings)[:160] or 'Документ ЕИС'
        if _is_notice_context(url, notice_number, bound_urls=(base_url,)) and 'documents' in urlsplit(url).path.lower():
            if url not in next_pages: next_pages.append(url)
        if _is_file_candidate(url, text) and not a.find_parent('footer'):
            links.append({'url': url, 'title': text, 'source_page': base_url})
    return links[:50], next_pages[:8]


def notice_documents_url(source_url: str, number: str) -> str | None:
    """Documented sibling tab of an already resolved, number-confirmed card."""
    parsed = urlsplit(source_url)
    if not _is_notice_context(source_url,number,bound_urls=(source_url,)) or not parsed.path.endswith('/common-info.html'):
        return None
    from urllib.parse import urlunsplit
    return urlunsplit((parsed.scheme,parsed.netloc,parsed.path[:-len('common-info.html')]+'documents.html',parsed.query,''))


def discover_public_documents(notice_number: str, *, opener=None, entry_urls=None) -> dict:
    """Return *unverified* preview links from public HTML, without importing files.

    A page is trusted only if it contains the exact notice number in visible text
    or is the notice-specific documents page. Network errors are surfaced.
    """
    number = validate_notice(notice_number)
    from modern.eis_document_download import build_official_opener
    opener = opener or build_official_opener()
    notice_path = ('/223/purchase/public/purchase/info/common-info.html' if len(number) == 11
                   else '/epz/order/notice/view/common-info.html')
    initial = entry_urls if entry_urls is not None else [ROOT + notice_path + '?' + urlencode({'regNumber':number})]
    started = monotonic()
    resolution_errors = []
    if entry_urls is None:
        resolved = resolve_notice_pages(number, opener=opener)
        resolution_errors = resolved['errors']
        if resolved['notice_urls']:
            initial = resolved['notice_urls']
    queue = list(initial)
    bound_urls = tuple(initial)
    seen = set()
    found = {}
    errors = list(resolution_errors)
    while queue and len(seen) < MAX_PAGES and len(found) < MAX_DOCS and monotonic() - started < MAX_DISCOVERY_SECONDS:
        url = queue.pop(0)
        if url in seen: continue
        seen.add(url)
        if not _is_notice_context(url, number, bound_urls):
            continue
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0 QXDesktop/4.0',
                                        'Accept':'text/html, application/xhtml+xml', 'Accept-Encoding': 'identity'})
            with opener.open(req, timeout=max(.1, min(8, MAX_DISCOVERY_SECONDS - (monotonic() - started)))) as resp:
                final = resp.geturl()
                if not _is_notice_context(final, number, bound_urls):
                    raise ValueError('ЕИС перенаправила на постороннюю страницу')
                mime = str(resp.headers.get('Content-Type','')).lower()
                if mime and not ('html' in mime):
                    raise ValueError('Вместо страницы ЕИС получен другой формат')
                payload = resp.read(MAX_PAGE + 1)
            if len(payload) > MAX_PAGE:
                raise ValueError('Страница ЕИС слишком велика')
            soup = BeautifulSoup(payload, 'html.parser')
            for node in soup(['script', 'style']): node.decompose()
            readable = soup.get_text(' ', strip=True)
            if not re.search(r'(?<!\d)' + re.escape(number) + r'(?!\d)', readable):
                raise ValueError('Номер закупки не подтверждён на странице')
            links, next_pages = extract_page_links(payload, final, number)
            sibling = notice_documents_url(final,number)
            if sibling and not next_pages and sibling not in seen:
                next_pages.append(sibling)
            for item in links:
                if item['url'] not in found:
                    found[item['url']] = item
            queue.extend(x for x in next_pages if x not in seen and x not in queue)
        except (HTTPError, URLError, OSError, ValueError, TimeoutError) as exc:
            errors.append(network_error_type(exc))
    limit_reached = bool(queue) or len(found) > MAX_DOCS
    return {
        'notice_number': number, 'documents': list(found.values())[:MAX_DOCS],
        'found': len(found), 'checked_pages': len(seen),
        'available': bool(found), 'source':'Публичные страницы ЕИС; ссылки требуют проверки при скачивании',
        'search_url': official_search_url(number),
        'message': ('Найдены ссылки на документы. Перед импортом QX проверит формат файлов и не скачает страницы входа.'
                    if found else 'Публичные ссылки на документы не найдены или ЕИС ограничила доступ. Откройте ЕИС вручную.'),
        'errors': errors[:MAX_PAGES],
        'limit_reached': limit_reached, 'document_limit': MAX_DOCS,
        'complete': not errors and not limit_reached,
    }


def discover_for_tender(tender_id: str, *, opener=None) -> dict:
    item = tender_store.get(tender_id)
    if not item: raise KeyError('Закупка не найдена')
    number = validate_notice(item.get('number') or '')
    return discover_public_documents(number, opener=opener)


def discover_and_import(tender_id: str, *, opener=None, discovered=None) -> dict:
    """Explicit button action: discovery followed by a capped, validated download."""
    details = discovered if discovered is not None else discover_for_tender(tender_id, opener=opener)
    item = tender_store.get(tender_id)
    if not item: raise KeyError('Закупка не найдена')
    number = validate_notice(item.get('number') or '')
    if details.get('notice_number') != number:
        raise ValueError('Список найденных файлов относится к другой закупке')
    urls = [x['url'] for x in details.get('documents', [])][:MAX_DOCS]
    if not urls:
        return {**details, 'imported':[], 'duplicates':[], 'warnings':[], 'failed_count':0, 'success_count':0,
                'documents': tender_store.detail(tender_id)['documents']}
    with document_source_label('zakupki.gov.ru (автопоиск по номеру закупки)'):
        if len(urls) <= 10:
            result = import_official_documents(tender_id, urls, opener=opener)
        else:
            result = import_official_documents(tender_id, urls, opener=opener, max_urls=MAX_DOCS)
    result.update({'found':details.get('found',0), 'checked_pages':details.get('checked_pages',0),
                   'search_url': details.get('search_url'), 'source':'Автопоиск публичных документов ЕИС',
                   'discovery_errors': details.get('errors', []),
                   'limit_reached': details.get('limit_reached',False) or result.get('limit_reached',False),
                   'document_limit': MAX_DOCS,
                   'complete': (details.get('complete',False) and bool(details.get('found')) and
                                not result.get('failed_count') and not result.get('limit_reached') and not result.get('ignored'))})
    return result
