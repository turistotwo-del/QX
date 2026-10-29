"""Explainable, offline estimate of the work needed to prepare a TZ response.

Version 2: technical score <20 simple, 20..44 medium, >=45 complex. The score is
the sum of distinct documented factors, capped at 100. Missing/poor source
recognition overrides the label to unknown while retaining observed factors.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import math
import re

from core.tz_parser import Requirements

DEFAULTS = asdict(Requirements())
LABELS = {'simple':'Простое', 'medium':'Среднее', 'complex':'Сложное', 'unknown':'Недостаточно данных'}
DISCLAIMER = 'Оценка трудоёмкости технической части по распознанным характеристикам. Реестры, сертификаты и подтверждающие документы показаны отдельно и не повышают сложность.'
MAX_TEXT = 2_000_000
MAX_POSITIONS = 500
EXCLUDED = {'title','item_name','ktru_code','quantity','nmck','product_type','raw_text',
            'equipment_profile_name','monitor_catalog_item','keyboard_catalog_item','mouse_catalog_item',
            'keyboard_source_mode','mouse_source_mode','system_case_mode','aio_platform_mode',
            'manual_requirements','monitor_resolution_is_min','monitor_response_ms_max_inclusive','warranty_months_min'}
ALIASES = {'ram_type_min_generation':'ram_type','need_os':'os','os_text':'os',
           'ssd_m2_required':'ssd_interface','ssd_25_required':'ssd_interface'}
PRODUCT = re.compile(r'системн\w*\s+блок|моноблок|монитор|клавиатур|мыш[ьиь]|компьютер|рабоч\w*\s+станци|сервер|ноутбук',re.I)
RULES = (
    ('russian_registry','Нужна проверка включения продукции в российский реестр',10,
     r'реестр\w*.{0,60}(?:российск\w*|радиоэлектронн\w*|промышленн\w*|минпромторг)|(?:минпромторг|гисп).{0,45}(?:реестр|заключени)|реестров\w*\s+(?:номер|запис)'),
    ('russian_bios','Требуется подтверждение российского или реестрового BIOS',12,
     r'(?:российск\w*|реестров\w*)\s+(?:\w+\s+){0,3}(?:bios|биос)|(?:bios|биос).{0,60}(?:российск\w*|реестр)'),
    ('special_certification','Нужны специальные сертификаты ФСТЭК/ФСБ',14,
     r'сертифика(?:т|ц)\w*.{0,45}(?:фстэк|фсб)|(?:фстэк|фсб).{0,45}сертифика(?:т|ц)'),
    ('fixed_model','Ограничен выбор эквивалента или конкретной модели',12,
     r'эквивалент\w*\s+не\s+допуска|без\s+(?:возможности\s+)?замен\w*\s+модел|строг\w*.{0,35}(?:модель|марк\w*|артикул)'),
    ('special_software','Нужно проверить специализированную ОС и программное обеспечение',8,
     r'astra\s*linux|астра\s+линукс|ред\s*ос|альт\s+(?:линукс|рабоч\w*|сервер)|криптопро|средств\w*\s+криптографическ'),
    ('compatibility','Есть отдельные требования совместимости или интеграции',12,
     r'совместим\w*.{0,90}(?:операционн|информационн|astra|астра|ред\s*ос|linux|программ|существующ|инфраструктур|домен|драйвер)|интеграц\w*.{0,65}(?:существующ|систем|инфраструктур)'),
    ('deployment','Нужны дополнительные работы по настройке или развёртыванию',8,
     r'(?:установк\w*|настройк\w*|разверт\w*|миграци\w*).{0,65}(?:домен|сети|крипт|информационн|образ\w*\s+ос|пользовательск)'),
)


TECHNICAL_RULES = {'fixed_model', 'compatibility', 'deployment'}
ADDITIONAL_RULES = tuple(rule for rule in RULES if rule[0] in {'russian_registry','russian_bios','special_certification'}) + (
    ('conformity_documents', 'Требуются документы о соответствии', 0,
     r'декларац\w*\s+соответствия|сертификат\w*\s+соответствия|подтверждающ\w*\s+документ'),
    ('origin_documents', 'Требуется подтверждение страны происхождения', 0,
     r'сертификат\w*.{0,20}ст[-– ]?1|подтвержден\w*.{0,30}стран\w*.{0,20}происхожден'),
    ('supplier_authorization', 'Есть требования к полномочиям или лицензиям поставщика', 0,
     r'авторизационн\w*\s+письм|лицензи\w*.{0,45}(?:поставщик|фстэк|фсб)|(?:поставщик|участник).{0,45}лицензи'),
    ('delivery_conditions', 'Указаны отдельные условия поставки', 0,
     r'срок\w*\s+поставки\s*[:—–-]?\s*(?:не\s+более\s+|до\s+)?\d|поставк\w*.{0,30}в\s+течени\w*\s+\d'),
    ('warranty_conditions', 'Указаны гарантийные условия', 0,
     r'гаранти\w*.{0,45}\d+\s*(?:месяц|мес\b|лет|год)|сервисн\w*\s+центр'),
)
NONTECHNICAL = re.compile(r'реестр|реестров|сертификат|сертификац|декларац|фстэк|фсб|лицензи|авторизацион|гаранти|срок.{0,15}поставк|обеспечени.{0,25}(?:заявк|контракт)', re.I)


def _norm(value):
    return re.sub(r'\s+',' ',str(value or '').replace('ё','е').replace('\xa0',' ')).strip().lower()


def _number(value):
    if isinstance(value,bool): return None
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (ValueError,TypeError,OverflowError): return None


def _active(key,value):
    if key in EXCLUDED or key not in DEFAULTS or key.startswith(('custom_','extra_')): return False
    default=DEFAULTS[key]
    if value is None or value == '' or value == default: return False
    if isinstance(default,bool): return value is True and default is False
    if isinstance(value,bool): return default is None  # explicit absence is a constraint
    if isinstance(value,(int,float)): return _number(value) is not None and value > 0
    return isinstance(value,str) and bool(value.strip())


def _negated(clause,match):
    before=clause[max(0,match.start()-55):match.start()]
    after=clause[match.end():match.end()+70]
    return bool(re.search(r'(?:не\s+требу\w*|не\s+обязател\w*|не\s+предусмотр\w*|без|при\s+наличии|по\s+желанию)\s+(?:\w+\s+){0,3}$',before)
                or re.search(r'^[\s:|—–-]*(?:не\s+(?:требу|обяз|предусмотр)|необяз|нет\b|отсутств|при\s+наличии|по\s+желанию)',after))


def _conflicts(reqs):
    conflicts=[]
    pairs=[(f'case_{axis}_min_mm',f'case_{axis}_max_mm',f'{name} корпуса')
           for axis,name in [('width','Ширина'),('length','Длина'),('height','Высота')]]
    pairs += [('monitor_brightness_min','monitor_brightness_max','Яркость монитора'),
              ('keyboard_cable_min_m','keyboard_cable_max_m','Длина кабеля клавиатуры'),
              ('mouse_cable_min_m','mouse_cable_max_m','Длина кабеля мыши')]
    for index,req in enumerate(reqs,1):
        title=str(req.get('title') or f'Позиция {index}')[:80]
        if req.get('forbid_wireless') is True and any(req.get(k) is True for k in ('need_wifi','need_bluetooth','keyboard_wireless','mouse_wireless')):
            conflicts.append(f'{title}: беспроводная связь одновременно запрещена и требуется')
        for low,high,label in pairs:
            a,b=_number(req.get(low)),_number(req.get(high))
            if a is not None and b is not None and a > b:
                conflicts.append(f'{title}: {label} — минимум {a:g} больше указанного максимума {b:g}')
    return list(dict.fromkeys(conflicts))


def assess_complexity(text, reqs, characteristics=None):
    """Estimate response preparation effort; input objects are never modified.

    Quantity and source length never add difficulty points. Distinct rules are
    counted once per document. Structured technical keys count once per position.
    """
    rows=[]
    for req in reqs if isinstance(reqs,(list,tuple)) else []:
        if is_dataclass(req): req=asdict(req)
        if isinstance(req,dict): rows.append(dict(req))
    limited=len(rows)>MAX_POSITIONS
    rows=rows[:MAX_POSITIONS]
    source=text if isinstance(text,str) else ''
    if not source.strip():
        source='\n'.join(str(r.get('raw_text') or '') for r in rows)
    limited=limited or len(source)>MAX_TEXT
    source=source[:MAX_TEXT]
    clauses=list(dict.fromkeys(_norm(line) for line in re.split(r'[\n;]+|(?<=[.!?])\s+',source) if line.strip()))
    per_position=[{ALIASES.get(k,k) for k,v in req.items() if _active(k,v)} for req in rows]
    structured=sum(len(keys) for keys in per_position)
    manual=set()
    for req in rows:
        values=req.get('manual_requirements') or []
        if isinstance(values,str): values=[values]
        if isinstance(values,(list,tuple)):
            manual.update(_norm(part) for v in values if isinstance(v,str) for part in re.split(r'[;\n]+', v) if part.strip() and not NONTECHNICAL.search(part))
    chars=set()
    for row in characteristics if isinstance(characteristics,(list,tuple)) else []:
        if not isinstance(row,dict): continue
        name=_norm(row.get('name'))
        value=_norm(row.get('original_value',row.get('value')))
        if name and value and not NONTECHNICAL.search(name): chars.add((str(row.get('plan_index',0)),name,value))
    constraints=max(structured,len(chars))
    kinds={str(req.get('product_type')) for req,keys in zip(rows,per_position)
           if req.get('product_type') and (keys or PRODUCT.search(str(req.get('title') or '')+' '+str(req.get('item_name') or '')))}
    missing_quantity=sum(_number(req.get('quantity')) is None or (_number(req.get('quantity')) or 0)<=0 for req in rows)
    conflicts=_conflicts(rows)
    factors=[]

    def add(key,label,points,evidence=None):
        factor={'key':key,'label':label,'points':int(points)}
        if evidence: factor['evidence']=[str(v)[:220] for v in evidence[:4]]
        factors.append(factor)

    if conflicts: add('conflicts','Найдены возможные противоречия: нужна ручная проверка',min(55,45+5*(len(conflicts)-1)),conflicts)
    n=len(rows)
    if n:
        points=0 if n==1 else 6 if n==2 else 12 if n<=5 else 20 if n<=10 else 28
        add('positions',f'Позиций в ТЗ: {n}',points)
    if len(kinds)>1: add('product_types',f'Разных типов оборудования: {len(kinds)}',6 if len(kinds)==2 else 10,sorted(kinds))
    if constraints:
        points=0 if constraints<=5 else 6 if constraints<=10 else 12 if constraints<=20 else 18 if constraints<=35 else 24
        add('technical_constraints',f'Отдельных технических ограничений: {constraints}',points)
    additional=[]
    for key,label,points,pattern in ADDITIONAL_RULES:
        rx=re.compile(pattern,re.I)
        hits=[clause for clause in clauses if any(not _negated(clause,m) for m in rx.finditer(clause))]
        if hits: additional.append({'key':key, 'label':label, 'evidence':[hit[:220] for hit in hits[:3]]})
    for key,label,points,pattern in RULES:
        if key not in TECHNICAL_RULES: continue
        rx=re.compile(pattern,re.I)
        hits=[clause for clause in clauses if not NONTECHNICAL.search(clause) and any(not _negated(clause,m) for m in rx.finditer(clause))]
        if hits: add(key,label,points,hits)
    bounds={key for req in rows for key,value in req.items() if _active(key,value) and '_max' in key}
    if bounds: add('upper_bounds',f'Жёстких верхних ограничений параметров: {len(bounds)}',min(12,len(bounds)*2))
    ports={key for req in rows for key,value in req.items() if _active(key,value) and any(part in key for part in ('usb','hdmi','displayport','_dp_','ethernet','pcie','m2_key'))}
    if len(ports)>=3: add('interface_combination',f'Нужно согласовать разные интерфейсы и порты: {len(ports)}',min(12,(len(ports)-2)*2))
    exact={key for req in rows for key in ('cpu_model','monitor_catalog_item') if req.get(key)}
    if exact: add('specified_models','Указаны конкретные модели технических компонентов',6)
    if manual: add('manual_review',f'Отдельных требований для ручной проверки: {len(manual)}',4 if len(manual)<=2 else 8 if len(manual)<=5 else 12,sorted(manual))
    unmapped=max(0,len(chars)-structured)
    if unmapped: add('unmapped_characteristics',f'Характеристик сверх структурированных полей: {unmapped}',4 if unmapped<=5 else 8)
    recognition='sufficient'
    source_letters=sum(ch.isalpha() for ch in source)
    bad_text=bool(source) and source.count('\ufffd')>max(3,len(source)*.03)
    insufficient=not rows or source_letters<4 or bad_text or not constraints
    if insufficient:
        recognition='insufficient'
        add('recognition','Недостаточно распознанных данных для надёжной оценки',0)
    elif limited:
        recognition='limited'
        add('recognition','Объём данных превышает предел оценки; нужен просмотр полного ТЗ',0)
    if missing_quantity: add('missing_quantity',f'Не указано или не распознано количество у позиций: {missing_quantity}',0)
    score=min(100,sum(f['points'] for f in factors))
    level='unknown' if insufficient or limited else 'simple' if score<20 else 'medium' if score<45 else 'complex'
    reasons=[f['label'] for f in factors]
    return {'version':2,'scope':'technical','additional_requirements':additional,'level':level,'label':LABELS[level],'score':score,'reasons':reasons,
            'factors':factors,'metrics':{'positions':n,'product_types':len(kinds),'product_type_names':sorted(kinds),
            'technical_constraints':constraints,'structured_constraints':structured,'characteristics':len(chars),
            'manual_requirements':len(manual),'unmapped_characteristics':unmapped,'contradictions':len(conflicts),
            'missing_quantity':missing_quantity,'recognition':recognition,'source_limited':limited,
            'unique_source_clauses':len(clauses)},'disclaimer':DISCLAIMER}
