import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import date, datetime
import json, hashlib, os, base64, re, webbrowser
from pathlib import Path
from PIL import Image

from core.tz_parser import parse_tz, Requirements
from core.selector import build_plan, resolve_platform
from core.registry import find_registry_record
from core.storage import load_prices, save_prices, load_settings, save_settings
from core.defaults import QX_SPECS, CASE_SPECS, AIO_SPECS
from core.exporter import export_xlsx
from core.ktru import fetch_reference, official_url
from core.project_calc import build_arsenal_text, exit_points, money, normalize_arsenal_os_name, arsenal_equipment_default
from core.currency import get_usd_rate, parse_price_input, buffered_rate
from core.project_io import dump_project, load_project, validate_quantities
from core.cpu_catalog import cpu_details, catalog_stats, reload_external_catalog, all_cpus
from core.tender_fill import extract_characteristics_docx, build_characteristic_rows, fill_docx_characteristics
from core.cpu_catalog_update import update_from_buildcores
from core.commercial_offer import build_offer_items, build_commercial_offer, next_sequence, reserve_sequence, outgoing_number
from core.native_files import save_bytes_dialog
from core.user_catalog import (
    list_items as catalog_list_items, get_item as catalog_get_item, save_item as catalog_save_item,
    delete_item as catalog_delete_item, catalog_path, portable_catalog_path, catalog_status, export_catalog_bytes, import_catalog_bytes
)
from core.price_import import (
    parse_supplier_price_excel, compare_price_lists, save_supplier_price_list, get_supplier_price_list,
    list_supplier_price_lists, update_all_linked_profiles, apply_latest_prices_to_profile,
    apply_latest_price_to_case, apply_latest_price_to_aio, apply_latest_price_to_peripheral, lookup_price
)
from core.autosave import save_autosave, load_autosave, autosave_info, delete_autosave
from core.theme_handoff import save_handoff as save_theme_handoff, load_handoff as load_theme_handoff
from core.ui_state import CALC_STAGES, DEFAULT_STAGE, BUILD_STAGE, normalize_calc_stage, make_focus_return_state, merge_ui_state_for_handoff

_ICON_PATH = Path(__file__).resolve().parent / 'assets' / 'qx_icon.png'
_PAGE_ICON = Image.open(_ICON_PATH) if _ICON_PATH.exists() else '🖥️'
st.set_page_config(page_title='QX Подборщик 2.9.5', page_icon=_PAGE_ICON, layout='wide', initial_sidebar_state='expanded')

# Native Streamlit theme is selected before the server starts by desktop_launcher.py.
# That is required for DataEditor/FileUploader/Selectbox; CSS-only recoloring creates a broken hybrid theme.
if 'settings' not in st.session_state:
    st.session_state.settings = load_settings()
_UI_THEME = str(os.environ.get('QX_FORCED_THEME') or st.session_state.settings.get('ui_theme') or 'dark').strip().lower()
if _UI_THEME not in ('dark','light'):
    _UI_THEME = 'dark'

_ROOT = Path(__file__).resolve().parent
_THEME_RESTART_FLAG = _ROOT / 'QX_UserData' / 'theme_restart.flag'
_THEME_HANDOFF_FILE = _ROOT / 'QX_UserData' / 'theme_handoff.json'


def _write_streamlit_theme_config(theme: str):
    """Persist the real Streamlit theme for browser launches and the next desktop server."""
    theme = 'light' if str(theme).lower() == 'light' else 'dark'
    if theme == 'light':
        colors = {
            'base':'light','primary':'#ff5a4f','bg':'#f4f7fb','secondary':'#ffffff','text':'#172033','border':'#d9e1ec'
        }
    else:
        colors = {
            'base':'dark','primary':'#ff5a4f','bg':'#0c1017','secondary':'#121824','text':'#f4f7fb','border':'#263244'
        }
    cfg = (
        '[server]\nheadless = true\nfileWatcherType = "none"\n\n'
        '[browser]\ngatherUsageStats = false\n\n'
        '[client]\ntoolbarMode = "minimal"\n\n'
        '[theme]\n'
        f'base = "{colors["base"]}"\n'
        f'primaryColor = "{colors["primary"]}"\n'
        f'backgroundColor = "{colors["bg"]}"\n'
        f'secondaryBackgroundColor = "{colors["secondary"]}"\n'
        f'textColor = "{colors["text"]}"\n'
    )
    try:
        cfg_path = _ROOT / '.streamlit' / 'config.toml'
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(cfg, encoding='utf-8')
    except Exception:
        pass


def _handoff_project_meta():
    """Snapshot live project-level controls before moving to the other themed backend."""
    meta = dict(st.session_state.get('project_meta') or {})
    meta.update({
        'delivery': float(st.session_state.get('project_delivery', meta.get('delivery', 0)) or 0),
        'bg': float(st.session_state.get('project_bg', meta.get('bg', 0)) or 0),
        'go': float(st.session_state.get('project_go', meta.get('go', 0)) or 0),
        'project_qty': int(st.session_state.get('ars_qty', meta.get('project_qty', 1)) or 1),
        'sender': str(st.session_state.get('ars_sender', meta.get('sender', st.session_state.settings.get('default_sender','ЗИОН')))),
        'country': str(st.session_state.get('ars_country', meta.get('country', st.session_state.settings.get('default_country','Россия')))),
        'os_name': str(st.session_state.get('ars_os', meta.get('os_name', 'нет'))),
        'trademark': str(st.session_state.get('ars_tm', meta.get('trademark', st.session_state.settings.get('default_trademark','1093786')))),
        'kp_markup_pct': float(st.session_state.get('kp_markup_pct', meta.get('kp_markup_pct', float(st.session_state.settings.get('default_markup',0.2))*100)) or 0),
        'kp_mode': str(st.session_state.get('kp_mode', meta.get('kp_mode','markup'))),
        'kp_warranty': int(st.session_state.get('kp_warranty', meta.get('kp_warranty',12)) or 12),
        'kp_validity': int(st.session_state.get('kp_validity', meta.get('kp_validity',30)) or 30),
    })
    eq_count = int(st.session_state.get('ars_eq_count', len(meta.get('equipment') or []) or 1) or 1)
    equipment = []
    for j in range(max(1, eq_count)):
        eq = str(st.session_state.get(f'ars_eq_{j}', '') or '')
        rn = str(st.session_state.get(f'ars_reg_{j}', '') or '')
        if eq or rn:
            equipment.append({'equipment': eq, 'registry_number': rn})
    if equipment:
        meta['equipment'] = equipment
    return meta


def _write_theme_handoff(theme: str):
    """Persist all calculation state so native theme switching cannot destroy the current work."""
    project_bytes = dump_project(
        reqs=st.session_state.get('reqs') or [], plans=st.session_state.get('plans') or [],
        source_text=st.session_state.get('source_text') or '', qx_prices=st.session_state.get('qx_prices') or {},
        project_meta=_handoff_project_meta(), settings_snapshot=st.session_state.get('settings') or {},
        source_filename=st.session_state.get('source_filename') or '',
        source_docx_bytes=st.session_state.get('source_docx_bytes'),
        tender_overrides=st.session_state.get('tender_overrides') or {},
        tender_characteristics=st.session_state.get('tender_characteristics') or [],
    )
    ui_state = {
        'main_nav': st.session_state.get('main_nav', '🧮 Расчёт'),
        'calc_workspace_stage': normalize_calc_stage(st.session_state.get('calc_workspace_stage'), DEFAULT_STAGE),
        'sidebar_open': bool(st.session_state.get('sidebar_open', True)),
        'sidebar_width': int(st.session_state.get('sidebar_width', 320) or 320),
        'focus_calc_idx': st.session_state.get('_focus_calc_idx'),
    }
    ui_state = merge_ui_state_for_handoff(ui_state, st.session_state.get('_focus_return_state'))
    save_theme_handoff(_THEME_HANDOFF_FILE, target_theme=theme, project_bytes=project_bytes, ui_state=ui_state)


def _request_theme_restart(theme: str):
    # Browser mode still needs config.toml for the next browser start. Desktop mode uses
    # two pre-warmed native-theme backends and switches between them without a server restart.
    _write_streamlit_theme_config(theme)
    if os.environ.get('QX_DESKTOP') == '1':
        try:
            _write_theme_handoff(theme)
            _THEME_RESTART_FLAG.parent.mkdir(parents=True, exist_ok=True)
            _THEME_RESTART_FLAG.write_text(json.dumps({'theme': theme, 'requested_at': datetime.now().isoformat()}), encoding='utf-8')
        except Exception as exc:
            st.warning(f'Тема сохранена, но переключение не удалось: {exc}. Текущий расчёт не потерян.')
            return
        st.toast('Переключаю тему…')
    else:
        st.warning('Тема сохранена. В браузерном режиме перезапусти RUN_BROWSER.bat, чтобы нативные таблицы и поля тоже сменили тему.')


if _UI_THEME == 'light':
    _PAL = dict(
        bg='#f4f7fb', panel='#ffffff', panel2='#f8fafc', border='#d9e1ec', muted='#65758b',
        text='#172033', soft='#eef3f9', sidebar1='#ffffff', sidebar2='#f7f9fc', nav='rgba(255,255,255,.96)',
        shadow='rgba(25,45,75,.09)', header='rgba(255,255,255,.88)', accent='#ff5a4f',
        input_bg='#ffffff', input_text='#111827', input_border='#5f7085', input_placeholder='#7b8798',
        input_disabled='#66758a', input_focus='#ff5a4f', scheme='light'
    )
else:
    _PAL = dict(
        bg='#0c1017', panel='#121824', panel2='#0f1620', border='#263244', muted='#91a0b5',
        text='#f4f7fb', soft='#182230', sidebar1='#111722', sidebar2='#0e131c', nav='rgba(15,22,32,.96)',
        shadow='rgba(0,0,0,.18)', header='rgba(12,16,23,.86)', accent='#ff5a4f',
        input_bg='#151e2b', input_text='#f8fafc', input_border='#7890ad', input_placeholder='#8492a6',
        input_disabled='#aab4c3', input_focus='#ff5a4f', scheme='dark'
    )

st.markdown(f'''<style>
:root{{--qx-accent:{_PAL['accent']};--qx-bg:{_PAL['bg']};--qx-panel:{_PAL['panel']};--qx-panel2:{_PAL['panel2']};--qx-border:{_PAL['border']};--qx-muted:{_PAL['muted']};--qx-text:{_PAL['text']};--qx-soft:{_PAL['soft']};--qx-nav:{_PAL['nav']};--qx-shadow:{_PAL['shadow']};--qx-input-bg:{_PAL['input_bg']};--qx-input-text:{_PAL['input_text']};--qx-input-border:{_PAL['input_border']};--qx-input-placeholder:{_PAL['input_placeholder']};--qx-input-disabled:{_PAL['input_disabled']};--qx-input-focus:{_PAL['input_focus']};color-scheme:{_PAL['scheme']};}}
html,body,[data-testid="stAppViewContainer"]{{background:var(--qx-bg)!important;}}
.block-container{{max-width:1480px;padding-top:3.35rem!important;padding-bottom:4rem!important;}}
header[data-testid="stHeader"]{{display:flex!important;background:{_PAL['header']}!important;backdrop-filter:blur(10px);height:2.65rem!important;border-bottom:1px solid var(--qx-border)!important;z-index:1000!important;}}
[data-testid="stToolbar"]{{display:none!important}}#MainMenu{{visibility:hidden!important}}footer{{visibility:hidden!important}}
[data-testid="stSidebarCollapseButton"],[data-testid="stSidebarCollapsedControl"],[data-testid="stSidebarResizeHandle"]{{display:none!important}}
section[data-testid="stSidebar"]{{background:linear-gradient(180deg,{_PAL['sidebar1']} 0%,{_PAL['sidebar2']} 100%)!important;border-right:1px solid var(--qx-border)!important;transform:none!important;visibility:visible!important;opacity:1!important;left:0!important;}}
section[data-testid="stSidebar"]>div{{padding-top:.45rem}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label{{padding:.36rem .55rem;border-radius:10px;margin:.05rem 0}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){{background:var(--qx-soft)!important;border:1px solid var(--qx-border)!important}}
section[data-testid="stSidebar"] .stMarkdown,section[data-testid="stSidebar"] p,section[data-testid="stSidebar"] label{{color:var(--qx-text)!important}}
[data-testid="stMetric"]{{background:var(--qx-panel)!important;border:1px solid var(--qx-border)!important;padding:14px 16px;border-radius:14px;box-shadow:0 4px 18px var(--qx-shadow)}}
[data-testid="stExpander"]{{border:1px solid var(--qx-border)!important;border-radius:13px!important;background:var(--qx-panel)!important}}
[data-testid="stDataFrame"],[data-testid="stDataEditor"]{{border-radius:12px;overflow:hidden;border:1px solid var(--qx-border)!important;box-shadow:0 7px 24px var(--qx-shadow)}}
.stButton>button,.stDownloadButton>button{{border-radius:10px!important;min-height:2.45rem}}
.stButton>button[kind="primary"]{{background:var(--qx-accent)!important;border-color:var(--qx-accent)!important;color:#fff!important}}
.qx-card{{background:var(--qx-panel)!important;border:1px solid var(--qx-border);border-radius:15px;padding:17px;margin:8px 0 16px;box-shadow:0 5px 24px var(--qx-shadow);color:var(--qx-text)!important}}
.qx-muted{{color:var(--qx-muted)!important;font-size:.92rem}}.qx-tag{{display:inline-block;border:1px solid var(--qx-border);border-radius:999px;padding:4px 9px;margin:2px 4px 2px 0;font-size:.82rem}}
.qx-title-wrap{{padding:.15rem 0 .1rem;overflow:visible!important}}.qx-title{{font-size:1.9rem;font-weight:780;letter-spacing:-.035em;line-height:1.3!important;min-height:2.6rem;margin:0;display:flex;align-items:center;gap:.55rem;color:var(--qx-text)!important}}.qx-app-icon{{width:36px;height:36px;border-radius:9px;box-shadow:0 2px 10px var(--qx-shadow)}}
.qx-currency{{position:sticky;top:.5rem;z-index:900;background:var(--qx-nav)!important;backdrop-filter:blur(12px);border:1px solid var(--qx-border);border-radius:12px;padding:9px 13px;margin:7px 0 14px;box-shadow:0 5px 18px var(--qx-shadow);color:var(--qx-text)!important}}
.qx-side-title{{font-size:1.05rem;font-weight:750;margin:.1rem 0 .1rem;color:var(--qx-text)!important}}.qx-side-muted{{font-size:.78rem;color:var(--qx-muted)!important}}.qx-rate{{background:var(--qx-panel2)!important;border:1px solid var(--qx-border);border-radius:12px;padding:10px 12px;margin:.7rem 0}}.qx-rate-big{{font-size:1.15rem;font-weight:760;color:var(--qx-text)!important}}.qx-section{{font-size:.72rem;color:var(--qx-muted)!important;text-transform:uppercase;letter-spacing:.09em;font-weight:700;margin:1rem 0 .35rem}}
/* Workspace switcher. Native Streamlit supplies the real light/dark palette for widgets. */
div[data-baseweb="tab-list"]{{position:sticky;top:2.9rem;z-index:850;gap:.38rem;padding:.38rem;border:1px solid var(--qx-border);border-radius:14px;background:var(--qx-nav)!important;backdrop-filter:blur(12px);box-shadow:0 8px 28px var(--qx-shadow);margin:.35rem 0 1rem}}
button[data-baseweb="tab"]{{height:2.55rem;padding:0 .95rem!important;border-radius:10px!important;border:0!important;color:var(--qx-muted)!important;font-weight:650}}
button[data-baseweb="tab"][aria-selected="true"]{{background:var(--qx-soft)!important;color:var(--qx-text)!important}}
.qx-workbench{{border:1px solid var(--qx-border);border-radius:16px;background:var(--qx-panel)!important;padding:13px 15px;margin:.35rem 0 .85rem;box-shadow:0 10px 34px var(--qx-shadow);color:var(--qx-text)!important}}
.qx-workbench-title{{font-size:1rem;font-weight:750;margin-bottom:.2rem;color:var(--qx-text)!important}}.qx-workbench-sub{{font-size:.82rem;color:var(--qx-muted)!important}}
.qx-focusbar{{position:sticky;top:0;z-index:2000;border:1px solid var(--qx-border);background:var(--qx-nav)!important;backdrop-filter:blur(12px);border-radius:14px;padding:.55rem .7rem;margin:0 0 .65rem;color:var(--qx-text)!important}}
.qx-pill{{display:inline-flex;align-items:center;gap:.32rem;border:1px solid var(--qx-border);background:var(--qx-panel);border-radius:999px;padding:.25rem .6rem;font-size:.78rem;color:var(--qx-muted);margin:.08rem .18rem .08rem 0}}
main [data-testid="stRadio"] div[role="radiogroup"]{{gap:.35rem;flex-wrap:wrap;background:var(--qx-panel)!important;border:1px solid var(--qx-border);border-radius:14px;padding:.36rem .42rem;margin:.25rem 0 .85rem;box-shadow:0 7px 24px var(--qx-shadow)}}
main [data-testid="stRadio"] div[role="radiogroup"] label{{border:1px solid transparent;border-radius:10px;padding:.38rem .62rem;transition:.12s ease;color:var(--qx-text)!important}}
main [data-testid="stRadio"] div[role="radiogroup"] label p{{color:var(--qx-text)!important}}
main [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked){{background:var(--qx-soft)!important;border-color:var(--qx-border);font-weight:700}}
[data-testid="stWidgetLabel"] p,[data-testid="stMarkdownContainer"] p{{opacity:1}}
/* v2.9.3: explicit form-control palette. Chromium/WebView can otherwise keep native dark
   input text transparent/near-background until focus even when Streamlit theme is correct. */
html,body,[data-testid="stAppViewContainer"]{{color-scheme:{_PAL['scheme']}!important;}}
[data-baseweb="input"],[data-baseweb="base-input"],[data-baseweb="textarea"]{{background-color:var(--qx-input-bg)!important;border-color:var(--qx-input-border)!important;color:var(--qx-input-text)!important;}}
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,[data-testid="stTextArea"] textarea,[data-testid="stDateInput"] input,[data-testid="stTimeInput"] input,[data-baseweb="input"] input,[data-baseweb="base-input"] input,[data-baseweb="textarea"] textarea{{color:var(--qx-input-text)!important;-webkit-text-fill-color:var(--qx-input-text)!important;caret-color:var(--qx-input-text)!important;opacity:1!important;}}
[data-testid="stTextInput"] input::placeholder,[data-testid="stNumberInput"] input::placeholder,[data-testid="stTextArea"] textarea::placeholder,[data-baseweb="input"] input::placeholder,[data-baseweb="textarea"] textarea::placeholder{{color:var(--qx-input-placeholder)!important;-webkit-text-fill-color:var(--qx-input-placeholder)!important;opacity:1!important;}}
[data-testid="stTextInput"] input:disabled,[data-testid="stNumberInput"] input:disabled,[data-testid="stTextArea"] textarea:disabled,[data-baseweb="input"] input:disabled{{color:var(--qx-input-disabled)!important;-webkit-text-fill-color:var(--qx-input-disabled)!important;opacity:1!important;}}
[data-testid="stNumberInput"] button{{color:var(--qx-input-text)!important;background:var(--qx-input-bg)!important;border-color:var(--qx-input-border)!important;}}
[data-testid="stNumberInput"] button svg,[data-testid="stNumberInput"] button svg path{{fill:currentColor!important;color:var(--qx-input-text)!important;}}
[data-baseweb="select"]>div{{background-color:var(--qx-input-bg)!important;border-color:var(--qx-input-border)!important;color:var(--qx-input-text)!important;}}
[data-baseweb="select"] [role="combobox"],[data-baseweb="select"] [role="combobox"] *{{color:var(--qx-input-text)!important;-webkit-text-fill-color:var(--qx-input-text)!important;opacity:1!important;}}
[data-baseweb="select"] svg,[data-baseweb="select"] svg path{{fill:currentColor!important;color:var(--qx-input-text)!important;}}
/* BaseWeb wraps displayed select values in dynamically named divs. Color the whole value tree,
   not only the combobox node, otherwise Chromium can render the value nearly black until focus. */
[data-baseweb="select"]>div *{{color:var(--qx-input-text)!important;-webkit-text-fill-color:var(--qx-input-text)!important;opacity:1!important;}}
[data-baseweb="popover"],[data-baseweb="menu"],ul[role="listbox"]{{background:var(--qx-input-bg)!important;color:var(--qx-input-text)!important;}}
[data-baseweb="popover"] [role="option"],[data-baseweb="menu"] [role="option"],ul[role="listbox"] [role="option"]{{color:var(--qx-input-text)!important;-webkit-text-fill-color:var(--qx-input-text)!important;background:var(--qx-input-bg)!important;}}
[data-baseweb="popover"] [role="option"]:hover,[data-baseweb="popover"] [aria-selected="true"],ul[role="listbox"] [role="option"]:hover{{background:var(--qx-soft)!important;}}
[data-testid="stNumberInput"] [data-baseweb="input"],[data-testid="stTextInput"] [data-baseweb="input"],[data-testid="stTextArea"] [data-baseweb="textarea"]{{background:var(--qx-input-bg)!important;}}
/* v2.9.5: controls must look like controls even when they are not focused.
   BaseWeb often sets border-style:none, so border-color alone is not visible. */
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stNumberInput"] [data-baseweb="input"],
[data-testid="stDateInput"] [data-baseweb="input"],
[data-testid="stTimeInput"] [data-baseweb="input"],
[data-testid="stTextArea"] [data-baseweb="textarea"],
[data-testid="stSelectbox"] [data-baseweb="select"]>div,
[data-testid="stMultiSelect"] [data-baseweb="select"]>div,
[data-baseweb="select"]>div{{
  border:1px solid var(--qx-input-border)!important;
  outline:1px solid var(--qx-input-border)!important;
  outline-offset:-1px!important;
  border-radius:9px!important;
  background:var(--qx-input-bg)!important;
  box-shadow:0 1px 2px var(--qx-shadow)!important;
}}
[data-testid="stTextInput"] [data-baseweb="input"]:hover,
[data-testid="stNumberInput"] [data-baseweb="input"]:hover,
[data-testid="stTextArea"] [data-baseweb="textarea"]:hover,
[data-baseweb="select"]>div:hover{{border-color:var(--qx-text)!important;outline-color:var(--qx-text)!important;}}
[data-testid="stNumberInput"] input:not(:focus),[data-testid="stTextInput"] input:not(:focus),[data-testid="stTextArea"] textarea:not(:focus){{color:var(--qx-input-text)!important;-webkit-text-fill-color:var(--qx-input-text)!important;}}
[data-baseweb="input"]:focus-within,[data-baseweb="base-input"]:focus-within,[data-baseweb="textarea"]:focus-within,[data-baseweb="select"]>div:focus-within{{border-color:var(--qx-input-focus)!important;box-shadow:0 0 0 1px var(--qx-input-focus)!important;}}
/* v2.9.5: paint the border on the actual editable surface too.
   Some Chromium/WebView builds suppress BaseWeb wrapper borders until focus. */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input,
[data-testid="stTimeInput"] input,
[data-testid="stTextArea"] textarea{{
  background:var(--qx-input-bg)!important;
  color:var(--qx-input-text)!important;
  border:1.5px solid var(--qx-input-border)!important;
  border-radius:8px!important;
  box-shadow:inset 0 0 0 .5px var(--qx-input-border)!important;
  opacity:1!important;
}}
[data-testid="stSelectbox"] [role="combobox"],
[data-testid="stMultiSelect"] [role="combobox"]{{
  background:var(--qx-input-bg)!important;
  color:var(--qx-input-text)!important;
  border:1.5px solid var(--qx-input-border)!important;
  border-radius:8px!important;
  box-shadow:inset 0 0 0 .5px var(--qx-input-border)!important;
}}
[data-testid="stNumberInput"] button{{
  border:1px solid var(--qx-input-border)!important;
  background:var(--qx-panel2)!important;
}}
[data-testid="stTextInput"] input:hover,[data-testid="stNumberInput"] input:hover,[data-testid="stTextArea"] textarea:hover,[data-testid="stSelectbox"] [role="combobox"]:hover{{
  border-color:var(--qx-text)!important;
  box-shadow:inset 0 0 0 .5px var(--qx-text)!important;
}}
[data-testid="stTextInput"] input:focus,[data-testid="stNumberInput"] input:focus,[data-testid="stTextArea"] textarea:focus,[data-testid="stSelectbox"] [role="combobox"]:focus{{
  border-color:var(--qx-input-focus)!important;
  box-shadow:0 0 0 2px rgba(255,90,79,.24)!important;
  outline:none!important;
}}
/* Keep native table/editor cells readable in both themes; do not recolor the canvas itself. */
[data-testid="stDataFrame"],[data-testid="stDataEditor"]{{color:var(--qx-text)!important;background:var(--qx-panel)!important;}}
/* v2.9.5: fullscreen is handled by explicit visible buttons and table-only focus mode. */
</style>''', unsafe_allow_html=True)

for key, value in [('qx_prices',load_prices()),('settings',load_settings()),('reqs',[]),('plans',[]),('source_text',''),('source_filename',''),('source_docx_bytes',None),('tender_characteristics',[]),('tender_overrides',{}),('plan_revision',0),('project_meta',{})]:
    if key not in st.session_state: st.session_state[key] = value


# A theme switch opens a fresh browser session on the already-warm backend of the other
# native theme. Restore the exact project/UI snapshot before any widgets are instantiated.
if os.environ.get('QX_DESKTOP') == '1' and not st.session_state.get('_theme_handoff_checked'):
    st.session_state['_theme_handoff_checked'] = True
    try:
        _handoff = load_theme_handoff(_THEME_HANDOFF_FILE, current_theme=_UI_THEME, max_age_seconds=300, consume=True)
        if _handoff and _handoff.get('project_bytes'):
            _obj = load_project(_handoff['project_bytes'])
            st.session_state.reqs = _obj.get('reqs') or []
            st.session_state.plans = _obj.get('plans') or []
            st.session_state.source_text = _obj.get('source_text') or ''
            st.session_state.source_filename = _obj.get('source_filename') or ''
            st.session_state.source_docx_bytes = _obj.get('source_docx_bytes')
            st.session_state.tender_characteristics = _obj.get('tender_characteristics') or []
            st.session_state.tender_overrides = _obj.get('tender_overrides') or {}
            if _obj.get('qx_prices'):
                st.session_state.qx_prices = _obj.get('qx_prices')
            st.session_state.project_meta = _obj.get('project_meta') or {}
            st.session_state.plan_revision = int(st.session_state.get('plan_revision',0)) + 1
            _meta = st.session_state.project_meta
            for _k,_v in {
                'project_delivery':_meta.get('delivery',st.session_state.settings.get('default_delivery',0)),
                'project_bg':_meta.get('bg',st.session_state.settings.get('default_bg',0)),
                'project_go':_meta.get('go',st.session_state.settings.get('default_go',0)),
                'ars_qty':_meta.get('project_qty',1),
                'ars_sender':_meta.get('sender',st.session_state.settings.get('default_sender','ЗИОН')),
                'ars_country':_meta.get('country',st.session_state.settings.get('default_country','Россия')),
                'ars_os':_meta.get('os_name','нет'),
                'ars_tm':_meta.get('trademark',st.session_state.settings.get('default_trademark','1093786')),
                'ars_eq_count':max(1,len(_meta.get('equipment') or [])),
                'kp_markup_pct':_meta.get('kp_markup_pct',float(st.session_state.settings.get('default_markup',0.2))*100),
                'kp_mode':_meta.get('kp_mode','markup'),
                'kp_warranty':_meta.get('kp_warranty',12),
                'kp_validity':_meta.get('kp_validity',30),
            }.items():
                st.session_state[_k] = _v
            for _j,_item in enumerate(_meta.get('equipment') or []):
                st.session_state[f'ars_eq_{_j}'] = _item.get('equipment','')
                st.session_state[f'ars_reg_{_j}'] = str(_item.get('registry_number',''))
            _ui = dict(_handoff.get('ui_state') or {})
            if _ui.get('main_nav'):
                st.session_state['main_nav'] = _ui.get('main_nav')
            if _ui.get('calc_workspace_stage'):
                st.session_state['calc_workspace_stage'] = normalize_calc_stage(_ui.get('calc_workspace_stage'), DEFAULT_STAGE)
            if 'sidebar_open' in _ui:
                st.session_state['sidebar_open'] = bool(_ui.get('sidebar_open'))
            if _ui.get('sidebar_width'):
                st.session_state['sidebar_width'] = int(_ui.get('sidebar_width'))
            if _ui.get('focus_calc_idx') is not None:
                st.session_state['_focus_calc_idx'] = int(_ui.get('focus_calc_idx'))
            if isinstance(_ui.get('focus_return_state'), dict):
                _fr = _ui.get('focus_return_state') or {}
                st.session_state['_focus_return_state'] = make_focus_return_state(
                    main_nav=_fr.get('main_nav'), stage=_fr.get('calc_workspace_stage'),
                    sidebar_open=_fr.get('sidebar_open'), sidebar_width=_fr.get('sidebar_width')
                )
            st.session_state['_theme_handoff_restored'] = True
    except Exception as _handoff_exc:
        st.session_state['_theme_handoff_error'] = str(_handoff_exc)

# Apply full-screen return state before any widget-backed sidebar/stage keys are instantiated.
# This avoids StreamlitWidgetAlreadyInstantiatedError and guarantees that the visual tab and
# the rendered content point to the same workspace after leaving focus mode.
_focus_restore_pending = st.session_state.pop('_focus_restore_pending', None)
if isinstance(_focus_restore_pending, dict):
    st.session_state['main_nav'] = str(_focus_restore_pending.get('main_nav') or '🧮 Расчёт')
    st.session_state['_calc_workspace_stage_pending'] = normalize_calc_stage(
        _focus_restore_pending.get('calc_workspace_stage'), BUILD_STAGE
    )
    if 'sidebar_open' in _focus_restore_pending:
        st.session_state['sidebar_open'] = bool(_focus_restore_pending.get('sidebar_open'))
    if _focus_restore_pending.get('sidebar_width') is not None:
        try:
            st.session_state['sidebar_width'] = max(260, min(460, int(_focus_restore_pending.get('sidebar_width'))))
        except Exception:
            pass

# App-controlled sidebar: never disappear completely, never depend on browser collapse state.
if 'sidebar_open' not in st.session_state:
    st.session_state.sidebar_open = True
