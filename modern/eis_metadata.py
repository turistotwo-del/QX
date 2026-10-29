"""Read labelled facts on public EIS cards when the XML print form is unavailable."""
from __future__ import annotations

from datetime import datetime
import re
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup
from time import monotonic

from modern.eis_public import validate_notice, official_search_url
from modern.eis_discovery import _is_notice_context, ROOT, MAX_PAGE
from modern.eis_document_download import OfficialRedirects
from modern.eis_resolver import resolve_notice_pages


def notice_page_url(number: str) -> str:
    number = validate_notice(number)
    path = ('/223/purchase/public/purchase/info/common-info.html' if len(number) == 11
            else '/epz/order/notice/view/common-info.html')
    return ROOT + path + '?regNumber=' + number


def parse_notice_html(data: bytes, number: str) -> dict:
    """Accept explicit label/value pairs only. Never infer customer from organizer."""
    number = validate_notice(number)
    if len(data) > MAX_PAGE:
        raise ValueError('Слишком большая страница ЕИС')
    soup = BeautifulSoup(data, 'html.parser')
    for el in soup(['script', 'style', 'noscript']):
        el.decompose()
    text = soup.get_text(' ', strip=True)
    if not re.search(r'(?<!\d)' + re.escape(number) + r'(?!\d)', text):
        raise ValueError('Номер закупки не подтверждён на странице ЕИС')
    labels = {
        'наименование объекта закупки': 'title', 'наименование закупки': 'title',
        'заказчик': 'customer', 'наименование заказчика': 'customer',
        'начальная (максимальная) цена контракта': 'nmck',
        'начальная (максимальная) цена договора': 'nmck',
        'дата и время окончания срока подачи заявок': 'application_due',
        'дата и время окончания подачи заявок': 'application_due',
        'дата и время проведения электронного аукциона': 'auction',
        'дата подведения итогов определения поставщика (подрядчика, исполнителя)': 'results',
        'место поставки товара, выполнения работы или оказания услуги': 'supply_address',
    }
    values = {}
    # Both current and older public EIS layouts use these section markers.
    for section in soup.select('.cardMainInfo__section, .blockInfo__section, .sectionInfo'):
        label = section.select_one('.cardMainInfo__title, .section__title, .sectionInfo__title')
        content = section.select_one('.cardMainInfo__content, .section__info, .sectionInfo__body')
        if not label or not content:
            continue
        key = re.sub(r'\s+', ' ', label.get_text(' ', strip=True)).strip(' :').lower()
        field = labels.get(key)
        value = re.sub(r'\s+', ' ', content.get_text(' ', strip=True)).strip()
        if field and value:
            values.setdefault(field, set()).add(value)
    result = {'number':number, 'verified':True}
    for key, candidates in values.items():
        if len(candidates) != 1:
            continue
        value = next(iter(candidates))
        if key == 'nmck':
            price = re.fullmatch(r'([\d\s]+(?:[,.]\d{1,2})?)\s*(?:₽|руб\.?|российский рубль)?', value, re.I)
            if price:
                result[key] = re.sub(r'\s+', '', price[1]).replace(',', '.')
        elif key in ('application_due', 'auction', 'results'):
            match = re.fullmatch(r'(\d{2}\.\d{2}\.\d{4})(?:\s+(\d{2}:\d{2}))?(?:\s*\(МСК(?:[+-]\d+)?\))?', value, re.I)
            if match:
                try:
                    parsed = datetime.strptime(match[1] + (' ' + match[2] if match[2] else ''),
                                               '%d.%m.%Y %H:%M' if match[2] else '%d.%m.%Y')
                    result[key + '_on'] = parsed.date().isoformat()
                    # The card schema has no zone. Never silently reinterpret a
                    # time published with an explicit EIS zone as machine-local.
                    if match[2] and 'МСК' not in value.upper(): result[key + '_time'] = match[2]
                except ValueError:
                    pass
        else:
            result[key] = value[:1000]
    result['fields_fetched'] = [k for k in result if k not in ('number', 'verified', 'fields_fetched')]
    if not result['fields_fetched']:
        raise ValueError('На странице нет однозначных подписанных полей закупки')
    return result


def fetch_notice_html_metadata(number: str, opener=None) -> dict:
    number = validate_notice(number)
    url = notice_page_url(number)
    opener = opener or build_opener(OfficialRedirects())
    deadline = monotonic() + 20
    resolution = resolve_notice_pages(number, opener=opener)
    candidates = resolution['notice_urls'] or [url]
    errors = list(resolution['errors'])
    for candidate in candidates[:2]:
        if monotonic() >= deadline:
            errors.append('TimeoutError')
            break
        try:
            req = Request(candidate, headers={'User-Agent':'Mozilla/5.0 QXDesktop/4.0',
                                             'Accept':'text/html', 'Accept-Encoding':'identity'})
            with opener.open(req, timeout=max(.1, min(8, deadline - monotonic()))) as response:
                final_url = response.geturl()
                if not _is_notice_context(final_url, number):
                    raise ValueError('ЕИС перенаправила на другую закупку')
                payload = response.read(MAX_PAGE + 1)
            return {'available':True, 'notice':parse_notice_html(payload, number),
                    'source_url':final_url, 'search_url':official_search_url(number),
                    'message':'Получены однозначные подписанные поля публичной карточки ЕИС. Время с явным часовым поясом не подставляется; проверьте его в ЕИС.'}
        except (HTTPError, URLError, OSError, ValueError, TimeoutError) as exc:
            errors.append(type(exc).__name__)
    return {'available':False, 'notice':None, 'source_url':url,
            'search_url':official_search_url(number), 'error_type':errors[-1] if errors else 'NoVerifiedFields',
            'errors':errors,
            'message':'ЕИС не предоставила проверяемые поля карточки. Можно открыть официальный поиск и прикрепить документы вручную.'}
