from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from io import BytesIO
import re
import zipfile
import posixpath
import xml.etree.ElementTree as ET
from typing import Dict, Iterable, List, Tuple

from .user_catalog import list_items, get_item, save_item


_PRICE_HEADERS = {
    'ОПТ': ('опт',),
    'РРЦ': ('ррц',),
    'Цена упаковки': ('цена упаковки', 'цена упаковки*'),
}


def _norm(value) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip()).casefold()


def normalize_sku(value) -> str:
    return re.sub(r'[^0-9a-zа-яё]+', '', str(value or '').strip().casefold())


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace('\xa0', '').replace(' ', '').replace(',', '.')
    if not text or text.casefold() in {'call', 'по запросу', 'нет', '-', '—'}:
        return None
    m = re.search(r'-?\d+(?:\.\d+)?', text)
    return float(m.group(0)) if m else None


def _to_int(value):
    x = _to_float(value)
    return int(x) if x is not None else 0


def _col_to_num(cell_ref: str) -> int:
    letters = ''.join(ch for ch in str(cell_ref or '') if ch.isalpha()).upper()
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def _xlsx_shared_strings(z: zipfile.ZipFile) -> List[str]:
    try:
        raw = z.read('xl/sharedStrings.xml')
    except KeyError:
        return []
    root = ET.fromstring(raw)
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    out = []
    for si in root.findall(f'{{{ns}}}si'):
        out.append(''.join((t.text or '') for t in si.iter(f'{{{ns}}}t')))
    return out


def _xlsx_cell_value(cell, shared: List[str]):
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ctype = cell.attrib.get('t')
    if ctype == 'inlineStr':
        return ''.join((t.text or '') for t in cell.iter(f'{{{ns}}}t'))
    v = cell.find(f'{{{ns}}}v')
    if v is None or v.text is None:
        return None
    text = v.text
    if ctype == 's':
        try:
            return shared[int(text)]
        except Exception:
            return text
    if ctype == 'b':
        return text == '1'
    try:
        return float(text) if ('.' in text or 'E' in text.upper()) else int(text)
    except Exception:
        return text


def _xlsx_sheets(z: zipfile.ZipFile) -> List[Tuple[str, str]]:
    main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    relns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    rel_root = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    relmap = {r.attrib.get('Id'): r.attrib.get('Target') for r in rel_root}
    out = []
    for sh in wb.findall(f'.//{{{main}}}sheet'):
        rid = sh.attrib.get(f'{{{relns}}}id')
        target = relmap.get(rid) or ''
        if target.startswith('/'):
            path = target.lstrip('/')
        else:
            path = posixpath.normpath(posixpath.join('xl', target))
        out.append((sh.attrib.get('name') or '', path))
    return out


def _xlsx_rows(z: zipfile.ZipFile, sheet_path: str, shared: List[str]):
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    root = ET.fromstring(z.read(sheet_path))
    for row in root.findall(f'.//{{{ns}}}sheetData/{{{ns}}}row'):
        values = {}
        for cell in row.findall(f'{{{ns}}}c'):
            col = _col_to_num(cell.attrib.get('r') or '')
            if col:
                values[col] = _xlsx_cell_value(cell, shared)
        yield int(row.attrib.get('r') or 0), values


def _find_header_rows(rows, scan_rows: int = 20):
    for row_no, values in rows:
        if row_no > scan_rows:
            break
        normalized = {_norm(v): col for col, v in values.items() if _norm(v)}
        if 'код' in normalized and any(x in normalized for x in ('p/n', 'pn')) and 'наименование' in normalized:
            return row_no, normalized
    return None, {}


def _header_col(headers: Dict[str, int], *candidates: str):
    for cand in candidates:
        n = _norm(cand)
        if n in headers:
            return headers[n]
    for key, col in headers.items():
        for cand in candidates:
            n = _norm(cand)
            if key.startswith(n):
                return col
    return None

