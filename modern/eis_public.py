"""Best-effort lookup of a notice in the *public* EIS RSS search feed.

EIS public pages may reject automated requests or change format.  This module is
not an authenticated EIS integration and NEVER treats a returned RSS item as
proof of contract execution, winner, price, or status.  Nothing is persisted
until the user explicitly confirms it.
"""
from __future__ import annotations

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, HTTPRedirectHandler, build_opener
import re

HOST = 'zakupki.gov.ru'
RSS_PATH = '/epz/order/extendedsearch/rss.html'
SEARCH_PATH = '/epz/order/extendedsearch/results.html'
MAX_RESPONSE = 2 * 1024 * 1024
NOTICE = re.compile(r'^(?:[0-9]{11}|[0-9]{19,20})$')


def network_error_type(exc):
    """Expose an actionable status without logging URLs, headers or credentials."""
    if isinstance(exc,HTTPError): return 'HTTP' + str(exc.code)
    reason = getattr(exc,'reason',None)
    if reason is not None and type(reason).__name__ in ('SSLError','SSLCertVerificationError'):
        return 'TLSVerificationError'
    return type(exc).__name__


def validate_notice(value: str) -> str:
    value = str(value or '').strip()
    if not NOTICE.fullmatch(value):
        raise ValueError('Введите номер извещения ЕИС из 11, 19 или 20 цифр')
    return value


def official_search_url(number: str) -> str:
    number = validate_notice(number)
    path = '/epz/order/extendedsearch/results.html'
    return f'https://{HOST}{path}?' + urlencode({'searchString': number})


def rss_search_url(number: str) -> str:
    return f'https://{HOST}{RSS_PATH}?' + urlencode({'searchString': validate_notice(number)})


def _is_official_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme == 'https' and p.hostname == HOST and not p.username and not p.password and p.port in (None,443)
    except (ValueError, TypeError):
        return False


class _SafeRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_official_url(newurl):
            raise ValueError('ЕИС перенаправила запрос на посторонний сайт')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _leaf_value(element, tag):
    for child in element:
        if child.tag.rsplit('}',1)[-1].lower() == tag.lower():
            if tag == 'link' and child.attrib.get('href'):
                return child.attrib['href']
            return ''.join(child.itertext()).strip()
    return ''


def _clean(value, limit=280):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]{0,200}>', ' ', str(value or ''))).strip()[:limit]


def parse_public_rss(data: bytes, number: str):
    """Return exact-number RSS matches only; never infer contract fields."""
    number = validate_notice(number)
    if len(data) > MAX_RESPONSE:
        raise ValueError('Ответ RSS ЕИС превышает допустимый размер')
    root = ET.fromstring(data)
    if root.tag.rsplit('}',1)[-1].lower() not in ('rss','feed','rdf'):
        raise ValueError('ЕИС вернула не RSS/XML-ленту; автоматическое получение недоступно')
    items = []
    for el in root.iter():
        if el.tag.rsplit('}',1)[-1].lower() not in ('item','entry'):
            continue
        title = _clean(_leaf_value(el,'title'))
        desc = _clean(_leaf_value(el,'description') or _leaf_value(el,'summary'),1000)
        link = _leaf_value(el,'link').strip()
        guid = _leaf_value(el,'guid') or _leaf_value(el,'id')
        # Never accept a similarly numbered procurement or unrelated result.
        if not any(re.search(r'(?<!\d)'+re.escape(number)+r'(?!\d)', t or '') for t in (title,desc,link,guid)):
            continue
        # The item mentioning the correct number is NOT enough: the link may
        # point to some other procurement on the genuine EIS host. Only use
        # direct links with the exact notice number in a documented query field.
        try:
            parsed_link = urlparse(link)
            q = parse_qs(parsed_link.query)
            linked_numbers = q.get('regNumber', []) + q.get('purchaseNumber', [])
            direct_notice = (_is_official_url(link) and number in linked_numbers and
                             len(linked_numbers) == 1)
        except (ValueError, TypeError):
            direct_notice = False
        valid_link = link if direct_notice else official_search_url(number)
        row = {'notice_number':number, 'title':title or 'Закупка № '+number,
               'description':desc[:300], 'url':valid_link,
               'link_verified':bool(direct_notice),
               'published':_clean(_leaf_value(el,'pubDate') or _leaf_value(el,'published'),100)}
        if row not in items:
            items.append(row)
        if len(items) >= 8:
            break
    return items


