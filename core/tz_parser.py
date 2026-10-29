import io
import re
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Tuple


KTRU_TYPE_HINTS = {
    '26.20.15.000-00000028': 'system',
    '26.20.17.110-00000011': 'monitor',
    '26.20.16.110-00000002': 'keyboard',
    '26.20.16.170-00000002': 'mouse',
    '26.20.15.000-00000032': 'aio24',
    '26.20.15.000-00000034': 'aio24',
}


@dataclass
class Requirements:
    title: str = 'ТИП 1'
    item_name: Optional[str] = None
    ktru_code: Optional[str] = None
    quantity: int = 0
    nmck: Optional[float] = None
    platform: Optional[str] = None  # intel|amd
    product_type: str = 'system'    # system|aio24|aio27|aws24|aws27|monitor|keyboard|mouse

    # Which reusable equipment database should be used for this position.
    # None means the built-in QX catalog. Any other value is the name of a saved
    # user equipment profile (for example, "Бештау"). Profiles live in the same
    # portable QX_UserCatalog.qxdb as saved cases/AIO platforms.
    equipment_profile_name: Optional[str] = None
    monitor_catalog_item: Optional[str] = None
    # QX is authoritative/default for keyboard and mouse. Saved user catalogs are
    # opt-in only: merely having a saved keyboard/mouse must never replace QX.
    keyboard_source_mode: str = 'qx'   # qx|catalog|manual
    mouse_source_mode: str = 'qx'      # qx|catalog|manual
    keyboard_catalog_item: Optional[str] = None
    mouse_catalog_item: Optional[str] = None

    cpu_model: Optional[str] = None
    cpu_cores_min: Optional[int] = None
    cpu_threads_min: Optional[int] = None
    cpu_freq_ghz_min: Optional[float] = None
    cpu_freq_max_ghz_min: Optional[float] = None
    cpu_l3_mb_min: Optional[int] = None
    cpu_tdp_w_max: Optional[int] = None
    cpu_passmark_min: Optional[int] = None
    cpu_x86_64_required: bool = False
    need_integrated_graphics: bool = False

    ram_gb_min: Optional[int] = None
    ram_type: Optional[str] = None
    ram_type_min_generation: Optional[int] = None  # e.g. 4 for 'не ниже DDR4'
    ram_mhz_min: Optional[int] = None
    ram_module_gb_min: Optional[int] = None
    ram_max_supported_gb_min: Optional[int] = None
    ram_dual_channel_required: bool = False
    ram_modules_min: Optional[int] = None
    ram_slots_min: Optional[int] = None

    ssd_gb_min: Optional[int] = None
    ssd_interface: Optional[str] = None
    ssd_m2_required: bool = False
    ssd_25_required: bool = False
    hdd_gb_min: Optional[int] = None
    extra_hdd_slot_required: bool = False
    ssd_tbw_min: Optional[int] = None

    need_gpu: bool = False
    gpu_vram_gb_min: Optional[int] = None
    gpu_dp_min: Optional[int] = None
    gpu_hdmi_min: Optional[int] = None
    system_hdmi_min: Optional[int] = None
    system_dp_min: Optional[int] = None
    system_vga_min: Optional[int] = None

    psu_w_min: Optional[int] = None
    external_psu_required: bool = False
    warranty_months_min: Optional[int] = None

    need_wifi: bool = False
    need_bluetooth: bool = False
    forbid_wireless: bool = False
    need_cardreader: bool = False
    need_keyboard: bool = False
    need_mouse: bool = False
    need_os: bool = False
    os_text: Optional[str] = None

    m2_key_m_min: Optional[int] = None
    m2_key_e_min: Optional[int] = None
    sata_ports_min: Optional[int] = None
    ethernet_ports_min: Optional[int] = None
    ethernet_mbps_min: Optional[int] = None
    pcie_x1_min: Optional[int] = None
    pcie_x16_min: Optional[int] = None
    expansion_slots_min: Optional[int] = None
    raid_0_1_5_10_required: bool = False
    simultaneous_monitors_min: Optional[int] = None
    tpm_required: bool = False
    board_sensors_required: bool = False
    bios_astra_management_required: bool = False
    bios_admin_password_required: bool = False
    manual_requirements: List[str] = field(default_factory=list)
    usb2_total_min: Optional[int] = None
    usb2_front_min: Optional[int] = None
    usb3_gen1_total_min: Optional[int] = None
    usb3_gen1_front_min: Optional[int] = None
    usb3_gen1_type_a_total_min: Optional[int] = None
    usb3_gen1_type_c_total_min: Optional[int] = None
    usb3_gen2_total_min: Optional[int] = None
    usb3_gen2_type_a_total_min: Optional[int] = None
    usb3_gen2_type_c_total_min: Optional[int] = None
    usb3x_total_min: Optional[int] = None
    usb_c_total_min: Optional[int] = None
    usb_a_front_min: Optional[int] = None
    usb_c_front_min: Optional[int] = None
    usb_a_rear_min: Optional[int] = None

    # Optional user-installed I/O expansion panels. These are not parsed from the TZ;
    # the technical specialist fills them in manually when a front/rear bracket is used.
    extra_front_usb2_a: int = 0
    extra_front_gen1_a: int = 0
    extra_front_gen1_c: int = 0
    extra_front_gen2_a: int = 0
    extra_front_gen2_c: int = 0
    extra_rear_usb2_a: int = 0
    extra_rear_gen1_a: int = 0
    extra_rear_gen1_c: int = 0
    extra_rear_gen2_a: int = 0
    extra_rear_gen2_c: int = 0

    case_width_max_mm: Optional[int] = None
    case_length_max_mm: Optional[int] = None
    case_height_max_mm: Optional[int] = None
    case_width_min_mm: Optional[int] = None
    case_length_min_mm: Optional[int] = None
    case_height_min_mm: Optional[int] = None
    bay_525_min: Optional[int] = None
    bay_25_min: Optional[int] = None
    bay_325_min: Optional[int] = None
    bay_35_min: Optional[int] = None
    bay_35_external_min: Optional[int] = None
    front_audio_out_required: bool = False
    front_mic_in_required: bool = False
    system_audio_out_required: bool = False
    system_mic_in_required: bool = False
    integrated_psu_required: bool = False
    protected_case: bool = False

    # System/AWS chassis selection. QX cases keep their catalog facts; a custom
    # chassis is completely user-described so the selector can re-check the TZ
    # without silently inheriting QX dimensions/ports/bays.
    system_case_mode: str = 'auto'  # auto|qx_standard|qx_protected|custom
    custom_case_name: Optional[str] = None
    custom_case_price: float = 0.0
    custom_case_width_mm: Optional[int] = None
    custom_case_length_mm: Optional[int] = None
    custom_case_height_mm: Optional[int] = None
    custom_case_bay_525: int = 0
    custom_case_bay_25: int = 0
    custom_case_bay_325: int = 0
    custom_case_bay_35: int = 0
    custom_case_bay_35_external: int = 0
    custom_case_front_audio_out: bool = False
    custom_case_front_mic_in: bool = False
    custom_case_usb2_front: int = 0
    custom_case_gen1_a_front: int = 0
    custom_case_gen1_c_front: int = 0
    custom_case_gen2_a_front: int = 0
    custom_case_gen2_c_front: int = 0
    custom_case_protected: bool = False

    monitor_inches: Optional[float] = None
    monitor_resolution: Optional[str] = None
    monitor_resolution_is_min: bool = False
    monitor_matrix: Optional[str] = None
    monitor_refresh_hz_min: Optional[int] = None
    monitor_response_ms_max: Optional[float] = None
    monitor_response_ms_max_inclusive: bool = False
    monitor_brightness_min: Optional[int] = None
    monitor_brightness_max: Optional[int] = None
    monitor_speakers: Optional[bool] = None
    monitor_vesa: Optional[str] = None
    monitor_interfaces: Optional[str] = None
    monitor_external_psu: Optional[bool] = None
    monitor_wall_mount: Optional[bool] = None
    monitor_pivot: Optional[bool] = None
    monitor_tilt: Optional[bool] = None
    monitor_webcam: Optional[bool] = None
    monitor_touch: Optional[bool] = None
    monitor_usb_hub: Optional[bool] = None
    monitor_curved: Optional[bool] = None
    monitor_height_adjust_mm_min: Optional[int] = None
    monitor_color_depth_bits: Optional[int] = None
    monitor_dynamic_contrast_max: Optional[int] = None
    monitor_energy_class: Optional[str] = None
    monitor_cable_type: Optional[str] = None
    monitor_aspect_ratio: Optional[str] = None
    monitor_swivel: Optional[bool] = None
    monitor_cable_included: Optional[bool] = None
    monitor_power_w_max: Optional[float] = None
    monitor_audio_in_required: bool = False
    monitor_audio_out_required: bool = False
    monitor_hdmi_ports_min: Optional[int] = None
    monitor_dp_ports_min: Optional[int] = None
    need_builtin_mic: bool = False
    need_audio_jacks: bool = False
    audio_jacks_min: Optional[int] = None
    monitor_contrast_min: Optional[int] = None
    monitor_view_angle_h_min: Optional[int] = None
    monitor_view_angle_v_min: Optional[int] = None
    webcam_mp_min: Optional[float] = None
    webcam_privacy_shutter: bool = False

    # Monoblock barebone/platform selection. QX facts are used only when mode='qx'.
    # For another platform the specialist enters real values manually; they are then
    # used in compatibility checks and in the factual-characteristics table.
    aio_platform_mode: str = 'qx'  # qx|custom
    custom_aio_name: Optional[str] = None
    custom_aio_price: float = 0.0
    custom_aio_diagonal_in: Optional[float] = None
    custom_aio_resolution: Optional[str] = None
    custom_aio_refresh_hz: Optional[int] = None
    custom_aio_matrix: Optional[str] = None
    custom_aio_built_in_cardreader: bool = False
    custom_aio_integrated_psu: bool = True
    custom_aio_psu_w: Optional[int] = None
    # Extra/front I/O supplied by the custom barebone itself, in addition to the
    # motherboard rear I/O. No assumptions are made for a custom platform.
    custom_aio_usb2_a: int = 0
    custom_aio_gen1_a: int = 0
    custom_aio_gen1_c: int = 0
    custom_aio_gen2_a: int = 0
    custom_aio_gen2_c: int = 0
    custom_aio_front_usb2: int = 0
    custom_aio_front_a: int = 0
    custom_aio_front_c: int = 0

    keyboard_wired: bool = False
    keyboard_wireless: bool = False
    keyboard_keys_min: Optional[int] = None
    keyboard_numeric_keypad: bool = False
    keyboard_russification: Optional[str] = None
    keyboard_fullsize: bool = False
    keyboard_usb: bool = False
    keyboard_cable_min_m: Optional[float] = None
    keyboard_cable_max_m: Optional[float] = None
    keyboard_layout: Optional[str] = None
    keyboard_flexible: Optional[bool] = None
    keyboard_has_usb_port: Optional[bool] = None
    keyboard_multifunction: Optional[bool] = None
    keyboard_touchpad: Optional[bool] = None
    keyboard_palmrest: Optional[bool] = None
    keyboard_scroll_wheel: Optional[bool] = None
    keyboard_water_protection: Optional[bool] = None
    keyboard_detachable_cable: Optional[bool] = None
    keyboard_volume_control: Optional[bool] = None
    keyboard_backlight: Optional[bool] = None

    mouse_wired: bool = False
    mouse_wireless: bool = False
    mouse_buttons_min: Optional[int] = None
    mouse_sensor_text: Optional[str] = None
    mouse_optical: bool = False
    mouse_usb: bool = False
    mouse_cable_min_m: Optional[float] = None
    mouse_cable_max_m: Optional[float] = None
    mouse_dpi_min: Optional[int] = None
    mouse_programmable_buttons: Optional[bool] = None
    mouse_side_buttons: Optional[bool] = None
    mouse_silent_click: Optional[bool] = None
    mouse_detachable_cable: Optional[bool] = None

    raw_text: str = ''

    def to_dict(self):
        return asdict(self)


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '').replace('\xa0', ' ')).strip()


