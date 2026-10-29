from __future__ import annotations

from dataclasses import dataclass
import re
import xml.etree.ElementTree as ET

import requests

CBR_XML_URL = 'https://www.cbr.ru/scripts/XML_daily.asp'


@dataclass
class RateInfo:
    rate: float
    date: str
    live: bool
    error: str = ''

    def to_dict(self):
        return {'rate': self.rate, 'date': self.date, 'live': self.live, 'error': self.error}


def fetch_usd_rate(timeout: int = 6) -> RateInfo:
    headers = {'User-Agent': 'Mozilla/5.0 QX-Selector/1.0'}
    resp = requests.get(CBR_XML_URL, headers=headers, timeout=timeout)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    date = root.attrib.get('Date', '')
    for valute in root.findall('Valute'):
        if (valute.findtext('CharCode') or '').strip().upper() != 'USD':
            continue
        nominal = float((valute.findtext('Nominal') or '1').replace(',', '.'))
        value = float((valute.findtext('Value') or '0').replace(',', '.'))
        if nominal <= 0 or value <= 0:
            raise ValueError('ЦБ РФ вернул некорректный курс USD')
        return RateInfo(rate=value / nominal, date=date, live=True)
    raise ValueError('USD не найден в ответе ЦБ РФ')


def get_usd_rate(cached_rate: float, cached_date: str = '', timeout: int = 6) -> RateInfo:
    try:
        return fetch_usd_rate(timeout=timeout)
    except Exception as exc:
        rate = float(cached_rate or 0)
        if rate <= 0:
            rate = 86.8872
        return RateInfo(rate=rate, date=str(cached_date or '04.09.2026'), live=False, error=str(exc))


def buffered_rate(rate: float, buffer_rub: float = 5.0) -> float:
    return float(rate or 0) + float(buffer_rub or 0)


def _number(text: str) -> float:
    s = str(text or '').strip().replace('\xa0', ' ')
    # Remove currency words/symbols and thousands separators, preserve decimal comma/dot.
    s = re.sub(r'(?i)usd|долл(?:ар(?:а|ов)?)?|руб(?:\.|ля|лей)?|₽|\$', '', s)
    s = s.strip().replace(' ', '')
    if not s:
        return 0.0
    # Russian comma decimal; if both comma and dot exist, comma is treated as thousands only
    # when it has exactly 3 digits after it and dot occurs later.
    if ',' in s and '.' not in s:
        s = s.replace(',', '.')
    elif ',' in s and '.' in s:
        s = s.replace(',', '')
    m = re.search(r'-?\d+(?:\.\d+)?', s)
    return float(m.group(0)) if m else 0.0


def parse_price_input(value, usd_rate: float, buffer_rub: float = 5.0):
    """Return (rubles, currency, note) for manual price input.

    Accepted examples: 15000, "15 000", "$100", "100 $", "USD 100", "100 usd".
    USD conversion deliberately uses CBR USD + configurable RUB reserve per dollar.
    """
    if value is None:
        return 0.0, 'RUB', ''
    if isinstance(value, (int, float)):
        return max(0.0, float(value)), 'RUB', ''
    raw = str(value).strip()
    is_usd = bool(re.search(r'(?i)\$|\busd\b|долл', raw))
    amount = max(0.0, _number(raw))
    if not is_usd:
        return amount, 'RUB', ''
    used = buffered_rate(usd_rate, buffer_rub)
    rub = amount * used
    note = f'${amount:g} × ({float(usd_rate):.4f} + {float(buffer_rub):g}) = {rub:.2f} ₽'
    return rub, 'USD', note
