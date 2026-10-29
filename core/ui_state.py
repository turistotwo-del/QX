from __future__ import annotations

CALC_STAGES = (
    '📥 ТЗ и требования',
    '🧩 Сборка и цены',
    '✅ Проверка заявки',
    '📋 Арсенал',
    '📤 Документы',
)

DEFAULT_STAGE = CALC_STAGES[0]
BUILD_STAGE = CALC_STAGES[1]


def normalize_calc_stage(value, default: str = DEFAULT_STAGE) -> str:
    """Return a valid calculation workspace stage; never leak a stale/unknown widget value."""
    text = str(value or '').strip()
    if text in CALC_STAGES:
        return text
    return default if default in CALC_STAGES else DEFAULT_STAGE


def make_focus_return_state(*, main_nav=None, stage=None, sidebar_open=None, sidebar_width=None) -> dict:
    """Pure snapshot used when entering the full-screen component editor."""
    out = {
        'main_nav': str(main_nav or '🧮 Расчёт'),
        'calc_workspace_stage': normalize_calc_stage(stage, BUILD_STAGE),
    }
    if sidebar_open is not None:
        out['sidebar_open'] = bool(sidebar_open)
    if sidebar_width is not None:
        try:
            out['sidebar_width'] = max(260, min(460, int(sidebar_width)))
        except Exception:
            pass
    return out


def merge_ui_state_for_handoff(ui_state: dict | None, focus_return_state: dict | None) -> dict:
    """Keep full-screen return destination across native-theme handoffs."""
    out = dict(ui_state or {})
    if focus_return_state:
        out['focus_return_state'] = make_focus_return_state(
            main_nav=focus_return_state.get('main_nav'),
            stage=focus_return_state.get('calc_workspace_stage'),
            sidebar_open=focus_return_state.get('sidebar_open'),
            sidebar_width=focus_return_state.get('sidebar_width'),
        )
    return out