def _num(s: str) -> float:
    return float(str(s).replace(' ', '').replace(',', '.'))


def _int_from_value(v: str) -> Optional[int]:
    m = re.search(r'(-?\d+(?:[\.,]\d+)?)', v or '')
    if not m:
        return None
    return int(round(_num(m.group(1))))


def _float_from_value(v: str) -> Optional[float]:
    m = re.search(r'(-?\d+(?:[\.,]\d+)?)', v or '')
    return _num(m.group(1)) if m else None


def _bool_from_value(v: str) -> Optional[bool]:
    low = _norm(v).lower().replace('ё','е')
    # Tender tables often contain a selectable value such as "Да или нет".  It is
    # not a requirement for either state and must stay unconstrained.
    has_yes = bool(re.search(r'\bда\b', low))
    has_no = bool(re.search(r'\bнет\b|отсутств', low))
    if has_yes and has_no:
        return None
    if re.search(r'да\s*(?:/|или)\s*нет|нет\s*(?:/|или)\s*да', low):
        return None
    if has_yes:
        return True
    if has_no:
        return False
    return None


def _capacity_gb(v: str, unit: str = '') -> Optional[int]:
    n = _float_from_value(v)
    if n is None:
        return None
    u = (unit or '').lower()
    if 'тера' in u or re.search(r'\bтб\b|\btb\b', v or '', re.I):
        return int(round(n * 1024))
    return int(round(n))


def _storage_capacity_gb(v: str, unit: str = '') -> Optional[int]:
    """Nominal drive capacity in GB.

    HDD/SSD manufacturers and tender specifications use decimal capacities: 1 TB = 1000 GB.
    Using 1024 here made a 1 TB requirement round up to a 2 TB HDD in the selector.
    """
    n = _float_from_value(v)
    if n is None:
        return None
    u = (unit or '').lower()
    if 'тера' in u or re.search(r'\bтб\b|\btb\b', v or '', re.I):
        return int(round(n * 1000))
    return int(round(n))


def _extract_resolution(v: str) -> Optional[str]:
    m = re.search(r'(\d{3,4})\s*[xх×]\s*(\d{3,4})', v or '', re.I)
    return f'{m.group(1)}x{m.group(2)}' if m else None


def _table_to_text(table) -> str:
    rows = []
    for row in table.rows:
        cells = [_norm(c.text) for c in row.cells]
        if any(cells):
            rows.append(' | '.join(cells))
    return '\n'.join(rows)


def _docx_ordered_blocks(data: bytes) -> List[Tuple[str, str]]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P

    doc = Document(io.BytesIO(data))
    blocks = []
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            p = Paragraph(child, doc)
            txt = _norm(p.text)
            if txt:
                blocks.append(('p', txt))
        elif isinstance(child, CT_Tbl):
            t = Table(child, doc)
            txt = _table_to_text(t)
            if txt:
                blocks.append(('table', txt))
    return blocks


def _indicator_unit_hint(name: str) -> str:
    low = _norm(name).lower().replace('ё','е')
    for needle, unit in [
        ('терабайт','Терабайт'),('гигабайт','Гигабайт'),('мегабайт','Мегабайт'),
        ('гигагерц','Гигагерц'),('мегагерц','Мегагерц'),('герц','Герц'),
        ('миллиметр','Миллиметр'),('дюйм','Дюйм'),('ватт','Ватт'),
        ('мегабит','Мегабит/с'),('мегабайт в секунду','Мегабайт/с'),
        ('миллисекунд','мс'),(' мс','мс'),('градус','Градус'),('бит','Бит'),
        ('штук','Штука'),(' шт','Штука'),
    ]:
        if needle in low:
            return unit
    return ''


def _clean_indicator_name(name: str) -> str:
    s=_norm(name)
    # In this corporate table the measurement unit is embedded in the characteristic
    # name instead of a separate column. Strip only a trailing unit suffix so existing
    # KTRU parser rules can be reused without losing semantic parts such as "5,25 дюйма".
    return _norm(re.sub(
        r',\s*(?:шт\.?|штук\w*|гигабайт|терабайт|мегабайт(?:\s+в\s+секунду)?|гигагерц|мегагерц|герц|ватт|миллиметр|дюйм(?:\s*\([^)]*\))?|кд/м2|кд/м²|бит|градус|мс)\s*$',
        '', s, flags=re.I
    ))


def _clean_grouped_product_cell(raw: str):
    lines=[_norm(x) for x in re.split(r'[\r\n]+', raw or '') if _norm(x)]
    code=''
    for line in lines:
        m=re.search(r'\b\d{2}\.\d{2}\.\d{2}\.\d{3}(?:-\d{8})?\b', line)
        if m:
            code=m.group(0); break
    name_parts=[]
    for line in lines:
        low=line.lower().replace('ё','е')
        if 'окпд' in low or 'ктру' in low:
            continue
        if re.fullmatch(r'\d{2}\.\d{2}\.\d{2}\.\d{3}(?:-\d{8})?', line):
            continue
        name_parts.append(line)
    name=_norm(' '.join(name_parts))
    return name,code


def _docx_grouped_characteristics_sections(data: bytes):
    """Parse a common corporate TZ layout with one row per characteristic.

    Shape: № | Наименование | Ед. измер | Кол-во | Наименование показателя |
    Содержание (значение) показателя | Инструкция ...

    Word repeats merged product cells in python-docx, so rows can be safely grouped by
    item number/name.  Each group is converted to the same internal characteristic-row
    format used by KTRU documents.
    """
    from docx import Document
    doc=Document(io.BytesIO(data))
    common_parts=[_norm(p.text) for p in doc.paragraphs if _norm(p.text)]
    common_text='\n'.join(common_parts)
    for table in doc.tables:
        if not table.rows:
            continue
        headers=[_norm(c.text).lower().replace('ё','е') for c in table.rows[0].cells]
        def idx(pred):
            for i,h in enumerate(headers):
                if pred(h): return i
            return None
        no_i=idx(lambda h: '№' in h or 'п/п' in h)
        name_i=idx(lambda h: h=='наименование' or (h.startswith('наименование') and 'показател' not in h))
        unit_i=idx(lambda h: 'ед.' in h or 'единиц' in h)
        qty_i=idx(lambda h: 'кол-во' in h or h=='количество')
        ind_i=idx(lambda h: 'наименование показател' in h)
        val_i=idx(lambda h: 'содержание' in h and 'показател' in h or 'значение показател' in h)
        instr_i=idx(lambda h: 'инструкц' in h)
        if None in (name_i, qty_i, ind_i, val_i):
            continue
        groups={}; order=[]
        for row in table.rows[1:]:
            cells=[c.text for c in row.cells]
            raw_name=cells[name_i] if name_i < len(cells) else ''
            item_name,code=_clean_grouped_product_cell(raw_name)
            indicator_raw=_norm(cells[ind_i]) if ind_i < len(cells) else ''
            indicator=_clean_indicator_name(indicator_raw)
            value=_norm(cells[val_i]) if val_i < len(cells) else ''
            if not item_name or not indicator:
                continue
            no=_norm(cells[no_i]) if no_i is not None and no_i < len(cells) else ''
            key=(re.sub(r'\D+','',no) or item_name.casefold(), item_name.casefold())
            if key not in groups:
                qty=_norm(cells[qty_i]) if qty_i < len(cells) else ''
                unit=_norm(cells[unit_i]) if unit_i is not None and unit_i < len(cells) else 'шт.'
                groups[key]={'name':item_name,'code':code,'qty':qty,'unit':unit,'rows':[]}
                order.append(key)
            instr=_norm(cells[instr_i]) if instr_i is not None and instr_i < len(cells) else ''
            groups[key]['rows'].append((indicator,value,_indicator_unit_hint(indicator_raw),instr))
        if len(groups) >= 2:
            sections=[]
            for pos,key in enumerate(order, start=1):
                g=groups[key]
                parts=[f'Наименование товара: {g["name"]}']
                if g['code']: parts.append(f'ОКПД2/КТРУ: {g["code"]}')
                if g['qty']: parts.append(f'Количество: {g["qty"]} {g["unit"]}'.strip())
                parts.append('Характеристики:')
                for n,v,u,ins in g['rows']:
                    parts.append(' | '.join([n,v,u,ins]))
                if common_text:
                    parts.append('Общие требования документа:')
                    parts.append(common_text)
                sections.append((g['name'], '\n'.join(parts)))
            return sections
    return []


def _docx_procurement_sections(data: bytes):
    """Recognize procurement tables where all specs are prose inside one cell.

    Common shape: № | ОКПД2 | Наименование | Технические характеристики | Ед. изм. | Кол-во.
    Unlike KTRU tables there is no separate value/instruction column, so we keep the
    technical-characteristics cell verbatim and add explicit item/quantity metadata.
    """
    from docx import Document
    doc = Document(io.BytesIO(data))
    sections = []
    common_parts = [_norm(p.text) for p in doc.paragraphs if _norm(p.text)]
    common_text = '\n'.join(common_parts)
    for table in doc.tables:
        if not table.rows:
            continue
        headers = [_norm(c.text).lower().replace('ё','е') for c in table.rows[0].cells]
        def idx_contains(*needles):
            for i,h in enumerate(headers):
                if any(n in h for n in needles):
                    return i
            return None
        name_i = idx_contains('наименование')
        spec_i = idx_contains('технические характеристики', 'характеристики')
        qty_i = idx_contains('кол-во', 'количество')
        unit_i = idx_contains('ед. изм', 'единица измер')
        code_i = idx_contains('окпд2', 'ктру', 'код позиции')
        if name_i is None or spec_i is None or qty_i is None:
            continue
        for row_no,row in enumerate(table.rows[1:], start=1):
            cells = [c.text.strip() for c in row.cells]
            name = _norm(cells[name_i]) if name_i < len(cells) else ''
            specs = cells[spec_i].strip() if spec_i < len(cells) else ''
            qty = _norm(cells[qty_i]) if qty_i < len(cells) else ''
            unit = _norm(cells[unit_i]) if unit_i is not None and unit_i < len(cells) else 'шт.'
            code = _norm(cells[code_i]) if code_i is not None and code_i < len(cells) else ''
            if not name or not specs:
                continue
            # Preserve line breaks inside the spec cell; Word uses them as individual requirements.
            spec_lines = [_norm(x) for x in re.split(r'[\r\n]+', specs) if _norm(x)]
            parts = [f'Наименование товара: {name}']
            if code:
                parts.append(f'ОКПД2/КТРУ: {code}')
            if qty:
                parts.append(f'Количество: {qty} {unit}'.strip())
            parts.append('Технические характеристики:')
            parts.extend(spec_lines)
            if common_text:
                parts.append('Общие требования документа:')
                parts.append(common_text)
            title = name if len(table.rows) == 2 else f'{name} {row_no}'
            sections.append((title, '\n'.join(parts)))
    return sections