if 'sidebar_width' not in st.session_state:
    try:
        st.session_state.sidebar_width = int(st.session_state.settings.get('sidebar_width', 320) or 320)
    except Exception:
        st.session_state.sidebar_width = 320
st.session_state.sidebar_width = max(260, min(460, int(st.session_state.sidebar_width)))
_sidebar_px = st.session_state.sidebar_width if st.session_state.sidebar_open else 58
_sidebar_pad = '.80rem .75rem' if st.session_state.sidebar_open else '.45rem .28rem'
st.markdown(f'''
<style>
section[data-testid="stSidebar"]{{width:{_sidebar_px}px!important;min-width:{_sidebar_px}px!important;max-width:{_sidebar_px}px!important;flex:0 0 {_sidebar_px}px!important;}}
section[data-testid="stSidebar"] [data-testid="stSidebarContent"]{{width:{_sidebar_px}px!important;min-width:{_sidebar_px}px!important;max-width:{_sidebar_px}px!important;padding:{_sidebar_pad}!important;overflow-x:hidden!important;}}
</style>
''', unsafe_allow_html=True)

if '_catalog_status' not in st.session_state:
    try:
        st.session_state['_catalog_status'] = catalog_status()
    except Exception as _catalog_exc:
        st.session_state['_catalog_status'] = {'portable_ok': False, 'error': str(_catalog_exc)}

_icon_html = ''
if _ICON_PATH.exists():
    try:
        _icon_html = '<img class="qx-app-icon" src="data:image/png;base64,' + base64.b64encode(_ICON_PATH.read_bytes()).decode('ascii') + '">'
    except Exception:
        _icon_html = ''
st.markdown(f'<div class="qx-title-wrap"><div class="qx-title">{_icon_html}<span>QX Подборщик</span><span style="font-size:1rem;color:#93a4b8;font-weight:600">v2.9.5 Portable</span></div></div>', unsafe_allow_html=True)
st.markdown('<div class="qx-muted">ТЗ/КТРУ → подбор совместимой сборки → фактические характеристики заявки → ручные цены ₽/$ → реестр → точки выхода → Арсенал → коммерческое предложение → нативное сохранение файлов → бекап проекта</div>', unsafe_allow_html=True)
if st.session_state.pop('_theme_handoff_restored', False):
    st.toast('Тема переключена. ТЗ, распознавание, расчёт и текущий рабочий этап восстановлены.')
if st.session_state.get('_theme_handoff_error'):
    st.warning('Не удалось восстановить состояние после переключения темы: '+str(st.session_state.pop('_theme_handoff_error')))

@st.cache_data(ttl=3600, show_spinner=False)
def _usd_rate_cached(cached_rate, cached_date):
    return get_usd_rate(cached_rate, cached_date).to_dict()

usd_info = _usd_rate_cached(float(st.session_state.settings.get('usd_rate_cached',86.8872)), str(st.session_state.settings.get('usd_rate_date_cached','04.09.2026')))
if usd_info.get('live'):
    changed = (abs(float(st.session_state.settings.get('usd_rate_cached',0))-float(usd_info['rate'])) > 1e-9 or str(st.session_state.settings.get('usd_rate_date_cached','')) != str(usd_info.get('date','')))
    if changed:
        st.session_state.settings['usd_rate_cached']=float(usd_info['rate'])
        st.session_state.settings['usd_rate_date_cached']=str(usd_info.get('date',''))
        save_settings(st.session_state.settings)
rate_with_buffer = buffered_rate(float(usd_info['rate']), float(st.session_state.settings.get('usd_buffer_rub',5)))
rate_status = 'ЦБ РФ' if usd_info.get('live') else 'кэш ЦБ РФ'
st.markdown(f'<div class="qx-currency"><b>USD:</b> {float(usd_info["rate"]):.4f} ₽ · для расчёта: <b>{rate_with_buffer:.4f} ₽/$</b> (+{float(st.session_state.settings.get("usd_buffer_rub",5)):g} ₽ запас) · {rate_status}, {usd_info.get("date","")}</div>', unsafe_allow_html=True)

_NAV_ITEMS = [
    '🧮 Расчёт',
    '💵 Цены и прайсы',
    '🗄️ База корпусов',
    '🖥️ Моноблочные платформы',
    '🖵 База мониторов',
    '⌨️ База клавиатур',
    '🖱️ База мышей',
    '🧩 База оборудования',
    '📋 Реестр',
    '📚 КТРУ',
    '🧠 Справочники',
    '⚙️ Настройки',
]
# Custom hide/show control: hidden mode is a 58px rail, so reveal is always reachable.
if not st.session_state.sidebar_open:
    if st.sidebar.button('→', key='sidebar_show', use_container_width=True, help='Показать левую панель'):
        st.session_state.sidebar_open = True
        st.rerun()
    _nav = st.session_state.get('main_nav') or _NAV_ITEMS[0]
else:
    _top_hide, _top_title = st.sidebar.columns([1,4])
    if _top_hide.button('←', key='sidebar_hide', use_container_width=True, help='Скрыть левую панель'):
        st.session_state.sidebar_open = False
        st.rerun()
    _top_title.markdown(f'<div class="qx-side-title">QX Подборщик</div><div class="qx-side-muted">v2.9.5 Portable</div>', unsafe_allow_html=True)
    st.sidebar.markdown(
        f'<div class="qx-rate"><div class="qx-side-muted">USD · {rate_status} · {usd_info.get("date","")}</div>'
        f'<div class="qx-rate-big">{float(usd_info["rate"]):.4f} ₽</div>'
        f'<div class="qx-side-muted">В расчёте: {rate_with_buffer:.4f} ₽/$ · запас +{float(st.session_state.settings.get("usd_buffer_rub",5)):g} ₽</div></div>',
        unsafe_allow_html=True
    )
    with st.sidebar.expander('Интерфейс', expanded=False):
        _theme_label = st.radio('Тема', ['🌙 Тёмная','☀️ Светлая'], horizontal=True,
            index=0 if _UI_THEME == 'dark' else 1, key='ui_theme_selector')
        _theme_value = 'dark' if _theme_label.startswith('🌙') else 'light'
        if str(st.session_state.settings.get('ui_theme') or 'dark') != _theme_value:
            st.session_state.settings['ui_theme'] = _theme_value
            save_settings(st.session_state.settings)
            _request_theme_restart(_theme_value)
            if os.environ.get('QX_DESKTOP') == '1':
                st.sidebar.info('Переключаю тему без сброса расчёта…')
                st.stop()
            st.rerun()
        _new_sidebar_width = st.slider('Ширина панели, px', min_value=260, max_value=460, step=10, key='sidebar_width')
        if int(st.session_state.settings.get('sidebar_width', 0) or 0) != int(_new_sidebar_width):
            st.session_state.settings['sidebar_width'] = int(_new_sidebar_width)
            save_settings(st.session_state.settings)
        st.caption('Тема и ширина сохраняются между запусками.')
    st.sidebar.markdown('<div class="qx-section">Навигация</div>', unsafe_allow_html=True)
    _nav = st.sidebar.radio('Раздел', _NAV_ITEMS, key='main_nav', label_visibility='collapsed')
    st.sidebar.markdown('<div class="qx-section">Быстрые действия</div>', unsafe_allow_html=True)
    if st.sidebar.button('🌐 Открыть DNS', use_container_width=True, key='sidebar_dns'):
        try:
            webbrowser.open_new_tab('https://www.dns-shop.ru/')
            st.toast('DNS открыт в браузере.')
        except Exception as _exc:
            st.warning(f'Не удалось открыть браузер автоматически: {_exc}')
    if st.session_state.get('source_filename'):
        st.sidebar.caption('ТЗ: ' + str(st.session_state.get('source_filename')))
    if st.session_state.get('plans'):
        st.sidebar.caption(f'Позиций в расчёте: {len(st.session_state.get("plans") or [])}')



def _reset_current_calculation():
    """Start a fresh calculation while preserving the user's price DB and settings."""
    try:
        delete_autosave()
    except Exception:
        pass
    keep = {
        'qx_prices': st.session_state.get('qx_prices', load_prices()),
        'settings': st.session_state.get('settings', load_settings()),
    }
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state.qx_prices = keep['qx_prices']
    st.session_state.settings = keep['settings']



def _last_save_dir():
    value = str(st.session_state.settings.get('last_save_dir') or '').strip()
    return value if value and Path(value).exists() else None


def _save_native(data, default_filename, *, title, filetypes):
    try:
        path = save_bytes_dialog(
            data, default_filename, title=title, filetypes=filetypes, initial_dir=_last_save_dir()
        )
        if path:
            st.session_state.settings['last_save_dir'] = str(Path(path).parent)
            save_settings(st.session_state.settings)
            st.success(f'Сохранено: {path}')
        return path
    except Exception as exc:
        st.error(f'Не удалось открыть окно «Сохранить как»: {exc}')
        return None


def _save_controls(data, default_filename, *, label, key, title, filetypes, mime):
    """Primary native Save As plus a compact browser-download fallback."""
    left, right = st.columns([5, 1])
    if left.button(label, key=f'native_save_{key}', use_container_width=True):
        _save_native(data, default_filename, title=title, filetypes=filetypes)
    right.download_button(
        '↓ Резерв', data=data, file_name=default_filename, mime=mime,
        key=f'browser_download_{key}', use_container_width=True,
        help='Резервное скачивание через встроенный web-интерфейс. Обычно используй кнопку «Сохранить как…» слева.'
    )


def _price_context():
    rate = float(usd_info.get('rate') or st.session_state.settings.get('usd_rate_cached', 86.8872))
    buffer_rub = float(st.session_state.settings.get('usd_buffer_rub', 5))
    return rate, buffer_rub


def _price_input_default(data, input_key='price_input', price_key='price'):
    """Keep the user's original $/RUB text when it exists; support old numeric DB records."""
    raw = (data or {}).get(input_key)
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    try:
        value = float((data or {}).get(price_key) or 0)
    except Exception:
        value = 0.0
    return '' if value <= 0 else f'{value:g}'


def _parse_catalog_price(raw):
    rate, buffer_rub = _price_context()
    rub, currency, note = parse_price_input(raw, rate, buffer_rub)
    return float(rub), currency, note


def _clear_arsenal_auto_fields():
    """Drop only auto-filled Arsenal equipment fields so a fresh plan can repopulate them."""
    for key in list(st.session_state.keys()):
        if key.startswith('ars_eq_') or key.startswith('ars_reg_'):
            del st.session_state[key]
    st.session_state.pop('_ars_auto_token', None)


def _restore_project_object(obj):
    """Restore a manual backup or an autosave into session state."""
    st.session_state.reqs=obj.get('reqs') or []
    st.session_state.plans=obj.get('plans') or []
    st.session_state.source_text=obj.get('source_text') or ''
    st.session_state.source_filename=obj.get('source_filename') or ''
    st.session_state.source_docx_bytes=obj.get('source_docx_bytes')
    st.session_state.tender_characteristics=obj.get('tender_characteristics') or []
    st.session_state.tender_overrides=obj.get('tender_overrides') or {}
    if st.session_state.source_docx_bytes and not st.session_state.tender_characteristics:
        st.session_state.tender_characteristics=extract_characteristics_docx(st.session_state.source_docx_bytes)
    if obj.get('qx_prices'):
        st.session_state.qx_prices=obj['qx_prices']
    st.session_state.project_meta=obj.get('project_meta') or {}
    st.session_state.pop('kp_bytes',None); st.session_state.pop('kp_filename',None)
    st.session_state.plan_revision += 1
    meta=st.session_state.project_meta
    for key,val in {
        'project_delivery':meta.get('delivery',st.session_state.settings.get('default_delivery',0)),
        'project_bg':meta.get('bg',st.session_state.settings.get('default_bg',0)),
        'project_go':meta.get('go',st.session_state.settings.get('default_go',0)),
        'ars_qty':meta.get('project_qty',1),
        'ars_sender':meta.get('sender',st.session_state.settings.get('default_sender','ЗИОН')),
        'ars_country':meta.get('country',st.session_state.settings.get('default_country','Россия')),
        'ars_os':meta.get('os_name','нет'),
        'ars_tm':meta.get('trademark',st.session_state.settings.get('default_trademark','1093786')),
        'ars_eq_count':max(1,len(meta.get('equipment') or [])),
        'kp_markup_pct':meta.get('kp_markup_pct',float(st.session_state.settings.get('default_markup',0.2))*100),
        'kp_mode':meta.get('kp_mode','markup'),
        'kp_warranty':meta.get('kp_warranty',12),
        'kp_validity':meta.get('kp_validity',30),
    }.items():
        st.session_state[key]=val
    for j,item in enumerate(meta.get('equipment') or []):
        st.session_state[f'ars_eq_{j}']=item.get('equipment','')
        st.session_state[f'ars_reg_{j}']=str(item.get('registry_number',''))


def _component_explanation(row, req):
    """Human-readable explanation of why a BOM row exists."""
    row = dict(row or {})
    req = dict(req or {})
    cat = str(row.get('category') or 'Компонент')
    name = str(row.get('name') or '')
    c = dict(row.get('constraints') or {})
    bits = []
    if row.get('note'):
        bits.append(str(row.get('note')))
    kind = str(c.get('kind') or '').lower()
    if kind == 'cpu':
        needs=[]
        for key,label in [('cpu_cores_min','ядер'),('cpu_threads_min','потоков')]:
            if req.get(key): needs.append(f"≥ {req[key]} {label}")
        if req.get('cpu_freq_ghz_min'): needs.append(f"база ≥ {req['cpu_freq_ghz_min']} ГГц")
        if req.get('cpu_freq_max_ghz_min'): needs.append(f"макс. ≥ {req['cpu_freq_max_ghz_min']} ГГц")
        if req.get('cpu_l3_mb_min'): needs.append(f"L3 ≥ {req['cpu_l3_mb_min']} МБ")
        if req.get('need_integrated_graphics'): needs.append('нужна встроенная графика')
        if needs: bits.append('Требования ТЗ к CPU: ' + ', '.join(needs) + '.')
    elif kind == 'ram':
        if req.get('ram_gb_min'): bits.append(f"ТЗ требует ОЗУ ≥ {req['ram_gb_min']} ГБ; выбрано {name}.")
        if c.get('ram_type'): bits.append(f"Тип памяти привязан к плате: {c.get('ram_type')}.")
    elif kind == 'ssd':
        if req.get('ssd_gb_min'): bits.append(f"ТЗ требует SSD ≥ {req['ssd_gb_min']} ГБ; выбран ближайший допустимый объём не ниже требования.")
        if c.get('interface'): bits.append(f"Интерфейс из ТЗ: {c.get('interface')}.")
        if c.get('form_factor'): bits.append(f"Форм-фактор из ТЗ: {c.get('form_factor')}.")
    elif kind == 'hdd':
        if req.get('hdd_gb_min'): bits.append(f"ТЗ требует HDD ≥ {req['hdd_gb_min']} ГБ; выбрано {name}.")
    elif kind == 'motherboard':
        if c.get('custom_profile'):
            bits.append(f"Плата взята из выбранной базы «{c.get('profile') or row.get('source')}», а не из QX.")
        else:
            bits.append('Плата выбрана из стандартной базы QX под рассчитанную платформу и требования ТЗ.')
    elif kind == 'm2_key_e_adapter':
        bits.append('Штатный переходник QX для AMD добавляется всегда: на A520 нет собственного M.2 Key E, поэтому переходник даёт одно подключение Key E для Wi‑Fi. Цена по умолчанию 0 ₽, но её можно изменить в ценах QX или прямо в расчёте.')
    elif kind == 'case':
        bits.append('Корпус участвует в проверке размеров, отсеков и передних портов из ТЗ.')
    elif kind in ('psu','integrated_psu'):
        if req.get('psu_w_min'): bits.append(f"ТЗ требует БП ≥ {req['psu_w_min']} Вт.")
        elif c.get('min_w'): bits.append(f"Мощность выбрана по конфигурации: {c.get('min_w')} Вт.")
    elif kind == 'profile_component':
        cond = str(c.get('condition') or 'always')
        bits.append(f"Компонент из пользовательской базы; правило добавления: {cond}.")
        if c.get('supplier_sku'): bits.append(f"Связка с прайсом: {c.get('supplier') or 'поставщик'} / {c.get('supplier_sku')}.")
    elif kind == 'port_inventory':
        bits.append('Это техническая строка: она суммирует подтверждённые USB-порты выбранной платы, корпуса/платформы и модулей.')
    if row.get('registry'):
        bits.append('Позиция отмечена как реестровая в выбранной схеме комплектации.')
    if not bits:
        bits.append(f'Позиция «{cat}» добавлена алгоритмом под распознанные требования ТЗ; при необходимости её можно заменить вручную.')
    return bits


def _plan_registry_messages(plan):
    """Offline registry-number sanity check. Does not claim to verify the government registry online."""
    plan = dict(plan or {})
    req = dict(plan.get('req') or {})
    product_type = str(req.get('product_type') or '')
    assembled = product_type in ('system','aio24','aio27','aws24','aws27')
    errors=[]; warnings=[]
    reg = dict(plan.get('registry') or {}) if plan.get('registry') else {}
    if assembled:
        rn = str(reg.get('registry_number') or '').strip()
        if not rn:
            errors.append('У готового изделия не указан реестровый номер.')
        elif not re.fullmatch(r'\d{5,}', rn):
            warnings.append(f'Реестровый номер готового изделия «{rn}» имеет необычный формат — проверь вручную.')
    for row in plan.get('rows') or []:
        if not row.get('registry'):
            continue
        if str(row.get('source') or '') == 'QX':
            continue  # QX component registry composition is encoded in the built-in recipe.
        c=dict(row.get('constraints') or {})
        rn=str(c.get('registry_number') or '').strip()
        if not rn:
            warnings.append(f"Компонент «{row.get('name') or row.get('category')}» отмечен реестровым, но его реестровый номер не заполнен.")
    return errors, warnings


def _autosave_current(project_bytes, fingerprint_payload):
    try:
        fp=hashlib.sha256(json.dumps(fingerprint_payload,ensure_ascii=False,sort_keys=True,default=str).encode('utf-8')).hexdigest()
        if st.session_state.get('_autosave_fingerprint') != fp:
            result=save_autosave(project_bytes)
            st.session_state['_autosave_fingerprint']=fp
            st.session_state['_autosave_last_at']=datetime.now().strftime('%H:%M:%S')
            st.session_state['_autosave_last_ok']=bool(result.get('local') or result.get('portable'))
    except Exception as exc:
        st.session_state['_autosave_last_ok']=False
        st.session_state['_autosave_error']=str(exc)


_CASE_CATALOG_FIELDS = [
    'custom_case_name','custom_case_price','custom_case_price_input','custom_case_price_conversion','custom_case_width_mm','custom_case_length_mm','custom_case_height_mm',
    'custom_case_bay_525','custom_case_bay_25','custom_case_bay_325','custom_case_bay_35','custom_case_bay_35_external','custom_case_front_audio_out','custom_case_front_mic_in','custom_case_usb2_front',
    'custom_case_gen1_a_front','custom_case_gen1_c_front','custom_case_gen2_a_front','custom_case_gen2_c_front',
    'custom_case_protected','custom_case_supplier','custom_case_supplier_sku','custom_case_supplier_price_usd','custom_case_supplier_price_mode','custom_case_supplier_price_date','custom_case_supplier_name',
]
_AIO_CATALOG_FIELDS = [
    'custom_aio_name','custom_aio_price','custom_aio_price_input','custom_aio_price_conversion',
    'custom_aio_supplier','custom_aio_supplier_sku','custom_aio_supplier_price_usd','custom_aio_supplier_price_mode','custom_aio_supplier_price_date','custom_aio_supplier_name',
    'custom_aio_diagonal_in','custom_aio_resolution','custom_aio_refresh_hz',
    'custom_aio_matrix','custom_aio_built_in_cardreader','custom_aio_integrated_psu','custom_aio_psu_w',
    'custom_aio_usb2_a','custom_aio_gen1_a','custom_aio_gen1_c','custom_aio_gen2_a','custom_aio_gen2_c',
    'custom_aio_front_usb2','custom_aio_front_a','custom_aio_front_c',
]


def _catalog_payload(d, fields):
    return {k: d.get(k) for k in fields}


def _equipment_profile_for_req(reqd):
    """Load a saved profile and recalculate its USD prices using today's active rate."""
    name = str((reqd or {}).get('equipment_profile_name') or '').strip()
    if not name:
        return None
    rec = catalog_get_item('equipment_profile', name)
    if not rec:
        return None
    data = dict(rec.get('data') or {})
    data.setdefault('profile_name', rec.get('name') or name)

    boards = {}
    for platform, raw in dict(data.get('boards') or {}).items():
        board = dict(raw or {})
        price_raw = _price_input_default(board)
        rub, currency, note = _parse_catalog_price(price_raw)
        board['price_input'] = price_raw
        board['price'] = float(rub)
        board['price_currency'] = currency
        board['price_conversion'] = note
        boards[platform] = board
    data['boards'] = boards

    components = []
    for raw in list(data.get('components') or []):
        item = dict(raw or {})
        price_raw = _price_input_default(item)
        rub, currency, note = _parse_catalog_price(price_raw)
        item['price_input'] = price_raw
        item['price'] = float(rub)
        item['price_currency'] = currency
        item['price_conversion'] = note
        components.append(item)
    data['components'] = components
    return data



def _peripheral_catalogs_live():
    """Load reusable monitor/keyboard/mouse databases with prices recalculated now.

    The saved price text (for example $35) remains authoritative, so moving the portable
    database to another PC or changing the USD buffer does not freeze an old RUB amount.
    """
    result={}
    for kind in ('monitor','keyboard','mouse'):
        out=[]
        for rec in catalog_list_items(kind):
            data=dict(rec.get('data') or {})
            data.setdefault('name',rec.get('name') or '')
            # If the item is linked to an imported supplier price, use the newest saved
            # supplier price first, then convert the resulting $ value at the current rate.
            try:
                data,_=apply_latest_price_to_peripheral(data)
            except Exception:
                pass
            raw=_price_input_default(data,'price_input','price')
            rub,currency,note=_parse_catalog_price(raw)
            data['price_input']=raw; data['price']=float(rub); data['price_currency']=currency; data['price_conversion']=note
            out.append({'name':rec.get('name') or data.get('name'),'data':data})
        result[kind]=out
    return result


def _catalog_choice_widget(kind, current, key, label):
    names=[x['name'] for x in catalog_list_items(kind)]
    options=['Авто — подобрать по ТЗ']+names
    cur=current if current in names else 'Авто — подобрать по ТЗ'
    chosen=st.selectbox(label,options,index=options.index(cur),key=key,
                        on_change=lambda: st.session_state.__setitem__('_peripheral_catalog_changed',True),
                        help='Авто выбирает самую дешёвую сохранённую модель, которая подтверждённо проходит распознанные требования ТЗ. Если ни одна не проходит, программа не подставляет неподходящую модель.')
    return None if chosen=='Авто — подобрать по ТЗ' else chosen


def _keyboard_mouse_source_widget(kind, d, idx, standalone=False):
    """QX is the default and is never replaced by a saved model unless the user opts in."""
    is_keyboard = kind == 'keyboard'
    mode_key = 'keyboard_source_mode' if is_keyboard else 'mouse_source_mode'
    item_key = 'keyboard_catalog_item' if is_keyboard else 'mouse_catalog_item'
    label_word = 'клавиатуры' if is_keyboard else 'мыши'
    labels = {
        'qx':'QX — стандарт (по умолчанию)',
        'catalog':f'Выбрать из базы {label_word}',
        'manual':'Другая / вручную',
    }
    current = str(d.get(mode_key) or 'qx')
    if current not in labels:
        current = 'qx'
    key_prefix = f'{kind}_source_{idx}' + ('_standalone' if standalone else '')
    chosen_label = st.selectbox(
        f'Источник {label_word}', list(labels.values()), index=list(labels).index(current), key=key_prefix,
        on_change=lambda: st.session_state.__setitem__('_peripheral_catalog_changed', True),
        help='QX остаётся стандартом. Сохранённая база не заменяет QX автоматически — она используется только после явного выбора здесь.'
    )
    mode = next(k for k,v in labels.items() if v == chosen_label)
    d[mode_key] = mode
    if mode == 'catalog':
        d[item_key] = _catalog_choice_widget(kind, d.get(item_key), f'{kind}_db_{idx}' + ('_standalone' if standalone else ''), f'Модель из базы {label_word}')
        st.caption('База используется только потому, что ты сам переключил источник с QX.')
    elif mode == 'qx':
        d[item_key] = None
        st.caption('Используется стандарт QX. Наличие записей в пользовательской базе его не меняет.')
    else:
        d[item_key] = None
        st.caption('Будет оставлена ручная позиция — название и цену можно изменить в таблице расчёта.')
    return mode

def _set_widget_state_if_present(key, value):
    # Called before the corresponding widget is rendered in the current Streamlit pass.
    st.session_state[key] = value


def _apply_case_catalog(d, data, idx):
    for field in _CASE_CATALOG_FIELDS:
        if field in data:
            d[field] = data[field]
    widget_keys = {
        'custom_case_name':f'custom_case_name_{idx}', 'custom_case_price_input':f'custom_case_price_input_{idx}',
        'custom_case_width_mm':f'custom_case_width_mm_{idx}', 'custom_case_length_mm':f'custom_case_length_mm_{idx}',
        'custom_case_height_mm':f'custom_case_height_mm_{idx}', 'custom_case_protected':f'custom_case_protected_{idx}',
        'custom_case_bay_525':f'custom_case_bay525_{idx}', 'custom_case_bay_25':f'custom_case_bay25_{idx}',
        'custom_case_bay_325':f'custom_case_bay325_{idx}', 'custom_case_bay_35':f'custom_case_bay35_{idx}', 'custom_case_usb2_front':f'custom_case_usb2_{idx}',
        'custom_case_gen1_a_front':f'custom_case_g1a_{idx}', 'custom_case_gen1_c_front':f'custom_case_g1c_{idx}',
        'custom_case_gen2_a_front':f'custom_case_g2a_{idx}', 'custom_case_gen2_c_front':f'custom_case_g2c_{idx}',
        'custom_case_supplier':f'custom_case_supplier_{idx}', 'custom_case_supplier_sku':f'custom_case_supplier_sku_{idx}',
    }
    for field, key in widget_keys.items():
        value = d.get(field)
        if field in ('custom_case_width_mm','custom_case_length_mm','custom_case_height_mm'):
            value = int(value or 0)
        elif field == 'custom_case_price_input':
            value = str(value or _price_input_default(d, 'custom_case_price_input', 'custom_case_price'))
        elif field in ('custom_case_price','custom_case_price_conversion'):
            continue
        elif field.startswith('custom_case_bay_') or field.startswith('custom_case_usb') or field.startswith('custom_case_gen'):
            value = int(value or 0)
        elif field in ('custom_case_protected','custom_case_front_audio_out','custom_case_front_mic_in'):
            value = bool(value)
        else:
            value = str(value or '')
        _set_widget_state_if_present(key, value)


def _apply_aio_catalog(d, data, idx):
    for field in _AIO_CATALOG_FIELDS:
        if field in data:
            d[field] = data[field]
    widget_keys = {
        'custom_aio_name':f'caioname_{idx}', 'custom_aio_price_input':f'caiprice_{idx}',
        'custom_aio_supplier':f'caisupplier_{idx}', 'custom_aio_supplier_sku':f'caisku_{idx}',
        'custom_aio_diagonal_in':f'custom_aio_diagonal_in_{idx}', 'custom_aio_resolution':f'caires_{idx}',
        'custom_aio_refresh_hz':f'custom_aio_refresh_hz_{idx}', 'custom_aio_matrix':f'caimat_{idx}',
        'custom_aio_built_in_cardreader':f'caicard_{idx}', 'custom_aio_integrated_psu':f'caipsu_{idx}',
        'custom_aio_psu_w':f'custom_aio_psu_w_{idx}', 'custom_aio_usb2_a':f'custom_aio_usb2_a_{idx}',
        'custom_aio_gen1_a':f'custom_aio_gen1_a_{idx}', 'custom_aio_gen1_c':f'custom_aio_gen1_c_{idx}',
        'custom_aio_gen2_a':f'custom_aio_gen2_a_{idx}', 'custom_aio_gen2_c':f'custom_aio_gen2_c_{idx}',
        'custom_aio_front_usb2':f'custom_aio_front_usb2_{idx}', 'custom_aio_front_a':f'custom_aio_front_a_{idx}',
        'custom_aio_front_c':f'custom_aio_front_c_{idx}',
    }
    bool_fields = {'custom_aio_built_in_cardreader','custom_aio_integrated_psu'}
    text_fields = {'custom_aio_name','custom_aio_supplier','custom_aio_supplier_sku','custom_aio_resolution','custom_aio_matrix'}
    for field, key in widget_keys.items():
        value = d.get(field)
        if field in bool_fields:
            value = bool(value)
        elif field in text_fields:
            value = str(value or '')
        elif field == 'custom_aio_price_input':
            value = str(value or _price_input_default(d, 'custom_aio_price_input', 'custom_aio_price'))
        elif field == 'custom_aio_diagonal_in':
            value = float(value or 0)
        else:
            value = int(value or 0)
        _set_widget_state_if_present(key, value)


TYPE_LABELS = {
    'system':'Системный блок','aio24':'Моноблок 23.8"','aio27':'Моноблок 27"','aws24':'АРМ 23.8"','aws27':'АРМ 27"',
    'monitor':'Монитор','keyboard':'Клавиатура','mouse':'Мышь'
}


EDITOR_COLS = ['category','name','qty','price_input','price','source','note','registry']


def _sync_component_editor(plan_idx, editor_key):
    """Apply editor deltas immediately; price accepts RUB or USD text."""
    state = st.session_state.get(editor_key) or {}
    if plan_idx >= len(st.session_state.plans):
        return
    rows = st.session_state.plans[plan_idx].get('rows', [])
    usd_rate = float(usd_info.get('rate') or st.session_state.settings.get('usd_rate_cached', 86.8872))
    buffer_rub = float(st.session_state.settings.get('usd_buffer_rub', 5))
    for raw_idx, changes in (state.get('edited_rows') or {}).items():
        try: idx = int(raw_idx)
        except Exception: continue
        if not (0 <= idx < len(rows)): continue
        overrides = dict(rows[idx].get('_user_overrides') or {})
        for col, value in changes.items():
            if col not in EDITOR_COLS: continue
            if col == 'qty':
                try: value = float(value or 0)
                except Exception: value = 0.0
            if col == 'registry': value = bool(value)
            if col == 'price':
                continue  # calculated field; manual input goes through price_input
            rows[idx][col] = value
            overrides[col] = True
        if 'price_input' in changes:
            raw = changes.get('price_input')
            rub, currency, note = parse_price_input(raw, usd_rate, buffer_rub)
            rows[idx]['price'] = float(rub)
            overrides['price'] = True
            overrides['price_conversion'] = True
            if rows[idx].get('source') not in ('QX','В составе баребона','В составе процессора','В составе QX','В составе платформы'):
                rows[idx]['source'] = 'Вручную $' if currency == 'USD' else 'Вручную ₽'
                overrides['source'] = True
            rows[idx]['price_conversion'] = note
        if overrides:
            rows[idx]['_user_overrides'] = overrides
    # Any component edit can change the commercial offer; never leave a stale DOCX download.
    st.session_state.pop('kp_bytes', None)
    st.session_state.pop('kp_filename', None)