def _extract_date(sheet_title: str) -> str:
    m = re.search(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})', sheet_title or '')
    if not m:
        return ''
    d, mo, y = m.groups()
    if len(y) == 2:
        y = '20' + y
    try:
        return f'{int(d):02d}.{int(mo):02d}.{int(y):04d}'
    except Exception:
        return ''


def parse_supplier_price_excel(blob: bytes, supplier: str = 'ExeGate', price_mode: str = 'ОПТ') -> Dict:
    """Parse supplier XLSX price list without loading drawings/images.

    The importer auto-detects the table by Код / P/N / Наименование. It was tested
    against the supplied ExeGate 16.09.2026 workbook (main sheet header on row 5), while
    deliberately avoiding fixed sheet names/row numbers so later ExeGate files can vary.
    """
    if not blob:
        raise ValueError('Пустой Excel-файл.')
    with zipfile.ZipFile(BytesIO(blob)) as z:
        shared = _xlsx_shared_strings(z)
        candidates = []
        for sheet_name, sheet_path in _xlsx_sheets(z):
            if not sheet_path or sheet_path not in z.namelist():
                continue
            # Read rows once for header detection. XML is only a few MB even when the workbook
            # contains thousands of embedded product images, which we intentionally ignore.
            rows = list(_xlsx_rows(z, sheet_path, shared))
            header_row, headers = _find_header_rows(iter(rows))
            if not header_row:
                continue
            code_col = _header_col(headers, 'Код')
            pn_col = _header_col(headers, 'P/N', 'PN')
            name_col = _header_col(headers, 'Наименование')
            if not (code_col and pn_col and name_col):
                continue
            product_rows = sum(1 for rn, vals in rows if rn > header_row and (vals.get(code_col) or vals.get(pn_col)))
            candidates.append((product_rows, sheet_name, sheet_path, header_row, headers, rows))
        if not candidates:
            raise ValueError('Не нашёл таблицу с колонками «Код», «P/N» и «Наименование».')
        _, sheet_name, sheet_path, header_row, headers, rows = max(candidates, key=lambda x: x[0])

        code_col = _header_col(headers, 'Код')
        pn_col = _header_col(headers, 'P/N', 'PN')
        name_col = _header_col(headers, 'Наименование')
        url_col = _header_col(headers, 'Ссылка')
        stock_col = _header_col(headers, 'Свободный остаток, шт.', 'Свободный остаток')
        reserve_col = _header_col(headers, 'Резерв, шт.', 'Резерв')
        eta_col = _header_col(headers, 'Ожидаемая дата прихода', 'Ожидаемая дата')
        pack_col = _header_col(headers, 'Цена упаковки', 'Цена упаковки*')
        opt_col = _header_col(headers, 'ОПТ')
        rrp_col = _header_col(headers, 'РРЦ')
        selected_col = {'ОПТ': opt_col, 'РРЦ': rrp_col, 'Цена упаковки': pack_col}.get(price_mode) or opt_col or rrp_col or pack_col
        if not selected_col:
            raise ValueError('Не нашёл ценовую колонку ОПТ / РРЦ / Цена упаковки.')

        items: List[Dict] = []
        for r, vals in rows:
            if r <= header_row:
                continue
            code = vals.get(code_col)
            pn = vals.get(pn_col)
            name = vals.get(name_col)
            if not str(code or '').strip() and not str(pn or '').strip():
                continue
            if not str(name or '').strip():
                continue
            opt = _to_float(vals.get(opt_col)) if opt_col else None
            rrp = _to_float(vals.get(rrp_col)) if rrp_col else None
            pack = _to_float(vals.get(pack_col)) if pack_col else None
            selected = {'ОПТ': opt, 'РРЦ': rrp, 'Цена упаковки': pack}.get(price_mode)
            if selected is None:
                selected = _to_float(vals.get(selected_col))
            items.append({
                'supplier': str(supplier or 'Поставщик').strip(),
                'code': str(code or '').strip(),
                'part_number': str(pn or '').strip(),
                'name': str(name or '').strip(),
                'url': str(vals.get(url_col) or '').strip() if url_col else '',
                'stock': _to_int(vals.get(stock_col)) if stock_col else 0,
                'reserve': _to_int(vals.get(reserve_col)) if reserve_col else 0,
                'eta': str(vals.get(eta_col) or '').strip() if eta_col else '',
                'price_pack_usd': pack,
                'price_opt_usd': opt,
                'price_rrp_usd': rrp,
                'selected_price_usd': selected,
                'selected_price_mode': price_mode,
                'sheet': sheet_name,
                'row': r,
            })

    return {
        'supplier': str(supplier or 'Поставщик').strip(),
        'sheet': sheet_name,
        'price_date': _extract_date(sheet_name),
        'price_mode': price_mode,
        'imported_at': datetime.now().isoformat(timespec='seconds'),
        'item_count': len(items),
        'items': items,
    }