def lookup_notice(number: str, opener=None):
    number = validate_notice(number)
    search = official_search_url(number)
    rss = rss_search_url(number)
    if opener is None:
        opener = build_opener(_SafeRedirects())
    req = Request(rss, headers={'User-Agent':'QXPodborshchik/4.0 (public RSS; user initiated)',
                                'Accept':'application/rss+xml, application/xml, text/xml',
                                'Accept-Encoding':'identity'})
    try:
        with opener.open(req, timeout=7) as response:
            body = response.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE:
                raise ValueError('Публичная RSS-выдача ЕИС слишком велика')
        records = parse_public_rss(body, number)
        return {'available':True, 'matches':records, 'search_url':search,
                'message':'Найдено точное совпадение в публичной RSS-выдаче. Данные нужно проверить в ЕИС.' if records else
                          'Публичная RSS-выдача получена, точное совпадение не обнаружено. Проверьте поиск в ЕИС.',
                'source':'Публичная RSS-выдача ЕИС (не официальный API)'}
    except (HTTPError, URLError, OSError, ValueError, ET.ParseError, DefusedXmlException) as exc:
        # EIS frequently restricts automated access. Never imply success.
        return {'available':False, 'matches':[], 'search_url':search,
                'message':'Автоматически получить данные из ЕИС не удалось. Откройте официальный поиск или добавьте документацию вручную.',
                'source':'Публичная RSS-выдача ЕИС (недоступна)',
                'error_type':network_error_type(exc)}

# Public print-form XML is not a guaranteed API: EIS may block it or change its
# schema. Every extracted value must have a clear official XML element and an
# exact purchase number in the same document. Fail closed on ambiguity.
XML_NOTICE_PATH = '/epz/order/notice/printForm/viewXml.html'


def _notice_xml_root(data: bytes):
    if len(data) > MAX_RESPONSE: raise ValueError('Извещение ЕИС превышает допустимый размер')
    try:
        root = ET.fromstring(data)
        if root.tag.rsplit('}',1)[-1].lower() != 'html': return root
    except ET.ParseError:
        if b'<pre' not in data[:20000].lower(): raise
    # Some print-form responses wrap escaped source XML in an HTML <pre>.
    # Read that element only; never execute scripts or flatten an arbitrary page.
    from bs4 import BeautifulSoup
    pre = BeautifulSoup(data,'html.parser').find('pre')
    if not pre: raise ValueError('ЕИС вернула HTML вместо XML извещения')
    payload = pre.get_text().strip().encode('utf-8')
    if not payload.startswith(b'<'): raise ValueError('В печатной форме нет XML извещения')
    return ET.fromstring(payload)

