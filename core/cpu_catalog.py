from __future__ import annotations

from dataclasses import dataclass, asdict, replace
import json
from pathlib import Path


@dataclass(frozen=True)
class CPU:
    model: str
    platform: str
    cores: int
    threads: int
    base_ghz: float
    boost_ghz: float
    l3_mb: int
    igpu: bool
    tdp_w: int
    fallback_rank: int = 999
    passmark_ref: int = 0
    business: bool = False
    manufacturer: str = ''
    socket: str = ''
    memory_types: tuple = ()
    source: str = 'builtin'

    def to_dict(self):
        d = asdict(self)
        d['memory_types'] = list(self.memory_types)
        return d


def _c(model, platform, cores, threads, base, boost, l3, igpu, tdp, rank=999, passmark=0, business=False, socket='', memory=()):
    manufacturer = 'Intel' if model.startswith('Intel') else 'AMD'
    return CPU(model, platform, cores, threads, base, boost, l3, igpu, tdp, rank, passmark, business,
               manufacturer, socket or ('LGA1700' if platform == 'intel' else 'AM4'), tuple(memory or (('DDR5','DDR4') if platform=='intel' else ('DDR4',))), 'builtin')


# Built-in offline catalog for the QX platforms.  The app can additionally download
# the full Intel/AMD catalog from BuildCores OpenDB in the “Справочники” tab.
# Intel base clock is the Performance-core base frequency for hybrid desktop CPUs.
BUILTIN_CPUS = [
    # AMD AM4 A520 — 4000/5000 families, including corporate PRO/GE variants.
    _c('AMD Ryzen 3 4100','amd',4,8,3.8,4.0,4,False,65,8),
    _c('AMD Ryzen 3 4300G','amd',4,8,3.8,4.0,4,True,65,10),
    _c('AMD Ryzen 3 PRO 4350G','amd',4,8,3.8,4.0,4,True,65,11,business=True),
    _c('AMD Ryzen 3 PRO 4350GE','amd',4,8,3.5,4.0,4,True,35,12,business=True),
    _c('AMD Ryzen 3 PRO 5350G','amd',4,8,4.0,4.2,8,True,65,13,business=True),
    _c('AMD Ryzen 3 PRO 5350GE','amd',4,8,3.6,4.2,8,True,35,14,business=True),
    _c('AMD Ryzen 3 PRO 5355G','amd',4,8,4.0,4.2,8,True,65,15,business=True),
    _c('AMD Ryzen 5 4500','amd',6,12,3.6,4.1,8,False,65,18),
    _c('AMD Ryzen 5 4600G','amd',6,12,3.7,4.2,8,True,65,20),
    _c('AMD Ryzen 5 PRO 4650G','amd',6,12,3.7,4.2,8,True,65,21,business=True),
    _c('AMD Ryzen 5 PRO 4650GE','amd',6,12,3.3,4.2,8,True,35,22,business=True),
    _c('AMD Ryzen 5 PRO 5650GE','amd',6,12,3.4,4.4,16,True,35,30,18006,True),
    _c('AMD Ryzen 5 5600GE','amd',6,12,3.4,4.4,16,True,35,31),
    _c('AMD Ryzen 5 PRO 5655GE','amd',6,12,3.4,4.4,16,True,35,32,18060,True),
    _c('AMD Ryzen 5 5500GT','amd',6,12,3.6,4.4,16,True,65,33),
    _c('AMD Ryzen 5 PRO 5650G','amd',6,12,3.9,4.4,16,True,65,34,business=True),
    _c('AMD Ryzen 5 PRO 5655G','amd',6,12,3.9,4.4,16,True,65,35,business=True),
    _c('AMD Ryzen 5 5600G','amd',6,12,3.9,4.4,16,True,65,36,19625),
    _c('AMD Ryzen 5 5600GT','amd',6,12,3.6,4.6,16,True,65,37),
    _c('AMD Ryzen 5 5500','amd',6,12,3.6,4.2,16,False,65,50),
    _c('AMD Ryzen 5 5600','amd',6,12,3.5,4.4,32,False,65,51),
    _c('AMD Ryzen 5 5600X','amd',6,12,3.7,4.6,32,False,65,52,21824),
    _c('AMD Ryzen 7 PRO 4750GE','amd',8,16,3.1,4.3,8,True,35,60,business=True),
    _c('AMD Ryzen 7 PRO 4750G','amd',8,16,3.6,4.4,8,True,65,61,business=True),
    _c('AMD Ryzen 7 PRO 5750GE','amd',8,16,3.2,4.6,16,True,35,62,21014,True),
    _c('AMD Ryzen 7 PRO 5755GE','amd',8,16,3.2,4.6,16,True,35,63,20870,True),
    _c('AMD Ryzen 7 PRO 5750G','amd',8,16,3.8,4.6,16,True,65,64,23752,True),
    _c('AMD Ryzen 7 5700G','amd',8,16,3.8,4.6,16,True,65,65,24221),
    _c('AMD Ryzen 7 5700','amd',8,16,3.7,4.6,16,False,65,70),
    _c('AMD Ryzen 7 5700X','amd',8,16,3.4,4.6,32,False,65,71),
    _c('AMD Ryzen 7 5700X3D','amd',8,16,3.0,4.1,96,False,105,72),
    _c('AMD Ryzen 7 5800X','amd',8,16,3.8,4.7,32,False,105,73),
    _c('AMD Ryzen 7 5800X3D','amd',8,16,3.4,4.5,96,False,105,74),
    _c('AMD Ryzen 9 5900X','amd',12,24,3.7,4.8,64,False,105,80),
    _c('AMD Ryzen 9 5900XT','amd',16,32,3.3,4.8,64,False,105,81),
    _c('AMD Ryzen 9 5950X','amd',16,32,3.4,4.9,64,False,105,82),

    # Intel LGA1700 — 12th generation.
    _c('Intel Core i3-12100','intel',4,8,3.3,4.3,12,True,60,10),
    _c('Intel Core i3-12100F','intel',4,8,3.3,4.3,12,False,58,11),
    _c('Intel Core i3-12300','intel',4,8,3.5,4.4,12,True,60,12),
    _c('Intel Core i5-12400','intel',6,12,2.5,4.4,18,True,65,20),
    _c('Intel Core i5-12400F','intel',6,12,2.5,4.4,18,False,65,21,19548),
    _c('Intel Core i5-12500','intel',6,12,3.0,4.6,18,True,65,22,19716),
    _c('Intel Core i5-12600','intel',6,12,3.3,4.8,18,True,65,23),
    _c('Intel Core i5-12600K','intel',10,16,3.7,4.9,20,True,125,24),
    _c('Intel Core i5-12600KF','intel',10,16,3.7,4.9,20,False,125,25),
    _c('Intel Core i7-12700','intel',12,20,2.1,4.9,25,True,65,30),
    _c('Intel Core i7-12700F','intel',12,20,2.1,4.9,25,False,65,31),
    _c('Intel Core i7-12700K','intel',12,20,3.6,5.0,25,True,125,32),
    _c('Intel Core i7-12700KF','intel',12,20,3.6,5.0,25,False,125,33),
    _c('Intel Core i9-12900','intel',16,24,2.4,5.1,30,True,65,40),
    _c('Intel Core i9-12900F','intel',16,24,2.4,5.1,30,False,65,41),
    _c('Intel Core i9-12900K','intel',16,24,3.2,5.2,30,True,125,42),
    _c('Intel Core i9-12900KF','intel',16,24,3.2,5.2,30,False,125,43),
    _c('Intel Core i9-12900KS','intel',16,24,3.4,5.5,30,True,150,44),

    # Intel LGA1700 — 13th generation.
    _c('Intel Core i3-13100','intel',4,8,3.4,4.5,12,True,60,50),
    _c('Intel Core i3-13100F','intel',4,8,3.4,4.5,12,False,58,51),
    _c('Intel Core i5-13400','intel',10,16,2.5,4.6,20,True,65,52,23895),
    _c('Intel Core i5-13400F','intel',10,16,2.5,4.6,20,False,65,53),
    _c('Intel Core i5-13500','intel',14,20,2.5,4.8,24,True,65,54),
    _c('Intel Core i5-13600','intel',14,20,2.7,5.0,24,True,65,55),
    _c('Intel Core i5-13600K','intel',14,20,3.5,5.1,24,True,125,56),
    _c('Intel Core i5-13600KF','intel',14,20,3.5,5.1,24,False,125,57),
    _c('Intel Core i7-13700','intel',16,24,2.1,5.2,30,True,65,60),
    _c('Intel Core i7-13700F','intel',16,24,2.1,5.2,30,False,65,61),
    _c('Intel Core i7-13700K','intel',16,24,3.4,5.4,30,True,125,62),
    _c('Intel Core i7-13700KF','intel',16,24,3.4,5.4,30,False,125,63),
    _c('Intel Core i9-13900','intel',24,32,2.0,5.6,36,True,65,70),
    _c('Intel Core i9-13900F','intel',24,32,2.0,5.6,36,False,65,71),
    _c('Intel Core i9-13900K','intel',24,32,3.0,5.8,36,True,125,72),
    _c('Intel Core i9-13900KF','intel',24,32,3.0,5.8,36,False,125,73),
    _c('Intel Core i9-13900KS','intel',24,32,3.2,6.0,36,True,150,74),

    # Intel LGA1700 — 14th generation.
    _c('Intel Core i3-14100','intel',4,8,3.5,4.7,12,True,60,80),
    _c('Intel Core i3-14100F','intel',4,8,3.5,4.7,12,False,58,81),
    _c('Intel Core i5-14400','intel',10,16,2.5,4.7,20,True,65,82),
    _c('Intel Core i5-14400F','intel',10,16,2.5,4.7,20,False,65,83),
    _c('Intel Core i5-14500','intel',14,20,2.6,5.0,24,True,65,84),
    _c('Intel Core i5-14600','intel',14,20,2.7,5.2,24,True,65,85),
    _c('Intel Core i5-14600K','intel',14,20,3.5,5.3,24,True,125,86),
    _c('Intel Core i5-14600KF','intel',14,20,3.5,5.3,24,False,125,87),
    _c('Intel Core i7-14700','intel',20,28,2.1,5.4,33,True,65,90),
    _c('Intel Core i7-14700F','intel',20,28,2.1,5.4,33,False,65,91),
    _c('Intel Core i7-14700K','intel',20,28,3.4,5.6,33,True,125,92),
    _c('Intel Core i7-14700KF','intel',20,28,3.4,5.6,33,False,125,93),
    _c('Intel Core i9-14900','intel',24,32,2.0,5.8,36,True,65,100),
    _c('Intel Core i9-14900F','intel',24,32,2.0,5.8,36,False,65,101),
    _c('Intel Core i9-14900K','intel',24,32,3.2,6.0,36,True,125,102),
    _c('Intel Core i9-14900KF','intel',24,32,3.2,6.0,36,False,125,103),
    _c('Intel Core i9-14900KS','intel',24,32,3.2,6.2,36,True,150,104),
]