def _item_keys(item: Dict) -> List[str]:
    out = []
    for value in (item.get('part_number'), item.get('code')):
        key = normalize_sku(value)
        if key and key not in out:
            out.append(key)
    return out


def price_index(price_data: Dict) -> Dict[str, Dict]:
    idx: Dict[str, Dict] = {}
    for item in (price_data or {}).get('items') or []:
        for key in _item_keys(item):
            idx[key] = item
    return idx


def lookup_price(price_data: Dict, sku: str):
    key = normalize_sku(sku)
    if not key:
        return None
    return price_index(price_data).get(key)


def compare_price_lists(old_data: Dict | None, new_data: Dict) -> Dict[str, int]:
    old_idx = price_index(old_data or {})
    new_idx = price_index(new_data or {})
    # Compare by unique product identity, preferring P/N when available.
    def canonical_items(data):
        out = {}
        for item in (data or {}).get('items') or []:
            key = normalize_sku(item.get('part_number')) or normalize_sku(item.get('code'))
            if key:
                out[key] = item
        return out
    old = canonical_items(old_data or {})
    new = canonical_items(new_data or {})
    changed = 0
    for key in set(old).intersection(new):
        a = old[key].get('selected_price_usd')
        b = new[key].get('selected_price_usd')
        if a is None and b is None:
            continue
        if a is None or b is None or abs(float(a) - float(b)) > 1e-9:
            changed += 1
    return {
        'new': len(set(new) - set(old)),
        'changed': changed,
        'missing': len(set(old) - set(new)),
        'total': len(new),
        'with_price': sum(1 for x in new.values() if x.get('selected_price_usd') is not None),
    }


def save_supplier_price_list(name: str, data: Dict) -> None:
    save_item('supplier_price_list', str(name or data.get('supplier') or 'Поставщик').strip(), data)


def get_supplier_price_list(name: str):
    rec = get_item('supplier_price_list', name)
    return dict((rec or {}).get('data') or {}) if rec else None


def list_supplier_price_lists() -> List[Dict]:
    return list_items('supplier_price_list')


def _supplier_matches(saved: str, target: str) -> bool:
    return _norm(saved) == _norm(target) and bool(_norm(saved))