def parse_notice_metadata(xml: bytes, number: str) -> dict:
    """Read only identified fields from a public EIS document; no AI guesses."""
    number = validate_notice(number)
    if len(xml) > MAX_RESPONSE:
        raise ValueError('Извещение ЕИС превышает допустимый размер')
    root = _notice_xml_root(xml)
    names = {}
    for el in root.iter():
        tag = el.tag.rsplit('}', 1)[-1].lower()
        # A simple text-only leaf, not the flattened text of whole XML sections.
        if list(el):
            continue
        value = (el.text or '').strip()
        if value:
            names.setdefault(tag, []).append(value)
    number_names = ('purchasenumber', 'notificationnumber', 'notice_number')
    numbers = {v for tag in number_names for v in names.get(tag, [])}
    if not numbers:
        numbers = set(names.get('regnumber', []))
    notice_223 = []
    if len(number) == 11:
        registrations = set()
        for node in root.iter():
            if node.tag.rsplit('}',1)[-1].lower() != 'purchasenoticedata': continue
            identifiers = [child for child in node if child.tag.rsplit('}',1)[-1].lower() == 'registrationnumber']
            registrations.update((child.text or '').strip() for child in identifiers)
            if len(identifiers) == 1 and (identifiers[0].text or '').strip() == number:
                notice_223.append(node)
        if not numbers: numbers = registrations
    if numbers != {number}:
        raise ValueError('Ответ ЕИС не содержит точного номера извещения')

    def unique(*tags, limit=500):
        values = {re.sub(r'\s+', ' ', v).strip() for tag in tags for v in names.get(tag, []) if v.strip()}
        return next(iter(values))[:limit] if len(values) == 1 else ''

    info = {
        'number': number,
        'title': unique('purchasename', 'purchaseobjectinfo', 'subject', 'objectinfo'),
        'customer': unique('fullname', 'customerfullname'),
        'nmck': '',
        'application_due_on': '',
        'application_due_time': '',
        'law': '',
    }
    if notice_223 and not info['title']:
        titles = [(child.text or '').strip() for child in notice_223[0]
                  if child.tag.rsplit('}',1)[-1].lower() == 'name']
        if len(titles) == 1: info['title'] = titles[0][:500]
    # Prefer a precise customer node over broad 'fullName' (which can include
    # a contact or an organizer). Never assign it from multiple candidates.
    customers=[]
    for el in root.iter():
        if el.tag.rsplit('}',1)[-1].lower() not in ('customer','customerinfo','customerorganization'):
            continue
        for item in el.iter():
            if item is el: continue
            if item.tag.rsplit('}',1)[-1].lower() in ('fullname', 'customerfullname', 'organizationname') and not list(item):
                v=(item.text or '').strip()
                if v: customers.append(v)
    if len(set(customers)) == 1:
        info['customer'] = customers[0][:500]
    elif len(set(customers)) > 1:
        info['customer'] = ''
    else:
        info['customer'] = unique('customerfullname')
    raw_price = unique('maxprice', 'maxpricetotal', 'initialsum', 'initialmaxcontractprice')
    if raw_price and re.fullmatch(r'\d+(?:[,.]\d{1,2})?', raw_price.replace(' ', '')):
        info['nmck'] = raw_price.replace(' ', '').replace(',', '.')
    date_raw = unique('enddate', 'submissionclosedate', 'enddateapplication', 'enddateapplications', 'enddt')
    m = re.fullmatch(r'(\d{4}-\d{2}-\d{2})(?:[T ](\d\d:\d\d)(?::\d\d)?)?(?:Z|[+-]\d\d:?\d\d)?', date_raw)
    if m:
        from datetime import date as _date
        try:
            _date.fromisoformat(m.group(1))
            info['application_due_on'] = m.group(1)
            if (m.group(2) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', m.group(2)) and
                    not date_raw.endswith('Z') and not re.search(r'[+-]\d\d:?\d\d$', date_raw)):
                info['application_due_time'] = m.group(2)
        except ValueError:
            pass
    for prefix, tags in (('auction', ('auctiondate', 'auctiondatetime')),
                         ('results', ('summarizingdate', 'resultsdate'))):
        value = unique(*tags)
        match = re.fullmatch(r'(\d{4}-\d{2}-\d{2})(?:[T ]([0-2]\d:[0-5]\d)(?::\d\d)?)?(?:Z|[+-]\d\d:?\d\d)?', value)
        if match:
            from datetime import date as _date
            try:
                _date.fromisoformat(match.group(1))
                info[prefix + '_on'] = match.group(1)
                if match.group(2) and match.group(2)[:2] < '24' and not value.endswith('Z') and not re.search(r'[+-]\d\d:?\d\d$', value):
                    info[prefix + '_time'] = match.group(2)
            except ValueError:
                pass
    for field, tags in (('supply_address', ('deliveryplace', 'supplyaddress')),
                        ('payment_terms', ('paymentterms',)), ('warranty', ('warrantyrequirements',))):
        value = unique(*tags, limit=1000)
        if value:
            info[field] = value
    law = unique('federallaw', 'purchaselaw', 'law')
    if law in ('44', '44-ФЗ', '44-FZ', '223', '223-ФЗ', '223-FZ'):
        info['law'] = '223-ФЗ' if law.startswith('223') else '44-ФЗ'
    # Do not treat a conversion from UTC to local tender time as certain.
    # The root's generic name is not sufficient to infer 44-ФЗ or 223-ФЗ.
    info['fields_fetched'] = [k for k,v in info.items() if v and k != 'number']
    info['verified'] = True  # XML notice number matched; not contract status.
    return info