def _docx_sections(data: bytes):
    grouped = _docx_grouped_characteristics_sections(data)
    if grouped:
        blocks = _docx_ordered_blocks(data)
        return grouped, '\n'.join(txt for _, txt in blocks)
    procurement = _docx_procurement_sections(data)
    if procurement:
        # Return one logical section per goods row, while preserving whole-document text for preview/search.
        blocks = _docx_ordered_blocks(data)
        return procurement, '\n'.join(txt for _, txt in blocks)
    blocks = _docx_ordered_blocks(data)
    # Standalone KTRU tables with columns in unexpected order.
    from docx import Document
    doc = Document(io.BytesIO(data))
    normalized_tables = []
    for table in doc.tables:
        normalized = _normalized_characteristic_table([[cell.text for cell in row.cells] for row in table.rows])
        if normalized:
            normalized_tables.extend(normalized)
    sections = []
    current_title = None
    current_parts = []

    pos_re = re.compile(r'^\s*\d+\.\s*Позиция\s+\d+\.\s*(.+)$', re.I)
    for kind, txt in blocks:
        m = pos_re.match(txt)
        if kind == 'p' and m:
            if current_title and current_parts:
                sections.append((current_title, '\n'.join(current_parts)))
            current_title = _norm(m.group(1)) or f'Позиция {len(sections)+1}'
            current_parts = [txt]
        elif current_title:
            current_parts.append(txt)

    if current_title and current_parts:
        sections.append((current_title, '\n'.join(current_parts)))

    if sections:
        return sections, '\n'.join(txt for _, txt in blocks)

    # No explicit "Позиция N" structure: parse entire file as one technical item.
    all_text = '\n'.join(txt for _, txt in blocks)
    if normalized_tables:
        all_text += '\n### Нормализованные характеристики\n' + '\n'.join(normalized_tables)
    return _split_text_positions(all_text), all_text



# Column names found in actual KTRU exports and corporate product specifications.
# The converter works on an individual table: it does not let the previous item
# or the quantity column silently become a technical requirement.
def _header_kind(value: str) -> str:
    v = _norm(value).casefold().replace('ё', 'е')
    if re.search(r'наименовани[ея]\s+(?:характерист|показател)|^характеристика$|^показатель$|^параметр$|^параметры$', v):
        return 'name'
    if re.search(r'инструкц|заполнени[ея]\s+заявк', v):
        return 'instruction'
    if re.search(r'единиц[аы]?\s+измерен|^ед\.?\s*изм|^ед\.?$', v):
        return 'unit'
    if re.search(r'значени[ея]\s+(?:характерист|показател)|требуемое\s+значени|допустимое\s+значени|содержани[ея]\s+(?:характерист|показател)|^значение$|^требование$|^минимум$', v):
        return 'value'
    return ''


def _normalized_characteristic_table(matrix):
    """Normalize permuted characteristic columns (Word/Excel/KTRU)."""
    rows = [[_norm(str(x)) if x is not None else '' for x in row] for row in matrix]
    for header_index, header in enumerate(rows[:7]):
        positions = {}
        for i, name in enumerate(header):
            kind = _header_kind(name)
            if kind and kind not in positions:
                positions[kind] = i
        if 'name' not in positions or 'value' not in positions or positions['name'] == positions['value']:
            continue
        result = []
        for row in rows[header_index + 1:]:
            def get(kind):
                i = positions.get(kind, -1)
                return row[i] if 0 <= i < len(row) else ''
            name, value = get('name'), get('value')
            if not name or not value or _header_kind(name):
                continue
            # Excel often has merged cells; only carry a header for the same
            # characteristic, never propagate another item's product name.
            result.append(' | '.join((name, value, get('unit'), get('instruction'))))
        if result:
            return result
    return []


def _xlsx_sections(data: bytes):
    """Interpret one-sheet/tabs as separate TZs only when each sheet has goods.

    Also preserve all cells for source preview and LLM evidence; structured
    attribute tables with shifted or reordered headers are normalized first.
    """
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    all_parts, sections = [], []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            vals = [str(v).strip() if v is not None else '' for v in row]
            if any(vals):
                rows.append(vals)
            if len(rows) > 18000:
                break
        if not rows:
            continue
        raw = '\n'.join(' | '.join(v for v in line if v) for line in rows)
        all_parts.append(f'### {ws.title}\n{raw}')
        normalized = _normalized_characteristic_table(rows)
        if normalized:
            # Sheets named "Лист1" still commonly carry an item name/quantity
            # in the opening caption rows above the characteristic table.
            item = ws.title
            metadata = []
            for row in rows[:8]:
                first = _norm(row[0]).casefold().replace('ё','е') if row else ''
                value = _norm(row[1]) if len(row) > 1 else ''
                if ('наименование товара' in first or 'наименование изделия' in first) and value:
                    item = value[:170]
                if re.fullmatch(r'количество|кол-во', first) and re.fullmatch(r'\d{1,7}', value):
                    metadata.append(f'Количество: {value} шт')
            sections.append((item, f'Наименование товара: {item}\n' + '\n'.join(metadata + normalized)))
            continue
        # Common purchasing specification: product name / description / qty.
        # Read by column label instead of assuming a fixed spreadsheet layout.
        header_i = None
        for hi, h in enumerate(rows[:8]):
            low = [_norm(c).casefold().replace('ё', 'е') for c in h]
            if any('наименовани' in c for c in low) and any('количество' in c or 'кол-во' in c for c in low):
                header_i = hi; break
        if header_i is not None:
            h = [_norm(c).casefold().replace('ё', 'е') for c in rows[header_i]]
            name_i = next((j for j,v in enumerate(h) if 'наименовани' in v), None)
            qty_i = next((j for j,v in enumerate(h) if 'количество' in v or 'кол-во' in v), None)
            spec_i = next((j for j,v in enumerate(h) if 'характерист' in v or 'описани' in v or 'техническ' in v), None)
            for ix, row in enumerate(rows[header_i+1:],1):
                name = row[name_i] if name_i is not None and name_i < len(row) else ''
                qty = row[qty_i] if qty_i is not None and qty_i < len(row) else ''
                if not name or not re.search(r'моноблок|системн.*блок|компьютер|монитор|клавиатур|мышь|арм\b',name,re.I):
                    continue
                spec = row[spec_i] if spec_i is not None and spec_i < len(row) else ''
                text = 'Наименование товара: ' + name + '\n'
                if qty:
                    text += 'Количество: ' + qty + ' шт\n'
                text += (spec or ' | '.join(v for j,v in enumerate(row) if j not in (name_i,qty_i)))
                sections.append((name if ix == 1 else f'{name} {ix}', text))
            if header_i is not None and sections:
                continue
        # A worksheet with a clearly distinct product in its title is one item.
        # Else leave the original whole-document fallback intact.
        if re.search(r'моноблок|системн.*блок|монитор|клавиатур|мышь|компьютер', ws.title, re.I):
            sections.append((ws.title, raw))
    all_text = '\n'.join(all_parts)
    return (sections or _split_text_positions(all_text)), all_text


def _odt_text(data: bytes) -> str:
    """Parse text from ODT without external office/OCR tools."""
    import zipfile
    from xml.etree import ElementTree
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if sum(i.file_size for i in zf.infolist() if i.filename == 'content.xml') > 25_000_000:
                raise ValueError('ODT содержит слишком большой XML')
            xml = zf.read('content.xml')
        root = ElementTree.fromstring(xml)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError('Некорректный ODT файл') from exc
    lines = []
    for element in root.iter():
        if element.tag.endswith(('}p','}h','}table-row')):
            value = _norm(' '.join(element.itertext()))
            if value and (not lines or lines[-1] != value):
                lines.append(value)
    return '\n'.join(lines)