def apply_latest_prices_to_profile(profile_data: Dict) -> Tuple[Dict, Dict]:
    """Apply stored supplier price lists to linked board/components by SKU.

    A profile row is linked when it has `supplier` and `supplier_sku`. The resulting
    price_input remains in USD (e.g. "$64.03"), so the normal QX currency engine applies
    the current CBR rate + user's buffer at calculation time.
    """
    data = dict(profile_data or {})
    price_lists = {x['name'].casefold(): dict(x.get('data') or {}) for x in list_supplier_price_lists()}
    cache = {name: price_index(payload) for name, payload in price_lists.items()}
    updated = 0
    missing = []

    def patch(item: Dict, label: str):
        nonlocal updated
        x = dict(item or {})
        supplier = str(x.get('supplier') or '').strip()
        sku = str(x.get('supplier_sku') or '').strip()
        if not supplier or not sku:
            return x
        payload = price_lists.get(supplier.casefold())
        idx = cache.get(supplier.casefold())
        if not payload or not idx:
            missing.append(f'{label}: нет загруженного прайса «{supplier}»')
            return x
        found = idx.get(normalize_sku(sku))
        if not found:
            missing.append(f'{label}: {supplier} / {sku} не найден в прайсе')
            return x
        price = found.get('selected_price_usd')
        if price is None:
            missing.append(f'{label}: {supplier} / {sku} — цена «Call/по запросу»')
            return x
        price_input = f'${float(price):g}'
        if str(x.get('price_input') or '').strip() != price_input:
            updated += 1
        x['price_input'] = price_input
        x['supplier_price_usd'] = float(price)
        x['supplier_price_mode'] = found.get('selected_price_mode') or payload.get('price_mode') or ''
        x['supplier_price_date'] = payload.get('price_date') or ''
        x['supplier_price_name'] = found.get('name') or ''
        x['supplier_code'] = found.get('code') or ''
        x['supplier_part_number'] = found.get('part_number') or ''
        return x

    boards = {}
    for platform, board in dict(data.get('boards') or {}).items():
        boards[platform] = patch(board, f'{platform.upper()}-плата')
    data['boards'] = boards

    components = []
    for i, item in enumerate(list(data.get('components') or []), start=1):
        label = str((item or {}).get('name') or f'компонент {i}')
        components.append(patch(item, label))
    data['components'] = components
    return data, {'updated': updated, 'missing': missing}



def apply_latest_price_to_case(case_data: Dict) -> Tuple[Dict, Dict]:
    data = dict(case_data or {})
    supplier = str(data.get('custom_case_supplier') or '').strip()
    sku = str(data.get('custom_case_supplier_sku') or '').strip()
    if not supplier or not sku:
        return data, {'updated': 0, 'missing': []}
    payload = get_supplier_price_list(supplier)
    if not payload:
        return data, {'updated': 0, 'missing': [f'нет загруженного прайса «{supplier}»']}
    found = lookup_price(payload, sku)
    if not found:
        return data, {'updated': 0, 'missing': [f'{supplier} / {sku} не найден в прайсе']}
    price = found.get('selected_price_usd')
    if price is None:
        return data, {'updated': 0, 'missing': [f'{supplier} / {sku} — цена «Call/по запросу»']}
    value = f'${float(price):g}'
    updated = int(str(data.get('custom_case_price_input') or '').strip() != value)
    data['custom_case_price_input'] = value
    data['custom_case_supplier_price_usd'] = float(price)
    data['custom_case_supplier_price_mode'] = found.get('selected_price_mode') or payload.get('price_mode') or ''
    data['custom_case_supplier_price_date'] = payload.get('price_date') or ''
    data['custom_case_supplier_name'] = found.get('name') or ''
    return data, {'updated': updated, 'missing': []}




def apply_latest_price_to_aio(aio_data: Dict) -> Tuple[Dict, Dict]:
    """Apply the newest supplier XLSX price to a saved monoblock platform."""
    data = dict(aio_data or {})
    supplier = str(data.get('custom_aio_supplier') or '').strip()
    sku = str(data.get('custom_aio_supplier_sku') or '').strip()
    if not supplier or not sku:
        return data, {'updated': 0, 'missing': []}
    payload = get_supplier_price_list(supplier)
    if not payload:
        return data, {'updated': 0, 'missing': [f'нет загруженного прайса «{supplier}»']}
    found = lookup_price(payload, sku)
    if not found:
        return data, {'updated': 0, 'missing': [f'{supplier} / {sku} не найден в прайсе']}
    price = found.get('selected_price_usd')
    if price is None:
        return data, {'updated': 0, 'missing': [f'{supplier} / {sku} — цена «Call/по запросу»']}
    value = f'${float(price):g}'
    updated = int(str(data.get('custom_aio_price_input') or '').strip() != value)
    data['custom_aio_price_input'] = value
    data['custom_aio_supplier_price_usd'] = float(price)
    data['custom_aio_supplier_price_mode'] = found.get('selected_price_mode') or payload.get('price_mode') or ''
    data['custom_aio_supplier_price_date'] = payload.get('price_date') or ''
    data['custom_aio_supplier_name'] = found.get('name') or ''
    return data, {'updated': updated, 'missing': []}

