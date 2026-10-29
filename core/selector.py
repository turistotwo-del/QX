from dataclasses import dataclass, asdict, field
import math
import re

from .registry import find_registry_record
from .defaults import QX_SPECS, CASE_SPECS, AIO_SPECS, REGISTRY_MODULE_SPECS
from .storage import normalize_prices
from .cpu_catalog import compatible_cpus_ignoring_selected, fallback_cpu, cpu_details, cpu_by_model


@dataclass
class Component:
    category: str
    name: str
    qty: float = 1.0
    price: float = 0.0
    price_input: str = ''
    source: str = 'Вручную'
    query: str = ''
    url: str = ''
    note: str = ''
    registry: bool = False
    alternatives: list = field(default_factory=list)
    constraints: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def _round_capacity(gb, choices):
    if not gb:
        return choices[0]
    for c in choices:
        if gb <= c:
            return c
    return int(math.ceil(gb / 1024) * 1024)


def _profile_label(profile):
    if not profile:
        return 'QX'
    return str(profile.get('manufacturer') or profile.get('profile_name') or profile.get('name') or 'Пользовательская база').strip()


def _empty_board(platform='amd'):
    """Safe board shell used when a custom profile is incomplete.

    Unknown values remain zero/empty, so compatibility checks fail visibly instead of
    silently inheriting QX characteristics.
    """
    return {
        'name': 'Материнская плата — НЕ ЗАПОЛНЕНО',
        'price': 0.0,
        'registry': False,
        'registry_number': '',
        'socket': '', 'chipset': '', 'form_factor': '',
        'ram_type': '', 'ram_max_gb': 0, 'ram_max_mhz': 0, 'ram_slots': 0,
        'ethernet_mbps': 0, 'ethernet_ports': 0,
        'video': {}, 'm2_key_m': 0, 'm2_key_e': 0, 'm2_key_e_via_adapter': 0, 'sata': 0,
        'pcie_x1': 0, 'pcie_x16': 0, 'tpm_header': 0,
        'usb_external': {}, 'platform': platform,
    }


def _profile_board(profile, platform):
    if not profile:
        return None
    boards = profile.get('boards') or {}
    raw = boards.get(platform) if isinstance(boards, dict) else None
    if not raw or not str(raw.get('name') or '').strip():
        return None
    out = _empty_board(platform)
    out.update(dict(raw))
    out['video'] = dict(raw.get('video') or {})
    out['usb_external'] = dict(raw.get('usb_external') or {})
    out['platform'] = platform
    return out


def _profile_components(profile):
    if not profile:
        return []
    out = []
    for item in profile.get('components') or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        if not name:
            continue
        x = dict(item)
        x['name'] = name
        x['price'] = float(item.get('price') or 0)
        x['registry'] = bool(item.get('registry'))
        x['condition'] = str(item.get('condition') or 'always')
        out.append(x)
    return out


def _condition_matches(item, req, platform):
    cond = str(item.get('condition') or 'always').strip().lower()
    if cond in ('always', 'всегда', ''):
        return True
    if cond in ('wifi', 'wi-fi', 'если нужен wi-fi', 'wifi_or_bluetooth', 'если нужен wi-fi или bluetooth'):
        return bool(req.need_wifi or req.need_bluetooth)
    if cond in ('cardreader', 'картридер', 'если нужен картридер'):
        return bool(req.need_cardreader)
    if cond in ('hdd', 'если нужен hdd'):
        return bool(req.hdd_gb_min)
    if cond in ('gpu', 'если нужна gpu', 'если нужна дискретная gpu'):
        return bool(req.need_gpu)
    if cond in ('amd', 'только amd'):
        return platform == 'amd'
    if cond in ('intel', 'только intel'):
        return platform == 'intel'
    if cond in ('wireless_forbidden', 'если wi-fi запрещён'):
        return bool(req.forbid_wireless)
    return False


def _profile_selected_components(profile, req, platform):
    return [x for x in _profile_components(profile) if _condition_matches(x, req, platform)]


def _profile_cardreader_spec(profile, req, platform):
    """Return confirmed USB contribution of selected custom cardreader component(s)."""
    result = {'usb2_a':0, 'usb3_gen1_type_a':0, 'usb3_gen1_type_c':0,
              'usb3_gen2_type_a':0, 'usb3_gen2_type_c':0, 'location':'unknown'}
    for item in _profile_selected_components(profile, req, platform):
        role = str(item.get('role') or '').lower()
        cat = str(item.get('category') or '').lower()
        if 'cardreader' not in role and 'картрид' not in cat:
            continue
        result['usb2_a'] += int(item.get('usb2_a') or 0)
        result['usb3_gen1_type_a'] += int(item.get('usb3_gen1_type_a') or 0)
        result['usb3_gen1_type_c'] += int(item.get('usb3_gen1_type_c') or 0)
        result['usb3_gen2_type_a'] += int(item.get('usb3_gen2_type_a') or 0)
        result['usb3_gen2_type_c'] += int(item.get('usb3_gen2_type_c') or 0)
        loc = str(item.get('location') or '').lower()
        if loc in ('front','передняя','передняя панель'):
            result['location'] = 'front'
    return result


def _effective_m2_key_e(board):
    """Confirmed Key E availability including an explicitly modelled QX adapter."""
    board = board or {}
    return max(int(board.get('m2_key_e') or 0), int(board.get('m2_key_e_via_adapter') or 0))


def _board_violation_score(req, board):
    """Lower is better for automatic motherboard selection inside a custom profile."""
    score = 0
    exact_ram = (req.ram_type or '').upper()
    have_ram = str(board.get('ram_type') or '').upper()
    if exact_ram and have_ram != exact_ram:
        score += 1000
    min_gen = int(getattr(req, 'ram_type_min_generation', 0) or 0)
    have_gen = int(''.join(ch for ch in have_ram if ch.isdigit()) or 0)
    if min_gen and have_gen < min_gen:
        score += 1000 + (min_gen-have_gen)*100
    for need, key in [
        (req.ram_max_supported_gb_min, 'ram_max_gb'), (req.ram_mhz_min, 'ram_max_mhz'),
        (req.ram_slots_min, 'ram_slots'), (req.m2_key_m_min, 'm2_key_m'),
        (req.ethernet_ports_min, 'ethernet_ports'),
        (req.ethernet_mbps_min, 'ethernet_mbps'), (req.pcie_x1_min, 'pcie_x1'),
        (req.pcie_x16_min, 'pcie_x16'),
    ]:
        if need is not None and float(board.get(key) or 0) < float(need):
            score += 100 + int(float(need)-float(board.get(key) or 0))
    if req.m2_key_e_min is not None and _effective_m2_key_e(board) < int(req.m2_key_e_min or 0):
        score += 100 + int(req.m2_key_e_min or 0) - _effective_m2_key_e(board)
    video = board.get('video') or {}
    if req.system_hdmi_min and int(video.get('HDMI',0)) < int(req.system_hdmi_min): score += 100
    if req.system_dp_min and int(video.get('DisplayPort',0)) < int(req.system_dp_min): score += 100
    # Price is only a tiny tie-breaker after technical compliance.
    score += min(float(board.get('price') or 0) / 1_000_000.0, 0.99)
    return score


def resolve_platform(req, equipment_profile=None):
    warnings = []
    if req.product_type in ('monitor', 'keyboard', 'mouse'):
        return None, warnings

    # For a saved non-QX equipment profile choose only among motherboards that the
    # specialist actually entered. Never borrow QX board facts for another vendor.
    if equipment_profile:
        available = [(p, _profile_board(equipment_profile, p)) for p in ('amd','intel')]
        available = [(p,b) for p,b in available if b]
        label = _profile_label(equipment_profile)
        if req.platform in ('intel','amd'):
            platform = req.platform
            if not _profile_board(equipment_profile, platform):
                warnings.append(f'В базе «{label}» не заполнена материнская плата для {platform.upper()}. Будет показана строка «НЕ ЗАПОЛНЕНО», характеристики QX не подставляются.')
            return platform, warnings
        if available:
            platform, board = min(available, key=lambda pb: _board_violation_score(req, pb[1]))
            if len(available) > 1:
                warnings.append(f'Платформа прямо не указана: из базы «{label}» автоматически выбрана {platform.upper()} по требованиям ТЗ и характеристикам сохранённых плат.')
            else:
                warnings.append(f'Платформа прямо не указана: в базе «{label}» доступна только {platform.upper()} плата, она и выбрана.')
            if _board_violation_score(req, board) >= 100:
                warnings.append(f'Сохранённая плата «{board.get("name") or "без названия"}» может не закрывать часть требований ТЗ. Проверь таблицу совместимости ниже.')
            return platform, warnings
        platform = 'intel' if (req.ram_type or '').upper() == 'DDR5' else 'amd'
        warnings.append(f'В базе «{label}» пока нет заполненной материнской платы. Выбрана ветка {platform.upper()} только для продолжения расчёта; строка платы будет помечена как незаполненная.')
        return platform, warnings

    explicit_platform = req.platform in ('intel', 'amd')
    if explicit_platform:
        # A user's explicit platform choice is authoritative. Never silently replace AMD
        # with Intel (or vice versa) just because the standard QX motherboard misses one
        # requirement. Keep the requested CPU family and report motherboard mismatches
        # separately so the specialist can swap the board/profile intentionally.
        platform = req.platform
        warnings.append(f'Платформа {platform.upper()} выбрана вручную — программа не будет автоматически переключать её на другую.')
    else:
        # When platform is AUTO, evaluate the whole branch: motherboard fit + whether the
        # catalog actually contains at least one CPU satisfying the tender. CPU availability
        # receives a very large penalty so we do not choose a technically closer motherboard
        # and then leave the CPU selector empty.
        candidates = []
        for _p in ('amd', 'intel'):
            _b = QX_SPECS[_p]
            _board_score = _board_violation_score(req, _b)
            _cpu_count = len(_cpu_items_for_board(req, _p, _b))
            _score = _board_score + (0 if _cpu_count else 10000)
            candidates.append((_score, _board_score, -_cpu_count, _p, _cpu_count))
        _score, _board_score, _neg_cpu_count, platform, _cpu_count = min(candidates)
        if _cpu_count:
            warnings.append(
                f'Платформа прямо не указана: автоматически выбрана {platform.upper()} после совместной проверки платы и наличия подходящих процессоров.'
            )
        else:
            platform = min(((_board_violation_score(req, QX_SPECS[p]), p) for p in ('amd','intel')))[1]
            warnings.append(
                f'Платформа прямо не указана: ни в одной стандартной ветке QX не найден подтверждённый CPU под все требования; для продолжения выбрана {platform.upper()} как ближайшая по характеристикам платы.'
            )

    # Important: the checks below are DIAGNOSTICS ONLY. They must never mutate `platform`.
    # Otherwise a manual AMD selection can unexpectedly become Intel and the CPU list is
    # then calculated for the wrong family.
    board = QX_SPECS[platform]
    board_name = str(board.get('name') or ('QX AMD/A520' if platform == 'amd' else 'QX Intel/B760'))
    mismatch = []
    exact_ram = (req.ram_type or '').upper()
    have_ram = str(board.get('ram_type') or '').upper()
    if exact_ram and have_ram and exact_ram != have_ram:
        mismatch.append(f'ТЗ требует {exact_ram}, а {board_name} использует {have_ram}')
    if (req.ram_max_supported_gb_min or 0) and int(board.get('ram_max_gb') or 0) < int(req.ram_max_supported_gb_min or 0):
        mismatch.append(f'поддержка ОЗУ платы {int(board.get("ram_max_gb") or 0)} ГБ < требуемых {int(req.ram_max_supported_gb_min or 0)} ГБ')
    if (req.m2_key_e_min or 0) and _effective_m2_key_e(board) < int(req.m2_key_e_min or 0):
        mismatch.append(f'M.2 Key E: доступно {_effective_m2_key_e(board)}, требуется ≥ {int(req.m2_key_e_min or 0)}')
    elif (req.m2_key_e_min or 0) and int(board.get('m2_key_e_via_adapter') or 0) and not int(board.get('m2_key_e') or 0):
        warnings.append('Требование M.2 Key E закрывается штатным переходником QX для AMD; отдельного Key E на самой плате A520 нет.')
    if (req.m2_key_m_min or 0) and int(board.get('m2_key_m') or 0) < int(req.m2_key_m_min or 0):
        mismatch.append(f'M.2 Key M: у платы {int(board.get("m2_key_m") or 0)}, требуется ≥ {int(req.m2_key_m_min or 0)}')
    min_ddr = int(getattr(req,'ram_type_min_generation',0) or 0)
    have_gen = int(''.join(ch for ch in have_ram if ch.isdigit()) or 0)
    if min_ddr and have_gen < min_ddr:
        mismatch.append(f'плата использует DDR{have_gen or "?"}, а ТЗ требует не ниже DDR{min_ddr}')
    if mismatch:
        prefix = 'Ручной выбор сохранён' if explicit_platform else 'Автовыбор платформы сохранён'
        warnings.append(prefix + ': стандартная материнская плата этой ветки не закрывает часть ТЗ — ' + '; '.join(mismatch) + '. Платформа не переключается молча: при необходимости выбери другую плату/пользовательскую базу.')
    return platform, warnings


def _cpu_items_for_board(req, platform, board=None):
    items = compatible_cpus_ignoring_selected(req, platform)
    if board:
        socket = str(board.get('socket') or '').strip().upper()
        ram_type = str(board.get('ram_type') or '').strip().upper()
        norm = lambda x: ''.join(ch for ch in str(x).upper() if ch.isalnum())
        if socket:
            items = [x for x in items if not getattr(x,'socket','') or norm(getattr(x,'socket','')) == norm(socket)]
        if ram_type:
            items = [x for x in items if not getattr(x,'memory_types',()) or ram_type in [str(m).upper() for m in getattr(x,'memory_types',())]]
    return items


def _cpu_model(req, platform, board=None):
    if req.cpu_model:
        return req.cpu_model
    items = _cpu_items_for_board(req, platform, board)
    return items[0].model if items else 'Процессор по ТЗ — выбрать вручную'


def _cpu_alternatives(req, platform, board=None):
    items = _cpu_items_for_board(req, platform, board)
    names = [x.model for x in items]
    if req.cpu_model and req.cpu_model not in names:
        names.insert(0, req.cpu_model)
    return names


def _cpu_query(req, platform):
    model = _cpu_model(req, platform)
    return f'процессор {model} OEM'