def _append_manual_calc_row(plan_idx):
    if not (0 <= plan_idx < len(st.session_state.get('plans') or [])):
        return
    row = {
        'category':'Дополнительно', 'name':'Новая позиция', 'qty':1.0,
        'price_input':'', 'price':0.0, 'source':'Вручную', 'note':'', 'registry':False,
        'constraints':{'kind':'manual_added','manual_added':True},
        '_user_overrides':{'category':True,'name':True,'qty':True,'source':True,'note':True,'registry':True},
    }
    st.session_state.plans[plan_idx].setdefault('rows', []).append(row)
    st.session_state.plans[plan_idx]['editor_rev'] = int(st.session_state.plans[plan_idx].get('editor_rev',0)) + 1
    st.session_state.pop('kp_bytes', None); st.session_state.pop('kp_filename', None)


def _remove_last_manual_calc_row(plan_idx):
    if not (0 <= plan_idx < len(st.session_state.get('plans') or [])):
        return False
    rows = st.session_state.plans[plan_idx].get('rows', [])
    for j in range(len(rows)-1, -1, -1):
        c = dict((rows[j] or {}).get('constraints') or {})
        if c.get('manual_added') or str(c.get('kind') or '') == 'manual_added':
            rows.pop(j)
            st.session_state.plans[plan_idx]['editor_rev'] = int(st.session_state.plans[plan_idx].get('editor_rev',0)) + 1
            st.session_state.pop('kp_bytes', None); st.session_state.pop('kp_filename', None)
            return True
    return False


def _sync_qx_price_editor(editor_key, row_keys):
    state = st.session_state.get(editor_key) or {}
    for raw_idx, changes in (state.get('edited_rows') or {}).items():
        try:
            idx = int(raw_idx)
        except Exception:
            continue
        if not (0 <= idx < len(row_keys)):
            continue
        key = row_keys[idx]
        item = st.session_state.qx_prices.get(key)
        if not item:
            continue
        if 'name' in changes:
            item['name'] = str(changes['name'] or '')
        if 'price' in changes:
            try: item['price'] = float(changes['price'] or 0)
            except Exception: pass
    st.session_state.pop('kp_bytes', None)
    st.session_state.pop('kp_filename', None)


def num(col, label, d, key, integer=True, step=1.0):
    val = d.get(key)
    if integer:
        return col.number_input(label, min_value=0, value=int(val or 0), step=int(step), key=f'{key}_{d.get("_idx")}') or None
    return col.number_input(label, min_value=0.0, value=float(val or 0), step=float(step), key=f'{key}_{d.get("_idx")}') or None


def tri_bool(col, label, value, key):
    """Three-state editor for TZ booleans: unspecified / yes / no."""
    opts=[None, True, False]
    cur=value if value in (None, True, False) else None
    return col.selectbox(label, opts, index=opts.index(cur), key=key,
                         format_func=lambda x: 'не задано' if x is None else ('Да' if x else 'Нет'))


def req_editor(req_dict, idx):
    d = dict(req_dict); d['_idx']=idx
    title = d.get('title') or f'Позиция {idx+1}'
    with st.expander(f'{title} — распознано из ТЗ', expanded=True):
        c1,c2,c3,c4 = st.columns(4)
        d['title']=c1.text_input('Название',title,key=f'title_{idx}')
        d['quantity']=c2.number_input('Количество',min_value=0,value=int(d.get('quantity') or 0),step=1,key=f'qty_{idx}')
        d['ktru_code']=c3.text_input('КТРУ',d.get('ktru_code') or '',key=f'ktru_{idx}') or None
        opts=list(TYPE_LABELS); current=d.get('product_type','system')
        d['product_type']=c4.selectbox('Тип позиции',opts,index=opts.index(current) if current in opts else 0,format_func=lambda x:TYPE_LABELS[x],key=f'ptype_{idx}')

        if d['product_type'] in ('system','aio24','aio27','aws24','aws27'):
            saved_equipment_profiles = catalog_list_items('equipment_profile')
            saved_equipment_names = [x['name'] for x in saved_equipment_profiles]
            current_equipment = str(d.get('equipment_profile_name') or '')
            equipment_options = ['QX — стандартная база'] + saved_equipment_names
            current_equipment_label = current_equipment if current_equipment in saved_equipment_names else 'QX — стандартная база'
            selected_equipment = st.selectbox(
                'База комплектующих', equipment_options,
                index=equipment_options.index(current_equipment_label), key=f'equipment_profile_{idx}',
                on_change=lambda: st.session_state.__setitem__('_equipment_profile_changed', True),
                help='Можно выбрать QX или сохранённую пользовательскую базу, например «Бештау». Материнская плата и сохранённые реестровые компоненты с ценами будут подставляться автоматически. При переключении уже рассчитанный проект пересобирается автоматически.'
            )
            d['equipment_profile_name'] = None if selected_equipment == 'QX — стандартная база' else selected_equipment
            if d['equipment_profile_name']:
                st.caption(f'Используется сохранённая база «{d["equipment_profile_name"]}». Её состав и цены редактируются во вкладке «База оборудования».')
            if d['product_type'].startswith('aws'):
                d['monitor_catalog_item'] = _catalog_choice_widget('monitor', d.get('monitor_catalog_item'), f'aws_monitor_db_{idx}', 'Монитор АРМ из базы')

            a,b,c,e=st.columns(4)
            pv=d.get('platform') or 'авто'; popts=['авто','intel','amd']
            p=a.selectbox('Платформа',popts,index=popts.index(pv) if pv in popts else 0,key=f'platform_{idx}', on_change=lambda: st.session_state.__setitem__('_platform_changed', True), help='Ручной выбор AMD/Intel является жёстким: программа не переключит платформу сама, даже если стандартная QX-плата этой ветки не проходит отдельное требование. Несоответствие платы будет показано отдельно.'); d['platform']=None if p=='авто' else p
            d['cpu_cores_min']=num(b,'Ядер ≥',d,'cpu_cores_min')
            d['cpu_threads_min']=num(c,'Потоков ≥',d,'cpu_threads_min')
            d['ram_gb_min']=num(e,'ОЗУ, ГБ ≥',d,'ram_gb_min')
            a,b,c,e=st.columns(4)
            ro=d.get('ram_type') or 'авто'; rro=['авто','DDR4','DDR5']; rv=a.selectbox('Тип ОЗУ (точно)',rro,index=rro.index(ro) if ro in rro else 0,key=f'ramtype_{idx}'); d['ram_type']=None if rv=='авто' else rv
            min_gen=int(d.get('ram_type_min_generation') or 0); min_opts=['нет','DDR4 или новее','DDR5 или новее']; min_cur='DDR5 или новее' if min_gen>=5 else 'DDR4 или новее' if min_gen==4 else 'нет'; min_sel=b.selectbox('Минимум поколения ОЗУ',min_opts,index=min_opts.index(min_cur),key=f'ramtypemin_{idx}'); d['ram_type_min_generation']=5 if min_sel.startswith('DDR5') else 4 if min_sel.startswith('DDR4') else None
            d['ram_mhz_min']=num(c,'ОЗУ, МГц ≥',d,'ram_mhz_min')
            d['ssd_gb_min']=num(e,'SSD, ГБ ≥',d,'ssd_gb_min')
            a,b,c,e,f=st.columns(5)
            d['hdd_gb_min']=num(a,'HDD, ГБ ≥',d,'hdd_gb_min')
            si=b.selectbox('Интерфейс SSD',['не ограничен','SATA','NVMe'],index=['не ограничен','SATA','NVMe'].index(d.get('ssd_interface') or 'не ограничен') if (d.get('ssd_interface') or 'не ограничен') in ['не ограничен','SATA','NVMe'] else 0,key=f'ssdif_{idx}')
            d['ssd_interface']=None if si=='не ограничен' else si
            d['ssd_m2_required']=c.checkbox('SSD именно M.2',bool(d.get('ssd_m2_required')),key=f'ssdm2_{idx}')
            d['ssd_25_required']=e.checkbox('SSD именно 2,5″',bool(d.get('ssd_25_required')),key=f'ssd25_{idx}')
            d['extra_hdd_slot_required']=f.checkbox('Нужна возможность доп. HDD',bool(d.get('extra_hdd_slot_required')),key=f'exhdd_{idx}')
            a,b,c,e=st.columns(4)
            d['forbid_wireless']=a.checkbox('Беспроводная связь запрещена',bool(d.get('forbid_wireless')),key=f'nowifi_{idx}')
            d['external_psu_required']=b.checkbox('Требуется внешний БП',bool(d.get('external_psu_required')),key=f'extpsu_{idx}')
            d['warranty_months_min']=num(c,'Гарантия, мес. ≥',d,'warranty_months_min')
            e.caption('')
            a,b,c,e=st.columns(4)
            d['need_gpu']=a.checkbox('Дискретная GPU',bool(d.get('need_gpu')),key=f'gpu_{idx}')
            d['gpu_vram_gb_min']=num(b,'VRAM, ГБ ≥',d,'gpu_vram_gb_min')
            d['psu_w_min']=num(c,'БП, Вт ≥',d,'psu_w_min')
            d['need_integrated_graphics']=e.checkbox('Встроенная графика',bool(d.get('need_integrated_graphics')),key=f'igpu_{idx}')
            a,b,c,e=st.columns(4)
            d['need_wifi']=a.checkbox('Wi‑Fi',bool(d.get('need_wifi')),key=f'wifi_{idx}')
            d['need_bluetooth']=b.checkbox('Bluetooth',bool(d.get('need_bluetooth')),key=f'bt_{idx}')
            d['need_cardreader']=c.checkbox('Картридер',bool(d.get('need_cardreader')),key=f'card_{idx}')
            d['protected_case']=e.checkbox('ТЗ требует защищённый корпус',bool(d.get('protected_case')),key=f'prot_{idx}')

            if d['product_type'] in ('system','aws24','aws27'):
                with st.expander('Корпус системного блока', expanded=False):
                    case_modes = {
                        'auto':'Авто — подобрать QX по ТЗ',
                        'qx_standard':'QX ТИП 1',
                        'qx_protected':'QX ТИП 2 / защищённый',
                        'custom':'Другой корпус — характеристики вручную',
                    }
                    current_case_mode = str(d.get('system_case_mode') or 'auto')
                    if current_case_mode not in case_modes:
                        current_case_mode = 'auto'
                    chosen_case_label = st.selectbox(
                        'Какой корпус использовать', list(case_modes.values()),
                        index=list(case_modes).index(current_case_mode), key=f'case_mode_{idx}'
                    )
                    d['system_case_mode'] = next(k for k,v in case_modes.items() if v == chosen_case_label)
                    if d['system_case_mode'] == 'custom':
                        saved_cases = catalog_list_items('case')
                        saved_case_names = [x['name'] for x in saved_cases]
                        load_col, btn_col = st.columns([4,1])
                        selected_saved_case = load_col.selectbox(
                            'Сохранённые корпуса', ['— Новый / вручную —'] + saved_case_names,
                            key=f'case_saved_{idx}',
                            help='На этом ПК база хранится в профиле Windows, а рядом с программой автоматически поддерживается переносимая копия для другого компьютера.'
                        )
                        if btn_col.button('Загрузить', key=f'case_load_{idx}', use_container_width=True, disabled=selected_saved_case == '— Новый / вручную —'):
                            rec = catalog_get_item('case', selected_saved_case)
                            if rec:
                                _apply_case_catalog(d, rec.get('data') or {}, idx)
                                st.success(f'Корпус «{selected_saved_case}» загружен из локальной базы.')
                        st.caption(f'Основная база: {catalog_path()} · переносимая копия: {portable_catalog_path()}')

                        a,b,c,e = st.columns([3,1,1,1.4])
                        d['custom_case_name'] = a.text_input('Модель / название корпуса', d.get('custom_case_name') or 'Другой корпус', key=f'custom_case_name_{idx}') or 'Другой корпус'
                        _case_price_default = str(d.get('custom_case_price_input') or '').strip() or _price_input_default(d, 'custom_case_price_input', 'custom_case_price')
                        d['custom_case_price_input'] = b.text_input('Цена корпуса, ₽ / $', value=_case_price_default, placeholder='3500 или $35', key=f'custom_case_price_input_{idx}').strip()
                        d['custom_case_supplier'] = c.text_input('Поставщик', value=str(d.get('custom_case_supplier') or ''), placeholder='ExeGate', key=f'custom_case_supplier_{idx}').strip()
                        d['custom_case_supplier_sku'] = e.text_input('Артикул / P/N', value=str(d.get('custom_case_supplier_sku') or ''), placeholder='EX.... или код', key=f'custom_case_supplier_sku_{idx}').strip()
                        _case_rub, _case_currency, _case_note = _parse_catalog_price(d['custom_case_price_input'])
                        d['custom_case_price'] = _case_rub
                        d['custom_case_price_conversion'] = _case_note
                        if _case_currency == 'USD' and _case_note:
                            st.caption('Цена корпуса: ' + _case_note)
                        if d.get('custom_case_supplier') and d.get('custom_case_supplier_sku'):
                            _sp=get_supplier_price_list(d['custom_case_supplier'])
                            _si=lookup_price(_sp or {},d['custom_case_supplier_sku']) if _sp else None
                            if _si and _si.get('selected_price_usd') is not None:
                                st.caption(f"Прайс {d['custom_case_supplier']}: {d['custom_case_supplier_sku']} → ${float(_si['selected_price_usd']):g} ({_si.get('selected_price_mode','')}, {_sp.get('price_date','')}). При сохранении корпуса эта цена будет подставлена автоматически.")
                            elif _sp:
                                st.caption(f"В последнем прайсе «{d['custom_case_supplier']}» артикул {d['custom_case_supplier_sku']} не найден.")
                        st.caption('Впиши реальные характеристики корпуса. Они будут участвовать в проверке ТЗ и попадут в фактические характеристики. Программа ничего не додумывает.')
                        a,b,c,e = st.columns(4)
                        d['custom_case_width_mm'] = num(a,'Ширина, мм',d,'custom_case_width_mm')
                        d['custom_case_length_mm'] = num(b,'Длина, мм',d,'custom_case_length_mm')
                        d['custom_case_height_mm'] = num(c,'Высота, мм',d,'custom_case_height_mm')
                        d['custom_case_protected'] = e.checkbox('Защищённый / спецкорпус', bool(d.get('custom_case_protected')), key=f'custom_case_protected_{idx}')
                        a,b,c,e = st.columns(4)
                        d['custom_case_bay_525'] = int(a.number_input('Отсеки 5,25', min_value=0, value=int(d.get('custom_case_bay_525') or 0), step=1, key=f'custom_case_bay525_{idx}'))
                        d['custom_case_bay_25'] = int(b.number_input('Отсеки 2,5', min_value=0, value=int(d.get('custom_case_bay_25') or 0), step=1, key=f'custom_case_bay25_{idx}'))
                        d['custom_case_bay_325'] = int(c.number_input('Отсеки 3,25', min_value=0, value=int(d.get('custom_case_bay_325') or 0), step=1, key=f'custom_case_bay325_{idx}'))
                        d['custom_case_bay_35'] = int(e.number_input('Отсеки 3,5', min_value=0, value=int(d.get('custom_case_bay_35') or 0), step=1, key=f'custom_case_bay35_{idx}'))
                        a,b,c=st.columns(3)
                        d['custom_case_bay_35_external']=int(a.number_input('Внешние отсеки 3,5',min_value=0,value=int(d.get('custom_case_bay_35_external') or 0),step=1,key=f'custom_case_bay35ext_{idx}'))
                        d['custom_case_front_audio_out']=b.checkbox('Аудиовыход спереди',bool(d.get('custom_case_front_audio_out')),key=f'custom_case_audioout_{idx}')
                        d['custom_case_front_mic_in']=c.checkbox('Микрофонный вход спереди',bool(d.get('custom_case_front_mic_in')),key=f'custom_case_micin_{idx}')
                        st.markdown('**Передние порты самого корпуса**')
                        a,b,c,e,f = st.columns(5)
                        d['custom_case_usb2_front'] = int(a.number_input('USB2 A', min_value=0, value=int(d.get('custom_case_usb2_front') or 0), step=1, key=f'custom_case_usb2_{idx}'))
                        d['custom_case_gen1_a_front'] = int(b.number_input('Gen1 A', min_value=0, value=int(d.get('custom_case_gen1_a_front') or 0), step=1, key=f'custom_case_g1a_{idx}'))
                        d['custom_case_gen1_c_front'] = int(c.number_input('Gen1 C', min_value=0, value=int(d.get('custom_case_gen1_c_front') or 0), step=1, key=f'custom_case_g1c_{idx}'))
                        d['custom_case_gen2_a_front'] = int(e.number_input('Gen2 A', min_value=0, value=int(d.get('custom_case_gen2_a_front') or 0), step=1, key=f'custom_case_g2a_{idx}'))
                        d['custom_case_gen2_c_front'] = int(f.number_input('Gen2 C', min_value=0, value=int(d.get('custom_case_gen2_c_front') or 0), step=1, key=f'custom_case_g2c_{idx}'))
                        if st.button('💾 Сохранить / обновить корпус в локальной базе', key=f'case_save_{idx}', use_container_width=True):
                            case_name = str(d.get('custom_case_name') or '').strip()
                            if not case_name or case_name == 'Другой корпус':
                                st.error('Сначала укажи нормальное название/модель корпуса.')
                            else:
                                _case_payload=_catalog_payload(d, _CASE_CATALOG_FIELDS)
                                _case_payload,_case_price_stat=apply_latest_price_to_case(_case_payload)
                                if _case_price_stat.get('updated'):
                                    _rub,_cur,_note=_parse_catalog_price(_case_payload.get('custom_case_price_input'))
                                    _case_payload['custom_case_price']=float(_rub); _case_payload['custom_case_price_conversion']=_note
                                catalog_save_item('case', case_name, _case_payload)
                                _msg=f'Корпус «{case_name}» сохранён. Переносимая копия базы тоже обновлена.'
                                if _case_price_stat.get('updated'): _msg += ' Цена автоматически взята из последнего прайса поставщика.'
                                st.success(_msg)
                                for _miss in _case_price_stat.get('missing') or []: st.warning(_miss)
                    elif d['system_case_mode'] == 'qx_standard':
                        st.info('Будет принудительно использован QX ТИП 1. Если он не проходит ТЗ, программа покажет предупреждение, но не запретит расчёт.')
                    elif d['system_case_mode'] == 'qx_protected':
                        st.info('Будет принудительно использован QX ТИП 2 / защищённый. Если он не проходит ТЗ, программа покажет предупреждение, но не запретит расчёт.')
                    else:
                        st.caption('Авто: программа сравнит QX ТИП 1 и ТИП 2 и выберет подходящий вариант с минимальным техническим запасом.')
            with st.expander('Расширенные требования портов / корпуса / CPU'):
                a,b,c,e=st.columns(4)
                d['cpu_freq_ghz_min']=num(a,'CPU база, ГГц ≥',d,'cpu_freq_ghz_min',integer=False,step=.1)
                d['cpu_freq_max_ghz_min']=num(b,'CPU макс., ГГц ≥',d,'cpu_freq_max_ghz_min',integer=False,step=.1)
                d['cpu_l3_mb_min']=num(c,'L3, МБ ≥',d,'cpu_l3_mb_min')
                d['cpu_passmark_min']=num(e,'PassMark CPU ≥',d,'cpu_passmark_min')
                a,b,c,e=st.columns(4)
                d['m2_key_m_min']=num(a,'M.2 Key M ≥',d,'m2_key_m_min')
                d['m2_key_e_min']=num(b,'M.2 Key E ≥',d,'m2_key_e_min')
                d['ram_slots_min']=num(c,'Слотов ОЗУ ≥',d,'ram_slots_min')
                d['ssd_tbw_min']=num(e,'SSD TBW/TWD ≥',d,'ssd_tbw_min')
                a,b,c,e=st.columns(4)
                d['ram_max_supported_gb_min']=num(a,'Макс. поддерживаемая ОЗУ, ГБ ≥',d,'ram_max_supported_gb_min')
                d['usb2_total_min']=num(b,'USB 2.0 всего ≥',d,'usb2_total_min')
                d['usb3x_total_min']=num(c,'USB 3.x всего ≥',d,'usb3x_total_min')
                d['usb_a_rear_min']=num(e,'USB Type-A сзади ≥',d,'usb_a_rear_min')
                a,b,c,e=st.columns(4)
                d['usb3_gen1_type_a_total_min']=num(a,'USB Gen1 Type-A ≥',d,'usb3_gen1_type_a_total_min')
                d['usb3_gen1_type_c_total_min']=num(b,'USB Gen1 Type-C ≥',d,'usb3_gen1_type_c_total_min')
                d['usb3_gen2_type_a_total_min']=num(c,'USB Gen2 Type-A ≥',d,'usb3_gen2_type_a_total_min')
                d['usb3_gen2_type_c_total_min']=num(e,'USB Gen2 Type-C ≥',d,'usb3_gen2_type_c_total_min')
                a,b,c,e=st.columns(4)
                d['usb3_gen1_total_min']=num(a,'USB Gen1 всего ≥',d,'usb3_gen1_total_min')
                d['usb3_gen2_total_min']=num(b,'USB Gen2 всего ≥',d,'usb3_gen2_total_min')
                d['usb_c_total_min']=num(c,'USB Type-C всего ≥',d,'usb_c_total_min')
                d['usb2_front_min']=num(e,'USB 2.0 спереди ≥',d,'usb2_front_min')
                a,b,c,e=st.columns(4)
                d['usb3_gen1_front_min']=num(a,'USB Gen1 спереди ≥',d,'usb3_gen1_front_min')
                d['usb_a_front_min']=num(b,'USB Type-A спереди ≥',d,'usb_a_front_min')
                d['usb_c_front_min']=num(c,'USB Type-C спереди ≥',d,'usb_c_front_min')
                d['bay_525_min']=num(e,'Отсеки 5,25 ≥',d,'bay_525_min')
                a,b,c,e=st.columns(4)
                d['system_hdmi_min']=num(a,'HDMI выходов ≥',d,'system_hdmi_min')
                d['system_dp_min']=num(b,'DisplayPort выходов ≥',d,'system_dp_min')
                d['pcie_x1_min']=num(c,'PCI-E x1 ≥',d,'pcie_x1_min')
                d['pcie_x16_min']=num(e,'PCI-E x16 ≥',d,'pcie_x16_min')
                a,b,c,e=st.columns(4)
                d['system_vga_min']=num(a,'VGA выходов ≥',d,'system_vga_min')
                d['sata_ports_min']=num(b,'SATA ≥',d,'sata_ports_min')
                d['expansion_slots_min']=num(c,'Слотов расширения ≥',d,'expansion_slots_min')
                d['ram_modules_min']=num(e,'Модулей ОЗУ ≥',d,'ram_modules_min')
                a,b,c,e=st.columns(4)
                d['bay_35_min']=num(a,'Внутр. отсеки 3,5 ≥',d,'bay_35_min')
                d['bay_35_external_min']=num(b,'Внешн. отсеки 3,5 ≥',d,'bay_35_external_min')
                d['bay_25_min']=num(c,'Отсеки 2,5 ≥',d,'bay_25_min')
                d['raid_0_1_5_10_required']=e.checkbox('RAID 0/1/5/10',bool(d.get('raid_0_1_5_10_required')),key=f'raid_{idx}')
                a,b,c,e=st.columns(4)
                d['front_audio_out_required']=a.checkbox('Аудиовыход спереди',bool(d.get('front_audio_out_required')),key=f'faudioout_{idx}')
                d['front_mic_in_required']=b.checkbox('Микрофон спереди',bool(d.get('front_mic_in_required')),key=f'fmicin_{idx}')
                d['system_audio_out_required']=c.checkbox('Встроенный аудиовыход',bool(d.get('system_audio_out_required')),key=f'saudioout_{idx}')
                d['system_mic_in_required']=e.checkbox('Встроенный микрофонный вход',bool(d.get('system_mic_in_required')),key=f'smicin_{idx}')

                st.markdown('**Дополнительные планки портов (если ставишь сам)**')
                st.caption('Указывай только фактические порты установленной планки. Если все значения 0 — планка в сборку не добавляется. Передняя и задняя планки считаются отдельно; название/цену потом можно изменить в таблице сборки.')
                st.markdown('Передняя панель')
                a,b,c,e,f=st.columns(5)
                d['extra_front_usb2_a']=num(a,'USB2 A',d,'extra_front_usb2_a')
                d['extra_front_gen1_a']=num(b,'Gen1 A',d,'extra_front_gen1_a')
                d['extra_front_gen1_c']=num(c,'Gen1 C',d,'extra_front_gen1_c')
                d['extra_front_gen2_a']=num(e,'Gen2 A',d,'extra_front_gen2_a')
                d['extra_front_gen2_c']=num(f,'Gen2 C',d,'extra_front_gen2_c')
                st.markdown('Задняя панель')
                a,b,c,e,f=st.columns(5)
                d['extra_rear_usb2_a']=num(a,'USB2 A',d,'extra_rear_usb2_a')
                d['extra_rear_gen1_a']=num(b,'Gen1 A',d,'extra_rear_gen1_a')
                d['extra_rear_gen1_c']=num(c,'Gen1 C',d,'extra_rear_gen1_c')
                d['extra_rear_gen2_a']=num(e,'Gen2 A',d,'extra_rear_gen2_a')
                d['extra_rear_gen2_c']=num(f,'Gen2 C',d,'extra_rear_gen2_c')
            with st.expander('Клавиатура / мышь в комплекте', expanded=False):
                a,b,c,e=st.columns(4)
                d['need_keyboard']=a.checkbox('Клавиатура в комплекте',bool(d.get('need_keyboard')),key=f'needkb_{idx}')
                d['need_mouse']=b.checkbox('Мышь в комплекте',bool(d.get('need_mouse')),key=f'needms_{idx}')
                d['keyboard_wireless']=c.checkbox('Клавиатура беспроводная',bool(d.get('keyboard_wireless')),key=f'kbwl_{idx}')
                d['mouse_wireless']=e.checkbox('Мышь беспроводная',bool(d.get('mouse_wireless')),key=f'mswl_{idx}')
                kbc,msc=st.columns(2)
                with kbc:
                    _keyboard_mouse_source_widget('keyboard', d, idx, standalone=False)
                with msc:
                    _keyboard_mouse_source_widget('mouse', d, idx, standalone=False)
                a,b,c,e=st.columns(4)
                d['keyboard_keys_min']=num(a,'Клавиш ≥',d,'keyboard_keys_min')
                d['mouse_buttons_min']=num(b,'Кнопок мыши ≥',d,'mouse_buttons_min')
                d['keyboard_numeric_keypad']=c.checkbox('Цифровой блок',bool(d.get('keyboard_numeric_keypad')),key=f'kbnum_{idx}')
                d['keyboard_fullsize']=e.checkbox('Полноразмерная клавиатура',bool(d.get('keyboard_fullsize')),key=f'kbfull_{idx}')
                a,b=st.columns(2)
                d['mouse_optical']=a.checkbox('Мышь оптическая',bool(d.get('mouse_optical')),key=f'msopt_{idx}')
                d['keyboard_russification']=b.text_input('Русификация',d.get('keyboard_russification') or '',key=f'kbrus_{idx}') or None
            if d.get('manual_requirements'):
                st.info('Отдельно проверить по ТЗ:\n' + '\n'.join('• '+str(x) for x in d.get('manual_requirements') or []))
            if d['product_type'].startswith('aio'):
                with st.expander('Моноблочная платформа: QX или другая', expanded=False):
                    mode_now=d.get('aio_platform_mode') or 'qx'
                    mode_label='Стандартная QX' if mode_now != 'custom' else 'Другая платформа — характеристики вручную'
                    chosen=st.radio('Используемая платформа', ['Стандартная QX','Другая платформа — характеристики вручную'],
                                    index=0 if mode_label=='Стандартная QX' else 1, horizontal=True, key=f'aiomode_{idx}')
                    d['aio_platform_mode']='qx' if chosen=='Стандартная QX' else 'custom'
                    if d['aio_platform_mode']=='qx':
                        spec=AIO_SPECS.get(d['product_type'],{})
                        st.info(f"QX: {spec.get('diagonal_in','?')}″ · {str(spec.get('resolution','?')).replace('x','×')} · {spec.get('refresh_hz','?')} Гц · встроенный нерестровый картридер. Эти факты программа подставляет автоматически.")
                    else:
                        st.caption('Для другой платформы программа не переносит характеристики QX. Впиши реальные значения платформы; всё неизвестное останется «НУЖНО ЗАПОЛНИТЬ»/«НЕТ ДАННЫХ».')
                        saved_aio = catalog_list_items('aio')
                        saved_aio_names = [x['name'] for x in saved_aio]
                        load_col, btn_col = st.columns([4,1])
                        selected_saved_aio = load_col.selectbox(
                            'Сохранённые моноблочные платформы', ['— Новая / вручную —'] + saved_aio_names,
                            key=f'aio_saved_{idx}',
                            help='База общая для будущих версий на этом ПК; переносимая копия рядом с программой позволяет перенести её на другой компьютер.'
                        )
                        if btn_col.button('Загрузить', key=f'aio_load_{idx}', use_container_width=True, disabled=selected_saved_aio == '— Новая / вручную —'):
                            rec = catalog_get_item('aio', selected_saved_aio)
                            if rec:
                                _apply_aio_catalog(d, rec.get('data') or {}, idx)
                                st.success(f'Платформа «{selected_saved_aio}» загружена из локальной базы.')
                        st.caption(f'Основная база: {catalog_path()} · переносимая копия: {portable_catalog_path()}')

                        a,b,c,e=st.columns([3,1.2,1.2,1.5])
                        d['custom_aio_name']=a.text_input('Название другой платформы',d.get('custom_aio_name') or '',key=f'caioname_{idx}') or None
                        _aio_price_default=str(d.get('custom_aio_price_input') or '').strip() or _price_input_default(d,'custom_aio_price_input','custom_aio_price')
                        d['custom_aio_price_input']=b.text_input('Цена платформы, ₽ / $',value=_aio_price_default,placeholder='25000 или $280',key=f'caiprice_{idx}').strip()
                        d['custom_aio_supplier']=c.text_input('Поставщик',value=str(d.get('custom_aio_supplier') or ''),placeholder='Поставщик',key=f'caisupplier_{idx}').strip()
                        d['custom_aio_supplier_sku']=e.text_input('Артикул / P/N',value=str(d.get('custom_aio_supplier_sku') or ''),placeholder='код или P/N',key=f'caisku_{idx}').strip()
                        _aio_rub,_aio_currency,_aio_note=_parse_catalog_price(d['custom_aio_price_input'])
                        d['custom_aio_price']=float(_aio_rub); d['custom_aio_price_conversion']=_aio_note
                        if _aio_currency=='USD' and _aio_note: st.caption('Цена платформы: '+_aio_note)
                        if d.get('custom_aio_supplier') and d.get('custom_aio_supplier_sku'):
                            _asp=get_supplier_price_list(d['custom_aio_supplier']); _asi=lookup_price(_asp or {},d['custom_aio_supplier_sku']) if _asp else None
                            if _asi and _asi.get('selected_price_usd') is not None:
                                st.caption(f"Прайс {d['custom_aio_supplier']}: {d['custom_aio_supplier_sku']} → ${float(_asi['selected_price_usd']):g} ({_asi.get('selected_price_mode','')}, {(_asp or {}).get('price_date','')}). При сохранении платформы эта цена будет подставлена автоматически.")
                            elif _asp:
                                st.caption(f"В последнем прайсе «{d['custom_aio_supplier']}» артикул {d['custom_aio_supplier_sku']} не найден.")
                        a,b,c,e=st.columns(4)
                        d['custom_aio_diagonal_in']=num(a,'Факт: диагональ, ″',d,'custom_aio_diagonal_in',integer=False,step=.1)
                        d['custom_aio_resolution']=b.text_input('Факт: разрешение',d.get('custom_aio_resolution') or '',placeholder='1920x1080',key=f'caires_{idx}') or None
                        d['custom_aio_refresh_hz']=num(c,'Факт: частота, Гц',d,'custom_aio_refresh_hz')
                        d['custom_aio_matrix']=e.text_input('Факт: матрица',d.get('custom_aio_matrix') or '',placeholder='IPS',key=f'caimat_{idx}') or None
                        a,b,c=st.columns(3)
                        d['custom_aio_built_in_cardreader']=a.checkbox('Встроенный картридер',bool(d.get('custom_aio_built_in_cardreader')),key=f'caicard_{idx}')
                        d['custom_aio_integrated_psu']=b.checkbox('БП встроен в платформу',bool(d.get('custom_aio_integrated_psu',True)),key=f'caipsu_{idx}')
                        d['custom_aio_psu_w']=num(c,'Факт: мощность встроенного БП, Вт',d,'custom_aio_psu_w')
                        st.markdown('**Порты самой платформы сверх задней панели материнской платы**')
                        a,b,c,e,f=st.columns(5)
                        d['custom_aio_usb2_a']=num(a,'USB2 A',d,'custom_aio_usb2_a')
                        d['custom_aio_gen1_a']=num(b,'Gen1 A',d,'custom_aio_gen1_a')
                        d['custom_aio_gen1_c']=num(c,'Gen1 C',d,'custom_aio_gen1_c')
                        d['custom_aio_gen2_a']=num(e,'Gen2 A',d,'custom_aio_gen2_a')
                        d['custom_aio_gen2_c']=num(f,'Gen2 C',d,'custom_aio_gen2_c')
                        st.markdown('**Из них на передней панели**')
                        a,b,c=st.columns(3)
                        d['custom_aio_front_usb2']=num(a,'USB2 спереди',d,'custom_aio_front_usb2')
                        d['custom_aio_front_a']=num(b,'Type-A спереди',d,'custom_aio_front_a')
                        d['custom_aio_front_c']=num(c,'Type-C спереди',d,'custom_aio_front_c')
                        st.caption('Если точный параметр неизвестен — оставь 0/пусто. Программа не будет додумывать его и покажет предупреждение.')
                        if st.button('💾 Сохранить / обновить платформу в локальной базе', key=f'aio_save_{idx}', use_container_width=True):
                            aio_name = str(d.get('custom_aio_name') or '').strip()
                            if not aio_name:
                                st.error('Сначала укажи название платформы.')
                            else:
                                _aio_payload=_catalog_payload(d, _AIO_CATALOG_FIELDS)
                                _aio_payload,_aio_price_stat=apply_latest_price_to_aio(_aio_payload)
                                _rub,_cur,_note=_parse_catalog_price(_aio_payload.get('custom_aio_price_input'))
                                _aio_payload['custom_aio_price']=float(_rub); _aio_payload['custom_aio_price_conversion']=_note
                                catalog_save_item('aio', aio_name, _aio_payload)
                                _msg=f'Платформа «{aio_name}» сохранена. Она останется доступна после обновления программы.'
                                if _aio_price_stat.get('updated'): _msg+=' Цена автоматически взята из последнего прайса поставщика.'
                                st.success(_msg)
                                for _miss in _aio_price_stat.get('missing') or []: st.warning(_miss)

                with st.expander('Требования дисплея / камеры моноблока'):
                    a,b,c,e=st.columns(4)
                    d['monitor_inches']=num(a,'Диагональ, ″ ≥',d,'monitor_inches',integer=False,step=.1)
                    d['monitor_resolution']=b.text_input('Разрешение',d.get('monitor_resolution') or '',key=f'aiomres_{idx}') or None
                    d['monitor_matrix']=c.text_input('Матрица',d.get('monitor_matrix') or '',key=f'aiommat_{idx}') or None
                    d['monitor_refresh_hz_min']=num(e,'Частота, Гц ≥',d,'monitor_refresh_hz_min')
                    a,b,c,e=st.columns(4)
                    d['monitor_contrast_min']=num(a,'Контрастность ≥ (:1)',d,'monitor_contrast_min')
                    d['monitor_view_angle_h_min']=num(b,'Угол обзора H, ° ≥',d,'monitor_view_angle_h_min')
                    d['monitor_view_angle_v_min']=num(c,'Угол обзора V, ° ≥',d,'monitor_view_angle_v_min')
                    d['audio_jacks_min']=num(e,'Аудио-разъёмов ≥',d,'audio_jacks_min')
                    a,b,c,e=st.columns(4)
                    d['monitor_wall_mount']=tri_bool(a,'Настенное крепление',d.get('monitor_wall_mount'),key=f'aiowall_{idx}')
                    d['monitor_pivot']=tri_bool(b,'Портретный поворот',d.get('monitor_pivot'),key=f'aiopivot_{idx}')
                    d['monitor_height_adjust_mm_min']=num(c,'Регулировка по высоте, мм ≥',d,'monitor_height_adjust_mm_min')
                    d['need_builtin_mic']=e.checkbox('Встроенный микрофон',bool(d.get('need_builtin_mic')),key=f'aiomic_{idx}')
                    a,b,c,e=st.columns(4)
                    d['webcam_mp_min']=num(a,'Веб-камера, Мп ≥',d,'webcam_mp_min',integer=False,step=.5)
                    d['webcam_privacy_shutter']=b.checkbox('Механическая шторка камеры',bool(d.get('webcam_privacy_shutter')),key=f'aiocamlock_{idx}')
                    d['need_audio_jacks']=c.checkbox('Наушники + микрофон',bool(d.get('need_audio_jacks')),key=f'aioaudio_{idx}')
        elif d['product_type']=='monitor':
            d['monitor_catalog_item'] = _catalog_choice_widget('monitor', d.get('monitor_catalog_item'), f'monitor_db_{idx}', 'Монитор из базы')
            a,b,c,e=st.columns(4)
            d['monitor_inches']=num(a,'Диагональ, ″ ≥',d,'monitor_inches',integer=False,step=.1)
            d['monitor_resolution']=b.text_input('Разрешение',d.get('monitor_resolution') or '',key=f'mres_{idx}') or None
            d['monitor_matrix']=c.text_input('Матрица',d.get('monitor_matrix') or '',key=f'mmat_{idx}') or None
            d['monitor_refresh_hz_min']=num(e,'Частота, Гц ≥',d,'monitor_refresh_hz_min')
            a,b=st.columns(2)
            d['monitor_speakers']=tri_bool(a,'Встроенные динамики',d.get('monitor_speakers'),key=f'msp_{idx}')
            d['monitor_interfaces']=b.text_input('Интерфейсы',d.get('monitor_interfaces') or '',key=f'mif_{idx}') or None
            a,b,c,e=st.columns(4)
            d['monitor_brightness_min']=num(a,'Яркость ≥',d,'monitor_brightness_min')
            d['monitor_response_ms_max']=num(b,'Отклик, мс max',d,'monitor_response_ms_max',integer=False,step=.1)
            d['monitor_power_w_max']=num(c,'Потребление, Вт max',d,'monitor_power_w_max',integer=False,step=1)
            d['monitor_vesa']=e.text_input('VESA',d.get('monitor_vesa') or '',key=f'mvesa_{idx}') or None
            a,b,c,e=st.columns(4)
            d['monitor_audio_in_required']=a.checkbox('Mini-Jack вход',bool(d.get('monitor_audio_in_required')),key=f'maudioin_{idx}')
            d['monitor_audio_out_required']=b.checkbox('Mini-Jack выход',bool(d.get('monitor_audio_out_required')),key=f'maudioout_{idx}')
            d['monitor_wall_mount']=tri_bool(c,'Крепление на стену',d.get('monitor_wall_mount'),key=f'mwall_{idx}')
            d['monitor_tilt']=tri_bool(e,'Регулировка наклона',d.get('monitor_tilt'),key=f'mtilt_{idx}')
        elif d['product_type']=='keyboard':
            _keyboard_mouse_source_widget('keyboard', d, idx, standalone=True)
            a,b,c=st.columns(3)
            d['keyboard_wired']=a.checkbox('Проводная',bool(d.get('keyboard_wired')),key=f'kbw_{idx}')
            d['keyboard_usb']=b.checkbox('USB',bool(d.get('keyboard_usb')),key=f'kbu_{idx}')
            d['keyboard_cable_min_m']=num(c,'Кабель, м ≥',d,'keyboard_cable_min_m',integer=False,step=.1)
            a,b=st.columns(2)
            d['keyboard_keys_min']=num(a,'Клавиш ≥',d,'keyboard_keys_min')
            d['keyboard_layout']=b.text_input('Раскладка',d.get('keyboard_layout') or '',key=f'kblayout_{idx}') or None
        elif d['product_type']=='mouse':
            _keyboard_mouse_source_widget('mouse', d, idx, standalone=True)
            a,b,c,e=st.columns(4)
            d['mouse_wired']=a.checkbox('Проводная',bool(d.get('mouse_wired')),key=f'msw_{idx}')
            d['mouse_usb']=b.checkbox('USB',bool(d.get('mouse_usb')),key=f'msu_{idx}')
            d['mouse_dpi_min']=num(c,'DPI ≥',d,'mouse_dpi_min')
            d['mouse_cable_min_m']=num(e,'Кабель, м ≥',d,'mouse_cable_min_m',integer=False,step=.1)
            a,b=st.columns(2)
            d['mouse_buttons_min']=num(a,'Кнопок ≥',d,'mouse_buttons_min')
    d.pop('_idx',None)
    return d