def apply_latest_price_to_peripheral(item_data: Dict) -> Tuple[Dict, Dict]:
    data = dict(item_data or {})
    supplier = str(data.get('supplier') or '').strip()
    sku = str(data.get('supplier_sku') or '').strip()
    if not supplier or not sku:
        return data, {'updated': 0, 'missing': []}
    payload = get_supplier_price_list(supplier)
    if not payload:
        return data, {'updated': 0, 'missing': [f'нет загруженного прайса «{supplier}»']}
    found = lookup_price(payload, sku)
    if not found:
        return data, {'updated': 0, 'missing': [f'{supplier} / {sku} не найден в прайсе']}
    price = found.get('selected_price_usd')
    if price is None:
        return data, {'updated': 0, 'missing': [f'{supplier} / {sku} — цена «Call/по запросу»']}
    value = f'${float(price):g}'
    updated = int(str(data.get('price_input') or '').strip() != value)
    data['price_input'] = value
    data['supplier_price_usd'] = float(price)
    data['supplier_price_mode'] = found.get('selected_price_mode') or payload.get('price_mode') or ''
    data['supplier_price_date'] = payload.get('price_date') or ''
    data['supplier_name'] = found.get('name') or ''
    return data, {'updated': updated, 'missing': []}

def update_all_linked_profiles(supplier: str) -> Dict:
    """Reprice every saved equipment profile linked to the imported supplier."""
    supplier_key = _norm(supplier)
    profiles_touched = 0
    rows_updated = 0
    missing = []
    for rec in list_items('equipment_profile'):
        data = dict(rec.get('data') or {})
        linked = False
        for board in dict(data.get('boards') or {}).values():
            if _norm((board or {}).get('supplier')) == supplier_key:
                linked = True
        for item in list(data.get('components') or []):
            if _norm((item or {}).get('supplier')) == supplier_key:
                linked = True
        if not linked:
            continue
        patched, stat = apply_latest_prices_to_profile(data)
        if stat['updated']:
            save_item('equipment_profile', rec['name'], patched)
            profiles_touched += 1
            rows_updated += int(stat['updated'])
        missing.extend([f'{rec["name"]}: {x}' for x in stat.get('missing') or []])
    cases_touched = 0
    for rec in list_items('case'):
        data = dict(rec.get('data') or {})
        if _norm(data.get('custom_case_supplier')) != supplier_key:
            continue
        patched, stat = apply_latest_price_to_case(data)
        if stat['updated']:
            save_item('case', rec['name'], patched)
            cases_touched += 1
            rows_updated += int(stat['updated'])
        missing.extend([f'{rec["name"]}: {x}' for x in stat.get('missing') or []])
    aio_touched = 0
    for rec in list_items('aio'):
        data = dict(rec.get('data') or {})
        if _norm(data.get('custom_aio_supplier')) != supplier_key:
            continue
        patched, stat = apply_latest_price_to_aio(data)
        if stat['updated']:
            save_item('aio', rec['name'], patched)
            aio_touched += 1
            rows_updated += int(stat['updated'])
        missing.extend([f'{rec["name"]}: {x}' for x in stat.get('missing') or []])
    peripherals_touched = {'monitor':0,'keyboard':0,'mouse':0}
    for kind in ('monitor','keyboard','mouse'):
        for rec in list_items(kind):
            data = dict(rec.get('data') or {})
            if _norm(data.get('supplier')) != supplier_key:
                continue
            patched, stat = apply_latest_price_to_peripheral(data)
            if stat['updated']:
                save_item(kind, rec['name'], patched)
                peripherals_touched[kind] += 1
                rows_updated += int(stat['updated'])
            missing.extend([f'{rec["name"]}: {x}' for x in stat.get('missing') or []])
    return {'profiles_touched': profiles_touched, 'cases_touched': cases_touched, 'aio_touched': aio_touched, 'peripherals_touched': peripherals_touched, 'rows_updated': rows_updated, 'missing': missing}