def _extra_panel_counts(req, prefix):
    """Return manually configured port contribution for a front/rear expansion panel."""
    if req is None:
        return {'usb2_a':0,'gen1_a':0,'gen1_c':0,'gen2_a':0,'gen2_c':0}
    return {
        'usb2_a': int(getattr(req, f'extra_{prefix}_usb2_a', 0) or 0),
        'gen1_a': int(getattr(req, f'extra_{prefix}_gen1_a', 0) or 0),
        'gen1_c': int(getattr(req, f'extra_{prefix}_gen1_c', 0) or 0),
        'gen2_a': int(getattr(req, f'extra_{prefix}_gen2_a', 0) or 0),
        'gen2_c': int(getattr(req, f'extra_{prefix}_gen2_c', 0) or 0),
    }


def _aio_spec_for_req(req):
    """Return facts for the actually selected monoblock barebone.

    QX platform facts are trusted only for the standard QX platform. A custom
    platform starts with no inferred facts; the specialist enters its real values.
    """
    if not req or not str(getattr(req, 'product_type', '')).startswith('aio'):
        return None
    if getattr(req, 'aio_platform_mode', 'qx') != 'custom':
        return dict(AIO_SPECS.get(req.product_type, {}))
    return {
        'custom': True,
        'name': getattr(req, 'custom_aio_name', None) or 'Другая моноблочная платформа',
        'price': float(getattr(req, 'custom_aio_price', 0) or 0),
        'diagonal_in': getattr(req, 'custom_aio_diagonal_in', None),
        'resolution': getattr(req, 'custom_aio_resolution', None),
        'refresh_hz': getattr(req, 'custom_aio_refresh_hz', None),
        'matrix': getattr(req, 'custom_aio_matrix', None),
        'built_in_cardreader': bool(getattr(req, 'custom_aio_built_in_cardreader', False)),
        'integrated_psu': bool(getattr(req, 'custom_aio_integrated_psu', True)),
        'psu_w': getattr(req, 'custom_aio_psu_w', None),
        'platform_usb': {
            'usb2_a': int(getattr(req, 'custom_aio_usb2_a', 0) or 0),
            'gen1_a': int(getattr(req, 'custom_aio_gen1_a', 0) or 0),
            'gen1_c': int(getattr(req, 'custom_aio_gen1_c', 0) or 0),
            'gen2_a': int(getattr(req, 'custom_aio_gen2_a', 0) or 0),
            'gen2_c': int(getattr(req, 'custom_aio_gen2_c', 0) or 0),
            'front_usb2': int(getattr(req, 'custom_aio_front_usb2', 0) or 0),
            'front_a': int(getattr(req, 'custom_aio_front_a', 0) or 0),
            'front_c': int(getattr(req, 'custom_aio_front_c', 0) or 0),
        },
    }


def _custom_case_spec(req, cardreader_spec=None):
    """Facts for a non-QX system chassis entered by the specialist.

    Values are intentionally not inferred. The registry cardreader, when selected,
    is treated as an additional module and its confirmed Gen1 A/C ports are added to
    the user-entered front I/O.
    """
    cr = cardreader_spec if cardreader_spec is not None else REGISTRY_MODULE_SPECS.get('cardreader', {})
    base_a = int(getattr(req, 'custom_case_gen1_a_front', 0) or 0)
    base_c = int(getattr(req, 'custom_case_gen1_c_front', 0) or 0)
    return {
        'name': getattr(req, 'custom_case_name', None) or 'Другой корпус',
        'height_mm': getattr(req, 'custom_case_height_mm', None),
        'length_mm': getattr(req, 'custom_case_length_mm', None),
        'width_mm': getattr(req, 'custom_case_width_mm', None),
        'bay_525': int(getattr(req, 'custom_case_bay_525', 0) or 0),
        'bay_25': int(getattr(req, 'custom_case_bay_25', 0) or 0),
        'bay_325': int(getattr(req, 'custom_case_bay_325', 0) or 0),
        'bay_35': int(getattr(req, 'custom_case_bay_35', 0) or 0),
        'bay_35_external': int(getattr(req, 'custom_case_bay_35_external', 0) or 0),
        'front_audio_out': bool(getattr(req, 'custom_case_front_audio_out', False)),
        'front_mic_in': bool(getattr(req, 'custom_case_front_mic_in', False)),
        'usb2_front': int(getattr(req, 'custom_case_usb2_front', 0) or 0),
        'usb3_gen1_a_front_base': base_a,
        'usb3_gen1_c_front_base': base_c,
        'usb3_gen1_a_front_with_cardreader': base_a + int(cr.get('usb3_gen1_type_a', 0)),
        'usb3_gen1_c_front_with_cardreader': base_c + int(cr.get('usb3_gen1_type_c', 0)),
        'usb3_gen2_a_front_base': int(getattr(req, 'custom_case_gen2_a_front', 0) or 0),
        'usb3_gen2_c_front_base': int(getattr(req, 'custom_case_gen2_c_front', 0) or 0),
        'usb3_gen2_a_front_with_cardreader': int(getattr(req, 'custom_case_gen2_a_front', 0) or 0),
        'usb3_gen2_c_front_with_cardreader': int(getattr(req, 'custom_case_gen2_c_front', 0) or 0),
        'protected': bool(getattr(req, 'custom_case_protected', False)),
        'custom': True,
        'price': float(getattr(req, 'custom_case_price', 0) or 0),
    }


def _case_spec_for_req(req, case_key, cardreader_spec=None):
    if not case_key:
        return None
    if case_key == 'custom':
        return _custom_case_spec(req, cardreader_spec=cardreader_spec)
    return CASE_SPECS.get(case_key)


def _usb_inventory(board, case=None, cardreader=False, aio_spec=None, req=None, cardreader_spec=None, extra_components=None):
    """Count known external USB ports for the complete QX configuration.

    Sources are kept separate conceptually:
    - motherboard rear I/O;
    - case front I/O (system blocks);
    - the AIO barebone's built-in *non-registry* cardreader (always included in QX 23.8/27 platforms);
    - an extra registry cardreader, when it is actually selected as the registry module;
    - optional front/rear expansion panels entered manually by the technical specialist.

    The mandatory registry USB-HUB is still not counted as an external chassis port because
    its external port specification is not confirmed in the supplied QX reference data.
    """
    ext = board.get('usb_external', {})
    inv = {
        'usb2_a': int(ext.get('USB 2.0 Type-A', 0)),
        'gen1_a': int(ext.get('USB 3.2 Gen1 Type-A', 0)),
        'gen1_c': int(ext.get('USB 3.2 Gen1 Type-C', 0)),
        'gen2_a': int(ext.get('USB 3.2 Gen2 Type-A', 0)),
        # Gen2x2 Type-C is a higher-speed Type-C port and counts as Gen2-or-better Type-C.
        'gen2_c': sum(int(v) for k, v in ext.items() if 'Type-C' in k and ('Gen2' in k or 'Gen 2' in k)),
    }
    inv['rear_a'] = int(ext.get('USB 2.0 Type-A', 0)) + int(ext.get('USB 3.2 Gen1 Type-A', 0)) + int(ext.get('USB 3.2 Gen2 Type-A', 0))
    inv['front_a'] = 0
    inv['front_c'] = 0
    inv['front_usb2'] = 0
    inv['front_gen1'] = 0

    if case is not None:
        # Count the chassis itself first. A registry cardreader is then added from the
        # actually selected equipment database, rather than assuming QX hardware.
        usb2 = int(case.get('usb2_front', 0))
        g1a = int(case.get('usb3_gen1_a_front_base', 0))
        g1c = int(case.get('usb3_gen1_c_front_base', 0))
        g2a = int(case.get('usb3_gen2_a_front_base', 0))
        g2c = int(case.get('usb3_gen2_c_front_base', 0))
        inv['front_a'] += usb2 + g1a + g2a
        inv['front_c'] += g1c + g2c
        inv['front_usb2'] += usb2
        inv['front_gen1'] += g1a + g1c
        inv['usb2_a'] += usb2
        inv['gen1_a'] += g1a
        inv['gen1_c'] += g1c
        inv['gen2_a'] += g2a
        inv['gen2_c'] += g2c
        if cardreader:
            cr = cardreader_spec if cardreader_spec is not None else REGISTRY_MODULE_SPECS.get('cardreader', {})
            cr_usb2 = int(cr.get('usb2_a', 0))
            cr_g1a = int(cr.get('usb3_gen1_type_a', 0))
            cr_g1c = int(cr.get('usb3_gen1_type_c', 0))
            cr_g2a = int(cr.get('usb3_gen2_type_a', 0))
            cr_g2c = int(cr.get('usb3_gen2_type_c', 0))
            inv['usb2_a'] += cr_usb2
            inv['gen1_a'] += cr_g1a
            inv['gen1_c'] += cr_g1c
            inv['gen2_a'] += cr_g2a
            inv['gen2_c'] += cr_g2c
            # 5.25/3.5 cardreaders are front modules; custom profiles can explicitly set
            # location='unknown' to count only total ports.
            if str(cr.get('location') or 'front').lower() == 'front':
                inv['front_a'] += cr_usb2 + cr_g1a + cr_g2a
                inv['front_c'] += cr_g1c + cr_g2c
                inv['front_usb2'] += cr_usb2
                inv['front_gen1'] += cr_g1a + cr_g1c
    elif aio_spec is not None:
        # Platform-specific front/external I/O. For QX this is the confirmed built-in
        # cardreader. For a custom barebone all counts come only from manual fields.
        pio = aio_spec.get('platform_usb', {}) or {}
        inv['usb2_a'] += int(pio.get('usb2_a', 0))
        inv['gen1_a'] += int(pio.get('gen1_a', 0))
        inv['gen1_c'] += int(pio.get('gen1_c', 0))
        inv['gen2_a'] += int(pio.get('gen2_a', 0))
        inv['gen2_c'] += int(pio.get('gen2_c', 0))
        inv['front_usb2'] += int(pio.get('front_usb2', 0))
        inv['front_a'] += int(pio.get('front_a', 0))
        inv['front_c'] += int(pio.get('front_c', 0))
        # QX AIO barebones include a non-registry cardreader in the platform price.
        built = aio_spec.get('built_in_cardreader_ports', {}) if aio_spec.get('built_in_cardreader') else {}
        inv['gen1_a'] += int(built.get('usb3_gen1_type_a', 0))
        inv['gen1_c'] += int(built.get('usb3_gen1_type_c', 0))
        # Its physical front/rear location was not specified, so only total counts are asserted.
        if cardreader:
            # If a registry cardreader is selected too, it is a separate module in addition to
            # the platform's built-in non-registry cardreader.
            cr = cardreader_spec if cardreader_spec is not None else REGISTRY_MODULE_SPECS.get('cardreader', {})
            inv['usb2_a'] += int(cr.get('usb2_a', 0))
            inv['gen1_a'] += int(cr.get('usb3_gen1_type_a', 0))
            inv['gen1_c'] += int(cr.get('usb3_gen1_type_c', 0))
            inv['gen2_a'] += int(cr.get('usb3_gen2_type_a', 0))
            inv['gen2_c'] += int(cr.get('usb3_gen2_type_c', 0))
    elif cardreader:
        cr = cardreader_spec if cardreader_spec is not None else REGISTRY_MODULE_SPECS.get('cardreader', {})
        inv['usb2_a'] += int(cr.get('usb2_a', 0))
        inv['gen1_a'] += int(cr.get('usb3_gen1_type_a', 0))
        inv['gen1_c'] += int(cr.get('usb3_gen1_type_c', 0))
        inv['gen2_a'] += int(cr.get('usb3_gen2_type_a', 0))
        inv['gen2_c'] += int(cr.get('usb3_gen2_type_c', 0))

    # Reusable non-QX equipment profiles may contain arbitrary registry/non-registry
    # modules with confirmed USB contribution. Count only what the specialist entered.
    for item in (extra_components or []):
        usb2 = int(item.get('usb2_a') or 0)
        g1a = int(item.get('usb3_gen1_type_a') or 0)
        g1c = int(item.get('usb3_gen1_type_c') or 0)
        g2a = int(item.get('usb3_gen2_type_a') or 0)
        g2c = int(item.get('usb3_gen2_type_c') or 0)
        inv['usb2_a'] += usb2
        inv['gen1_a'] += g1a
        inv['gen1_c'] += g1c
        inv['gen2_a'] += g2a
        inv['gen2_c'] += g2c
        loc = str(item.get('location') or 'unknown').lower()
        if loc in ('front','передняя','передняя панель'):
            inv['front_a'] += usb2 + g1a + g2a
            inv['front_c'] += g1c + g2c
            inv['front_usb2'] += usb2
            inv['front_gen1'] += g1a + g1c
        elif loc in ('rear','задняя','задняя панель'):
            inv['rear_a'] += usb2 + g1a + g2a

    # Optional user-installed expansion panels. The program never invents their port mix:
    # the specialist enters the actual panel ports in the requirements editor.
    front_extra = _extra_panel_counts(req, 'front')
    rear_extra = _extra_panel_counts(req, 'rear')
    for extra in (front_extra, rear_extra):
        inv['usb2_a'] += extra['usb2_a']
        inv['gen1_a'] += extra['gen1_a']
        inv['gen1_c'] += extra['gen1_c']
        inv['gen2_a'] += extra['gen2_a']
        inv['gen2_c'] += extra['gen2_c']
    inv['front_a'] += front_extra['usb2_a'] + front_extra['gen1_a'] + front_extra['gen2_a']
    inv['front_c'] += front_extra['gen1_c'] + front_extra['gen2_c']
    inv['front_usb2'] += front_extra['usb2_a']
    inv['front_gen1'] += front_extra['gen1_a'] + front_extra['gen1_c']
    inv['rear_a'] += rear_extra['usb2_a'] + rear_extra['gen1_a'] + rear_extra['gen2_a']

    inv['gen1_total'] = inv['gen1_a'] + inv['gen1_c']
    inv['gen2_total'] = inv['gen2_a'] + inv['gen2_c']
    inv['usb3x_total'] = inv['gen1_total'] + inv['gen2_total']
    inv['type_c_total'] = inv['gen1_c'] + inv['gen2_c']
    return inv


def _usb_requirements_present(req):
    keys = [
        'usb2_total_min','usb2_front_min','usb3_gen1_total_min','usb3_gen1_front_min',
        'usb3_gen1_type_a_total_min','usb3_gen1_type_c_total_min','usb3_gen2_total_min',
        'usb3_gen2_type_a_total_min','usb3_gen2_type_c_total_min','usb3x_total_min','usb_c_total_min',
        'usb_a_front_min','usb_c_front_min','usb_a_rear_min',
    ]
    return any(getattr(req, k, None) is not None for k in keys)