def extract_text(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith('.docx'):
        _, text = _docx_sections(data)
        return text
    if lower.endswith('.pdf'):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return '\n'.join((page.extract_text() or '') for page in reader.pages)
    if lower.endswith(('.xlsx', '.xlsm')):
        return _xlsx_sections(data)[1]
    if lower.endswith('.odt'):
        return _odt_text(data)
    if lower.endswith(('.txt', '.csv')):
        for enc in ('utf-8-sig', 'utf-8', 'cp1251'):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                pass
        return data.decode('utf-8', errors='ignore')
    raise ValueError('Поддерживаются PDF, DOCX, XLSX/XLSM, ODT, TXT и CSV.')


def _split_text_positions(text: str):
    # Generic fallback for PDF/TXT.
    matches = list(re.finditer(r'(?im)^\s*(?:\d+[.)]\s*)?позиция\s*(?:№|N|#)?\s*\d+\s*[:.\-–]?\s*(.*)$', text))
    if matches and (len(matches) > 1 or matches[0].start() <= 400):
        out = []
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            out.append((_norm(m.group(1)) or f'Позиция {i+1}', text[m.start():end]))
        return out

    matches = list(re.finditer(r'(?im)^\s*(?:арм\s*)?(?:тип|тип\s*№)\s*([1-9]\d*)\b', text))
    if len(matches) > 1:
        out = []
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            out.append((f'ТИП {m.group(1)}', text[m.start():end]))
        return out
    return [('ТИП 1', text)]


def _characteristic_rows(text: str):
    rows = []
    for line in text.splitlines():
        if '|' in line:
            cells = [_norm(x) for x in line.split('|')]
        elif '\t' in line:
            cells = [_norm(x) for x in line.split('\t')]
        elif re.match(r'^\s*[А-Яа-яЁёA-Za-z][^—–]{4,110}\s[—–]\s\S', line):
            cells = [_norm(x) for x in re.split(r'\s[—–]\s', line, maxsplit=1)]
        elif re.match(r'^\s*[А-Яа-яЁёA-Za-z][^:]{4,110}:\s*\S', line):
            cells = [_norm(x) for x in line.split(':', 1)]
        else:
            continue
        if len(cells) < 2:
            continue
        name = cells[0]
        value = cells[1]
        unit = cells[2] if len(cells) > 2 else ''
        # Aliases common in supplier and non-KTRU specification forms.
        alias = _norm(name).casefold().replace('ё','е')
        if re.fullmatch(r'(?:объем|обьем|объём)\s+(?:озу|ram)|(?:озу|оперативная память|ram)', alias):
            name = 'Объем установленной оперативной памяти'
        elif re.fullmatch(r'(?:объем|обьем|объём)\s+(?:ssd|твердотельного накопителя)|(?:ssd|ssd диск)', alias):
            name = 'Общий объем накопителей SSD'
        elif re.fullmatch(r'(?:число|количество)\s+ядер(?:\s+процессора)?', alias):
            name = 'Количество ядер процессора'
        elif re.fullmatch(r'(?:число|количество)\s+потоков(?:\s+процессора)?', alias):
            name = 'Количество потоков процессора'
        elif re.fullmatch(r'(?:объем|обьем|объём)\s+(?:hdd|жесткого диска)|hdd', alias):
            name = 'Общий объем накопителей HDD'
        if not name or name.lower().startswith(('наименование характерист', 'код окпд2', '№')):
            continue
        rows.append((name, value, unit, cells))
    return rows


def _find_row(rows, *patterns):
    for name, value, unit, cells in rows:
        low = name.lower().replace('ё', 'е')
        for p in patterns:
            if re.search(p, low, re.I):
                return name, value, unit, cells
    return None


def _find_rows(rows, *patterns):
    out = []
    for row in rows:
        low = row[0].lower().replace('ё', 'е')
        if any(re.search(p, low, re.I) for p in patterns):
            out.append(row)
    return out


def _infer_item_name(title: str, text: str) -> Optional[str]:
    """Prefer the *named item*, not mentions in unrelated specification prose.

    A monoblock tender routinely references system units and monitors inside
    its characteristics. Searching the whole document for 'system unit' first
    used to classify such documents as an ordinary system unit.
    """
    t = _norm(title)
    if t and not re.fullmatch(r'(?:АРМ\s*)?ТИП\s*(?:№\s*)?\d+|Позиция\s*\d+', t, re.I):
        return t
    m = re.search(r'(?im)^\s*(?:наименование\s+(?:товара|изделия|продукции)|предмет\s+закупки)\s*[:：]\s*([^\n|]{3,180})', text)
    if m:
        return _norm(m.group(1))
    # Only a product mention in a heading qualifies as a fallback. The overall
    # document may discuss parts like a monitor, chassis and motherboard.
    head_lines = [_norm(line) for line in text.splitlines()[:10] if _norm(line)]
    # A monoblock can be described as a 'computer with integrated screen',
    # and specifications often mention monitor/system unit as components.
    for line in head_lines:
        if len(line)<180 and re.search(r'\bмоноблок\b',line,re.I):
            return 'моноблок'
    for line in head_lines:
        for word in ('системный блок', 'монитор', 'клавиатура', 'мышь'):
            if re.match(r'^'+re.escape(word)+r'(?:\b|\s|[,:])',line,re.I):
                return word
    return None


def _infer_product_type(item_name: Optional[str], ktru: Optional[str], rows, text: str) -> str:
    """Classify integrated PCs before treating a display as a standalone monitor."""
    low_name = (item_name or '').casefold().replace('ё', 'е')
    names = ' '.join(r[0].casefold().replace('ё','е') for r in rows)
    body = (text or '').casefold().replace('ё','е')
    # Explicit item nomenclature is more reliable than KTRU in arbitrary long
    # source files: the first code found may belong to another item.
    if 'моноблок' in low_name or re.search(r'компьютер\s+персональный\s+настольный\s*\(моноблок\)',low_name):
        kind='aio'
    elif 'системн' in low_name and 'блок' in low_name:
        return 'system'
    elif 'монитор' in low_name and 'моноблок' not in low_name:
        return 'monitor'
    elif 'клавиатур' in low_name:
        return 'keyboard'
    elif 'мыш' in low_name:
        return 'mouse'
    else:
        kind=None

    has_screen = bool(re.search(r'диагонал[ьи]\s*(?:экран|диспле|монитор)|(?:экран|диспле)\w*\s+диагонал',names))
    has_cpu = bool(re.search(r'количеств\w*\s+(?:ядер|потоков)\s+процессор|частот\w*\s+процессор|\bпроцессор\b',names))
    has_memory = bool(re.search(r'оперативн\w*\s+памят|\b(?:ram|ddr4|ddr5)\b',names))
    has_storage = bool(re.search(r'накопител|\bssd\b|твердотельн',names))
    if kind == 'aio' or (has_screen and has_cpu and has_memory and has_storage):
        diag_row = _find_row(rows, r'диагонал.*(?:экран|диспле)',r'(?:экран|диспле).*диагонал')
        diag = _float_from_value(diag_row[1]) if diag_row else None
        # A 27-inch screen often appears without a clean dedicated diagonal row.
        if diag is None:
            # The dimension may be in the procurement item label rather than
            # in a well-formed characteristic table (e.g. 'AIO ... /27').
            m=re.search(r'(?<!\d)27(?:[\.,]0)?(?!\d)',low_name)
            if m:diag=27.0
        if diag is None:
            m=re.search(r'(?<!\d)27\s*(?:[″”]|дюйм)',body)
            if m:diag=27.0
        return 'aio27' if diag is not None and diag >= 27 else 'aio24'
    if ktru in KTRU_TYPE_HINTS:
        return KTRU_TYPE_HINTS[ktru]
    if has_screen and re.search(r'разрешени\w*\s+(?:экран|диспле)',names):
        return 'monitor'
    return 'system'


def parse_one(text: str, title='ТИП 1') -> Requirements:
    t = text.replace('\u00a0', ' ')
    low = t.lower().replace('ё', 'е')
    rows = _characteristic_rows(t)
    item_name = _infer_item_name(title, t)

    codes = re.findall(r'\b\d{2}\.\d{2}\.\d{2}\.\d{3}-\d{8}\b', t)
    ktru = codes[0] if codes else None

    r = Requirements(title=title, item_name=item_name, ktru_code=ktru, raw_text=t)
    r.product_type = _infer_product_type(item_name, ktru, rows, t)

    # Quantity. Never infer it from a characteristic row like "USB ... | ≥ 1 | Штука".
    # Only explicit quantity wording is accepted here; summary/prose tables are handled below.
    qm = re.search(r'(?:количеств\w*|кол-?во)[^\d]{0,20}(\d+(?:[\.,]\d+)?)\s*(?:штук\w*|шт\.?|ед\.?|комплект\w*)', t, re.I)
    if qm:
        try:
            r.quantity = max(0, int(round(_num(qm.group(1)))))
        except Exception:
            pass
    if not r.quantity:
        # Sectioned KTRU DOCX often renders the position header as:
        # 'Код позиции / Количество / Цена / ... / 97,00 штука'. Search only the
        # beginning of the position so characteristic rows like 'Количество портов'
        # cannot be mistaken for procurement quantity.
        head = t[:700]
        qm2 = re.search(r'количеств\w*.{0,220}?(\d+(?:[\.,]\d+)?)\s*штук\w*', head, re.I | re.S)
        if qm2:
            try:
                r.quantity = max(0, int(round(_num(qm2.group(1)))))
            except Exception:
                pass

    # Platform hints.
    if re.search(r'\b(?:core\s+i[3579]|lga\s*1700|b760)\b', low):
        r.platform = 'intel'
    if re.search(r'\b(?:ryzen|am4|a520)\b', low):
        r.platform = 'amd'

    # Exact CPU model if present.
    m = re.search(r'((?:intel\s+)?core\s+i[3579][\-\s]?\d{4,5}[a-z]{0,2}|(?:amd\s+)?ryzen\s+[3579]\s+\d{4}[a-z]{0,2})', t, re.I)
    if m:
        r.cpu_model = _norm(m.group(1))

    # CPU characteristics.
    row = _find_row(rows, r'количество ядер процессора')
    if row: r.cpu_cores_min = _int_from_value(row[1])
    row = _find_row(rows, r'количество потоков процессора')
    if row: r.cpu_threads_min = _int_from_value(row[1])
    row = _find_row(rows, r'частота процессора базовая', r'базовая частота процессора', r'базовая тактовая частота.*процессора', r'базовая тактовая частота производительных ядер процессора')
    if row: r.cpu_freq_ghz_min = _float_from_value(row[1])
    row = _find_row(rows, r'частота процессора максимальная', r'максимальная частота процессора', r'максимальная тактовая частота процессора')
    if row: r.cpu_freq_max_ghz_min = _float_from_value(row[1])
    row = _find_row(rows, r'кэш.*третьего уровня.*l3', r'кэш памяти третьего уровня', r'^объем кэш памяти процессора$', r'^объ[её]м кэш памяти процессора$')
    if row: r.cpu_l3_mb_min = _int_from_value(row[1])
    row = _find_row(rows, r'тепловыделение процессора')
    if row: r.cpu_tdp_w_max = _int_from_value(row[1])
    # Integrated graphics can be expressed either as a boolean controller requirement
    # or as a categorical video-adapter type (e.g. "Интегрированный (Встроенный)").
    row = _find_row(rows, r'графического контроллера интегрированного в процессор', r'наличие.*интегрированн.*графическ', r'^интегрированный видеоадаптер$')
    if row:
        # A numeric characteristic such as "Базовая частота графического контроллера
        # интегрированного в процессор ≥ 1000 МГц" also unambiguously requires an iGPU.
        b = _bool_from_value(row[1])
        if b is not None:
            r.need_integrated_graphics = b
        elif re.search(r'частот', row[0], re.I) and _float_from_value(row[1]) is not None:
            r.need_integrated_graphics = True
    row = _find_row(rows, r'^тип видеоадаптера$', r'^тип графического адаптера$', r'^тип видеокарты$')
    if row:
        v = row[1].lower().replace('ё','е')
        if 'интегр' in v or 'встроенн' in v:
            r.need_integrated_graphics = True
            r.need_gpu = False
        elif 'дискрет' in v:
            r.need_gpu = True

    # RAM.
    row = _find_row(rows, r'^объем установленной оперативной памяти$', r'^объем оперативной установленной памяти$', r'^общий объем установленной оперативной памяти$')
    if row: r.ram_gb_min = _capacity_gb(row[1], row[2])
    row = _find_row(rows, r'^тип оперативной памяти$')
    if row:
        if 'ddr5' in row[1].lower(): r.ram_type = 'DDR5'
        elif 'ddr4' in row[1].lower(): r.ram_type = 'DDR4'
    row = _find_row(rows, r'тактовая частота оперативной памяти')
    if row: r.ram_mhz_min = _int_from_value(row[1])
    row = _find_row(rows, r'объем каждого установленного модуля оперативной памяти')
    if row: r.ram_module_gb_min = _capacity_gb(row[1], row[2])
    row = _find_row(rows, r'количество установленных модулей оперативной памяти')
    if row: r.ram_modules_min = _int_from_value(row[1])
    row = _find_row(rows, r'^количество слотов оперативной памяти$')
    if row: r.ram_slots_min = _int_from_value(row[1])
    row = _find_row(rows, r'^максимальный объем оперативной памяти$', r'^максимальный объ[её]м поддерживаемой оперативной памяти$', r'^допустимый максимальный объ[её]м увеличения оперативной памяти$', r'^общий поддерживаемый объем оперативной памяти$')
    if row: r.ram_max_supported_gb_min = _capacity_gb(row[1], row[2])

    # Drives. Parse both a single-drive capacity and total SSD capacity regardless of
    # form factor wording (2.5", M.2, PCIe, etc.). The previous parser only recognised
    # total SSD capacity when the characteristic itself contained M.2, so a row such as
    # 'Общий объем накопителей SSD форм-фактора 2,5" | ≥ 480 ГБ' was accidentally ignored.
    ssd_rows = [x for x in rows if re.search(r'(?i)\bssd\b', x[0]) and re.search(r'(?i)об[ъь]?[её]м', x[0])]
    for row in ssd_rows:
        cap = _storage_capacity_gb(row[1], row[2])
        if cap is not None:
            r.ssd_gb_min = max(r.ssd_gb_min or 0, cap)
        lname = row[0].lower().replace(',', '.')
        if re.search(r'm\s*\.\s*2', lname):
            r.ssd_m2_required = True
        if re.search(r'(?:форм[- ]?фактор\w*\s*)?2\s*\.\s*5', lname):
            r.ssd_25_required = True
    if not r.ssd_gb_min:
        # Some TЗ only state SSD count; registry always has an SSD anyway.
        row = _find_row(rows, r'количество накопителей типа ssd')
        if row and (_int_from_value(row[1]) or 0) >= 1:
            r.ssd_gb_min = None
    # A form factor can also be stated only in the SSD-count characteristic.
    row = _find_row(rows, r'количество накопителей типа ssd.*2[,.]5')
    if row and (_int_from_value(row[1]) or 0) >= 1:
        r.ssd_25_required = True
    row = _find_row(rows, r'количество накопителей типа ssd.*m\.2')
    if row and (_int_from_value(row[1]) or 0) >= 1:
        r.ssd_m2_required = True
    row = _find_row(rows, r'^интерфейс накопителя ssd$')
    if row:
        v = row[1].lower()
        if 'nvme' in v: r.ssd_interface = 'NVMe'
        elif 'sata' in v: r.ssd_interface = 'SATA'

    hdd_rows = [x for x in rows if re.search(r'(?i)\bhdd\b', x[0]) and re.search(r'(?i)об[ъь]?[её]м', x[0])]
    for row in hdd_rows:
        cap = _storage_capacity_gb(row[1], row[2])
        if cap is not None:
            r.hdd_gb_min = max(r.hdd_gb_min or 0, cap)
    row_count_hdd = _find_row(rows, r'количество накопителей типа hdd')
    if row_count_hdd and (_int_from_value(row_count_hdd[1]) or 0) >= 1 and not r.hdd_gb_min:
        r.hdd_gb_min = 1000

    # Graphics.
    dg = _find_row(rows, r'наличие установленного дискретного графического контроллера')
    if dg:
        b = _bool_from_value(dg[1])
        if b is not None: r.need_gpu = b
    row = _find_row(rows, r'объем дискретной видеопамяти')
    if row:
        r.gpu_vram_gb_min = _capacity_gb(row[1], row[2]); r.need_gpu = True
    row = _find_row(rows, r'количество портов displayport дискретного графического')
    if row:
        r.gpu_dp_min = _int_from_value(row[1]); r.need_gpu = True
    row = _find_row(rows, r'количество портов hdmi дискретного графического')
    if row:
        r.gpu_hdmi_min = _int_from_value(row[1]); r.need_gpu = True
    row = _find_row(rows, r'^количество портов hdmi$', r'количество встроенных выходных разъемов hdmi')
    if row: r.system_hdmi_min = _int_from_value(row[1])
    row = _find_row(rows, r'^количество портов display\s*port$', r'^количество портов displayport$', r'^общее количество установленных портов display\s*port$', r'количество встроенных выходных разъемов displayport', r'количество встроенных выходных разъемов display\s*port')
    if row: r.system_dp_min = _int_from_value(row[1])
    row = _find_row(rows, r'^количество портов vga$', r'количество встроенных выходных разъемов vga')
    if row: r.system_vga_min = _int_from_value(row[1])
    # Some KTRU/TZ list required built-in video outputs as repeated categorical rows.
    for vrow in _find_rows(rows, r'наличие встроенных выходных видео разъемов', r'наличие встроенных выходных видеоразъемов'):
        vv = vrow[1].lower().replace('ё','е')
        if 'hdmi' in vv:
            r.system_hdmi_min = max(r.system_hdmi_min or 0, 1)
        if 'display port' in vv or 'displayport' in vv:
            r.system_dp_min = max(r.system_dp_min or 0, 1)

    # PSU.
    row = _find_row(rows, r'мощность блока питания')
    if row: r.psu_w_min = _int_from_value(row[1])
    row = _find_row(rows, r'^встроенный блок питания$')
    if row and _bool_from_value(row[1]) is True: r.integrated_psu_required = True

    # Wireless / cardreader / bundled peripherals.
    for row in _find_rows(rows, r'^беспроводная связь$'):
        val = row[1].lower()
        if 'wi-fi' in val or 'wifi' in val: r.need_wifi = True
        if 'bluetooth' in val or 'блютус' in val: r.need_bluetooth = True
    row = _find_row(rows, r'наличие встроенного картридера')
    if row:
        b = _bool_from_value(row[1])
        if b is not None: r.need_cardreader = b
    row = _find_row(rows, r'наличие клавиатуры.*в комплекте')
    if row:
        b = _bool_from_value(row[1]); r.need_keyboard = bool(b)
    row = _find_row(rows, r'наличие манипулятора мыш.*в комплекте')
    if row:
        b = _bool_from_value(row[1]); r.need_mouse = bool(b)

    # OS: distinguish presence ("Да") from the actual OS product name.
    # A yes/no row must never become the Arsenal value "Название ОС: Да".
    row = _find_row(rows, r'^предустановленная операционная система$', r'^наличие предустановленной операционной системы$')
    if row:
        b = _bool_from_value(row[1])
        if b is not None:
            r.need_os = b
            r.os_text = None
        elif str(row[1] or '').strip():
            r.need_os = True
            r.os_text = _norm(row[1])

    # A separate naming row, when present, is authoritative.
    os_name_row = _find_row(rows, r'^название ос$', r'^наименование ос$', r'^наименование операционной системы$', r'^операционная система$')
    if os_name_row and str(os_name_row[1] or '').strip():
        maybe_bool = _bool_from_value(os_name_row[1])
        if maybe_bool is None:
            r.need_os = True
            r.os_text = _norm(os_name_row[1])

    if r.os_text is None and not row:
        # Capture an explicit Windows product name from free text only when there is no presence row;
        # a separate "Наличие ... = Да" row does not identify the installed OS. The later "Без ОС" guard still overrides this if applicable.
        m = re.search(r'(windows\s*(?:10|11)?(?:\s+(?:pro|professional|home|enterprise|education))?[^\n,;]{0,30})', t, re.I)
        if m and not re.search(r'\bбез\s+ос\b', t, re.I):
            r.need_os = True
            r.os_text = _norm(m.group(1))

    # Ports / slots / network.
    row = _find_row(rows, r'^количество слотов m\.2 key m$', r'^количество слотов m\.2 кеу m$')
    if row: r.m2_key_m_min = _int_from_value(row[1])
    row = _find_row(rows, r'^количество слотов m\.2 key e$', r'^количество слотов m\.2 кеу e$')
    if row: r.m2_key_e_min = _int_from_value(row[1])
    row = _find_row(rows, r'^количество разъемов sata$', r'^количество разъ[её]мов sata$')
    if row:
        # Board SATA is checked as a manual/compatibility fact via the selected motherboard.
        setattr(r, 'sata_ports_min', _int_from_value(row[1]))
    row = _find_row(rows, r'^сетевой интерфейс 8p8c', r'^количество встроенных разъемов 8p8c', r'^количество встроенных разъ[её]мов 8p8c')
    if row: r.ethernet_ports_min = _int_from_value(row[1])
    row = _find_row(rows, r'наличие в корпусе порт[а-я]* gigabit ethernet 8p8c')
    if row and _bool_from_value(row[1]):
        r.ethernet_ports_min = max(r.ethernet_ports_min or 0, 1)
        r.ethernet_mbps_min = max(r.ethernet_mbps_min or 0, 1000)
    row = _find_row(rows, r'скорость передачи данных проводного сетевого контроллера')
    if row: r.ethernet_mbps_min = _int_from_value(row[1])
    row = _find_row(rows, r'количество слотов pci[- ]?express x1')
    if row: r.pcie_x1_min = _int_from_value(row[1])
    row = _find_row(rows, r'количество слотов pci[- ]?express x16')
    if row: r.pcie_x16_min = _int_from_value(row[1])
    row = _find_row(rows, r'количество слотов расширения')
    if row: r.expansion_slots_min = _int_from_value(row[1])
    row = _find_row(rows, r'поддержка raid 0/1/5/10')
    if row and _bool_from_value(row[1]) is True: r.raid_0_1_5_10_required = True
    # USB requirements. Keep connector type and generation separate: procurement TZs
    # can simultaneously require Gen1 Type-A, Gen1 Type-C, Gen2 Type-A, Gen2 Type-C,
    # aggregate USB 3.x and aggregate Type-C counts.
    row = _find_row(
        rows,
        r'^(?:суммарное\s+)?количество\s+встроенных\s+в\s+корпус\s+портов\s+usb\s*2\.0(?:\s+type-a)?$',
    )
    if row: r.usb2_total_min = _int_from_value(row[1])
    row = _find_row(rows, r'количество портов usb 2\.0(?: type-a)? на передней панели')
    if row: r.usb2_front_min = _int_from_value(row[1])

    row = _find_row(rows, r'^(?:суммарное\s+)?количество\s+встроенных\s+в\s+корпус\s+портов\s+usb\s*3\.2\s+gen\s*1(?:\s*\([^)]*\))?\s+type-a$')
    if row:
        r.usb3_gen1_type_a_total_min = _int_from_value(row[1])
        r.usb3_gen1_total_min = max(r.usb3_gen1_total_min or 0, r.usb3_gen1_type_a_total_min or 0)
    row = _find_row(rows, r'^(?:суммарное\s+)?количество\s+встроенных\s+в\s+корпус\s+портов\s+usb\s*3\.2\s+gen\s*1(?:\s*\([^)]*\))?\s+type-c$')
    if row:
        r.usb3_gen1_type_c_total_min = _int_from_value(row[1])
    # Generic Gen1 requirement without a connector suffix.
    row = _find_row(rows, r'^(?:суммарное\s+)?количество\s+встроенных\s+в\s+корпус\s+портов\s+usb\s*3\.2\s+gen\s*1(?:\s*\([^)]*\))?$')
    if row: r.usb3_gen1_total_min = _int_from_value(row[1])
    row = _find_row(rows, r'количество портов usb 3\.2 gen 1.*на передней панели')
    if row: r.usb3_gen1_front_min = _int_from_value(row[1])

    row = _find_row(rows, r'^(?:суммарное\s+)?количество\s+встроенных\s+в\s+корпус\s+портов\s+usb\s*3\.2\s+gen\s*2(?:\s*\([^)]*\))?\s+type-a$')
    if row:
        r.usb3_gen2_type_a_total_min = _int_from_value(row[1])
        r.usb3_gen2_total_min = max(r.usb3_gen2_total_min or 0, r.usb3_gen2_type_a_total_min or 0)
    row = _find_row(rows, r'^(?:суммарное\s+)?количество\s+встроенных\s+в\s+корпус\s+портов\s+usb\s*3\.2\s+gen\s*2(?:\s*\([^)]*\))?\s+type-c$')
    if row:
        r.usb3_gen2_type_c_total_min = _int_from_value(row[1])
    row = _find_row(rows, r'^(?:суммарное\s+)?количество\s+встроенных\s+в\s+корпус\s+портов\s+usb\s*3\.2\s+gen\s*2(?:\s*\([^)]*\))?$')
    if row: r.usb3_gen2_total_min = _int_from_value(row[1])

    row = _find_row(rows, r'^(?:суммарное\s+)?количество\s+встроенных\s+в\s+корпус\s+портов\s+usb\s*3\.(?:x|х)$', r'^количество встроенных в корпус портов usb 3\.(?:x|х)$')
    if row: r.usb3x_total_min = _int_from_value(row[1])
    row = _find_row(rows, r'^(?:суммарное\s+)?количество\s+встроенных\s+в\s+корпус\s+портов\s+usb\s+type-c$')
    if row: r.usb_c_total_min = _int_from_value(row[1])

    # Case dimensions / bays.
    def _set_case_dimension(row, min_attr, max_attr):
        if not row:
            return
        val = _int_from_value(row[1])
        if val is None:
            return
        raw = str(row[1] or '').replace('≤','<=').replace('≥','>=').strip()
        if re.search(r'(?:>=|>|не\s+менее)', raw, re.I):
            setattr(r, min_attr, val)
        else:
            # Bare/exact values and '<'/'≤' stay on the historical max side. An
            # exact dimension is stricter, but max is safer than accidentally
            # rejecting a valid larger chassis in old projects.
            setattr(r, max_attr, val)
    row = _find_row(rows, r'^ширина корпуса$')
    _set_case_dimension(row, 'case_width_min_mm', 'case_width_max_mm')
    row = _find_row(rows, r'^длина корпуса$')
    _set_case_dimension(row, 'case_length_min_mm', 'case_length_max_mm')
    row = _find_row(rows, r'^высота корпуса$')
    _set_case_dimension(row, 'case_height_min_mm', 'case_height_max_mm')
    row = _find_row(rows, r'количество внешних отсеков(?: корпуса)? 5,25', r'количество внешних отсеков(?: корпуса)? 5\.25')
    if row: r.bay_525_min = _int_from_value(row[1])
    row = _find_row(rows, r'количество внешних отсеков(?: корпуса)? 3,5', r'количество внешних отсеков(?: корпуса)? 3\.5')
    if row: r.bay_35_external_min = _int_from_value(row[1])
    row = _find_row(rows, r'количество внутренних отсеков корпуса 2,5')
    if row: r.bay_25_min = _int_from_value(row[1])
    row = _find_row(rows, r'количество внутренних отсеков корпуса 3,25')
    if row: r.bay_325_min = _int_from_value(row[1])
    row = _find_row(rows, r'количество внутренних отсеков корпуса 3,5')
    if row: r.bay_35_min = _int_from_value(row[1])
    row = _find_row(rows, r'наличие выходного аудиоразъема на передней панели')
    if row and _bool_from_value(row[1]) is True: r.front_audio_out_required = True
    row = _find_row(rows, r'наличие входного аудиоразъема для микрофона на передней панели')
    if row and _bool_from_value(row[1]) is True: r.front_mic_in_required = True
    row = _find_row(rows, r'^наличие встроенного выходного аудиоразъема$')
    if row and _bool_from_value(row[1]) is True: r.system_audio_out_required = True
    row = _find_row(rows, r'^наличие встроенного входного аудиоразъема для микрофона$')
    if row and _bool_from_value(row[1]) is True: r.system_mic_in_required = True
    r.protected_case = bool(re.search(r'защищ[её]нн\w+\s+корпус|антивандальн\w+|замок\w*\s+корпус', low))

    # Monitor / AIO display characteristics.
    row = _find_row(rows, r'^диагональ экрана$', r'^размер диагонали$')
    if row: r.monitor_inches = _float_from_value(row[1])
    row = _find_row(rows, r'^разрешение экрана')
    if row:
        r.monitor_resolution = _extract_resolution(row[1])
        r.monitor_resolution_is_min = bool(re.search(r'≥|>=|не\s+менее', row[1], re.I))
    row = _find_row(rows, r'^формат изображения$')
    if row: r.monitor_aspect_ratio = _norm(row[1])
    row = _find_row(rows, r'технология изготовления матрицы')
    if row:
        v = row[1]
        if 'IPS' in v.upper(): r.monitor_matrix = 'IPS'
        else: r.monitor_matrix = _norm(v)
    row = _find_row(rows, r'^частота обновления экрана$', r'^максимальная частота обновления')
    if row: r.monitor_refresh_hz_min = _int_from_value(row[1])
    row = _find_row(rows, r'^время отклика')
    if row:
        r.monitor_response_ms_max = _float_from_value(row[1])
        r.monitor_response_ms_max_inclusive = bool(re.search(r'не\s+более|≤|<=', str(row[1] or ''), re.I))
    row = _find_row(rows, r'^контрастность$')
    if row: r.monitor_contrast_min = _int_from_value(row[1])
    row = _find_row(rows, r'^угол обзора по горизонтали')
    if row: r.monitor_view_angle_h_min = _int_from_value(row[1])
    row = _find_row(rows, r'^угол обзора по вертикали')
    if row: r.monitor_view_angle_v_min = _int_from_value(row[1])
    row = _find_row(rows, r'^яркость')
    if row:
        nums = re.findall(r'\d+(?:[\.,]\d+)?', row[1])
        if nums:
            r.monitor_brightness_min = int(round(_num(nums[0])))
            if len(nums) > 1: r.monitor_brightness_max = int(round(_num(nums[1])))
    row = _find_row(rows, r'наличие встроенных динамиков', r'наличие встроенной акустической системы')
    if row: r.monitor_speakers = _bool_from_value(row[1])
    row = _find_row(rows, r'^стандарт крепления$')
    if row: r.monitor_vesa = _norm(row[1])
    row = _find_row(rows, r'^интерфейс подключения$')
    if row and r.product_type == 'monitor': r.monitor_interfaces = _norm(row[1])
    if r.product_type == 'monitor':
        row = _find_row(rows, r'^количество встроенных в корпус портов hdmi$', r'^количество портов hdmi$')
        if row: r.monitor_hdmi_ports_min = _int_from_value(row[1])
        row = _find_row(rows, r'^количество встроенных в корпус портов display\s*port$', r'^количество портов display\s*port$', r'^общее количество установленных портов display\s*port$')
        if row: r.monitor_dp_ports_min = _int_from_value(row[1])
    row = _find_row(rows, r'^блок питания$')
    if row and r.product_type == 'monitor':
        v = str(row[1] or '').lower()
        if 'внеш' in v: r.monitor_external_psu = True
        elif 'встро' in v or 'внутр' in v: r.monitor_external_psu = False

    row = _find_row(rows, r'^настенное крепление$', r'наличие возможности крепления на стену')
    if row: r.monitor_wall_mount = _bool_from_value(row[1])
    row = _find_row(rows, r'возможность поворота экрана.*портретный режим', r'возможность поворота экрана по вертикали')
    if row: r.monitor_pivot = _bool_from_value(row[1])
    row = _find_row(rows, r'наличие функции регулировки наклона')
    if row: r.monitor_tilt = _bool_from_value(row[1])
    row = _find_row(rows, r'наличие вэб-камеры', r'наличие веб-камеры')
    if row: r.monitor_webcam = _bool_from_value(row[1])
    row = _find_row(rows, r'наличие сенсорного экрана')
    if row: r.monitor_touch = _bool_from_value(row[1])
    row = _find_row(rows, r'наличие usb-концентратора')
    if row: r.monitor_usb_hub = _bool_from_value(row[1])
    row = _find_row(rows, r'^изогнутый экран$')
    if row: r.monitor_curved = _bool_from_value(row[1])
    row = _find_row(rows, r'^глубина цвета$')
    if row: r.monitor_color_depth_bits = _int_from_value(row[1])
    row = _find_row(rows, r'^класс энергетической эффективности$')
    if row: r.monitor_energy_class = _norm(row[1])
    row = _find_row(rows, r'^тип кабеля для подключения к источнику изображения в комплекте$')
    if row: r.monitor_cable_type = _norm(row[1])
    row = _find_row(rows, r'^динамическая контрастность$')
    if row:
        mnum = re.search(r'(\d[\d\s]*)', str(row[1] or ''))
        if mnum: r.monitor_dynamic_contrast_max = int(re.sub(r'\s+','',mnum.group(1)))
    row = _find_row(rows, r'возможность поворота экрана по горизонтали')
    if row: r.monitor_swivel = _bool_from_value(row[1])
    row = _find_row(rows, r'^кабель для подключения к источнику изображения в комплекте$')
    if row: r.monitor_cable_included = _bool_from_value(row[1])
    row = _find_row(rows, r'^потребляемая мощность')
    if row: r.monitor_power_w_max = _float_from_value(row[1])
    row = _find_row(rows, r'^разъем$', r'^разъ[её]м$')
    if row and r.product_type == 'monitor':
        vv=str(row[1] or '').lower().replace('ё','е')
        if 'mini-jack' in vv or '3,5' in vv or '3.5' in vv:
            if 'вход' in vv: r.monitor_audio_in_required = True
            if 'выход' in vv: r.monitor_audio_out_required = True
    row = _find_row(rows, r'максимальная регулировка экрана по высоте', r'регулировка.*по высоте')
    if row: r.monitor_height_adjust_mm_min = _int_from_value(row[1])
    row = _find_row(rows, r'наличие встроенного микрофона')
    if row: r.need_builtin_mic = bool(_bool_from_value(row[1]))
    row = _find_row(rows, r'наличие в корпусе разъемов подключения для наушников и микрофона')
    if row: r.need_audio_jacks = bool(_bool_from_value(row[1]))
    row = _find_row(rows, r'разрешение в[еэ]б-?камеры', r'разрешение web-?камеры')
    if row: r.webcam_mp_min = _float_from_value(row[1])
    row = _find_row(rows, r'механической блокировки видеопотока встроенной камеры', r'механическ.*шторк.*камер')
    if row: r.webcam_privacy_shutter = bool(_bool_from_value(row[1]))

    # Standalone keyboard.
    if r.product_type == 'keyboard':
        row = _find_row(rows, r'^тип подключения$', r'^передача данных клавиатуры$')
        if row:
            v = row[1].lower()
            if 'беспровод' in v:
                r.keyboard_wireless = True; r.keyboard_wired = False
            elif 'провод' in v:
                r.keyboard_wired = True; r.keyboard_wireless = False
        row = _find_row(rows, r'^интерфейс подключения$', r'^интерфейс клавиатуры$')
        if row: r.keyboard_usb = 'usb' in row[1].lower()
        row = _find_row(rows, r'^тип$')
        if row: r.keyboard_fullsize = 'полноразмер' in row[1].lower()
        row = _find_row(rows, r'^раскладка клавиатуры$', r'^раскладка клавиатуры qwerty/йцукен$', r'^раскладка клавиатуры qwerty.*йцукен$')
        if row:
            if 'qwerty' in row[0].lower() and 'йцукен' in row[0].lower() and _bool_from_value(row[1]) is True:
                r.keyboard_layout = 'QWERTY/ЙЦУКЕН'
            else:
                r.keyboard_layout = _norm(row[1])
        row = _find_row(rows, r'^количество клавиш клавиатуры')
        if row: r.keyboard_keys_min = _int_from_value(row[1])
        row = _find_row(rows, r'^способ нанесения русификации клавиатуры$')
        if row: r.keyboard_russification = _norm(row[1])
        for attr, pats in [
            ('keyboard_flexible',(r'^гибкая клавиатура$',)),
            ('keyboard_has_usb_port',(r'^usb порт$',)),
            ('keyboard_multifunction',(r'^мультифункциональные клавиши$',)),
            ('keyboard_touchpad',(r'^встроенный тачпад$',)),
            ('keyboard_palmrest',(r'^подставка для рук$',)),
            ('keyboard_scroll_wheel',(r'^наличие колеса прокрутки$',)),
            ('keyboard_water_protection',(r'^наличие защиты от воды$',)),
            ('keyboard_detachable_cable',(r'^наличие съемного кабеля$', r'^наличие съ[её]много кабеля$')),
            ('keyboard_volume_control',(r'^наличие регулировки громкости$',)),
            ('keyboard_backlight',(r'^наличие подсветки клавиш$',)),
        ]:
            rr = _find_row(rows, *pats)
            if rr: setattr(r, attr, _bool_from_value(rr[1]))
        row = _find_row(rows, r'^длина кабеля$')
        if row:
            nums = re.findall(r'\d+(?:[\.,]\d+)?', row[1])
            if nums:
                r.keyboard_cable_min_m = _num(nums[0])
                if len(nums) > 1: r.keyboard_cable_max_m = _num(nums[1])

    # Standalone mouse.
    if r.product_type == 'mouse':
        row = _find_row(rows, r'^тип сенсора$')
        if row: r.mouse_optical = 'оптич' in row[1].lower()
        row = _find_row(rows, r'^тип подключения$', r'^передача данных манипулятора мышь$')
        if row:
            v = row[1].lower()
            if 'беспровод' in v:
                r.mouse_wireless = True; r.mouse_wired = False
            elif 'провод' in v:
                r.mouse_wired = True; r.mouse_wireless = False
        row = _find_row(rows, r'^интерфейс подключения$', r'^интерфейс манипулятора мышь$')
        if row: r.mouse_usb = 'usb' in row[1].lower()
        row = _find_row(rows, r'^длина кабеля$')
        if row:
            nums = re.findall(r'\d+(?:[\.,]\d+)?', row[1])
            if nums:
                r.mouse_cable_min_m = _num(nums[0])
                if len(nums) > 1: r.mouse_cable_max_m = _num(nums[1])
        row = _find_row(rows, r'^разрешение сенсора')
        if row: r.mouse_dpi_min = _int_from_value(row[1])
        row = _find_row(rows, r'^количество кнопок манипулятора мышь', r'^общее количество кнопок мыш')
        if row: r.mouse_buttons_min = _int_from_value(row[1])
        for attr, pats in [
            ('mouse_programmable_buttons',(r'^наличие программируемых кнопок$',)),
            ('mouse_side_buttons',(r'^наличие боковых кнопок$',)),
            ('mouse_silent_click',(r'^наличие функции тихого клика$',)),
            ('mouse_detachable_cable',(r'^наличие съемного кабеля$', r'^наличие съ[её]много кабеля$')),
        ]:
            rr = _find_row(rows, *pats)
            if rr: setattr(r, attr, _bool_from_value(rr[1]))

    # If KTRU says monoblock or characteristics imply it, pick registry size from minimum diagonal.
    if r.product_type.startswith('aio'):
        r.product_type = 'aio27' if (r.monitor_inches or 0) >= 27 else 'aio24'

    return _freeform_enrich(r, t)



def _freeform_enrich(r: Requirements, text: str) -> Requirements:
    """Parse prose-style tender requirements that are not a KTRU characteristic table.

    Corporate TZs often use sectioned prose (CPU / motherboard / BIOS / RAM) instead of
    a four-column characteristic table.  This function adds conservative fallbacks without
    overwriting stronger table-derived values.
    """
    low = _norm(text).lower().replace('ё', 'е')

    # Quantity. Examples: "2.1 | Системный блок Тип 2 | 100" or prose "Количество 100 шт".
    if not r.quantity:
        pats = [
            r'системн(?:ый|ого)\s+блок[^|\n]{0,80}\|\s*(\d{1,6})\b',
            r'(?:количеств\w*|кол-?во)[^\d]{0,30}(\d{1,6})\s*(?:штук\w*|шт\.?|ед\.?)',
            r'перечень\s+товаров.*?системн(?:ый|ого)\s+блок[^\d]{0,40}(\d{1,6})',
        ]
        for pat in pats:
            m = re.search(pat, text, re.I | re.S)
            if m:
                r.quantity = int(m.group(1)); break

    # CPU performance / architecture requirements.
    m = re.search(r'passmark\s*cpu.{0,120}?не\s+менее\s*([\d\s]{4,})', low, re.I)
    if m and not r.cpu_passmark_min:
        try: r.cpu_passmark_min = int(re.sub(r'\s+', '', m.group(1)))
        except Exception: pass
    if re.search(r'x86[\s\-]*64\s*bit|x86_?64|64[\s\-]*bit', low):
        r.cpu_x86_64_required = True

    # RAM prose: "Не менее 32GB DDR4/DDR5 (каждая планка ... 16GB)", dual-channel, slots.
    m = re.search(r'не\s+менее\s*(\d+)\s*(?:gb|гб)\s*ddr\s*4\s*/\s*ddr\s*5', low)
    if m:
        r.ram_gb_min = max(r.ram_gb_min or 0, int(m.group(1)))
        # Both types are allowed by the TZ; platform logic may choose either QX family.
        if r.ram_type not in ('DDR4','DDR5'):
            r.ram_type = None
    m = re.search(r'кажд(?:ая|ой)\s+планк\w*[^\d]{0,50}не\s+менее\s*(\d+)\s*(?:gb|гб)', low)
    if m: r.ram_module_gb_min = max(r.ram_module_gb_min or 0, int(m.group(1)))
    m = re.search(r'частот\w*\s+не\s+менее\s*(\d{3,5})\s*(?:mhz|мгц)', low)
    if m: r.ram_mhz_min = max(r.ram_mhz_min or 0, int(m.group(1)))
    m = re.search(r'макс\.?\s*поддерживаем\w*\s+об[ъь]?[её]м\s+оперативн\w+\s+памят\w*\s+не\s+менее\s*(\d+)\s*(?:gb|гб)', low)
    if m: r.ram_max_supported_gb_min = max(r.ram_max_supported_gb_min or 0, int(m.group(1)))
    if 'двухканальн' in low:
        r.ram_dual_channel_required = True
    m = re.search(r'не\s+менее\s*(\d+)[-\s]*(?:х|x)?\s*слот\w*\s+для\s+оперативн', low)
    if m: r.ram_slots_min = max(r.ram_slots_min or 0, int(m.group(1)))

    # Generic SSD capacity: do NOT invent NVMe/M.2 when the TZ allows any interface.
    if not r.ssd_gb_min:
        m = re.search(r'\bssd\b.{0,120}?не\s+менее\s*(\d+)\s*(?:gb|гб)', low, re.I)
        if m: r.ssd_gb_min = int(m.group(1))
    if re.search(r'(?:ssd|твердотельн\w*\s+накопител\w*).{0,100}?(?:форм[- ]?фактор\w*\s*)?2[,.]5', low, re.I):
        r.ssd_25_required = True
    # If a prose requirement enumerates SATA / M.2 SATA / M.2 PCIe, all are allowed.
    if re.search(r'ssd\s+sata\s+или\s+м\.?2\s+sata\s+или\s+m?\.?2\s*pcie', low):
        r.ssd_interface = None
        r.ssd_m2_required = False
    if re.search(r'возможност\w*\s+установк\w*\s+дополнительн\w*\s+hdd', low):
        r.extra_hdd_slot_required = True
    m = re.search(r'\b(?:tbw|twd)\b[^\d]{0,30}не\s+менее\s*(\d+)', low)
    if m: r.ssd_tbw_min = int(m.group(1))

    # Wireless can be explicitly forbidden. Registry logic then prefers cardreader, not Wi-Fi.
    if re.search(r'беспроводн\w*\s+связ\w*\s*(?:\||:)?\s*отсутств', low):
        r.need_wifi = False; r.need_bluetooth = False; r.forbid_wireless = True

    # "Без ОС" means no licence in the build even if the same paragraph says Windows/Astra support.
    if re.search(r'\bбез\s+ос\b|операционн\w*\s+систем\w*\s*\([^)]*ос[^)]*\)[^\n]{0,20}\bбез\s+ос\b', low):
        r.need_os = False; r.os_text = None

    # Bundled peripherals and network/audio in prose-style system-block TZs.
    if re.search(r'\bклавиатур\w*\b.{0,180}?проводн', low):
        r.need_keyboard = True; r.keyboard_wired = True; r.keyboard_usb = 'usb' in low
    if re.search(r'\bмыш\w*\b.{0,180}?проводн', low):
        r.need_mouse = True; r.mouse_wired = True; r.mouse_usb = 'usb' in low
    if re.search(r'rj-?45.{0,40}?10\s*/\s*100\s*/\s*1000', low):
        r.ethernet_ports_min = max(r.ethernet_ports_min or 0, 1)
        r.ethernet_mbps_min = max(r.ethernet_mbps_min or 0, 1000)
    if re.search(r'аудио\s+вход\w*\s+и\s+выход|mini\s*jack\s*3[\.,]5', low):
        r.need_audio_jacks = True

    # Motherboard / I/O prose requirements.
    if re.search(r'не\s+менее\s*1\s+цифров\w*\s+порт\w*\s+display\s*port', low):
        r.system_dp_min = max(r.system_dp_min or 0, 1)
    if re.search(r'не\s+менее\s*1\s+цифров\w*\s+порт\w*\s+hdmi', low):
        r.system_hdmi_min = max(r.system_hdmi_min or 0, 1)
    if re.search(r'pci-?e\s*x1\s+и\s*x16', low):
        r.pcie_x1_min = max(r.pcie_x1_min or 0, 1); r.pcie_x16_min = max(r.pcie_x16_min or 0, 1)
    m = re.search(r'передн\w*\s+панел\w*\s*:\s*не\s+менее\s*(\d+)[-\s]*(?:х|x)?\s*usb\s*type-a', low)
    if m: r.usb_a_front_min = max(r.usb_a_front_min or 0, int(m.group(1)))
    m = re.search(r'передн\w*\s+панел\w*.*?не\s+менее\s*(\d+)[-\s]*(?:го|х|x)?\s*usb\s*type-c', low)
    if m: r.usb_c_front_min = max(r.usb_c_front_min or 0, int(m.group(1)))
    m = re.search(r'задн\w*\s+панел\w*\s*:\s*не\s+менее\s*(\d+)[-\s]*(?:х|x)?\s*usb\s*type-a', low)
    if m: r.usb_a_rear_min = max(r.usb_a_rear_min or 0, int(m.group(1)))
    m = re.search(r'одновременн\w*\s+работ\w*\s+не\s+менее\s*(\d+)[-\s]*(?:х|x)?\s+монитор', low)
    if m: r.simultaneous_monitors_min = int(m.group(1))
    if re.search(r'\btpm\s*2\.0\b|intel\s+ptt|amd\s+ftpm', low): r.tpm_required = True
    if re.search(r'датчик\w*\s+температур\w*.*напряжен.*оборот.*вскрыт', low): r.board_sensors_required = True
    if 'astra linux' in low and re.search(r'конфигурац\w*\s+bios|конфигурир\w*\s+bios', low): r.bios_astra_management_required = True
    if re.search(r'парол\w*\s+администратор\w*\s+bios', low): r.bios_admin_password_required = True

    # Compact case dimensions in prose, e.g. "Не более 175 мм х 380 мм х 420 мм".
    m = re.search(r'не\s+более\s*(\d+)\s*мм\s*[xх×]\s*(\d+)\s*мм\s*[xх×]\s*(\d+)\s*мм', low)
    if m and not (r.case_width_max_mm or r.case_length_max_mm or r.case_height_max_mm):
        r.case_width_max_mm, r.case_length_max_mm, r.case_height_max_mm = map(int, m.groups())

    # Descriptive-table / narrative procurement format ("Технические характеристики" in one cell).
    # CPU
    m = re.search(r'(?:общее\s+)?количеств\w*\s+ядер\s+процессор\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+)', low)
    if m: r.cpu_cores_min = max(r.cpu_cores_min or 0, int(m.group(1)))
    m = re.search(r'(?:максимальн\w*\s+(?:число|количеств\w*)|количеств\w*)\s+поток\w*\s+процессор\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+)', low)
    if m: r.cpu_threads_min = max(r.cpu_threads_min or 0, int(m.group(1)))
    m = re.search(r'базов\w*\s+(?:тактов\w*\s+)?частот\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+(?:[\.,]\d+)?)\s*ггц', low)
    if m: r.cpu_freq_ghz_min = max(r.cpu_freq_ghz_min or 0, _num(m.group(1)))
    m = re.search(r'максимальн\w*\s+(?:тактов\w*\s+)?частот\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+(?:[\.,]\d+)?)\s*ггц', low)
    if m: r.cpu_freq_max_ghz_min = max(r.cpu_freq_max_ghz_min or 0, _num(m.group(1)))
    m = re.search(r'об[ъь]?[её]м\s+к[эе]ш\w*\s+памят\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+)\s*(?:мбайт|мб)', low)
    if m: r.cpu_l3_mb_min = max(r.cpu_l3_mb_min or 0, int(m.group(1)))
    m = re.search(r'\btdp\b\s*[:\-–—]?\s*не\s+более\s*(\d+)\s*вт', low)
    if m: r.cpu_tdp_w_max = int(m.group(1)) if not r.cpu_tdp_w_max else min(r.cpu_tdp_w_max, int(m.group(1)))
    if re.search(r'встроенн\w*\s+графическ\w*\s+адаптер\w*\s*[:\-–—]?\s*налич', low):
        r.need_integrated_graphics = True; r.need_gpu = False

    # RAM. "не ниже DDR4" allows DDR4 and newer, unlike an exact "DDR4" KTRU value.
    m = re.search(r'тип\s+оперативн\w*\s+памят\w*\s*[:\-–—]?\s*не\s+ниже\s+ddr\s*([45])', low)
    if m:
        r.ram_type_min_generation = max(r.ram_type_min_generation or 0, int(m.group(1)))
        if r.ram_type and int(re.sub(r'\D','',r.ram_type) or 0) < r.ram_type_min_generation:
            r.ram_type = None
    m = re.search(r'об[ъь]?[её]м\s+оперативн\w*\s+памят\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+)\s*(?:гигабайт|гб|gb)', low)
    if m and not r.ram_gb_min: r.ram_gb_min = int(m.group(1))
    m = re.search(r'количеств\w*\s+слот\w*\s+оперативн\w*\s+памят\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+)', low)
    if m: r.ram_slots_min = max(r.ram_slots_min or 0, int(m.group(1)))

    # SSD and motherboard/system I/O.
    m = re.search(r'(?:общ\w*\s+об[ъь]?[её]м\s+твердотельн\w*\s+накопител\w*\s*\(ssd\)|об[ъь]?[её]м\s+ssd\s+накопител\w*).{0,60}?не\s+менее\s*(\d+)\s*(?:гигабайт|гб|gb)', low)
    if m: r.ssd_gb_min = max(r.ssd_gb_min or 0, int(m.group(1)))
    m = re.search(r'количеств\w*\s+(?:выходн\w*\s+)?раз[ъь]?[её]м\w*\s+hdmi\s*[:\-–—]?\s*не\s+менее\s*(\d+)', low)
    if m: r.system_hdmi_min = max(r.system_hdmi_min or 0, int(m.group(1)))
    m = re.search(r'количеств\w*\s+раз[ъь]?[её]м\w*\s+display\s*port\s*[:\-–—]?\s*не\s+менее\s*(\d+)', low)
    if m: r.system_dp_min = max(r.system_dp_min or 0, int(m.group(1)))
    m = re.search(r'количеств\w*\s+раз[ъь]?[её]м\w*\s+rj-?45\s*[:\-–—]?\s*не\s+менее\s*(\d+)', low)
    if m:
        r.ethernet_ports_min = max(r.ethernet_ports_min or 0, int(m.group(1)))
        r.ethernet_mbps_min = max(r.ethernet_mbps_min or 0, 1000)
    m = re.search(r'общее\s+количеств\w*\s+порт\w*\s+usb\s*2\.0\s*[:\-–—]?\s*не\s+менее\s*(\d+)', low)
    if m: r.usb2_total_min = max(r.usb2_total_min or 0, int(m.group(1)))
    m = re.search(r'общее\s+количеств\w*\s+порт\w*\s+usb\s*3\.2\s*gen\s*1(?:\s*\([^)]*\))?\s*[:\-–—]?\s*не\s+менее\s*(\d+)', low)
    if m: r.usb3_gen1_total_min = max(r.usb3_gen1_total_min or 0, int(m.group(1)))
    m = re.search(r'аудио\s+раз[ъь]?[её]м\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+)', low)
    if m:
        r.audio_jacks_min = max(r.audio_jacks_min or 0, int(m.group(1))); r.need_audio_jacks = True

    # AIO/display/camera.
    m = re.search(r'диагонал\w*\s+экрана(?:\s*\([^)]*\))?\s*[:\-–—]?\s*не\s+менее\s*(\d+(?:[\.,]\d+)?)', low)
    if m: r.monitor_inches = max(r.monitor_inches or 0, _num(m.group(1)))
    m = re.search(r'разрешени\w*\s+экрана\s*[:\-–—]?\s*не\s+менее\s*(\d{3,4})\s*[xх×]\s*(\d{3,4})', low)
    if m:
        r.monitor_resolution = f'{m.group(1)}x{m.group(2)}'
        r.monitor_resolution_is_min = True
    m = re.search(r'технологи\w*\s+изготовлени\w*\s+матриц\w*\s*[:\-–—]?\s*([a-z0-9()\s,]+?)(?=\s+(?:контрастност|угл|общее\s+количеств|аудио|$))', low, re.I)
    if m and 'ips' in m.group(1).lower(): r.monitor_matrix = 'IPS'
    m = re.search(r'контрастност\w*\s+экрана\s*[:\-–—]?\s*не\s+менее\s*(\d+)\s*:\s*1', low)
    if m: r.monitor_contrast_min = max(r.monitor_contrast_min or 0, int(m.group(1)))
    m = re.search(r'угл\w*\s+обзор\w*\s+экрана\s+по\s+горизонтал\w*\s*/\s*вертикал\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+)\s*/\s*(\d+)', low)
    if m:
        r.monitor_view_angle_h_min=max(r.monitor_view_angle_h_min or 0,int(m.group(1)))
        r.monitor_view_angle_v_min=max(r.monitor_view_angle_v_min or 0,int(m.group(2)))
    if re.search(r'веб-?камер\w*\s+встроенн\w*\s*[:\-–—]?\s*налич', low):
        r.webcam_mp_min = r.webcam_mp_min or None
    m = re.search(r'количеств\w*\s+мегапиксел\w*\s+веб-?камер\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+(?:[\.,]\d+)?)', low)
    if m: r.webcam_mp_min = max(r.webcam_mp_min or 0, _num(m.group(1)))
    if re.search(r'механическ\w*\s+блокировк\w*\s+видеопоток\w*\s+камер\w*\s*[:\-–—]?\s*налич', low): r.webcam_privacy_shutter = True
    if re.search(r'встроенн\w*\s+микрофон\w*\s*[:\-–—]?\s*налич', low): r.need_builtin_mic = True
    if re.search(r'встроенн\w*\s+динамик\w*\s*[:\-–—]?\s*налич', low): r.monitor_speakers = True

    # Wireless and power supply.
    if re.search(r'встроенн\w*\s+беспроводн\w*\s+модул\w*\s+wi-?fi\s*[:\-–—]?\s*налич', low): r.need_wifi = True
    if re.search(r'встроенн\w*\s+беспроводн\w*\s+модул\w*\s+bluetooth\s*[:\-–—]?\s*налич', low): r.need_bluetooth = True
    if re.search(r'внешн\w*\s+блок\w*\s+питан\w*\s*[:\-–—]?\s*налич', low): r.external_psu_required = True
    m = re.search(r'мощност\w*\s+блок\w*\s+питан\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+)\s*вт', low)
    if m: r.psu_w_min = max(r.psu_w_min or 0, int(m.group(1)))
    m = re.search(r'гаранти\w*[^\n]{0,50}?не\s+менее\s*(\d+)\s*месяц', low)
    if m: r.warranty_months_min = max(r.warranty_months_min or 0, int(m.group(1)))

    # Bundled keyboard and mouse can be wireless and have their own minimums.
    if re.search(r'клавиатур\w*\s+и\s+мыш\w*\s+в\s+комплект\w*\s+поставк\w*\s*[:\-–—]?\s*налич', low):
        r.need_keyboard = True; r.need_mouse = True
    if re.search(r'тип\s+подключени\w*\s+мыш\w*\s*[:\-–—]?\s*беспроводн', low):
        r.need_mouse = True; r.mouse_wireless = True; r.mouse_wired = False
    if re.search(r'тип\s+подключени\w*\s+клавиатур\w*\s*[:\-–—]?\s*беспроводн', low):
        r.need_keyboard = True; r.keyboard_wireless = True; r.keyboard_wired = False
    if re.search(r'тип\s+сенсор\w*\s+мыш\w*\s*[:\-–—]?\s*оптическ', low):
        r.need_mouse = True; r.mouse_optical = True; r.mouse_sensor_text = 'оптический светодиодный'
    m = re.search(r'общее\s+количеств\w*\s+кнопок\s+мыш\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+)', low)
    if m: r.mouse_buttons_min = max(r.mouse_buttons_min or 0, int(m.group(1)))
    m = re.search(r'общее\s+количеств\w*\s+клавиш\s+клавиатур\w*\s*[:\-–—]?\s*не\s+менее\s*(\d+)', low)
    if m: r.keyboard_keys_min = max(r.keyboard_keys_min or 0, int(m.group(1)))
    if re.search(r'цифров\w*\s+блок\w*\s*[:\-–—]?\s*налич', low): r.keyboard_numeric_keypad = True
    if re.search(r'формат\s+клавиатур\w*\s*[:\-–—]?\s*полноразмерн', low): r.keyboard_fullsize = True
    m = re.search(r'способ\s+нанесени\w*\s+русификац\w*\s+клавиатур\w*\s*[:\-–—]?\s*([^;\n]+)', low)
    if m and not r.keyboard_russification: r.keyboard_russification = _norm(m.group(1))

    # The descriptive table names the product explicitly; preserve AIO size after prose parsing.
    if r.product_type.startswith('aio'):
        r.product_type = 'aio27' if (r.monitor_inches or 0) >= 27 else 'aio24'

    # Important prose-only requirements that cannot be proven from the supplied QX sheet.
    manual = []
    if re.search(r'серийн\w*\s+номер\w*\s+и\s+модел\w*\s+системн\w*\s+блок\w*.*bios', low):
        manual.append('Модель и серийный номер системного блока в BIOS; сохранение при сбросе/обновлении BIOS')
    if re.search(r'актуальн\w*\s+драйвер\w*.*windows\s*10\s*/\s*11.*astra', low):
        manual.append('Актуальные драйверы всех встроенных устройств для Windows 10/11 и Astra Linux на сайте производителя')
    if re.search(r'тестов\w*\s+образц\w*.*обязатель', low):
        manual.append('Обязательное предоставление тестового образца и прохождение тестирования заказчика')
    if r.cpu_passmark_min:
        manual.append(f'PassMark CPU Mark ≥ {r.cpu_passmark_min}: перепроверить на cpubenchmark.net на дату подачи заявки')
    if r.bios_astra_management_required:
        manual.append('Управление/чтение BIOS из Astra Linux из консоли: требуется подтверждение производителя/тест')
    if r.bios_admin_password_required:
        manual.append('Управление паролем администратора BIOS из ОС: требуется подтверждение производителя/тест')
    if r.board_sensors_required:
        manual.append('Датчики температуры/напряжения/оборотов/вскрытия: требуется подтверждение')
    if r.ssd_tbw_min:
        manual.append(f'Ресурс SSD TBW/TWD ≥ {r.ssd_tbw_min}: проверить у выбранного SSD')
    if r.extra_hdd_slot_required:
        manual.append('Возможность установки дополнительного HDD с крепежом и питанием')
    if r.external_psu_required:
        manual.append('ТЗ требует внешний блок питания — проверить тип БП выбранной моноблочной платформы')
    if r.warranty_months_min:
        manual.append(f'Гарантия на оборудование ≥ {r.warranty_months_min} месяцев')
    _igpu_freq_m = re.search(
        r'частота графического контроллера интегрированного в процессор[^\n]{0,80}?(?:≥|не\s+менее)\s*(\d+(?:[\.,]\d+)?)\s*(мегагерц|мгц)?',
        low, re.I
    )
    if _igpu_freq_m:
        _igpu_freq = _num(_igpu_freq_m.group(1))
        _igpu_unit = 'МГц'
        manual.append(
            f'Частота встроенного графического контроллера ≥ {_igpu_freq:g} {_igpu_unit}: '
            'текущий справочник CPU не хранит этот параметр, требуется подтверждение по спецификации выбранного процессора'
        )
    if re.search(r'ред\s+ос.{0,80}(?:верси\w*\s*)?8|совместим\w*.*ред\s+ос', low):
        manual.append('Совместимость с РЕД ОС 8: требуется подтверждение/проверка драйверов и штатной работы')
    for item in manual:
        if item not in r.manual_requirements:
            r.manual_requirements.append(item)
    return r

def parse_tz(filename: str, data: bytes):
    lower = filename.lower()
    if lower.endswith('.docx'):
        sections, text = _docx_sections(data)
    elif lower.endswith(('.xlsx', '.xlsm')):
        sections, text = _xlsx_sections(data)
    else:
        text = extract_text(filename, data)
        sections = _split_text_positions(text)
    reqs = [parse_one(section, title) for title, section in sections]
    return reqs, text
