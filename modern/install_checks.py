"""Non-destructive installation checks, including the *actual* expanded CPU list.

The legacy regression suite intentionally uses stock QX fixtures; this additional
check validates current real catalog selection without depending on a fixed model.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import cpu_catalog
from core.cpu_catalog import cpu_satisfies, cpu_by_model
from core.tz_parser import Requirements
from core.storage import load_prices, load_settings
from core.selector import build_plan
from core.defaults import QX_SPECS


def check(name: str, req: Requirements):
    rows, registry, warnings, checks = build_plan(req, load_prices(), load_settings())
    procs = [r for r in rows if r.get('category') == 'Процессор']
    if len(procs) != 1:
        raise AssertionError(f'{name}: ожидалась одна строка CPU, получено {len(procs)}')
    row=procs[0]
    model=row['name'].removesuffix(' OEM')
    cpu=cpu_by_model(model)
    platform=row.get('constraints',{}).get('platform') or req.platform
    if not cpu or not cpu_satisfies(cpu, req, platform):
        raise AssertionError(f'{name}: неподходящий CPU {model!r} для {req!r}, платформа {platform}')
    if platform not in QX_SPECS:
        raise AssertionError(f'{name}: неизвестная платформа {platform}')
    board=QX_SPECS[platform]
    socket=str(board.get('socket') or '').upper().replace('-','').replace(' ','')
    cpu_socket=str(cpu.socket or '').upper().replace('-','').replace(' ','')
    if socket and cpu_socket and socket != cpu_socket:
        raise AssertionError(f'{name}: CPU {model} сокет {cpu.socket}, плата {socket}')
    board_ram=str(board.get('ram_type') or '').upper()
    if board_ram and cpu.memory_types and board_ram not in [str(v).upper() for v in cpu.memory_types]:
        raise AssertionError(f'{name}: CPU {model} не поддерживает RAM платы {board_ram}')
    print(f'[QX] {name}: {model} ({platform.upper()}) — подходит по ограничениям')


def main():
    # The dynamic, possibly user-updated CPU list MUST remain enabled here.
    print(f'[QX] CPU database: {cpu_catalog.catalog_stats()["total"]} models, '
          f'external: {cpu_catalog.catalog_stats()["external"]}')
    check('Моноблок, автоматическая платформа', Requirements(
          title='Тест моноблока',product_type='aio24',quantity=1,
          cpu_cores_min=6,cpu_threads_min=12,cpu_freq_ghz_min=2.5,
          cpu_freq_max_ghz_min=4.3,cpu_l3_mb_min=12,cpu_tdp_w_max=65,
          need_integrated_graphics=True,ram_type_min_generation=4))
    check('Системный блок AMD',Requirements(
          title='Тест системного блока',product_type='system',quantity=1,platform='amd',
          cpu_cores_min=6,cpu_threads_min=12,cpu_freq_ghz_min=3.3,
          cpu_freq_max_ghz_min=4.2,cpu_l3_mb_min=12,need_integrated_graphics=True))
    print('[QX] Live CPU compatibility checks: OK')


if __name__=='__main__':
    main()
