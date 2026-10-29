import re
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup

CODE_RE = re.compile(r'^\d{2}\.\d{2}\.\d{2}\.\d{3}-\d{8}$')


def validate_code(code: str):
    code = (code or '').strip()
    if not CODE_RE.match(code):
        raise ValueError('Код КТРУ должен выглядеть как 26.20.15.000-00000028')
    return code


def official_url(code: str):
    code = validate_code(code)
    return f'https://zakupki.gov.ru/epz/ktru/ktruCard/commonInfo.html?itemId={quote(code)}'


def fetch_reference(code: str, timeout=15):
    """Best-effort online KTRU reference.

    Actual tender-selected values still come from the uploaded TЗ. This lookup is
    used as a dictionary of catalog names/characteristics and links to the EIS card.
    """
    code = validate_code(code)
    headers = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36'}
    sources = [
        ('moy-zakupki.ru', f'https://moy-zakupki.ru/ktru/{code}/'),
        ('Агрегатор ЕАТ', f'https://ktru.agregatoreat.ru/catalog/ktru/{code}'),
    ]
    last_error = None
    for source, url in sources:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code >= 400:
                raise RuntimeError(f'HTTP {resp.status_code}')
            soup = BeautifulSoup(resp.text, 'html.parser')
            h1 = soup.find('h1')
            name = h1.get_text(' ', strip=True) if h1 else f'КТРУ {code}'
            text = ' '.join(soup.stripped_strings)
            # Gather recognizable characteristic labels without relying on fragile CSS.
            labels = []
            known = [
                'Объем установленной оперативной памяти','Тип оперативной памяти','Количество ядер процессора',
                'Количество потоков процессора','Частота процессора базовая','Частота процессора максимальная',
                'Объем накопителя SSD','Объем накопителя HDD','Беспроводная связь','Диагональ экрана',
                'Разрешение экрана','Мощность блока питания','Количество слотов M.2 Key M','Количество слотов M.2 Кеу E',
                'Наличие установленного дискретного графического контроллера','Объем дискретной видеопамяти',
                'Сетевой интерфейс 8P8C (RJ-45)','Технология изготовления матрицы дисплея'
            ]
            for label in known:
                if label.lower() in text.lower(): labels.append(label)
            return {'code':code,'name':name,'source':source,'source_url':url,'official_url':official_url(code),'characteristics':labels}
        except Exception as e:
            last_error = e
    raise RuntimeError(f'Не удалось загрузить справочник КТРУ: {last_error}')