EXTERNAL_FILE = Path(__file__).resolve().parent.parent / 'data' / 'cpu_catalog_external.json'
_external_cache = None


def _load_external():
    global _external_cache
    if _external_cache is not None:
        return _external_cache
    out = []
    try:
        obj = json.loads(EXTERNAL_FILE.read_text(encoding='utf-8'))
        for d in obj.get('cpus') or []:
            try:
                out.append(CPU(
                    model=str(d.get('model') or ''), platform=str(d.get('platform') or 'other'),
                    cores=int(d.get('cores') or 0), threads=int(d.get('threads') or 0),
                    base_ghz=float(d.get('base_ghz') or 0), boost_ghz=float(d.get('boost_ghz') or 0),
                    l3_mb=int(d.get('l3_mb') or 0), igpu=bool(d.get('igpu')), tdp_w=int(d.get('tdp_w') or 0),
                    fallback_rank=999, passmark_ref=int(d.get('passmark_ref') or 0), business=bool(d.get('business')),
                    manufacturer=str(d.get('manufacturer') or ''), socket=str(d.get('socket') or ''),
                    memory_types=tuple(d.get('memory_types') or ()), source=str(d.get('source') or 'BuildCores OpenDB')
                ))
            except Exception:
                continue
    except Exception:
        pass
    _external_cache = out
    return out