def _usb_summary(inv):
    return (f"USB 2.0 A: {inv['usb2_a']}; Gen1 A: {inv['gen1_a']}; Gen1 C: {inv['gen1_c']}; "
            f"Gen2+ A: {inv['gen2_a']}; Gen2+ C: {inv['gen2_c']}; "
            f"USB 3.x всего: {inv['usb3x_total']}; Type-C всего: {inv['type_c_total']}; "
            f"USB 2.0 спереди: {inv.get('front_usb2',0)}; Gen1 спереди: {inv.get('front_gen1',0)}; "
            f"Type-A спереди: {inv['front_a']}; Type-C спереди: {inv['front_c']}; Type-A сзади: {inv['rear_a']}")


def _usb_deficit_score(req, inv):
    """Technical deficit score used only to choose between registry Wi-Fi/cardreader.

    Zero means all numeric USB requirements represented by the parser are satisfied.
    A lower score is better; price/preference breaks ties elsewhere.
    """
    pairs = [
        (req.usb2_total_min, inv.get('usb2_a',0)),
        (req.usb2_front_min, inv.get('front_usb2',0)),
        (req.usb3_gen1_total_min, inv.get('gen1_total',0)),
        (req.usb3_gen1_front_min, inv.get('front_gen1',0)),
        (req.usb3_gen1_type_a_total_min, inv.get('gen1_a',0)),
        (req.usb3_gen1_type_c_total_min, inv.get('gen1_c',0)),
        (req.usb3_gen2_total_min, inv.get('gen2_total',0)),
        (req.usb3_gen2_type_a_total_min, inv.get('gen2_a',0)),
        (req.usb3_gen2_type_c_total_min, inv.get('gen2_c',0)),
        (req.usb3x_total_min, inv.get('usb3x_total',0)),
        (req.usb_c_total_min, inv.get('type_c_total',0)),
        (req.usb_a_front_min, inv.get('front_a',0)),
        (req.usb_c_front_min, inv.get('front_c',0)),
        (req.usb_a_rear_min, inv.get('rear_a',0)),
    ]
    return sum(max(0, int(need or 0)-int(have or 0)) for need, have in pairs if need is not None)

def _case_fits(req, case, board, cardreader=False, cardreader_spec=None, extra_components=None):
    reasons = []
    ok = True
    if getattr(req, 'protected_case', False) and not bool(case.get('protected')):
        ok = False; reasons.append('ТЗ требует защищённый корпус, а выбранный корпус не отмечен как защищённый')
    for attr, key, label in [
        ('case_width_max_mm','width_mm','ширина'), ('case_length_max_mm','length_mm','длина'), ('case_height_max_mm','height_mm','высота')
    ]:
        lim = getattr(req, attr, None)
        have = case.get(key)
        if lim is not None and have is None:
            ok = False; reasons.append(f'{label}: фактическое значение корпуса не заполнено (требуется < {lim} мм)')
        elif lim is not None and have >= lim:  # ТЗ uses strict < in supplied examples
            ok = False; reasons.append(f'{label} {have} мм не проходит < {lim} мм')
    for attr, key, label in [
        ('case_width_min_mm','width_mm','ширина'), ('case_length_min_mm','length_mm','длина'), ('case_height_min_mm','height_mm','высота')
    ]:
        lim = getattr(req, attr, None)
        have = case.get(key)
        if lim is not None and have is None:
            ok = False; reasons.append(f'{label}: фактическое значение корпуса не заполнено (требуется ≥ {lim} мм)')
        elif lim is not None and have < lim:
            ok = False; reasons.append(f'{label} {have} мм не проходит ≥ {lim} мм')
    for attr, key, label in [
        ('bay_525_min','bay_525','внешних отсеков 5,25'), ('bay_25_min','bay_25','отсеков 2,5'), ('bay_325_min','bay_325','отсеков 3,25'), ('bay_35_min','bay_35','внутренних отсеков 3,5'), ('bay_35_external_min','bay_35_external','внешних отсеков 3,5')
    ]:
        need = getattr(req, attr, None)
        have = case.get(key)
        if need is not None and have is None:
            ok = False; reasons.append(f'{label}: фактическое значение корпуса не заполнено (требуется ≥ {need})')
        elif need is not None and have < need:
            ok = False; reasons.append(f'{label}: {have} < {need}')

    inv = _usb_inventory(board, case, cardreader=cardreader, req=req, cardreader_spec=cardreader_spec, extra_components=extra_components)
    checks = [
        (req.usb2_total_min, inv['usb2_a'], 'USB 2.0 всего'),
        (req.usb2_front_min, inv['front_usb2'], 'USB 2.0 спереди'),
        (req.usb3_gen1_total_min, inv['gen1_total'], 'USB 3.2 Gen1 всего'),
        (req.usb3_gen1_front_min, inv['front_gen1'], 'USB 3.2 Gen1 спереди'),
        (req.usb3_gen1_type_a_total_min, inv['gen1_a'], 'USB 3.2 Gen1 Type-A'),
        (req.usb3_gen1_type_c_total_min, inv['gen1_c'], 'USB 3.2 Gen1 Type-C'),
        (req.usb3_gen2_total_min, inv['gen2_total'], 'USB 3.2 Gen2+ всего'),
        (req.usb3_gen2_type_a_total_min, inv['gen2_a'], 'USB 3.2 Gen2+ Type-A'),
        (req.usb3_gen2_type_c_total_min, inv['gen2_c'], 'USB 3.2 Gen2+ Type-C'),
        (req.usb3x_total_min, inv['usb3x_total'], 'USB 3.x всего'),
        (req.usb_c_total_min, inv['type_c_total'], 'USB Type-C всего'),
        (req.usb_a_front_min, inv['front_a'], 'USB Type-A спереди'),
        (req.usb_c_front_min, inv['front_c'], 'USB Type-C спереди'),
        (req.usb_a_rear_min, inv['rear_a'], 'USB Type-A сзади'),
    ]
    for need, have, label in checks:
        if need is not None and have < need:
            ok = False; reasons.append(f'{label}: {have} < {need}')
    return ok, reasons


def _choose_case_for_profile(req, board, extra_components=None):
    """Choose chassis for a non-QX equipment profile without inventing QX registry logic."""
    mode = str(getattr(req, 'system_case_mode', 'auto') or 'auto')
    if mode == 'custom':
        candidate_cases = ['custom']
    elif mode == 'qx_standard':
        candidate_cases = ['standard']
    elif mode == 'qx_protected':
        candidate_cases = ['protected']
    else:
        candidate_cases = ['protected'] if req.protected_case else ['standard','protected']
    best = None
    for ckey in candidate_cases:
        case = _case_spec_for_req(req, ckey)
        ok, reasons = _case_fits(req, case, board, cardreader=False, extra_components=extra_components)
        score = (0 if ok else 1000) + len(reasons) + (0 if ckey in ('standard','custom') else 1)
        cand = (score, ok, ckey, reasons)
        if best is None or cand[0] < best[0]:
            best = cand
    return best[2], best[3], best[1]


def _choose_case_and_registry_device(req, platform, settings):
    board = QX_SPECS[platform]

    if req.forbid_wireless:
        registry_device = 'cardreader'
    elif req.need_wifi and req.need_cardreader:
        registry_device = settings.get('prefer_registry_device_when_both_required', 'wifi')
    elif req.need_cardreader:
        registry_device = 'cardreader'
    elif req.need_wifi:
        registry_device = 'wifi'
    else:
        registry_device = settings.get('prefer_registry_device_when_not_required', 'wifi')

    mode = str(getattr(req, 'system_case_mode', 'auto') or 'auto')
    if mode == 'custom':
        candidate_cases = ['custom']
    elif mode == 'qx_standard':
        candidate_cases = ['standard']
    elif mode == 'qx_protected':
        candidate_cases = ['protected']
    else:
        candidate_cases = ['protected'] if req.protected_case else ['standard','protected']
    best = None
    for ckey in candidate_cases:
        case = _case_spec_for_req(req, ckey)
        for dev in ([registry_device] if (mode == 'custom' or req.forbid_wireless or req.need_wifi or req.need_cardreader or not settings.get('smart_registry_device', True)) else ['wifi','cardreader']):
            ok, reasons = _case_fits(req, case, board, cardreader=(dev=='cardreader'))
            score = (0 if ok else 1000) + len(reasons) + (0 if ckey in ('standard','custom') else 1)
            cand = (score, ok, ckey, dev, reasons)
            if best is None or cand[0] < best[0]:
                best = cand
    return best[2], best[3], best[4], best[1]


