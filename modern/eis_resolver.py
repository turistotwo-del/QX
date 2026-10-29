"""Resolve an existing official notice URL; never guess the procurement-type path."""
from __future__ import annotations

from urllib.parse import urljoin, urlsplit, parse_qs
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup

from modern.eis_public import validate_notice, official_search_url, _is_official_url
from modern.eis_document_download import validate_document_url, OfficialRedirects

MAX_SEARCH_BYTES = 2 * 1024 * 1024


def is_notice_context(url: str, number: str) -> bool:
    try:
        validate_document_url(url)
        parsed = urlsplit(url)
        return (parsed.path.startswith(('/epz/order/notice/', '/223/purchase/public/purchase/info/'))
                and parse_qs(parsed.query).get('regNumber', []) == [number])
    except (ValueError, TypeError):
        return False


def extract_notice_urls(data: bytes, base_url: str, number: str) -> list[str]:
    number = validate_notice(number)
    if len(data) > MAX_SEARCH_BYTES:
        raise ValueError('Слишком большая поисковая страница ЕИС')
    soup = BeautifulSoup(data, 'html.parser')
    urls = []
    for anchor in soup.find_all('a', href=True):
        candidate = urljoin(base_url, anchor['href'])
        if (is_notice_context(candidate, number) and
                'common-info' in urlsplit(candidate).path and candidate not in urls):
            urls.append(candidate)
    return urls[:3]


def resolve_notice_pages(number: str, opener=None) -> dict:
    number = validate_notice(number)
    search = official_search_url(number)
    opener = opener or build_opener(OfficialRedirects())
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
        return {'notice_urls':[], 'search_url':search, 'errors':[type(exc).__name__]}
