"""Resolve an existing official notice URL; never guess the procurement-type path."""
from __future__ import annotations

from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qs
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup

from modern.eis_public import validate_notice, official_search_url, _is_official_url, network_error_type
from modern.eis_document_download import validate_document_url, build_official_opener
import re

MAX_SEARCH_BYTES = 2 * 1024 * 1024


def official_https_url(value: str, base_url: str, *, upgrade_http=False) -> str:
    """Old published XML may contain HTTP links: request HTTPS only, same host."""
    url = urljoin(base_url, value.strip())
    parsed = urlsplit(url)
    if upgrade_http and parsed.scheme == 'http' and parsed.hostname == 'zakupki.gov.ru' and not parsed.username and not parsed.password and parsed.port in (None,80):
        url = urlunsplit(('https','zakupki.gov.ru',parsed.path,parsed.query,''))
    return validate_document_url(url)


def _notice_path(path):
    return path.startswith(('/epz/order/notice/', '/223/purchase/public/purchase/info/'))


def is_notice_context(url: str, number: str, bound_urls=()) -> bool:
    try:
        validate_document_url(url)
        parsed = urlsplit(url)
        if not _notice_path(parsed.path): return False
        query = parse_qs(parsed.query)
        numbers = query.get('regNumber',[]) + query.get('purchaseNumber',[])
        if numbers: return numbers == [number]
        # ID-only 223 links are trusted only after the exact-number search card
        # bound that ID to this number. The fetched card must confirm it again.
        for bound in bound_urls:
            b = urlsplit(bound)
            if not _notice_path(b.path): continue
            bq = parse_qs(b.query)
            for key in ('purchaseId','noticeInfoId'):
                if (len(query.get(key,[])) == 1 and query[key] == bq.get(key) and
                        re.fullmatch(r'[0-9]{1,20}',query[key][0])):
                    return True
        return False
    except (ValueError, TypeError):
        return False


def extract_notice_urls(data: bytes, base_url: str, number: str) -> list[str]:
    number = validate_notice(number)
    if len(data) > MAX_SEARCH_BYTES:
        raise ValueError('Слишком большая поисковая страница ЕИС')
    soup = BeautifulSoup(data, 'html.parser')
    urls = []
    for anchor in soup.find_all('a', href=True):
        try: candidate = official_https_url(anchor['href'],base_url)
        except (ValueError, TypeError): continue
        exact_context = is_notice_context(candidate, number)
        if not exact_context:
            card = anchor.find_parent(class_='search-registry-entry-block')
            visible = (card or anchor).get_text(' ',strip=True)
            if re.search(r'(?<!\d)' + re.escape(number) + r'(?!\d)',visible):
                exact_context = is_notice_context(candidate, number, bound_urls=(candidate,))
        if (exact_context and
                'common-info' in urlsplit(candidate).path and candidate not in urls):
            urls.append(candidate)
    return urls[:3]


def resolve_notice_pages(number: str, opener=None) -> dict:
    number = validate_notice(number)
    search = official_search_url(number)
    opener = opener or build_official_opener()
    try:
        req = Request(search, headers={'User-Agent':'Mozilla/5.0 QXDesktop/4.0',
                                      'Accept':'text/html', 'Accept-Encoding':'identity'})
        with opener.open(req, timeout=7) as response:
            final = response.geturl()
            if not _is_official_url(final):
                raise ValueError('ЕИС перенаправила поиск на посторонний сайт')
            payload = response.read(MAX_SEARCH_BYTES + 1)
        return {'notice_urls':extract_notice_urls(payload, final, number),
                'search_url':search, 'errors':[]}
    except (HTTPError, URLError, OSError, ValueError, TimeoutError) as exc:
        return {'notice_urls':[], 'search_url':search, 'errors':[network_error_type(exc)]}
