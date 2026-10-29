DEFAULT_QX_PRICES = {
    'barebone_24_fhd': {'name': 'Баребон QX 24" 1K РАПТЕР', 'price': 13086.00},
    'barebone_27_2k': {'name': 'Баребон QX 27" 2K РАПТЕР', 'price': 16106.00},
    'case_protected': {'name': 'Корпус QX защищённый', 'price': 1750.00},
    'case_standard': {'name': 'Корпус QX незащищённый', 'price': 1407.00},
    'motherboard_intel': {'name': 'Материнская плата QX Орбита B760m PRO', 'price': 11800.00},
    'motherboard_amd': {'name': 'Материнская плата QX A520M-W X8', 'price': 6151.00},
    'm2_key_e_adapter': {'name': 'Переходник QX для M.2 Key E / Wi‑Fi (AMD)', 'price': 0.00},
    'cardreader_registry': {'name': 'Картридер QX CRDQX0001RU (реестр)', 'price': 1500.00},
    'wifi_registry': {'name': 'Wi-Fi/Bluetooth QX WFQXSPD0001RU (реестр)', 'price': 914.64},
    'expansion_bar': {'name': 'Расширительная планка QX для АРМ', 'price': 1005.00},
    'hub_registry': {'name': 'USB-HUB QX USBQX0001RU (реестр)', 'price': 390.00},
    'keyboard_mouse': {'name': 'Клавиатура + мышь QX', 'price': 668.00},
    'keyboard': {'name': 'Клавиатура QX', 'price': 0.00},
    'mouse': {'name': 'Мышь QX', 'price': 0.00},
    'assembly': {'name': 'Сборка ПК', 'price': 750.00},
}

DEFAULT_SETTINGS = {
    'usd_buffer_rub': 5.0,
    'offline_mode': False,
    'usd_rate_cached': 86.8872,
    'usd_rate_date_cached': '04.09.2026',
    'default_markup': 0.20,
    'default_delivery': 0.0,
    'default_bg1': 0.0,
    'default_bg2': 0.0,
    # Arsenal / project defaults
    'default_bg': 0.0,
    'default_go': 0.0,
    'default_sender': 'ЗИОН',
    'default_country': 'Россия',
    'default_trademark': '1093786',
    'prefer_registry_device_when_not_required': 'wifi',
    'prefer_registry_device_when_both_required': 'wifi',
    'smart_registry_device': True,
    'ui_theme': 'dark',
    'sidebar_width': 320,
    'sidebar_collapsed': False,
}

QX_SPECS = {
    'intel': {
        'name': 'QX Орбита B760m PRO',
        'socket': 'LGA1700', 'chipset': 'B760', 'form_factor': 'micro ATX 244x244 мм',
        'ram_type': 'DDR5', 'ram_max_gb': 128, 'ram_max_mhz': 5800, 'ram_slots': 4,
        'ethernet_mbps': 2500, 'ethernet_ports': 1,
        'video': {'DVI-D': 1, 'DisplayPort': 2, 'HDMI': 1, 'VGA': 1},
        'm2_key_m': 2, 'm2_key_e': 1, 'sata': 4, 'pcie_x1': 1, 'pcie_x16': 1, 'tpm_header': 1,
        'usb_external': {'USB 2.0 Type-A': 2, 'USB 3.2 Gen1 Type-A': 2, 'USB 3.2 Gen2 Type-A': 2, 'USB 3.2 Gen2x2 Type-C': 2},
    },
    'amd': {
        'name': 'QX A520M-W X8',
        'socket': 'AM4', 'chipset': 'A520', 'form_factor': 'micro ATX 220x215 мм',
        'ram_type': 'DDR4', 'ram_max_gb': 64, 'ram_max_mhz': 3200, 'ram_slots': 2,
        'ethernet_mbps': 1000, 'ethernet_ports': 1,
        'video': {'DisplayPort': 1, 'HDMI': 1, 'VGA': 1},
        'm2_key_m': 1, 'm2_key_e': 0, 'm2_key_e_via_adapter': 1, 'sata': 4, 'pcie_x1': 1, 'pcie_x16': 1, 'tpm_header': 0,
        'usb_external': {'USB 2.0 Type-A': 2, 'USB 3.2 Gen1 Type-A': 4},
        'wifi_adapter_note': 'На AMD QX отдельного M.2 Key E на плате нет: используется штатный переходник QX, который даёт 1 подключение Key E для Wi‑Fi. Переходник добавляется в расчёт всегда и по умолчанию стоит 0 ₽.',
    },
}

CASE_SPECS = {
    'standard': {
        'name': 'Корпус QX ТИП 1', 'height_mm': 349, 'length_mm': 310, 'width_mm': 185,
        'bay_525': 1, 'bay_25': 7, 'bay_35': 2,
        'usb2_front': 2,
        'usb3_gen1_a_front_base': 0, 'usb3_gen1_c_front_base': 0,
        'usb3_gen1_a_front_with_cardreader': 1, 'usb3_gen1_c_front_with_cardreader': 1,
        'protected': False,
    },
    'protected': {
        'name': 'Корпус QX ТИП 2', 'height_mm': 345, 'length_mm': 299, 'width_mm': 170,
        'bay_525': 3, 'bay_25': 2, 'bay_35': 0,
        'usb2_front': 0,
        'usb3_gen1_a_front_base': 2, 'usb3_gen1_c_front_base': 2,
        'usb3_gen1_a_front_with_cardreader': 3, 'usb3_gen1_c_front_with_cardreader': 3,
        'protected': True,
    },
}

# Capabilities explicitly visible in the supplied QX developer workbook.
# The cardreader contributes one USB 3.2 Gen1 Type-A and one Type-C port.
REGISTRY_MODULE_SPECS = {
    'cardreader': {
        'usb3_gen1_type_a': 1,
        'usb3_gen1_type_c': 1,
    },
    'wifi': {},
    # The supplied workbook does not state the external-port count of USBQX0001RU,
    # so it is intentionally not counted as a chassis/external USB port.
    'hub': {},
}

# Only characteristics that are explicit in the supplied QX price/developer files are asserted here.
# Unknown display/chassis features are reported as "НЕТ ДАННЫХ" rather than guessed.
AIO_SPECS = {
    'aio24': {
        'diagonal_in': 23.8,
        'resolution': '1920x1080',
        'refresh_hz': 75,
        # User-confirmed current platform fact: the non-registry cardreader is built into
        # the barebone price and exposes one USB 3.2 Gen1 Type-A and one Type-C.
        'built_in_cardreader': True,
        'built_in_cardreader_ports': {
            'usb3_gen1_type_a': 1,
            'usb3_gen1_type_c': 1,
        },
        'known_from': 'QX platform facts confirmed by user: 23.8 Full HD, 75 Hz, built-in non-registry cardreader',
    },
    'aio27': {
        'diagonal_in': 27.0,
        'resolution': '2560x1440',
        'refresh_hz': 75,
        'built_in_cardreader': True,
        'built_in_cardreader_ports': {
            'usb3_gen1_type_a': 1,
            'usb3_gen1_type_c': 1,
        },
        'known_from': 'QX platform facts confirmed by user: 27 2K, 75 Hz, built-in non-registry cardreader',
    },
}