def _row_identity(row):
    row = dict(row or {})
    c = dict(row.get('constraints') or {})
    kind = str(c.get('kind') or '').strip().casefold()
    role = str(c.get('role') or '').strip().casefold()
    category = str(row.get('category') or '').strip().casefold()
    if c.get('manual_added') or kind == 'manual_added':
        return None
    if kind == 'profile_component':
        return ('profile_component', role, str(row.get('name') or '').strip().casefold())
    if kind:
        return (kind, role)
    return ('category', category)


def _merge_rebuilt_rows(old_rows, new_rows):
    """Soft rebuild: update technical logic without wiping the specialist's work."""
    old_rows = [dict(x or {}) for x in (old_rows or [])]
    new_rows = [dict(x or {}) for x in (new_rows or [])]
    buckets = {}
    manual_rows = []
    for old in old_rows:
        c = dict(old.get('constraints') or {})
        if c.get('manual_added') or str(c.get('kind') or '') == 'manual_added':
            manual_rows.append(old)
            continue
        ident = _row_identity(old)
        if ident is not None:
            buckets.setdefault(ident, []).append(old)

    merged = []
    for fresh in new_rows:
        ident = _row_identity(fresh)
        old = None
        if ident in buckets and buckets[ident]:
            old = buckets[ident].pop(0)
        if old:
            overrides = dict(old.get('_user_overrides') or {})
            # Prices entered in the calculation are valuable even for older saved projects
            # that predate explicit override markers.
            if str(old.get('price_input') or '').strip():
                overrides['price_input'] = True
                overrides['price'] = True
                overrides['price_conversion'] = True
                overrides['source'] = True
            for field in ('category','name','qty','source','note','registry','price_input','price','price_conversion'):
                if overrides.get(field):
                    fresh[field] = old.get(field)
            if overrides:
                fresh['_user_overrides'] = overrides
        merged.append(fresh)
    # Anything the specialist added manually is never removed by a tender re-run.
    merged.extend(manual_rows)
    return merged


def _build_plans_from_current_requirements(preserve_existing=True):
    old_plans = list(st.session_state.get('plans') or [])
    plans = []
    peripheral_catalogs = _peripheral_catalogs_live()
    for i, reqd in enumerate(st.session_state.reqs):
        req = Requirements(**{k:v for k,v in reqd.items() if k in Requirements.__dataclass_fields__})
        profile = _equipment_profile_for_req(reqd)
        rows, registry, warnings, checks = build_plan(
            req, st.session_state.qx_prices, st.session_state.settings, equipment_profile=profile,
            peripheral_catalogs=peripheral_catalogs
        )
        old_plan = old_plans[i] if i < len(old_plans) else None
        if preserve_existing and old_plan:
            rows = _merge_rebuilt_rows(old_plan.get('rows') or [], rows)
        plans.append({
            'req':dict(reqd),'rows':rows,'registry':registry,'warnings':warnings,'checks':checks,
            'editor_rev':int((old_plan or {}).get('editor_rev',0))+1 if old_plan else 0
        })
    st.session_state.plan_revision += 1
    st.session_state.plans = plans
    st.session_state.pop('kp_bytes', None)
    st.session_state.pop('kp_filename', None)
    _clear_arsenal_auto_fields()
    return plans


def _equipment_profile_selection_is_stale():
    """True when visible QX/vendor selection no longer matches the calculated plan."""
    plans = list(st.session_state.get('plans') or [])
    reqs = list(st.session_state.get('reqs') or [])
    if not plans or len(plans) != len(reqs):
        return False
    for reqd, plan in zip(reqs, plans):
        current = str((reqd or {}).get('equipment_profile_name') or '').strip().casefold()
        planned = str(((plan or {}).get('req') or {}).get('equipment_profile_name') or '').strip().casefold()
        if current != planned:
            return True
        current_platform = str((reqd or {}).get('platform') or '').strip().casefold()
        planned_platform = str(((plan or {}).get('req') or {}).get('platform') or '').strip().casefold()
        if current_platform != planned_platform:
            return True
    return False



def _component_table_config():
    return {
        'category':st.column_config.TextColumn('Категория',width='small'),
        'name':st.column_config.TextColumn('Наименование',width='large'),
        'qty':st.column_config.NumberColumn('Кол-во/ед.',min_value=0.0,step=1.0,format='%.2f'),
        'price_input':st.column_config.TextColumn('Ввести цену ₽ / $',help='Примеры: 14500, $120, USD 120'),
        'price':st.column_config.NumberColumn('Цена, ₽',format='%.2f',disabled=True),
        'source':st.column_config.TextColumn('Источник',width='small'),
        'note':st.column_config.TextColumn('Комментарий',width='large'),
        'registry':st.column_config.CheckboxColumn('Реестр'),
    }


def _maybe_restore_focus_scroll(anchor_id: str):
    """Return from focus mode to the table that opened it instead of page top."""
    if not st.session_state.get('_focus_scroll_restore_pending'):
        return
    expected=str(st.session_state.get('_focus_scroll_restore_anchor') or '')
    if expected and expected != anchor_id:
        return
    st.session_state.pop('_focus_scroll_restore_pending',None)
    st.session_state.pop('_focus_scroll_restore_anchor',None)
    safe=re.sub(r'[^a-zA-Z0-9_\-:.]','',str(anchor_id))
    script = """<script>
    (function(){
      const id = __ANCHOR__;
      let tries=0;
      function restore(){
        tries++;
        try {
          const d=window.parent.document;
          const el=d.getElementById(id);
          if(el){ el.scrollIntoView({block:'start',inline:'nearest'}); window.parent.scrollBy(0,-90); return; }
        } catch(e) {}
        if(tries<25) setTimeout(restore,60);
      }
      setTimeout(restore,40);
    })();
    </script>""".replace('__ANCHOR__', json.dumps(safe))
    components.html(script,height=0,width=0)


def _restore_after_fullscreen():
    """Queue exact return state and client scroll position for the next normal render."""
    saved = dict(st.session_state.pop('_focus_return_state', {}) or {})
    stage = normalize_calc_stage(saved.get('calc_workspace_stage'), BUILD_STAGE)
    st.session_state['_focus_restore_pending'] = make_focus_return_state(
        main_nav=saved.get('main_nav'),
        stage=stage,
        sidebar_open=saved.get('sidebar_open'),
        sidebar_width=saved.get('sidebar_width'),
    )
    st.session_state['_focus_scroll_restore_pending'] = True
    st.session_state['_focus_scroll_restore_anchor'] = str(st.session_state.pop('_focus_return_anchor', '') or ('qx-stage-verify-anchor' if stage == '✅ Проверка заявки' else 'qx-stage-build-anchor'))


def _enter_fullscreen_calc(idx: int, current_stage=None):
    """Enter focused editor without losing the current workspace destination."""
    st.session_state['_focus_return_state'] = make_focus_return_state(
        main_nav=st.session_state.get('main_nav', '🧮 Расчёт'),
        stage=current_stage or st.session_state.get('calc_workspace_stage') or BUILD_STAGE,
        sidebar_open=st.session_state.get('sidebar_open', True),
        sidebar_width=st.session_state.get('sidebar_width', 320),
    )
    st.session_state['_focus_return_anchor'] = f'qx-build-table-{int(idx)}'
    st.session_state['_focus_calc_idx'] = int(idx)


def _enter_fullscreen_tender(current_stage=None):
    st.session_state['_focus_return_state'] = make_focus_return_state(
        main_nav=st.session_state.get('main_nav', '🧮 Расчёт'),
        stage=current_stage or '✅ Проверка заявки',
        sidebar_open=st.session_state.get('sidebar_open', True),
        sidebar_width=st.session_state.get('sidebar_width', 320),
    )
    st.session_state['_focus_return_anchor'] = 'qx-verify-table'
    st.session_state['_focus_tender_editor'] = True


def _render_fullscreen_tender_editor():
    if not st.session_state.get('_focus_tender_editor'):
        return False
    st.markdown('''
    <style>
    section[data-testid="stSidebar"]{display:none!important}
    header[data-testid="stHeader"]{display:none!important}
    .qx-title-wrap,.qx-title-wrap + .qx-muted,.qx-currency{display:none!important}
    .block-container{max-width:none!important;width:100%!important;padding:.65rem .75rem 1rem!important}
    [data-testid="stDataEditor"]{min-height:82vh!important}
    </style>
    ''',unsafe_allow_html=True)
    top1,top2=st.columns([1,7])
    if top1.button('← Назад',use_container_width=True,key='focus_tender_close'):
        st.session_state.pop('_focus_tender_editor',None)
        _restore_after_fullscreen(); st.rerun()
    top2.markdown('<div class="qx-focusbar"><b>Фактические характеристики — таблица на весь экран</b><br><span class="qx-side-muted">Редактируй только колонку «Фактическое значение». Остальные колонки защищены.</span></div>',unsafe_allow_html=True)
    if not (st.session_state.source_docx_bytes and st.session_state.tender_characteristics):
        st.info('Полноэкранное редактирование фактических характеристик доступно для исходного DOCX.')
        st.stop(); return True
    char_rows=build_characteristic_rows(st.session_state.tender_characteristics,st.session_state.reqs,st.session_state.plans,st.session_state.tender_overrides)
    editable=[x for x in char_rows if x.get('editable')]
    if not editable:
        st.info('В ТЗ нет изменяемых характеристик для заполнения.')
        st.stop(); return True
    edf=pd.DataFrame([{
        '_id':x['id'],
        'Позиция': (st.session_state.reqs[x.get('plan_index',0)].get('title') if x.get('plan_index',0) < len(st.session_state.reqs) else ''),
        'Характеристика':x['name'],'Требование из ТЗ':x['original_value'],'Ед.':x['unit'],
        'Автофакт':x.get('auto_value',''),'Фактическое значение':x['value'],'Автоисточник':x['source'],
        'Статус':x['status'],'Инструкция':x['instruction'],
    } for x in editable]).set_index('_id')
    key=f'focus_tender_values_{st.session_state.plan_revision}'
    edited=st.data_editor(edf,hide_index=True,use_container_width=True,num_rows='fixed',height=760,key=key,
        disabled=['Позиция','Характеристика','Требование из ТЗ','Ед.','Автофакт','Автоисточник','Статус','Инструкция'],
        column_config={
            'Позиция':st.column_config.TextColumn('Позиция',width='small'),'Характеристика':st.column_config.TextColumn('Характеристика',width='large'),
            'Требование из ТЗ':st.column_config.TextColumn('Требование из ТЗ',width='medium'),'Ед.':st.column_config.TextColumn('Ед.',width='small'),
            'Автофакт':st.column_config.TextColumn('Автофакт',width='small'),'Фактическое значение':st.column_config.TextColumn('Фактическое значение',width='medium'),
            'Автоисточник':st.column_config.TextColumn('Откуда взято',width='medium'),'Статус':st.column_config.TextColumn('Статус',width='small'),
            'Инструкция':st.column_config.TextColumn('Инструкция заказчика',width='large'),
        })
    auto_by_id={x['id']:str(x.get('auto_value') or '') for x in editable}
    auto_status_by_id={x['id']:str(x.get('auto_status') or '') for x in editable}
    changed=False
    for rid,row in edited.iterrows():
        val=str(row.get('Фактическое значение') or '').strip(); auto=auto_by_id.get(str(rid),''); old=st.session_state.tender_overrides.get(str(rid),None)
        if val == auto and auto_status_by_id.get(str(rid)) != 'НЕ СООТВЕТСТВУЕТ':
            if str(rid) in st.session_state.tender_overrides: st.session_state.tender_overrides.pop(str(rid),None); changed=True
        elif old != val:
            st.session_state.tender_overrides[str(rid)]=val; changed=True
    if changed: st.rerun()
    fresh=build_characteristic_rows(st.session_state.tender_characteristics,st.session_state.reqs,st.session_state.plans,st.session_state.tender_overrides)
    fresh=[x for x in fresh if x.get('editable')]
    ok=sum(1 for x in fresh if x.get('status') in ('OK','ЗАПОЛНЕНО')); miss=sum(1 for x in fresh if x.get('status')=='НУЖНО ЗАПОЛНИТЬ')
    a,b,c=st.columns(3); a.metric('Заполнено',f'{ok} / {len(fresh)}'); b.metric('Нужно заполнить',miss); c.metric('Несоответствий',sum(1 for x in fresh if x.get('status') in ('НЕ ПРОХОДИТ','НЕ СООТВЕТСТВУЕТ','АВТО НЕ СООТВЕТСТВУЕТ')))
    st.stop(); return True


def _render_fullscreen_component_editor():
    """Dedicated distraction-free editor for one calculated position."""
    raw_idx=st.session_state.get('_focus_calc_idx')
    if raw_idx is None:
        return False
    try: idx=int(raw_idx)
    except Exception:
        st.session_state.pop('_focus_calc_idx',None)
        _restore_after_fullscreen()
        return False
    plans=st.session_state.get('plans') or []
    if not (0 <= idx < len(plans)):
        st.session_state.pop('_focus_calc_idx',None)
        _restore_after_fullscreen()
        return False
    plan=plans[idx]; req=plan.get('req') or {}
    st.markdown('''
    <style>
    section[data-testid="stSidebar"]{display:none!important}
    header[data-testid="stHeader"]{display:none!important}
    .qx-title-wrap,.qx-title-wrap + .qx-muted,.qx-currency{display:none!important}
    .block-container{max-width:none!important;width:100%!important;padding:.75rem 1.15rem 1.2rem!important}
    [data-testid="stDataEditor"]{min-height:70vh!important}
    </style>
    ''',unsafe_allow_html=True)
    c0,cpos,c1,c2=st.columns([.8,2.2,4.4,1])
    if c0.button('← Назад',use_container_width=True,key='focus_calc_close'):
        plan['editor_rev']=int(plan.get('editor_rev',0))+1
        st.session_state.pop('_focus_calc_idx',None)
        _restore_after_fullscreen()
        st.rerun()
    _selected_focus_idx=cpos.selectbox('Позиция',list(range(len(plans))),index=idx,
        format_func=lambda n: str((plans[n].get('req') or {}).get('title') or f'Позиция {n+1}'),key=f'focus_position_selector_{idx}')
    if int(_selected_focus_idx) != idx:
        plan['editor_rev']=int(plan.get('editor_rev',0))+1
        st.session_state['_focus_calc_idx']=int(_selected_focus_idx)
        st.rerun()
    c1.markdown(f'<div class="qx-focusbar"><b>Комплектующие — таблица на весь экран</b> · {req.get("title",f"Позиция {idx+1}")}<br><span class="qx-side-muted">Цены можно вводить в ₽ или $ — итог пересчитывается автоматически.</span></div>',unsafe_allow_html=True)
    if c2.button('🌐 DNS',use_container_width=True,key='focus_calc_dns'):
        try: webbrowser.open_new_tab('https://www.dns-shop.ru/')
        except Exception as exc: st.warning(str(exc))
    df=pd.DataFrame(plan.get('rows') or [])
    for col in EDITOR_COLS:
        if col not in df:
            df[col]='' if col not in ('qty','price','registry') else (False if col=='registry' else 0.0)
    editor_key=f'focus_components_{st.session_state.plan_revision}_{idx}_{plan.get("editor_rev",0)}'
    st.data_editor(df[EDITOR_COLS],hide_index=True,num_rows='fixed',use_container_width=True,height=790,key=editor_key,
        on_change=_sync_component_editor,args=(idx,editor_key),column_config=_component_table_config())
    addc,delc,sp,metricc=st.columns([1.2,1.2,3,1.6])
    if addc.button('＋ Добавить строку',use_container_width=True,key=f'focus_add_{idx}'):
        _append_manual_calc_row(idx); st.rerun()
    manual_count=sum(1 for r in plan.get('rows') or [] if (dict((r or {}).get('constraints') or {}).get('manual_added') or str(dict((r or {}).get('constraints') or {}).get('kind') or '')=='manual_added'))
    if delc.button('− Удалить ручную',use_container_width=True,disabled=manual_count==0,key=f'focus_del_{idx}'):
        if _remove_last_manual_calc_row(idx): st.rerun()
    unit=sum(float(x.get('qty') or 0)*float(x.get('price') or 0) for x in plan.get('rows') or [])
    metricc.metric('Себестоимость 1 ед.',f'{unit:,.2f} ₽'.replace(',',' '))
    sp.caption('Только таблица комплектующих. «Назад» вернёт на тот же рабочий этап и прокрутит страницу обратно к этой таблице.')
    st.stop()
    return True


# Explicit table focus modes. We do not rely on Streamlit's optional hover toolbar.
if _render_fullscreen_tender_editor():
    st.stop()
if _render_fullscreen_component_editor():
    st.stop()

