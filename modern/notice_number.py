"""Canonical purchase numbers from typed numbers or an explicitly pasted card URL.

This module deliberately has no network or third-party dependencies: creating a
local draft must work even while provider packages are missing from an old runtime.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlsplit

NUMBER = re.compile(r'(?:[0-9]{11}|[0-9]{19,20})\Z')
TOKEN = re.compile(r'(?<![0-9])(?:[0-9]{19,20}|[0-9]{11})(?![0-9])')
INPUT_HOSTS = {'zakupki.gov.ru', 'www.zakupki.gov.ru', 'zakupki.kontur.ru'}


def normalize_notice(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Введите номер закупки или ссылку на карточку ЕИС')
    text = value.strip()
    if NUMBER.fullmatch(text):
        return text
    if '://' in text:
        try:
            parsed = urlsplit(text)
            if (parsed.scheme not in ('https', 'http') or parsed.hostname not in INPUT_HOSTS
                    or parsed.username or parsed.password or parsed.port not in (None, 80, 443)):
                raise ValueError('Используйте ссылку ЕИС или Контур.Закупок с номером извещения')
            query = parse_qs(parsed.query)
            candidates = [entry for key in ('regNumber', 'purchaseNumber', 'registrationNumber', 'searchString')
                          for entry in query.get(key, []) if NUMBER.fullmatch(entry)]
            if not candidates and parsed.hostname == 'zakupki.kontur.ru':
                candidates = TOKEN.findall(unquote(parsed.path))
            if len(set(candidates)) == 1:
                return candidates[0]
        except (ValueError, UnicodeError):
            pass
        raise ValueError('В ссылке не найден единственный номер извещения ЕИС. Скопируйте сам номер.')
    # Copying from a card often includes a number sign or non-breaking spaces.
    compact = re.sub(r'\s+', '', text.lstrip('№#').strip())
    if NUMBER.fullmatch(compact):
        return compact
    match = re.fullmatch(r'(?:закупка|извещение|номер(?:\s+закупки|\s+извещения)?)\s*[№#:]?\s*([0-9]{11}|[0-9]{19,20})', text, re.I)
    if match:
        return match[1]
    raise ValueError('Номер извещения должен содержать 11, 19 или 20 цифр. Можно вставить ссылку на карточку ЕИС.')