def _compatibility(req, platform, case_key, registry_device=None, board=None, source_label='QX', cardreader_selected=None, cardreader_spec=None, extra_components=None):
    board = dict(board or QX_SPECS[platform])
    case = _case_spec_for_req(req, case_key, cardreader_spec=cardreader_spec)
    checks = []

    def add(label, have, need, ok):
        if need is not None:
            checks.append({'Проверка': label, 'Требование': str(need), 'Факт QX': str(have), 'Статус': 'OK' if ok else 'НЕ ПРОХОДИТ'})

    def unknown(label, need, fact=None):
        if fact is None:
            fact = f'Нет данных в справочнике {source_label}'
        if need:
            checks.append({'Проверка': label, 'Требование': str(need), 'Факт QX': fact, 'Статус': 'НЕТ ДАННЫХ'})

    if req.ram_type:
        add('Тип ОЗУ', board['ram_type'], req.ram_type, board['ram_type'].upper()==req.ram_type.upper())
    min_ddr = int(getattr(req,'ram_type_min_generation',0) or 0)
    if min_ddr:
        have_gen = int(''.join(ch for ch in str(board.get('ram_type','')) if ch.isdigit()) or 0)
        add('Поколение ОЗУ', board.get('ram_type','?'), f'не ниже DDR{min_ddr}', have_gen >= min_ddr)
    add('Макс. частота ОЗУ, МГц', board['ram_max_mhz'], req.ram_mhz_min, board['ram_max_mhz'] >= (req.ram_mhz_min or 0))
    add('Максимально поддерживаемая ОЗУ, ГБ', board['ram_max_gb'], req.ram_max_supported_gb_min, board['ram_max_gb'] >= (req.ram_max_supported_gb_min or 0))
    add('M.2 Key M', board['m2_key_m'], req.m2_key_m_min, board['m2_key_m'] >= (req.m2_key_m_min or 0))
    _m2e_have = _effective_m2_key_e(board)
    _m2e_fact = (f'{_m2e_have} (через штатный переходник QX)' if int(board.get('m2_key_e_via_adapter') or 0) and not int(board.get('m2_key_e') or 0) else _m2e_have)
    add('M.2 Key E', _m2e_fact, req.m2_key_e_min, _m2e_have >= (req.m2_key_e_min or 0))
    add('Ethernet, Мбит/с', board['ethernet_mbps'], req.ethernet_mbps_min, board['ethernet_mbps'] >= (req.ethernet_mbps_min or 0))
    add('Ethernet портов', board['ethernet_ports'], req.ethernet_ports_min, board['ethernet_ports'] >= (req.ethernet_ports_min or 0))
    add('Слотов ОЗУ', board.get('ram_slots', 0), req.ram_slots_min, board.get('ram_slots', 0) >= (req.ram_slots_min or 0))
    add('PCI-E x1', board.get('pcie_x1', 0), req.pcie_x1_min, board.get('pcie_x1', 0) >= (req.pcie_x1_min or 0))
    add('PCI-E x16', board.get('pcie_x16', 0), req.pcie_x16_min, board.get('pcie_x16', 0) >= (req.pcie_x16_min or 0))
    add('SATA', board.get('sata', 0), getattr(req,'sata_ports_min',None), board.get('sata',0) >= (getattr(req,'sata_ports_min',0) or 0))
    if getattr(req,'expansion_slots_min',None) is not None:
        _exp_have=int(board.get('pcie_x1',0) or 0)+int(board.get('pcie_x16',0) or 0)
        add('Слотов расширения PCI-E всего', _exp_have, req.expansion_slots_min, _exp_have >= req.expansion_slots_min)
    if getattr(req,'raid_0_1_5_10_required',False):
        if board.get('raid_0_1_5_10') is not None:
            add('RAID 0/1/5/10', 'Да' if board.get('raid_0_1_5_10') else 'Нет', 'Да', bool(board.get('raid_0_1_5_10')))
        else:
            unknown('RAID 0/1/5/10', 'Да')

    if case is not None:
        if req.protected_case:
            add('Защищённый корпус', 'Да' if case.get('protected') else 'Нет', 'Да', bool(case.get('protected')))
        for label, key, need in [
            ('Ширина корпуса, мм','width_mm',req.case_width_max_mm),
            ('Длина корпуса, мм','length_mm',req.case_length_max_mm),
            ('Высота корпуса, мм','height_mm',req.case_height_max_mm),
        ]:
            have = case.get(key)
            if need is not None:
                if have is None:
                    checks.append({'Проверка':label,'Требование':f'< {need}','Факт QX':'не заполнено','Статус':'НЕТ ДАННЫХ'})
                else:
                    add(label, have, f'< {need}', have < need)
        add('Отсеки 5,25', case['bay_525'], req.bay_525_min, case['bay_525'] >= (req.bay_525_min or 0))
        add('Отсеки 2,5', case['bay_25'], req.bay_25_min, case['bay_25'] >= (req.bay_25_min or 0))
        add('Отсеки 3,5', case['bay_35'], req.bay_35_min, case['bay_35'] >= (req.bay_35_min or 0))
        if getattr(req,'bay_35_external_min',None) is not None:
            have=case.get('bay_35_external')
            if have is None: unknown('Внешние отсеки 3,5', f'≥ {req.bay_35_external_min}')
            else: add('Внешние отсеки 3,5', have, req.bay_35_external_min, int(have) >= int(req.bay_35_external_min))
        if getattr(req,'front_audio_out_required',False):
            if 'front_audio_out' in case: add('Аудиовыход спереди', 'Да' if case.get('front_audio_out') else 'Нет', 'Да', bool(case.get('front_audio_out')))
            else: unknown('Аудиовыход спереди','Да')
        if getattr(req,'front_mic_in_required',False):
            if 'front_mic_in' in case: add('Микрофонный вход спереди', 'Да' if case.get('front_mic_in') else 'Нет', 'Да', bool(case.get('front_mic_in')))
            else: unknown('Микрофонный вход спереди','Да')

    if cardreader_selected is None:
        cardreader_selected = (registry_device == 'cardreader')
    inv = _usb_inventory(board, case, cardreader=bool(cardreader_selected), aio_spec=_aio_spec_for_req(req) if req.product_type.startswith('aio') else None, req=req, cardreader_spec=cardreader_spec, extra_components=extra_components)
    add('USB 2.0 всего', inv['usb2_a'], req.usb2_total_min, inv['usb2_a'] >= (req.usb2_total_min or 0))
    if case is not None or any(_extra_panel_counts(req, 'front').values()):
        add('USB 2.0 спереди', inv['front_usb2'], req.usb2_front_min, inv['front_usb2'] >= (req.usb2_front_min or 0))
    elif req.usb2_front_min is not None:
        unknown('USB 2.0 спереди', f'≥ {req.usb2_front_min}')
    add('USB 3.2 Gen1 всего', inv['gen1_total'], req.usb3_gen1_total_min, inv['gen1_total'] >= (req.usb3_gen1_total_min or 0))
    if case is not None or any(_extra_panel_counts(req, 'front').values()):
        add('USB 3.2 Gen1 спереди', inv['front_gen1'], req.usb3_gen1_front_min, inv['front_gen1'] >= (req.usb3_gen1_front_min or 0))
    elif req.usb3_gen1_front_min is not None:
        unknown('USB 3.2 Gen1 спереди', f'≥ {req.usb3_gen1_front_min}')
    add('USB 3.2 Gen1 Type-A', inv['gen1_a'], req.usb3_gen1_type_a_total_min, inv['gen1_a'] >= (req.usb3_gen1_type_a_total_min or 0))
    add('USB 3.2 Gen1 Type-C', inv['gen1_c'], req.usb3_gen1_type_c_total_min, inv['gen1_c'] >= (req.usb3_gen1_type_c_total_min or 0))
    add('USB 3.2 Gen2+ всего', inv['gen2_total'], req.usb3_gen2_total_min, inv['gen2_total'] >= (req.usb3_gen2_total_min or 0))
    add('USB 3.2 Gen2+ Type-A', inv['gen2_a'], req.usb3_gen2_type_a_total_min, inv['gen2_a'] >= (req.usb3_gen2_type_a_total_min or 0))
    add('USB 3.2 Gen2+ Type-C', inv['gen2_c'], req.usb3_gen2_type_c_total_min, inv['gen2_c'] >= (req.usb3_gen2_type_c_total_min or 0))
    add('USB 3.x всего', inv['usb3x_total'], req.usb3x_total_min, inv['usb3x_total'] >= (req.usb3x_total_min or 0))
    add('USB Type-C всего', inv['type_c_total'], req.usb_c_total_min, inv['type_c_total'] >= (req.usb_c_total_min or 0))
    if case is not None or any(_extra_panel_counts(req, 'front').values()):
        add('USB Type-A спереди', inv['front_a'], req.usb_a_front_min, inv['front_a'] >= (req.usb_a_front_min or 0))
        add('USB Type-C спереди', inv['front_c'], req.usb_c_front_min, inv['front_c'] >= (req.usb_c_front_min or 0))
    else:
        unknown('USB Type-A спереди', f'≥ {req.usb_a_front_min}' if req.usb_a_front_min else None)
        unknown('USB Type-C спереди', f'≥ {req.usb_c_front_min}' if req.usb_c_front_min else None)
    add('USB Type-A сзади', inv['rear_a'], req.usb_a_rear_min, inv['rear_a'] >= (req.usb_a_rear_min or 0))

    if req.tpm_required:
        unknown('TPM 2.0 / PTT / fTPM', 'Да', 'В справочнике платы есть TPM-разъём' if board.get('tpm_header') else 'Нет подтверждения TPM 2.0 в переданном справочнике')
    if req.simultaneous_monitors_min:
        outputs = sum(int(v) for v in board.get('video', {}).values())
        unknown('Одновременная работа мониторов', f'≥ {req.simultaneous_monitors_min}', f'Физических видеовыходов платы: {outputs}; одновременный режим не подтверждён')
    unknown('Датчики платы', 'температура/напряжение/обороты/вскрытие' if req.board_sensors_required else None)
    unknown('Управление BIOS из Astra Linux', 'Да' if req.bios_astra_management_required else None)
    unknown('Пароль администратора BIOS из ОС', 'Да' if req.bios_admin_password_required else None)
    if req.extra_hdd_slot_required:
        if case is None:
            unknown('Дополнительный HDD: слот/крепёж/питание', 'Да')
        else:
            bays = int(case.get('bay_25',0)) + int(case.get('bay_35',0))
            unknown('Дополнительный HDD: слот/крепёж/питание', 'Да', f'Подходящих отсеков корпуса: {bays}; крепёж и питание отдельно не подтверждены')

    hdmi_have = board['video'].get('HDMI',0) + (1 if req.need_gpu else 0)
    dp_have = board['video'].get('DisplayPort',0) + (1 if req.need_gpu else 0)
    vga_have = board['video'].get('VGA',0)
    add('HDMI выходов', hdmi_have, req.system_hdmi_min, hdmi_have >= (req.system_hdmi_min or 0))
    add('DisplayPort выходов', dp_have, req.system_dp_min, dp_have >= (req.system_dp_min or 0))
    add('VGA выходов', vga_have, getattr(req,'system_vga_min',None), vga_have >= (getattr(req,'system_vga_min',0) or 0))
    if getattr(req,'integrated_psu_required',False):
        add('Встроенный блок питания', 'Да', 'Да', True)
    if getattr(req,'system_audio_out_required',False):
        if board.get('audio_out') is None: unknown('Встроенный аудиовыход', 'Да')
        else: add('Встроенный аудиовыход','Да' if board.get('audio_out') else 'Нет','Да',bool(board.get('audio_out')))
    if getattr(req,'system_mic_in_required',False):
        if board.get('mic_in') is None: unknown('Встроенный микрофонный вход', 'Да')
        else: add('Встроенный микрофонный вход','Да' if board.get('mic_in') else 'Нет','Да',bool(board.get('mic_in')))

    if req.product_type.startswith('aio'):
        aio = _aio_spec_for_req(req) or {}
        add('Диагональ моноблока, дюйм', aio.get('diagonal_in','?'), req.monitor_inches, isinstance(aio.get('diagonal_in'), (int,float)) and aio.get('diagonal_in',0) >= (req.monitor_inches or 0))
        if req.monitor_resolution:
            have_res = aio.get('resolution')
            add('Разрешение моноблока', have_res or 'нет данных', ('≥ ' if _resolution_is_minimum(req) else '') + req.monitor_resolution, _resolution_passes(have_res, req.monitor_resolution, _resolution_is_minimum(req)))
        if req.monitor_refresh_hz_min is not None:
            have_hz = aio.get('refresh_hz')
            if have_hz is None:
                unknown('Частота обновления экрана, Гц', f'≥ {req.monitor_refresh_hz_min}')
            else:
                add('Частота обновления экрана, Гц', have_hz, req.monitor_refresh_hz_min, have_hz >= req.monitor_refresh_hz_min)
        unknown('Матрица дисплея', req.monitor_matrix)
        unknown('Контрастность экрана', f'≥ {req.monitor_contrast_min}:1' if getattr(req,'monitor_contrast_min',None) else None)
        if getattr(req,'monitor_view_angle_h_min',None) or getattr(req,'monitor_view_angle_v_min',None):
            unknown('Углы обзора экрана', f'≥ {getattr(req,"monitor_view_angle_h_min",0) or 0}/{getattr(req,"monitor_view_angle_v_min",0) or 0}°')
        unknown('Настенное крепление', 'Да' if req.monitor_wall_mount else None)
        unknown('Поворот экрана в портретный режим', 'Да' if req.monitor_pivot else None)
        unknown('Регулировка экрана по высоте, мм', f'≥ {req.monitor_height_adjust_mm_min}' if req.monitor_height_adjust_mm_min else None)
        unknown('Встроенный микрофон', 'Да' if req.need_builtin_mic else None)
        if req.need_cardreader:
            add('Встроенный картридер', 'Да' if aio.get('built_in_cardreader') else 'Нет', 'Да', bool(aio.get('built_in_cardreader')))
        unknown('Механическая блокировка камеры', 'Да' if req.webcam_privacy_shutter else None)
        unknown('Разрешение веб-камеры, Мп', f'≥ {req.webcam_mp_min:g}' if req.webcam_mp_min else None)
        if req.need_audio_jacks:
            # Motherboard has three audio jacks, but their accessibility in a specific AIO barebone is not stated.
            unknown('Разъёмы наушники/микрофон в корпусе', 'Да', f'Плата: {board.get("audio_external", "аудио разъёмы есть")}; доступность на баребоне не описана')
        if getattr(req,'external_psu_required',False):
            is_external = not bool(aio.get('integrated_psu', True))
            add('Тип блока питания моноблока', 'Внешний' if is_external else 'Встроенный', 'Внешний', is_external)

    return checks


def _peripheral_records(peripheral_catalogs, kind):
    out=[]
    for rec in list((peripheral_catalogs or {}).get(kind) or []):
        if not isinstance(rec, dict):
            continue
        data=dict(rec.get('data') or rec)
        name=str(rec.get('name') or data.get('name') or '').strip()
        if not name:
            continue
        data['name']=name
        out.append(data)
    return out


def _iface_tokens(value):
    low=str(value or '').casefold().replace('display port','displayport').replace('display-port','displayport')
    out=set()
    for token, aliases in {
        'HDMI':['hdmi'], 'DisplayPort':['displayport','dp'], 'VGA':['vga','d-sub','dsub'],
        'DVI':['dvi'], 'USB-C':['usb-c','type-c'],
    }.items():
        if any(re.search(r'(?<![a-zа-я0-9])'+re.escape(a)+r'(?![a-zа-я0-9])', low) for a in aliases):
            out.add(token)
    return out


def _resolution_is_minimum(req):
    """Backward compatibility: older project files only preserved the raw TZ text."""
    if bool(getattr(req, 'monitor_resolution_is_min', False)):
        return True
    for line in str(getattr(req, 'raw_text', '') or '').splitlines():
        if re.search(r'разрешени[ея]\s+экрана', line, re.I):
            fields = [v.strip() for v in line.split('|')]
            v = fields[1] if len(fields) > 1 else line
            if re.search(r'≥|>=|не\s+менее|от\s+\d', v, re.I):
                return True
    return False


def _resolution_passes(actual, required, minimum=False):
    """Validate resolution dimensions, not equal string spelling."""
    def dims(v):
        m = re.search(r'(\d{3,5})\s*[xх×]\s*(\d{3,5})', str(v or ''), re.I)
        return (int(m.group(1)), int(m.group(2))) if m else None
    have, need = dims(actual), dims(required)
    if have is None or need is None:
        return False
    return (have[0] >= need[0] and have[1] >= need[1]) if minimum else have == need


def _energy_class_rank(value):
    s=str(value or '').upper().replace(' ','')
    # Higher is better. Covers common procurement labels used for monitors.
    order={'A+++':7,'A++':6,'A+':5,'A':4,'B':3,'C':2,'D':1,'E':0,'F':-1,'G':-2}
    for key in ('A+++','A++','A+','A','B','C','D','E','F','G'):
        if key in s:
            return order[key]
    return None


