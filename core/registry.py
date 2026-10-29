from dataclasses import dataclass, asdict
from typing import Literal

Platform = Literal['intel', 'amd']
ProductType = Literal['system', 'aio24', 'aio27', 'aws24', 'aws27']
RegistryDevice = Literal['wifi', 'cardreader']

CODES = ['0102', '0112', '1102', '1112', '0101', '0111', '1101', '1111']

@dataclass
class RegistryRecord:
    platform: str
    product_type: str
    execution_code: str
    product_name: str
    primary_registration_number: str
    registry_number: int
    has_gpu: bool
    has_ssd: bool
    has_hdd: bool
    has_hub: bool
    registry_wifi: bool
    registry_cardreader: bool

    def to_dict(self):
        return asdict(self)


def _suffix(number: int | None) -> str:
    return '' if number is None else f'-{number:02d}'


def _record_meta(platform: Platform, product_type: ProductType):
    # Values reconstructed from the supplied "Таблица исполнений реестр".
    if platform == 'intel':
        platform_name = 'B760'
        if product_type == 'system':
            return platform_name, 'PC', None, 10598678, '47237353.466369.001', 0
        if product_type == 'aio24':
            return platform_name, 'AIO', '24', 10598686, '47237353.466369.002', 0
        if product_type == 'aio27':
            return platform_name, 'AIO', '27', 10598694, '47237353.466369.002', 8
        if product_type == 'aws24':
            return platform_name, 'AWS', '24', 10598702, '47237353.466369.003', 0
        if product_type == 'aws27':
            return platform_name, 'AWS', '27', 10598710, '47237353.466369.003', 8
    else:
        platform_name = 'A520'
        if product_type == 'system':
            return platform_name, 'PC', None, 10598719, '47237353.466369.001', 8
        if product_type == 'aio24':
            return platform_name, 'AIO', '24', 10598727, '47237353.466369.002', 16
        if product_type == 'aio27':
            return platform_name, 'AIO', '27', 10598735, '47237353.466369.002', 24
        if product_type == 'aws24':
            return platform_name, 'AWS', '24', 10598743, '47237353.466369.003', 16
        if product_type == 'aws27':
            return platform_name, 'AWS', '27', 10598751, '47237353.466369.003', 24
    raise ValueError('Unsupported platform/product type')


def choose_execution_code(has_gpu: bool, has_hdd: bool, registry_device: RegistryDevice) -> str:
    # Registry table supplied by user: SSD and USB hub are present in every execution.
    return f"{1 if has_gpu else 0}1{1 if has_hdd else 0}{1 if registry_device == 'wifi' else 2}"


def find_registry_record(platform: Platform, product_type: ProductType,
                         has_gpu: bool, has_hdd: bool,
                         registry_device: RegistryDevice) -> RegistryRecord:
    code = choose_execution_code(has_gpu, has_hdd, registry_device)
    idx = CODES.index(code)
    platform_name, prefix, size, reg_base, primary_base, suffix_base = _record_meta(platform, product_type)

    suffix_number = suffix_base + idx
    if suffix_base == 0 and idx == 0:
        suffix_number = None
    # System Intel first record and AIO/AWS Intel 24 first records have no suffix.
    primary = primary_base + _suffix(suffix_number)

    if prefix == 'PC':
        name = f'Системный блок QX "PC {platform_name}/{code}" {primary}'
    else:
        name = f'{"Моноблок" if prefix == "AIO" else "АРМ/ПЭВМ"} QX "{prefix} {platform_name}/{size}-{code}" {primary}'

    return RegistryRecord(
        platform=platform,
        product_type=product_type,
        execution_code=code,
        product_name=name,
        primary_registration_number='Без номера',
        registry_number=reg_base + idx,
        has_gpu=has_gpu,
        has_ssd=True,
        has_hdd=has_hdd,
        has_hub=True,
        registry_wifi=registry_device == 'wifi',
        registry_cardreader=registry_device == 'cardreader',
    )


def all_records():
    out = []
    for platform in ('intel', 'amd'):
        for product_type in ('system', 'aio24', 'aio27', 'aws24', 'aws27'):
            for code in CODES:
                gpu = code[0] == '1'
                hdd = code[2] == '1'
                device = 'wifi' if code[3] == '1' else 'cardreader'
                out.append(find_registry_record(platform, product_type, gpu, hdd, device).to_dict())
    return out