if _nav == '🧮 Расчёт':
    _preview_purchase=sum(sum(float(r.get('qty') or 0)*float(r.get('price') or 0) for r in (p.get('rows') or []))*int((p.get('req') or {}).get('quantity') or 0) for p in (st.session_state.get('plans') or []))
    _preview_warn=sum(len(p.get('warnings') or []) + sum(1 for c in (p.get('checks') or []) if str(c.get('Статус') or '') != 'OK') for p in (st.session_state.get('plans') or []))
    _src_label=str(st.session_state.get('source_filename') or 'ТЗ ещё не загружено')
    st.markdown(f'<div class="qx-workbench"><div class="qx-workbench-title">Рабочий стол расчёта</div><div class="qx-workbench-sub"><span class="qx-pill">📄 {_src_label}</span><span class="qx-pill">Позиций: {len(st.session_state.get("reqs") or [])}</span><span class="qx-pill">Себестоимость оборудования: {_preview_purchase:,.0f} ₽</span><span class="qx-pill">Предупреждений: {_preview_warn}</span></div></div>',unsafe_allow_html=True)
    _pending_stage = st.session_state.pop('_calc_workspace_stage_pending', None)
    if _pending_stage:
        st.session_state['calc_workspace_stage'] = normalize_calc_stage(_pending_stage, DEFAULT_STAGE)
    if st.session_state.get('calc_workspace_stage') not in CALC_STAGES:
        st.session_state['calc_workspace_stage'] = DEFAULT_STAGE
    st.radio('Рабочий этап', list(CALC_STAGES), horizontal=True, key='calc_workspace_stage', label_visibility='collapsed')
    _stage = normalize_calc_stage(st.session_state.get('calc_workspace_stage'), DEFAULT_STAGE)
    if not st.session_state.plans and _stage != '📥 ТЗ и требования':
        st.info('Сначала загрузи ТЗ и нажми «Подобрать комплектующие». После этого остальные рабочие разделы станут полезными.')
    if _stage == '📥 ТЗ и требования':
        reset_col, _ = st.columns([1, 4])
        if reset_col.button('↻ Новый расчёт / Сбросить', use_container_width=True, help='Очистить текущий расчёт и начать заново. Цены QX и настройки сохранятся.'):
            _reset_current_calculation()
            st.rerun()

        if not st.session_state.reqs and not st.session_state.plans and not st.session_state.get('_autosave_dismissed'):
            _ainfo=autosave_info()
            if _ainfo:
                try:
                    _adt=datetime.fromisoformat(_ainfo.get('modified_at') or '')
                    _alabel=_adt.strftime('%d.%m.%Y %H:%M:%S')
                except Exception:
                    _alabel=str(_ainfo.get('modified_at') or '')
                st.info(f'Найдено автосохранение незавершённого расчёта от {_alabel}. Можно восстановить его одним нажатием.')
                _ar,_ad,_ax=st.columns([2,1,3])
                if _ar.button('↩ Восстановить автосохранение',type='primary',use_container_width=True,key='restore_autosave'):
                    try:
                        _raw=load_autosave()
                        if not _raw: raise ValueError('Файл автосохранения не найден.')
                        _restore_project_object(load_project(_raw))
                        st.session_state['_autosave_dismissed']=True
                        st.success('Автосохранение восстановлено.')
                        st.rerun()
                    except Exception as _exc:
                        st.error(f'Не удалось восстановить автосохранение: {_exc}')
                if _ad.button('Удалить',use_container_width=True,key='delete_autosave_prompt'):
                    delete_autosave(); st.session_state['_autosave_dismissed']=True; st.rerun()

        st.subheader('1. Техническое задание / сохранённый проект')
        left,right=st.columns([2,1])
        upload=left.file_uploader('Загрузить ТЗ: DOCX, PDF, XLSX, TXT',type=['docx','pdf','xlsx','xlsm','txt','csv'],key='tz_upload')
        backup_upload=right.file_uploader('Открыть бекап QX',type=['qxproj','json'],key='backup_upload')
        if right.button('Загрузить сохранённый расчёт',disabled=backup_upload is None,use_container_width=True):
            try:
                obj=load_project(backup_upload.getvalue())
                _restore_project_object(obj)
                st.success('Бекап загружен. Весь расчёт восстановлен и снова редактируется.')
                st.rerun()
            except Exception as e:
                st.error(f'Не удалось открыть бекап: {e}')

        st.caption('Цены в интернете программа больше не ищет. Она подбирает технически подходящую конфигурацию, а цены ты вводишь вручную в ₽ или $, после чего всё пересчитывается автоматически.')
        if st.button('Разобрать ТЗ',type='primary',disabled=upload is None,use_container_width=True):
            try:
                upload_bytes=upload.getvalue()
                reqs,text=parse_tz(upload.name,upload_bytes)
                st.session_state.reqs=[r.to_dict() for r in reqs]
                st.session_state.source_text=text
                st.session_state.source_filename=upload.name
                if upload.name.lower().endswith('.docx'):
                    st.session_state.source_docx_bytes=upload_bytes
                    st.session_state.tender_characteristics=extract_characteristics_docx(upload_bytes)
                else:
                    st.session_state.source_docx_bytes=None
                    st.session_state.tender_characteristics=[]
                st.session_state.tender_overrides={}
                st.session_state.plans=[]
                st.session_state.project_meta={}
                st.session_state.pop('kp_bytes',None); st.session_state.pop('kp_filename',None)
                # A new project starts with clean project-level values.
                for key in ['project_delivery','project_bg','project_go','ars_qty','ars_sender','ars_country','ars_os','ars_tm','ars_eq_count']:
                    st.session_state.pop(key,None)
                st.success(f'Готово. Найдено позиций: {len(reqs)}')
                try:
                    _parsed_project=dump_project(reqs=st.session_state.reqs,plans=[],source_text=st.session_state.source_text,
                        qx_prices=st.session_state.qx_prices,project_meta={},settings_snapshot=st.session_state.settings,
                        source_filename=st.session_state.source_filename,source_docx_bytes=st.session_state.source_docx_bytes,
                        tender_overrides=st.session_state.tender_overrides,tender_characteristics=st.session_state.tender_characteristics)
                    save_autosave(_parsed_project)
                    st.session_state['_autosave_fingerprint']='parsed:'+hashlib.sha256(_parsed_project).hexdigest()
                except Exception:
                    pass
            except Exception as e:
                st.error(f'Не удалось прочитать ТЗ: {e}')

        if st.session_state.reqs:
            st.subheader('2. Проверить распознавание')
            st.session_state.reqs=[req_editor(r,i) for i,r in enumerate(st.session_state.reqs)]
            _db_changed = (st.session_state.pop('_equipment_profile_changed', False) or st.session_state.pop('_peripheral_catalog_changed', False) or st.session_state.pop('_platform_changed', False))
            if _db_changed and st.session_state.plans:
                _build_plans_from_current_requirements(preserve_existing=False)
                st.success('Выбранная база изменена — расчёт и строка Арсенала автоматически обновлены.')
                st.rerun()
            elif _equipment_profile_selection_is_stale():
                _build_plans_from_current_requirements(preserve_existing=False)
                st.rerun()
            if st.button('Подобрать комплектующие',type='primary',use_container_width=True):
                qty_errors=validate_quantities(st.session_state.reqs)
                if qty_errors:
                    st.error('Сначала укажи количество по каждой позиции:\n' + '\n'.join('• '+x for x in qty_errors))
                else:
                    _build_plans_from_current_requirements(preserve_existing=True)
                    st.success('Комплектующие подобраны. Твои ручные строки, цены и правки сохранены. Теперь выбери процессор из подходящих вариантов (если их несколько) и внеси цены вручную.')
                    st.session_state['_calc_workspace_stage_pending']='🧩 Сборка и цены'
                    st.rerun()

    if st.session_state.plans:
        # Shared project context is calculated even when another workspace tab is active.
        # This keeps Arsenal/Documents independent from the Build tab and makes stage switching stable across reruns.
        delivery=float(st.session_state.get('project_delivery',st.session_state.settings.get('default_delivery',0)) or 0)
        bg=float(st.session_state.get('project_bg',st.session_state.settings.get('default_bg',st.session_state.settings.get('default_bg1',0))) or 0)
        go=float(st.session_state.get('project_go',st.session_state.settings.get('default_go',st.session_state.settings.get('default_bg2',0))) or 0)
        total_purchase=0.0
        auto_equipment=[]
        assembled_qty_candidates=[]
        all_qty_candidates=[]
        os_defaults=[]
        for _ctx_plan in st.session_state.plans:
            _ctx_req=_ctx_plan.get('req') or {}
            _ctx_unit=sum(float(x.get('qty') or 0)*float(x.get('price') or 0) for x in (_ctx_plan.get('rows') or []))
            _ctx_qty=int(_ctx_req.get('quantity') or 0)
            total_purchase += _ctx_unit * _ctx_qty
            all_qty_candidates.append(_ctx_qty)
            if _ctx_req.get('product_type') in ('system','aio24','aio27','aws24','aws27'):
                assembled_qty_candidates.append(_ctx_qty)
            if _ctx_req.get('need_os'):
                os_defaults.append(normalize_arsenal_os_name(True,_ctx_req.get('os_text')))
            auto_equipment.append(arsenal_equipment_default(_ctx_plan))
        default_project_qty=max(assembled_qty_candidates or all_qty_candidates or [1])
        _ars_auto_token_shared = str(st.session_state.plan_revision) + ':' + hashlib.sha1(json.dumps(auto_equipment,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()
        if st.session_state.get('_ars_auto_token') != _ars_auto_token_shared:
            for _k in list(st.session_state.keys()):
                if _k.startswith('ars_eq_') or _k.startswith('ars_reg_'):
                    del st.session_state[_k]
            st.session_state.ars_qty=int(default_project_qty)
            st.session_state.ars_eq_count=max(1,len(auto_equipment))
            for _j,_item in enumerate(auto_equipment):
                st.session_state[f'ars_eq_{_j}']=str(_item.get('equipment') or '')
                st.session_state[f'ars_reg_{_j}']=str(_item.get('registry_number') or '')
            _named_os = next((x for x in os_defaults if str(x or '').strip()), None)
            st.session_state.ars_os = _named_os if _named_os is not None else ('' if os_defaults else 'нет')
            st.session_state['_ars_auto_token'] = _ars_auto_token_shared
        project_qty=int(st.session_state.get('ars_qty',default_project_qty) or default_project_qty)
        sender=str(st.session_state.get('ars_sender',st.session_state.settings.get('default_sender','ЗИОН')))
        country=str(st.session_state.get('ars_country',st.session_state.settings.get('default_country','Россия')))
        os_name=str(st.session_state.get('ars_os',''))
        trademark=str(st.session_state.get('ars_tm',st.session_state.settings.get('default_trademark','1093786')))
        equip_count=int(st.session_state.get('ars_eq_count',max(1,len(auto_equipment))) or max(1,len(auto_equipment)))
        equipment=[]
        for _j in range(equip_count):
            _default=auto_equipment[_j] if _j < len(auto_equipment) else {'equipment':'','registry_number':''}
            equipment.append({
                'equipment':str(st.session_state.get(f'ars_eq_{_j}',_default.get('equipment') or '')),
                'registry_number':str(st.session_state.get(f'ars_reg_{_j}',_default.get('registry_number') or '')),
            })

        if _stage == '🧩 Сборка и цены':
            st.markdown('<div id="qx-stage-build-anchor"></div>', unsafe_allow_html=True)
            _maybe_restore_focus_scroll('qx-stage-build-anchor')
            st.subheader('3. Сборка и расчёт')
            _dns_col,_dns_spacer=st.columns([1,4])
            if _dns_col.button('🌐 Открыть DNS',use_container_width=True,help='Открыть сайт DNS в браузере для быстрого поиска комплектующих.'):
                try:
                    webbrowser.open_new_tab('https://www.dns-shop.ru/')
                    st.toast('DNS открыт в браузере.')
                except Exception as _exc:
                    st.warning(f'Не удалось открыть браузер автоматически: {_exc}')
            st.caption('Цена может быть, например, «15000» или «$120». Для долларов используется курс ЦБ РФ + запас, указанный в настройках. Поле «Цена, ₽» рассчитывается автоматически.')

            fa,fb,fc=st.columns(3)
            delivery=fa.number_input('Доставка, ₽ (весь проект)',min_value=0.0,value=float(st.session_state.get('project_delivery',st.session_state.settings.get('default_delivery',0))),step=1000.0,key='project_delivery')
            bg=fb.number_input('БГ, ₽',min_value=0.0,value=float(st.session_state.get('project_bg',st.session_state.settings.get('default_bg',st.session_state.settings.get('default_bg1',0)))),step=1000.0,key='project_bg')
            go=fc.number_input('ГО, ₽',min_value=0.0,value=float(st.session_state.get('project_go',st.session_state.settings.get('default_go',st.session_state.settings.get('default_bg2',0)))),step=1000.0,key='project_go')

            total_purchase=0.0
            auto_equipment=[]
            assembled_qty_candidates=[]
            all_qty_candidates=[]
            os_defaults=[]

            for i,plan in enumerate(st.session_state.plans):
                req=plan['req']
                st.markdown(f'### {req.get("title",f"Позиция {i+1}")}')
                if req.get('ktru_code'): st.caption(f'КТРУ: {req["ktru_code"]}')

                # CPU selection is always visible. Every confirmed matching model is offered,
                # and a manual option remains available for a new/unlisted processor.
                cpu_row=next((r for r in plan.get('rows',[]) if r.get('category')=='Процессор'),None)
                if cpu_row:
                    alternatives=list(dict.fromkeys(cpu_row.get('alternatives') or []))
                    current=(cpu_row.get('name') or '').replace(' OEM','').strip()
                    st.markdown('**Процессор — выбор модели**')
                    if alternatives:
                        details=pd.DataFrame(cpu_details(alternatives))
                        if not details.empty:
                            show_cols=[x for x in ['model','cores','threads','base_ghz','boost_ghz','l3_mb','tdp_w','igpu','socket','source'] if x in details]
                            st.dataframe(details[show_cols],hide_index=True,use_container_width=True)
                        options=alternatives + ['Другая модель (вручную)']
                        default_idx=options.index(current) if current in options else 0
                    else:
                        _cpu_platform=str((cpu_row.get('constraints') or {}).get('platform') or '').upper() or 'не определена'
                        _cpu_needs=[]
                        if req.get('cpu_cores_min'): _cpu_needs.append(f"ядер ≥ {req['cpu_cores_min']}")
                        if req.get('cpu_threads_min'): _cpu_needs.append(f"потоков ≥ {req['cpu_threads_min']}")
                        if req.get('cpu_freq_ghz_min'): _cpu_needs.append(f"база ≥ {req['cpu_freq_ghz_min']} ГГц")
                        if req.get('cpu_freq_max_ghz_min'): _cpu_needs.append(f"макс. ≥ {req['cpu_freq_max_ghz_min']} ГГц")
                        if req.get('cpu_l3_mb_min'): _cpu_needs.append(f"L3 ≥ {req['cpu_l3_mb_min']} МБ")
                        if req.get('cpu_tdp_w_max'): _cpu_needs.append(f"TDP ≤ {req['cpu_tdp_w_max']} Вт")
                        if req.get('need_integrated_graphics'): _cpu_needs.append('встроенная графика')
                        st.warning(
                            f'Для выбранной платформы {_cpu_platform} в справочнике нет подтверждённого процессора, который закрывает все распознанные ограничения'
                            + (': ' + ', '.join(_cpu_needs) if _cpu_needs else '.')
                            + ' Программа не подставляет случайный более мощный CPU.'
                        )
                        options=['Другая модель (вручную)']
                        default_idx=0
                    show_all_cpu=st.checkbox('Показать всю базу Intel/AMD для ручного выбора',value=False,key=f'cpu_all_{st.session_state.plan_revision}_{i}',
                        help='Можно выбрать любой CPU из базы. Если он не подходит по сокету, памяти или требованиям ТЗ, программа не запретит выбор, а покажет «НЕ ПРОХОДИТ».')
                    if show_all_cpu:
                        full_names=sorted({c.model for c in all_cpus()})
                        options=full_names + ['Другая модель (вручную)']
                        default_idx=options.index(current) if current in options else len(options)-1
                    chosen=st.selectbox('Какой процессор поставить',options,index=default_idx,key=f'cpu_choice_{st.session_state.plan_revision}_{i}')
                    manual_cpu=''
                    if chosen=='Другая модель (вручную)':
                        manual_default='' if 'выбрать вручную' in current.lower() else current
                        manual_cpu=st.text_input('Модель процессора вручную',value=manual_default,key=f'cpu_manual_{st.session_state.plan_revision}_{i}',
                                                 help='Если модель есть в обновлённой базе, программа проверит её автоматически. Если нет — характеристики CPU будут помечены как «НЕТ ДАННЫХ», а не как соответствующие.')
                    target_cpu=(manual_cpu.strip() if chosen=='Другая модель (вручную)' else chosen)
                    if st.button('Применить выбранный процессор',key=f'cpu_apply_{st.session_state.plan_revision}_{i}',disabled=not bool(target_cpu)):
                        old_rows=plan.get('rows',[])
                        reqd=dict(plan['req']); reqd['cpu_model']=target_cpu
                        req_obj=Requirements(**{k:v for k,v in reqd.items() if k in Requirements.__dataclass_fields__})
                        profile=_equipment_profile_for_req(reqd)
                        new_rows,new_registry,new_warnings,new_checks=build_plan(req_obj,st.session_state.qx_prices,st.session_state.settings,equipment_profile=profile,peripheral_catalogs=_peripheral_catalogs_live())
                        old_by_cat={r.get('category'):r for r in old_rows}
                        for nr in new_rows:
                            oldr=old_by_cat.get(nr.get('category'))
                            if not oldr or nr.get('category') in ('Процессор','Графика'):
                                continue
                            if oldr.get('source','').startswith('Вручную') and oldr.get('name') == nr.get('name'):
                                for key in ('price','price_input','source','price_conversion'):
                                    if key in oldr: nr[key]=oldr[key]
                        plan.update({'req':reqd,'rows':new_rows,'registry':new_registry,'warnings':new_warnings,'checks':new_checks,'editor_rev':int(plan.get('editor_rev',0))+1})
                        st.session_state.reqs[i]=reqd
                        st.session_state.pop('kp_bytes',None); st.session_state.pop('kp_filename',None)
                        st.rerun()

                for w in plan.get('warnings',[]): st.warning(w)
                if plan.get('checks'):
                    cdf=pd.DataFrame(plan['checks'])
                    with st.expander('Проверка требований по выбранной конфигурации',expanded=any(x['Статус']!='OK' for x in plan['checks'])):
                        st.dataframe(cdf,hide_index=True,use_container_width=True)

                df=pd.DataFrame(plan['rows'])
                for col in EDITOR_COLS:
                    if col not in df:
                        df[col]='' if col not in ('qty','price','registry') else (False if col=='registry' else 0.0)
                editor_key=f'components_{st.session_state.plan_revision}_{i}_{plan.get("editor_rev",0)}'
                st.markdown(f'<div id="qx-build-table-{i}"></div>', unsafe_allow_html=True)
                _maybe_restore_focus_scroll(f'qx-build-table-{i}')
                _fsb1,_fsb2=st.columns([1.8,5])
                if _fsb1.button('⛶ Таблица на весь экран',key=f'focus_open_calc_{i}',use_container_width=True,type='secondary'):
                    _enter_fullscreen_calc(i,_stage)
                    st.rerun()
                _fsb2.caption('Откроется только таблица комплектующих. После «Назад» программа вернёт сюда, а не в начало страницы.')
                st.data_editor(df[EDITOR_COLS],hide_index=True,num_rows='fixed',use_container_width=True,key=editor_key,
                    on_change=_sync_component_editor,args=(i,editor_key),column_config=_component_table_config())
                st.caption('После Enter цена пересчитывается сразу. Для $ используется курс сверху + запас. Позиции из выбранной базы уже имеют сохранённую цену из твоего внутреннего справочника.')
                _addc,_delc,_spc=st.columns([1.4,1.4,4])
                if _addc.button('＋ Добавить строку', key=f'add_manual_row_{i}', use_container_width=True, help='Добавить свою позицию в текущий расчёт. Она не исчезнет после повторного подбора по изменённому ТЗ.'):
                    _append_manual_calc_row(i)
                    st.rerun()
                _manual_count=sum(1 for _r in plan.get('rows') or [] if (dict((_r or {}).get('constraints') or {}).get('manual_added') or str(dict((_r or {}).get('constraints') or {}).get('kind') or '')=='manual_added'))
                if _delc.button('− Удалить ручную', key=f'del_manual_row_{i}', use_container_width=True, disabled=_manual_count==0, help='Удалить последнюю добавленную вручную строку.'):
                    if _remove_last_manual_calc_row(i):
                        st.rerun()
                _spc.caption('Повторный «Подобрать комплектующие» теперь делает мягкое обновление: ручные строки, цены и отредактированные поля сохраняются.')
                conversions=[r.get('price_conversion') for r in plan['rows'] if r.get('price_conversion')]
                if conversions:
                    st.caption('Конвертация: ' + ' · '.join(conversions))

                with st.expander('🔎 Почему выбраны эти комплектующие',expanded=False):
                    st.caption('Для каждой строки можно открыть объяснение: какое требование ТЗ или правило базы привело к её появлению.')
                    for _ri,_row in enumerate(plan.get('rows') or []):
                        _ec1,_ec2=st.columns([5,1])
                        _ec1.write(f"**{_row.get('category','Компонент')}** — {_row.get('name','')}")
                        with _ec2.popover('Почему?'):
                            for _bit in _component_explanation(_row,req):
                                st.write('• '+str(_bit))

                unit=sum(float(x.get('qty') or 0)*float(x.get('price') or 0) for x in plan['rows'])
                qty=int(req.get('quantity') or 0)
                purchase=unit*qty
                total_purchase+=purchase
                all_qty_candidates.append(qty)
                if req.get('product_type') in ('system','aio24','aio27','aws24','aws27'):
                    assembled_qty_candidates.append(qty)
                if req.get('need_os'):
                    os_defaults.append(normalize_arsenal_os_name(True, req.get('os_text')))
                a,b,c=st.columns(3)
                a.metric('Себестоимость 1 ед.',f'{unit:,.2f} ₽'.replace(',',' '))
                b.metric('Количество',f'{qty} шт.')
                c.metric('Закупка по позиции',f'{purchase:,.2f} ₽'.replace(',',' '))
                reg=plan.get('registry')
                if reg:
                    st.markdown(f'''<div class="qx-card"><b>Реестровая запись готового изделия</b><br>{reg['product_name']}<br><span class="qx-tag">№ {reg['registry_number']}</span><span class="qx-tag">{reg['execution_code']}</span><span class="qx-tag">{reg['platform'].upper()}</span></div>''',unsafe_allow_html=True)
                elif req.get('equipment_profile_name'):
                    st.warning(
                        f'Для базы «{req.get("equipment_profile_name")}» не задан реестровый номер готового изделия. '
                        'Реестровые номера материнской платы и отдельных модулей не подставляются вместо номера системного блока. '
                        'Заполни блок «Данные готового изделия / Арсенал» в базе оборудования либо введи номер вручную в Арсенале.'
                    )
                _reg_errors,_reg_warnings=_plan_registry_messages(plan)
                if _reg_errors:
                    st.error('Проверка реестра: ' + ' '.join(_reg_errors))
                elif req.get('product_type') in ('system','aio24','aio27','aws24','aws27'):
                    st.success('Проверка реестра: реестровый номер готового изделия заполнен.')
                for _rw in _reg_warnings:
                    st.warning('Проверка реестра: '+_rw)
                auto_equipment.append(arsenal_equipment_default(plan))
                try:
                    export=export_xlsx(req.get('title','QX'),req,plan['rows'],reg,{'delivery':delivery,'bg1':bg,'bg2':go,'markup':.20},plan.get('checks'))
                    _save_controls(
                        export, f'QX_{i+1}.xlsx',
                        label=f'Сохранить Excel — {req.get("title","позиция")}…', key=f'xlsx_{i}',
                        title='Сохранить расчёт Excel', filetypes=[('Excel (*.xlsx)','*.xlsx')],
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
                except Exception as exc:
                    st.warning(f'Не удалось сформировать Excel: {exc}. Сам расчёт продолжает работать.')

        if _stage == '✅ Проверка заявки':
            st.markdown('<div id="qx-stage-verify-anchor"></div>', unsafe_allow_html=True)
            _maybe_restore_focus_scroll('qx-stage-verify-anchor')
            # Application characteristics: keep locked KTRU values untouched and replace only
            # rows where the participant must state a concrete factual value.
            st.markdown('### 4. Фактические характеристики для заявки')
            if st.session_state.source_docx_bytes and st.session_state.tender_characteristics:
                char_rows=build_characteristic_rows(
                    st.session_state.tender_characteristics,
                    st.session_state.reqs,
                    st.session_state.plans,
                    st.session_state.tender_overrides,
                )
                locked=[x for x in char_rows if not x.get('editable')]
                editable=[x for x in char_rows if x.get('editable')]
                st.caption('Неизменяемые строки программа не трогает. В изменяемых строках подставляется факт выбранной сборки/платформы, но его можно изменить вручную. Знаки ТЗ проверяются строго: >, ≥, <, ≤ и диапазоны. Несоответствие только предупреждается и ничего не блокирует.')

                if locked:
                    with st.expander(f'Неизменяемые характеристики из ТЗ — {len(locked)}', expanded=False):
                        ldf=pd.DataFrame([{
                            'Позиция': (st.session_state.reqs[x.get('plan_index',0)].get('title') if x.get('plan_index',0) < len(st.session_state.reqs) else ''),
                            'Характеристика':x['name'],'Значение из ТЗ':x['original_value'],'Ед.':x['unit'],'Инструкция':x['instruction']
                        } for x in locked])
                        st.dataframe(ldf,hide_index=True,use_container_width=True)

                if editable:
                    edf=pd.DataFrame([{
                        '_id':x['id'],
                        'Позиция': (st.session_state.reqs[x.get('plan_index',0)].get('title') if x.get('plan_index',0) < len(st.session_state.reqs) else ''),
                        'Характеристика':x['name'],
                        'Требование из ТЗ':x['original_value'],
                        'Ед.':x['unit'],
                        'Автофакт':x.get('auto_value',''),
                        'Фактическое значение':x['value'],
                        'Автоисточник':x['source'],
                        'Статус':x['status'],
                        'Инструкция':x['instruction'],
                    } for x in editable]).set_index('_id')
                    tender_key=f'tender_values_{st.session_state.plan_revision}'
                    st.markdown('<div id="qx-verify-table"></div>', unsafe_allow_html=True)
                    _maybe_restore_focus_scroll('qx-verify-table')
                    _vfs1,_vfs2=st.columns([1.8,5])
                    if _vfs1.button('⛶ Таблица на весь экран',key='focus_open_tender',use_container_width=True,type='secondary'):
                        _enter_fullscreen_tender(_stage)
                        st.rerun()
                    _vfs2.caption('Откроется только таблица фактических характеристик. После «Назад» программа вернёт сюда.')
                    edited=st.data_editor(
                        edf,hide_index=True,use_container_width=True,num_rows='fixed',key=tender_key,
                        disabled=['Позиция','Характеристика','Требование из ТЗ','Ед.','Автофакт','Автоисточник','Статус','Инструкция'],
                        column_config={
                            'Позиция':st.column_config.TextColumn('Позиция',width='small'),
                            'Характеристика':st.column_config.TextColumn('Характеристика',width='large'),
                            'Требование из ТЗ':st.column_config.TextColumn('Требование из ТЗ',width='medium'),
                            'Ед.':st.column_config.TextColumn('Ед.',width='small'),
                            'Автофакт':st.column_config.TextColumn('Автофакт',width='small',help='Что программа знает о выбранной сборке. Если это значение не соответствует ТЗ, оно не переносится автоматически в фактическое поле.'),
                            'Фактическое значение':st.column_config.TextColumn('Фактическое значение',width='medium',help='Автозначение можно заменить своим фактическим значением. Любое несоответствие будет предупреждением, а не блокировкой.'),
                            'Автоисточник':st.column_config.TextColumn('Откуда взято',width='medium'),
                            'Статус':st.column_config.TextColumn('Статус',width='small'),
                            'Инструкция':st.column_config.TextColumn('Инструкция заказчика',width='large'),
                        }
                    )
                    auto_by_id={x['id']:str(x.get('auto_value') or '') for x in editable}
                    auto_status_by_id={x['id']:str(x.get('auto_status') or '') for x in editable}
                    changed=False
                    for rid,row in edited.iterrows():
                        val=str(row.get('Фактическое значение') or '').strip()
                        auto=auto_by_id.get(str(rid),'')
                        old=st.session_state.tender_overrides.get(str(rid),None)
                        if val == auto and auto_status_by_id.get(str(rid)) != 'НЕ СООТВЕТСТВУЕТ':
                            if str(rid) in st.session_state.tender_overrides:
                                st.session_state.tender_overrides.pop(str(rid),None); changed=True
                        elif old != val:
                            st.session_state.tender_overrides[str(rid)]=val; changed=True
                    if changed:
                        st.rerun()

                    # Rebuild after overrides to calculate final validation state.
                    char_rows=build_characteristic_rows(st.session_state.tender_characteristics,st.session_state.reqs,st.session_state.plans,st.session_state.tender_overrides)
                    editable=[x for x in char_rows if x.get('editable')]
                    missing=[x for x in editable if x.get('status')=='НУЖНО ЗАПОЛНИТЬ']
                    auto_rejected=[x for x in editable if x.get('status')=='АВТО НЕ СООТВЕТСТВУЕТ']
                    failing=[x for x in editable if x.get('status') in ('НЕ ПРОХОДИТ','НЕ СООТВЕТСТВУЕТ')]
                    ok_count=sum(1 for x in editable if x.get('status') in ('OK','ЗАПОЛНЕНО'))
                    a,b,c,d=st.columns(4)
                    a.metric('Заполнено',f'{ok_count} / {len(editable)}')
                    b.metric('Нужно заполнить',len(missing))
                    c.metric('Автофакт отклонён',len(auto_rejected))
                    d.metric('Ручных несоответствий',len(failing))
                    if missing:
                        st.warning('Не хватает фактических значений: ' + '; '.join(x['name'] for x in missing[:8]) + ('…' if len(missing)>8 else ''))
                    if auto_rejected:
                        st.warning('Программа нашла фактические значения, но НЕ подставила их в заявку, потому что они не соответствуют знакам/границам ТЗ: ' + '; '.join(f"{x['name']}: авто {x.get('auto_value','')} при требовании {x['original_value']}" for x in auto_rejected[:8]) + ('…' if len(auto_rejected)>8 else '') + '. Можно изменить конфигурацию или ввести фактическое значение вручную.')
                    if failing:
                        st.warning('ВНИМАНИЕ — есть фактические значения, которые не соответствуют знакам/границам ТЗ: ' + '; '.join(f"{x['name']} = {x['value']} (требование {x['original_value']})" for x in failing[:8]) + ('…' if len(failing)>8 else '') + '. Программа не блокирует работу: проверь конфигурацию или исправь значение вручную.')

                    values={x['id']:x.get('value','') for x in editable}
                    ready=True  # предупреждения не блокируют выгрузку по правилу пользователя
                    try:
                        filled_docx=fill_docx_characteristics(st.session_state.source_docx_bytes,st.session_state.tender_characteristics,values)
                        base=(st.session_state.source_filename or 'ТЗ.docx').rsplit('.',1)[0]
                        _save_controls(
                            filled_docx, f'{base}_заполненное.docx',
                            label='Сохранить готовое ТЗ в Word…', key='filled_tender',
                            title='Сохранить заполненное ТЗ', filetypes=[('Word (*.docx)','*.docx')],
                            mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                        )
                        if missing or auto_rejected or failing:
                            st.caption('Word всё равно можно сохранить. Пустые фактические значения в исходной форме не заменяются, а несоответствия остаются на твоей ответственности — программа только предупреждает.')
                    except Exception as exc:
                        st.warning(f'Не удалось сформировать Word: {exc}')
            elif st.session_state.source_filename:
                st.info('Автозаполнение Word доступно для исходного ТЗ в формате DOCX. Для PDF/XLSX расчёт работает, но готовый Word из исходной формы не формируется.')

        if _stage == '🧩 Сборка и цены':
            extras=delivery+bg+go
            total_cost=total_purchase+extras
            st.markdown('### Итог по проекту')
            a,b,c,d=st.columns(4)
            a.metric('Закупка оборудования',f'{total_purchase:,.2f} ₽'.replace(',',' '))
            b.metric('Доставка + БГ + ГО',f'{extras:,.2f} ₽'.replace(',',' '))
            c.metric('Полная себестоимость',f'{total_cost:,.2f} ₽'.replace(',',' '))
            e20=dict(exit_points(total_purchase,delivery,bg,go)).get(20,total_cost)
            d.metric('Точка выхода 20%',f'{e20:,.2f} ₽'.replace(',',' '))
            st.markdown('**Точки выхода:** ' + ' · '.join(f'{p}% — {money(v)} ₽' for p,v in exit_points(total_purchase,delivery,bg,go)))

        if _stage == '📋 Арсенал':
            st.markdown('### 5. Строка для Арсенала')
            st.caption('Все поля можно менять вручную. Если в проекте несколько товаров, для каждого остаётся отдельная строка оборудования/реестрового номера.')
            default_project_qty=max(assembled_qty_candidates or all_qty_candidates or [1])
            # Re-sync automatic Arsenal fields whenever the calculated plan changes. Manual
            # edits persist while the current plan revision stays unchanged.
            _ars_auto_token = str(st.session_state.plan_revision) + ':' + hashlib.sha1(
                json.dumps(auto_equipment, ensure_ascii=False, sort_keys=True).encode('utf-8')
            ).hexdigest()
            if st.session_state.get('_ars_auto_token') != _ars_auto_token:
                for _k in list(st.session_state.keys()):
                    if _k.startswith('ars_eq_') or _k.startswith('ars_reg_'):
                        del st.session_state[_k]
                st.session_state.ars_qty=int(default_project_qty)
                st.session_state.ars_eq_count=max(1,len(auto_equipment))
                for _j,_item in enumerate(auto_equipment):
                    st.session_state[f'ars_eq_{_j}']=str(_item.get('equipment') or '')
                    st.session_state[f'ars_reg_{_j}']=str(_item.get('registry_number') or '')
                _named_os = next((x for x in os_defaults if str(x or '').strip()), None)
                st.session_state.ars_os = _named_os if _named_os is not None else ('' if os_defaults else 'нет')
                st.session_state['_ars_auto_token'] = _ars_auto_token

            if 'ars_qty' not in st.session_state: st.session_state.ars_qty=int(default_project_qty)
            if 'ars_eq_count' not in st.session_state: st.session_state.ars_eq_count=max(1,len(auto_equipment))
            qcol,ecol=st.columns([1,2])
            project_qty=qcol.number_input('Количество комплектов / ед. для «Себестоимость за ед.»',min_value=1,value=int(st.session_state.ars_qty),step=1,key='ars_qty')
            equip_count=ecol.number_input('Количество строк оборудования в Арсенале',min_value=1,max_value=30,value=int(st.session_state.ars_eq_count),step=1,key='ars_eq_count')

            if 'ars_sender' not in st.session_state: st.session_state.ars_sender=str(st.session_state.settings.get('default_sender','ЗИОН'))
            if 'ars_country' not in st.session_state: st.session_state.ars_country=str(st.session_state.settings.get('default_country','Россия'))
            if 'ars_os' not in st.session_state:
                _named_os = next((x for x in os_defaults if str(x or '').strip()), None)
                st.session_state.ars_os = _named_os if _named_os is not None else ('' if os_defaults else 'нет')
            if 'ars_tm' not in st.session_state: st.session_state.ars_tm=str(st.session_state.settings.get('default_trademark','1093786'))
            a,b,c,d=st.columns(4)
            sender=a.text_input('От кого',key='ars_sender')
            country=b.text_input('Страна',key='ars_country')
            os_name=c.text_input('Название ОС',key='ars_os')
            trademark=d.text_input('Товарный знак',key='ars_tm')
            if os_defaults and not str(os_name or '').strip():
                st.warning('ТЗ требует предустановленную ОС, но её точное название не найдено. Поле «Название ОС» оставлено пустым — укажи фактическую ОС вручную.')
            if any(bool(x.get('registry_missing')) for x in auto_equipment):
                st.caption('Пустой реестровый номер означает, что для готового изделия он не задан. Номер материнской платы/модуля программа намеренно не подменяет под реестровый номер системного блока.')

            equipment=[]
            for j in range(int(equip_count)):
                default=auto_equipment[j] if j < len(auto_equipment) else {'equipment':'','registry_number':''}
                if f'ars_eq_{j}' not in st.session_state: st.session_state[f'ars_eq_{j}']=str(default.get('equipment') or '')
                if f'ars_reg_{j}' not in st.session_state: st.session_state[f'ars_reg_{j}']=str(default.get('registry_number') or '')
                c1,c2=st.columns([4,1])
                eq=c1.text_input(f'Оборудование {j+1}',key=f'ars_eq_{j}')
                rn=c2.text_input(f'Реестровый номер {j+1}',key=f'ars_reg_{j}')
                equipment.append({'equipment':eq,'registry_number':rn})

            _missing_registry=[]; _odd_registry=[]
            for _j,_item in enumerate(equipment):
                _eq=str(_item.get('equipment') or '').strip(); _rn=str(_item.get('registry_number') or '').strip()
                _needs_registry=(_j < len(st.session_state.plans) and str((st.session_state.plans[_j].get('req') or {}).get('product_type') or '') in ('system','aio24','aio27','aws24','aws27'))
                if _eq and not _rn and _needs_registry:
                    _missing_registry.append(_j+1)
                elif _rn and not re.fullmatch(r'\d{5,}',_rn):
                    _odd_registry.append((_j+1,_rn))
            if _missing_registry:
                st.error('Проверка перед выгрузкой: не заполнен реестровый номер у строк Арсенала: ' + ', '.join(map(str,_missing_registry)) + '. Файл можно сохранить, но проверь номер перед отправкой.')
            elif equipment:
                st.success('Проверка перед выгрузкой: реестровые номера во всех заполненных строках Арсенала указаны.')
            for _j,_rn in _odd_registry:
                st.warning(f'Строка Арсенала {_j}: номер «{_rn}» имеет необычный формат. Это офлайн-проверка формата, а не подтверждение записи в реестре.')

            arsenal_text=build_arsenal_text(purchase=total_purchase,project_qty=project_qty,delivery=delivery,bg=bg,go=go,
                sender=sender,equipment=equipment,country=country,os_name=os_name,trademark=trademark)
            st.code(arsenal_text,language=None)
            _save_controls(
                arsenal_text.encode('utf-8-sig'), 'Арсенал.txt',
                label='Сохранить строку Арсенала…', key='arsenal_txt', title='Сохранить строку Арсенала',
                filetypes=[('Текст (*.txt)','*.txt')], mime='text/plain'
            )

        if _stage == '📤 Документы':
            st.markdown('### 6. Коммерческое предложение')
            st.caption('КП формируется по образцу БРОКТЕХНОЛОДЖИ: модель/реестровый номер, количество, цена за единицу, сумма, итог, исходящий номер и дата. Цены берутся из текущей сборки.')
            if 'kp_markup_pct' not in st.session_state:
                st.session_state.kp_markup_pct=float(st.session_state.settings.get('default_markup',0.20))*100
            if 'kp_mode' not in st.session_state:
                st.session_state.kp_mode='markup'
            if 'kp_warranty' not in st.session_state:
                tender_warranties=[int((x or {}).get('warranty_months_min') or 0) for x in st.session_state.reqs]
                st.session_state.kp_warranty=max([12]+tender_warranties)
            if 'kp_validity' not in st.session_state:
                st.session_state.kp_validity=30
            kp_today=date.today()
            if 'kp_seq' not in st.session_state or st.session_state.get('kp_seq_date') != kp_today.isoformat():
                st.session_state.kp_seq=next_sequence(kp_today)
                st.session_state.kp_seq_date=kp_today.isoformat()
            ka,kb,kc,kd=st.columns(4)
            kp_markup=ka.number_input('Наценка / маржа, %',min_value=0.0,max_value=99.0,value=float(st.session_state.kp_markup_pct),step=1.0,key='kp_markup_pct')
            mode_label=kb.selectbox('Как считать процент',['Наценка к себестоимости','Маржа от цены продажи'],index=0 if st.session_state.kp_mode=='markup' else 1,key='kp_mode_label')
            kp_mode='markup' if mode_label.startswith('Наценка') else 'margin'
            st.session_state.kp_mode=kp_mode
            kp_seq=kc.number_input('Порядковый № за сегодня',min_value=1,value=int(st.session_state.kp_seq),step=1,key='kp_seq')
            kp_warranty=kd.number_input('Гарантия в КП, мес.',min_value=1,value=int(st.session_state.kp_warranty),step=1,key='kp_warranty')
            ke,kf=st.columns([2,1])
            kp_out_default=outgoing_number(kp_today,int(kp_seq))
            if st.session_state.get('kp_outgoing_date_seq') != f'{kp_today.isoformat()}:{int(kp_seq)}':
                st.session_state.kp_outgoing=kp_out_default
                st.session_state.kp_outgoing_date_seq=f'{kp_today.isoformat()}:{int(kp_seq)}'
            kp_outgoing=ke.text_input('Исходящий номер',key='kp_outgoing')
            kp_validity=kf.number_input('Срок действия, дней',min_value=1,value=int(st.session_state.kp_validity),step=1,key='kp_validity')

            try:
                kp_items=build_offer_items(st.session_state.plans,kp_markup,kp_mode)
                preview=pd.DataFrame([{
                    'Наименование':x['name'],
                    'Реестровый номер':x['registry_number'],
                    'Количество':x['quantity'],
                    'Себестоимость/ед., ₽':round(x['unit_cost'],2),
                    'Цена КП/ед., ₽':round(x['unit_price'],2),
                    'Сумма, ₽':round(x['total'],2),
                } for x in kp_items])
                if not preview.empty:
                    st.dataframe(preview,hide_index=True,use_container_width=True)
                    zero_cost=[x for x in kp_items if float(x.get('unit_cost') or 0)<=0]
                    if zero_cost:
                        st.warning('В КП есть позиции с нулевой себестоимостью. Внеси цены комплектующих перед формированием итогового документа.')
                else:
                    st.info('Нет позиций с количеством больше нуля для КП.')
            except Exception as exc:
                kp_items=[]
                st.warning(f'Не удалось посчитать КП: {exc}')

            kp_fingerprint=hashlib.sha256(json.dumps({
                'items':kp_items,'markup':float(kp_markup),'mode':kp_mode,'outgoing':kp_outgoing,
                'warranty':int(kp_warranty),'validity':int(kp_validity),'date':kp_today.isoformat(),
            },ensure_ascii=False,sort_keys=True,default=str).encode('utf-8')).hexdigest()

            if st.button('Создать коммерческое предложение (.docx)',type='primary',use_container_width=True,disabled=not bool(kp_items)):
                try:
                    kp_bytes=build_commercial_offer(
                        kp_items,sequence=int(kp_seq),offer_date=kp_today,
                        warranty_months=int(kp_warranty),validity_days=int(kp_validity),outgoing=kp_outgoing,
                    )
                    st.session_state.kp_bytes=kp_bytes
                    st.session_state.kp_filename=f'{kp_outgoing}.docx'
                    st.session_state.kp_fingerprint=kp_fingerprint
                    reserve_sequence(kp_today,int(kp_seq))
                    st.success(f'КП сформировано: {kp_outgoing}')
                except Exception as exc:
                    st.error(f'Не удалось сформировать КП: {exc}')
            if st.session_state.get('kp_bytes') and st.session_state.get('kp_fingerprint') == kp_fingerprint:
                _save_controls(
                    st.session_state.kp_bytes, st.session_state.get('kp_filename','Коммерческое предложение.docx'),
                    label='Сохранить готовое КП…', key='commercial_offer', title='Сохранить коммерческое предложение',
                    filetypes=[('Word (*.docx)','*.docx')],
                    mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
            elif st.session_state.get('kp_bytes'):
                st.info('Параметры или расчёт изменились после создания КП. Нажми «Создать коммерческое предложение» ещё раз — старый файл не предлагается как актуальный.')

            st.markdown('### 7. Бекап расчёта')
            st.caption('Нажми «Сохранить бекап проекта…» и выбери нужную папку/имя файла. Потом его можно загрузить сверху и продолжить с теми же комплектующими, ценами, реестром, доставкой, БГ/ГО и полями Арсенала.')
            meta={'delivery':delivery,'bg':bg,'go':go,'project_qty':project_qty,'sender':sender,'country':country,'os_name':os_name,'trademark':trademark,'equipment':equipment,
                  'kp_markup_pct':float(st.session_state.get('kp_markup_pct',20.0)),'kp_mode':st.session_state.get('kp_mode','markup'),
                  'kp_warranty':int(st.session_state.get('kp_warranty',12)),'kp_validity':int(st.session_state.get('kp_validity',30))}
            st.session_state.project_meta=meta
            project_bytes=dump_project(reqs=st.session_state.reqs,plans=st.session_state.plans,source_text=st.session_state.source_text,
                qx_prices=st.session_state.qx_prices,project_meta=meta,settings_snapshot=st.session_state.settings,
                source_filename=st.session_state.source_filename,source_docx_bytes=st.session_state.source_docx_bytes,
                tender_overrides=st.session_state.tender_overrides,tender_characteristics=st.session_state.tender_characteristics)
            _autosave_current(project_bytes,{
                'reqs':st.session_state.reqs,'plans':st.session_state.plans,'meta':meta,'qx_prices':st.session_state.qx_prices,
                'tender_overrides':st.session_state.tender_overrides,'source_filename':st.session_state.source_filename
            })
            if st.session_state.get('_autosave_last_ok'):
                st.caption(f"Автосохранение активно · последнее сохранение {st.session_state.get('_autosave_last_at','')}. При следующем запуске незавершённый расчёт можно будет восстановить.")
            elif st.session_state.get('_autosave_error'):
                st.warning('Автосохранение не удалось: '+str(st.session_state.get('_autosave_error')))
            _save_controls(
                project_bytes, 'QX_расчёт.qxproj',
                label='Сохранить бекап проекта…', key='project_backup', title='Сохранить проект QX',
                filetypes=[('Проект QX (*.qxproj)','*.qxproj')], mime='application/json'
            )

        # Keep autosave alive regardless of which workspace stage is currently open.
        _auto_meta={'delivery':delivery,'bg':bg,'go':go,'project_qty':project_qty,'sender':sender,'country':country,'os_name':os_name,'trademark':trademark,'equipment':equipment,
                    'kp_markup_pct':float(st.session_state.get('kp_markup_pct',20.0)),'kp_mode':st.session_state.get('kp_mode','markup'),
                    'kp_warranty':int(st.session_state.get('kp_warranty',12)),'kp_validity':int(st.session_state.get('kp_validity',30))}
        st.session_state.project_meta=_auto_meta
        try:
            _auto_project_bytes=dump_project(reqs=st.session_state.reqs,plans=st.session_state.plans,source_text=st.session_state.source_text,
                qx_prices=st.session_state.qx_prices,project_meta=_auto_meta,settings_snapshot=st.session_state.settings,
                source_filename=st.session_state.source_filename,source_docx_bytes=st.session_state.source_docx_bytes,
                tender_overrides=st.session_state.tender_overrides,tender_characteristics=st.session_state.tender_characteristics)
            _autosave_current(_auto_project_bytes,{
                'reqs':st.session_state.reqs,'plans':st.session_state.plans,'meta':_auto_meta,'qx_prices':st.session_state.qx_prices,
                'tender_overrides':st.session_state.tender_overrides,'source_filename':st.session_state.source_filename
            })
        except Exception as _autosave_exc:
            st.session_state['_autosave_error']=str(_autosave_exc)

def _render_peripheral_db(kind, title, singular):
    st.subheader(title)
    st.caption(
        f'Отдельная переносимая база: {singular.lower()} один раз заполняется здесь, а затем программа автоматически использует её '
        'в самостоятельной позиции ТЗ и в составе АРМ/комплекта, если характеристики подтверждённо проходят требования. '
        'Цена может быть в ₽ или $, реестровый номер и связка с прайсом сохраняются вместе с моделью.'
    )
    st.caption(f'Основная база: {catalog_path()} · переносимая копия: {portable_catalog_path()}')
    records=catalog_list_items(kind); rmap={x['name']:x for x in records}; names=list(rmap)
    selected=st.selectbox(f'Сохранённые {title.lower().replace("база ","")}', ['— Новая позиция —']+names, key=f'{kind}_db_select')
    rec=rmap.get(selected); data=dict((rec or {}).get('data') or {})
    token=hashlib.sha1((str(selected)+':'+str(st.session_state.get(f'{kind}_db_rev',0))).encode('utf-8')).hexdigest()[:10]

    a,b,c,d,e=st.columns([3,1,1.3,1.5,1.6])
    name=a.text_input('Модель / название',value=str(data.get('name') or ((rec or {}).get('name') or '')),key=f'{kind}_db_name_{token}').strip()
    price_input=b.text_input('Цена, ₽ / $',value=_price_input_default(data,'price_input','price'),placeholder='$35',key=f'{kind}_db_price_{token}').strip()
    registry_number=c.text_input('Реестровый №',value=str(data.get('registry_number') or ''),key=f'{kind}_db_reg_{token}').strip()
    supplier=d.text_input('Поставщик прайса',value=str(data.get('supplier') or ''),placeholder='ExeGate',key=f'{kind}_db_supplier_{token}').strip()
    supplier_sku=e.text_input('Артикул / P/N',value=str(data.get('supplier_sku') or ''),placeholder='код или P/N',key=f'{kind}_db_sku_{token}').strip()
    price_rub,currency,price_note=_parse_catalog_price(price_input)
    if currency=='USD' and price_note: st.caption('Цена: '+price_note)
    if supplier and supplier_sku:
        spl=get_supplier_price_list(supplier); found=lookup_price(spl or {},supplier_sku) if spl else None
        if found and found.get('selected_price_usd') is not None:
            st.caption(f"Прайс {supplier}: {supplier_sku} → ${float(found['selected_price_usd']):g} ({found.get('selected_price_mode','')}, {(spl or {}).get('price_date','')}).")
        elif spl:
            st.caption(f'Артикул {supplier_sku} не найден в последнем прайсе «{supplier}».')

    payload={'name':name,'price_input':price_input,'price':float(price_rub),'price_conversion':price_note,
             'registry':bool(registry_number),'registry_number':registry_number,'supplier':supplier,'supplier_sku':supplier_sku}

    if kind=='monitor':
        a,b,c,d,e=st.columns(5)
        payload['inches']=float(a.number_input('Диагональ, ″',min_value=0.0,value=float(data.get('inches') or 0),step=.1,key=f'mon_inches_{token}'))
        payload['resolution']=b.text_input('Разрешение',value=str(data.get('resolution') or ''),placeholder='1920x1080',key=f'mon_res_{token}').strip()
        payload['matrix']=c.text_input('Матрица',value=str(data.get('matrix') or ''),placeholder='IPS',key=f'mon_matrix_{token}').strip()
        payload['refresh_hz']=int(d.number_input('Частота, Гц',min_value=0,value=int(data.get('refresh_hz') or 0),step=1,key=f'mon_hz_{token}'))
        payload['response_ms']=float(e.number_input('Отклик, мс',min_value=0.0,value=float(data.get('response_ms') or 0),step=.1,key=f'mon_resp_{token}'))
        a,b,c,d,e=st.columns(5)
        payload['brightness']=int(a.number_input('Яркость, кд/м²',min_value=0,value=int(data.get('brightness') or 0),step=10,key=f'mon_bright_{token}'))
        payload['contrast']=int(b.number_input('Контрастность (:1)',min_value=0,value=int(data.get('contrast') or 0),step=100,key=f'mon_contrast_{token}'))
        payload['view_angle_h']=int(c.number_input('Угол H, °',min_value=0,max_value=180,value=int(data.get('view_angle_h') or 0),step=1,key=f'mon_vah_{token}'))
        payload['view_angle_v']=int(d.number_input('Угол V, °',min_value=0,max_value=180,value=int(data.get('view_angle_v') or 0),step=1,key=f'mon_vav_{token}'))
        payload['color_depth_bits']=int(e.number_input('Глубина цвета, бит',min_value=0,value=int(data.get('color_depth_bits') or 0),step=1,key=f'mon_depth_{token}'))
        a,b,c=st.columns(3)
        payload['aspect_ratio']=a.text_input('Формат изображения',value=str(data.get('aspect_ratio') or ''),placeholder='16:9',key=f'mon_aspect_{token}').strip()
        payload['energy_class']=b.text_input('Класс энергоэффективности',value=str(data.get('energy_class') or ''),placeholder='A+',key=f'mon_energy_{token}').strip()
        payload['dynamic_contrast']=int(c.number_input('Динамическая контрастность (:1)',min_value=0,value=int(data.get('dynamic_contrast') or 0),step=1000,key=f'mon_dyn_{token}'))
        a,b,c=st.columns(3)
        payload['power_w']=float(a.number_input('Потребляемая мощность, Вт',min_value=0.0,value=float(data.get('power_w') or 0),step=1.0,key=f'mon_power_{token}'))
        payload['audio_in']=b.checkbox('Mini-Jack вход',value=bool(data.get('audio_in')),key=f'mon_audioin_{token}')
        payload['audio_out']=c.checkbox('Mini-Jack выход',value=bool(data.get('audio_out')),key=f'mon_audioout_{token}')
        a,b,c,d,e=st.columns(5)
        payload['interfaces']=a.text_input('Интерфейсы',value=str(data.get('interfaces') or ''),placeholder='VGA, HDMI, DisplayPort',key=f'mon_if_{token}').strip()
        payload['hdmi_ports']=int(b.number_input('HDMI, шт.',min_value=0,value=int(data.get('hdmi_ports') or 0),step=1,key=f'mon_hdmi_{token}'))
        payload['dp_ports']=int(c.number_input('DisplayPort, шт.',min_value=0,value=int(data.get('dp_ports') or 0),step=1,key=f'mon_dp_{token}'))
        payload['vesa']=d.text_input('VESA',value=str(data.get('vesa') or ''),placeholder='75 x 75',key=f'mon_vesa_{token}').strip()
        payload['cable_type']=e.text_input('Кабель в комплекте',value=str(data.get('cable_type') or ''),placeholder='HDMI-HDMI',key=f'mon_cable_{token}').strip()
        a,b,c,d,e=st.columns(5)
        payload['speakers']=a.checkbox('Динамики',value=bool(data.get('speakers')),key=f'mon_sp_{token}')
        payload['external_psu']=b.checkbox('Внешний БП',value=bool(data.get('external_psu')),key=f'mon_epsu_{token}')
        payload['wall_mount']=c.checkbox('Крепление на стену',value=bool(data.get('wall_mount')),key=f'mon_wall_{token}')
        payload['pivot']=d.checkbox('Портретный поворот',value=bool(data.get('pivot')),key=f'mon_pivot_{token}')
        payload['tilt']=e.checkbox('Регулировка наклона',value=bool(data.get('tilt')),key=f'mon_tilt_{token}')
        a,b,c,d,e,f=st.columns(6)
        payload['webcam']=a.checkbox('Веб-камера',value=bool(data.get('webcam')),key=f'mon_webcam_{token}')
        payload['touch']=b.checkbox('Сенсорный экран',value=bool(data.get('touch')),key=f'mon_touch_{token}')
        payload['usb_hub']=c.checkbox('USB-концентратор',value=bool(data.get('usb_hub')),key=f'mon_hub_{token}')
        payload['curved']=d.checkbox('Изогнутый экран',value=bool(data.get('curved')),key=f'mon_curved_{token}')
        payload['swivel']=e.checkbox('Поворот по горизонтали',value=bool(data.get('swivel')),key=f'mon_swivel_{token}')
        payload['cable_included']=f.checkbox('Кабель в комплекте',value=bool(data.get('cable_included')),key=f'mon_cable_inc_{token}')
    elif kind=='keyboard':
        a,b,c,d,e=st.columns(5)
        payload['wired']=a.checkbox('Проводная',value=bool(data.get('wired')),key=f'kb_wired_{token}')
        payload['wireless']=b.checkbox('Беспроводная',value=bool(data.get('wireless')),key=f'kb_wireless_{token}')
        payload['usb']=c.checkbox('USB',value=bool(data.get('usb')),key=f'kb_usb_{token}')
        payload['fullsize']=d.checkbox('Полноразмерная',value=bool(data.get('fullsize')),key=f'kb_full_{token}')
        payload['numeric_keypad']=e.checkbox('Цифровой блок',value=bool(data.get('numeric_keypad')),key=f'kb_num_{token}')
        a,b,c,d=st.columns(4)
        payload['layout']=a.text_input('Раскладка',value=str(data.get('layout') or ''),placeholder='ЙЦУКЕН',key=f'kb_layout_{token}').strip()
        payload['russification']=b.text_input('Русификация',value=str(data.get('russification') or ''),placeholder='Промышленный',key=f'kb_rus_{token}').strip()
        payload['keys']=int(c.number_input('Клавиш, шт.',min_value=0,value=int(data.get('keys') or 0),step=1,key=f'kb_keys_{token}'))
        payload['cable_m']=float(d.number_input('Длина кабеля, м',min_value=0.0,value=float(data.get('cable_m') or 0),step=.1,key=f'kb_cable_{token}'))
        bools=[('flexible','Гибкая'),('has_usb_port','USB-порт на клавиатуре'),('multifunction','Мультифункциональные клавиши'),('touchpad','Тачпад'),('palmrest','Подставка для рук'),('scroll_wheel','Колесо прокрутки'),('water_protection','Защита от воды'),('detachable_cable','Съёмный кабель'),('volume_control','Регулировка громкости'),('backlight','Подсветка')]
        cols=st.columns(5)
        for i,(k,lbl) in enumerate(bools[:5]): payload[k]=cols[i].checkbox(lbl,value=bool(data.get(k)),key=f'kb_{k}_{token}')
        cols=st.columns(5)
        for i,(k,lbl) in enumerate(bools[5:]): payload[k]=cols[i].checkbox(lbl,value=bool(data.get(k)),key=f'kb_{k}_{token}')
    else:
        a,b,c,d,e=st.columns(5)
        payload['wired']=a.checkbox('Проводная',value=bool(data.get('wired')),key=f'ms_wired_{token}')
        payload['wireless']=b.checkbox('Беспроводная',value=bool(data.get('wireless')),key=f'ms_wireless_{token}')
        payload['usb']=c.checkbox('USB',value=bool(data.get('usb')),key=f'ms_usb_{token}')
        payload['optical']=d.checkbox('Оптическая',value=bool(data.get('optical')),key=f'ms_opt_{token}')
        payload['silent_click']=e.checkbox('Тихий клик',value=bool(data.get('silent_click')),key=f'ms_silent_{token}')
        a,b,c,d=st.columns(4)
        payload['dpi']=int(a.number_input('DPI',min_value=0,value=int(data.get('dpi') or 0),step=100,key=f'ms_dpi_{token}'))
        payload['cable_m']=float(b.number_input('Длина кабеля, м',min_value=0.0,value=float(data.get('cable_m') or 0),step=.1,key=f'ms_cable_{token}'))
        payload['buttons']=int(c.number_input('Кнопок, шт.',min_value=0,value=int(data.get('buttons') or 0),step=1,key=f'ms_buttons_{token}'))
        d.caption('')
        a,b,c=st.columns(3)
        payload['programmable_buttons']=a.checkbox('Программируемые кнопки',value=bool(data.get('programmable_buttons')),key=f'ms_prog_{token}')
        payload['side_buttons']=b.checkbox('Боковые кнопки',value=bool(data.get('side_buttons')),key=f'ms_side_{token}')
        payload['detachable_cable']=c.checkbox('Съёмный кабель',value=bool(data.get('detachable_cable')),key=f'ms_detach_{token}')

    scol,dcol=st.columns([4,1])
    if scol.button(f'💾 Сохранить / обновить {singular.lower()}',type='primary',use_container_width=True,key=f'{kind}_db_save_{token}'):
        if not name:
            st.error('Укажи модель / название.')
        else:
            patched,stat=apply_latest_price_to_peripheral(payload)
            rub,cur,note=_parse_catalog_price(patched.get('price_input'))
            patched['price']=float(rub); patched['price_conversion']=note; patched['name']=name
            catalog_save_item(kind,name,patched)
            st.session_state['_catalog_status']=catalog_status(); st.session_state['_peripheral_catalog_changed']=True
            st.session_state[f'{kind}_db_rev']=int(st.session_state.get(f'{kind}_db_rev',0))+1
            msg=f'{singular} «{name}» сохранён' if kind!='keyboard' else f'{singular} «{name}» сохранена'
            if stat.get('updated'): msg+='; цена обновлена из последнего прайса.'
            else: msg+='.'
            st.success(msg)
            for miss in stat.get('missing') or []: st.warning(miss)
            st.rerun()
    if rec and dcol.button('Удалить',use_container_width=True,key=f'{kind}_db_delete_{token}'):
        if catalog_delete_item(kind,rec['name']):
            st.session_state['_catalog_status']=catalog_status(); st.session_state['_peripheral_catalog_changed']=True
            st.session_state[f'{kind}_db_rev']=int(st.session_state.get(f'{kind}_db_rev',0))+1
            st.rerun()
    if records:
        with st.expander('Список сохранённых моделей',expanded=False):
            st.dataframe(pd.DataFrame([{'Модель':x['name'],'Цена':_price_input_default(x.get('data') or {},'price_input','price'),'Реестровый №':(x.get('data') or {}).get('registry_number',''),'Поставщик':(x.get('data') or {}).get('supplier',''),'P/N':(x.get('data') or {}).get('supplier_sku','')} for x in records]),hide_index=True,use_container_width=True)

if _nav == '💵 Цены и прайсы':
    st.subheader('Актуальные цены QX')
    st.caption('Сборка зафиксирована 750 ₽ по текущему правилу пользователя. Все значения можно менять вручную.')
    qx_keys=list(st.session_state.qx_prices.keys())
    pdf=pd.DataFrame([{'key':k,'name':st.session_state.qx_prices[k]['name'],'price':float(st.session_state.qx_prices[k]['price'])} for k in qx_keys])
    qx_editor_key='qx_prices_editor_v04'
    st.data_editor(pdf,hide_index=True,use_container_width=True,num_rows='fixed',key=qx_editor_key,
        on_change=_sync_qx_price_editor,args=(qx_editor_key,qx_keys),
        column_config={'key':st.column_config.TextColumn('Код',disabled=True),'name':st.column_config.TextColumn('Наименование',width='large'),'price':st.column_config.NumberColumn('Цена, ₽',min_value=0.0,step=1.0,format='%.2f')})
    if st.button('Сохранить цены QX',type='primary'):
        save_prices(st.session_state.qx_prices); st.success('Сохранено.')

    st.divider()
    st.subheader('Импорт прайса поставщика')
    st.caption('Загрузи Excel поставщика один раз. Для ExeGate программа автоматически находит таблицу по колонкам «Код / P/N / Наименование» и умеет брать ОПТ, РРЦ или цену упаковки. Сохранённые платы, компоненты, корпуса, мониторы, клавиатуры и мыши с указанными Поставщиком + Артикулом/P/N обновятся автоматически.')
    _pi1,_pi2=st.columns([2,1])
    _supplier_name=_pi1.text_input('Название поставщика',value='ExeGate',key='supplier_price_name').strip() or 'ExeGate'
    _price_mode=_pi2.selectbox('Какую цену использовать',['ОПТ','РРЦ','Цена упаковки'],index=0,key='supplier_price_mode')
    _price_file=st.file_uploader('Прайс поставщика Excel (.xlsx)',type=['xlsx'],key='supplier_price_upload')
    if st.button('Импортировать прайс и обновить связанные цены',type='primary',use_container_width=True,disabled=_price_file is None,key='supplier_price_import_btn'):
        try:
            with st.spinner('Читаю прайс и обновляю локальную базу…'):
                _old_price=get_supplier_price_list(_supplier_name)
                _new_price=parse_supplier_price_excel(_price_file.getvalue(),_supplier_name,_price_mode)
                _cmp=compare_price_lists(_old_price,_new_price)
                save_supplier_price_list(_supplier_name,_new_price)
                _upd=update_all_linked_profiles(_supplier_name)
                _current_links_updated=0
                for _reqd in st.session_state.reqs:
                    if str((_reqd or {}).get('custom_case_supplier') or '').strip().casefold() != _supplier_name.casefold():
                        continue
                    _sku=str((_reqd or {}).get('custom_case_supplier_sku') or '').strip()
                    _found=lookup_price(_new_price,_sku) if _sku else None
                    if _found and _found.get('selected_price_usd') is not None:
                        _reqd['custom_case_price_input']=f"${float(_found['selected_price_usd']):g}"
                        _rub,_cur,_note=_parse_catalog_price(_reqd['custom_case_price_input'])
                        _reqd['custom_case_price']=float(_rub); _reqd['custom_case_price_conversion']=_note
                        _current_links_updated+=1
                _preview=[{
                    'Код':x.get('code'),'P/N':x.get('part_number'),'Наименование':x.get('name'),
                    'ОПТ, $':x.get('price_opt_usd'),'РРЦ, $':x.get('price_rrp_usd'),'Выбрано, $':x.get('selected_price_usd'),
                    'Остаток':x.get('stock')
                } for x in (_new_price.get('items') or [])[:80]]
                st.session_state['_last_price_import']={'supplier':_supplier_name,'sheet':_new_price.get('sheet'),'date':_new_price.get('price_date'),'cmp':_cmp,'upd':_upd,'count':_new_price.get('item_count'),'current_links_updated':_current_links_updated}
                st.session_state['_last_price_preview']=_preview
                st.session_state['equipment_db_rev']=int(st.session_state.get('equipment_db_rev',0))+1
                if int(_upd.get('rows_updated') or 0)>0:
                    st.session_state['_peripheral_catalog_changed']=True
                if st.session_state.plans and (int(_upd.get('rows_updated') or 0)>0 or _current_links_updated>0):
                    _build_plans_from_current_requirements()
            st.rerun()
        except Exception as _exc:
            st.error(f'Не удалось импортировать прайс: {_exc}')

    _last_pi=st.session_state.get('_last_price_import')
    if _last_pi:
        _cmp=_last_pi.get('cmp') or {}; _upd=_last_pi.get('upd') or {}
        st.success(f"Прайс «{_last_pi.get('supplier')}» импортирован: {_last_pi.get('count',0)} позиций · лист «{_last_pi.get('sheet','')}» · дата {_last_pi.get('date') or 'не определена'}.")
        _m1,_m2,_m3,_m4=st.columns(4)
        _m1.metric('Цен изменилось',int(_cmp.get('changed') or 0))
        _m2.metric('Новых позиций',int(_cmp.get('new') or 0))
        _m3.metric('Пропало из прайса',int(_cmp.get('missing') or 0))
        _m4.metric('Связанных цен обновлено',int(_upd.get('rows_updated') or 0))
        _pt=_upd.get('peripherals_touched') or {}
        if _upd.get('profiles_touched') or _upd.get('cases_touched') or any(_pt.values()) or _last_pi.get('current_links_updated'):
            st.caption(f"Обновлено: базы оборудования {_upd.get('profiles_touched',0)} · корпуса {_upd.get('cases_touched',0)} · моноблочные платформы {_upd.get('aio_touched',0)} · мониторы {_pt.get('monitor',0)} · клавиатуры {_pt.get('keyboard',0)} · мыши {_pt.get('mouse',0)} · корпуса в текущем расчёте {_last_pi.get('current_links_updated',0)}. Цены $ при расчёте пересчитываются по текущему курсу + запас.")
        for _miss in (_upd.get('missing') or [])[:10]: st.warning(_miss)
        _pv=st.session_state.get('_last_price_preview') or []
        if _pv:
            with st.expander('Показать первые позиции из распознанного прайса',expanded=False):
                st.dataframe(pd.DataFrame(_pv),hide_index=True,use_container_width=True)

    _saved_prices=list_supplier_price_lists()
    if _saved_prices:
        with st.expander('Сохранённые прайсы',expanded=False):
            st.dataframe(pd.DataFrame([{
                'Поставщик':x.get('name'),
                'Дата прайса':(x.get('data') or {}).get('price_date'),
                'Тип цены':(x.get('data') or {}).get('price_mode'),
                'Позиций':(x.get('data') or {}).get('item_count'),
                'Импортирован':(x.get('data') or {}).get('imported_at'),
            } for x in _saved_prices]),hide_index=True,use_container_width=True)

if _nav == '🗄️ База корпусов':
    st.subheader('База корпусов')
    st.caption(
        'Отдельная база корпусов — как с «Бештау», только именно для корпусов. '
        'Здесь можно один раз сохранить модель корпуса, его размеры, отсеки, передние USB-порты, признак защищённого корпуса, '
        'а также цену в ₽ или $ и связку с прайсом поставщика. Потом этот корпус выбирается в расчёте из сохранённой базы.'
    )
    st.caption(f'Основная база: {catalog_path()} · переносимая копия: {portable_catalog_path()}')

    _saved_cases = catalog_list_items('case')
    _case_map = {x['name']: x for x in _saved_cases}
    _case_names = list(_case_map)
    _selected_case = st.selectbox(
        'Сохранённые корпуса', ['— Новый корпус —'] + _case_names,
        key='case_db_manage_select',
        help='Эта вкладка — отдельный справочник корпусов. Записи хранятся в той же переносимой базе и переживают обновления программы.'
    )
    _case_rec = _case_map.get(_selected_case)
    _case_data = dict((_case_rec or {}).get('data') or {})
    _case_token = hashlib.sha1((str(_selected_case)+':'+str(st.session_state.get('case_db_rev',0))).encode('utf-8')).hexdigest()[:10]

    h1,h2,h3,h4 = st.columns([3,1,1,1.4])
    _case_name = h1.text_input('Модель / название корпуса', value=str(_case_data.get('custom_case_name') or ((_case_rec or {}).get('name') or '')), placeholder='Например: ExeGate BAA-104U', key=f'case_db_name_{_case_token}').strip()
    _case_price_default = _price_input_default(_case_data, 'custom_case_price_input', 'custom_case_price')
    _case_price_input = h2.text_input('Цена корпуса, ₽ / $', value=_case_price_default, placeholder='3500 или $35', key=f'case_db_price_{_case_token}').strip()
    _case_supplier = h3.text_input('Поставщик', value=str(_case_data.get('custom_case_supplier') or ''), placeholder='ExeGate', key=f'case_db_supplier_{_case_token}').strip()
    _case_supplier_sku = h4.text_input('Артикул / P/N', value=str(_case_data.get('custom_case_supplier_sku') or ''), placeholder='EX.... или код', key=f'case_db_supplier_sku_{_case_token}').strip()
    _case_rub, _case_currency, _case_note = _parse_catalog_price(_case_price_input)
    if _case_currency == 'USD' and _case_note:
        st.caption('Цена корпуса: ' + _case_note)
    if _case_supplier and _case_supplier_sku:
        _sp = get_supplier_price_list(_case_supplier)
        _si = lookup_price(_sp or {}, _case_supplier_sku) if _sp else None
        if _si and _si.get('selected_price_usd') is not None:
            st.caption(f"Прайс {_case_supplier}: {_case_supplier_sku} → ${float(_si['selected_price_usd']):g} ({_si.get('selected_price_mode','')}, {(_sp or {}).get('price_date','')}). При сохранении корпуса эта цена будет подставлена автоматически.")
        elif _sp:
            st.caption(f"В последнем прайсе «{_case_supplier}» артикул {_case_supplier_sku} не найден.")

    st.caption('Заполни реальные характеристики корпуса. Они будут участвовать в проверке ТЗ и попадут в фактические характеристики. Программа ничего не додумывает.')
    a,b,c,d = st.columns(4)
    _case_width_mm = num(a,'Ширина, мм',_case_data,'custom_case_width_mm')
    _case_length_mm = num(b,'Длина, мм',_case_data,'custom_case_length_mm')
    _case_height_mm = num(c,'Высота, мм',_case_data,'custom_case_height_mm')
    _case_protected = d.checkbox('Защищённый / спецкорпус', bool(_case_data.get('custom_case_protected')), key=f'case_db_protected_{_case_token}')

    a,b,c,d = st.columns(4)
    _case_bay_525 = int(a.number_input('Отсеки 5,25', min_value=0, value=int(_case_data.get('custom_case_bay_525') or 0), step=1, key=f'case_db_bay525_{_case_token}'))
    _case_bay_25 = int(b.number_input('Отсеки 2,5', min_value=0, value=int(_case_data.get('custom_case_bay_25') or 0), step=1, key=f'case_db_bay25_{_case_token}'))
    _case_bay_325 = int(c.number_input('Отсеки 3,25', min_value=0, value=int(_case_data.get('custom_case_bay_325') or 0), step=1, key=f'case_db_bay325_{_case_token}'))
    _case_bay_35 = int(d.number_input('Внутренние отсеки 3,5', min_value=0, value=int(_case_data.get('custom_case_bay_35') or 0), step=1, key=f'case_db_bay35_{_case_token}'))
    a,b,c=st.columns(3)
    _case_bay_35_external=int(a.number_input('Внешние отсеки 3,5',min_value=0,value=int(_case_data.get('custom_case_bay_35_external') or 0),step=1,key=f'case_db_bay35ext_{_case_token}'))
    _case_front_audio_out=b.checkbox('Аудиовыход спереди',value=bool(_case_data.get('custom_case_front_audio_out')),key=f'case_db_audioout_{_case_token}')
    _case_front_mic_in=c.checkbox('Микрофонный вход спереди',value=bool(_case_data.get('custom_case_front_mic_in')),key=f'case_db_micin_{_case_token}')

    st.markdown('**Передние порты корпуса**')
    a,b,c,d,e = st.columns(5)
    _case_usb2_front = int(a.number_input('USB2 A', min_value=0, value=int(_case_data.get('custom_case_usb2_front') or 0), step=1, key=f'case_db_usb2_{_case_token}'))
    _case_gen1_a_front = int(b.number_input('Gen1 A', min_value=0, value=int(_case_data.get('custom_case_gen1_a_front') or 0), step=1, key=f'case_db_g1a_{_case_token}'))
    _case_gen1_c_front = int(c.number_input('Gen1 C', min_value=0, value=int(_case_data.get('custom_case_gen1_c_front') or 0), step=1, key=f'case_db_g1c_{_case_token}'))
    _case_gen2_a_front = int(d.number_input('Gen2 A', min_value=0, value=int(_case_data.get('custom_case_gen2_a_front') or 0), step=1, key=f'case_db_g2a_{_case_token}'))
    _case_gen2_c_front = int(e.number_input('Gen2 C', min_value=0, value=int(_case_data.get('custom_case_gen2_c_front') or 0), step=1, key=f'case_db_g2c_{_case_token}'))

    _case_payload = {
        'custom_case_name': _case_name or 'Другой корпус',
        'custom_case_price_input': _case_price_input,
        'custom_case_price': float(_case_rub),
        'custom_case_price_conversion': _case_note,
        'custom_case_width_mm': int(_case_width_mm or 0),
        'custom_case_length_mm': int(_case_length_mm or 0),
        'custom_case_height_mm': int(_case_height_mm or 0),
        'custom_case_bay_525': int(_case_bay_525 or 0),
        'custom_case_bay_25': int(_case_bay_25 or 0),
        'custom_case_bay_325': int(_case_bay_325 or 0),
        'custom_case_bay_35': int(_case_bay_35 or 0),
        'custom_case_bay_35_external': int(_case_bay_35_external or 0),
        'custom_case_front_audio_out': bool(_case_front_audio_out),
        'custom_case_front_mic_in': bool(_case_front_mic_in),
        'custom_case_usb2_front': int(_case_usb2_front or 0),
        'custom_case_gen1_a_front': int(_case_gen1_a_front or 0),
        'custom_case_gen1_c_front': int(_case_gen1_c_front or 0),
        'custom_case_gen2_a_front': int(_case_gen2_a_front or 0),
        'custom_case_gen2_c_front': int(_case_gen2_c_front or 0),
        'custom_case_protected': bool(_case_protected),
        'custom_case_supplier': _case_supplier,
        'custom_case_supplier_sku': _case_supplier_sku,
    }

    save_col, delete_col = st.columns([4,1])
    if save_col.button('💾 Сохранить / обновить корпус', type='primary', use_container_width=True, key=f'case_db_save_{_case_token}'):
        if not _case_name or _case_name == 'Другой корпус':
            st.error('Укажи нормальное название/модель корпуса.')
        else:
            _patched_payload, _case_price_stat = apply_latest_price_to_case(_case_payload)
            _rub,_cur,_note = _parse_catalog_price(_patched_payload.get('custom_case_price_input'))
            _patched_payload['custom_case_price'] = float(_rub)
            _patched_payload['custom_case_price_conversion'] = _note
            catalog_save_item('case', _case_name, _patched_payload)
            st.session_state['_catalog_status'] = catalog_status()
            _msg = f'Корпус «{_case_name}» сохранён в отдельной базе корпусов.'
            if _case_price_stat.get('updated'):
                _msg += ' Цена автоматически взята из последнего прайса поставщика.'
            st.success(_msg)
            for _miss in _case_price_stat.get('missing') or []:
                st.warning(_miss)
            st.session_state['case_db_rev'] = int(st.session_state.get('case_db_rev',0)) + 1
            st.rerun()

    if _case_rec:
        if delete_col.button('Удалить', use_container_width=True, key=f'case_db_delete_{_case_token}'):
            if catalog_delete_item('case', _case_rec['name']):
                st.session_state['_catalog_status'] = catalog_status()
                st.session_state['case_db_rev'] = int(st.session_state.get('case_db_rev',0)) + 1
                st.success(f'Корпус «{_case_rec["name"]}» удалён.')
                st.rerun()

    if _saved_cases:
        with st.expander('Список сохранённых корпусов', expanded=False):
            _rows = []
            for _it in _saved_cases:
                _d = dict(_it.get('data') or {})
                _rows.append({
                    'Название': _it.get('name'),
                    'Цена': _price_input_default(_d, 'custom_case_price_input', 'custom_case_price'),
                    'Поставщик': _d.get('custom_case_supplier') or '',
                    'Артикул / P/N': _d.get('custom_case_supplier_sku') or '',
                    'Ш×Д×В, мм': f"{int(_d.get('custom_case_width_mm') or 0)}×{int(_d.get('custom_case_length_mm') or 0)}×{int(_d.get('custom_case_height_mm') or 0)}",
                    'Отсеки 2,5 / 3,5': f"{int(_d.get('custom_case_bay_25') or 0)} / {int(_d.get('custom_case_bay_35') or 0)}",
                    'Защищённый': 'Да' if _d.get('custom_case_protected') else 'Нет',
                })
            st.dataframe(pd.DataFrame(_rows), hide_index=True, use_container_width=True)



if _nav == '🖥️ Моноблочные платформы':
    st.subheader('База моноблочных платформ')
    st.caption(
        'Отдельная переносимая база моноблочных платформ. Здесь можно один раз сохранить модель платформы, цену в ₽ или $, '
        'характеристики дисплея/БП/портов и при необходимости привязку к прайсу поставщика. '
        'После этого платформа появляется в расчёте в разделе «Моноблочная платформа: QX или другая».'
    )
    st.caption(f'Основная база: {catalog_path()} · переносимая копия: {portable_catalog_path()}')

    _aio_records=catalog_list_items('aio')
    _aio_map={x['name']:x for x in _aio_records}
    _aio_names=list(_aio_map)
    _aio_selected=st.selectbox('Сохранённые моноблочные платформы',['— Новая платформа —']+_aio_names,key='aio_db_manage_select')
    _aio_rec=_aio_map.get(_aio_selected)
    _aio_data=dict((_aio_rec or {}).get('data') or {})
    _aio_token=hashlib.sha1((str(_aio_selected)+':'+str(st.session_state.get('aio_db_rev',0))).encode('utf-8')).hexdigest()[:10]

    a,b,c,d=st.columns([3,1.3,1.3,1.5])
    _aio_name=a.text_input('Название платформы',value=str(_aio_data.get('custom_aio_name') or ((_aio_rec or {}).get('name') or '')),placeholder='Например: платформа 23.8″ IPS',key=f'aio_db_name_{_aio_token}').strip()
    _aio_price_input=b.text_input('Цена, ₽ / $',value=_price_input_default(_aio_data,'custom_aio_price_input','custom_aio_price'),placeholder='25000 или $280',key=f'aio_db_price_{_aio_token}').strip()
    _aio_supplier=c.text_input('Поставщик прайса',value=str(_aio_data.get('custom_aio_supplier') or ''),placeholder='Поставщик',key=f'aio_db_supplier_{_aio_token}').strip()
    _aio_supplier_sku=d.text_input('Артикул / P/N',value=str(_aio_data.get('custom_aio_supplier_sku') or ''),placeholder='код или P/N',key=f'aio_db_sku_{_aio_token}').strip()
    _aio_rub,_aio_currency,_aio_note=_parse_catalog_price(_aio_price_input)
    if _aio_currency=='USD' and _aio_note:
        st.caption('Цена платформы: '+_aio_note)
    if _aio_supplier and _aio_supplier_sku:
        _spl=get_supplier_price_list(_aio_supplier); _found=lookup_price(_spl or {},_aio_supplier_sku) if _spl else None
        if _found and _found.get('selected_price_usd') is not None:
            st.caption(f"Прайс {_aio_supplier}: {_aio_supplier_sku} → ${float(_found['selected_price_usd']):g} ({_found.get('selected_price_mode','')}, {(_spl or {}).get('price_date','')}). При сохранении цена будет обновлена из прайса.")
        elif _spl:
            st.caption(f'Артикул {_aio_supplier_sku} не найден в последнем прайсе «{_aio_supplier}».')

    a,b,c,d=st.columns(4)
    _aio_diag=float(a.number_input('Диагональ, ″',min_value=0.0,value=float(_aio_data.get('custom_aio_diagonal_in') or 0),step=.1,key=f'aio_db_diag_{_aio_token}'))
    _aio_res=b.text_input('Разрешение',value=str(_aio_data.get('custom_aio_resolution') or ''),placeholder='1920x1080',key=f'aio_db_res_{_aio_token}').strip()
    _aio_hz=int(c.number_input('Частота, Гц',min_value=0,value=int(_aio_data.get('custom_aio_refresh_hz') or 0),step=1,key=f'aio_db_hz_{_aio_token}'))
    _aio_matrix=d.text_input('Матрица',value=str(_aio_data.get('custom_aio_matrix') or ''),placeholder='IPS',key=f'aio_db_matrix_{_aio_token}').strip()

    a,b,c=st.columns(3)
    _aio_card=a.checkbox('Встроенный картридер',value=bool(_aio_data.get('custom_aio_built_in_cardreader')),key=f'aio_db_card_{_aio_token}')
    _aio_integrated_psu=b.checkbox('БП встроен в платформу',value=bool(_aio_data.get('custom_aio_integrated_psu',True)),key=f'aio_db_ipsu_{_aio_token}')
    _aio_psu_w=int(c.number_input('Мощность встроенного БП, Вт',min_value=0,value=int(_aio_data.get('custom_aio_psu_w') or 0),step=10,key=f'aio_db_psuw_{_aio_token}'))

    st.markdown('**Порты самой платформы сверх задней панели материнской платы**')
    a,b,c,d,e=st.columns(5)
    _aio_usb2=int(a.number_input('USB2 A',min_value=0,value=int(_aio_data.get('custom_aio_usb2_a') or 0),step=1,key=f'aio_db_usb2_{_aio_token}'))
    _aio_g1a=int(b.number_input('Gen1 A',min_value=0,value=int(_aio_data.get('custom_aio_gen1_a') or 0),step=1,key=f'aio_db_g1a_{_aio_token}'))
    _aio_g1c=int(c.number_input('Gen1 C',min_value=0,value=int(_aio_data.get('custom_aio_gen1_c') or 0),step=1,key=f'aio_db_g1c_{_aio_token}'))
    _aio_g2a=int(d.number_input('Gen2 A',min_value=0,value=int(_aio_data.get('custom_aio_gen2_a') or 0),step=1,key=f'aio_db_g2a_{_aio_token}'))
    _aio_g2c=int(e.number_input('Gen2 C',min_value=0,value=int(_aio_data.get('custom_aio_gen2_c') or 0),step=1,key=f'aio_db_g2c_{_aio_token}'))

    st.markdown('**Из них на передней панели**')
    a,b,c=st.columns(3)
    _aio_front_usb2=int(a.number_input('USB2 спереди',min_value=0,value=int(_aio_data.get('custom_aio_front_usb2') or 0),step=1,key=f'aio_db_fusb2_{_aio_token}'))
    _aio_front_a=int(b.number_input('Type-A спереди',min_value=0,value=int(_aio_data.get('custom_aio_front_a') or 0),step=1,key=f'aio_db_fa_{_aio_token}'))
    _aio_front_c=int(c.number_input('Type-C спереди',min_value=0,value=int(_aio_data.get('custom_aio_front_c') or 0),step=1,key=f'aio_db_fc_{_aio_token}'))

    _aio_payload={
        'custom_aio_name':_aio_name,
        'custom_aio_price_input':_aio_price_input,
        'custom_aio_price':float(_aio_rub),
        'custom_aio_price_conversion':_aio_note,
        'custom_aio_supplier':_aio_supplier,
        'custom_aio_supplier_sku':_aio_supplier_sku,
        'custom_aio_diagonal_in':_aio_diag,
        'custom_aio_resolution':_aio_res,
        'custom_aio_refresh_hz':_aio_hz,
        'custom_aio_matrix':_aio_matrix,
        'custom_aio_built_in_cardreader':bool(_aio_card),
        'custom_aio_integrated_psu':bool(_aio_integrated_psu),
        'custom_aio_psu_w':_aio_psu_w,
        'custom_aio_usb2_a':_aio_usb2,
        'custom_aio_gen1_a':_aio_g1a,
        'custom_aio_gen1_c':_aio_g1c,
        'custom_aio_gen2_a':_aio_g2a,
        'custom_aio_gen2_c':_aio_g2c,
        'custom_aio_front_usb2':_aio_front_usb2,
        'custom_aio_front_a':_aio_front_a,
        'custom_aio_front_c':_aio_front_c,
    }
    save_col,delete_col=st.columns([4,1])
    if save_col.button('💾 Сохранить / обновить моноблочную платформу',type='primary',use_container_width=True,key=f'aio_db_save_{_aio_token}'):
        if not _aio_name:
            st.error('Укажи название платформы.')
        else:
            _patched,_stat=apply_latest_price_to_aio(_aio_payload)
            _rub,_cur,_note=_parse_catalog_price(_patched.get('custom_aio_price_input'))
            _patched['custom_aio_price']=float(_rub); _patched['custom_aio_price_conversion']=_note
            catalog_save_item('aio',_aio_name,_patched)
            st.session_state['_catalog_status']=catalog_status()
            _msg=f'Моноблочная платформа «{_aio_name}» сохранена.'
            if _stat.get('updated'): _msg+=' Цена автоматически взята из последнего прайса поставщика.'
            st.success(_msg)
            for _miss in _stat.get('missing') or []: st.warning(_miss)
            st.session_state['aio_db_rev']=int(st.session_state.get('aio_db_rev',0))+1
            st.rerun()
    if _aio_rec:
        if delete_col.button('Удалить',use_container_width=True,key=f'aio_db_delete_{_aio_token}'):
            if catalog_delete_item('aio',_aio_rec['name']):
                st.session_state['_catalog_status']=catalog_status(); st.session_state['aio_db_rev']=int(st.session_state.get('aio_db_rev',0))+1
                st.success(f'Платформа «{_aio_rec["name"]}» удалена.')
                st.rerun()

    if _aio_records:
        with st.expander('Список сохранённых моноблочных платформ',expanded=False):
            _rows=[]
            for _r in _aio_records:
                _d=dict(_r.get('data') or {})
                _rows.append({
                    'Название':_r.get('name'),
                    'Цена':_price_input_default(_d,'custom_aio_price_input','custom_aio_price'),
                    'Поставщик':_d.get('custom_aio_supplier') or '',
                    'Артикул / P/N':_d.get('custom_aio_supplier_sku') or '',
                    'Экран':f"{float(_d.get('custom_aio_diagonal_in') or 0):g}″ {str(_d.get('custom_aio_resolution') or '')} {str(_d.get('custom_aio_matrix') or '')}".strip(),
                    'Гц':int(_d.get('custom_aio_refresh_hz') or 0),
                    'БП, Вт':int(_d.get('custom_aio_psu_w') or 0),
                })
            st.dataframe(pd.DataFrame(_rows),hide_index=True,use_container_width=True)


if _nav == '🖵 База мониторов':
    _render_peripheral_db('monitor','База мониторов','Монитор')

if _nav == '⌨️ База клавиатур':
    _render_peripheral_db('keyboard','База клавиатур','Клавиатура')

if _nav == '🖱️ База мышей':
    _render_peripheral_db('mouse','База мышей','Мышь')

if _nav == '🧩 База оборудования':
    st.subheader('База другого оборудования')
    st.caption(
        'Здесь создаются свои базы комплектующих по производителю или линейке — например «Бештау». '
        'В такой базе можно сохранить материнскую плату, её реальные характеристики, цену и реестровый номер, '
        'а также любые дополнительные реестровые компоненты. После этого в позиции ТЗ выбираешь эту базу, '
        'и сохранённое оборудование подставляется автоматически.'
    )
    st.caption(f'Основная база: {catalog_path()} · переносимая копия: {portable_catalog_path()}')

    _profiles = catalog_list_items('equipment_profile')
    _profile_map = {x['name']: x for x in _profiles}
    _profile_names = list(_profile_map)
    _selected_profile = st.selectbox(
        'Сохранённые базы / производители', ['— Новая база —'] + _profile_names,
        key='equip_profile_manage_select',
        help='Одна база может содержать AMD-плату, Intel-плату и набор реестровых/дополнительных компонентов со своими ценами.'
    )
    _profile_rec = _profile_map.get(_selected_profile)
    _profile_data = dict((_profile_rec or {}).get('data') or {})
    _profile_token = hashlib.sha1((str(_selected_profile)+':'+str(st.session_state.get('equipment_db_rev',0))).encode('utf-8')).hexdigest()[:10]

    _head1, _head2 = st.columns([2, 2])
    _profile_name = _head1.text_input(
        'Название базы', value=(_profile_rec or {}).get('name', ''),
        placeholder='Например: Бештау', key=f'equip_profile_name_{_profile_token}'
    ).strip()
    _manufacturer = _head2.text_input(
        'Производитель / источник', value=str(_profile_data.get('manufacturer') or ((_profile_rec or {}).get('name') or '')),
        placeholder='Например: Бештау', key=f'equip_manufacturer_{_profile_token}'
    ).strip()
    if _profile_rec:
        st.caption('Если изменить «Название базы» и сохранить, будет создана отдельная копия. Старую запись это не удалит.')

    def _board_editor(_platform, _title, _raw, _token):
        _raw = dict(_raw or {})
        with st.expander(_title, expanded=bool(_raw.get('name'))):
            _enabled = st.checkbox(
                f'Использовать {_title.lower()} в этой базе',
                value=bool(str(_raw.get('name') or '').strip()), key=f'eq_board_enabled_{_platform}_{_token}'
            )
            if not _enabled:
                st.caption('Эта платформа не будет предлагаться при подборе из данной базы.')
                return None

            a,b,c = st.columns([3,1,1])
            _name = a.text_input('Модель материнской платы', value=str(_raw.get('name') or ''), placeholder='Бештау ...', key=f'eq_board_name_{_platform}_{_token}').strip()
            _price_input = b.text_input('Цена, ₽ / $', value=_price_input_default(_raw), placeholder='$80', key=f'eq_board_price_input_{_platform}_{_token}').strip()
            _price, _price_currency, _price_note = _parse_catalog_price(_price_input)
            _registry = c.checkbox('Реестровая', value=bool(_raw.get('registry')), key=f'eq_board_registry_{_platform}_{_token}')
            if _price_currency == 'USD' and _price_note:
                st.caption(f'{_title}: {_price_note}')
            _registry_number = st.text_input('Реестровый номер платы / компонента', value=str(_raw.get('registry_number') or ''), key=f'eq_board_regnum_{_platform}_{_token}').strip()
            _sup1,_sup2=st.columns(2)
            _supplier=_sup1.text_input('Поставщик прайса',value=str(_raw.get('supplier') or ''),placeholder='ExeGate',key=f'eq_board_supplier_{_platform}_{_token}').strip()
            _supplier_sku=_sup2.text_input('Артикул / P/N из прайса',value=str(_raw.get('supplier_sku') or ''),placeholder='EX123... или код',key=f'eq_board_supplier_sku_{_platform}_{_token}').strip()
            if _supplier and _supplier_sku:
                _spl=get_supplier_price_list(_supplier)
                _found=lookup_price(_spl or {},_supplier_sku) if _spl else None
                if _found and _found.get('selected_price_usd') is not None:
                    st.caption(f"Связка с прайсом: {_supplier_sku} → ${float(_found['selected_price_usd']):g} ({_found.get('selected_price_mode','')}, {(_spl or {}).get('price_date','')}). При сохранении базы цена подставится автоматически.")
                elif _spl:
                    st.caption(f'Артикул {_supplier_sku} не найден в последнем прайсе «{_supplier}».')

            a,b,c,d = st.columns(4)
            _socket = a.text_input('Сокет', value=str(_raw.get('socket') or ''), placeholder='AM4 / LGA1700', key=f'eq_board_socket_{_platform}_{_token}').strip()
            _chipset = b.text_input('Чипсет', value=str(_raw.get('chipset') or ''), key=f'eq_board_chipset_{_platform}_{_token}').strip()
            _form = c.text_input('Форм-фактор', value=str(_raw.get('form_factor') or ''), placeholder='mATX', key=f'eq_board_form_{_platform}_{_token}').strip()
            _ram_options = ['', 'DDR4', 'DDR5']
            _ram_cur = str(_raw.get('ram_type') or '').upper()
            if _ram_cur not in _ram_options: _ram_cur = ''
            _ram_type = d.selectbox('Тип ОЗУ', _ram_options, index=_ram_options.index(_ram_cur), format_func=lambda x: x or 'не указан', key=f'eq_board_ramtype_{_platform}_{_token}')

            a,b,c,d = st.columns(4)
            _ram_max_gb = a.number_input('Макс. ОЗУ, ГБ', min_value=0, value=int(_raw.get('ram_max_gb') or 0), step=1, key=f'eq_board_rammax_{_platform}_{_token}')
            _ram_max_mhz = b.number_input('Макс. частота ОЗУ, МГц', min_value=0, value=int(_raw.get('ram_max_mhz') or 0), step=100, key=f'eq_board_rammhz_{_platform}_{_token}')
            _ram_slots = c.number_input('Слотов ОЗУ', min_value=0, value=int(_raw.get('ram_slots') or 0), step=1, key=f'eq_board_ramslots_{_platform}_{_token}')
            _sata = d.number_input('SATA', min_value=0, value=int(_raw.get('sata') or 0), step=1, key=f'eq_board_sata_{_platform}_{_token}')

            a,b,c,d = st.columns(4)
            _m2m = a.number_input('M.2 Key M', min_value=0, value=int(_raw.get('m2_key_m') or 0), step=1, key=f'eq_board_m2m_{_platform}_{_token}')
            _m2e = b.number_input('M.2 Key E', min_value=0, value=int(_raw.get('m2_key_e') or 0), step=1, key=f'eq_board_m2e_{_platform}_{_token}')
            _pcie1 = c.number_input('PCIe x1', min_value=0, value=int(_raw.get('pcie_x1') or 0), step=1, key=f'eq_board_pcie1_{_platform}_{_token}')
            _pcie16 = d.number_input('PCIe x16', min_value=0, value=int(_raw.get('pcie_x16') or 0), step=1, key=f'eq_board_pcie16_{_platform}_{_token}')

            a,b,c = st.columns(3)
            _eth_mbps = a.number_input('Ethernet, Мбит/с', min_value=0, value=int(_raw.get('ethernet_mbps') or 0), step=100, key=f'eq_board_ethspeed_{_platform}_{_token}')
            _eth_ports = b.number_input('RJ-45, шт.', min_value=0, value=int(_raw.get('ethernet_ports') or 0), step=1, key=f'eq_board_ethports_{_platform}_{_token}')
            _tpm = c.number_input('Разъём TPM, шт.', min_value=0, value=int(_raw.get('tpm_header') or 0), step=1, key=f'eq_board_tpm_{_platform}_{_token}')
            def _tri_db(label,keyname):
                _val=_raw.get(keyname,None); _opts=['Не указано','Да','Нет']; _cur='Не указано' if _val is None else ('Да' if bool(_val) else 'Нет')
                _sel=st.selectbox(label,_opts,index=_opts.index(_cur),key=f'eq_board_{keyname}_{_platform}_{_token}')
                return None if _sel=='Не указано' else (_sel=='Да')
            a,b,c=st.columns(3)
            with a: _raid=_tri_db('RAID 0/1/5/10','raid_0_1_5_10')
            with b: _audio_out=_tri_db('Встроенный аудиовыход','audio_out')
            with c: _mic_in=_tri_db('Встроенный микрофонный вход','mic_in')

            st.markdown('**Видеовыходы платы**')
            _video = dict(_raw.get('video') or {})
            a,b,c,d = st.columns(4)
            _hdmi = a.number_input('HDMI', min_value=0, value=int(_video.get('HDMI') or 0), step=1, key=f'eq_board_hdmi_{_platform}_{_token}')
            _dp = b.number_input('DisplayPort', min_value=0, value=int(_video.get('DisplayPort') or 0), step=1, key=f'eq_board_dp_{_platform}_{_token}')
            _vga = c.number_input('VGA', min_value=0, value=int(_video.get('VGA') or 0), step=1, key=f'eq_board_vga_{_platform}_{_token}')
            _dvi = d.number_input('DVI-D', min_value=0, value=int(_video.get('DVI-D') or 0), step=1, key=f'eq_board_dvi_{_platform}_{_token}')

            st.markdown('**Внешние USB материнской платы**')
            _usb = dict(_raw.get('usb_external') or {})
            a,b,c,d,e = st.columns(5)
            _usb2 = a.number_input('USB 2.0 A', min_value=0, value=int(_usb.get('USB 2.0 Type-A') or 0), step=1, key=f'eq_board_usb2_{_platform}_{_token}')
            _g1a = b.number_input('Gen1 A', min_value=0, value=int(_usb.get('USB 3.2 Gen1 Type-A') or 0), step=1, key=f'eq_board_g1a_{_platform}_{_token}')
            _g1c = c.number_input('Gen1 C', min_value=0, value=int(_usb.get('USB 3.2 Gen1 Type-C') or 0), step=1, key=f'eq_board_g1c_{_platform}_{_token}')
            _g2a = d.number_input('Gen2 A', min_value=0, value=int(_usb.get('USB 3.2 Gen2 Type-A') or 0), step=1, key=f'eq_board_g2a_{_platform}_{_token}')
            _g2c = e.number_input('Gen2 C', min_value=0, value=int(_usb.get('USB 3.2 Gen2 Type-C') or 0), step=1, key=f'eq_board_g2c_{_platform}_{_token}')

            return {
                'name': _name, 'price_input': _price_input, 'price': float(_price), 'price_currency': _price_currency,
                'price_conversion': _price_note, 'registry': bool(_registry), 'registry_number': _registry_number,
                'supplier': _supplier, 'supplier_sku': _supplier_sku,
                'socket': _socket, 'chipset': _chipset, 'form_factor': _form, 'ram_type': _ram_type,
                'ram_max_gb': int(_ram_max_gb), 'ram_max_mhz': int(_ram_max_mhz), 'ram_slots': int(_ram_slots),
                'ethernet_mbps': int(_eth_mbps), 'ethernet_ports': int(_eth_ports),
                'm2_key_m': int(_m2m), 'm2_key_e': int(_m2e), 'sata': int(_sata),
                'pcie_x1': int(_pcie1), 'pcie_x16': int(_pcie16), 'tpm_header': int(_tpm),
                'raid_0_1_5_10': _raid, 'audio_out': _audio_out, 'mic_in': _mic_in,
                'video': {'HDMI': int(_hdmi), 'DisplayPort': int(_dp), 'VGA': int(_vga), 'DVI-D': int(_dvi)},
                'usb_external': {
                    'USB 2.0 Type-A': int(_usb2), 'USB 3.2 Gen1 Type-A': int(_g1a),
                    'USB 3.2 Gen1 Type-C': int(_g1c), 'USB 3.2 Gen2 Type-A': int(_g2a),
                    'USB 3.2 Gen2 Type-C': int(_g2c),
                },
            }

    _boards_raw = dict(_profile_data.get('boards') or {})
    _amd_board = _board_editor('amd', 'AMD-плата', _boards_raw.get('amd'), _profile_token)
    _intel_board = _board_editor('intel', 'Intel-плата', _boards_raw.get('intel'), _profile_token)

    st.markdown('#### Реестровые и дополнительные компоненты')
    st.caption(
        'Добавляй сюда USB-хаб, Wi‑Fi, картридер, сборку или любой другой компонент. '
        'Цена и реестровый признак сохраняются. В колонке «Когда добавлять» можно указать, '
        'что компонент нужен всегда либо только при конкретном требовании ТЗ. Для Wi‑Fi/Bluetooth используй условие `wifi`.'
    )
    _component_columns = [
        'role','condition','category','name','supplier','supplier_sku','qty','price_input','price','registry','registry_number','location',
        'usb2_a','usb3_gen1_type_a','usb3_gen1_type_c','usb3_gen2_type_a','usb3_gen2_type_c','note'
    ]
    _component_defaults = list(_profile_data.get('components') or [])
    if not _component_defaults:
        _component_defaults = [
            {'role':'hub','condition':'always','category':'USB-хаб','name':'','qty':1.0,'price':0.0,'registry':False},
            {'role':'wifi','condition':'wifi','category':'Wi‑Fi','name':'','qty':1.0,'price':0.0,'registry':False},
            {'role':'cardreader','condition':'cardreader','category':'Картридер','name':'','qty':1.0,'price':0.0,'registry':False},
            {'role':'assembly','condition':'always','category':'Сборка','name':'','qty':1.0,'price':0.0,'registry':False},
        ]
    _cdf = pd.DataFrame(_component_defaults)
    for _col in _component_columns:
        if _col not in _cdf.columns:
            _cdf[_col] = False if _col == 'registry' else (1.0 if _col == 'qty' else 0.0 if _col == 'price' else 0 if _col.startswith('usb') else '')
    if 'price_input' in _cdf.columns:
        for _row_idx in range(len(_cdf)):
            _raw_input = _cdf.at[_row_idx, 'price_input']
            if pd.isna(_raw_input) or not str(_raw_input or '').strip():
                try:
                    _legacy_price = float(_cdf.at[_row_idx, 'price'] or 0)
                except Exception:
                    _legacy_price = 0.0
                _cdf.at[_row_idx, 'price_input'] = '' if _legacy_price <= 0 else f'{_legacy_price:g}'
            _cur_rub,_cur_currency,_cur_note=_parse_catalog_price(_cdf.at[_row_idx, 'price_input'])
            _cdf.at[_row_idx, 'price']=float(_cur_rub)
    _cdf = _cdf[_component_columns]
    _components_edited = st.data_editor(
        _cdf, hide_index=True, use_container_width=True, num_rows='dynamic', key=f'equipment_components_{_profile_token}',
        column_config={
            'role': st.column_config.SelectboxColumn('Роль', options=['extra','hub','wifi','cardreader','assembly'], width='small', help='Роль помогает программе понять назначение компонента.'),
            'condition': st.column_config.SelectboxColumn('Когда добавлять', options=['always','wifi','cardreader','hdd','gpu','amd','intel','wireless_forbidden'], width='medium'),
            'category': st.column_config.TextColumn('Категория', width='medium'),
            'name': st.column_config.TextColumn('Наименование', width='large'),
            'supplier': st.column_config.TextColumn('Поставщик', width='small', help='Например ExeGate. Если загружен его прайс, цена может обновляться автоматически по артикулу.'),
            'supplier_sku': st.column_config.TextColumn('Артикул / P/N', width='medium', help='Можно указать код или P/N из прайса поставщика.'),
            'qty': st.column_config.NumberColumn('Кол-во', min_value=0.0, step=1.0, format='%.2f'),
            'price_input': st.column_config.TextColumn('Цена ₽ / $', help='Примеры: 2500, $35, USD 35'),
            'price': st.column_config.NumberColumn('Цена, ₽', min_value=0.0, step=1.0, format='%.2f', disabled=True),
            'registry': st.column_config.CheckboxColumn('Реестр'),
            'registry_number': st.column_config.TextColumn('Реестровый №', width='medium'),
            'location': st.column_config.SelectboxColumn('USB где', options=['unknown','front','rear'], width='small'),
            'usb2_a': st.column_config.NumberColumn('USB2 A', min_value=0, step=1),
            'usb3_gen1_type_a': st.column_config.NumberColumn('G1 A', min_value=0, step=1),
            'usb3_gen1_type_c': st.column_config.NumberColumn('G1 C', min_value=0, step=1),
            'usb3_gen2_type_a': st.column_config.NumberColumn('G2 A', min_value=0, step=1),
            'usb3_gen2_type_c': st.column_config.NumberColumn('G2 C', min_value=0, step=1),
            'note': st.column_config.TextColumn('Комментарий', width='large'),
        }
    )
    st.caption('USB-колонки нужны только если этот компонент реально добавляет внешние порты. Пустые строки при сохранении игнорируются. В «Цена ₽ / $» можно писать 2500 или $35. Если указать Поставщика + Артикул/P/N и загрузить его прайс, цена будет обновляться автоматически.')

    st.markdown('#### Данные готового изделия / Арсенал')
    st.caption(
        'Это данные именно готового системного блока/моноблока, а не материнской платы. '
        'Если их заполнить, название изделия и его реестровый номер автоматически попадут в «Строку для Арсенала». '
        'Реестровые номера отдельных плат, хабов и других компонентов сохраняются отдельно и сюда не подменяются.'
    )
    a,b,c = st.columns([3,2,2])
    _final_reg_name = a.text_input('Наименование готового изделия', value=str(_profile_data.get('final_registry_name') or ''), placeholder='Например: Системный блок БЕШТАУ ...', key=f'eq_final_reg_name_{_profile_token}').strip()
    _final_reg_number = b.text_input('Реестровый номер готового изделия', value=str(_profile_data.get('final_registry_number') or ''), key=f'eq_final_reg_num_{_profile_token}').strip()
    _final_reg_code = c.text_input('Код исполнения (если есть)', value=str(_profile_data.get('final_registry_code') or ''), key=f'eq_final_reg_code_{_profile_token}').strip()
    if not _final_reg_number:
        st.caption('Если реестровый номер зависит от конкретного исполнения и заранее неизвестен — оставь пустым. В расчёте поле Арсенала будет пустым для ручного ввода, но название CPU туда больше не попадёт.')

    def _clean_component_value(_v, _numeric=False, _boolean=False):
        if _boolean:
            return bool(_v) if not pd.isna(_v) else False
        if _numeric:
            if pd.isna(_v) or _v in ('', None): return 0
            try: return int(_v)
            except Exception: return 0
        if pd.isna(_v) or _v is None: return ''
        return str(_v).strip()

    _normalized_components = []
    for _r in _components_edited.to_dict('records'):
        _name = _clean_component_value(_r.get('name'))
        if not _name:
            continue
        _price_input = _clean_component_value(_r.get('price_input'))
        if not _price_input:
            try:
                _legacy_price = float(_r.get('price') or 0) if not pd.isna(_r.get('price')) else 0.0
            except Exception:
                _legacy_price = 0.0
            _price_input = '' if _legacy_price <= 0 else f'{_legacy_price:g}'
        _price, _price_currency, _price_note = _parse_catalog_price(_price_input)
        _normalized_components.append({
            'role': _clean_component_value(_r.get('role')) or 'extra',
            'condition': _clean_component_value(_r.get('condition')) or 'always',
            'category': _clean_component_value(_r.get('category')) or 'Доп. компонент',
            'name': _name, 'supplier': _clean_component_value(_r.get('supplier')), 'supplier_sku': _clean_component_value(_r.get('supplier_sku')),
            'qty': (float(_r.get('qty') or 1) if not pd.isna(_r.get('qty')) else 1.0),
            'price_input': _price_input, 'price': float(_price), 'price_currency': _price_currency, 'price_conversion': _price_note,
            'registry': _clean_component_value(_r.get('registry'), _boolean=True),
            'registry_number': _clean_component_value(_r.get('registry_number')),
            'location': _clean_component_value(_r.get('location')) or 'unknown',
            'usb2_a': _clean_component_value(_r.get('usb2_a'), _numeric=True),
            'usb3_gen1_type_a': _clean_component_value(_r.get('usb3_gen1_type_a'), _numeric=True),
            'usb3_gen1_type_c': _clean_component_value(_r.get('usb3_gen1_type_c'), _numeric=True),
            'usb3_gen2_type_a': _clean_component_value(_r.get('usb3_gen2_type_a'), _numeric=True),
            'usb3_gen2_type_c': _clean_component_value(_r.get('usb3_gen2_type_c'), _numeric=True),
            'note': _clean_component_value(_r.get('note')),
        })

    _component_usd_notes = [str(x.get('price_conversion') or '') for x in _normalized_components if str(x.get('price_conversion') or '').strip()]
    if _component_usd_notes:
        st.caption('Пересчёт $ в базе: ' + ' · '.join(_component_usd_notes[:6]) + (' …' if len(_component_usd_notes) > 6 else ''))

    _save_col, _delete_col = st.columns([4,1])
    if _save_col.button('💾 Сохранить / обновить базу оборудования', type='primary', use_container_width=True, key=f'equip_save_{_profile_token}'):
        if not _profile_name:
            st.error('Укажи название базы, например «Бештау».')
        elif not ((_amd_board and _amd_board.get('name')) or (_intel_board and _intel_board.get('name'))):
            st.error('Заполни хотя бы одну материнскую плату: AMD или Intel.')
        else:
            _boards = {}
            if _amd_board and _amd_board.get('name'): _boards['amd'] = _amd_board
            if _intel_board and _intel_board.get('name'): _boards['intel'] = _intel_board
            _payload = {
                'profile_name': _profile_name,
                'manufacturer': _manufacturer or _profile_name,
                'boards': _boards,
                'components': _normalized_components,
                'final_registry_name': _final_reg_name,
                'final_registry_number': _final_reg_number,
                'final_registry_code': _final_reg_code,
            }
            _payload,_price_stat=apply_latest_prices_to_profile(_payload)
            # Recalculate RUB values after supplier USD prices were injected.
            for _bp,_bd in dict(_payload.get('boards') or {}).items():
                _rub,_cur,_note=_parse_catalog_price(_bd.get('price_input'))
                _bd['price']=float(_rub); _bd['price_currency']=_cur; _bd['price_conversion']=_note
            for _ci in _payload.get('components') or []:
                _rub,_cur,_note=_parse_catalog_price(_ci.get('price_input'))
                _ci['price']=float(_rub); _ci['price_currency']=_cur; _ci['price_conversion']=_note
            catalog_save_item('equipment_profile', _profile_name, _payload)
            st.session_state['_catalog_status'] = catalog_status()
            _msg=f'База «{_profile_name}» сохранена. Теперь она доступна в поле «База комплектующих» и переносится вместе с QX_UserCatalog.qxdb.'
            if _price_stat.get('updated'): _msg += f' Цены из прайсов обновлены: {_price_stat.get("updated")}.'
            st.success(_msg)
            for _miss in (_price_stat.get('missing') or [])[:8]: st.warning(_miss)
            st.session_state['equipment_db_rev']=int(st.session_state.get('equipment_db_rev',0))+1
            st.rerun()

    if _profile_rec:
        if _delete_col.button('Удалить', use_container_width=True, key=f'equip_delete_{_profile_token}'):
            if catalog_delete_item('equipment_profile', _profile_rec['name']):
                st.session_state['_catalog_status'] = catalog_status()
                st.session_state['equipment_db_rev']=int(st.session_state.get('equipment_db_rev',0))+1
                st.success(f'База «{_profile_rec["name"]}» удалена. Переключи вкладку/обнови экран, чтобы список перечитался.')


if _nav == '📋 Реестр':
    st.subheader('Проверка реестровой записи')
    a,b,c=st.columns(3); platform=a.selectbox('Платформа',['amd','intel']); product_type=b.selectbox('Изделие',['system','aws24','aws27','aio24','aio27']); device=c.selectbox('Реестровый модуль',['wifi','cardreader'])
    d,e=st.columns(2); gpu=d.checkbox('Есть дискретная видеокарта'); hdd=e.checkbox('Есть HDD')
    rec=find_registry_record(platform,product_type,gpu,hdd,device).to_dict()
    st.markdown(f'''<div class="qx-card"><b>{rec['product_name']}</b><br>Реестровый номер: <b>{rec['registry_number']}</b><br>Код исполнения: <b>{rec['execution_code']}</b></div>''',unsafe_allow_html=True)
    st.caption('SSD и USB-HUB считаются обязательными. Реестровым выбирается только один модуль: Wi‑Fi или картридер.')

if _nav == '📚 КТРУ':
    st.subheader('Справочник КТРУ')
    st.caption('КТРУ используется как словарь характеристик и для определения типа позиции. Конкретные выбранные заказчиком значения программа всё равно берёт из ТЗ.')
    code=st.text_input('Код КТРУ',placeholder='26.20.15.000-00000028')
    if code:
        try: st.link_button('Открыть официальную карточку в ЕИС',official_url(code))
        except Exception: pass
    if st.button('Загрузить справочную карточку',disabled=not bool(code)):
        try:
            with st.spinner('Загружаю справочник…'): info=fetch_reference(code)
            st.success(info['name']); st.write(f'Источник справочных характеристик: {info["source"]}')
            if info['characteristics']: st.write('Распознаваемые характеристики: ' + ', '.join(info['characteristics']))
        except Exception as e: st.error(str(e))

if _nav == '🧠 Справочники':
    st.subheader('Технические справочники QX')
    a,b=st.columns(2)
    with a: st.markdown('#### B760 DDR5'); st.json(QX_SPECS['intel'],expanded=True)
    with b: st.markdown('#### A520 DDR4'); st.json(QX_SPECS['amd'],expanded=True)
    st.markdown('#### Моноблочные платформы QX'); st.json(AIO_SPECS,expanded=True)
    st.caption('Эти факты относятся только к стандартным платформам QX. Для другой моноблочной платформы выбери режим «Другая платформа» в позиции и введи реальные характеристики вручную — QX-значения к ней не применяются.')
    st.markdown('#### База процессоров AMD / Intel')
    cpu_stats=catalog_stats()
    ca,cb,cc,cd=st.columns(4)
    ca.metric('Всего CPU в базе',cpu_stats['total'])
    cb.metric('Intel',cpu_stats['intel'])
    cc.metric('AMD',cpu_stats['amd'])
    cd.metric('Из полной OpenDB',cpu_stats['external'])
    st.caption('Встроенная офлайн-база содержит расширенный набор AM4 и LGA1700. Кнопка ниже загружает полный актуальный каталог Intel/AMD из BuildCores OpenDB; для QX-подбора автоматически отбираются совместимые AM4/LGA1700 модели.')
    if st.button('Обновить полную базу процессоров из BuildCores OpenDB',use_container_width=True):
        try:
            with st.spinner('Скачиваю и индексирую базу процессоров…'):
                result=update_from_buildcores()
                reload_external_catalog()
            st.success(f'Готово. Загружено записей Intel/AMD: {int(result.get("count",0))}.')
            st.rerun()
        except Exception as exc:
            st.warning(f'Не удалось обновить базу из интернета: {exc}. Встроенная офлайн-база продолжает работать.')
    st.caption('Источник полной базы: BuildCores OpenDB — ODC Attribution License (ODC-By) v1.0.')
    with st.expander('Поиск по базе процессоров', expanded=False):
        cpu_search=st.text_input('Модель / сокет / производитель',placeholder='12600K, Ryzen 5 PRO, AM4, LGA1700…',key='cpu_catalog_search').strip().lower()
        cpu_rows=[]
        for c in all_cpus():
            hay=' '.join([c.model,c.manufacturer,c.socket,' '.join(c.memory_types)]).lower()
            if cpu_search and cpu_search not in hay:
                continue
            cpu_rows.append({'Производитель':c.manufacturer,'Модель':c.model,'Сокет':c.socket,'Ядра':c.cores,'Потоки':c.threads,
                             'База, ГГц':c.base_ghz,'Boost, ГГц':c.boost_ghz,'L3, МБ':c.l3_mb,'TDP, Вт':c.tdp_w,
                             'iGPU':'Да' if c.igpu else 'Нет','Память':', '.join(c.memory_types),'Источник':c.source})
        if cpu_rows:
            st.dataframe(pd.DataFrame(cpu_rows[:1000]),hide_index=True,use_container_width=True,height=360)
            if len(cpu_rows)>1000: st.caption(f'Найдено {len(cpu_rows)} записей; показаны первые 1000 — уточни поиск.')
        else:
            st.info('Совпадений нет.')
    st.markdown('#### Корпуса'); st.json(CASE_SPECS,expanded=True)

if _nav == '⚙️ Настройки':
    st.subheader('Настройки')
    s=dict(st.session_state.settings)

    st.markdown('#### Валюта')
    a,b,c=st.columns(3)
    a.metric('Курс USD ЦБ РФ',f'{float(usd_info["rate"]):.4f} ₽')
    s['usd_buffer_rub']=b.number_input('Запас к курсу, ₽ на $',min_value=0.0,max_value=50.0,value=float(s.get('usd_buffer_rub',5)),step=0.5)
    c.metric('Курс для расчёта',f'{buffered_rate(float(usd_info["rate"]),float(s["usd_buffer_rub"])):.4f} ₽/$')
    st.caption('Пример: вводишь «$100» — программа умножает 100 на актуальный курс ЦБ РФ + этот запас. Если ЦБ временно недоступен, используется последний сохранённый курс и это видно в шапке.')
    if st.button('Обновить курс сейчас'):
        _usd_rate_cached.clear()
        st.rerun()

    st.markdown('#### Арсенал и расчёт')
    a,b,c=st.columns(3)
    s['default_delivery']=a.number_input('Доставка по умолчанию, ₽',min_value=0.0,value=float(s.get('default_delivery',0)))
    s['default_bg']=b.number_input('БГ по умолчанию, ₽',min_value=0.0,value=float(s.get('default_bg',s.get('default_bg1',0))))
    s['default_go']=c.number_input('ГО по умолчанию, ₽',min_value=0.0,value=float(s.get('default_go',s.get('default_bg2',0))))
    a,b,c=st.columns(3)
    s['default_sender']=a.text_input('От кого по умолчанию',value=str(s.get('default_sender','ЗИОН')))
    s['default_country']=b.text_input('Страна по умолчанию',value=str(s.get('default_country','Россия')))
    s['default_trademark']=c.text_input('Товарный знак по умолчанию',value=str(s.get('default_trademark','1093786')))

    st.markdown('#### Реестровая логика')
    a,b,c=st.columns(3)
    s['prefer_registry_device_when_not_required']=a.selectbox('Если не требуется Wi‑Fi/картридер',['wifi','cardreader'],index=0 if s.get('prefer_registry_device_when_not_required','wifi')=='wifi' else 1)
    s['prefer_registry_device_when_both_required']=b.selectbox('Если нужны оба — реестровым',['wifi','cardreader'],index=0 if s.get('prefer_registry_device_when_both_required','wifi')=='wifi' else 1)
    s['smart_registry_device']=c.checkbox('Умно выбирать модуль по портам ТЗ',value=bool(s.get('smart_registry_device',True)))
    st.caption('Эти настройки относятся к стандартной базе QX. Если ТЗ прямо запрещает беспроводную связь, Wi‑Fi не добавляется вообще, а обязательным реестровым модулем становится картридер. Для другой базы состав и условия компонентов задаются во вкладке «База оборудования».')

    st.markdown('#### Пользовательская база: корпуса, мониторы, клавиатуры, мыши и другое оборудование')
    _cstat = st.session_state.get('_catalog_status') or {}
    st.caption(
        'Корпуса, мониторы, клавиатуры, мыши, моноблочные платформы и пользовательские базы оборудования хранятся вместе. На этом компьютере рабочая база хранится в профиле Windows, а программа автоматически делает её переносимую копию '
        '`QX_UserData/QX_UserCatalog.qxdb` рядом с программой. Если скопировать всю папку QX Подборщика на другой ПК, '
        'эта база будет подхвачена автоматически при первом запуске.'
    )
    st.code(f'Основная: {catalog_path()}\nПереносимая: {portable_catalog_path()}', language=None)
    if _cstat.get('portable_ok') is False:
        st.warning('Не удалось обновить переносимую копию рядом с программой. Основная база в AppData продолжает работать; экспорт ниже теперь формируется напрямую из основной базы и не зависит от доступа к папке программы.')

    exp_col, imp_col = st.columns(2)
    exp_col.caption('Экспорт открывает обычное окно Windows «Сохранить как…». Это надёжнее встроенного скачивания в desktop-режиме.')
    if exp_col.button('⬇ Экспортировать базу для другого ПК…', use_container_width=True, key='catalog_export_native'):
        try:
            _catalog_blob = export_catalog_bytes()
            _saved_path = _save_native(
                _catalog_blob, 'QX_UserCatalog.qxdb',
                title='Экспорт базы QX для другого ПК',
                filetypes=[('База QX', '*.qxdb'), ('SQLite database', '*.sqlite3;*.db'), ('Все файлы', '*.*')],
            )
            if not _saved_path:
                exp_col.info('Экспорт отменён: файл не выбран.')
        except Exception as _exp_exc:
            exp_col.error(f'Не удалось экспортировать базу: {_exp_exc}')
    try:
        _catalog_blob_reserve = export_catalog_bytes()
        exp_col.download_button(
            '↓ Резервное скачивание', data=_catalog_blob_reserve,
            file_name='QX_UserCatalog.qxdb', mime='application/octet-stream',
            use_container_width=True, key='catalog_export_download_reserve',
            help='Если системное окно сохранения по какой-то причине не откроется, попробуй резервное скачивание.'
        )
    except Exception as _exp_reserve_exc:
        exp_col.caption(f'Резервное скачивание временно недоступно: {_exp_reserve_exc}')

    _catalog_upload = imp_col.file_uploader(
        'Импорт базы (.qxdb)', type=['qxdb','sqlite3','db'], key='catalog_import_upload',
        help='Импорт объединяет записи: существующие не пропадают, а одноимённые записи из импортируемой базы обновляются.'
    )
    if imp_col.button('⬆ Импортировать / объединить', disabled=_catalog_upload is None, use_container_width=True, key='catalog_import_btn'):
        try:
            _changed = import_catalog_bytes(_catalog_upload.getvalue())
            st.session_state['_catalog_status'] = catalog_status()
            st.success(f'База импортирована. Добавлено/обновлено записей: {_changed}.')
            st.rerun()
        except Exception as _imp_exc:
            st.error(f'Не удалось импортировать базу: {_imp_exc}')

    if st.button('Сохранить настройки',type='primary'):
        s['default_bg1']=s['default_bg']; s['default_bg2']=s['default_go']
        # Preserve the current rate as an offline fallback.
        s['usd_rate_cached']=float(usd_info['rate']); s['usd_rate_date_cached']=str(usd_info.get('date',''))
        st.session_state.settings=s
        save_settings(s)
        st.success('Сохранено.')