def _peripheral_checks(req, kind, data):
    """Return requirement checks for one saved monitor/keyboard/mouse.

    Unknown fields are deliberately NOT treated as passing: auto-selection only uses a
    saved item when every relevant parsed TZ requirement is confirmed by its database row.
    """
    checks=[]
    def add(label, need, have, ok=None, known=True):
        if need is None:
            return
        status='НЕТ ДАННЫХ' if not known else ('OK' if ok else 'НЕ ПРОХОДИТ')
        checks.append({'Проверка':label,'Требование':str(need),'Факт QX':str(have if known else 'не заполнено'),'Статус':status})

    if kind=='monitor':
        if req.monitor_inches is not None:
            have=data.get('inches'); add('Диагональ монитора, ″',f'≥ {req.monitor_inches}',have,have is not None and float(have)>=float(req.monitor_inches),have not in (None,''))
        if req.monitor_resolution:
            have=str(data.get('resolution') or ''); add('Разрешение монитора',('≥ ' if _resolution_is_minimum(req) else '')+req.monitor_resolution,have,_resolution_passes(have, req.monitor_resolution, _resolution_is_minimum(req)),bool(have))
        if getattr(req,'monitor_aspect_ratio',None):
            have=str(data.get('aspect_ratio') or ''); add('Формат изображения',req.monitor_aspect_ratio,have,re.sub(r'\s+','',have)==re.sub(r'\s+','',str(req.monitor_aspect_ratio)),bool(have))
        if req.monitor_matrix:
            have=str(data.get('matrix') or ''); add('Матрица монитора',req.monitor_matrix,have,str(req.monitor_matrix).casefold() in have.casefold(),bool(have))
        if req.monitor_refresh_hz_min is not None:
            have=data.get('refresh_hz'); add('Частота монитора, Гц',f'≥ {req.monitor_refresh_hz_min}',have,have not in (None,'') and float(have)>=float(req.monitor_refresh_hz_min),have not in (None,''))
        if req.monitor_response_ms_max is not None:
            have=data.get('response_ms'); _inclusive=bool(getattr(req,'monitor_response_ms_max_inclusive',False)); _op='≤' if _inclusive else '<'
            _ok=have not in (None,'') and (float(have)<=float(req.monitor_response_ms_max) if _inclusive else float(have)<float(req.monitor_response_ms_max))
            add('Время отклика, мс',f'{_op} {req.monitor_response_ms_max}',have,_ok,have not in (None,''))
        if req.monitor_brightness_min is not None:
            have=data.get('brightness'); add('Яркость, кд/м²',f'≥ {req.monitor_brightness_min}',have,have not in (None,'') and float(have)>=float(req.monitor_brightness_min),have not in (None,''))
        if req.monitor_brightness_max is not None:
            have=data.get('brightness'); add('Максимальная яркость по ТЗ',f'< {req.monitor_brightness_max}',have,have not in (None,'') and float(have)<float(req.monitor_brightness_max),have not in (None,''))
        if req.monitor_contrast_min is not None:
            have=data.get('contrast'); add('Контрастность',f'≥ {req.monitor_contrast_min}:1',have,have not in (None,'') and int(have)>=int(req.monitor_contrast_min),have not in (None,''))
        if getattr(req,'monitor_dynamic_contrast_max',None) is not None:
            have=data.get('dynamic_contrast'); add('Динамическая контрастность',f'< {req.monitor_dynamic_contrast_max}:1',have,have not in (None,'') and int(have)<int(req.monitor_dynamic_contrast_max),have not in (None,''))
        if getattr(req,'monitor_energy_class',None):
            have=str(data.get('energy_class') or '')
            need_rank=_energy_class_rank(req.monitor_energy_class); have_rank=_energy_class_rank(have)
            add('Класс энергоэффективности',req.monitor_energy_class,have,need_rank is not None and have_rank is not None and have_rank>=need_rank,bool(have))
        if req.monitor_view_angle_h_min is not None:
            have=data.get('view_angle_h'); add('Угол обзора H',f'≥ {req.monitor_view_angle_h_min}°',have,have not in (None,'') and int(have)>=int(req.monitor_view_angle_h_min),have not in (None,''))
        if req.monitor_view_angle_v_min is not None:
            have=data.get('view_angle_v'); add('Угол обзора V',f'≥ {req.monitor_view_angle_v_min}°',have,have not in (None,'') and int(have)>=int(req.monitor_view_angle_v_min),have not in (None,''))
        for attr,key,label in [
            ('monitor_speakers','speakers','Встроенные динамики'),('monitor_external_psu','external_psu','Внешний БП'),
            ('monitor_wall_mount','wall_mount','Крепление на стену'),('monitor_pivot','pivot','Портретный поворот'),
            ('monitor_tilt','tilt','Регулировка наклона'),('monitor_webcam','webcam','Веб-камера'),
            ('monitor_touch','touch','Сенсорный экран'),('monitor_usb_hub','usb_hub','USB-концентратор'),
            ('monitor_curved','curved','Изогнутый экран'),('monitor_swivel','swivel','Поворот по горизонтали'),('monitor_cable_included','cable_included','Кабель в комплекте')]:
            need=getattr(req,attr,None)
            if need is not None:
                known=key in data
                have=bool(data.get(key)) if known else None
                add(label,'Да' if need else 'Нет','Да' if have else 'Нет',known and have is bool(need),known)
        if req.monitor_vesa:
            have=str(data.get('vesa') or ''); _vesa_norm=lambda x: re.sub(r'\s+','',re.sub(r'^vesa\s*','',str(x or ''),flags=re.I)).casefold(); add('VESA',req.monitor_vesa,have,_vesa_norm(have)==_vesa_norm(req.monitor_vesa),bool(have))
        if req.monitor_interfaces:
            need=_iface_tokens(req.monitor_interfaces); have=_iface_tokens(data.get('interfaces'))
            add('Интерфейсы монитора',', '.join(sorted(need)),', '.join(sorted(have)),need.issubset(have),bool(data.get('interfaces')))
        if req.monitor_hdmi_ports_min is not None:
            have=int(data.get('hdmi_ports') or 0); add('HDMI, шт.',f'≥ {req.monitor_hdmi_ports_min}',have,have>=int(req.monitor_hdmi_ports_min),True)
        if req.monitor_dp_ports_min is not None:
            have=int(data.get('dp_ports') or 0); add('DisplayPort, шт.',f'≥ {req.monitor_dp_ports_min}',have,have>=int(req.monitor_dp_ports_min),True)
        if req.monitor_color_depth_bits is not None:
            have=data.get('color_depth_bits'); add('Глубина цвета, бит',req.monitor_color_depth_bits,have,have not in (None,'') and int(have)==int(req.monitor_color_depth_bits),have not in (None,''))
        if req.monitor_cable_type:
            have=str(data.get('cable_type') or '')
            need_cables=_iface_tokens(req.monitor_cable_type); have_cables=_iface_tokens(have)
            cable_ok=(need_cables.issubset(have_cables) if need_cables else str(req.monitor_cable_type).casefold() in have.casefold())
            add('Кабель в комплекте',req.monitor_cable_type,have,cable_ok,bool(have))
        if getattr(req,'monitor_power_w_max',None) is not None:
            have=data.get('power_w'); add('Потребляемая мощность, Вт',f'≤ {req.monitor_power_w_max:g}',have,have not in (None,'') and float(have)<=float(req.monitor_power_w_max),have not in (None,''))
        if getattr(req,'monitor_audio_in_required',False):
            known='audio_in' in data; have=bool(data.get('audio_in')) if known else None; add('Mini-Jack вход','Да','Да' if have else 'Нет',known and have,known)
        if getattr(req,'monitor_audio_out_required',False):
            known='audio_out' in data; have=bool(data.get('audio_out')) if known else None; add('Mini-Jack выход','Да','Да' if have else 'Нет',known and have,known)

    elif kind=='keyboard':
        if req.keyboard_wired:
            known='wired' in data; have=bool(data.get('wired')) if known else None; add('Тип подключения клавиатуры','Проводная','Проводная' if have else 'Не проводная',known and have,known)
        if req.keyboard_wireless:
            known='wireless' in data; have=bool(data.get('wireless')) if known else None; add('Тип подключения клавиатуры','Беспроводная','Беспроводная' if have else 'Не беспроводная',known and have,known)
        if req.keyboard_usb:
            known='usb' in data; have=bool(data.get('usb')) if known else None; add('USB клавиатуры','Да','Да' if have else 'Нет',known and have,known)
        if req.keyboard_layout:
            have=str(data.get('layout') or '')
            need_low=str(req.keyboard_layout).casefold(); have_low=have.casefold()
            if 'qwerty' in need_low and 'йцукен' in need_low:
                ok=('йцукен' in have_low and ('qwerty' in have_low or bool(have_low)))
            else:
                ok=(need_low==have_low)
            add('Раскладка',req.keyboard_layout,have,ok,bool(have))
        if req.keyboard_russification:
            have=str(data.get('russification') or ''); add('Русификация',req.keyboard_russification,have,str(req.keyboard_russification).casefold() in have.casefold(),bool(have))
        if req.keyboard_keys_min is not None:
            have=data.get('keys'); add('Клавиш клавиатуры',f'≥ {req.keyboard_keys_min}',have,have not in (None,'') and int(have)>=int(req.keyboard_keys_min),have not in (None,''))
        if req.keyboard_numeric_keypad:
            known='numeric_keypad' in data; have=bool(data.get('numeric_keypad')) if known else None; add('Цифровой блок','Да','Да' if have else 'Нет',known and have,known)
        if req.keyboard_fullsize:
            known='fullsize' in data; have=bool(data.get('fullsize')) if known else None; add('Полноразмерная клавиатура','Да','Да' if have else 'Нет',known and have,known)
        if req.keyboard_cable_min_m is not None:
            have=data.get('cable_m'); add('Длина кабеля клавиатуры, м',f'≥ {req.keyboard_cable_min_m}',have,have not in (None,'') and float(have)>=float(req.keyboard_cable_min_m),have not in (None,''))
        if req.keyboard_cable_max_m is not None:
            have=data.get('cable_m'); add('Макс. длина кабеля клавиатуры, м',f'< {req.keyboard_cable_max_m}',have,have not in (None,'') and float(have)<float(req.keyboard_cable_max_m),have not in (None,''))
        for attr,key,label in [
            ('keyboard_flexible','flexible','Гибкая клавиатура'),('keyboard_has_usb_port','has_usb_port','USB-порт на клавиатуре'),
            ('keyboard_multifunction','multifunction','Мультифункциональные клавиши'),('keyboard_touchpad','touchpad','Тачпад'),
            ('keyboard_palmrest','palmrest','Подставка для рук'),('keyboard_scroll_wheel','scroll_wheel','Колесо прокрутки'),
            ('keyboard_water_protection','water_protection','Защита от воды'),('keyboard_detachable_cable','detachable_cable','Съёмный кабель'),
            ('keyboard_volume_control','volume_control','Регулировка громкости'),('keyboard_backlight','backlight','Подсветка клавиш')]:
            need=getattr(req,attr,None)
            if need is not None:
                known=key in data; have=bool(data.get(key)) if known else None
                add(label,'Да' if need else 'Нет','Да' if have else 'Нет',known and have is bool(need),known)

    elif kind=='mouse':
        if req.mouse_wired:
            known='wired' in data; have=bool(data.get('wired')) if known else None; add('Тип подключения мыши','Проводная','Проводная' if have else 'Не проводная',known and have,known)
        if req.mouse_wireless:
            known='wireless' in data; have=bool(data.get('wireless')) if known else None; add('Тип подключения мыши','Беспроводная','Беспроводная' if have else 'Не беспроводная',known and have,known)
        if req.mouse_usb:
            known='usb' in data; have=bool(data.get('usb')) if known else None; add('USB мыши','Да','Да' if have else 'Нет',known and have,known)
        if req.mouse_optical:
            known='optical' in data; have=bool(data.get('optical')) if known else None; add('Оптический сенсор','Да','Да' if have else 'Нет',known and have,known)
        if req.mouse_dpi_min is not None:
            have=data.get('dpi'); add('Разрешение мыши, DPI',f'≥ {req.mouse_dpi_min}',have,have not in (None,'') and int(have)>=int(req.mouse_dpi_min),have not in (None,''))
        if req.mouse_cable_min_m is not None:
            have=data.get('cable_m'); add('Длина кабеля мыши, м',f'≥ {req.mouse_cable_min_m}',have,have not in (None,'') and float(have)>=float(req.mouse_cable_min_m),have not in (None,''))
        if req.mouse_cable_max_m is not None:
            have=data.get('cable_m'); add('Макс. длина кабеля мыши, м',f'< {req.mouse_cable_max_m}',have,have not in (None,'') and float(have)<float(req.mouse_cable_max_m),have not in (None,''))
        if req.mouse_buttons_min is not None:
            have=data.get('buttons'); add('Кнопок мыши',f'≥ {req.mouse_buttons_min}',have,have not in (None,'') and int(have)>=int(req.mouse_buttons_min),have not in (None,''))
        for attr,key,label in [
            ('mouse_programmable_buttons','programmable_buttons','Программируемые кнопки'),
            ('mouse_side_buttons','side_buttons','Боковые кнопки'),('mouse_silent_click','silent_click','Тихий клик'),
            ('mouse_detachable_cable','detachable_cable','Съёмный кабель')]:
            need=getattr(req,attr,None)
            if need is not None:
                known=key in data; have=bool(data.get(key)) if known else None
                add(label,'Да' if need else 'Нет','Да' if have else 'Нет',known and have is bool(need),known)
    return checks


def _peripheral_source_mode(req, kind):
    if kind not in ('keyboard','mouse'):
        return 'catalog'
    mode = str(getattr(req, f'{kind}_source_mode', 'qx') or 'qx').strip().lower()
    return mode if mode in ('qx','catalog','manual') else 'qx'


def _qx_individual_peripheral(kind, qx_prices):
    key = 'keyboard' if kind == 'keyboard' else 'mouse'
    category = 'Клавиатура' if kind == 'keyboard' else 'Мышь'
    fallback_name = 'Клавиатура QX' if kind == 'keyboard' else 'Мышь QX'
    item = dict((qx_prices or {}).get(key) or {})
    name = str(item.get('name') or fallback_name)
    price = float(item.get('price') or 0)
    note = 'Стандарт QX закреплён по умолчанию и не заменяется позициями из пользовательской базы автоматически.'
    if price <= 0:
        note += ' Отдельная цена этой позиции пока не задана; её можно указать во вкладке «Цены / прайсы» или вручную в расчёте. Для пары клавиатура+мышь используется отдельная стандартная цена комплекта QX.'
    return Component(category, name, price=price, source='QX', note=note, constraints={'kind':kind,'qx_default':True}).to_dict()


def _select_peripheral(req, kind, peripheral_catalogs):
    records=_peripheral_records(peripheral_catalogs,kind)
    selected_name=str(getattr(req,f'{kind}_catalog_item',None) or '').strip()
    if selected_name:
        item=next((x for x in records if str(x.get('name') or '').casefold()==selected_name.casefold()),None)
        return item, True
    compliant=[]
    for item in records:
        checks=_peripheral_checks(req,kind,item)
        if not [x for x in checks if x['Статус']!='OK']:
            compliant.append(item)
    if not compliant:
        return None, False
    compliant.sort(key=lambda x:(float(x.get('price') or 0),str(x.get('name') or '').casefold()))
    return compliant[0], False


def _build_peripheral(req, qx_prices, peripheral_catalogs=None):
    rows=[]; warnings=[]; checks=[]
    kind=req.product_type
    mode=_peripheral_source_mode(req,kind)

    # Keyboard/mouse are QX-first. Saved bases are opt-in and must never silently
    # replace the standard QX item just because a matching record exists.
    if kind in ('keyboard','mouse') and mode=='qx':
        row=_qx_individual_peripheral(kind,qx_prices)
        rows.append(row)
        # We deliberately do not claim detailed compliance for the generic built-in QX
        # item because its technical spec is not encoded here. Keep QX selected and warn.
        specific = _peripheral_checks(req,kind,{})
        if specific:
            warnings.append(('Клавиатура QX' if kind=='keyboard' else 'Мышь QX') +
                            ' оставлена как стандарт по умолчанию. Подробные характеристики QX не зашиты в справочник, поэтому требования ТЗ нужно подтвердить; программа не заменяет QX без твоего выбора.')
        return rows,None,warnings,checks

    if kind in ('keyboard','mouse') and mode=='manual':
        category='Клавиатура' if kind=='keyboard' else 'Мышь'
        rows.append(Component(category, category+' — вручную', price=0.0, source='Вручную',
                              note='Ручной режим выбран пользователем; название и цену укажи в таблице расчёта.',
                              constraints={'kind':kind}).to_dict())
        return rows,None,warnings,checks

    item, forced=_select_peripheral(req,kind,peripheral_catalogs)
    if item:
        checks=_peripheral_checks(req,kind,item)
        failed=[x for x in checks if x['Статус']!='OK']
        category={'monitor':'Монитор','keyboard':'Клавиатура','mouse':'Мышь'}[kind]
        registry_number=str(item.get('registry_number') or '').strip()
        note=('Выбрано автоматически из сохранённой базы как минимальная по цене подтверждённо подходящая позиция.' if not forced else 'Выбрано вручную из сохранённой базы.')
        if kind in ('keyboard','mouse'):
            note='Пользователь явно переключил источник с QX на пользовательскую базу. ' + note
        if failed:
            note += ' ВНИМАНИЕ: есть несоответствия/нехватка данных.'
            warnings.append(f'Сохранённая позиция «{item.get("name")}» не закрывает все требования ТЗ: ' + '; '.join(x['Проверка'] for x in failed))
        rows.append(Component(category,str(item.get('name')),price=float(item.get('price') or 0),price_input=str(item.get('price_input') or ''),source='Пользовательская база',note=note,registry=bool(item.get('registry') or registry_number),constraints={'kind':kind,'registry_number':registry_number,**item}).to_dict())
        reg={'product_name':str(item.get('name')),'registry_number':registry_number,'execution_code':str(item.get('registry_code') or ''),'platform':'','product_type':kind}
        if not registry_number:
            warnings.append(f'У выбранной позиции «{item.get("name")}» не заполнен реестровый номер.')
        return rows,reg,warnings,checks

    records=_peripheral_records(peripheral_catalogs,kind)
    if records:
        warnings.append(f'В базе { {"monitor":"мониторов","keyboard":"клавиатур","mouse":"мышей"}[kind] } нет позиции, которая подтверждённо закрывает все распознанные требования ТЗ. Оставлена ручная строка; добавь/дополни подходящую модель в соответствующей вкладке.')
    if kind=='monitor':
        size=req.monitor_inches or 23.8; res=req.monitor_resolution or '1920x1080'
        rows.append(Component('Монитор',f'Монитор от {size}" {res}',note='Автоподбор из базы не дал подтверждённого соответствия; модель и цену проверь вручную.',constraints={'kind':'monitor','min_inches':size,'resolution':res,'matrix':req.monitor_matrix or '','min_hz':req.monitor_refresh_hz_min or 0}).to_dict())
    elif kind=='keyboard':
        rows.append(Component('Клавиатура','Клавиатура по ТЗ',note='В режиме базы подходящая сохранённая модель не найдена; модель и цену проверь вручную.',constraints={'kind':'keyboard'}).to_dict())
    elif kind=='mouse':
        rows.append(Component('Мышь','Мышь по ТЗ',note='В режиме базы подходящая сохранённая модель не найдена; модель и цену проверь вручную.',constraints={'kind':'mouse'}).to_dict())
    return rows,None,warnings,checks