def extract_xml_document_links(xml: bytes, number: str, *, base_url='https://zakupki.gov.ru/') -> list[dict]:
    """Source-declared attachment URLs from an exact-number verified XML notice."""
    parse_notice_metadata(xml,number)
    root = _notice_xml_root(xml)
    from modern.eis_resolver import official_https_url
    records, seen = [], set()
    for section in root.iter():
        if section.tag.rsplit('}',1)[-1].lower() not in ('attachments','attachmentlist'):
            continue
        for document in section.iter():
            if document.tag.rsplit('}',1)[-1].lower() not in ('document','attachment','attachmentinfo'): continue
            values = {}
            for child in document:
                if not list(child): values[child.tag.rsplit('}',1)[-1].lower()] = (child.text or '').strip()
            raw_url = values.get('url') or values.get('downloadurl')
            if not raw_url: continue
            try: url = official_https_url(raw_url,base_url,upgrade_http=True)
            except (ValueError,TypeError): continue
            if url in seen: continue
            seen.add(url)
            records.append({'url':url,'title':(values.get('filename') or values.get('description') or 'Документ ЕИС')[:200],
                            'source_page':base_url})
            if len(records) >= 81: return records
    return records


def fetch_notice_metadata(number: str, opener=None) -> dict:
    """Fetch public EIS XML for one explicit user-supplied number, at most 7 sec."""
    number = validate_notice(number)
    search = official_search_url(number)
    if len(number) == 11:
        return {'available':False, 'notice':None, 'source_url':search, 'search_url':search,
                'message':'Для 223-ФЗ публичный XML по номеру не поддерживается. QX проверит открытые страницы и документы; отсутствующие поля можно заполнить вручную.',
                'error_type':'UnsupportedPublicXML'}
    url = 'https://' + HOST + XML_NOTICE_PATH + '?' + urlencode({'regNumber':number})
    opener = opener or build_opener(_SafeRedirects())
    req = Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; QX desktop)',
                                'Accept':'application/xml, text/xml, */*',
                                'Accept-Encoding':'identity'})
    try:
        with opener.open(req, timeout=7) as response:
            data = response.read(MAX_RESPONSE+1)
        if len(data) > MAX_RESPONSE:
            raise ValueError('Слишком большой ответ ЕИС')
        result = parse_notice_metadata(data, number)
        documents = extract_xml_document_links(data,number,base_url=url)
        return {'available':True,'notice':result,'source_url':url,
                'documents':documents[:40], 'document_limit':40, 'documents_limit_reached':len(documents)>40,
                'search_url':search,'message':'Поля получены из публичного XML ЕИС по точному номеру. Проверьте актуальную редакцию извещения.'}
    except (HTTPError, URLError, OSError, ValueError, ET.ParseError, DefusedXmlException) as exc:
        return {'available':False,'notice':None,'source_url':url,'search_url':search,
                'message':'ЕИС не предоставила проверяемую XML-карточку. Введите сведения вручную либо откройте официальный поиск.',
                'error_type':network_error_type(exc)}
