from __future__ import annotations

from typing import Iterable


EXIT_PERCENTS = (25, 22, 20, 15, 10)


def money(value: float, decimals: bool = False) -> str:
    value = float(value or 0)
    if not decimals and abs(value - round(value)) < 0.005:
        return f'{int(round(value)):,}'.replace(',', ' ')
    return f'{value:,.2f}'.replace(',', ' ').replace('.', ',')


def exit_points(purchase: float, delivery: float = 0, bg: float = 0, go: float = 0,
                percents: Iterable[int] = EXIT_PERCENTS):
    """Return selling break/exit points used in the legacy QX calculator.

    Markup is applied to equipment purchase only. Delivery, BG and GO are added after it.
    This mirrors the supplied «Расчёт V 3.0_CF» workbook and the user's Arsenal example.
    """
    purchase = float(purchase or 0)
    extras = float(delivery or 0) + float(bg or 0) + float(go or 0)
    return [(int(p), purchase * (1 + float(p) / 100.0) + extras) for p in percents]



def normalize_arsenal_os_name(need_os: bool, os_text) -> str:
    """Return a human OS name for Arsenal, never a boolean-like "Да/Есть" value."""
    if not need_os:
        return 'нет'
    text = str(os_text or '').strip()
    if not text:
        return ''
    low = text.casefold().strip(' .;:')
    boolean_words = {
        'да', 'есть', 'имеется', 'наличие', 'предусмотрено', 'требуется',
        'true', '1', 'yes', 'present',
    }
    if low in boolean_words:
        return ''
    return text


def arsenal_equipment_default(plan: dict) -> dict:
    """Safe default Arsenal row for one project position.

    Prefer the registry record of the finished product. For a custom vendor profile
    without such a record, never fall back to the first BOM component (usually CPU).
    """
    plan = dict(plan or {})
    reg = dict(plan.get('registry') or {})
    if str(reg.get('product_name') or '').strip():
        return {
            'equipment': str(reg.get('product_name') or '').strip(),
            'registry_number': str(reg.get('registry_number') or '').strip(),
            'registry_missing': not bool(str(reg.get('registry_number') or '').strip()),
        }

    req = dict(plan.get('req') or {})
    title = str(req.get('title') or '').strip()
    profile = str(req.get('equipment_profile_name') or '').strip()
    if profile and title:
        equipment = title if profile.casefold() in title.casefold() else f'{profile} — {title}'
    else:
        equipment = profile or title or 'Оборудование'
    return {'equipment': equipment, 'registry_number': '', 'registry_missing': True}


def arsenal_position_summary(plans: list[dict]) -> dict:
    """Compute purchase and a meaningful *set* unit only for equal quantities.

    Four independent product rows with quantity 59 do NOT represent 236 sets.
    When quantities differ, there is no justified single set unit cost.
    The returned breakdown is intentionally suitable for an audit trail.
    """
    positions = []
    for index, plan in enumerate(plans or [], 1):
        requirement = (plan or {}).get('req') or {}
        try:
            quantity = max(0, int(requirement.get('quantity') or 0))
        except (TypeError, ValueError):
            quantity = 0
        unit_cost = 0.0
        for row in (plan or {}).get('rows') or []:
            try:
                row_qty = float(row.get('qty') if row.get('qty') not in (None, '') else 1)
                row_price = float(row.get('price') or 0)
                unit_cost += row_qty * row_price
            except (ValueError, TypeError):
                continue
        positions.append({
            'title': str(requirement.get('item_name') or requirement.get('title') or f'Позиция {index}'),
            'quantity': quantity,
            'unit_cost': unit_cost,
            'total_cost': unit_cost * quantity,
        })
    total_cost = sum(p['total_cost'] for p in positions)
    same_count = bool(positions) and positions[0]['quantity'] > 0 and all(
        p['quantity'] == positions[0]['quantity'] for p in positions)
    set_quantity = positions[0]['quantity'] if same_count else None
    set_unit_cost = sum(p['unit_cost'] for p in positions) if same_count else None
    return {'positions': positions, 'purchase': total_cost,
            'set_quantity': set_quantity, 'set_unit_cost': set_unit_cost,
            'is_set': len(positions) > 1 and same_count}


def build_arsenal_text(
    purchase: float,
    project_qty: int,
    delivery: float,
    bg: float,
    go: float,
    sender: str,
    equipment: list[dict],
    country: str,
    os_name: str,
    trademark: str,
    position_summary: dict | None = None,
) -> str:
    qty = max(1, int(project_qty or 1))
    unit_cost = float(purchase or 0) / qty
    exits = exit_points(purchase, delivery, bg, go)
    exit_text = ', '.join(f'{money(value)} ({pct}%)' for pct, value in exits)

    if position_summary and position_summary.get('positions'):
        positions = position_summary['positions']
        total = float(position_summary['purchase'])
        set_qty = position_summary.get('set_quantity')
        set_unit = position_summary.get('set_unit_cost')
        if set_qty and len(positions) > 1:
            cost_header = (f'Себестоимость: {money(set_unit)} за комплект '
                           f'(по 1 шт. каждой из {len(positions)} позиций), {money(total)} общ.')
            quantity_header = f'Количество комплектов: {set_qty}'
        elif set_qty:
            cost_header = f'Себестоимость: {money(set_unit)} за ед., {money(total)} общ.'
            quantity_header = f'Количество изделий: {set_qty}'
        else:
            cost_header = f'Общая себестоимость: {money(total)} (разные количества товаров)'
            quantity_header = ('Единую себестоимость комплекта рассчитать нельзя: '
                               'проверьте количества отдельных товаров.')
        breakdown = ['По позициям:'] + [
            f"  {i}. {row['title']}: {row['quantity']} шт. × {money(row['unit_cost'])} "
            f"= {money(row['total_cost'])}"
            for i, row in enumerate(positions, 1)
        ]
    else:
        cost_header = f'Себестоимость: {money(unit_cost)} за ед., {money(purchase)} общ.'
        quantity_header = ''
        breakdown = []

    lines = [
        cost_header,
        *([quantity_header] if quantity_header else []),
        *breakdown,
        f'Доставка: {money(delivery)}',
        f'Точка выхода: {exit_text}',
        '_' * 53,
        f'1. От кого: {sender}',
    ]

    if not equipment:
        lines.extend(['2. Оборудование: ', 'Реестровый номер: '])
    else:
        first = True
        for item in equipment:
            prefix = '2. Оборудование: ' if first else 'Оборудование: '
            lines.append(prefix + str(item.get('equipment') or ''))
            lines.append('Реестровый номер: ' + str(item.get('registry_number') or ''))
            first = False

    lines.extend([
        f'3. Страна: {country}',
        f'4. Название ОС: {os_name}',
        f'5. Информация БГ/ГО участие/исполнение: БГ: {money(bg)}; ГО: {money(go)}',
        f'6. Товарный знак: {trademark}',
    ])
    return '\n'.join(lines)