def reload_external_catalog():
    global _external_cache
    _external_cache = None
    return _load_external()


def all_cpus():
    # Built-in records win when an upstream record with the same marketing name exists,
    # because the bundled QX-relevant values have been reviewed against our tender logic.
    merged = {c.model.lower(): c for c in _load_external()}
    for c in BUILTIN_CPUS:
        merged[c.model.lower()] = c
    return list(merged.values())


# Backward-compatible name used by a few old imports/tests.
CPUS = BUILTIN_CPUS


def catalog_stats():
    rows = all_cpus()
    return {
        'total': len(rows),
        'intel': sum(1 for c in rows if c.manufacturer.lower() == 'intel'),
        'amd': sum(1 for c in rows if c.manufacturer.lower() == 'amd'),
        'qx_intel': sum(1 for c in rows if c.platform == 'intel'),
        'qx_amd': sum(1 for c in rows if c.platform == 'amd'),
        'external': len(_load_external()),
    }


def _explicit_match(model: str):
    low = (model or '').lower().replace('®','').replace('™','').replace(' oem','').strip()
    if not low:
        return None
    rows = all_cpus()
    # Exact marketing-name match first. This is essential for suffixes such as
    # 12600 / 12600K / 12600KF, otherwise a substring match can pick the wrong CPU.
    for cpu in rows:
        if cpu.model.lower() == low:
            return cpu
    # Then accept wrapped names such as "Процессор Intel Core i5-12600K BOX".
    candidates = [cpu for cpu in rows if cpu.model.lower() in low or low in cpu.model.lower()]
    if candidates:
        return max(candidates, key=lambda c: len(c.model))
    return None