def build_plan(req, qx_prices, settings, equipment_profile=None, peripheral_catalogs=None):
    # Saved projects may contain a price catalog from before new QX parts existed.
    # Complete it in memory for all selection paths (Modern API and classic UI).
    qx_prices = normalize_prices(qx_prices)
    if req.product_type in ('monitor','keyboard','mouse'):
        return _build_peripheral(req, qx_prices, peripheral_catalogs=peripheral_catalogs)

    custom_equipment = bool(equipment_profile)
    profile_label = _profile_label(equipment_profile)
    platform, warnings = resolve_platform(req, equipment_profile=equipment_profile)
    if custom_equipment:
        board = _profile_board(equipment_profile, platform) or _empty_board(platform)
        profile_components = _profile_selected_components(equipment_profile, req, platform)
    else:
        board = QX_SPECS[platform]
        profile_components = []
    rows = []

    def qx(key, category, note='', registry=False):
        item = qx_prices[key]
        rows.append(Component(category=category, name=item['name'], qty=1, price=float(item['price']), source='QX', note=note, registry=registry))

    def profile_component_row(item):
        note_bits = []
        if item.get('registry_number'):
            note_bits.append(f"Реестровый номер компонента: {item.get('registry_number')}")
        if item.get('price_conversion'):
            note_bits.append(str(item.get('price_conversion')))
        if item.get('note'):
            note_bits.append(str(item.get('note')))
        return Component(
            category=str(item.get('category') or 'Доп. компонент'),
            name=str(item.get('name') or 'Компонент — НЕ ЗАПОЛНЕНО'),
            qty=float(item.get('qty') or 1),
            price=float(item.get('price') or 0),
            source=profile_label,
            note='; '.join(note_bits),
            registry=bool(item.get('registry')),
            constraints={
                'kind':'profile_component', 'role':str(item.get('role') or ''),
                'profile':profile_label, 'registry_number':str(item.get('registry_number') or ''),
                'supplier':str(item.get('supplier') or ''), 'supplier_sku':str(item.get('supplier_sku') or ''),
                'condition':str(item.get('condition') or 'always'),
                'usb2_a':int(item.get('usb2_a') or 0),
                'usb3_gen1_type_a':int(item.get('usb3_gen1_type_a') or 0),
                'usb3_gen1_type_c':int(item.get('usb3_gen1_type_c') or 0),
                'usb3_gen2_type_a':int(item.get('usb3_gen2_type_a') or 0),
                'usb3_gen2_type_c':int(item.get('usb3_gen2_type_c') or 0),
                'location':str(item.get('location') or 'unknown'),
            }
        )

    # QX has a fixed registry-composition algorithm. A saved profile is different:
    # its own list of components and conditions is authoritative, so we never inject
    # QX hub/Wi-Fi/cardreader rows into another manufacturer's calculation.
    if custom_equipment:
        registry_device = None
        selected_wifi = any('wifi' in str(x.get('role') or '').lower() or 'wi-fi' in str(x.get('category') or '').lower() or 'wifi' in str(x.get('category') or '').lower() for x in profile_components)
        selected_cardreader = any('cardreader' in str(x.get('role') or '').lower() or 'картрид' in str(x.get('category') or '').lower() for x in profile_components)
        if req.forbid_wireless:
            before=len(profile_components)
            profile_components=[x for x in profile_components if not ('wifi' in str(x.get('role') or '').lower() or 'wi-fi' in str(x.get('category') or '').lower() or 'wifi' in str(x.get('category') or '').lower() or 'bluetooth' in str(x.get('category') or '').lower())]
            if len(profile_components) != before:
                warnings.append(f'ТЗ запрещает беспроводную связь: Wi‑Fi/Bluetooth-компоненты из базы «{profile_label}» исключены автоматически.')
            selected_wifi=False
        if (req.need_wifi or req.need_bluetooth) and not selected_wifi:
            warnings.append(f'ТЗ требует Wi‑Fi/Bluetooth, но в базе «{profile_label}» нет выбранного по условию беспроводного компонента. Добавь его в профиль с условием «wifi» или «always».')
        if req.need_cardreader and not selected_cardreader and not (req.product_type.startswith('aio') and (_aio_spec_for_req(req) or {}).get('built_in_cardreader')):
            warnings.append(f'ТЗ требует картридер, но в базе «{profile_label}» нет выбранного по условию картридера. Добавь его в профиль.')
        if req.product_type.startswith('aio'):
            case_key=None
            case_reasons=[]; case_ok=True
        else:
            case_key, case_reasons, case_ok = _choose_case_for_profile(req, board, extra_components=profile_components)
            if not case_ok and case_reasons:
                warnings.append(f'С выбранной платой из базы «{profile_label}» корпус не закрывает все найденные требования: ' + '; '.join(case_reasons))
    else:
        # Choose QX case and the registry module as a single technical decision.
        if req.product_type.startswith('aio'):
            case_key = None
            aio_spec = _aio_spec_for_req(req) or {}
            if req.forbid_wireless:
                registry_device = 'cardreader'
                warnings.append('ТЗ прямо запрещает беспроводную связь: реестровым выбран картридер, Wi‑Fi в сборку не добавляется.')
            elif req.need_wifi:
                # Current QX AIO platforms already contain a non-registry cardreader, so if Wi-Fi
                # is required the technically clean registry choice is Wi-Fi.
                registry_device = 'wifi'
            else:
                preferred = settings.get('prefer_registry_device_when_not_required', 'wifi')
                if settings.get('smart_registry_device', True) and _usb_requirements_present(req):
                    candidates = ['wifi', 'cardreader']
                    scored = []
                    for dev in candidates:
                        inv = _usb_inventory(board, None, cardreader=(dev == 'cardreader'), aio_spec=aio_spec, req=req)
                        scored.append((_usb_deficit_score(req, inv), 0 if dev == preferred else 1, dev))
                    registry_device = min(scored)[2]
                    if registry_device == 'cardreader' and registry_device != preferred:
                        warnings.append('Для моноблока реестровый картридер выбран дополнительно, потому что его порты лучше закрывают требования ТЗ.')
                else:
                    registry_device = preferred
            if req.need_cardreader and aio_spec.get('built_in_cardreader'):
                warnings.append('Картридер уже встроен в выбранную моноблочную платформу, входит в её стоимость и не является реестровым модулем.')
        else:
            case_key, registry_device, case_reasons, case_ok = _choose_case_and_registry_device(req, platform, settings)
            if not case_ok and case_reasons:
                warnings.append('По справочнику QX ни один корпус не закрывает все найденные требования автоматически: ' + '; '.join(case_reasons))
            if not (req.need_wifi or req.need_cardreader) and registry_device == 'cardreader' and settings.get('smart_registry_device', True):
                warnings.append('Картридер выбран реестровым не из-за прямого требования, а потому что его USB-порты помогают закрыть требования ТЗ по передней панели/Type-C.')
            if req.forbid_wireless:
                warnings.append('ТЗ прямо запрещает беспроводную связь: Wi‑Fi исключён, для реестровой комплектации используется картридер.')

        if req.need_wifi and req.need_cardreader:
            if req.product_type.startswith('aio') and (_aio_spec_for_req(req) or {}).get('built_in_cardreader'):
                warnings.append('ТЗ требует Wi‑Fi и картридер: Wi‑Fi используется как реестровый модуль, а картридер уже встроен в выбранную платформу и отдельно не закупается.')
            else:
                warnings.append('ТЗ требует и Wi‑Fi, и картридер: один модуль будет реестровым, второй — обычным китайским.')

    cpu_model = _cpu_model(req, platform, board)
    cpu_note_bits = []
    if req.cpu_cores_min: cpu_note_bits.append(f'≥{req.cpu_cores_min} ядер')
    if req.cpu_threads_min: cpu_note_bits.append(f'≥{req.cpu_threads_min} потоков')
    if req.cpu_freq_ghz_min: cpu_note_bits.append(f'база ≥{req.cpu_freq_ghz_min} ГГц')
    if req.cpu_freq_max_ghz_min: cpu_note_bits.append(f'макс. ≥{req.cpu_freq_max_ghz_min} ГГц')
    if req.cpu_l3_mb_min: cpu_note_bits.append(f'L3 ≥{req.cpu_l3_mb_min} МБ')
    if req.need_integrated_graphics: cpu_note_bits.append('со встроенной графикой')
    if req.cpu_passmark_min: cpu_note_bits.append(f'PassMark ≥{req.cpu_passmark_min} (справочно, перепроверить на дату заявки)')
    if req.cpu_x86_64_required: cpu_note_bits.append('x86-64')
    cpu_alternatives = _cpu_alternatives(req, platform, board)
    cpu_note = ('Автоподбор по минимально достаточным характеристикам: ' + ', '.join(cpu_note_bits)) if cpu_note_bits else 'Автоподбор по минимально достаточным характеристикам.'
    if cpu_alternatives:
        cpu_note += ' Подходящие процессоры отсортированы по минимальному техническому запасу; цену программа не угадывает — выбери реально выгодную модель.'
    else:
        cpu_note += ' В текущей базе нет подтверждённого совпадения — выбери/впиши процессор вручную и проверь его характеристики.'
        warnings.append('По найденным ограничениям процессора нет подтверждённого совпадения в локальной базе. Программа НЕ подставляет заведомо неподходящий CPU; используй ручной выбор или обнови базу процессоров.')
    rows.append(Component('Процессор', f'{cpu_model} OEM' if not cpu_model.endswith('вручную') else cpu_model, note=cpu_note, alternatives=cpu_alternatives, constraints={'kind':'cpu','platform':platform,'requires_igpu':bool(req.need_integrated_graphics)}))
    if req.need_integrated_graphics:
        rows.append(Component(
            'Графика', f'Интегрированная графика в {cpu_model}', qty=1, price=0.0, source='В составе процессора', query='',
            note='ТЗ требует интегрированный/встроенный видеоадаптер. Выбран процессор со встроенной графикой; отдельная видеокарта не добавляется.',
            constraints={'kind':'integrated_graphics'}
        ))

    if custom_equipment:
        board_note = f'Материнская плата из сохранённой базы «{profile_label}». Характеристики для проверки ТЗ берутся только из этой записи.'
        if board.get('registry_number'):
            board_note += f' Реестровый номер компонента: {board.get("registry_number")}.'
        if board.get('price_conversion'):
            board_note += f' Цена: {board.get("price_conversion")}.'
        rows.append(Component(
            'Материнская плата', board.get('name') or 'Материнская плата — НЕ ЗАПОЛНЕНО',
            price=float(board.get('price') or 0), source=profile_label,
            note=board_note, registry=bool(board.get('registry')),
            constraints={'kind':'motherboard','custom_profile':True,'profile':profile_label, **board}
        ))
        if not str(board.get('name') or '').strip() or 'НЕ ЗАПОЛНЕНО' in str(board.get('name')):
            warnings.append(f'В базе «{profile_label}» нет материнской платы для {platform.upper()}. Заполни её во вкладке «База оборудования».')
    else:
        qx('motherboard_intel' if platform == 'intel' else 'motherboard_amd', 'Материнская плата', registry=True)
        rows[-1].constraints = {'kind':'motherboard','custom_profile':False, **dict(board)}
        if platform == 'amd':
            qx('m2_key_e_adapter', 'Переходник M.2 Key E', note='Штатный переходник QX для AMD: плата A520 не имеет собственного M.2 Key E. Переходник добавляется всегда, даёт 1 подключение Key E для Wi‑Fi и по умолчанию имеет цену 0 ₽.')
            rows[-1].constraints = {'kind':'m2_key_e_adapter','provides_m2_key_e':1,'qx_default':True}

    ram_gb = _round_capacity(req.ram_gb_min, [8,16,32,64,128])
    ram_type = str(board.get('ram_type') or req.ram_type or 'ОЗУ')
    ram_mhz = max(req.ram_mhz_min or 0, 4800 if ram_type=='DDR5' else 3200 if ram_type=='DDR4' and req.ram_mhz_min else 0)
    if custom_equipment and ram_type == 'ОЗУ':
        warnings.append(f'В базе «{profile_label}» у выбранной материнской платы не указан тип памяти. Программа не подставляет DDR4/DDR5 от QX.')
    ram_modules = max(2 if req.ram_dual_channel_required else 1, int(getattr(req,'ram_modules_min',0) or 0), 1)
    ram_module_gb = ram_gb
    # IMPORTANT: a minimum capacity of EACH installed module does NOT imply that two
    # modules are required. Example: total RAM >= 8 GB + each installed module >= 8 GB
    # is correctly satisfied by 1x8 GB. Only an explicit dual-channel requirement forces
    # two modules. An explicit 'Количество установленных модулей' is respected separately.
    min_module = int(req.ram_module_gb_min or 0)
    if ram_modules > 1:
        min_total = max(ram_gb, ram_modules * min_module)
        ram_gb = _round_capacity(min_total, [8,16,32,64,128])
        # Keep equal modules for dual-channel operation. Round per-module capacity only
        # when the total would otherwise not divide cleanly.
        ram_module_gb = max(min_module, int(math.ceil(ram_gb / ram_modules)))
        ram_module_gb = _round_capacity(ram_module_gb, [4,8,16,32,64])
        ram_gb = ram_module_gb * ram_modules
    else:
        if min_module and ram_gb < min_module:
            ram_gb = _round_capacity(min_module, [8,16,32,64,128])
        ram_module_gb = ram_gb
    module_part = f' ({ram_modules}x{ram_module_gb} ГБ)' if ram_modules > 1 else ''
    ram_name = f'{ram_type} {ram_gb} ГБ{module_part}' + (f' {ram_mhz} МГц' if ram_mhz else '')
    ram_query = f'оперативная память {ram_name}'
    rows.append(Component('Оперативная память', ram_name, query=ram_query, note=f'ЖЁСТКАЯ совместимость: плата {board["name"]} использует {ram_type or "неуказанный тип ОЗУ"}; память другого DDR-типа запрещена.', constraints={'kind':'ram','ram_type':ram_type,'min_gb':ram_gb,'min_mhz':ram_mhz,'desktop_dimm':True,'modules':ram_modules,'module_gb':ram_module_gb}))

    # Use real market capacity steps and never select a drive below the parsed TZ minimum.
    # 480 GB is common in procurement specs and must not fall back to the registry default 256 GB.
    ssd_gb = _round_capacity(req.ssd_gb_min, [256,480,512,960,1024,1920,2048,3840,4096])
    if req.ssd_gb_min is not None and ssd_gb < req.ssd_gb_min:
        ssd_gb = int(math.ceil(req.ssd_gb_min))
    ssd_parts = [f'SSD {ssd_gb} ГБ']
    if req.ssd_interface:
        ssd_parts.append(req.ssd_interface)
    if req.ssd_m2_required and 'M.2' not in ' '.join(ssd_parts):
        ssd_parts.append('M.2')
    if getattr(req, 'ssd_25_required', False):
        ssd_parts.append('2.5"')
    ssd_name = ' '.join(ssd_parts)
    ssd_note = ('SSD обязателен для всех реестровых исполнений QX.' if not custom_equipment else f'SSD подобран по требованиям ТЗ; реестровую применимость для базы «{profile_label}» определяют сохранённые компоненты профиля.')
    if req.ssd_gb_min is None:
        ssd_note += ' В ТЗ ёмкость SSD не задана — поставлено минимальное реестровое значение 256 ГБ; можно изменить вручную.'
    if not req.ssd_interface and not req.ssd_m2_required and not getattr(req, 'ssd_25_required', False):
        ssd_note += ' ТЗ не ограничивает интерфейс/форм-фактор SSD: SATA/NVMe/M.2 не навязываются.'
    if req.ssd_m2_required and getattr(req, 'ssd_25_required', False):
        warnings.append('В ТЗ одновременно найдены требования SSD M.2 и 2,5". Проверь, требуются ли два разных накопителя: текущая строка SSD не может одновременно иметь оба форм-фактора.')
    rows.append(Component('SSD', ssd_name, note=ssd_note, constraints={'kind':'ssd','min_gb':ssd_gb,'interface':req.ssd_interface or '', 'm2_required':bool(req.ssd_m2_required), 'form_factor':'2.5' if getattr(req,'ssd_25_required',False) else 'M.2' if req.ssd_m2_required else ''}))

    if req.hdd_gb_min:
        hdd_gb = _round_capacity(req.hdd_gb_min, [500,1000,2000,4000,6000,8000])
        if hdd_gb < req.hdd_gb_min:
            hdd_gb = int(math.ceil(req.hdd_gb_min))
        hdd_label = f'HDD {int(hdd_gb/1000)} ТБ' if hdd_gb >= 1000 and hdd_gb % 1000 == 0 else f'HDD {hdd_gb} ГБ'
        rows.append(Component('HDD', hdd_label, constraints={'kind':'hdd','min_gb':hdd_gb,'capacity_gb':hdd_gb}))

    if req.need_gpu:
        vram = req.gpu_vram_gb_min or 4
        q = f'видеокарта {vram} ГБ HDMI DisplayPort'
        note = []
        if req.gpu_dp_min: note.append(f'DisplayPort на дискретной GPU ≥{req.gpu_dp_min}')
        if req.gpu_hdmi_min: note.append(f'HDMI на дискретной GPU ≥{req.gpu_hdmi_min}')
        if req.system_hdmi_min: note.append(f'общий HDMI системы ≥{req.system_hdmi_min}; фактические выходы выбранной платы учтены в проверке ниже')
        rows.append(Component('Видеокарта', f'Видеокарта от {vram} ГБ, HDMI + DisplayPort', note='; '.join(note), constraints={'kind':'gpu','min_vram_gb':vram}))

    rows.append(Component('Кулер', f'Кулер для {board["socket"]}', constraints={'kind':'cooler','socket':board['socket'],'min_tdp_w':120}))

    if req.product_type.startswith('aio'):
        aio_spec = _aio_spec_for_req(req) or {}
        if aio_spec.get('custom'):
            rows.append(Component(
                'Моноблочная платформа', aio_spec.get('name') or 'Другая моноблочная платформа', qty=1, price=float(aio_spec.get('price') or 0), source='Вручную', query='',
                note='Другая платформа: название, цену и реальные характеристики задаёт технический специалист. Программа ничего не додумывает.',
                constraints={'kind':'aio_platform','custom':True, **{k:v for k,v in aio_spec.items() if k != 'platform_usb'}, 'platform_usb':aio_spec.get('platform_usb',{})}
            ))
        else:
            qx('barebone_27_2k' if req.product_type == 'aio27' else 'barebone_24_fhd', 'Моноблочная платформа',
               note='Баребон QX включает встроенный блок питания и встроенный нерестровый картридер; отдельный БП не добавляется к себестоимости.')
            # Attach factual platform values to the row so saved projects stay self-contained.
            rows[-1].constraints = {'kind':'aio_platform','custom':False, **aio_spec}

        if aio_spec.get('integrated_psu', True):
            if getattr(req,'external_psu_required',False):
                warnings.append('ТЗ требует ВНЕШНИЙ блок питания, а выбранная моноблочная платформа использует встроенный БП. Это несоответствие; выбери другую платформу или проверь фактическую конструкцию.')
            psu_name = 'Встроенный в платформу' if aio_spec.get('custom') else 'Встроенный в баребон QX'
            rows.append(Component(
                'Блок питания', psu_name, qty=1, price=0.0, source='В составе баребона', query='',
                note='Отдельно не закупается: блок питания входит в стоимость выбранной моноблочной платформы.',
                constraints={'kind':'integrated_psu','w':aio_spec.get('psu_w')}
            ))
            if req.psu_w_min and not aio_spec.get('psu_w'):
                warnings.append(f'ТЗ содержит требование к БП ≥{req.psu_w_min} Вт. У выбранной платформы мощность встроенного БП не указана — впиши фактическое значение вручную и проверь соответствие.')
            elif req.psu_w_min and float(aio_spec.get('psu_w') or 0) < req.psu_w_min:
                warnings.append(f'Встроенный БП выбранной платформы {aio_spec.get("psu_w")} Вт не соответствует требованию ТЗ ≥{req.psu_w_min} Вт. Это предупреждение, расчёт не блокируется.')
        else:
            psu_w = req.psu_w_min or (650 if req.need_gpu else 500)
            psu_label = f'Внешний блок питания {psu_w} Вт' if getattr(req,'external_psu_required',False) else f'Блок питания {psu_w} Вт'
            rows.append(Component('Блок питания', psu_label, constraints={'kind':'psu','min_w':psu_w,'form_factor':'external' if getattr(req,'external_psu_required',False) else 'ATX'}))

        if aio_spec.get('built_in_cardreader'):
            built = aio_spec.get('built_in_cardreader_ports', {})
            rows.append(Component(
                'Картридер платформы', ('Встроенный картридер QX (не реестр)' if not aio_spec.get('custom') else 'Встроенный картридер выбранной платформы (не реестр)'),
                qty=1, price=0.0, source='В составе платформы', query='',
                note='Встроенный картридер входит в выбранную платформу и как реестровый модуль не засчитывается.',
                constraints={'kind':'built_in_cardreader','registry':False,
                             'usb3_gen1_type_a':int(built.get('usb3_gen1_type_a',0)),
                             'usb3_gen1_type_c':int(built.get('usb3_gen1_type_c',0))}
            ))
        if aio_spec.get('custom'):
            warnings.append('Используется другая моноблочная платформа. Все её фактические характеристики берутся только из введённых вручную значений; неизвестные поля будут помечены как требующие проверки. Реестровую применимость такой платформы проверь отдельно.')
    else:
        psu_w = req.psu_w_min or (650 if req.need_gpu else 500)
        rows.append(Component('Блок питания', f'Блок питания {psu_w} Вт', constraints={'kind':'psu','min_w':psu_w,'form_factor':'ATX'}))
        if case_key == 'custom':
            custom_case = _custom_case_spec(req)
            rows.append(Component(
                'Корпус', custom_case.get('name') or 'Другой корпус', qty=1,
                price=float(custom_case.get('price') or 0), source='Вручную', query='',
                note='Другой корпус: модель, цена и фактические размеры/отсеки/порты задаются вручную. Программа использует эти значения при проверке ТЗ.',
                constraints={'kind':'case','custom':True, **custom_case}
            ))
            warnings.append('Используется другой корпус системного блока. Его соответствие ТЗ проверяется только по заполненным вручную характеристикам; незаполненные факты будут отмечены как требующие проверки.')
        else:
            qx('case_protected' if case_key=='protected' else 'case_standard', 'Корпус')
            rows[-1].constraints = {'kind':'case','custom':False, **dict(CASE_SPECS[case_key])}
        if case_key == 'protected':
            qx('expansion_bar', 'Дополнительно', note='Защищённый корпус по прайсу используется только с расширительной планкой.')

    # Registry / reusable vendor components.
    if custom_equipment:
        for item in profile_components:
            role = str(item.get('role') or '').strip().lower()
            if role in ('assembly','сборка'):
                continue
            rows.append(profile_component_row(item))
    else:
        # QX registry recipe: motherboard + hub + exactly one registry Wi-Fi/cardreader.
        qx('hub_registry', 'USB-хаб', registry=True)
        if registry_device == 'wifi':
            qx('wifi_registry', 'Wi‑Fi', registry=True)
            if req.need_cardreader and not (req.product_type.startswith('aio') and (_aio_spec_for_req(req) or {}).get('built_in_cardreader')):
                rows.append(Component('Картридер', 'Картридер (не реестр)', note='Обычный модуль: Wi‑Fi уже выбран реестровым.', constraints={'kind':'cardreader'}))
        else:
            qx('cardreader_registry', 'Картридер', registry=True)
            if req.need_wifi:
                rows.append(Component('Wi‑Fi', 'Wi‑Fi/Bluetooth адаптер (не реестр)', note='Обычный модуль: картридер уже выбран реестровым.', constraints={'kind':'wifi','bluetooth':True}))

    # Optional user-installed I/O brackets. Their exact port mix is entered manually in
    # the requirement editor and therefore can safely participate in compatibility/factual values.
    for location, label in [('front','передняя панель'), ('rear','задняя панель')]:
        extra = _extra_panel_counts(req, location)
        if any(extra.values()):
            item = qx_prices.get('expansion_bar', {'name':'Дополнительная планка портов','price':0.0})
            port_bits = []
            labels = [('usb2_a','USB2 A'),('gen1_a','Gen1 A'),('gen1_c','Gen1 C'),('gen2_a','Gen2 A'),('gen2_c','Gen2 C')]
            for key, port_label in labels:
                if extra.get(key):
                    port_bits.append(f'{port_label} ×{extra[key]}')
            rows.append(Component(
                'Доп. планка портов', f"{item.get('name','Дополнительная планка портов')} — {label}", qty=1,
                price=float(item.get('price') or 0), source='QX / вручную', query='',
                note='Фактический состав портов введён вручную: ' + ', '.join(port_bits) + '. Цена/название можно изменить в таблице сборки.',
                constraints={'kind':'port_expansion','location':location, **extra}
            ))

    if _usb_requirements_present(req):
        port_case = _case_spec_for_req(req, case_key)
        inv = _usb_inventory(
            board, port_case,
            cardreader=(not custom_equipment and registry_device=='cardreader'),
            aio_spec=_aio_spec_for_req(req) if req.product_type.startswith('aio') else None,
            req=req,
            extra_components=profile_components if custom_equipment else None,
        )
        rows.append(Component(
            'Порты USB', _usb_summary(inv), qty=1, price=0.0,
            source=f'В составе {profile_label}' if custom_equipment else 'В составе QX', query='',
            note=(f'Порты посчитаны только по сохранённым характеристикам платы/компонентов базы «{profile_label}», корпуса/моноблочной платформы и вручную заданных планок. Неуказанные порты не додумываются.'
                  if custom_equipment else
                  'Порты посчитаны по материнской плате QX, корпусу/моноблочной платформе, известным картридерам и вручную заданным дополнительным планкам. В моноблоках встроенный нерестровый картридер даёт 1× Gen1 Type-A + 1× Gen1 Type-C. Обязательный USB-HUB не считается внешним портом, т.к. его внешняя портовая спецификация не подтверждена.'),
            constraints={'kind':'port_inventory', **inv}
        ))

    if (not custom_equipment) and platform == 'amd' and registry_device == 'wifi':
        warnings.append('Для AMD A520 планка/адаптер реализации Wi‑Fi входит в платформу по исходному справочнику.')

    if req.product_type.startswith('aws'):
        inches = 27 if req.product_type == 'aws27' else 23.8
        res = req.monitor_resolution or ('2560x1440' if inches >= 27 else '1920x1080')
        # Reuse the standalone monitor database for AWS bundles. This keeps one source
        # of truth for model, price and registry number instead of duplicating monitors.
        mitem, _ = _select_peripheral(req, 'monitor', peripheral_catalogs)
        if mitem:
            mchecks = _peripheral_checks(req, 'monitor', mitem)
            bad = [x for x in mchecks if x['Статус'] != 'OK']
            rows.append(Component('Монитор', str(mitem.get('name')), price=float(mitem.get('price') or 0),
                                  price_input=str(mitem.get('price_input') or ''), source='База мониторов',
                                  note='Монитор автоматически взят из общей базы мониторов.' + (' Есть несоответствия — проверь.' if bad else ''),
                                  registry=bool(mitem.get('registry') or mitem.get('registry_number')),
                                  constraints={'kind':'monitor','registry_number':str(mitem.get('registry_number') or ''),**mitem}))
            if bad:
                warnings.append(f'Монитор «{mitem.get("name")}» в АРМ не закрывает часть требований: ' + '; '.join(x['Проверка'] for x in bad))
        else:
            rows.append(Component('Монитор', f'Монитор {inches}" {res}', constraints={'kind':'monitor','min_inches':inches,'resolution':res,'matrix':'IPS'}))

    def _append_saved_peripheral(kind):
        item, _forced = _select_peripheral(req, kind, peripheral_catalogs)
        if not item:
            return False
        pchecks = _peripheral_checks(req, kind, item)
        bad = [x for x in pchecks if x['Статус'] != 'OK']
        category = 'Клавиатура' if kind == 'keyboard' else 'Мышь'
        rows.append(Component(category, str(item.get('name')), price=float(item.get('price') or 0),
                              price_input=str(item.get('price_input') or ''), source=f'База {"клавиатур" if kind=="keyboard" else "мышей"}',
                              note='Пользователь явно выбрал пользовательскую базу вместо стандарта QX.' + (' Есть несоответствия — проверь.' if bad else ''),
                              registry=bool(item.get('registry') or item.get('registry_number')),
                              constraints={'kind':kind,'registry_number':str(item.get('registry_number') or ''),**item}))
        if bad:
            warnings.append(f'{category} «{item.get("name")}» не закрывает часть требований: ' + '; '.join(x['Проверка'] for x in bad))
        return True

    def _append_manual_peripheral(kind):
        category = 'Клавиатура' if kind == 'keyboard' else 'Мышь'
        rows.append(Component(category, category+' — вручную', price=0.0, source='Вручную',
                              note='Ручной источник выбран пользователем; название и цену укажи в таблице расчёта.',
                              constraints={'kind':kind}).to_dict())

    if req.need_keyboard or req.need_mouse:
        kb_mode = _peripheral_source_mode(req,'keyboard') if req.need_keyboard else None
        ms_mode = _peripheral_source_mode(req,'mouse') if req.need_mouse else None

        # This is the normal/default path: QX pair is kept even if user catalogs contain
        # matching keyboards or mice. Replacement happens only after explicit source switch.
        if req.need_keyboard and req.need_mouse and kb_mode=='qx' and ms_mode=='qx':
            qx('keyboard_mouse', 'Клавиатура + мышь',
               note='Стандарт QX. Пользовательские базы клавиатур/мышей не заменяют этот комплект автоматически.')
        else:
            for kind, needed, mode in (('keyboard',req.need_keyboard,kb_mode),('mouse',req.need_mouse,ms_mode)):
                if not needed:
                    continue
                if mode=='catalog':
                    if not _append_saved_peripheral(kind):
                        category='Клавиатура' if kind=='keyboard' else 'Мышь'
                        rows.append(Component(category, category+' по ТЗ', price=0.0, source='Вручную',
                                              note='Пользователь выбрал базу, но подходящая сохранённая модель не найдена. Название и цену укажи вручную.',
                                              constraints={'kind':kind}).to_dict())
                        warnings.append(f'Для {"клавиатуры" if kind=="keyboard" else "мыши"} выбран режим пользовательской базы, но подходящая модель не найдена.')
                elif mode=='manual':
                    _append_manual_peripheral(kind)
                else:
                    row=_qx_individual_peripheral(kind,qx_prices)
                    rows.append(row)
                    if float(row.get('price') or 0)<=0:
                        warnings.append(('Для отдельной клавиатуры QX' if kind=='keyboard' else 'Для отдельной мыши QX') +
                                        ' не задана отдельная цена. Стандартный комплект QX (клавиатура+мышь) имеет общую цену; отдельную цену можно задать во вкладке «Цены / прайсы».')

    if req.need_os:
        rows.append(Component('ОС', req.os_text or 'Операционная система', price=0, source='Вручную', note='Лицензию и цену ОС нужно подтвердить вручную.'))

    # One assembly operation per PC/AIO/AWS unit. A custom equipment profile can
    # keep its own assembly name/price; otherwise the row remains manual instead of
    # borrowing the QX price invisibly.
    if custom_equipment:
        assembly_item = next((x for x in profile_components if str(x.get('role') or '').strip().lower() in ('assembly','сборка')), None)
        if assembly_item:
            rows.append(profile_component_row({**assembly_item, 'category':'Сборка'}))
        else:
            rows.append(Component('Сборка', f'Сборка ({profile_label})', price=0.0, source=profile_label,
                                  note='Цена сборки в этом профиле не задана. Можно добавить компонент с ролью «Сборка» в базе оборудования или ввести цену вручную.'))
    else:
        qx('assembly', 'Сборка', note='750 ₽ на одну собираемую единицу; редактируется во вкладке «Цены QX».')

    if custom_equipment:
        reg_name = str(equipment_profile.get('final_registry_name') or '').strip()
        reg_number = str(equipment_profile.get('final_registry_number') or '').strip()
        reg_code = str(equipment_profile.get('final_registry_code') or '').strip()
        if reg_name or reg_number:
            rec = {
                'platform': platform,
                'product_type': req.product_type,
                'execution_code': reg_code or 'профиль',
                'product_name': reg_name or f'{profile_label} — реестровое изделие',
                'primary_registration_number': '',
                'registry_number': reg_number,
                'has_gpu': bool(req.need_gpu), 'has_ssd': True, 'has_hdd': bool(req.hdd_gb_min),
                'has_hub': any('hub' in str(x.get('role') or '').lower() or 'хаб' in str(x.get('category') or '').lower() for x in profile_components),
                'registry_wifi': any(bool(x.get('registry')) and ('wifi' in str(x.get('role') or '').lower() or 'wi-fi' in str(x.get('category') or '').lower()) for x in profile_components),
                'registry_cardreader': any(bool(x.get('registry')) and ('cardreader' in str(x.get('role') or '').lower() or 'картрид' in str(x.get('category') or '').lower()) for x in profile_components),
                'source_profile': profile_label,
            }
        else:
            rec = None
            warnings.append(f'Для базы «{profile_label}» не задана реестровая запись готового изделия. Компоненты и их реестровые признаки подставлены, но карточка реестрового изделия останется пустой до заполнения профиля.')
        checks = _compatibility(req, platform, case_key, board=board, source_label=profile_label,
                                cardreader_selected=False, extra_components=profile_components)
    else:
        rec = find_registry_record(platform, req.product_type, bool(req.need_gpu), bool(req.hdd_gb_min), registry_device)
        checks = _compatibility(req, platform, case_key, registry_device)

    # Independent drive-capacity guard. This makes a parser/rounding regression visible
    # immediately instead of allowing a smaller SSD/HDD to hide behind the filled-TZ table.
    def _drive_row(category):
        return next((x for x in rows if getattr(x, 'category', None) == category), None)
    ssd_row = _drive_row('SSD')
    if ssd_row is not None and req.ssd_gb_min is not None:
        have = int((ssd_row.constraints or {}).get('min_gb') or 0)
        checks.insert(0, {'Проверка':'Объём SSD, ГБ','Требование':f'≥ {req.ssd_gb_min}','Факт QX':str(have),'Статус':'OK' if have >= req.ssd_gb_min else 'НЕ ПРОХОДИТ'})
    if ssd_row is not None and getattr(req, 'ssd_25_required', False):
        ff = str((ssd_row.constraints or {}).get('form_factor') or '')
        checks.insert(0, {'Проверка':'Форм-фактор SSD','Требование':'2,5"','Факт QX':ff or 'не указан','Статус':'OK' if ff == '2.5' else 'НЕ ПРОХОДИТ'})
    hdd_row = _drive_row('HDD')
    if req.hdd_gb_min is not None:
        have = int(((hdd_row.constraints if hdd_row else {}) or {}).get('capacity_gb') or ((hdd_row.constraints if hdd_row else {}) or {}).get('min_gb') or 0)
        checks.insert(0, {'Проверка':'Объём HDD, ГБ','Требование':f'≥ {req.hdd_gb_min}','Факт QX':str(have or 'HDD не выбран'),'Статус':'OK' if have >= req.hdd_gb_min else 'НЕ ПРОХОДИТ'})

    # CPU requirements are checked against the selected CPU itself. Older builds could
    # fall back to i7-14700 even when its base clock violated the tender; never do that.
    cpu_obj = cpu_by_model(cpu_model)
    if cpu_obj:
        def cpu_check(label, need, have, ok):
            if need is not None:
                checks.insert(0, {'Проверка':label,'Требование':str(need),'Факт QX':str(have),'Статус':'OK' if ok else 'НЕ ПРОХОДИТ'})
        # A manually selected CPU is allowed, but socket/RAM incompatibility must be visible.
        board_socket = str(board.get('socket') or '')
        cpu_socket = str(getattr(cpu_obj, 'socket', '') or '')
        norm_socket = lambda x: ''.join(ch for ch in str(x).upper() if ch.isalnum())
        if board_socket and cpu_socket:
            cpu_check('Сокет процессора / материнской платы', board_socket, cpu_socket, norm_socket(board_socket) == norm_socket(cpu_socket))
        board_ram = str(board.get('ram_type') or req.ram_type or '').upper()
        cpu_mem = [str(x).upper() for x in (getattr(cpu_obj, 'memory_types', ()) or ())]
        if board_ram and cpu_mem:
            cpu_check('Поддержка типа оперативной памяти процессором', board_ram, ', '.join(cpu_mem), board_ram in cpu_mem)
        cpu_check('Ядра процессора', f'≥ {req.cpu_cores_min}' if req.cpu_cores_min else None, cpu_obj.cores, not req.cpu_cores_min or cpu_obj.cores >= req.cpu_cores_min)
        cpu_check('Потоки процессора', f'≥ {req.cpu_threads_min}' if req.cpu_threads_min else None, cpu_obj.threads, not req.cpu_threads_min or cpu_obj.threads >= req.cpu_threads_min)
        cpu_check('Базовая частота CPU, ГГц', f'≥ {req.cpu_freq_ghz_min:g}' if req.cpu_freq_ghz_min else None, cpu_obj.base_ghz, not req.cpu_freq_ghz_min or cpu_obj.base_ghz >= req.cpu_freq_ghz_min)
        cpu_check('Максимальная частота CPU, ГГц', f'≥ {req.cpu_freq_max_ghz_min:g}' if req.cpu_freq_max_ghz_min else None, cpu_obj.boost_ghz, not req.cpu_freq_max_ghz_min or cpu_obj.boost_ghz >= req.cpu_freq_max_ghz_min)
        cpu_check('Кэш L3 CPU, МБ', f'≥ {req.cpu_l3_mb_min}' if req.cpu_l3_mb_min else None, cpu_obj.l3_mb, not req.cpu_l3_mb_min or cpu_obj.l3_mb >= req.cpu_l3_mb_min)
        cpu_check('Тепловыделение CPU, Вт', f'≤ {req.cpu_tdp_w_max}' if req.cpu_tdp_w_max else None, cpu_obj.tdp_w, not req.cpu_tdp_w_max or cpu_obj.tdp_w <= req.cpu_tdp_w_max)
        if req.need_integrated_graphics:
            cpu_check('Встроенная графика', 'Да', 'Да' if cpu_obj.igpu else 'Нет', cpu_obj.igpu)
        if req.cpu_passmark_min:
            have = int(cpu_obj.passmark_ref or 0)
            checks.insert(0, {'Проверка':'PassMark CPU Mark (справочно)','Требование':f'≥ {req.cpu_passmark_min}','Факт QX':str(have or 'нет справочного значения'),'Статус':'OK' if have >= req.cpu_passmark_min else 'НЕТ ДАННЫХ' if not have else 'НЕ ПРОХОДИТ'})
        if req.cpu_x86_64_required:
            checks.insert(0, {'Проверка':'Архитектура x86-64','Требование':'Да','Факт QX':cpu_model,'Статус':'OK'})
    else:
        needed = []
        if req.cpu_cores_min: needed.append(f'ядра ≥{req.cpu_cores_min}')
        if req.cpu_threads_min: needed.append(f'потоки ≥{req.cpu_threads_min}')
        if req.cpu_freq_ghz_min: needed.append(f'база ≥{req.cpu_freq_ghz_min:g} ГГц')
        if req.cpu_freq_max_ghz_min: needed.append(f'boost ≥{req.cpu_freq_max_ghz_min:g} ГГц')
        if req.cpu_l3_mb_min: needed.append(f'L3 ≥{req.cpu_l3_mb_min} МБ')
        if req.cpu_tdp_w_max: needed.append(f'TDP ≤{req.cpu_tdp_w_max} Вт')
        checks.insert(0, {'Проверка':'Процессор','Требование':', '.join(needed) or 'по ТЗ','Факт QX':cpu_model,'Статус':'НЕТ ДАННЫХ'})
    failed = [c for c in checks if c.get('Статус') == 'НЕ ПРОХОДИТ']
    unknowns = [c for c in checks if c.get('Статус') == 'НЕТ ДАННЫХ']
    if failed:
        warnings.append(f'Есть требования ТЗ, которые текущая конфигурация {profile_label} не закрывает: ' + '; '.join(f"{x['Проверка']} ({x['Факт QX']} / нужно {x['Требование']})" for x in failed))
        if any('USB' in str(x.get('Проверка','')) for x in failed) and not (any(_extra_panel_counts(req,'front').values()) or any(_extra_panel_counts(req,'rear').values())):
            warnings.append('Если эти USB-требования закрываются дополнительной передней/задней планкой, укажи её фактические порты в блоке «Дополнительные планки портов» и пересобери позицию.')
    if unknowns:
        warnings.append(f'По части характеристик {profile_label} в сохранённом справочнике нет данных; программа не считает их выполненными автоматически: ' + '; '.join(x['Проверка'] for x in unknowns))
    if req.manual_requirements:
        warnings.append('Требуют отдельного подтверждения по ТЗ: ' + '; '.join(req.manual_requirements))
    rec_out = rec.to_dict() if hasattr(rec, 'to_dict') else rec
    return [x.to_dict() if hasattr(x,'to_dict') else x for x in rows], rec_out, warnings, checks