def cpu_satisfies(cpu: CPU, req, platform: str) -> bool:
    if cpu.platform != platform:
        return False
    if req.cpu_cores_min and (not cpu.cores or cpu.cores < req.cpu_cores_min):
        return False
    if req.cpu_threads_min and (not cpu.threads or cpu.threads < req.cpu_threads_min):
        return False
    if req.cpu_freq_ghz_min and (not cpu.base_ghz or cpu.base_ghz < req.cpu_freq_ghz_min):
        return False
    if req.cpu_freq_max_ghz_min and (not cpu.boost_ghz or cpu.boost_ghz < req.cpu_freq_max_ghz_min):
        return False
    if req.cpu_l3_mb_min and (not cpu.l3_mb or cpu.l3_mb < req.cpu_l3_mb_min):
        return False
    if req.cpu_tdp_w_max and (not cpu.tdp_w or cpu.tdp_w > req.cpu_tdp_w_max):
        return False
    need_igpu = bool(req.need_integrated_graphics or not req.need_gpu)
    if need_igpu and not cpu.igpu:
        return False
    pm = int(getattr(req, 'cpu_passmark_min', 0) or 0)
    if pm and (not cpu.passmark_ref or cpu.passmark_ref < pm):
        return False
    return True


def _score_cpu(cpu: CPU, req):
    """Sort by the smallest technical overkill, not by generation/marketing tier.

    Price is deliberately not guessed. The specialist sees every passing CPU and can
    choose the actually cheaper one. This makes exact-fit CPUs such as i5-12600K appear
    ahead of an unnecessarily large i7/i9 when both satisfy a tender.
    """
    constrained = any([
        req.cpu_cores_min, req.cpu_threads_min, req.cpu_freq_ghz_min,
        req.cpu_freq_max_ghz_min, req.cpu_l3_mb_min, req.cpu_tdp_w_max,
        getattr(req, 'cpu_passmark_min', 0), req.need_integrated_graphics,
    ])
    if not constrained:
        return (cpu.fallback_rank, cpu.tdp_w or 9999, cpu.model)
    score = 0.0
    if req.cpu_cores_min: score += max(0, cpu.cores - req.cpu_cores_min) * 100
    if req.cpu_threads_min: score += max(0, cpu.threads - req.cpu_threads_min) * 25
    if req.cpu_freq_ghz_min: score += max(0, cpu.base_ghz - req.cpu_freq_ghz_min) * 20
    if req.cpu_freq_max_ghz_min: score += max(0, cpu.boost_ghz - req.cpu_freq_max_ghz_min) * 8
    if req.cpu_l3_mb_min: score += max(0, cpu.l3_mb - req.cpu_l3_mb_min) * 2
    # Lower power is a mild tie-breaker only; exact CPU requirements dominate.
    score += (cpu.tdp_w or 999) / 1000.0
    return (score, 0 if cpu.business else 1, cpu.cores, cpu.threads, cpu.tdp_w or 9999, cpu.model)


def compatible_cpus(req, platform: str):
    if req.cpu_model:
        explicit = _explicit_match(req.cpu_model)
        if explicit:
            return [explicit] if cpu_satisfies(explicit, replace(req, cpu_model=None), platform) else []
        return []
    items = [cpu for cpu in all_cpus() if cpu_satisfies(cpu, req, platform)]
    return sorted(items, key=lambda c: _score_cpu(c, req))


def compatible_cpus_ignoring_selected(req, platform: str):
    return compatible_cpus(replace(req, cpu_model=None), platform)


def fallback_cpu(req, platform: str) -> str:
    if req.cpu_model:
        return req.cpu_model
    items = compatible_cpus(req, platform)
    if items:
        return items[0].model
    return 'Процессор по ТЗ — выбрать вручную'


def cpu_details(models):
    wanted = set(models or [])
    return [cpu.to_dict() for cpu in all_cpus() if cpu.model in wanted]


def cpu_by_model(model: str):
    return _explicit_match(model)
