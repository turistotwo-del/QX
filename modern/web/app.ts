// @ts-nocheck
/* QX Modern 4.0.40 — Immediate drafts and background source retrieval. */
const $ = (s) => document.querySelector(s);
const fmt = (v, dec = 0) => new Intl.NumberFormat('ru-RU', { maximumFractionDigits: dec, minimumFractionDigits: dec }).format(Number(v) || 0);
const rub = (v) => `${fmt(v, 0)} ₽`;
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] || c));
const num = (v, def = 0) => { const x = Number(String(v ?? '').replace(',', '.')); return Number.isFinite(x) ? x : def; };
const clone = (s) => JSON.parse(JSON.stringify(s));
const state = { charRows: [], charFilter: 'all', tab: 'home', stage: 'ТЗ и требования', busy: false, name: 'Новый расчёт', reqs: [], plans: [], pos: 0, source_text: '', source_filename: '', source_docx_base64: '', sourcePreview: null, characteristics: [], overrides: {}, prices: {}, settings: {}, rate: { rate: 0, date: '', live: false }, catalogKind: 'equipment_profile', catalogs: {}, collapse: false, theme: 'dark', full: false, arsenalText: '', arsenalFields: { sender: 'ЗИОН', country: 'Россия', trademark: '1093786', delivery: 0, bg: 0, go: 0, os: '' }, reqSearch: '', catalogSearch: '', diagnostics: null, attachmentAudit: null, tenderRepairFile: null, tenderRepairPreview: null, legacyPreview: null, modal: '', reqDefaults: {}, showAllFields: false, tzDocuments: [], tzAiResults: {}, tzAiModel: '', tzAiAuto: false, tzAiRunning: false, tzAiMessage: '', tenderLinkEnabled: false, tenderNoticeNumber: '', tenderEisPreview: null, tenderEisMessage: '', projectSavedManually: false, projectHasEdits: false, tenderEisDiscovery: null };
const notesState = { items: [], selected: '', query: '', showDone: false, error: '', loaded: false };
const noteSaveTimers = new Map();
const noteSaveChains = new Map();
const titles = { notes: 'Быстрые заметки', home: 'Главная', tz: 'Загрузка и разбор ТЗ', build: 'Сборка и цены', verify: 'Проверка заявки', arsenal: 'Арсенал', docs: 'Документы и экспорт', catalog: 'Каталоги оборудования', prices: 'Цены QX', settings: 'Настройки', tenders: 'Тендерный отдел' };
const tenderNav = [['registry', '▤', 'Реестр закупок'], ['contracts', '▣', 'Контракты и поставки'], ['analytics', '◫', 'Аналитика'], ['reminders', '◷', 'Сроки и напоминания'], ['organizations', '◇', 'Организации']];
const tenderViewTitles = { registry: 'Реестр закупок', calendar: 'Календарь и задачи', contracts: 'Контракты и поставки', analytics: 'Аналитика', reminders: 'Сроки и напоминания', organizations: 'Организации' };
const nav1 = [['home', '⌂', 'Главная'], ['tz', '↥', 'Загрузка ТЗ'], ['build', '▦', 'Сборка и цены'], ['verify', '✓', 'Проверка заявки'], ['arsenal', '▤', 'Арсенал'], ['docs', '↗', 'Документы'], ['notes', '✎', 'Быстрые заметки']];
const nav2 = [['catalog', '◇', 'Базы оборудования'], ['prices', '₽', 'Прайс QX'], ['settings', '⚙', 'Настройки']];
let autosaveTimer;
let uiTimer;
const reqLabels = { title: 'Название позиции', item_name: 'Наименование товара', ktru_code: 'Код КТРУ', quantity: 'Количество', nmck: 'НМЦК, ₽', platform: 'Платформа', product_type: 'Тип изделия', equipment_profile_name: 'База производителя', cpu_model: 'Модель процессора', cpu_cores_min: 'Ядер CPU, не менее', cpu_threads_min: 'Потоков CPU, не менее', cpu_freq_ghz_min: 'Базовая частота, ГГц', cpu_freq_max_ghz_min: 'Максимальная частота, ГГц', cpu_l3_mb_min: 'Кэш L3, МБ', cpu_tdp_w_max: 'TDP CPU, не более', cpu_passmark_min: 'PassMark, не менее', need_integrated_graphics: 'Встроенная графика', ram_gb_min: 'Оперативная память, ГБ', ram_type: 'Тип памяти', ram_mhz_min: 'Частота RAM, МГц', ram_max_supported_gb_min: 'Максимальная RAM, ГБ', ram_slots_min: 'Слотов памяти, не менее', ssd_gb_min: 'SSD, ГБ', ssd_interface: 'Интерфейс SSD', hdd_gb_min: 'HDD, ГБ', need_gpu: 'Дискретная видеокарта', gpu_vram_gb_min: 'Видеопамять, ГБ', psu_w_min: 'Мощность БП, Вт', need_wifi: 'Wi-Fi', need_bluetooth: 'Bluetooth', forbid_wireless: 'Запрет беспроводной связи', need_cardreader: 'Картридер', need_keyboard: 'Клавиатура', need_mouse: 'Мышь', need_os: 'Операционная система', os_text: 'Название ОС', m2_key_m_min: 'M.2 Key M, не менее', m2_key_e_min: 'M.2 Key E, не менее', ethernet_mbps_min: 'Ethernet, Мбит/с', ethernet_ports_min: 'Портов RJ-45', usb2_total_min: 'USB 2.0, всего', usb3_gen1_total_min: 'USB 3.2 Gen1, всего', usb3_gen2_total_min: 'USB 3.2 Gen2, всего', usb_c_total_min: 'USB Type-C, всего', case_height_max_mm: 'Высота корпуса до, мм', case_length_max_mm: 'Длина корпуса до, мм', case_width_max_mm: 'Ширина корпуса до, мм', bay_525_min: 'Отсеков 5,25″', bay_25_min: 'Отсеков 2,5″', bay_35_min: 'Отсеков 3,5″', system_case_mode: 'Режим выбора корпуса', warranty_months_min: 'Гарантия, месяцев', monitor_diagonal_in_min: 'Экран от, дюйм', monitor_refresh_hz_min: 'Частота экрана, Гц', monitor_inches: 'Диагональ экрана, дюйм', monitor_resolution: 'Разрешение экрана', monitor_matrix: 'Матрица экрана', monitor_brightness_min: 'Яркость экрана, кд/м²', monitor_hdmi_ports_min: 'HDMI монитора, портов', monitor_dp_ports_min: 'DisplayPort монитора, портов', aio_platform_mode: 'Режим моноблочной платформы', custom_aio_name: 'Платформа из базы', custom_case_name: 'Корпус из базы', keyboard_source_mode: 'Источник клавиатуры', mouse_source_mode: 'Источник мыши', keyboard_catalog_item: 'Клавиатура из моей базы', mouse_catalog_item: 'Мышь из моей базы', monitor_catalog_item: 'Монитор из моей базы' };
const legacyKeyGroups = [['Основное', ['title', 'item_name', 'quantity', 'nmck', 'product_type', 'platform', 'equipment_profile_name', 'ktru_code']], ['Процессор', ['cpu_model', 'cpu_cores_min', 'cpu_threads_min', 'cpu_freq_ghz_min', 'cpu_freq_max_ghz_min', 'cpu_l3_mb_min', 'cpu_tdp_w_max', 'cpu_passmark_min', 'need_integrated_graphics']], ['Память и накопители', ['ram_gb_min', 'ram_type', 'ram_mhz_min', 'ram_max_supported_gb_min', 'ram_slots_min', 'ssd_gb_min', 'ssd_interface', 'hdd_gb_min']], ['Видеокарта и периферия', ['need_gpu', 'gpu_vram_gb_min', 'need_wifi', 'need_bluetooth', 'forbid_wireless', 'need_cardreader', 'need_keyboard', 'need_mouse', 'need_os', 'os_text']], ['Корпус и интерфейсы', ['psu_w_min', 'm2_key_m_min', 'm2_key_e_min', 'ethernet_mbps_min', 'ethernet_ports_min', 'usb2_total_min', 'usb3_gen1_total_min', 'usb3_gen2_total_min', 'usb_c_total_min', 'case_height_max_mm', 'case_length_max_mm', 'case_width_max_mm', 'bay_525_min', 'bay_25_min', 'bay_35_min', 'system_case_mode', 'custom_case_name']], ['Монитор и гарантия', ['monitor_diagonal_in_min', 'monitor_refresh_hz_min', 'aio_platform_mode', 'custom_aio_name', 'warranty_months_min']]];
const emptyReq = () => ({ ...clone(state.reqDefaults), title: 'ТИП 1', quantity: 1, product_type: 'system', platform: null, manual_requirements: [], keyboard_source_mode: 'qx', mouse_source_mode: 'qx' });
async function api(path, body, method = 'POST', headers = {}, requestOptions = {}) {
    const opt = { ...requestOptions, method: body === undefined && method === 'POST' ? 'GET' : method, headers: { ...headers } };
    if (body !== undefined) {
        if (body instanceof Blob || body instanceof ArrayBuffer) {
            opt.body = body;
        }
        else {
            opt.body = JSON.stringify(body);
            opt.headers['Content-Type'] = 'application/json';
        }
    }
    const resp = await fetch('/api/' + path, opt);
    if (!resp.ok) {
        let msg = resp.statusText;
        try {
            const o = await resp.json();
            msg = o.error || o.detail || msg;
        }
        catch { }
        const error = new Error(Array.isArray(msg) ? msg.map(item => item.msg || String(item)).join('; ') : String(msg));
        error.status = resp.status;
        throw error;
    }
    if (resp.headers.get('content-type')?.includes('application/json'))
        return resp.json();
    return resp.blob();
}
function toast(message, error = false) {
    let box = $('#toasts');
    if (!box) {
        const d = document.createElement('div');
        d.id = 'toasts';
        d.className = 'toast-container';
        document.body.appendChild(d);
        box = d;
    }
    const e = document.createElement('div');
    e.className = 'toast' + (error ? ' error' : '');
    e.textContent = message;
    box.appendChild(e);
    setTimeout(() => e.remove(), 4500);
}
async function busy(fn) {
    state.busy = true;
    showBusy();
    try {
        return await fn();
    }
    catch (e) {
        console.error(e);
        toast(e.message || 'Ошибка операции', true);
        return undefined;
    }
    finally {
        state.busy = false;
        showBusy();
    }
}
function showBusy() {
    const e = $('#busy-overlay');
    if (e)
        e.remove();
    if (state.busy) {
        const d = document.createElement('div');
        d.id = 'busy-overlay';
        d.className = 'load-overlay';
        d.innerHTML = '<div class="loader"></div>';
        document.body.appendChild(d);
    }
}
function currentPlan() { return state.plans[state.pos]; }
function currentReq() { return state.reqs[state.pos]; }
const unitCost = (p) => p ? (p.rows || []).reduce((s, r) => s + num(r.qty, 1) * num(r.price), 0) : 0;
const countWarnings = () => state.plans.reduce((n, p) => n + (p.warnings?.length || 0) + (p.checks || []).filter(c => c['Статус'] === 'НЕ ПРОХОДИТ').length, 0);
const purchase = () => state.plans.reduce((s, p) => s + unitCost(p) * num(p.req?.quantity), 0);
function dataPackage() { storeCurrentDoc(); return { tz_documents: state.tzDocuments, name: state.name, reqs: state.reqs, plans: state.plans, source_text: state.source_text, source_filename: state.source_filename, source_docx_base64: state.source_docx_base64, characteristics: state.characteristics, tender_overrides: state.overrides, prices: state.prices, settings: state.settings, tender_project_key: state.tenderProjectKey, tender_link_enabled: state.tenderLinkEnabled, tender_notice_number: state.tenderNoticeNumber }; }
function scheduleSave() {
    state.projectHasEdits = true;
    if (state.reqs.length)
        synchronizeTenderSoon();
    clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(async () => {
        if (state.reqs.length) {
            try {
                await api('project/autosave', dataPackage());
            }
            catch (e) {
                console.warn('Autosave failed', e);
            }
        }
    }, 1200);
}
function goto(tab) { if (tab === 'notes')
    void loadNotes(); if (tab === 'tenders')
    loadTenders(); if (tab === 'home') void loadTenders(); state.full = false; $('#fullscreen-area')?.remove(); const changed = state.tab !== tab; state.tab = tab; render(changed); if (tab === 'tz' && !state.tenderAiStatus)
    void refreshTenderAiStatus(); if (tab === 'verify' && state.characteristics.length && !state.charRows.length)
    refreshChar(); }
function navBtn([tab, icon, title]) { return `<button class="nav ${state.tab === tab ? 'active' : ''}" data-action="tab" data-tab="${tab}" title="${title}"><span class="ico">${icon}</span><span class="nav-text">${title}</span></button>`; }
function tenderNavBtn([view, icon, title]) { return `<button class="nav tender-subnav ${state.tab === 'tenders' && state.tenders.view === view && !state.tenders.selected ? 'active' : ''}" data-action="tender-nav" data-view="${view}" title="${title}"><span class="ico">${icon}</span><span class="nav-text">${title}</span></button>`; }
function tenderSidebar() {
    const opened = !!state.tenders.expanded;
    const active = state.tab === 'tenders' && (state.tenders.view !== 'calendar' || !!state.tenders.selected);
    return `<div class="sidebar-tenders"><button class="tender-group ${active ? 'active' : ''}" id="tender-nav-toggle" data-action="tender-group" title="ТЕНДЕРНЫЙ ОТДЕЛ" aria-label="ТЕНДЕРНЫЙ ОТДЕЛ" aria-expanded="${opened}" aria-controls="tender-nav-submenu"><span class="group-icon" aria-hidden="true">▥</span><span class="nav-text">ТЕНДЕРНЫЙ ОТДЕЛ</span><span class="tender-chevron" aria-hidden="true">${opened ? '⌄' : '›'}</span></button><div id="tender-nav-submenu" class="tender-submenu ${opened ? 'expanded' : ''}" ${opened ? '' : 'hidden'}>${tenderNav.map(tenderNavBtn).join('')}</div></div>`;
}
function calendarSidebar() {
    const active = state.tab === 'tenders' && state.tenders.view === 'calendar' && !state.tenders.selected;
    return `<button class="nav qx-calendar-nav ${active ? 'active' : ''}" data-action="tender-nav" data-view="calendar" title="Календарь" aria-label="Календарь" ${active ? 'aria-current="page"' : ''}><span class="ico" aria-hidden="true">▦</span><span class="nav-text">Календарь</span></button>`;
}
function headerActions() { if (state.tab === 'notes')
    return `<button class="top-btn new-project" data-action="notes-new">＋ Новая заметка</button><div class="avatar">QX</div>`; return state.tab === 'tenders' ? `<button class="top-btn" data-action="tender-backup">⇩ Копия базы</button><button class="top-btn new-project" data-action="tender-new">＋ Новая закупка</button><div class="avatar">QX</div>` : `<button class="top-btn new-project" data-action="new">＋ Новый расчёт</button><button class="top-btn" data-action="project-save">⇩ Сохранить</button><button class="top-btn" data-action="project-load">▣ Открыть</button><div class="avatar">QX</div>`; }
function workspaceSidebar() {
    const tabs = ['tz', 'build', 'verify', 'arsenal', 'docs'];
    let opened = state.workspaceExpanded;
    if (opened === undefined) {
        try { opened = localStorage.getItem('qx-workspace-expanded') === 'true'; } catch { opened = false; }
        if (tabs.includes(state.tab)) opened = true;
        state.workspaceExpanded = opened;
    }
    if (tabs.includes(state.tab) && state.workspaceLastTab !== state.tab) opened = true;
    state.workspaceLastTab = state.tab;
    state.workspaceExpanded = opened;
    return `<details class="qx-workspace-group ${tabs.includes(state.tab) ? 'is-active' : ''}" id="workspace-nav-group" ${opened ? 'open' : ''}><summary title="РАСЧЁТ И ДОКУМЕНТЫ" aria-label="РАСЧЁТ И ДОКУМЕНТЫ"><span class="ico" aria-hidden="true">▦</span><span class="nav-text">РАСЧЁТ И ДОКУМЕНТЫ</span><span class="qx-workspace-chevron" aria-hidden="true">›</span></summary><div class="qx-workspace-submenu">${nav1.filter(([tab]) => tabs.includes(tab)).map(navBtn).join('')}</div></details>`;
}
document.addEventListener('toggle', event => {
    if (event.target.id !== 'workspace-nav-group') return;
    state.workspaceExpanded = event.target.open;
    try { localStorage.setItem('qx-workspace-expanded', String(state.workspaceExpanded)); } catch { }
}, true);
function dashboardDates() {
    const today = new Date().toLocaleDateString('sv-SE');
    const events = [];
    for (const tender of state.tenders.items || []) {
        if (['Проиграли', 'Отменено', 'Контракт исполнен'].includes(tender.status)) continue;
        for (const [key, label] of [['application_due_on', 'Подача заявок'], ['auction_on', 'Аукцион'], ['results_on', 'Итоги котировки'], ['calculated_due_on', 'Поставка'], ['payment_due_on', 'Оплата']]) {
            const date = tender[key];
            if (!/^\d{4}-\d{2}-\d{2}$/.test(date || '') || date < today) continue;
            if (key === 'auction_on' && tender.is_quotation || key === 'results_on' && !tender.is_quotation || key === 'calculated_due_on' && tender.is_delivered) continue;
            events.push({ date, label, title: tender.number || tender.title || 'Закупка', id: tender.id, action: 'tender-open' });
        }
    }
    for (const note of state.tenders.calendarNotes || []) {
        if (!note.completed && /^\d{4}-\d{2}-\d{2}$/.test(note.due_on || '') && note.due_on >= today)
            events.push({ date: note.due_on, label: 'Задача', title: note.title || note.body || 'Заметка', id: note.id, action: 'tender-calendar-open-note' });
    }
    return events.sort((a, b) => a.date.localeCompare(b.date)).slice(0, 4);
}
function shell() { return `<div class="app-shell ${state.collapse ? 'collapsed' : ''}" style="--sidebar-current-width:${state.collapse ? 72 : Math.max(260, Math.min(460, num(state.settings.sidebar_width, 320)))}px"><aside class="sidebar" style="width:${state.collapse ? 72 : Math.max(260, Math.min(460, num(state.settings.sidebar_width, 320)))}px"><div class="brand"><div class="brand-logo">QX</div><div class="brand-text"><strong>QX <em>Подборщик</em></strong><small>${esc(state.runtimeVersion || 'QX WORKSPACE')}</small></div></div><div class="sidebar-menu"><div class="side-caption">РАБОЧАЯ ОБЛАСТЬ</div>${nav1.filter(([tab]) => tab === 'home').map(navBtn).join('')}${workspaceSidebar()}${tenderSidebar()}${calendarSidebar()}${nav1.filter(([tab]) => tab === 'notes').map(navBtn).join('')}<div class="side-caption">СПРАВОЧНИКИ</div>${nav2.map(navBtn).join('')}</div><div class="sidebar-bottom"><span class="fx">USD · ЦБ РФ ${state.rate.live ? '● актуальный' : '○ сохранённый'}</span><b>${fmt(state.rate.rate, 2)} ₽</b><small>Для расчёта: ${fmt(num(state.rate.rate) + num(state.settings.usd_buffer_rub, 5), 2)} ₽</small><div class="toolbar"><button data-action="rate" class="btn secondary small mini-btn">↻ Курс</button><button data-action="dns" class="btn secondary small mini-btn">DNS ↗</button></div></div><button class="sidebar-collapse" data-action="collapse">${state.collapse ? '›' : '‹'}</button></aside><div class="main"><header class="topbar"><div class="crumbs">Рабочая область QX <span>›</span> <strong>${state.tab === 'tenders' ? state.tenders.view === 'calendar' && !state.tenders.selected ? 'Календарь' : 'Тендеры · ' + (state.tenders.selected ? 'Карточка закупки' : tenderViewTitles[state.tenders.view]) : titles[state.tab]}</strong></div><div class="top-right"><div class="top-rate">Расчётный USD <strong>${fmt(num(state.rate.rate) + num(state.settings.usd_buffer_rub, 5), 2)} ₽</strong></div><span class="pill">● Локально</span>${headerActions()}</div></header><main class="content" id="content"><div class="page">${pageContent()}</div></main></div></div>${state.modal ? modal() : ''}`; }
function noteDate(v) { try {
    return new Date(v).toLocaleString('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}
catch {
    return String(v || '');
} }
function notePreview(n) { return (n.title || n.body || 'Новая заметка').trim().replace(/\s+/g, ' ').slice(0, 100) || 'Новая заметка'; }
function noteStatus(n) { if (n.completed)
    return '<span class="qx-note-state done">✓ Выполнено</span>'; if (n.due_on) {
    const today = new Date().toLocaleDateString('sv-SE');
    if (n.due_on < today)
        return '<span class="qx-note-state overdue">Просрочено</span>';
    if (n.due_on === today)
        return '<span class="qx-note-state today">Сегодня</span>';
} return ''; }
function notesPage() {
    const notes = notesState.items.filter(n => (notesState.showDone || !n.completed) && (!notesState.query || [n.title, n.body, n.source, n.due_on].join(' ').toLocaleLowerCase('ru').includes(notesState.query.toLocaleLowerCase('ru'))));
    const n = notesState.items.find(n => n.id === notesState.selected);
    return `${pageHead('Быстрые заметки', 'Записывай поручения и информацию прямо во время звонка. Текст сохраняется автоматически.', `<button class="btn secondary" data-action="notes-export">⇩ Копия заметок</button><button class="btn primary" data-action="notes-new">＋ Новая заметка</button>`)}
 <div class="qx-notes-layout">
 <section class="panel qx-notes-list" aria-label="Список заметок"><div class="qx-notes-list-title"><h2>Мои записи</h2><span class="badge-count">${notesState.items.filter(x => !x.completed).length} активных</span></div>
 <input class="qx-note-search" data-notes-search placeholder="Поиск по заметкам…" value="${esc(notesState.query)}" aria-label="Поиск заметок">
 <label class="qx-notes-show-done"><input type="checkbox" data-notes-done ${notesState.showDone ? 'checked' : ''}> Показывать выполненные</label>
 <div class="qx-notes-items">${notes.map(item => `<button class="qx-note-row ${item.id === notesState.selected ? 'selected' : ''} ${item.completed ? 'is-done' : ''}" data-action="notes-open" data-id="${esc(item.id)}"><span class="qx-note-row-head"><b>${item.pinned ? '📌 ' : ''}${esc(notePreview(item))}</b>${noteStatus(item)}</span><small>${esc(item.source || 'Запись')} · ${esc(noteDate(item.updated_at))}</small><span class="qx-note-snippet">${esc(item.body.slice(0, 110) || 'Нажми, чтобы записать информацию…')}</span></button>`).join('') || '<p class="subtitle qx-notes-empty">Заметок пока нет. Создай первую запись кнопкой выше.</p>'}</div></section>
 <section class="panel qx-notes-editor" aria-label="Редактор заметки">${n ? `
 <div class="qx-note-editor-head"><div><span class="qx-note-eyebrow">ЗАПИСЬ · ${esc(noteDate(n.created_at))}</span><h2>Заметка</h2></div><div class="toolbar"><button class="btn secondary small" data-action="notes-pin" data-id="${esc(n.id)}">${n.pinned ? 'Открепить' : '📌 Закрепить'}</button><button class="btn secondary small" data-action="notes-complete" data-id="${esc(n.id)}">${n.completed ? '↺ Вернуть в работу' : '✓ Выполнено'}</button><button class="btn secondary small qx-note-delete" data-action="notes-delete" data-id="${esc(n.id)}">Удалить</button></div></div>
 <label class="field"><span>Заголовок</span><input data-note-field="title" maxlength="200" placeholder="Например: Андрей — позвонить на завод" value="${esc(n.title)}"></label>
 <div class="qx-note-meta"><label class="field"><span>Откуда информация</span><select data-note-field="source">${['Звонок', 'Поручение босса', 'Встреча', 'Переписка', 'Личная запись'].map(x => `<option value="${esc(x)}" ${n.source === x ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></label>
 <label class="field"><span>Выполнить до (необязательно)</span><input type="date" data-note-field="due_on" value="${esc(n.due_on)}"></label></div>
 <label class="field qx-note-body-label"><span>Что нужно сделать / что сообщили</span><textarea data-note-field="body" maxlength="30000" placeholder="Пиши прямо здесь: номер закупки, сроки, что попросили заказать, кому позвонить, какие документы отправить…" rows="12">${esc(n.body)}</textarea></label>
 ${n.due_on ? `<div class="qx-note-calendar-link"><button class="btn secondary small" data-action="notes-show-calendar" data-id="${esc(n.id)}">▦ Показать задачу в календаре · ${esc(tenderDate(n.due_on))}</button></div>` : '<p class="subtitle">Укажи дату выполнения — задача автоматически появится в календаре.</p>'}
 <div class="qx-note-footer"><span id="qx-note-save-state" role="status">${notesState.error ? esc(notesState.error) : '✓ Автосохранение включено'}</span><span>Данные хранятся локально в QX</span></div>
 ` : `<div class="qx-notes-intro"><div class="qx-notes-intro-icon">✎</div><h2>Записать поручение?</h2><p>Нажми «Новая заметка». Запись сразу появится в базе, а текст будет сохраняться во время печати.</p><button class="btn primary" data-action="notes-new">＋ Записать</button></div>`}</section></div>`;
}
function noteLocalKey(id) { return 'qx-notes-draft:' + id; }
function safeLocalDraft(id, record) { try {
    localStorage.setItem(noteLocalKey(id), JSON.stringify(record));
}
catch (e) {
    console.warn('Local note draft', e);
} }
function clearLocalDraft(id) { try {
    localStorage.removeItem(noteLocalKey(id));
}
catch (e) {
    console.warn(e);
} }
async function loadNotes() {
    try {
        const result = await api('notes', undefined, 'GET');
        notesState.items = result.items || [];
        notesState.loaded = true;
        notesState.error = '';
        for (const n of notesState.items) {
            try {
                const raw = localStorage.getItem(noteLocalKey(n.id));
                if (!raw)
                    continue;
                const d = JSON.parse(raw);
                if (Number(d.revision) > n.revision && d.fields) {
                    Object.assign(n, d.fields);
                    n._editRev = d.revision;
                    scheduleNoteWrite(n.id, 100);
                }
                else
                    clearLocalDraft(n.id);
            }
            catch (e) {
                console.warn('Draft restore', e);
            }
        }
        if (!notesState.items.some(n => n.id === notesState.selected))
            notesState.selected = notesState.items[0]?.id || '';
        if (state.tab === 'notes')
            render();
    }
    catch (e) {
        notesState.error = 'Не удалось загрузить заметки: ' + e.message;
        toast(notesState.error, true);
        if (state.tab === 'notes')
            render();
    }
}
async function addNote() {
    try {
        const result = await api('notes', { source: 'Звонок' });
        const n = result.note;
        notesState.items.unshift(n);
        notesState.selected = n.id;
        notesState.query = '';
        notesState.showDone = false;
        state.tab = 'notes';
        render(true);
        $('[data-note-field="body"]')?.focus();
    }
    catch (e) {
        toast('Не удалось создать запись: ' + e.message, true);
    }
}
function noteEdited(el) {
    const n = notesState.items.find(x => x.id === notesState.selected);
    if (!n)
        return;
    const key = el.dataset.noteField;
    if (!['title', 'body', 'source', 'due_on'].includes(key))
        return;
    n[key] = el.value;
    n._editRev = Math.max(Number(n._editRev || 0), Number(n.revision || 0)) + 1;
    safeLocalDraft(n.id, { revision: n._editRev, fields: { title: n.title, body: n.body, source: n.source, due_on: n.due_on, pinned: n.pinned, completed: n.completed } });
    const status = $('#qx-note-save-state');
    if (status)
        status.textContent = '● Сохранение…';
    scheduleNoteWrite(n.id, 550);
}
function scheduleNoteWrite(id, ms) { clearTimeout(noteSaveTimers.get(id)); noteSaveTimers.set(id, setTimeout(() => { noteSaveTimers.delete(id); void saveNote(id); }, ms)); }
async function saveNote(id) {
    const n = notesState.items.find(x => x.id === id);
    if (!n)
        return;
    const revision = Number(n._editRev || n.revision);
    if (revision <= n.revision)
        return;
    const fields = { title: n.title, body: n.body, source: n.source, due_on: n.due_on, pinned: n.pinned, completed: n.completed };
    const previous = noteSaveChains.get(id) || Promise.resolve();
    const task = previous.catch(() => { }).then(async () => {
        const result = await api('notes/' + encodeURIComponent(id), { revision, fields }, 'PATCH');
        const original = notesState.items.find(x => x.id === id);
        if (!original)
            return;
        original.revision = Math.max(original.revision, result.note.revision);
        if (Number(original._editRev || 0) <= original.revision) {
            clearLocalDraft(id);
            const status = $('#qx-note-save-state');
            if (notesState.selected === id && status)
                status.textContent = '✓ Сохранено ' + noteDate(result.note.updated_at);
        }
    });
    noteSaveChains.set(id, task);
    try {
        await task;
    }
    catch (e) {
        notesState.error = 'Не сохранено: ' + e.message;
        const status = $('#qx-note-save-state');
        if (notesState.selected === id && status)
            status.textContent = '⚠ ' + notesState.error;
        toast('Заметка: ' + e.message, true);
    }
}
async function noteToggle(id, prop) {
    const n = notesState.items.find(x => x.id === id);
    if (!n)
        return;
    n[prop] = !n[prop];
    n._editRev = Math.max(Number(n._editRev || 0), Number(n.revision || 0)) + 1;
    safeLocalDraft(id, { revision: n._editRev, fields: { title: n.title, body: n.body, source: n.source, due_on: n.due_on, pinned: n.pinned, completed: n.completed } });
    await saveNote(id);
    notesState.items.sort((a, b) => Number(a.completed) - Number(b.completed) || Number(b.pinned) - Number(a.pinned) || String(b.updated_at).localeCompare(String(a.updated_at)));
    if (n.completed && !notesState.showDone) {
        notesState.selected = notesState.items.find(x => !x.completed)?.id || '';
    }
    render();
}
async function removeNote(id) {
    if (!window.confirm('Удалить заметку без возможности восстановления? При необходимости сначала экспортируйте копию.'))
        return;
    try {
        clearTimeout(noteSaveTimers.get(id));
        await noteSaveChains.get(id)?.catch(() => { });
        await api('notes/' + encodeURIComponent(id), undefined, 'DELETE');
        clearLocalDraft(id);
        notesState.items = notesState.items.filter(x => x.id !== id);
        notesState.selected = notesState.items[0]?.id || '';
        render();
        toast('Заметка удалена');
    }
    catch (e) {
        toast('Ошибка удаления: ' + e.message, true);
    }
}
function pageContent() {
    switch (state.tab) {
        case 'home': return home();
        case 'notes': return notesPage();
        case 'tenders': return tendersPage();
        case 'tz': return tz();
        case 'build': return build();
        case 'verify': return verify();
        case 'arsenal': return arsenal();
        case 'docs': return docs();
        case 'catalog': return catalog();
        case 'prices': return prices();
        case 'settings': return settings();
        default: return home();
    }
}
function pageHead(title, sub, buttons = '') { return `<div class="page-header"><div><div class="eyebrow">QX / 2026 / MODERN</div><h1>${title}</h1><div class="subtitle">${sub}</div></div><div class="toolbar">${buttons}</div></div>`; }
function empty(title, sub, button) { return `<div class="empty"><div class="empty-icon">◇</div><strong>${title}</strong><p>${sub}</p>${button || ''}</div>`; }
function posChips() { return state.reqs.length ? `<div class="position-list">${state.reqs.map((r, i) => `<button class="position-chip ${state.pos === i ? 'active' : ''}" data-action="pos" data-index="${i}">${esc(r.title || `Позиция ${i + 1}`)} <span>${esc(r.quantity || 0)} шт.</span></button>`).join('')}<button class="position-chip" data-action="new-position">＋ Позиция</button></div>` : ''; }
function dashboardImportReport(result, number = '') {
    const matchesNumber = item => !number || item?.number === number || item?.tender?.number === number;
    const job = matchesNumber(state.eisImportJob) ? state.eisImportJob : null;
    const draft = matchesNumber(state.eisImportDraft) ? state.eisImportDraft : null;
    if (result && !matchesNumber(result)) result = null;
    const activeJob = job && ['queued', 'pending', 'running'].includes(job.status);
    const active = !!activeJob || !job && state.eisImportBusy && (!number || draft?.number === number);
    const tender = result?.tender || draft || (job?.tender_id ? { id: job.tender_id, number: job.number } : null);
    const noticeNumber = job?.number || result?.tender?.number || draft?.number || number;
    const cardButton = tender?.id ? `<button class="btn secondary small" data-action="tender-open" data-id="${esc(tender.id)}">Открыть карточку →</button>` : '';
    const retryButton = `<button class="btn secondary small qx-import-retry" data-action="home-eis-import" data-number="${esc(noticeNumber || '')}" data-tender-id="${esc(tender?.id || '')}">↻ Повторить поиск</button>`;
    const jobFailed = job && ['error', 'failed', 'cancelled', 'interrupted'].includes(job.status);
    const error = !active && (jobFailed ? state.eisImportError || job.message || 'Поиск завершился с ошибкой.' : !number ? state.eisImportError : '');
    if (active) {
        const stages = { connecting: 'Соединение с ЕИС', queued: 'В очереди', pending: 'Ожидание запуска', started: 'Запуск поиска', metadata: 'Получение сведений', notice: 'Поиск извещения', xml: 'Получение XML ЕИС', notice_xml: 'Получение XML ЕИС', html: 'Проверка карточки ЕИС', notice_html: 'Проверка карточки ЕИС', fallback: 'Проверка дополнительных источников', documents: 'Загрузка документов', discover: 'Поиск ссылок на документы', discovery: 'Поиск ссылок на документы', download: 'Скачивание документов', saving: 'Сохранение результата', complete: 'Завершение поиска' };
        const stage = job?.stage ? stages[job.stage] || job.stage : 'Запуск поиска';
        const progress = typeof job?.progress === 'number' && Number.isFinite(job.progress) ? Math.max(0, Math.min(100, job.progress)) : null;
        return `<div class="qx-import-feedback pending qx-import-job" role="status" aria-live="polite" aria-busy="true"><div class="qx-import-report"><div class="qx-import-report-head"><div><strong>${esc(stage)}</strong><span>${esc(job?.message || 'Ожидаем сведения о ходе загрузки.')}</span></div>${cardButton}</div><div class="qx-import-progress"><progress max="100" ${progress !== null ? `value="${progress}"` : ''} aria-label="Ход получения закупки">${progress !== null ? progress + '%' : 'Выполняется'}</progress>${progress !== null ? `<span>${Math.round(progress)}%</span>` : ''}</div><small class="qx-import-background">${noticeNumber ? `Закупка № ${esc(noticeNumber)}. ` : ''}${tender?.id ? 'Карточка уже создана. ' : ''}Можно продолжать работу в других разделах — поиск идёт в фоне.</small></div></div>`;
    }
    if (!result) {
        if (!error) return '';
        return `<div class="qx-import-feedback error" role="alert"><div class="qx-import-report"><div class="qx-import-report-head"><div><strong>Поиск не завершён</strong><span>${esc(error)}</span></div>${cardButton}</div><div class="qx-import-report-actions">${retryButton}</div></div></div>`;
    }
    const docs = result.documents_result;
    const fieldName = field => tenderLabels[typeof field === 'string' ? field : field?.field] || (typeof field === 'string' ? field : field?.field) || 'Поле';
    const fields = result.fields_applied || [];
    const conflicts = result.conflicts || [];
    const missing = result.missing_fields || result.notice?.missing_fields || [];
    const warnings = result.warnings || [];
    const failures = docs?.failures || [];
    const partial = result.partial || job?.status === 'partial';
    const safeSourceLink = value => {
        try {
            const url = new URL(value);
            return url.protocol === 'https:' && !url.username && !url.password ? url.href : '';
        } catch { return ''; }
    };
    const sourceStatus = { success: 'Получено', available: 'Доступен', ok: 'Получено', verified: 'Проверен', error: 'Ошибка', failed: 'Недоступен', unavailable: 'Недоступен', blocked: 'Доступ ограничен', skipped: 'Пропущен', empty: 'Данные не найдены', not_found: 'Данные не найдены', partial: 'Частичные данные', fallback: 'Дополнительный источник' };
    const sources = (result.sources || []).map(source => {
        const url = safeSourceLink(source.url);
        return `<li class="qx-import-source"><div><b>${esc(source.name || 'Источник')}</b>${source.status ? `<span class="qx-import-source-status">${esc(sourceStatus[source.status] || source.status)}</span>` : ''}</div>${source.message ? `<p>${esc(source.message)}</p>` : ''}${source.error_type ? `<small>${esc(({HTTP403: 'Доступ ограничен (HTTP 403)', HTTP404: 'Страница источника не найдена (HTTP 404)', URLError: 'Ошибка соединения с источником', TimeoutError: 'Источник не ответил за время ожидания', NoVerifiedFields: 'Проверяемые поля не найдены', ValueError: 'Страница или формат данных не распознаны'})[source.error_type] || source.error_type)}</small>` : ''}${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(new URL(url).hostname)} ↗</a>` : ''}</li>`;
    }).join('');
    let official = '';
    try {
        const url = new URL(result.search_url);
        if (url.origin === 'https://zakupki.gov.ru' && !url.username && !url.password) official = url.href;
    } catch { }
    return `<div class="qx-import-feedback ${error ? 'error' : partial ? 'partial' : ''}" role="status"><div class="qx-import-report"><div class="qx-import-report-head"><div><strong>${esc(result.tender?.title || (partial ? 'Получена часть данных' : 'Результат поиска'))}</strong><span>${esc(error || result.message || 'Проверьте полученные сведения в отчёте.')}</span></div>${cardButton}</div>${partial || error ? `<div class="qx-import-report-actions">${retryButton}</div>` : ''}<details class="qx-import-details"><summary>Источники и результат${partial ? ' · есть ограничения' : ''}</summary><div class="qx-import-counts">Заполнено полей: ${fields.length}${docs ? ` · новых файлов: ${(docs.imported || []).length} · уже в базе: ${(docs.duplicates || []).length}` : ' · загрузка документов не запрашивалась'}</div>${result.metadata_source ? `<p><b>Источник сведений:</b> ${esc(result.metadata_source)}.</p>` : ''}${sources ? `<ul class="qx-import-sources">${sources}</ul>` : ''}${fields.length ? `<p><b>Заполнено:</b> ${fields.map(field => esc(fieldName(field))).join(', ')}.</p>` : ''}${conflicts.length ? `<p><b>Сохранены ваши значения:</b> ${conflicts.map(field => esc(fieldName(field))).join(', ')}. Сверьте расхождения с извещением.</p>` : ''}${missing.length ? `<p><b>Не получено:</b> ${missing.map(field => esc(fieldName(field))).join(', ')}. Эти поля можно заполнить вручную.</p>` : ''}${warnings.map(warning => `<p>${esc(warning)}</p>`).join('')}${failures.length ? `<ul>${failures.map(failure => `<li>${esc(failure.name || failure.filename || 'Документ')}: ${esc(failure.reason || failure.message || 'не удалось загрузить')}</li>`).join('')}</ul>` : ''}${official ? `<a href="${esc(official)}" target="_blank" rel="noopener noreferrer">Открыть официальный поиск ЕИС ↗</a>` : ''}</details></div></div>`;
}
function home() {
    const n = state.reqs.length;
    const warnings = countWarnings();
    const tenders = state.tenders.items || [];
    const dates = dashboardDates();
    const recent = [...tenders].sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || ''))).slice(0, 3);
    const imported = state.eisImportResult;
    return `<div class="qx-dashboard">
    <div class="qx-dashboard-heading"><div><div class="eyebrow">QX WORKSPACE</div><h1>Всё для следующей победы</h1><p class="subtitle">Закупки, комплектация и документы — ваш рабочий день в одном окне.</p></div><span class="qx-dashboard-date">${esc(new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', weekday: 'long' }))}</span></div>
    <div class="qx-dashboard-top">
      <section class="qx-purchase-hero" aria-labelledby="home-eis-title"><div class="qx-hero-label"><span class="qx-live-dot" aria-hidden="true"></span> БЫСТРЫЙ СТАРТ · ЕИС</div><h2 id="home-eis-title">Начните с номера закупки</h2><p>Получите сведения о закупке и доступные документы. QX создаст карточку или дополнит уже сохранённую.</p>
        <form class="qx-purchase-form" id="home-eis-form"><label class="field" for="home-eis-number"><span>Номер извещения</span><input id="home-eis-number" name="notice_number" inputmode="numeric" autocomplete="off" maxlength="2048" placeholder="Номер закупки или ссылка ЕИС" value="${esc(state.homeEisNumber || '')}" ${state.eisImportBusy ? 'disabled' : ''} aria-describedby="home-eis-help"></label><button type="button" class="btn primary" data-action="home-eis-import" ${state.eisImportBusy ? 'disabled' : ''}>${state.eisImportBusy ? 'Получаем данные…' : 'Найти закупку →'}</button></form>
        <label class="qx-purchase-docs"><input type="checkbox" id="home-eis-docs" ${state.homeEisDownloadDocuments !== false ? 'checked' : ''} ${state.eisImportBusy ? 'disabled' : ''}> Скачать доступные документы в карточку</label><small id="home-eis-help" class="qx-hero-help">44-ФЗ и 223-ФЗ · Если ЕИС ограничит доступ, QX покажет причину и сохранит полученные результаты.</small>
        ${dashboardImportReport(imported)}
      </section>
      <section class="panel qx-project-card" aria-label="Текущий расчёт"><div class="section-title"><h2>Текущий расчёт</h2><span class="qx-project-indicator">${n ? 'В работе' : 'Можно начинать'}</span></div><h3>${esc(n ? state.name : 'От ТЗ — к предложению')}</h3><p class="subtitle">${esc(n ? state.source_filename || 'Позиции добавлены вручную' : 'Загрузите задание или создайте расчёт вручную. Все этапы — в разделе слева.')}</p><ol class="qx-project-steps"><li class="${n ? 'is-done' : ''}"><span>${n ? '✓' : '1'}</span><div><b>ТЗ и требования</b><small>${n ? fmt(n) + ' позиций в проекте' : 'Загрузить и разобрать задание'}</small></div></li><li class="${state.plans.length ? 'is-done' : ''}"><span>${state.plans.length ? '✓' : '2'}</span><div><b>Комплектация и расчёт</b><small>${state.plans.length ? 'Есть рассчитанные комплектации' : 'Подобрать оборудование и цены'}</small></div></li><li><span>3</span><div><b>Проверка и документы</b><small>${state.plans.length ? warnings ? 'Замечаний к проверке: ' + warnings : 'Открыть проверку соответствия' : 'Подготовить итоговое предложение'}</small></div></li></ol><div class="toolbar"><button class="btn primary" data-action="${n ? 'tab' : 'upload'}" ${n ? 'data-tab="build"' : ''}>${n ? 'Продолжить расчёт →' : '↥ Загрузить ТЗ'}</button><button class="btn secondary" data-action="${n ? 'project-save' : 'new'}">${n ? 'Сохранить' : 'Вручную'}</button></div></section>
    </div>
    <div class="qx-dashboard-metrics"><div class="panel"><span class="qx-metric-label">Закупки в реестре</span><strong>${state.tenders.loaded || tenders.length ? fmt(tenders.length) : '—'}</strong><button data-action="tender-nav" data-view="registry">Открыть реестр ↗</button></div><div class="panel"><span class="qx-metric-label">Позиций в расчёте</span><strong>${fmt(n)}</strong><span class="qx-metric-note">${state.plans.reduce((sum, plan) => sum + (plan.rows?.length || 0), 0)} строк комплектации</span></div><div class="panel"><span class="qx-metric-label">Себестоимость проекта</span><strong>${n ? rub(purchase()) : '—'}</strong><span class="qx-metric-note">${n ? 'По текущему расчёту' : 'Появится после расчёта'}</span></div><div class="panel"><span class="qx-metric-label">Замечания к комплектации</span><strong class="${warnings ? 'qx-metric-warning' : ''}">${state.plans.length ? fmt(warnings) : '—'}</strong><button data-action="tab" data-tab="verify">Проверить заявку ↗</button></div></div>
    <div class="qx-dashboard-bottom"><section class="panel qx-upcoming"><div class="section-title"><h2>Ближайшие даты</h2><button class="btn secondary small" data-action="tender-nav" data-view="calendar">Календарь →</button></div>${dates.length ? dates.map(event => `<button class="qx-dashboard-event" data-action="${event.action}" data-id="${esc(event.id)}"><span class="qx-event-date"><b>${esc(event.date.slice(8))}</b><small>${esc(new Date(event.date + 'T12:00:00').toLocaleDateString('ru-RU', { month: 'short' }))}</small></span><span class="qx-event-copy"><b>${esc(event.label)}</b><small>${esc(event.title)}</small></span><span class="qx-event-arrow" aria-hidden="true">↗</span></button>`).join('') : '<div class="qx-dashboard-empty"><span aria-hidden="true">▦</span><b>Сроки под контролем</b><p>Здесь появятся ближайшие даты закупок и задач из календаря.</p></div>'}</section>
    <section class="panel qx-recent"><div class="section-title"><h2>Недавние закупки</h2><button class="btn secondary small" data-action="tender-nav" data-view="registry">Все закупки →</button></div>${recent.length ? recent.map(tender => `<button class="qx-dashboard-tender" data-action="tender-open" data-id="${esc(tender.id)}"><span><small>№ ${esc(tender.number || 'не указан')}</small><b>${esc(tender.title || 'Закупка без названия')}</b><small>${esc(tender.customer || 'Заказчик пока не указан')}</small></span><span class="status ${tenderStatusColor(tender.status)}">${esc(tender.status || 'Черновик')}</span></button>`).join('') : '<div class="qx-dashboard-empty"><span aria-hidden="true">▤</span><b>Ваша следующая закупка — здесь</b><p>Введите номер выше или создайте карточку в тендерном отделе.</p></div>'}</section></div>
    <div class="qx-dashboard-quick"><span>Под рукой</span><button class="btn secondary" data-action="restore">▣ Открыть автосохранение</button><button class="btn secondary" data-action="tab" data-tab="notes">✎ Быстрая заметка</button><button class="btn secondary" data-action="tab" data-tab="docs">↗ Документы и экспорт</button></div>
    </div>`;
}
// A project can hold several documents. Every position remembers its source.
function storeCurrentDoc() {
    const doc = (state.tzDocuments || []).find(x => x.id === state.activeTzDocId);
    if (!doc)
        return;
    doc.overrides = clone(state.overrides || {});
    doc.characteristics = state.characteristics || [];
}
function activeDocForPosition(index = state.pos) {
    const req = state.reqs[index] || {};
    return (state.tzDocuments || []).find(x => x.id === req._qx_doc_id) || null;
}
function chooseDocForPosition(index = state.pos) {
    storeCurrentDoc();
    const doc = activeDocForPosition(index);
    if (!doc) {
        state.activeTzDocId = '';
        state.source_text = '';
        state.source_filename = '';
        state.source_docx_base64 = '';
        state.characteristics = [];
        state.overrides = {};
        state.sourcePreview = null;
        state.charRows = [];
        return;
    }
    if (state.activeTzDocId === doc.id)
        return;
    state.activeTzDocId = doc.id;
    state.source_text = doc.text || '';
    state.source_filename = doc.name || '';
    state.source_docx_base64 = doc.docx || '';
    state.characteristics = doc.characteristics || [];
    state.overrides = clone(doc.overrides || {});
    state.sourcePreview = null;
    state.charRows = [];
}
function currentDocCalculation() {
    const source = state.activeTzDocId;
    const indices = state.reqs.map((r, i) => r._qx_doc_id === source ? i : -1).filter(i => i >= 0);
    return { reqs: indices.map(i => state.reqs[i]), plans: indices.map(i => state.plans[i] || {}) };
}
function tzAiPanel() {
    const models = state.tenderAiStatus?.models || [];
    const proposals = state.tzAiResults[state.pos]?.proposals || [];
    const report = state.tzAiResults[state.pos];
    return `<div class="col-12 panel"><div class="section-title"><h2>✧ QX AI · Понимание технического задания</h2><span class="badge-count">Локальная нейросеть</span></div>
 <p class="subtitle">После загрузки ТЗ нейросеть может проверить пропуски и ошибки обычного парсера и предлагает исправления с дословными цитатами. Однозначно подтверждённые пустые поля может заполнить автоматически; спорные исправления потребуют подтверждения. Подбор и проверка выполняются движком QX.</p>
 <div class="toolbar" style="margin:14px 0;align-items:center;flex-wrap:wrap">
  <select id="tz-ai-model" aria-label="Локальная нейросеть для разбора ТЗ" style="max-width:330px"><option value="">Выберите нейросеть...</option>${models.map(m => `<option value="${esc(m)}" ${state.tzAiModel === m ? 'selected' : ''}>${esc(m)}</option>`).join('')}</select>
  <button class="btn secondary small" data-action="tz-ai-models">↻ Проверить модели</button>
  <button class="btn secondary small" data-action="tz-ai-diagnostic">Тест ответа AI</button>
  <button class="btn primary" data-action="tz-ai-run" ${!state.reqs.length || state.tzAiRunning ? 'disabled' : ''}>${state.tzAiRunning ? 'Анализируется...' : '✧ Проверить текущую позицию'}</button>
  <button class="btn secondary" data-action="tz-ai-all" ${!state.reqs.length || state.tzAiRunning ? 'disabled' : ''}>Проверить все позиции</button>
 </div>
 <label class="tz-ai-toggle"><input type="checkbox" data-tz-ai-auto ${state.tzAiAuto ? 'checked' : ''}> Проверять все новые позиции ТЗ сразу после загрузки (если выбрана модель)</label>
 <label class="tz-ai-toggle"><input type="checkbox" data-tz-ai-fill ${state.tzAiFill ? 'checked' : ''}> Автоматически заполнять только пустые числовые поля с однозначной цитатой (исправления и неоднозначности — вручную)</label>
 <p class="subtitle">${esc(state.tenderAiStatus?.message || 'Нажмите «Проверить модели», чтобы найти Ollama и GGUF на этом компьютере.')} <button class="btn secondary small" data-action="tender-ai-model-folder">Папка GGUF</button></p>
 ${!models.length ? `<p class="note">QX AI Lite (около 1,2–1,5 ГБ) настраивается при установке. Если модель не обнаружена, воспользуйтесь «УСТАНОВИТЬ_QX_AI.cmd» и нажмите «Проверить модели». Обычный разбор ТЗ доступен всегда.</p>` : ''}
 ${state.tzAiMessage ? `<p class="subtitle" role="status">${esc(state.tzAiMessage)}</p>` : ''}
 ${report ? `<div class="note">${esc(report.warning || '')}</div>${report.rejected ? `<small>Отклонено неподтверждённых предложений: ${report.rejected}</small>` : ''}
 <div class="table-wrap"><table class="table"><thead><tr><th>Применить</th><th>Характеристика</th><th>Сейчас</th><th>Предложение AI</th><th>Цитата из ТЗ</th></tr></thead><tbody>${proposals.map((p, i) => `<tr><td><input type="checkbox" data-tz-ai-check="${i}" checked></td><td>${esc(reqLabels[p.field] || p.field)}</td><td>${esc(String(p.previous ?? 'Не распознано'))}</td><td><b>${esc(String(p.value))}</b></td><td><small>${esc(p.quote)}</small></td></tr>`).join('') || '<tr><td colspan="5">Исправления с проверяемыми цитатами не предложены. Это не гарантирует полноту распознавания.</td></tr>'}</tbody></table></div>
 ${proposals.length ? `<button class="btn primary" data-action="tz-ai-apply" style="margin-top:12px">Применить отмеченные и пересчитать</button>` : ''}` : ''}</div>`;
}
const complexityLevels = { simple: 'Простое', medium: 'Среднее', complex: 'Сложное', unknown: 'Недостаточно данных' };
function complexityForDoc(doc) {
    const value = doc?.complexity;
    return value && Object.prototype.hasOwnProperty.call(complexityLevels, value.level) ? value : { level: 'unknown', reasons: ['Оценка недоступна. Откройте сохранённый проект заново или загрузите исходное ТЗ.'] };
}
function tzComplexityBadge(doc) {
    const result = complexityForDoc(doc);
    return `<span class="qx-complexity-badge level-${result.level}" data-tz-complexity-badge data-level="${result.level}" data-doc-id="${esc(doc.id)}" aria-label="Сложность ТЗ: ${complexityLevels[result.level]}">${complexityLevels[result.level]}</span>`;
}
function tzComplexityPanel() {
    const doc = activeDocForPosition();
    if (!doc) return '';
    const result = complexityForDoc(doc);
    const reasons = Array.isArray(result.reasons) ? result.reasons.filter(item => typeof item === 'string').slice(0, 10) : [];
    return `<section class="panel qx-tz-complexity level-${result.level}" data-tz-complexity data-level="${result.level}" data-doc-id="${esc(doc.id)}" aria-label="Оценка сложности технического задания"><div class="qx-tz-complexity-heading"><div><span class="eyebrow">ОЦЕНКА ТЕХНИЧЕСКОЙ ЧАСТИ</span><h2>Сложность технической части ТЗ</h2><small>${esc(doc.name)}</small></div>${tzComplexityBadge(doc)}</div><ul class="qx-tz-complexity-reasons">${reasons.map(reason => `<li>${esc(reason)}</li>`).join('')}</ul><p class="qx-tz-complexity-note">${esc(result.disclaimer || 'Ориентировочная оценка трудоёмкости по распознанным требованиям. Проверьте исходное ТЗ.')}</p></section>`;
}
function tzAdditionalRequirements() {
    const doc = activeDocForPosition();
    if (!doc) return '';
    const assessment = complexityForDoc(doc);
    const conditions = Array.isArray(assessment.additional_requirements) ? assessment.additional_requirements : [];
    return `<section class="panel qx-tz-additional" data-tz-additional data-doc-id="${esc(doc.id)}"><div class="section-title"><h2>Дополнительные требования ТЗ</h2><span class="badge-count">${conditions.length}</span></div><p class="subtitle">Реестры, сертификаты и другие условия показаны отдельно. Они не повышают сложность технической части.</p>${conditions.length ? `<ul class="qx-tz-condition-list">${conditions.map(condition => `<li data-tz-condition="${esc(condition.key)}"><strong>${esc(condition.label)}</strong>${Array.isArray(condition.evidence) && typeof condition.evidence[0] === 'string' ? `<small>Из ТЗ: «${esc(condition.evidence[0])}»</small>` : ''}</li>`).join('')}</ul>` : '<p class="qx-tz-condition-empty">Отдельные условия в распознанном тексте не выделены. Проверьте исходный документ.</p>'}</section>`;
}
function tzDocumentList() {
    return (state.tzDocuments || []).length ? `<div class="panel"><div class="section-title"><h2>Загруженные ТЗ</h2><span class="badge-count">${state.tzDocuments.length}/12 документов</span></div>
 ${state.tzDocuments.map((d, i) => `<div class="activity-item"><span class="activity-icon">${i + 1}</span><div><strong>${esc(d.name)}</strong><small>${state.reqs.filter(r => r._qx_doc_id === d.id).length} позиций</small><div class="qx-doc-complexity">${tzComplexityBadge(d)}</div></div><button class="btn secondary small" data-action="tz-doc-view" data-id="${esc(d.id)}">Открыть</button><button class="btn secondary small" data-action="tz-doc-remove" data-id="${esc(d.id)}">Убрать</button></div>`).join('')}
 <p class="subtitle">Дополнительные файлы добавляются к текущему расчёту. Исходные документы и привязки сохраняются в .qxproj. Для отдельного расчёта используйте «Новый расчёт».</p></div>` : '';
}
function tenderLinkPanel() {
    const checked = !!state.tenderLinkEnabled;
    return `<div class="qx-tz-tender-link panel">
    <div class="qx-tender-link-head"><div><h2>Привязка к тендерному отделу</h2><p class="subtitle">Расчёт можно оставить отдельно от реестра закупок. Сами документы ЕИС скачивать не нужно.</p></div>
    <label class="qx-toggle"><input type="checkbox" data-tender-auto-link ${checked ? 'checked' : ''}><span>Добавить в реестр закупок</span></label></div>
    ${checked ? `<div class="qx-tender-link-fields"><label class="field">Номер извещения ЕИС<input data-tender-notice-input inputmode="numeric" maxlength="20" placeholder="11, 19 или 20 цифр" value="${esc(state.tenderNoticeNumber || '')}"></label><button class="btn secondary" data-action="tender-eis-preview" ${/^\d{19,20}$/.test(state.tenderNoticeNumber || '') ? '' : 'disabled'}>Получить сведения из ЕИС</button></div>
      ${state.reqs.some(r => r._qx_doc_id) ? `<button class="btn primary small" data-action="tender-link-loaded" ${/^(?:\d{11}|\d{19,20})$/.test(state.tenderNoticeNumber || '') ? '' : 'disabled'}>Привязать уже загруженное ТЗ</button>` : ''}
      <p class="subtitle">При загрузке ТЗ QX привяжет его к указанному номеру. Для 223-ФЗ допускается 11 цифр; получение XML ЕИС доступно только для 19–20 цифр. Подтверждённые поля из ЕИС добавятся только в пустые поля карточки; при недоступности сайта их можно заполнить вручную.</p>
      ${state.tenderEisMessage ? `<p class="qx-eis-status" role="status">${esc(state.tenderEisMessage)}</p>` : ''}
      ${state.tenderEisPreview?.notice ? `<div class="qx-eis-preview"><b>${esc(state.tenderEisPreview.notice.title || 'Закупка ' + state.tenderNoticeNumber)}</b><span>Заказчик: ${esc(state.tenderEisPreview.notice.customer || 'не найден')}</span><span>НМЦК: ${esc(state.tenderEisPreview.notice.nmck || 'не найдена')}</span><span>Подача до: ${esc(state.tenderEisPreview.notice.application_due_on || 'не найдена')}</span></div>` : ''}
    ` : ''}
  </div>`;
}
function tz() { return `${pageHead('Техническое задание', 'Разбор Word/PDF, проверка распознавания и редактирование характеристик.', `<button class="btn secondary" data-action="new-position">＋ Позиция</button><button class="btn primary" data-action="upload">↥ Загрузить ТЗ</button>`)}<div class="grid"><div class="col-12">${state.source_filename ? `<div class="loaded-source"><span>📄</span><div><strong>Загруженный документ: ${esc(state.source_filename)}</strong><small>${state.characteristics.length} строк характеристик · ${currentDocCalculation().reqs.length} ${currentDocCalculation().reqs.length % 10 === 1 && state.reqs.length % 100 !== 11 ? 'позиция' : state.reqs.length % 10 >= 2 && state.reqs.length % 10 <= 4 && (state.reqs.length % 100 < 12 || state.reqs.length % 100 > 14) ? 'позиции' : 'позиций'} · исходный файл хранится в проекте${state.source_docx_base64 ? ' для заполнения заявки' : ''}</small></div><button class="btn secondary small" data-action="view-source">Просмотреть ТЗ</button></div>` : ''}${tzComplexityPanel()}${tzAdditionalRequirements()}<div class="drop-area" id="drop" data-action="upload"><div class="drop-icon">↥</div><strong>Перетащите несколько файлов ТЗ сюда</strong><p>DOCX, PDF, Excel, ODT, TXT, CSV, MD · можно выбрать сразу несколько и добавлять позже</p><button class="btn primary" data-action="upload">＋ Добавить файлы ТЗ</button></div>${tenderLinkPanel()}${tzDocumentList()}</div>${tzAiPanel()}${state.reqs.length ? `<div class="col-12 panel"><div class="section-title"><h2>Позиции технического задания</h2><button class="btn primary small" data-action="select">⚡ Подобрать комплектующие</button></div>${posChips()}<div class="flex between wrap" style="margin-bottom:18px"><div class="field" style="flex:1"><label>Имя проекта</label><input data-field="name" value="${esc(state.name)}"></div><div class="field"><label>Поиск характеристики</label><input data-field="reqSearch" placeholder="Например: USB, кэш, DDR5" value="${esc(state.reqSearch)}"></div></div><div class="toolbar" style="justify-content:flex-end;margin:12px 0"><button class="btn secondary small" data-action="toggle-all-fields">${state.showAllFields ? 'Скрыть пустые характеристики' : 'Показать все 224 характеристики'}</button></div>${num(currentReq()?.quantity) <= 0 ? '<div class="warning quantity-warning" style="margin-top:18px">⚠ Количество товара не найдено в ТЗ. Укажите его вручную, иначе стоимость партии будет нулевой и коммерческое предложение не сформируется.</div>' : ''}${requirements()}<div class="separator"></div><button class="btn primary" data-action="select">⚡ Пересчитать по ТЗ</button></div>` : `<div class="col-12 panel">${empty('ТЗ ещё не загружено', 'Можно загрузить Word с несколькими позициями или создать пустую позицию вручную.')}</div>`}</div>`; }
function options(items, selected) { return items.map(x => `<option value="${esc(x.val)}" ${String(selected ?? '') === x.val ? 'selected' : ''}>${esc(x.label)}</option>`).join(''); }
function reqField(key, r) {
    const value = r[key] === undefined ? state.reqDefaults[key] : r[key];
    const lab = reqLabels[key] || key;
    const attr = `data-req="${esc(key)}"`;
    if (key === 'product_type')
        return field(lab, `<select ${attr}>${options([{ val: 'system', label: 'Системный блок' }, { val: 'aio24', label: 'Моноблок 23,8″' }, { val: 'aio27', label: 'Моноблок 27″' }, { val: 'aws24', label: 'АРМ 23,8″' }, { val: 'aws27', label: 'АРМ 27″' }, { val: 'monitor', label: 'Монитор' }, { val: 'keyboard', label: 'Клавиатура' }, { val: 'mouse', label: 'Мышь' }], value)}</select>`);
    if (key === 'platform')
        return field(lab, `<select ${attr}>${options([{ val: '', label: 'Автоматически' }, { val: 'amd', label: 'AMD · вручную' }, { val: 'intel', label: 'Intel · вручную' }], value)}</select>`);
    if (key === 'equipment_profile_name')
        return field(lab, `<select ${attr}>${options([{ val: '', label: 'Стандарт QX' }, ...(state.catalogs.equipment_profile || []).map((x) => ({ val: x.name, label: x.name }))], value)}</select>`);
    if (key === 'system_case_mode')
        return field(lab, `<select ${attr}>${options([{ val: 'auto', label: 'Автоматически' }, { val: 'qx_standard', label: 'QX ТИП 1' }, { val: 'qx_protected', label: 'QX ТИП 2' }, { val: 'custom', label: 'Свой корпус' }], value)}</select>`);
    if (key === 'custom_case_name')
        return field('Корпус из моей базы', `<select ${attr}><option value="">Выберите сохранённый корпус</option>${(state.catalogs.case || []).map(x => `<option value="${esc(x.name)}" ${x.name === value ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select>`);
    if (key === 'aio_platform_mode')
        return field('Выбор моноблочной платформы', `<select ${attr}>${options([{ val: 'qx', label: 'Стандартная QX' }, { val: 'custom', label: 'Из собственной базы / вручную' }], value)}</select>`);
    if (key === 'custom_aio_name')
        return field('Моноблочная платформа из базы', `<select ${attr}><option value="">Выберите платформу</option>${(state.catalogs.aio || []).map(x => `<option value="${esc(x.name)}" ${x.name === value ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select>`);
    if (key === 'keyboard_source_mode' || key === 'mouse_source_mode')
        return field(lab, `<select ${attr}>${options([{ val: 'qx', label: 'Стандарт QX' }, { val: 'catalog', label: 'Из моей базы' }, { val: 'manual', label: 'Вручную' }], value)}</select>`);
    if (key === 'keyboard_catalog_item' || key === 'mouse_catalog_item' || key === 'monitor_catalog_item') {
        const kind = key.split('_')[0];
        const items = state.catalogs[kind] || [];
        const mode = kind === 'monitor' ? 'catalog' : String(r[kind + '_source_mode'] || 'qx');
        const selectable = true; // Direct selection switches keyboard/mouse source to catalog automatically.
        const title = kind === 'keyboard' ? 'клавиатуру' : kind === 'mouse' ? 'мышь' : 'монитор';
        const label = kind === 'monitor' ? 'Автоматически по требованиям ТЗ' : 'Автоматически выбрать подходящую модель';
        return `<div class="field catalog-picker"><label>${esc(lab)}</label><select ${attr} ${selectable ? '' : 'disabled'}><option value="">${esc(label)}</option>${items.map(x => `<option value="${esc(x.name)}" ${x.name === value ? 'selected' : ''}>${esc(x.name)}${x.data?.price ? ` — ${fmt(x.data.price)} ₽` : ''}</option>`).join('')}</select><div class="catalog-picker-hint">${!selectable ? 'Выберите модель — источник переключится на базу автоматически.' : items.length ? `Доступно моделей: ${items.length}. Выбор модели подключит базу автоматически, цена и реестровый номер попадут в расчёт.` : `В базе пока нет ни одной записи.`} <button class="inline-catalog-link" type="button" data-action="open-peripheral-catalog" data-kind="${kind}">${items.length ? `Управлять базой` : `Добавить ${title} в базу`}</button></div></div>`;
    }
    if (typeof value === 'boolean' || key.startsWith('need_') || key === 'forbid_wireless')
        return field(lab, `<select ${attr}>${options([{ val: 'true', label: 'Да' }, { val: 'false', label: 'Нет' }], !!value ? 'true' : 'false')}</select>`);
    const isNumeric = typeof value === 'number' || /^quantity$|^nmck$|^monitor_inches$|_in$|_inches$|_hz$|_min$|_max$|_min_|_max_|_mm$|_gb$|_mhz$|_w$|_months$|_ghz_min$|_mb_min$/.test(key);
    return field(lab, `<input ${attr} type="${isNumeric ? 'number' : 'text'}" ${isNumeric ? 'step="any" min="0"' : ''} value="${esc(value ?? '')}">`);
}
function field(label, input) { return `<div class="field"><label>${esc(label)}</label>${input}</div>`; }
function productTitle(type) { return ({ system: 'Системный блок', aio24: 'Моноблок 23,8″', aio27: 'Моноблок 27″', aws24: 'АРМ 23,8″', aws27: 'АРМ 27″', monitor: 'Монитор', keyboard: 'Клавиатура', mouse: 'Мышь' })[type] || 'Не определён'; }
function groupsForProduct(r) {
    const t = String(r.product_type || 'system');
    const isAio = t.startsWith('aio') || t.startsWith('aws');
    const isSystem = t === 'system' || t.startsWith('aws');
    const isMonitor = t === 'monitor';
    const isPc = isAio || isSystem;
    const standalonePeripheral = t === 'keyboard' || t === 'mouse' || t === 'monitor';
    const basic = standalonePeripheral
        ? ['title', 'item_name', 'quantity', 'nmck', 'product_type', 'ktru_code']
        : ['title', 'item_name', 'quantity', 'nmck', 'product_type', 'platform', 'equipment_profile_name', 'ktru_code'];
    const processor = ['cpu_model', 'cpu_cores_min', 'cpu_threads_min', 'cpu_freq_ghz_min', 'cpu_freq_max_ghz_min', 'cpu_l3_mb_min', 'cpu_tdp_w_max', 'cpu_passmark_min', 'need_integrated_graphics'];
    const memory = ['ram_gb_min', 'ram_type', 'ram_mhz_min', 'ram_max_supported_gb_min', 'ram_slots_min', 'ssd_gb_min', 'ssd_interface', 'hdd_gb_min'];
    const extras = ['need_gpu', 'gpu_vram_gb_min', 'need_wifi', 'need_bluetooth', 'forbid_wireless', 'need_cardreader', 'need_keyboard', 'keyboard_source_mode', 'keyboard_catalog_item', 'need_mouse', 'mouse_source_mode', 'mouse_catalog_item', 'need_os', 'os_text'];
    const ports = ['psu_w_min', 'm2_key_m_min', 'm2_key_e_min', 'ethernet_mbps_min', 'ethernet_ports_min', 'usb2_total_min', 'usb3_gen1_total_min', 'usb3_gen2_total_min', 'usb_c_total_min'];
    const chassis = ['case_height_max_mm', 'case_length_max_mm', 'case_width_max_mm', 'bay_525_min', 'bay_25_min', 'bay_35_min', 'system_case_mode', 'custom_case_name'];
    const display = ['monitor_inches', 'monitor_resolution', 'monitor_matrix', 'monitor_refresh_hz_min', 'monitor_brightness_min'];
    const aio = ['aio_platform_mode', 'custom_aio_name'];
    const groups = [];
    if (t === 'keyboard')
        groups.push(['Выбор клавиатуры', ['keyboard_source_mode', 'keyboard_catalog_item']]);
    else if (t === 'mouse')
        groups.push(['Выбор мыши', ['mouse_source_mode', 'mouse_catalog_item']]);
    else if (t === 'monitor')
        groups.push(['Выбор модели из базы мониторов', ['monitor_catalog_item']]);
    groups.push(['Основные сведения', basic]);
    if (isPc) {
        groups.push(['Процессор', processor], ['Память и накопители', memory], ['Периферия и оснащение', extras]);
        groups.push([isAio ? 'Интерфейсы моноблока' : 'Корпус и интерфейсы', isSystem ? [...ports, ...chassis] : ports]);
    }
    if (isAio) {
        if (t.startsWith('aws'))
            groups.push(['Монитор для АРМ', ['monitor_catalog_item']]);
        groups.push(['Экран и моноблочная платформа', [...display, ...aio, 'warranty_months_min']]);
    }
    else if (isMonitor)
        groups.push(['Характеристики монитора', [...display, 'monitor_hdmi_ports_min', 'monitor_dp_ports_min', 'warranty_months_min']]);
    else if (t === 'keyboard' || t === 'mouse')
        groups.push(['Параметры изделия', ['warranty_months_min']]);
    else if (isSystem)
        groups.push(['Гарантия', ['warranty_months_min']]);
    else
        groups.push(['Параметры изделия', ['warranty_months_min']]);
    return groups;
}
function requirements() {
    const r = currentReq();
    if (!r)
        return '';
    const q = (state.reqSearch || '').toLowerCase().trim();
    const seen = new Set();
    const allGroups = groupsForProduct(r);
    const relevant = new Set(allGroups.flatMap(g => g[1]));
    const hiddenNotApplicable = new Set([...legacyKeyGroups.flatMap(g => g[1])].filter(k => !relevant.has(k)));
    // Standalone peripherals must not offer a motherboard/manufacturer profile.
    // The selection is made only from the catalog matching the product type.
    if (['keyboard', 'mouse', 'monitor'].includes(String(r.product_type || ''))) {
        ['equipment_profile_name', 'platform', 'keyboard_catalog_item', 'mouse_catalog_item', 'monitor_catalog_item', 'keyboard_source_mode', 'mouse_source_mode'].forEach(k => { if (!relevant.has(k))
            hiddenNotApplicable.add(k); });
    }
    const type = String(r.product_type || 'system');
    // Old projects may contain values of an unrelated device type. These must not
    // silently appear under 'Additional requirements' after classifying a monoblock.
    for (const key of Object.keys({ ...state.reqDefaults, ...r })) {
        if ((type.startsWith('aio') || type === 'monitor') && (/^custom_case_|^system_case_|^case_(?:width|length|height)|^bay_|^protected_case$/.test(key)))
            hiddenNotApplicable.add(key);
        if (type === 'system' && (/^monitor_|^custom_aio_|^aio_platform_/.test(key)))
            hiddenNotApplicable.add(key);
        if (type === 'monitor' && (/^cpu_|^ram_|^ssd_|^hdd_|^psu_|^m2_|^ethernet_|^usb[23]_|^need_integrated_graphics$|^platform$/.test(key)))
            hiddenNotApplicable.add(key);
    }
    // Do not leak another product's field group into 'Additional requirements'.
    const unavailable = new Set(['raw_text', 'manual_requirements', 'source_docx_base64', 'source_filename']);
    let groups = `<div class="product-classification"><span>Распознано изделие</span><strong>${esc(productTitle(r.product_type))}</strong><span class="muted mini">Неверный тип? Измените его в таблице ниже. Подбор обновится автоматически.</span></div>`;
    if (['monitor', 'keyboard', 'mouse'].includes(type)) {
        const kindName = type === 'monitor' ? 'мониторов' : type === 'keyboard' ? 'клавиатур' : 'мышей';
        const count = (state.catalogs[type] || []).length;
        groups += `<div class="peripheral-guide"><strong>База ${kindName} · ${count} моделей</strong><span>${type === 'monitor' ? 'Выберите модель ниже либо оставьте автоматический подбор.' : 'Можно сразу выбрать модель — источник переключится на базу автоматически. По умолчанию сохраняется QX.'} Материнские платы здесь не используются.</span><button class="btn secondary small" data-action="open-peripheral-catalog" data-kind="${type}">Открыть базу ${kindName} ↗</button></div>`;
    }
    for (const [label, keys] of allGroups) {
        keys.forEach(x => seen.add(x));
        const fields = keys.filter(k => !q || (reqLabels[k] || k).toLowerCase().includes(q) || k.toLowerCase().includes(q));
        if (!fields.length)
            continue;
        groups += `<div class="requirement-group"><h2>${esc(label)} <span class="badge-count">${fields.length}</span></h2><div class="table-wrap"><table class="table requirements-table"><thead><tr><th>Характеристика</th><th>Требуемое значение / выбор</th></tr></thead><tbody>${fields.map(k => `<tr><td><strong>${esc(reqLabels[k] || k)}</strong></td><td>${reqField(k, r)}</td></tr>`).join('')}</tbody></table></div></div>`;
    }
    const extras = Object.keys({ ...state.reqDefaults, ...r }).filter(k => !seen.has(k) && !unavailable.has(k) && !hiddenNotApplicable.has(k) && !Array.isArray(r[k]) && (!q || (reqLabels[k] || k).toLowerCase().includes(q)) && (state.showAllFields || q || r[k] !== undefined && r[k] !== null && r[k] !== false && r[k] !== 0 && r[k] !== ''));
    if (extras.length)
        groups += `<div class="requirement-group"><h2>Дополнительные требования <span class="badge-count">${extras.length}</span></h2><div class="table-wrap"><table class="table requirements-table"><thead><tr><th>Характеристика</th><th>Требуемое значение / выбор</th></tr></thead><tbody>${extras.map(k => `<tr><td><strong>${esc(reqLabels[k] || k)}</strong></td><td>${reqField(k, r)}</td></tr>`).join('')}</tbody></table></div></div>`;
    return groups + `<div class="note" style="margin-top:20px">Изменения требований автоматически сохраняются, а рассчитанная комплектация обновляется после изменения характеристики. Неизвестные характеристики не считаются выполненными без подтверждения.</div>`;
}
function build() { const p = currentPlan(); return `${pageHead('Сборка и цены', 'Редактируемая спецификация с мгновенным пересчётом сумм и сохранением ручных правок.', `<button class="btn secondary" data-action="new-position">＋ Позиция</button><button class="btn secondary" data-action="select">↻ Пересчитать</button><button class="btn primary" data-action="full">⛶ На весь экран</button>`)}${state.reqs.length ? `${state.source_filename ? `<div class="source-strip">📄 ТЗ: <strong>${esc(state.source_filename)}</strong><button class="btn secondary small" data-action="view-source">Просмотреть</button></div>` : ''}${posChips()}${p ? `<div class="grid"><div class="col-3 panel stat"><div class="label">Себестоимость 1 ед.</div><div class="value" id="unit-cost">${rub(unitCost(p))}</div><div class="detail">Без доставки и БГ/ГО</div></div><div class="col-3 panel stat"><div class="label">Количество</div><div class="value" style="margin:10px 0 5px"><input aria-label="Количество изделий" title="Количество изделий в закупке" data-build-quantity type="number" step="1" min="1" value="${esc(p.req.quantity ?? 0)}" style="font-size:20px;font-weight:750;width:105px;max-width:100%;padding:5px 9px"></div><div class="detail" data-quantity-hint>${num(p.req.quantity) > 0 ? 'Количество изделий в партии' : 'Укажите количество больше нуля'}</div></div><div class="col-3 panel stat"><div class="label">Стоимость партии</div><div class="value" id="total-cost">${rub(unitCost(p) * num(p.req.quantity))}</div><div class="detail">Комплектующие × количество</div></div><div class="col-3 panel stat"><div class="label">Соответствие ТЗ</div><div class="value ${(p.checks || []).some(c => c['Статус'] === 'НЕ ПРОХОДИТ') ? 'warn' : 'good'}">${(p.checks || []).filter(c => c['Статус'] === 'OK').length}/${(p.checks || []).length}</div><div class="detail">Проверок пройдено</div></div><div class="col-12 panel">${tableBuild(p)}<div class="flex between wrap" style="margin-top:16px"><button class="btn secondary" data-action="manual">＋ Добавить строку</button><div class="flex"><span class="muted mini">Строк: ${p.rows.length}</span><strong id="table-total">Итого: ${rub(unitCost(p))}</strong></div></div></div>${p.warnings?.length ? `<div class="col-12 panel"><div class="section-title"><h2>Замечания к подбору</h2><span class="badge-count">${p.warnings.length}</span></div>${p.warnings.map(w => `<div class="warning">⚠ ${esc(w)}</div>`).join('')}</div>` : ''}</div>` : empty('Позиции не подобраны', 'Нажмите «Подобрать комплектующие», чтобы сформировать состав.', `<button class="btn primary" data-action="select">⚡ Подобрать</button>`)}` : empty('Сначала загрузите ТЗ', 'Или создайте позицию вручную.', `<button class="btn primary" data-action="upload">↥ Загрузить ТЗ</button>`)}`; }
function tableBuild(p) { return `<div class="table-toolbar"><div><h2>Спецификация оборудования</h2><span class="muted mini">Цена в ₽ или $ · Enter сохраняет изменение</span></div><div class="toolbar"><input class="table-search" type="search" data-filter-rows placeholder="Поиск по комплектующим…" aria-label="Поиск по комплектующим"><span class="badge-count">${p.rows.length} строк</span></div></div><div class="table-wrap"><table class="table price-table compact-price-table"><thead><tr><th style="width:145px">Категория</th><th>Комплектующее / модель</th><th class="number">Кол-во, шт.</th><th class="number">Цена, ₽ / $</th><th class="number">Сумма, ₽</th><th>Источник</th><th>Действия</th></tr></thead><tbody>${p.rows.map((r, i) => `<tr data-row="${i}"><td>${esc(r.category || '—')}</td><td class="name-cell"><input class="edit long component-name" data-row-field="name" data-index="${i}" value="${esc(r.name)}" aria-label="Наименование комплектующего">${(r.alternatives || []).length ? `<small><select class="edit" data-row-field="alternative" data-index="${i}"><option value="">Другие процессоры (${r.alternatives.length})...</option>${r.alternatives.map((v) => `<option>${esc(v)}</option>`).join('')}</select></small>` : ''}${r.note ? `<small class="row-note" title="${esc(r.note)}">${esc(String(r.note).slice(0, 110))}${String(r.note).length > 110 ? '…' : ''}</small>` : ''}</td><td><input class="edit qty" data-row-field="qty" data-index="${i}" type="number" min="0" step="any" value="${esc(r.qty ?? 1)}"></td><td><input class="edit price component-price" data-row-field="price_input" data-index="${i}" value="${esc(r.price_input || r.price || 0)}" title="Можно вводить $100"></td><td class="number" data-row-sum="${i}" class="row-money">${rub(num(r.qty, 1) * num(r.price))}</td><td><span class="status ${r.source === 'QX' ? 'ok' : 'unknown'}">${esc(r.source || 'Вручную')}</span></td><td><button class="btn danger small" data-action="remove-row" data-index="${i}" title="Удалить строку">✕</button></td></tr>`).join('')}</tbody></table></div>`; }
function verify() {
    const p = currentPlan();
    const checks = p?.checks || [];
    const bad = checks.filter(c => c['Статус'] === 'НЕ ПРОХОДИТ').length;
    return `${pageHead('Заполнение заявки', 'Отредактируйте фактические значения — только затем выгружайте заполненное ТЗ.', `<button class="btn secondary" data-action="refresh-char">↻ Обновить значения</button><button class="btn secondary" data-action="minimums">↓ По минимальным требованиям</button><button class="btn primary" data-action="fill">⇩ Выгрузить заявку DOCX</button>`)}${posChips()}${p ? `<div class="panel"><div class="section-title"><h2>Характеристики для заявки</h2><span class="badge-count">${state.characteristics.length} строк исходного ТЗ</span></div><div class="note">Редактируйте третий столбец. Кнопка «По минимальным требованиям» использует числа из требований, а для строгих «больше»/«меньше» берёт границу ±1. Это не доказательство фактического соответствия: перед подачей сверьте значения с паспортом оборудования. Исходные неизменяемые поля не редактируются.</div><div class="toolbar" style="margin:16px 0"><input class="table-search" placeholder="Найти характеристику…" data-char-search="1"><button class="btn secondary small" data-action="char-filter" data-value="all">Все</button><button class="btn secondary small" data-action="char-filter" data-value="issues">Требуют внимания</button></div><div id="characteristic-list">${state.charRows.length ? characteristicTable() : empty('Заполните характеристики', 'Нажмите «Обновить значения», чтобы получить фактические параметры выбранной сборки.')}</div></div><details class="panel check-details"><summary>Техническая проверка комплектации · ${checks.length} показателей · ${bad} несоответствий</summary>${checksTable(checks)}</details>` : empty('Сначала выполните подбор', 'Загрузите ТЗ и выберите оборудование.')}`;
}
function characteristicTable() { return `<div class="table-wrap"><table class="table application-table"><thead><tr><th>Характеристика</th><th>Требование заказчика</th><th>Значение в заявке (можно изменить)</th><th>Проверка</th></tr></thead><tbody>${state.charRows.filter(ch => state.charFilter !== 'issues' || (ch.status !== 'OK' && ch.status !== 'НЕ ИЗМЕНЯЕТСЯ')).map(ch => `<tr data-char-row="${esc(ch.id)}"><td>${esc(ch.name)}</td><td>${esc(ch.original_value)}</td><td>${ch.editable ? `<input data-characteristic="${esc(ch.id)}" class="edit long" value="${esc(state.overrides[ch.id] ?? ch.value)}">` : `<span class="readonly-value">${esc(ch.value)}</span>`}</td><td><span class="status ${ch.status === 'OK' ? 'ok' : ch.status === 'НЕ СООТВЕТСТВУЕТ' ? 'bad' : 'unknown'}">${esc(ch.status)}</span></td></tr>`).join('')}</tbody></table></div>`; }
function checksTable(checks) { return `<div class="table-wrap"><table class="table"><thead><tr><th>Проверка</th><th>Требование</th><th>Фактическое значение</th><th>Статус</th></tr></thead><tbody>${checks.map(c => `<tr><td>${esc(c['Проверка'])}</td><td>${esc(c['Требование'])}</td><td>${esc(c['Факт QX'])}</td><td><span class="status ${c['Статус'] === 'OK' ? 'ok' : c['Статус'] === 'НЕ ПРОХОДИТ' ? 'bad' : 'unknown'}">${esc(c['Статус'])}</span></td></tr>`).join('')}</tbody></table></div>`; }
function arsenalSummary() {
    const positions = state.plans.map((p, i) => {
        const quantity = Math.max(0, Math.trunc(num(p.req?.quantity)));
        const unit = unitCost(p);
        return { title: p.req?.item_name || p.req?.title || `Позиция ${i + 1}`, quantity, unit, total: quantity * unit };
    });
    const total = positions.reduce((s, p) => s + p.total, 0);
    const equalCount = positions.length > 0 && positions[0].quantity > 0 && positions.every(p => p.quantity === positions[0].quantity);
    return { positions, total, setCount: equalCount ? positions[0].quantity : null, setUnit: equalCount ? positions.reduce((s, p) => s + p.unit, 0) : null };
}
function arsenalBreakdown() {
    const calc = arsenalSummary();
    if (!calc.positions.length)
        return '';
    const price = v => `${fmt(v, 2)} ₽`;
    const completePrices = calc.positions.every(p => p.unit > 0);
    const kit = calc.setCount !== null && calc.positions.length > 1;
    const description = kit
        ? `<strong>${calc.setCount} комплектов по ${calc.positions.length} товара</strong><span>Один комплект содержит по 1 шт. каждой позиции. Себестоимость комплекта: <strong>${price(calc.setUnit)}</strong></span>`
        : calc.positions.length === 1 && calc.setCount !== null
            ? `<strong>${calc.setCount} шт. оборудования</strong><span>За единицу: <strong>${price(calc.setUnit)}</strong></span>`
            : '<strong>Количество товаров различается</strong><span>Стоимость комплекта не выводится: сравните количества по каждой позиции.</span>';
    return `<div class="col-12 panel"><div class="section-title"><h2>Расшифровка себестоимости</h2><strong class="arsenal-cost-total">${price(calc.total)}</strong></div><div class="arsenal-kit-info">${description}</div>${completePrices ? '' : '<div class="warning">⚠ У одной или нескольких позиций нулевая себестоимость. Убедитесь, что прайс заполнен, прежде чем отправлять расчёт.</div>'}<div class="table-wrap"><table class="table arsenal-cost-table"><thead><tr><th>Оборудование</th><th>Количество, шт.</th><th>Себестоимость 1 шт.</th><th>Всего</th></tr></thead><tbody>${calc.positions.map(p => `<tr><td>${esc(p.title)}</td><td>${fmt(p.quantity)}</td><td>${price(p.unit)}</td><td><strong>${price(p.total)}</strong></td></tr>`).join('')}</tbody><tfoot><tr><td colspan="3"><strong>Итого по всем позициям</strong></td><td><strong>${price(calc.total)}</strong></td></tr></tfoot></table></div><p class="subtitle">Доставка, банковская гарантия и гарантийные обязательства считаются отдельно. Проценты точек выхода применяются к закупке оборудования.</p></div>`;
}
function arsenal() {
    const f = state.arsenalFields;
    return `${pageHead('Арсенал', 'Проверка себестоимости по всем позициям, расчёт точки выхода и текст для передачи.', `<button class="btn primary" data-action="make-arsenal">⚡ Сформировать</button>`)}<div class="grid">${arsenalBreakdown()}<div class="col-5 panel"><div class="section-title"><h2>Параметры передачи</h2></div><div class="form-grid two">${[['sender', 'От кого'], ['country', 'Страна'], ['trademark', 'Товарный знак'], ['os', 'Название ОС'], ['delivery', 'Доставка, ₽'], ['bg', 'БГ, ₽'], ['go', 'ГО, ₽']].map(([k, l]) => field(l, `<input data-arsenal="${k}" ${['delivery', 'bg', 'go'].includes(k) ? 'type="number" min="0"' : ''} value="${esc(f[k] ?? '')}">`)).join('')}</div><div class="note" style="margin-top:20px">Используется реестровая запись готового изделия, а не номер процессора или материнской платы.</div></div><div class="col-7 panel"><div class="section-title"><h2>Результат для Арсенала</h2><button class="btn small secondary" data-action="copy-arsenal">▣ Копировать</button></div>${state.arsenalText ? `<div class="readonly">${esc(state.arsenalText)}</div>` : empty('Текст не сформирован', 'Поля необязательны: пустые значения берутся из настроек. Нажмите «Сформировать».')}</div></div>`;
}
function docs() { return `${pageHead('Документы и экспорт', 'Официальные шаблоны, расчёт в Excel, коммерческое предложение и заполненное ТЗ.')}<div class="grid"><div class="col-4 panel"><div class="activity-icon" style="margin-bottom:18px">↧</div><h2>Excel — расчёт</h2><p class="subtitle">Выгрузка спецификации, себестоимости, характеристик и проверок выбранной позиции.</p><div style="height:17px"></div><button class="btn primary" data-action="excel" ${!currentPlan() ? 'disabled' : ''}>⇩ Скачать XLSX</button></div><div class="col-4 panel"><div class="activity-icon" style="margin-bottom:18px">▤</div><h2>Коммерческое предложение</h2><p class="subtitle">Фирменный Word-шаблон QX. Рассчитывается по всем позициям проекта.</p><div class="form-grid two" style="margin-top:15px">${field('Наценка / маржа, %', '<input data-doc="percent" type="number" min="0" max="99" value="20">')}${field('Вид расчёта', '<select data-doc="mode"><option value="markup">Наценка</option><option value="margin">Маржа</option></select>')}${field('Гарантия, мес.', '<input data-doc="warranty" type="number" value="12">')}${field('Действует, дней', '<input data-doc="validity" type="number" value="30">')}</div><div style="height:17px"></div><button class="btn primary" data-action="offer" ${!state.plans.length ? 'disabled' : ''}>⇩ Скачать КП DOCX</button></div><div class="col-4 panel"><div class="activity-icon" style="margin-bottom:18px">✓</div><h2>Заполненная заявка</h2><p class="subtitle">Исходная Word-таблица ТЗ с конкретными характеристиками. Неизменяемые поля сохраняются.</p><div class="note" style="margin:15px 0">${state.source_docx_base64 ? 'Исходный DOCX сохранён в проекте' : 'Сначала загрузите исходный DOCX'}</div><button class="btn primary" data-action="fill" ${!state.source_docx_base64 ? 'disabled' : ''}>⇩ Заполнить DOCX</button></div><div class="col-12 panel"><div class="section-title"><h2>Проект и резервные копии</h2></div><div class="toolbar"><button class="btn" data-action="project-save">⇩ Сохранить проект .qxproj</button><button class="btn secondary" data-action="project-load">▣ Открыть .qxproj</button><button class="btn secondary" data-action="restore">↻ Восстановить автосохранение</button><button class="btn secondary" data-action="catalog-export">⇩ Экспорт базы .qxdb</button></div><div class="subtitle">Форматы проекта и пользовательской базы совместимы с классическим QX 2.9.5.</div></div></div>`; }
function catalog() { const kinds = [['equipment_profile', 'Производители / платформы'], ['case', 'Корпуса'], ['aio', 'Моноблоки'], ['monitor', 'Мониторы'], ['keyboard', 'Клавиатуры'], ['mouse', 'Мыши']]; const items = (state.catalogs[state.catalogKind] || []).filter((x) => !state.catalogSearch || String(x.name).toLowerCase().includes(state.catalogSearch.toLowerCase())); return `${pageHead('Каталоги оборудования', 'Собственные базы, реестровые номера и характеристики. Рабочая база QX не подменяется.', `<button class="btn secondary" data-action="supplier-import">↥ Прайс поставщика XLSX</button><button class="btn secondary" data-action="catalog-import">↥ Импорт .qxdb</button><button class="btn secondary" data-action="catalog-export">⇩ Экспорт .qxdb</button><button class="btn primary" data-action="add-catalog">＋ Добавить запись</button>`)}<div class="panel"><div class="stage-tabs">${kinds.map(([key, label]) => `<button class="stage-tab ${key === state.catalogKind ? 'active' : ''}" data-action="kind" data-kind="${key}">${label}</button>`).join('')}</div><div class="flex between wrap" style="margin-bottom:18px"><h2>${kinds.find(x => x[0] === state.catalogKind)?.[1]} <span class="badge-count">${items.length}</span></h2>${field('Поиск', `<input placeholder="Название модели..." data-field="catalogSearch" value="${esc(state.catalogSearch)}">`)}</div><div class="table-wrap"><table class="table"><thead><tr><th>Наименование</th><th>Производитель / тип</th><th>Изменено</th><th>Действия</th></tr></thead><tbody>${items.map((x, i) => `<tr><td><strong>${esc(x.name)}</strong></td><td>${esc(x.data?.manufacturer || x.data?.product_type || state.catalogKind)}</td><td>${esc(x.updated_at || '—')}</td><td><button class="btn secondary small" data-action="edit-catalog" data-name="${esc(x.name)}">Изменить</button> <button class="btn danger small" data-action="delete-catalog" data-name="${esc(x.name)}">Удалить</button></td></tr>`).join('')}</tbody></table></div>${items.length ? '' : empty('Записи не найдены', 'Создайте новую модель, импортируйте базу или смените категорию.')}</div><div class="note" style="margin-top:15px">Карточки содержат исходные поля технических характеристик. При редактировании JSON сохраняется полная структура записи — это важно для сложных профилей производителей с условиями установки компонентов.</div>`; }
function prices() { const list = Object.entries(state.prices); return `${pageHead('Прайс QX', 'Редактируйте стандартные цены. Неизвестная стоимость процессора никогда не выдумывается.', `<button class="btn primary" data-action="save-prices">✓ Сохранить прайс</button>`)}<div class="panel"><div class="section-title"><h2>Стандартные компоненты</h2><span class="badge-count">${list.length} позиций</span></div>${list.map(([k, v]) => `<div class="price-row"><strong>${esc(v.name || k)}</strong><span class="muted mini mono">${esc(k)}</span><input data-price-key="${esc(k)}" type="number" step="0.01" min="0" value="${esc(v.price || 0)}" aria-label="Цена"></div>`).join('')}</div>`; }
function legacyImportPanel() {
    const p = state.legacyPreview;
    if (!p)
        return '<div class="subtitle">Импорт не начат. Можно сначала сохранить текущий прайс и проект на диск.</div>';
    return `<div class="note" style="margin-top:12px"><strong>Что найдено в старой версии:</strong><div>Прайс: ${p.prices?.found ? String(p.prices.positions) + ' позиций, отличаются ' + (p.prices.changed === null ? 'неизвестно' : String(p.prices.changed)) : 'не найден'}</div><div>Настройки: ${p.settings?.found ? String(p.settings.parameters) + ' параметров, отличаются ' + (p.settings.changed === null ? 'неизвестно' : String(p.settings.changed)) : 'не найдены'}</div><div class="subtitle">${esc(p.warning || '')}</div><div class="toolbar" style="margin-top:12px"><button class="btn primary" data-action="legacy-import-apply">Подтвердить перенос</button><button class="btn secondary" data-action="legacy-import-cancel">Отмена</button></div></div>`;
}
function diagnosticsPanel() {
    const d = state.diagnostics;
    const a = state.attachmentAudit;
    if (!d)
        return `<div class="subtitle">Нажмите «Проверить систему»: QX локально проверит пользовательскую папку, базу закупок, наличие вложений, свободное место и AI. Данные контрактов никуда не отправляются.</div>`;
    const sign = { ok: '✓', warning: '!', error: '✕' };
    return `<div class="subtitle" style="margin-bottom:12px"><strong>QX ${esc(d.version)}</strong> · ${esc(d.os)} · ${d.packaged ? 'Установленная программа' : 'Запуск из исходников'}<div>Папка данных: <code>${esc(d.data_directory)}</code></div></div>` +
        (d.checks || []).map(c => `<div class="price-row"><strong>${esc(sign[c.status] || '?')} ${esc(c.name)}</strong><span class="muted mini">${esc(c.detail)}</span></div>`).join('') +
        `<p class="subtitle">${esc(d.privacy || '')}</p>` +
        (a ? `<div class="note" style="margin-top:12px" id="qx-attachment-audit"><strong>Полная проверка документов: ${a.status === 'ok' ? '✓ Всё в порядке' : '✕ Обнаружены повреждения'}</strong><div>Связей с закупками: ${a.linked}; уникальных вложений: ${a.unique}; проверено успешно: ${a.valid}.</div><div>Отсутствуют: ${a.missing}; изменены: ${a.modified}; недопустимые пути: ${a.unsafe}; превышен размер: ${a.oversized}; ошибка чтения: ${a.unreadable}.</div><p class="subtitle">${esc(a.note)}</p></div>` : '');
}
function settings() { return `${pageHead('Настройки', 'Управление темой, курсом валют и параметрами расчёта.', `<button class="btn primary" data-action="save-settings">✓ Сохранить настройки</button>`)}<div class="grid"><div class="col-6 panel"><div class="section-title"><h2>Внешний вид</h2></div><div class="stage-tabs"><button data-action="theme" data-theme="dark" class="stage-tab ${state.theme === 'dark' ? 'active' : ''}">☾ Тёмная тема</button><button data-action="theme" data-theme="light" class="stage-tab ${state.theme === 'light' ? 'active' : ''}">☀ Светлая тема</button></div><div class="subtitle">Переключение моментальное, без перезагрузки расчёта и потери таблиц.</div><div class="field" style="margin-top:18px"><label>Ширина бокового меню: ${state.settings.sidebar_width || 320} px</label><input data-setting="sidebar_width" type="range" min="260" max="460" step="10" value="${esc(state.settings.sidebar_width || 320)}"></div><div class="separator"></div><div class="section-title"><h2>Курс USD</h2></div><div class="form-grid two">${field('Курс ЦБ, ₽', `<input disabled value="${fmt(state.rate.rate, 4)}">`)}${field('Запас поверх курса, ₽', `<input data-setting="usd_buffer_rub" type="number" step="0.01" value="${esc(state.settings.usd_buffer_rub ?? 5)}">`)}</div><div class="subtitle">Стоимость USD = сумма в долларах × (курс ЦБ + запас).</div><button class="btn secondary" style="margin-top:15px" data-action="rate">↻ Обновить из ЦБ</button><div style="margin-top:16px"><label class="field"><input type="checkbox" data-setting="offline_mode" ${state.settings.offline_mode ? 'checked' : ''}> Работать без обращения к сайту ЦБ</label><p class="subtitle">При включении используется сохранённый курс USD, без сетевых запросов. Нажмите «Сохранить настройки». Перед расчётом проверьте актуальность курса.</p></div></div><div class="col-6 panel"><div class="section-title"><h2>Параметры по умолчанию</h2></div><div class="form-grid two">${[['default_delivery', 'Доставка, ₽'], ['default_bg', 'БГ, ₽'], ['default_go', 'ГО, ₽'], ['default_sender', 'От кого в Арсенале'], ['default_country', 'Страна'], ['default_trademark', 'Товарный знак']].map(([k, l]) => field(l, `<input data-setting="${k}" value="${esc(state.settings[k] ?? '')}">`)).join('')}</div></div><div class="col-12 panel"><div class="section-title"><h2>Совместимость и безопасность данных</h2></div><p class="subtitle">Расчётный движок: QX 2.9.5 · Интерфейс: TypeScript · локальный сервер: 127.0.0.1 · отдельное Windows-окно при наличии Edge/Chrome.</p><div class="toolbar" style="margin-top:18px"><button class="btn secondary" data-action="project-save">Сохранить текущий проект</button><button class="btn secondary" data-action="catalog-export">Скачать пользовательскую базу</button><button class="btn secondary" data-action="classic-info">Классический интерфейс</button></div></div><div class="col-12 panel" id="qx-legacy-panel"><div class="section-title"><h2>Переход с QX 3.3.7</h2><button class="btn secondary small" data-action="legacy-import-choose">Импортировать из ZIP</button></div><p class="subtitle">Выберите ZIP-архив своей старой папки QX со скорректированными файлами data/qx_prices.json и data/settings.json. Сначала увидите предварительный просмотр, затем подтвердите перенос. Перед заменой QX сохранит копию текущего прайса и настроек. Каталоги и контракты не затрагиваются.</p>${legacyImportPanel()}</div><div class="col-12 panel" id="qx-diag-panel"><div class="section-title"><h2>Диагностика и версия QX</h2><div class="toolbar"><button class="btn secondary small" data-action="diagnostics-run">Проверить систему</button><button class="btn secondary small" data-action="audit-attachments">Проверить все документы (SHA-256)</button><button class="btn secondary small" data-action="repair-attachments-choose">Восстановить повреждённые из ZIP</button></div></div>${diagnosticsPanel()}</div></div>`; }
function catalogEditorFields(kind) {
    if (kind === 'monitor')
        return [['inches', 'Диагональ, дюймы', 'number'], ['resolution', 'Разрешение'], ['matrix', 'Матрица'], ['refresh_hz', 'Частота, Гц', 'number'], ['brightness', 'Яркость, кд/м²', 'number'], ['hdmi_ports', 'HDMI, шт.', 'number'], ['dp_ports', 'DisplayPort, шт.', 'number'], ['speakers', 'Динамики', 'bool'], ['wall_mount', 'Крепление VESA', 'bool'], ['pivot', 'Портретный поворот', 'bool'], ['tilt', 'Регулировка наклона', 'bool'], ['touch', 'Сенсорный экран', 'bool']];
    if (kind === 'keyboard')
        return [['wired', 'Проводная', 'bool'], ['wireless', 'Беспроводная', 'bool'], ['usb', 'USB', 'bool'], ['layout', 'Раскладка'], ['backlight', 'Подсветка', 'bool'], ['water_protection', 'Защита от влаги', 'bool']];
    if (kind === 'mouse')
        return [['wired', 'Проводная', 'bool'], ['wireless', 'Беспроводная', 'bool'], ['usb', 'USB', 'bool'], ['optical', 'Оптическая', 'bool'], ['dpi', 'Разрешение, DPI', 'number'], ['cable_m', 'Длина кабеля, м', 'number'], ['side_buttons', 'Боковые кнопки', 'bool'], ['silent_click', 'Тихие кнопки', 'bool']];
    if (kind === 'aio')
        return [['custom_aio_diagonal_in', 'Диагональ, дюймы', 'number'], ['custom_aio_resolution', 'Разрешение'], ['custom_aio_refresh_hz', 'Частота, Гц', 'number'], ['custom_aio_matrix', 'Матрица'], ['custom_aio_integrated_psu', 'Блок питания встроен', 'bool'], ['custom_aio_psu_w', 'Мощность БП, Вт', 'number'], ['custom_aio_built_in_cardreader', 'Встроенный картридер', 'bool'], ['custom_aio_usb2_a', 'USB 2.0, шт.', 'number'], ['custom_aio_gen1_a', 'USB 3.2 Gen1 Type-A, шт.', 'number'], ['custom_aio_gen1_c', 'USB 3.2 Gen1 Type-C, шт.', 'number']];
    if (kind === 'equipment_profile')
        return [['manufacturer', 'Производитель'], ['final_product_name', 'Наименование готового изделия'], ['final_registry_number', 'Реестровый номер готового изделия']];
    return [['custom_case_width_mm', 'Ширина, мм', 'number'], ['custom_case_length_mm', 'Длина, мм', 'number'], ['custom_case_height_mm', 'Высота, мм', 'number'], ['custom_case_protected', 'Защищённый корпус', 'bool'], ['custom_case_bay_525', 'Отсеки 5,25″', 'number'], ['custom_case_bay_25', 'Отсеки 2,5″', 'number'], ['custom_case_bay_35', 'Отсеки 3,5″', 'number'], ['custom_case_usb2_front', 'USB 2.0 спереди', 'number'], ['custom_case_gen1_a_front', 'USB 3.2 Gen1 Type-A спереди', 'number'], ['custom_case_gen1_c_front', 'USB 3.2 Gen1 Type-C спереди', 'number']];
}
function previewTable(table, index) {
    const headers = table.headers || [];
    const rows = table.rows || [];
    return `<section class="doc-preview-section" data-source-section><div class="doc-preview-section-head"><h3>${esc(table.title || `Таблица ${index + 1}`)}</h3><span>${rows.length} строк</span></div><div class="doc-preview-scroll"><table class="doc-preview-grid"><thead><tr>${headers.map(h => `<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((row, i) => `<tr data-source-row>${row.map((v, j) => `<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section>`;
}
function sourceModal() {
    const preview = state.sourcePreview;
    return `<div class="modal-backdrop"><div class="modal document-preview-modal" role="dialog" aria-modal="true" aria-label="Просмотр технического задания"><div class="modal-header doc-preview-header"><div class="doc-preview-title"><div class="doc-preview-kicker">ИСХОДНОЕ ТЕХНИЧЕСКОЕ ЗАДАНИЕ</div><h2>📄 ${esc(state.source_filename || 'Техническое задание')}</h2><p>Таблицы из загруженного документа · только просмотр</p></div><button class="btn secondary" data-action="close-modal">✕ Закрыть</button></div>${preview ? `<div class="doc-preview-toolbar"><span>${preview.table_count} таблиц · ${preview.row_count} строк</span><label class="doc-preview-search"><span>⌕</span><input data-source-filter placeholder="Найти характеристику или значение…" autocomplete="off" aria-label="Поиск по таблицам ТЗ"></label><span data-source-count></span></div><div class="doc-preview-content">${preview.tables.map(previewTable).join('') || '<div class="doc-preview-empty">В документе нет таблиц.</div>'}${preview.paragraphs?.length ? `<details class="doc-preview-paragraphs"><summary>Текст документа вне таблиц (${preview.paragraphs.length} абзацев)</summary><div>${preview.paragraphs.map(p => `<p>${esc(p)}</p>`).join('')}</div></details>` : ''}</div>` : '<div class="doc-preview-loading">Загружаю таблицы документа…</div>'}</div></div>`;
}
function modal() {
    if (state.modal === 'unsaved-project') {
        return `<div class="modal-backdrop"><div class="modal qx-restore-modal" role="dialog" aria-modal="true" aria-label="Несохранённый расчёт">
          <div class="modal-header"><h2>Расчёт ещё не сохранён</h2><button class="btn secondary" data-action="close-modal">✕</button></div>
          <p>Вы ещё не сохранили текущий расчёт в файл <b>.qxproj</b>${state.projectHasEdits && state.projectSavedManually ? ' после последних изменений' : ''}.</p>
          <div class="note">Автосохранение не заменяет отдельную копию проекта. При создании нового расчёта текущая работа будет заменена.</div>
          <div class="toolbar" style="justify-content:flex-end;margin-top:18px"><button class="btn secondary" data-action="close-modal">Отмена</button>
          <button class="btn secondary" data-action="new-discard">Создать без сохранения</button>
          <button class="btn primary" data-action="new-save-first">Сохранить .qxproj и создать</button></div></div></div>`;
    }
    if (state.modal === 'tender-delete') {
        const t = state.tenders.deleteCandidate;
        if (!t)
            return '';
        const label = t.number || t.title || 'Без номера';
        return `<div class="modal-backdrop"><div class="modal qx-restore-modal" role="dialog" aria-modal="true" aria-label="Подтверждение удаления закупки"><div class="modal-header"><h2>Удалить закупку?</h2><button class="btn secondary" data-action="close-modal">✕ Отмена</button></div><p>Вы собираетесь удалить <b>${esc(label)}</b>${t.number && t.title ? ` — ${esc(t.title)}` : ''}.</p><div class="note" style="margin:16px 0">Карточка, её комментарии, этапы поставки, история и прикреплённые документы будут удалены без возможности отмены. Сохранённые отдельно проекты QX и базы оборудования не затронутся.</div><p class="subtitle">Если эти данные могут понадобиться, сначала закройте окно и сохраните резервную копию реестра закупок.</p><div class="toolbar" style="margin-top:22px;justify-content:flex-end"><button class="btn secondary" data-action="close-modal">Отмена</button><button class="btn qx-delete-tender" data-action="tender-delete-confirm" data-id="${esc(t.id)}">Удалить безвозвратно</button></div></div></div>`;
    }
    if (state.modal === 'source')
        return sourceModal();
    if (state.modal === 'tender-restore') {
        const p = state.tenderRestorePreview || {};
        return `<div class="modal-backdrop"><div class="modal qx-restore-modal" role="dialog" aria-modal="true"><div class="modal-header"><h2>Восстановление тендерного отдела</h2><button class="btn secondary" data-action="close-modal">Закрыть</button></div><p class="subtitle">Архив прошёл проверку целостности. Восстановление <b>заменит текущие закупки</b>, но сначала QX сохранит их защитную копию.</p><div class="tender-restore-grid"><div><span>Закупок в архиве</span><b>${num(p.tenders)}</b></div><div><span>Организаций</span><b>${num(p.organizations)}</b></div><div><span>Документов</span><b>${num(p.documents)}</b></div></div><div class="note">Версия структуры архива: <b>${num(p.schema_version)}</b>. Совместимость проверена до восстановления.</div><div class="note">Сохранённые проекты и пользовательские базы оборудования не затрагиваются. Для переноса тендеров на другой компьютер используйте этот архив.</div><div class="toolbar" style="margin-top:22px;justify-content:flex-end"><button class="btn secondary" data-action="close-modal">Отмена</button><button class="btn primary" data-action="tender-restore-confirm">Подтвердить замену тендеров</button></div></div></div>`;
    }
    if (state.modal === 'tender-repair') {
        const p = state.tenderRepairPreview || {};
        return `<div class="modal-backdrop"><div class="modal qx-restore-modal" role="dialog" aria-modal="true" aria-label="Восстановление только документов"><div class="modal-header"><h2>Восстановление повреждённых документов</h2><button class="btn secondary" data-action="close-modal">Закрыть</button></div><p class="subtitle">QX проверил ZIP и SHA-256. При подтверждении будут возвращены <b>только отсутствующие или повреждённые документы</b>. Закупки, цены, новые комментарии и расчёты останутся без изменений.</p><div class="tender-restore-grid"><div><span>Можно восстановить</span><b>${num(p.repairable)}</b></div><div><span>Уже целые</span><b>${num(p.intact)}</b></div><div><span>Отсутствуют в этой копии</span><b>${num(p.not_in_backup)}</b></div></div>${p.unsafe ? `<div class="warning">Вложений с небезопасными путями: ${num(p.unsafe)}. Они не будут изменены.</div>` : ''}<div class="note">Повреждённые оригиналы будут сохранены в локальной папке резервных снимков. Путь к документам и содержимое файлов не передаются в интернет. Для полного отката закупок используйте отдельную функцию восстановления базы.</div><div class="toolbar" style="margin-top:22px;justify-content:flex-end"><button class="btn secondary" data-action="close-modal">Отмена</button><button class="btn primary" data-action="repair-attachments-confirm" ${!p.repairable ? 'disabled' : ''}>Восстановить ${num(p.repairable)} документов</button></div></div></div>`;
    }
    if (state.modal === 'catalog') {
        const item = state.draftCatalog || { name: '', data: {} };
        const d = item.data || {};
        const common = [['registry_number', 'Реестровый номер'], ['supplier', 'Поставщик'], ['supplier_sku', 'Артикул / P/N']];
        const fields = state.catalogKind === 'equipment_profile' ? catalogEditorFields(state.catalogKind) : state.catalogKind === 'case' ? [['custom_case_supplier', 'Поставщик'], ['custom_case_supplier_sku', 'Артикул / P/N'], ...catalogEditorFields(state.catalogKind)] : state.catalogKind === 'aio' ? [['custom_aio_supplier', 'Поставщик'], ['custom_aio_supplier_sku', 'Артикул / P/N'], ...catalogEditorFields(state.catalogKind)] : [...common, ...catalogEditorFields(state.catalogKind)];
        const priceInput = state.catalogKind === 'case' ? (d.custom_case_price_input || (d.custom_case_price ? String(d.custom_case_price) : '')) : state.catalogKind === 'aio' ? (d.custom_aio_price_input || (d.custom_aio_price ? String(d.custom_aio_price) : '')) : (d.price_input || (d.price ? String(d.price) : ''));
        const form = fields.map(([key, title, kind]) => field(title, kind === 'bool' ? `<select data-catalog-value="${key}" data-catalog-type="bool"><option value="false" ${!d[key] ? 'selected' : ''}>Нет</option><option value="true" ${d[key] ? 'selected' : ''}>Да</option></select>` : `<input data-catalog-value="${key}" data-catalog-type="${kind || 'text'}" type="${kind === 'number' ? 'number' : 'text'}" ${kind === 'number' ? 'min="0" step="any"' : ''} value="${esc(d[key] ?? '')}">`)).join('');
        return `<div class="modal-backdrop"><div class="modal catalog-modal"><div class="modal-header"><div><h2>${item.name ? 'Редактирование оборудования' : 'Новое оборудование'}</h2><p class="subtitle">${esc(state.catalogKind === 'equipment_profile' ? 'Профиль производителя' : state.catalogKind)}</p></div><button class="btn ghost" data-action="close-modal">✕</button></div>
   <div class="form-grid two">${field('Название / модель', `<input data-modal-name value="${esc(item.name)}" placeholder="Например, Бештау А520">`)}${state.catalogKind === 'equipment_profile' ? '' : field('Цена, ₽ или $', `<input data-modal-price-input value="${esc(priceInput)}" placeholder="5000 или $45">`)}</div>
   <div class="section-title" style="margin-top:22px"><h2>Характеристики и реквизиты</h2></div><div class="form-grid two">${form}</div>
   <details class="advanced-json" ${state.catalogKind === 'equipment_profile' ? 'open' : ''}><summary>Расширенные параметры и техническая структура JSON</summary><p class="hint">Сохранение оставит все незатронутые параметры. Для сложных плат Intel/AMD, дополнительных USB-модулей и условий установки редактируйте структуру здесь. Значения простых полей выше имеют приоритет.</p><textarea data-modal-json rows="10">${esc(JSON.stringify(d, null, 2))}</textarea></details>
   <div class="toolbar" style="justify-content:flex-end;margin-top:20px"><button class="btn secondary" data-action="close-modal">Отмена</button><button class="btn primary" data-action="save-catalog">✓ Сохранить в базу</button></div></div></div>`;
    }
    return `<div class="modal-backdrop"><div class="modal"><div class="modal-header"><h2>Классическая версия QX</h2><button class="btn ghost" data-action="close-modal">✕</button></div><p class="subtitle">Полная классическая версия QX 2.9.5 находится в этом же архиве. Запустите START_QX.bat для работы с функциями, которые ещё не перенесены в Modern.</p><button class="btn primary" data-action="close-modal">Понятно</button></div></div>`;
}
function render(resetScroll = false) {
    const keepFull = state.full && !!currentPlan();
    const overlayY = $('#fullscreen-area .table-wrap')?.scrollTop || 0;
    $('#fullscreen-area')?.remove();
    state.full = false;
    const oldScroll = window.scrollY;
    document.documentElement.classList.toggle('light', state.theme === 'light');
    const container = $('#app');
    if (container)
        container.innerHTML = shell();
    bindDrop();
    if (keepFull) {
        state.full = true;
        toggleFull();
    }
    // Preserve the place when editing; switch tabs resets the scroll.
    requestAnimationFrame(() => {
        window.scrollTo({ top: resetScroll ? 0 : oldScroll, behavior: 'instant' });
        const overlay = $('#fullscreen-area');
        if (overlay)
            overlay.querySelector('.table-wrap')?.scrollTo(0, overlayY);
    });
}
function bindDrop() {
    const drop = $('#drop');
    if (!drop)
        return;
    for (const name of ['dragenter', 'dragover'])
        drop.addEventListener(name, e => { e.preventDefault(); drop.classList.add('drag'); });
    for (const name of ['dragleave', 'drop'])
        drop.addEventListener(name, e => { e.preventDefault(); drop.classList.remove('drag'); });
    drop.addEventListener('drop', (e) => { e.preventDefault(); const files = Array.from(e.dataTransfer?.files || []); if (files.length)
        uploadTzFiles(files); });
}
function bridgeApi() { return window.pywebview?.api; }
async function openNativeFile(kind) {
    const bridge = bridgeApi();
    if (!bridge?.choose_file) {
        const ids = { tz: '#file-tz', project: '#file-project', catalog: '#file-catalog', supplier: '#file-supplier', tender: '#file-tender', tender_package: '#file-tender-package', tender_backup: '#file-tender-backup', tender_project: '#file-tender-project', tender_repair: '#file-tender-repair', legacy: '#file-legacy' };
        const input = $(ids[kind]);
        if (!input) {
            toast('Поле выбора файла не найдено', true);
            return null;
        }
        input.click();
        return null;
    }
    try {
        const result = await bridge.choose_file(kind);
        if (!result || result.cancelled)
            return null;
        const decoded = atob(result.base64 || '');
        const bytes = new Uint8Array(decoded.length);
        for (let i = 0; i < decoded.length; i++)
            bytes[i] = decoded.charCodeAt(i);
        return new File([bytes], result.name || 'document.docx');
    }
    catch (e) {
        toast('Системный диалог недоступен, пробуем выбор в браузере: ' + e.message, true);
        const ids = { tz: '#file-tz', project: '#file-project', catalog: '#file-catalog', supplier: '#file-supplier', tender: '#file-tender', tender_package: '#file-tender-package', tender_backup: '#file-tender-backup', tender_project: '#file-tender-project', tender_repair: '#file-tender-repair', legacy: '#file-legacy' };
        $(ids[kind])?.click();
        return null;
    }
}
async function chooseAndUpload(kind) {
    if (kind === 'tz') {
        $('#file-tz')?.click();
        return;
    }
    const f = await openNativeFile(kind);
    if (!f)
        return;
    if (kind === 'tz')
        await uploadTz(f);
    else if (kind === 'project')
        await loadProjectFile(f);
    else if (kind === 'catalog')
        await loadCatalogFile(f);
    else
        await loadSupplierFile(f);
}
async function previewLegacyZip(file) {
    if (file.size > 60 * 1024 * 1024) {
        toast('Архив превышает 60 МБ', true);
        return;
    }
    state.legacyPreview = null;
    state.legacyZip = null;
    render();
    await busy(async () => {
        const preview = await api('legacy/preview', file);
        state.legacyZip = file;
        state.legacyPreview = preview;
        state.tab = 'settings';
        render();
        toast('Проверка архива завершена. Просмотрите состав перед импортом.');
    });
}
async function applyLegacyZip() {
    if (!state.legacyZip || !state.legacyPreview) {
        toast('Сначала выберите архив', true);
        return;
    }
    if (!window.confirm('ЗАМЕНИТЬ текущие прайс и настройки данными из старой версии? QX сохранит резервную копию. Каталог, проекты и тендеры не изменятся.'))
        return;
    await busy(async () => {
        const response = await api('legacy/import', state.legacyZip, 'POST', { 'X-QX-Confirm-Legacy': 'IMPORT_LEGACY_SETTINGS_AND_PRICES' });
        const refreshed = await api('boot');
        state.prices = refreshed.prices || {};
        state.settings = refreshed.settings || {};
        state.legacyZip = null;
        state.legacyPreview = null;
        state.theme = state.settings.ui_theme || 'dark';
        render();
        toast('Перенесены данные старого QX. Копия прежних файлов сохранена.');
    });
}
async function loadProjectFile(file) { await busy(async () => { const obj = await api('project/load', file); importProject(obj); toast('Проект загружен: ' + state.name); }); }
async function loadCatalogFile(file) { await busy(async () => { const result = await api('catalog-import', file); await refreshCatalog(); render(); toast('База импортирована: ' + result.imported); }); }
async function loadSupplierFile(file) { const supplier = window.prompt('Название поставщика', 'ExeGate') || 'ExeGate'; await busy(async () => { const result = await api('supplier-price', file, 'POST', { 'X-Supplier': supplier, 'X-Price-Mode': 'ОПТ' }); toast('Прайс ' + supplier + ' импортирован: ' + result.items + ' позиций'); await refreshCatalog(); render(); }); }
async function previewTenderEis(updateCard = false) {
    const number = String(state.tenderNoticeNumber || '').trim();
    if (!/^\d{19,20}$/.test(number)) {
        toast('Для проверки XML нужен номер из 19 или 20 цифр', true);
        return;
    }
    state.tenderEisMessage = 'Проверяем официальный XML ЕИС по номеру ' + number + '…';
    if (!updateCard)
        render();
    try {
        const result = await api('eis/notice/' + encodeURIComponent(number), undefined, 'GET');
        if (String(state.tenderNoticeNumber) !== number)
            return;
        state.tenderEisPreview = result;
        state.tenderEisMessage = result.message || '';
        if (updateCard && result.available && result.notice && state.tenderId) {
            const old = await api('tenders/' + encodeURIComponent(state.tenderId), undefined, 'GET');
            const t = old.tender || {};
            if (t.number === number) {
                const fields = {};
                for (const key of ['customer', 'law', 'application_due_on', 'application_due_time', 'nmck']) {
                    if (!t[key] && result.notice[key])
                        fields[key] = result.notice[key];
                }
                if ((!t.title || t.title === state.name || t.title === 'Закупка без номера') && result.notice.title)
                    fields.title = result.notice.title;
                if (Object.keys(fields).length)
                    await api('tenders/' + encodeURIComponent(state.tenderId), fields, 'PATCH');
                await loadTenders();
            }
        }
    }
    catch (e) {
        state.tenderEisPreview = null;
        state.tenderEisMessage = 'ЕИС недоступна: ' + e.message + '. Заполните карточку вручную.';
    }
    render();
}
async function uploadTzFiles(files, targetTenderId = '') {
    if (!files?.length)
        return;
    if (state.tenderLinkEnabled && !/^(?:\d{11}|\d{19,20})$/.test(String(state.tenderNoticeNumber || '').trim())) {
        toast('Для добавления в реестр укажите номер закупки ЕИС (11, 19 или 20 цифр) либо отключите галочку', true);
        return;
    }
    const accepted = ['.docx', '.pdf', '.xlsx', '.xlsm', '.odt', '.txt', '.csv', '.md'];
    if (state.tzDocuments.length + files.length > 12) {
        toast('В одном проекте допускается до 12 файлов ТЗ', true);
        return;
    }
    const batch = files.filter(f => accepted.some(ext => f.name.toLowerCase().endsWith(ext)) && f.size <= 30 * 1024 * 1024);
    if (batch.length !== files.length) {
        toast('Часть файлов отклонена: поддерживаются DOCX/PDF/XLSX/ODT/TXT/CSV/MD до 30 МБ', true);
        return;
    }
    const usedBytes = state.tzDocuments.reduce((s, d) => s + num(d.byteSize), 0);
    if (usedBytes + batch.reduce((s, f) => s + f.size, 0) > 75 * 1024 * 1024) {
        toast('Превышено ограничение 75 МБ исходных ТЗ на проект', true);
        return;
    }
    await busy(async () => {
        const parsed = [];
        const errors = [];
        // Parse first; do not change existing requirements if a file is malformed.
        for (const file of batch) {
            try {
                const result = await api('parse', file, 'POST', { 'X-File-Name': encodeURIComponent(file.name) });
                parsed.push({ file, result });
            }
            catch (e) {
                errors.push(file.name + ': ' + e.message);
            }
        }
        if (!parsed.length) {
            toast('Не удалось прочитать файлы: ' + errors.join('; '), true);
            return;
        }
        if (state.reqs.length === 1 && !state.tzDocuments.length && !state.plans.length && !state.reqs[0]._qx_doc_id && state.name === 'Новый расчёт') {
            state.reqs = [];
        }
        if (!state.reqs.length) {
            state.tenderProjectKey = (globalThis.crypto?.randomUUID?.() || 'qx-' + Date.now());
            state.tenderId = '';
            state.name = parsed[0].file.name.replace(/\.[^.]+$/, '');
        }
        if (targetTenderId) state.tenderId = targetTenderId;
        storeCurrentDoc();
        const firstNew = state.reqs.length;
        for (const { file, result } of parsed) {
            const id = 'tz-' + (globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + '-' + Math.random().toString(36).slice(2));
            state.tzDocuments.push({ id, name: file.name, text: result.source_text || '', docx: result.source_docx_base64 || '', characteristics: result.characteristics || [], complexity: result.complexity || null, overrides: {}, byteSize: file.size });
            for (const r of result.reqs || []) {
                state.reqs.push({ ...r, _qx_doc_id: id });
            }
        }
        state.charRows = [];
        state.tzAiResults = {};
        state.pos = firstNew;
        state.activeTzDocId = '';
        chooseDocForPosition(state.pos);
        state.tab = 'tz';
        render(true);
        scheduleSave();
        toast(`Добавлено ТЗ: ${parsed.length}, новых позиций: ${state.reqs.length - firstNew}`);
        if (errors.length)
            toast('Ошибки: ' + errors.join('; '), true);
        try {
            await syncTenderProject();
            if (state.tenderId) {
                for (const { file } of parsed) {
                    try {
                        await api('tenders/' + state.tenderId + '/documents', file, 'POST', { 'X-File-Name': encodeURIComponent(file.name) });
                    }
                    catch (e) {
                        toast('Не удалось сохранить вложение ' + file.name + ': ' + e.message, true);
                    }
                }
            }
        }
        catch (e) {
            toast('Синхронизация карточки закупки: ' + e.message, true);
        }
        if (state.tenderLinkEnabled && state.tenderId)
            void previewTenderEis(true);
        if (state.tzAiAuto && state.tzAiModel)
            void runTzAiBatch(firstNew, state.reqs.length);
    });
}
async function uploadTz(file) { return uploadTzFiles([file]); }
async function testLiteInference() {
    state.tzAiMessage = 'Проверяю реальный ответ модели на короткий запрос...';
    render();
    try {
        const d = await api('parse/ai/diagnostic');
        state.tzAiMessage = (d.ok ? '✓ ' : 'Ошибка: ') + (d.detail || 'Нет ответа') + (d.seconds != null ? ' Время: ' + d.seconds + ' с.' : '');
        if (!d.ok)
            toast(state.tzAiMessage, true);
    }
    catch (e) {
        state.tzAiMessage = 'Проверка AI: ' + e.message;
        toast(state.tzAiMessage, true);
    }
    render();
}
async function runTzAiBatch(start = 0, end = state.reqs.length) {
    if (state.tzAiRunning) {
        toast('Анализ уже выполняется', true);
        return;
    }
    const project = state.tenderProjectKey;
    for (let index = start; index < end; index++) {
        if (state.tenderProjectKey !== project)
            break; // user opened another project
        await runTzAi(false, index);
    }
}
async function runTzAi(wrap = true, positionIndex = null) {
    const index = positionIndex === null ? state.pos : positionIndex;
    const req = state.reqs[index];
    const doc = state.tzDocuments.find(d => d.id === req?._qx_doc_id) || activeDocForPosition();
    const model = state.tzAiModel || $('#tz-ai-model')?.value;
    if (!req || !doc) {
        if (positionIndex === null)
            toast('Выберите позицию из загруженного ТЗ', true);
        return;
    }
    if (!model) {
        if (positionIndex === null)
            toast('Сначала выберите установленную локальную нейросеть', true);
        return;
    }
    if (state.tzAiRunning)
        return;
    state.tzAiModel = model;
    state.tzAiRunning = true;
    const started = Date.now();
    const initialMessage = 'AI анализирует позицию ' + (index + 1) + ' из ' + doc.name + '.';
    state.tzAiMessage = initialMessage + ' Выбраны релевантные фрагменты ТЗ.';
    render();
    const progressTimer = setInterval(() => {
        if (!state.tzAiRunning)
            return;
        const seconds = Math.round((Date.now() - started) / 1000);
        state.tzAiMessage = initialMessage + ' Прошло ' + seconds + ' с — ожидается ответ локальной модели.';
        const el = document.querySelector('[role="status"]');
        if (el)
            el.textContent = state.tzAiMessage;
    }, 15000);
    try {
        const result = await api('parse/ai', { source_text: doc.text, req, model });
        if (state.reqs[index] !== req)
            return; // source changed during inference
        let applied = 0;
        if (state.tzAiFill) {
            for (const proposal of result.proposals || []) {
                if (proposal.auto_safe === true && req[proposal.field] === proposal.previous) {
                    req[proposal.field] = proposal.value;
                    applied++;
                }
            }
        }
        result.proposals = (result.proposals || []).filter(p => !(p.auto_safe === true && req[p.field] === p.value));
        state.tzAiResults[index] = result;
        state.tzAiMessage = `Позиция ${index + 1}: заполнено ${applied} пустых полей; на проверку ${(result.proposals || []).length}.`;
        if (applied) {
            state.charRows = [];
            scheduleSave();
            synchronizeTenderSoon();
            // Keep any already-calculated build in sync while preserving manual locks.
            // Do not navigate away from the technical document during analysis.
            if (state.plans.length) {
                try {
                    const built = await api('select', { reqs: state.reqs, prices: state.prices, settings: state.settings, previous: state.plans, hard: false });
                    if (state.reqs[index] === req)
                        state.plans = built.plans || state.plans;
                }
                catch (e) {
                    state.tzAiMessage += ' Автопересчёт недоступен: ' + e.message;
                }
            }
        }
    }
    catch (e) {
        state.tzAiMessage = 'AI, позиция ' + (index + 1) + ': ' + e.message;
        toast(state.tzAiMessage, true);
    }
    finally {
        clearInterval(progressTimer);
        state.tzAiRunning = false;
        render();
    }
}
function applyTzAi() {
    const report = state.tzAiResults[state.pos];
    if (!report)
        return;
    const checked = [...document.querySelectorAll('[data-tz-ai-check]:checked')].map(x => Number(x.dataset.tzAiCheck));
    if (!checked.length) {
        toast('Отметьте исправления для применения', true);
        return;
    }
    let applied = 0;
    for (const i of checked) {
        const p = report.proposals[i];
        if (p && state.reqs[state.pos] && state.reqs[state.pos][p.field] === p.previous) {
            state.reqs[state.pos][p.field] = p.value;
            applied++;
        }
    }
    delete state.tzAiResults[state.pos];
    state.tzAiMessage = `Применено ${applied} изменений. Выполните проверку соответствия и просмотрите расчёт.`;
    state.charRows = [];
    render();
    scheduleSave();
    // Apply only the chosen proposals, then recalculate the normal deterministic engine.
    void selectPlans();
}
async function selectPlans(hard = false) {
    if (!state.reqs.length) {
        toast('Сначала загрузите ТЗ', true);
        return;
    }
    await busy(async () => { const result = await api('select', { reqs: state.reqs, prices: state.prices, settings: state.settings, previous: state.plans, hard }); state.plans = result.plans || []; state.charRows = []; state.tab = 'build'; render(true); scheduleSave(); synchronizeTenderSoon(); toast('Комплектация рассчитана. Проверьте замечания.'); });
}
async function updateRowPrice(index, raw) {
    const p = currentPlan();
    if (!p || !p.rows[index])
        return;
    await busy(async () => {
        const result = await api('price', { value: raw, rate: state.rate.rate, buffer: state.settings.usd_buffer_rub });
        const r = p.rows[index];
        r.price = result.price;
        r.price_input = raw;
        r._locked = true;
        if (result.note)
            r.note = result.note;
        render();
        scheduleSave();
    });
}
function updateTotals() {
    const p = currentPlan();
    if (!p)
        return;
    const update = (s, t) => { document.querySelectorAll(s).forEach(el => { el.textContent = t; }); };
    update('#unit-cost', rub(unitCost(p)));
    update('#total-cost', rub(unitCost(p) * num(p.req.quantity)));
    update('#table-total', 'Итого: ' + rub(unitCost(p)));
    for (let i = 0; i < p.rows.length; i++)
        update(`[data-row-sum="${i}"]`, rub(num(p.rows[i].qty) * num(p.rows[i].price)));
}
async function download(path, body, filename) {
    await busy(async () => {
        const blob = await api(path, body);
        const bridge = bridgeApi();
        if (bridge?.save_file) {
            const bytes = new Uint8Array(await blob.arrayBuffer());
            let raw = '';
            for (let i = 0; i < bytes.length; i += 16384)
                raw += String.fromCharCode(...bytes.subarray(i, i + 16384));
            const result = await bridge.save_file(filename, btoa(raw));
            if (result?.cancelled)
                return false;
            if (result?.name) {
                toast('Сохранено: ' + result.name);
                return true;
            }
            if (!result?.browser_fallback)
                throw new Error('Окно сохранения не вернуло путь к файлу');
            // If native OS dialogs are blocked, let WebView2 perform its
            // ordinary browser download rather than losing the export.
            toast('Системное окно сохранения недоступно. Пробуем загрузку файла.', true);
        }
        const url = URL.createObjectURL(blob), a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        toast('Файл передан менеджеру загрузок: ' + filename);
        return true;
    });
}
async function saveProjectNow() {
    const filename = (state.name || 'QX_проект').replace(/[\\/:*?"<>|]/g, '_') + '.qxproj';
    const saved = await download('project/save', dataPackage(), filename);
    if (saved) { state.projectSavedManually = true; state.projectHasEdits = false; }
    return Boolean(saved);
}
function resetCalculation() {
    state.modal = '';
    state.projectSavedManually = false;
    state.projectHasEdits = false;
    state.tenderProjectKey = (globalThis.crypto?.randomUUID?.() || 'qx-' + Date.now() + '-' + Math.random().toString(36).slice(2));
    state.tenderId = ''; state.tenderLinkEnabled = false; state.tenderNoticeNumber = ''; state.tenderEisPreview = null;
    state.reqs = [emptyReq()]; state.plans = []; state.pos = 0; state.name = 'Новый расчёт';
    state.source_text = ''; state.source_docx_base64 = ''; state.source_filename = '';
    state.tzDocuments = []; state.activeTzDocId = ''; state.tzAiResults = {}; state.tzAiMessage = '';
    state.overrides = {}; state.sourcePreview = null; state.characteristics = []; state.charRows = [];
    state.tab = 'tz'; render(); scheduleSave();
    state.projectHasEdits = false;
}
function importProject(project) {
    state.tenderLinkEnabled = Boolean(project.project_meta?.tender_link_enabled);
    state.tenderNoticeNumber = project.project_meta?.tender_notice_number || '';
    state.tenderEisPreview = null;
    state.tenderProjectKey = project.project_meta?.tender_project_key || (globalThis.crypto?.randomUUID?.() || 'qx-' + Date.now() + '-' + Math.random().toString(36).slice(2));
    state.tenderId = '';
    state.name = project.project_meta?.name || project.name || 'Открытый проект';
    state.reqs = project.reqs || [];
    state.plans = project.plans || [];
    state.prices = { ...state.prices, ...(project.qx_prices || {}) };
    state.settings = { ...state.settings, ...(project.settings_snapshot || {}) };
    state.source_text = project.source_text || '';
    state.source_filename = project.source_filename || '';
    state.source_docx_base64 = project.source_docx_base64 || '';
    state.sourcePreview = null;
    state.characteristics = project.tender_characteristics || [];
    state.overrides = project.tender_overrides || {};
    state.tzDocuments = Array.isArray(project.tz_documents) ? project.tz_documents : [];
    if (!state.tzDocuments.length && state.source_filename) {
        const id = 'legacy-source';
        state.tzDocuments = [{ id, name: state.source_filename, text: state.source_text, docx: state.source_docx_base64, characteristics: state.characteristics, complexity: project.source_complexity || null, overrides: state.overrides, byteSize: 0 }];
        state.reqs.forEach(r => { if (!r._qx_doc_id)
            r._qx_doc_id = id; });
    }
    state.activeTzDocId = '';
    state.tzAiResults = {};
    state.tzAiMessage = '';
    state.charRows = [];
    state.pos = 0;
    chooseDocForPosition(0);
    state.tab = 'build';
    render();
    scheduleSave();
    state.projectSavedManually = true;
    state.projectHasEdits = false;
}
function setField(el) {
    const key = el.dataset.field;
    if (key === 'name') {
        state.name = el.value;
        scheduleSave();
    }
    if (key === 'reqSearch') {
        state.reqSearch = el.value;
        render();
    }
    if (key === 'catalogSearch') {
        state.catalogSearch = el.value;
        render();
    }
}
let recalcSequence = 0;
async function recalcRequirements(hard = false) {
    const serial = ++recalcSequence;
    const previousTab = state.tab;
    try {
        const result = await api('select', { reqs: clone(state.reqs), prices: state.prices, settings: state.settings, previous: state.plans, hard });
        if (serial !== recalcSequence)
            return;
        state.plans = result.plans || [];
        state.charRows = [];
        state.tab = previousTab;
        render();
        scheduleSave();
    }
    catch (err) {
        if (serial === recalcSequence)
            toast('Автопересчёт не выполнен: ' + err.message, true);
    }
}
function synchronizeQuantity(amount) {
    const r = currentReq(), p = currentPlan();
    if (r)
        r.quantity = amount;
    if (p)
        p.req.quantity = amount;
    document.querySelectorAll('.quantity-warning').forEach(node => { node.style.display = amount > 0 ? 'none' : ''; });
    document.querySelectorAll('[data-quantity-hint]').forEach(node => { node.textContent = amount > 0 ? 'Количество изделий в партии' : 'Укажите количество больше нуля'; });
    document.querySelectorAll('.position-chip.active span').forEach(node => { node.textContent = amount + ' шт.'; });
    if (p) {
        updateTotals();
        document.querySelectorAll('[data-build-quantity]').forEach(node => { if (node !== document.activeElement)
            node.value = String(amount); });
    }
    scheduleSave();
}
function onChange(e) {
    const el = e.target;
    if (!el || !('dataset' in el))
        return;
    const reqKey = el.dataset.req;
    if (reqKey && currentReq()) {
        const r = currentReq();
        let value = el.value;
        if (value === '')
            value = null;
        else if (['true', 'false'].includes(value) && (['need_', 'forbid_'].some(prefix => reqKey.startsWith(prefix)) || typeof r[reqKey] === 'boolean'))
            value = value === 'true';
        else if (el.type === 'number')
            value = num(value);
        r[reqKey] = value;
        if (reqKey === 'keyboard_catalog_item' && value)
            r.keyboard_source_mode = 'catalog';
        if (reqKey === 'mouse_catalog_item' && value)
            r.mouse_source_mode = 'catalog';
        if (reqKey === 'keyboard_source_mode' && value !== 'catalog')
            r.keyboard_catalog_item = null;
        if (reqKey === 'mouse_source_mode' && value !== 'catalog')
            r.mouse_catalog_item = null;
        if (reqKey === 'custom_case_name' && value) {
            r.system_case_mode = 'custom';
            const item = (state.catalogs.case || []).find(x => x.name === value);
            if (item)
                Object.assign(r, item.data || {}, { custom_case_name: value, system_case_mode: 'custom' });
            render();
        }
        if (reqKey === 'custom_aio_name' && value) {
            const item = (state.catalogs.aio || []).find(x => x.name === value);
            if (item)
                Object.assign(r, item.data || {}, { custom_aio_name: value, aio_platform_mode: 'custom' });
            render();
        }
        if (reqKey === 'quantity') {
            synchronizeQuantity(Math.max(0, Math.trunc(num(value))));
            render();
        }
        else if (['product_type', 'aio_platform_mode', 'system_case_mode', 'keyboard_source_mode', 'mouse_source_mode', 'keyboard_catalog_item', 'mouse_catalog_item', 'monitor_catalog_item'].includes(reqKey)) {
            render();
            if (state.plans.length)
                recalcRequirements(['product_type', 'keyboard_source_mode', 'mouse_source_mode', 'keyboard_catalog_item', 'mouse_catalog_item', 'monitor_catalog_item'].includes(reqKey));
        }
        else if (state.plans.length)
            recalcRequirements();
        scheduleSave();
        return;
    }
    if (el.dataset.rowField) {
        const p = currentPlan(), idx = Number(el.dataset.index), row = p?.rows[idx];
        if (!row)
            return;
        const k = el.dataset.rowField;
        if (k === 'price_input')
            updateRowPrice(idx, el.value);
        else if (k === 'alternative') {
            if (el.value) {
                row.name = el.value;
                row.price = 0;
                row.price_input = '';
                row._locked = true;
                toast('Цена нового процессора сброшена. Укажите актуальную цену.');
                render();
                scheduleSave();
            }
        }
        else {
            row[k] = k === 'qty' ? Math.max(0, num(el.value)) : el.value;
            row._locked = true;
            updateTotals();
            scheduleSave();
        }
        return;
    }
    if (el.dataset.buildQuantity !== undefined) {
        const amount = Math.max(0, Math.trunc(num(el.value)));
        synchronizeQuantity(amount);
        render();
        return;
    }
    if (el.dataset.arsenal) {
        state.arsenalFields[el.dataset.arsenal] = el.value;
        scheduleSave();
        return;
    }
    if (el.dataset.setting) {
        state.settings[el.dataset.setting] = el.type === 'checkbox' ? el.checked : ((el.type === 'number' || el.type === 'range') ? num(el.value) : el.value);
        if (el.dataset.setting === 'sidebar_width')
            render();
        return;
    }
    if (el.dataset.priceKey) {
        const k = el.dataset.priceKey;
        if (state.prices[k])
            state.prices[k].price = num(el.value);
        return;
    }
    if (el.dataset.field) {
        setField(el);
        return;
    }
}
let eisPollTimer;
let eisPollFailures = 0;
const eisActive = job => ['queued', 'running'].includes(job?.status);
async function eisJobApi(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try { return await api(path, body, 'POST', {}, { signal: controller.signal }); }
    finally { clearTimeout(timeout); }
}
function refreshEisProgress() {
    const active = document.activeElement;
    if (active?.matches('input,textarea,select')) {
        const feedback = document.querySelector('.qx-import-job');
        if (feedback) feedback.outerHTML = dashboardImportReport(state.eisImportResult, state.tab === 'tenders' ? state.tenders.current?.number : '');
        return;
    }
    if (state.tab === 'home' || state.tab === 'tenders') render();
}
function acceptEisJob(payload) {
    const job = payload.job;
    state.eisImportJob = job;
    state.eisImportDraft = payload.tender || state.eisImportDraft;
    state.eisImportBusy = eisActive(job);
    state.eisImportResult = job.result || null;
    state.eisImportError = job.status === 'failed' ? (job.message || 'Поиск не завершён. Карточка сохранена.') : '';
    try {
        if (eisActive(job)) localStorage.setItem('qx-eis-last-job', job.id);
        else localStorage.removeItem('qx-eis-last-job');
    } catch { }
}
async function pollEisJob(id) {
    clearTimeout(eisPollTimer);
    try {
        const payload = await eisJobApi('eis/jobs/' + encodeURIComponent(id));
        if (state.eisImportJob?.id !== id) return;
        eisPollFailures = 0;
        acceptEisJob(payload);
        if (!eisActive(payload.job)) {
            await loadTenders(null, false);
            if (state.tenders.current?.id === payload.job.tender_id && !document.activeElement?.dataset?.tenderField)
                await openTender(payload.job.tender_id, false);
        }
        refreshEisProgress();
        if (eisActive(payload.job)) eisPollTimer = setTimeout(() => void pollEisJob(id), 700);
    } catch (error) {
        if (state.eisImportJob?.id !== id) return;
        if (error.status !== 404 && ++eisPollFailures < 4) {
            state.eisImportJob.message = 'Не удалось обновить ход поиска. Восстанавливаем связь с локальной программой…';
            refreshEisProgress();
            eisPollTimer = setTimeout(() => void pollEisJob(id), 2000);
            return;
        }
        state.eisImportBusy = false;
        state.eisImportJob = { ...state.eisImportJob, status: 'interrupted' };
        state.eisImportError = error.status === 404 ? 'Задача больше не выполняется. Карточка и уже скачанные файлы сохранены; можно повторить поиск.' : 'Не удалось получить состояние поиска. Карточка сохранена. Откройте реестр или повторите поиск.';
        await loadTenders(null, false);
        refreshEisProgress();
    }
}
async function restoreEisJobs() {
    try {
        let last;
        try { last = localStorage.getItem('qx-eis-last-job'); } catch { }
        let payload;
        if (last) {
            try { payload = await eisJobApi('eis/jobs/' + encodeURIComponent(last)); } catch { }
        }
        if (!payload) {
            const active = await eisJobApi('eis/jobs');
            const job = active.jobs?.[active.jobs.length - 1];
            if (job) payload = await eisJobApi('eis/jobs/' + encodeURIComponent(job.id));
        }
        if (!payload || state.eisImportBusy) return;
        state.homeEisNumber = payload.job.number;
        acceptEisJob(payload);
        refreshEisProgress();
        if (eisActive(payload.job)) void pollEisJob(payload.job.id);
    } catch { /* Older local server versions have no job API until restarted. */ }
}
async function importEisByNumber(tenderId = '', downloadDocuments = true, numberOverride = '') {
    if (state.eisImportBusy) return;
    const raw = numberOverride || (tenderId ? state.tenders.current?.number : ($('#home-eis-number')?.value || state.homeEisNumber || ''));
    const number = String(raw || '').trim();
    if (!number || number.length > 2048) {
        state.eisImportError = 'Введите номер извещения или ссылку на карточку ЕИС.';
        state.eisImportResult = null;
        state.eisImportJob = null;
        render();
        $('#home-eis-number')?.focus();
        return;
    }
    if (!tenderId) {
        state.homeEisNumber = number;
        state.homeEisDownloadDocuments = $('#home-eis-docs')?.checked !== false;
        downloadDocuments = state.homeEisDownloadDocuments;
    }
    state.eisImportBusy = true;
    state.eisImportError = '';
    state.eisImportResult = null;
    state.eisImportDraft = null;
    state.eisImportJob = null;
    render();
    try {
        // An unrelated invalid edit must not prevent creating a new local card.
        const candidates = number.match(/[0-9]{19,20}|[0-9]{11}/g) || [];
        for (const [id, queue] of tenderFieldSaves)
            if (id === tenderId || candidates.includes(queue.target?.number)) await flushTenderFields(id);
        const payload = await eisJobApi('eis/jobs', { number, download_documents: downloadDocuments, tender_id: tenderId });
        state.homeEisNumber = payload.job.number;
        acceptEisJob(payload);
        render();
        await loadTenders(null, false);
        refreshEisProgress();
        if (eisActive(payload.job)) void pollEisJob(payload.job.id);
    } catch (error) {
        state.eisImportBusy = false;
        state.eisImportError = error.status === 404 ? 'Запущена старая версия локального сервера. Полностью закройте QX и запустите ЗАПУСТИТЬ_QX.cmd из обновлённой папки.' : (error.name === 'AbortError' ? 'Локальный сервер не ответил вовремя. Проверьте реестр: созданная карточка сохраняется независимо от поиска.' : 'Не удалось начать поиск: ' + error.message);
        await loadTenders(null, false);
        refreshEisProgress();
    }
}
function eisSyncReport(number) {
    const result = state.eisImportResult?.tender?.number === number ? state.eisImportResult : null;
    return dashboardImportReport(result, number);
}
async function handleAction(el) {
    const a = el.dataset.action;
    if (a === 'home-eis-import') return importEisByNumber(el.dataset.tenderId || '', true, el.dataset.number || '');
    if (a === 'tender-eis-sync') return importEisByNumber(state.tenders.current?.id, true);
    if (a?.startsWith('notes-')) {
        if (a === 'notes-new')
            return addNote();
        if (a === 'notes-open') {
            notesState.selected = el.dataset.id;
            render();
            return;
        }
        if (a === 'notes-pin')
            return noteToggle(el.dataset.id, 'pinned');
        if (a === 'notes-complete')
            return noteToggle(el.dataset.id, 'completed');
        if (a === 'notes-delete')
            return removeNote(el.dataset.id);
        if (a === 'notes-show-calendar') {
            const note = notesState.items.find(n => n.id === el.dataset.id);
            if (!note?.due_on) return;
            clearTimeout(noteSaveTimers.get(note.id));
            await saveNote(note.id);
            state.tenders.calendarFocus = note.due_on;
            const parts = note.due_on.split('-').map(Number);
            const today = new Date();
            state.tenders.monthDelta = (parts[0]-today.getFullYear())*12+parts[1]-1-today.getMonth();
            gotoTender('calendar');
            return;
        }
        if (a === 'notes-export') {
            return download('notes-export', undefined, 'QX_Quick_Notes.json');
        }
    }
    if (a === 'tender-group') {
        state.tenders.expanded = !state.tenders.expanded;
        render();
        $('#tender-nav-toggle')?.focus({ preventScroll: true });
        return;
    }
    if (a === 'tender-nav') {
        gotoTender(el.dataset.view || 'registry');
        return;
    }
    if (a === 'tender-eis-preview')
        return previewTenderEis();
    if (a === 'tender-link-loaded') {
        await syncTenderProject(true);
        if (state.tenderId && /^\d{19,20}$/.test(state.tenderNoticeNumber || ''))
            void previewTenderEis(true);
        return;
    }
    if (a?.startsWith('tender-'))
        return handleTenderAction(el);
    if (!a)
        return;
    const actions = {
        'tab': () => goto((el.dataset.tab || 'home')),
        'collapse': () => { state.collapse = !state.collapse; state.settings.sidebar_collapsed = state.collapse; api('settings', { sidebar_collapsed: state.collapse }).catch(console.warn); render(); },
        'pos': () => { state.pos = Number(el.dataset.index) || 0; chooseDocForPosition(state.pos); state.arsenalText = ''; render(true); },
        'kind': async () => { state.catalogKind = el.dataset.kind || 'equipment'; state.catalogSearch = ''; render(); },
        'open-peripheral-catalog': () => { state.catalogKind = ['monitor', 'keyboard', 'mouse'].includes(el.dataset.kind) ? el.dataset.kind : 'monitor'; state.catalogSearch = ''; goto('catalog'); },
        'upload': () => chooseAndUpload('tz'),
        'tz-doc-view': () => { const index = state.reqs.findIndex(r => r._qx_doc_id === el.dataset.id); if (index < 0)
            return; state.pos = index; chooseDocForPosition(index); state.tab = 'tz'; render(true); },
        'tz-doc-remove': () => {
            const id = el.dataset.id;
            if (!window.confirm('Убрать этот файл и все связанные с ним позиции из расчёта? Сначала сохраните копию проекта.'))
                return;
            storeCurrentDoc();
            const saved = [];
            const savedPlans = [];
            state.reqs.forEach((r, i) => { if (r._qx_doc_id !== id) {
                saved.push(r);
                if (state.plans[i])
                    savedPlans.push({ index: saved.length - 1, plan: state.plans[i] });
            } });
            state.reqs = saved;
            state.plans = [];
            for (const p of savedPlans)
                state.plans[p.index] = p.plan;
            state.tzDocuments = state.tzDocuments.filter(d => d.id !== id);
            state.activeTzDocId = '';
            state.pos = Math.min(state.pos, Math.max(0, state.reqs.length - 1));
            state.tzAiResults = {};
            chooseDocForPosition();
            render();
            scheduleSave();
            toast('Файл и связанные позиции убраны из расчёта. Документы в карточке закупки при необходимости удалите отдельно.');
        },
        'tz-ai-models': () => refreshTenderAiStatus(),
        'tz-ai-run': () => runTzAi(),
        'tz-ai-all': () => runTzAiBatch(),
        'tz-ai-diagnostic': () => testLiteInference(),
        'tz-ai-apply': () => applyTzAi(),
        'view-source': async () => {
            state.modal = 'source';
            render();
            if (!state.sourcePreview) {
                try {
                    const result = await api('document/preview', {
                        source_filename: state.source_filename,
                        source_docx_base64: state.source_docx_base64,
                        source_text: state.source_text,
                        characteristics: state.characteristics,
                    });
                    state.sourcePreview = result;
                    if (state.modal === 'source')
                        render();
                }
                catch (err) {
                    console.error(err);
                    toast('Не удалось открыть таблицу ТЗ: ' + err.message, true);
                    state.modal = '';
                    render();
                }
            }
        },
        'char-filter': () => { state.charFilter = el.dataset.value || 'all'; const node = $('#characteristic-list'); if (node)
            node.innerHTML = characteristicTable(); },
        'minimums': async () => { if (!state.charRows.length)
            await refreshChar(); let n = 0; for (const ch of state.charRows) {
            if (!ch.editable)
                continue;
            const val = minimumFor(ch.original_value);
            if (val !== null) {
                state.overrides[ch.id] = val;
                n++;
            }
        } await refreshChar(); scheduleSave(); toast('Установлены минимальные значения: ' + n + '. Проверьте фактическое соответствие оборудования.'); },
        'new': () => {
            const hasWork = Boolean(state.source_filename || state.tzDocuments.length || state.plans.length || state.name !== 'Новый расчёт' || state.reqs.length > 1);
            if (hasWork && (!state.projectSavedManually || state.projectHasEdits)) {
                state.modal = 'unsaved-project'; render(); return;
            }
            resetCalculation();
        },
        'new-discard': () => resetCalculation(),
        'new-save-first': async () => { if (await saveProjectNow()) resetCalculation(); },
        'toggle-all-fields': () => { state.showAllFields = !state.showAllFields; render(); },
        'new-position': () => { const r = emptyReq(); r.title = 'ТИП ' + (state.reqs.length + 1); state.reqs.push(r); state.pos = state.reqs.length - 1; chooseDocForPosition(state.pos); state.tab = 'tz'; render(true); scheduleSave(); },
        'select': () => selectPlans(),
        'full': () => { state.full = !state.full; toggleFull(); },
        'manual': () => {
            const p = currentPlan();
            if (!p)
                return;
            p.rows.push({ category: 'Своя позиция', name: 'Новая строка', qty: 1, price: 0, price_input: '', source: 'Вручную', _manual: true });
            render();
            scheduleSave();
        },
        'remove-row': () => {
            const p = currentPlan();
            if (!p)
                return;
            const i = num(el.dataset.index);
            p.rows.splice(i, 1);
            render();
            scheduleSave();
        },
        'dns': () => window.open('https://www.dns-shop.ru/', '_blank', 'noopener,noreferrer'),
        'supplier-import': () => chooseAndUpload('supplier'),
        'rate': async () => { await busy(async () => { state.rate = await api('rate'); render(); toast(state.rate.live ? 'Курс ЦБ обновлён' : 'Используется сохранённый курс: ЦБ РФ сейчас недоступен'); }); },
        'project-save': () => saveProjectNow(),
        'project-load': () => chooseAndUpload('project'),
        'restore': async () => {
            await busy(async () => {
                const result = await api('project/autosave');
                if (result.found) {
                    importProject(result.project);
                    toast('Проект восстановлен');
                }
                else
                    toast('Автосохранение не найдено', true);
            });
        },
        'excel': () => currentPlan() && download('export/excel', { name: state.name, plan: currentPlan() }, 'QX_Расчёт_' + (state.pos + 1) + '.xlsx'),
        'offer': () => {
            const bad = state.plans.findIndex(p => num(p.req?.quantity) <= 0);
            if (bad >= 0) {
                state.pos = bad;
                goto('build');
                toast('Для коммерческого предложения укажите количество изделий больше нуля', true);
                return;
            }
            const read = (k) => $(`[data-doc="${k}"]`)?.value;
            download('export/offer', { plans: state.plans, percent: num(read('percent'), 20), mode: read('mode') || 'markup', warranty: num(read('warranty'), 12), validity: num(read('validity'), 30) }, 'QX_Коммерческое_предложение.docx');
        },
        'fill': () => { const scope = currentDocCalculation(); download('export/filled-tz', { source_docx_base64: state.source_docx_base64, characteristics: state.characteristics, overrides: state.overrides, reqs: scope.reqs, plans: scope.plans }, 'QX_Заполненное_' + (state.source_filename || 'ТЗ').replace(/\.[^.]+$/, '').replace(/[\\/:*?"<>|]/g, '_') + '.docx'); },
        'refresh-char': () => refreshChar(),
        'make-arsenal': async () => {
            if (state.plans.some(p => num(p.req?.quantity) <= 0)) {
                toast('Укажите количество для каждой позиции перед формированием Арсенала', true);
                return;
            }
            await busy(async () => { const result = await api('arsenal', { plans: state.plans, fields: state.arsenalFields }); state.arsenalText = result.text; render(); });
        },
        'copy-arsenal': async () => {
            try {
                await navigator.clipboard.writeText(state.arsenalText);
                toast('Текст Арсенала скопирован');
            }
            catch {
                toast('Копирование недоступно, выделите текст вручную', true);
            }
        },
        'catalog-export': () => download('catalog-export', undefined, 'QX_UserCatalog.qxdb'),
        'catalog-import': () => chooseAndUpload('catalog'),
        'add-catalog': () => { state.draftCatalog = { name: '', data: {} }; state.modal = 'catalog'; render(); },
        'edit-catalog': () => { const found = (state.catalogs[state.catalogKind] || []).find((x) => x.name === el.dataset.name); state.draftCatalog = clone(found || { name: '', data: {} }); state.modal = 'catalog'; render(); },
        'delete-catalog': async () => {
            if (!window.confirm('Удалить ' + el.dataset.name + '?'))
                return;
            await busy(async () => { await api('catalog/' + encodeURIComponent(state.catalogKind) + '/' + encodeURIComponent(el.dataset.name || ''), {}, 'DELETE'); await refreshCatalog(); render(); });
        },
        'save-catalog': async () => {
            const name = $('[data-modal-name]')?.value.trim();
            const raw = $('[data-modal-json]')?.value || '{}';
            let d;
            try {
                d = JSON.parse(raw);
                if (!d || Array.isArray(d) || typeof d !== 'object')
                    throw new Error();
            }
            catch {
                toast('Исправьте JSON: неверный формат карточки', true);
                return;
            }
            if (!name) {
                toast('Укажите название оборудования', true);
                return;
            }
            for (const element of Array.from(document.querySelectorAll('[data-catalog-value]'))) {
                const el = element;
                const key = el.dataset.catalogValue || '', typ = el.dataset.catalogType;
                d[key] = typ === 'bool' ? el.value === 'true' : typ === 'number' ? (el.value.trim() ? num(el.value) : 0) : el.value.trim();
            }
            d.name = name;
            if (state.catalogKind === 'case')
                d.custom_case_name = name;
            if (state.catalogKind === 'aio')
                d.custom_aio_name = name;
            if (state.catalogKind === 'equipment_profile')
                d.profile_name = name;
            const rawPrice = $('[data-modal-price-input]')?.value?.trim();
            if (rawPrice !== undefined) {
                if (rawPrice) {
                    try {
                        const calc = await api('price', { value: rawPrice, rate: state.rate.rate, buffer: state.settings.usd_buffer_rub });
                        const pref = state.catalogKind === 'case' ? 'custom_case_' : state.catalogKind === 'aio' ? 'custom_aio_' : '';
                        d[pref + 'price'] = calc.price;
                        d[pref + 'price_input'] = rawPrice;
                        d[pref + 'price_conversion'] = calc.note || '';
                    }
                    catch (e) {
                        toast('Невозможно обработать цену: ' + e.message, true);
                        return;
                    }
                }
                else {
                    const pref = state.catalogKind === 'case' ? 'custom_case_' : state.catalogKind === 'aio' ? 'custom_aio_' : '';
                    d[pref + 'price'] = 0;
                    d[pref + 'price_input'] = '';
                }
            }
            if (d.registry_number !== undefined)
                d.registry = !!d.registry_number;
            await busy(async () => { await api('catalog/' + encodeURIComponent(state.catalogKind), { name, data: d }); state.modal = ''; await refreshCatalog(); render(); toast('Оборудование сохранено в базе'); });
        },
        'close-modal': () => { state.modal = ''; render(); },
        'save-prices': async () => { await busy(async () => { const r = await api('prices', state.prices); state.prices = r.prices; render(); toast('Прайс сохранён'); }); },
        'legacy-import-choose': async () => { const f = await openNativeFile('legacy'); if (f)
            await previewLegacyZip(f); },
        'legacy-import-apply': async () => { await applyLegacyZip(); },
        'legacy-import-cancel': () => { state.legacyPreview = null; state.legacyZip = null; render(); },
        'diagnostics-run': async () => { await busy(async () => { state.diagnostics = await api('diagnostics', undefined); render(); toast(state.diagnostics.overall === 'error' ? 'Диагностика обнаружила ошибки' : 'Проверка системы завершена', state.diagnostics.overall === 'error'); }); },
        'audit-attachments': async () => { await busy(async () => { if (!state.diagnostics)
            state.diagnostics = await api('diagnostics', undefined); state.attachmentAudit = await api('diagnostics/attachments', undefined); render(); toast(state.attachmentAudit.status === 'error' ? 'Проверка нашла повреждения документов' : 'Все документы проверены', state.attachmentAudit.status === 'error'); }); },
        'repair-attachments-choose': async () => { const f = await openNativeFile('tender_repair'); if (f)
            await previewTenderRepair(f); },
        'repair-attachments-confirm': async () => { const file = state.tenderRepairFile; if (!file || !state.tenderRepairPreview?.repairable)
            return toast('Нечего восстанавливать', true); await busy(async () => { const r = await api('tenders/backup/repair', file, 'POST', { 'X-QX-Confirm-Repair': 'REPAIR_DAMAGED_ATTACHMENTS_ONLY' }); state.tenderRepairFile = null; state.tenderRepairPreview = null; state.modal = ''; state.attachmentAudit = await api('diagnostics/attachments'); render(); toast('Восстановлено документов: ' + r.repaired + '. Закупки и комментарии не менялись.'); }); },
        'save-settings': async () => { await busy(async () => { const r = await api('settings', state.settings); state.settings = r.settings; render(); toast('Настройки сохранены'); }); },
        'theme': async () => { state.theme = el.dataset.theme || 'dark'; state.settings.ui_theme = state.theme; await api('settings', { ui_theme: state.theme }); render(); },
        'classic-info': async () => {
            if (bridgeApi()?.open_classic) {
                const r = await bridgeApi().open_classic();
                if (r?.ok)
                    toast('Открываем классический QX');
                else
                    toast(r?.error || 'Ошибка запуска', true);
            }
            else {
                state.modal = 'classic';
                render();
            }
        },
    };
    if (actions[a])
        await actions[a]();
}
async function refreshCatalog() { const r = await api('catalog/' + state.catalogKind, undefined); state.catalogs[state.catalogKind] = r.items; }
async function refreshChar() { await busy(async () => { const r = await api('characteristics', { characteristics: state.characteristics, ...currentDocCalculation(), overrides: state.overrides }); state.charRows = r.rows || []; const node = $('#characteristic-list'); if (node)
    node.innerHTML = state.charRows.length ? characteristicTable() : empty('Нет строк для заполнения', 'Исходный документ не содержит распознанных характеристик.'); }); }
function minimumFor(original) { const str = String(original ?? '').replaceAll('≥', '>=').replaceAll('≤', '<=').replaceAll('−', '-').trim(); const m = str.match(/(>=|<=|>|<|не менее|не более|более|менее)\s*(-?\d+(?:[.,]\d+)?)/i); if (!m)
    return null; let n = Number(m[2].replace(',', '.')); const op = m[1].toLowerCase(); if (op === '>' || op === 'более')
    n += 1; if (op === '<' || op === 'менее')
    n -= 1; return String(n).replace('.', ','); }
function toggleFull() {
    let overlay = $('#fullscreen-area');
    if (overlay)
        overlay.remove();
    if (state.full && currentPlan()) {
        const el = document.createElement('div');
        el.className = 'fulltable';
        el.id = 'fullscreen-area';
        el.innerHTML = `<div class="flex between" style="margin-bottom:18px"><div><h2>⛶ Полноэкранная спецификация</h2><p class="subtitle">Изменения сохраняются в текущем расчёте</p></div><button class="btn primary" data-action="full">✕ Закрыть</button></div>${tableBuild(currentPlan())}<div class="toolbar" style="margin-top:15px"><button class="btn secondary" data-action="manual">＋ Добавить строку</button><strong id="table-total">${rub(unitCost(currentPlan()))}</strong></div>`;
        document.body.appendChild(el);
    }
}
function installGlobalEvents() {
    document.addEventListener('submit', e => {
        if (e.target?.id === 'home-eis-form') { e.preventDefault(); void importEisByNumber(); }
    });
    document.addEventListener('click', async (e) => {
        const el = e.target?.closest('[data-action]');
        if (el) {
            e.preventDefault();
            await handleAction(el);
        }
    });
    document.addEventListener('change', e => {
        const el = e.target;
        if (el?.id === 'home-eis-docs') { state.homeEisDownloadDocuments = el.checked; return; }
        if (el?.dataset?.notesDone !== undefined) {
            notesState.showDone = !!el.checked;
            render();
            return;
        }
        if (el?.dataset?.noteField !== undefined) {
            noteEdited(el);
            return;
        }
        if (el?.dataset?.tenderNotifications !== undefined || el?.dataset?.tenderLead !== undefined) {
            const enabled = !!document.querySelector('[data-tender-notifications]')?.checked;
            const lead = Number(document.querySelector('[data-tender-lead]')?.value || 7);
            api('tenders/reminders/settings', { enabled, advance_days: lead }).then(r => { state.tenders.reminderSettings = r.settings; toast('Настройки напоминаний сохранены'); }).catch(err => toast('Настройки: ' + err.message, true));
            return;
        }
        if (el?.dataset?.tenderStatusFilter !== undefined) {
            state.tenders.statusFilter = el.value;
            filterTenderRows();
            return;
        }
        if (el?.dataset?.tenderOrgFilter !== undefined) {
            state.tenders.orgFilter = el.value;
            filterTenderRows();
            return;
        }
        if (el?.dataset?.tenderAutoLink !== undefined) {
            state.tenderLinkEnabled = el.checked;
            state.tenderEisMessage = '';
            scheduleSave();
            render();
            return;
        }
        if (el?.dataset?.tenderNoticeInput !== undefined) {
            const next = el.value.trim();
            if (next !== state.tenderNoticeNumber) {
                state.tenderNoticeNumber = next;
                state.tenderId = '';
                state.tenderEisPreview = null;
                state.tenderEisMessage = '';
            }
            scheduleSave();
            render();
            return;
        }
        if (el?.dataset?.tenderField) {
            tenderChanged(el);
            return;
        }
        if (el?.dataset.tzAiAuto !== undefined) {
            state.tzAiAuto = el.checked;
            return;
        }
        if (el?.dataset.tzAiFill !== undefined) {
            state.tzAiFill = el.checked;
            return;
        }
        if (el?.id === 'tz-ai-model') {
            state.tzAiModel = el.value;
            return;
        }
        onChange(e);
        if (el?.dataset.characteristic) {
            state.overrides[el.dataset.characteristic] = el.value;
            scheduleSave();
        }
    });
    document.addEventListener('input', e => {
        const el = e.target;
        if (el?.id === 'home-eis-number') { state.homeEisNumber = el.value; return; }
        if (el?.dataset?.noteField !== undefined) {
            noteEdited(el);
            return;
        }
        if (el?.dataset?.notesSearch !== undefined) {
            notesState.query = el.value;
            const pos = el.selectionStart || el.value.length;
            render();
            requestAnimationFrame(() => { const inp = $('[data-notes-search]'); if (inp) {
                inp.focus();
                inp.setSelectionRange(pos, pos);
            } });
            return;
        }
        if (el?.dataset?.tenderSearch !== undefined) {
            state.tenders.filter = el.value;
            filterTenderRows();
            return;
        }
        if (el?.dataset.req === 'quantity' || el?.dataset.buildQuantity !== undefined) {
            synchronizeQuantity(Math.max(0, Math.trunc(num(el.value))));
            return;
        }
        if (el?.dataset.field === 'reqSearch' || el?.dataset.field === 'catalogSearch') {
            const kind = el.dataset.field;
            const value = el.value;
            const pos = el.selectionStart || value.length;
            if (kind === 'reqSearch')
                state.reqSearch = value;
            else
                state.catalogSearch = value;
            render();
            requestAnimationFrame(() => {
                const fresh = $(`[data-field="${kind}"]`);
                if (fresh) {
                    fresh.focus();
                    fresh.setSelectionRange(pos, pos);
                }
            });
            return;
        }
        if (el?.dataset.sourceFilter !== undefined) {
            const query = el.value.trim().toLocaleLowerCase('ru');
            let matching = 0;
            document.querySelectorAll('[data-source-section]').forEach(section => {
                let visible = 0;
                section.querySelectorAll('[data-source-row]').forEach(row => {
                    const found = !query || row.textContent.toLocaleLowerCase('ru').includes(query);
                    row.hidden = !found;
                    if (found) {
                        visible++;
                        matching++;
                    }
                });
                section.hidden = visible === 0 && !!query;
            });
            const count = $('[data-source-count]');
            if (count)
                count.textContent = query ? `Найдено строк: ${matching}` : '';
            return;
        }
        if (el?.dataset.charSearch !== undefined) {
            const query = el.value.toLowerCase().trim();
            document.querySelectorAll('[data-char-row]').forEach(row => {
                row.style.display = (row.textContent + ' ' + Array.from(row.querySelectorAll('input')).map(x => x.value).join(' ')).toLowerCase().includes(query) ? '' : 'none';
            });
        }
        if (el?.dataset.filterRows !== undefined) {
            const query = el.value.toLowerCase().trim();
            document.querySelectorAll('.price-table tbody tr').forEach(row => {
                const r = row;
                const values = [r.textContent || '', ...Array.from(r.querySelectorAll('input')).map(input => input.value)].join(' ').toLowerCase();
                r.style.display = values.includes(query) ? '' : 'none';
            });
        }
    });
    document.addEventListener('focusout', e => { if (e.target?.dataset?.noteField !== undefined) {
        const id = notesState.selected;
        if (id)
            scheduleNoteWrite(id, 0);
    } });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && state.full) {
            state.full = false;
            toggleFull();
        }
        if (e.ctrlKey && e.key.toLowerCase() === 's') {
            e.preventDefault();
            void saveProjectNow();
        }
    });
    const listenFile = async (id, handler) => {
        const input = $(id);
        input?.addEventListener('change', async () => {
            const f = input.files?.[0];
            if (f)
                await handler(f);
            input.value = '';
        });
    };
    const tzInput = $('#file-tz');
    tzInput?.addEventListener('change', async () => { const files = Array.from(tzInput.files || []); tzInput.value = ''; if (files.length)
        await uploadTzFiles(files); });
    listenFile('#file-tender', tenderUpload);
    listenFile('#file-tender-project', tenderImportProject);
    listenFile('#file-tender-package', tenderImportPackage);
    listenFile('#file-tender-backup', tenderRestoreInspect);
    listenFile('#file-tender-repair', previewTenderRepair);
    listenFile('#file-legacy', previewLegacyZip);
    listenFile('#file-project', loadProjectFile);
    listenFile('#file-catalog', loadCatalogFile);
    listenFile('#file-supplier', loadSupplierFile);
}
async function init() {
    installGlobalEvents();
    try {
        const boot = await api('boot');
        state.runtimeVersion = boot.version || '';
        state.settings = boot.settings || {};
        state.reqDefaults = boot.requirements_defaults || {};
        state.prices = boot.prices || {};
        state.catalogs = boot.catalogs || {};
        state.theme = state.settings.ui_theme || 'dark';
        state.collapse = !!state.settings.sidebar_collapsed;
        state.rate = { rate: num(state.settings.usd_rate_cached), date: state.settings.usd_rate_date_cached || '', live: false };
        state.arsenalFields = { ...state.arsenalFields, sender: state.settings.default_sender || 'ЗИОН', country: state.settings.default_country || 'Россия', trademark: state.settings.default_trademark || '1093786' };
        render();
        void loadTenders();
        void restoreEisJobs();
        api('rate').then(rate => {
            state.rate = rate;
            const active = document.activeElement;
            if (!active || active.tagName === 'BODY')
                render();
            else {
                const top = $('.top-rate strong');
                if (top)
                    top.textContent = fmt(num(rate.rate) + num(state.settings.usd_buffer_rub, 5), 2) + ' ₽';
            }
        }).catch(console.warn);
    }
    catch (e) {
        const root = $('#app');
        if (root)
            root.innerHTML = `<div class="boot-screen"><div class="boot-mark">Q<span>X</span></div><h2>Не удалось запустить QX Modern</h2><p>${esc(e.message)}</p><p>Проверьте, что локальный сервер запущен.</p></div>`;
    }
}
/* QX Tender workspace. All financial values come from local data, not examples. */
state.tenders = { items: [], organizations: [], summary: {}, statuses: [], selected: null, current: null, deleteCandidate: null, analysis: null, detailTab: 'overview', filter: '', statusFilter: '', orgFilter: '', view: 'registry', expanded: false };
function gotoTender(view) { state.tab = 'tenders'; state.tenders.view = tenderViewTitles[view] ? view : 'registry'; state.tenders.selected = null; state.tenders.current = null; state.tenders.analysis = null; render(true); loadTenders(); }
state.tenderProjectKey = (globalThis.crypto?.randomUUID?.() || 'qx-' + Date.now() + '-' + Math.random().toString(36).slice(2));
state.tenderId = '';
state.tenders.calendar = false;
state.tenders.calendarNotes = [];
state.tenders.monthDelta = 0;
state.tenderLocalAnswer = null;
state.tenderAiStatus = null;
state.tenderAiInstall = null;
state.tenderAiModel = 'offline-search';
state.tenderEisLookup = null;
let tenderSyncTimer;
const tenderDate = (s) => s ? new Date(s + 'T12:00:00').toLocaleDateString('ru-RU') : '—';
const tenderStatusColor = (s) => s === 'Контракт исполнен' ? 'ok' : s === 'Проиграли' || s === 'Отменено' ? 'bad' : s?.includes('подписан') ? 'ok' : 'unknown';
async function loadTenders(selected = null, redraw = true) {
    try {
        const [res, rem, noteResult] = await Promise.all([api('tenders', undefined, 'GET'), api('tenders/reminders', undefined, 'GET'), api('calendar/notes', undefined, 'GET')]);
        Object.assign(state.tenders, { loaded: true, items: res.items || [], organizations: res.organizations || [], summary: res.summary || {}, statuses: res.statuses || [], reminders: rem.items || [], reminderSettings: rem.settings || { enabled: false, advance_days: 7 }, calendarNotes: (noteResult.items || []).map(n => { const editing = notesState.items.find(x => x.id === n.id); return editing && Number(editing._editRev || 0) > Number(n.revision || 0) ? {...n, ...editing} : n; }) });
        if (selected)
            await openTender(selected, false);
        if (redraw && (state.tab === 'tenders' || (state.tab === 'home' && document.activeElement?.id !== 'home-eis-number')))
            render();
    }
    catch (e) {
        toast('База закупок недоступна: ' + e.message, true);
    }
}
async function openTender(id, redraw = true) {
    await flushTenderFields(id);
    const res = await api('tenders/' + encodeURIComponent(id), undefined, 'GET');
    if (state.tenders.selected !== id)
        state.tenders.detailTab = 'overview';
    state.tenders.selected = id;
    state.tenders.current = res.tender;
    state.tenders.analysis = null;
    state.tenderLocalAnswer = null;
    state.tenderEisLookup = null;
    if (state.tenderEisDiscovery?.notice_number !== res.tender.number) state.tenderEisDiscovery = null;
    if (redraw)
        render(true);
}
function tenderField(name, value, type = 'text', extra = '') {
    const input = type === 'select' ? `<select data-tender-field="${esc(name)}">${extra}</select>` : type === 'textarea' ? `<textarea data-tender-field="${esc(name)}" rows="3">${esc(value ?? '')}</textarea>` : `<input data-tender-field="${esc(name)}" type="${type}" ${type === 'number' ? 'min="0" step="any"' : ''} value="${esc(value ?? '')}">`;
    return field(tenderLabels[name] || name, input);
}
const tenderLabels = { is_quotation: 'Запрос котировок (без торгов)', results_on: 'Подведение итогов котировки (дата)', results_time: 'Подведение итогов (время, если известно)', number: 'Номер закупки', lot: 'Лот', title: 'Предмет закупки', customer: 'Заказчик', law: 'Закон', status: 'Статус', organization_id: 'Организация', nmck: 'НМЦК, ₽', bid_price: 'Цена предложения, ₽', contract_price: 'Цена контракта, ₽', purchase_cost: 'Себестоимость, ₽', delivery_cost: 'Логистика, ₽', extra_cost: 'Прочие расходы, ₽', paid_amount: 'Оплачено, ₽', payment_status: 'Статус оплаты', contract_number: 'Номер контракта', signed_on: 'Контракт подписан', application_due_on: 'Приём заявок до (дата)', application_due_time: 'Приём заявок до (время местное)', auction_on: 'Аукцион (дата)', auction_time: 'Аукцион (время местное)', payment_due_on: 'Оплата ожидается до', due_on: 'Крайняя дата поставки', due_days: 'Срок после подписания, дней', due_unit: 'Тип дней', supply_address: 'Адрес поставки', payment_terms: 'Условия оплаты', warranty: 'Гарантия', security: 'Обеспечение контракта', notes: 'Примечание', is_delivered: 'Исполнение подтверждено' };
function tenderStats() { const s = state.tenders.summary; return `<div class="tender-stats"><div><span>Всего закупок</span><b>${s.total || 0}</b></div><div><span>На просчёте</span><b>${s.calculating || 0}</b></div><div><span>Заявки поданы</span><b>${s.submitted || 0}</b></div><div><span>Выиграно</span><b>${s.won || 0}</b></div><div><span>Исполняются</span><b>${s.active || 0}</b></div><div><span>С возможной просрочкой</span><b class="${s.at_risk ? 'danger-text' : ''}">${s.at_risk || 0}</b></div></div>`; }
function tenderMatches(t) { const v = state.tenders; const q = v.filter.toLocaleLowerCase('ru').trim(); return [t.number, t.title, t.customer, t.organization_name].join(' ').toLocaleLowerCase('ru').includes(q) && (!v.statusFilter || t.status === v.statusFilter) && (!v.orgFilter || (t.organization_id || 'none') === v.orgFilter); }
function tenderEisImportReport() { const r = state.tenderEisUpload; if (!r)
    return ''; const fail = r.failures || []; return `<div class="note" role="status" style="margin-top:10px"><b>Последняя загрузка из ЕИС:</b> успешно обработано ссылок: ${Number(r.success_count ?? 1)}, добавлено файлов: ${(r.imported || []).length}, ошибок: ${fail.length}.${fail.length ? `<div style="margin-top:6px">${fail.map(x => `<div><b>Строка ${Number(x.line) || '?'}:</b> ${esc(x.reason)}</div>`).join('')}</div>` : ''}</div>`; }
function tenderList() { const items = state.tenders.items || []; const matched = items.filter(tenderMatches); return `${pageHead('Реестр закупок', 'Сохраняйте закупки и привязывайте расчёты по желанию.', `<button class="btn secondary" data-action="tender-backup">⇩ Резервная копия</button><button class="btn secondary" data-action="tender-restore">↥ Восстановить</button><button class="btn primary" data-action="tender-new">＋ Новая закупка</button>`)}${tenderStats()}<div class="panel"><div class="tender-list-head"><div><h2>Все закупки</h2><p class="subtitle">Поиск, статусы и организации — без перезагрузки.</p></div><div class="tender-filter-row"><input class="table-search" placeholder="Поиск по номеру, заказчику, товару…" data-tender-search value="${esc(state.tenders.filter)}"><select data-tender-status-filter><option value="">Все статусы</option>${state.tenders.statuses.map(x => `<option value="${esc(x)}" ${state.tenders.statusFilter === x ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select><select data-tender-org-filter><option value="">Все организации</option><option value="none" ${state.tenders.orgFilter === 'none' ? 'selected' : ''}>Без организации</option>${state.tenders.organizations.map(o => `<option value="${esc(o.id)}" ${state.tenders.orgFilter === o.id ? 'selected' : ''}>${esc(o.name)}</option>`).join('')}</select></div></div><div class="table-wrap"><table class="table tender-list-table"><thead><tr><th>Номер / предмет</th><th>Организация / заказчик</th><th>Статус</th><th>Себестоимость</th><th>Обновлено</th><th></th></tr></thead><tbody>${items.map(t => `<tr data-tender-row data-status="${esc(t.status)}" data-org="${esc(t.organization_id || 'none')}" data-query="${esc([t.number, t.title, t.customer, t.organization_name].join(' ').toLowerCase())}" ${tenderMatches(t) ? '' : 'hidden'}><td class="qx-tender-ident"><b>${esc(t.number || 'Без номера')}</b><small>${esc(t.title || 'Без названия')}</small><small>${t.is_quotation ? 'Котировка · ' : ''}Подача до: ${esc(t.application_due_on ? tenderDate(t.application_due_on) + (t.application_due_time ? ' ' + t.application_due_time : '') : 'не указана')}</small></td><td>${esc(t.organization_name || 'Не выбрана')}<small>${esc(t.customer || 'Заказчик не указан')}</small></td><td><span class="status ${tenderStatusColor(t.status)}">${esc(t.status)}</span></td><td class="number">${rub(t.purchase_cost)}</td><td>${esc((t.updated_at || '').slice(0, 10))}</td><td><div class="qx-tender-row-actions"><button class="btn primary small" data-action="tender-open" data-id="${esc(t.id)}">Открыть →</button><button class="btn secondary small qx-delete-tender-icon" data-action="tender-delete" data-id="${esc(t.id)}" aria-label="Удалить закупку ${esc(t.number || t.title || 'без номера')}" title="Удалить закупку">🗑</button></div></td></tr>`).join('')}</tbody></table></div><p id="tender-no-matches" class="subtitle" ${matched.length ? 'hidden' : ''}>По выбранным фильтрам закупки не найдены.</p>${items.length ? '' : empty('Пока нет закупок', 'Загрузите ТЗ, выполните подбор либо создайте закупку вручную.')}</div><div class="note" style="margin-top:16px">ЕИС: ссылки открывают официальный поиск. Автоматическое получение актуального статуса без подтверждённого подключения к ЕИС не выполняется.</div>`; }
function tenderDetail() {
    const t = state.tenders.current;
    if (!t)
        return tenderList();
    const d = t.deadline || {}, docs = t.documents || [], comm = t.comments || [], ship = t.shipments || [], ev = t.events || [], profit = num(t.contract_price) - num(t.purchase_cost) - num(t.delivery_cost) - num(t.extra_cost);
    const detailTabs = [['overview', 'Обзор'], ['docs', 'Документы'], ['projects', 'Расчёты'], ['contract', 'Контракт'], ['shipments', 'Поставки'], ['comments', 'Комментарии'], ['history', 'История']];
    const activeTab = state.tenders.detailTab || 'overview';
    const panelVis = (tab) => activeTab === tab ? '' : 'hidden';
    const organizationOptions = `<option value="">Не выбрана</option>${state.tenders.organizations.map(o => `<option value="${esc(o.id)}" ${o.id === t.organization_id ? 'selected' : ''}>${esc(o.name)}</option>`).join('')}`;
    const statuses = state.tenders.statuses.map(s => `<option value="${esc(s)}" ${s === t.status ? 'selected' : ''}>${esc(s)}</option>`).join('');
    return `${pageHead('Карточка закупки', esc(t.number || 'Черновик без номера'), `<button class="btn secondary" data-action="tender-back">← Все закупки</button><button class="btn secondary" data-action="tender-eis">↗ Поиск в ЕИС</button><button class="btn secondary" data-action="tender-export-report">⇩ Отчёт Word</button><button class="btn primary" data-action="tender-analyze">✧ Анализ документов</button><button class="btn secondary qx-delete-tender" data-action="tender-delete" data-id="${esc(t.id)}">Удалить закупку</button>`)}<div class="tender-detail-tabs" role="tablist" aria-label="Разделы закупки">${detailTabs.map(([key, title]) => `<button role="tab" aria-selected="${activeTab === key}" class="tender-detail-tab ${activeTab === key ? 'active' : ''}" data-action="tender-detail-tab" data-view="${key}">${title}${key === 'docs' ? ` <span>${docs.length}</span>` : key === 'comments' ? ` <span>${comm.length}</span>` : ''}</button>`).join('')}</div><div class="tender-detail-grid ${activeTab === 'overview' ? '' : 'focus-layout'}">
 <div class="tender-primary">
  <div class="panel" data-tender-panel="overview" ${panelVis('overview')}><div class="section-title"><h2>Общие сведения</h2><span class="status ${tenderStatusColor(t.status)}">${esc(t.status)}</span></div><div class="form-grid two">${tenderField('number', t.number)}${tenderField('lot', t.lot)}${tenderField('title', t.title)}${tenderField('customer', t.customer)}${tenderField('organization_id', t.organization_id, 'select', organizationOptions)}${tenderField('law', t.law, 'select', `<option value="">Не указано</option>${['44-ФЗ', '223-ФЗ', 'Коммерческая'].map(s => `<option ${t.law === s ? 'selected' : ''}>${s}</option>`).join('')}`)}${tenderField('status', t.status, 'select', statuses)}${tenderField('nmck', t.nmck, 'number')}${tenderField('application_due_on', t.application_due_on, 'date')}${tenderField('application_due_time', t.application_due_time, 'time')}${t.is_quotation ? `${tenderField('results_on', t.results_on, 'date')}${tenderField('results_time', t.results_time, 'time')}` : `${tenderField('auction_on', t.auction_on, 'date')}${tenderField('auction_time', t.auction_time, 'time')}`}</div><label class="tender-check qx-quotation-check"><input type="checkbox" data-tender-field="is_quotation" ${t.is_quotation ? 'checked' : ''}> Запрос котировок — без аукциона и торгов</label>${t.is_quotation ? '<p class="subtitle">Для котировки указывайте срок подачи и дату подведения итогов. Время аукциона не требуется.</p>' : ''}</div>
  <div class="panel" data-tender-panel="overview" ${panelVis('overview')}><div class="section-title"><h2>Поиск в ЕИС</h2><span class="badge-count">По номеру извещения</span></div><p class="subtitle">Заполните пустые поля из извещения и скачайте доступные документы. Ваши значения сохраняются; расхождения будут показаны в отчёте.</p><div class="toolbar" style="margin-top:10px"><button class="btn primary" data-action="tender-eis-sync" ${state.eisImportBusy ? 'disabled' : ''}>${state.eisImportBusy ? 'Получаем данные…' : '↓ Получить данные и документы'}</button><button class="btn secondary small" data-action="tender-eis-lookup">Проверить по номеру</button><button class="btn secondary small" data-action="tender-eis">Открыть официальный поиск ↗</button></div>${eisSyncReport(t.number)}${state.eisImportError ? `<p class="warning" role="alert">${esc(state.eisImportError)}</p>` : ''}${state.tenderEisLookup ? `<div class="tender-rss-result" role="status"><p class="subtitle">${esc(state.tenderEisLookup.message)}</p>${(state.tenderEisLookup.matches || []).map(item => `<div class="activity-item"><div><b>${esc(item.title)}</b><small>${esc(item.description)}</small><small>Источник: RSS ЕИС · ${item.link_verified ? 'прямая ссылка' : 'ссылка на поиск'}</small></div><button class="btn secondary small" data-action="tender-eis-open-match" data-url="${esc(item.url)}">Проверить ↗</button></div>`).join('')}</div>` : ''}</div>
  <div class="panel" data-tender-panel="contract" ${panelVis('contract')}><div class="section-title"><h2>Контракт и сроки</h2><span class="status ${d.remaining < 0 && !t.is_delivered ? 'bad' : 'unknown'}">${esc(d.label || 'Срок не установлен')}</span></div><div class="form-grid two">${tenderField('contract_number', t.contract_number)}${tenderField('contract_price', t.contract_price, 'number')}${tenderField('signed_on', t.signed_on, 'date')}${tenderField('application_due_on', t.application_due_on, 'date')}${tenderField('application_due_time', t.application_due_time, 'time')}${t.is_quotation ? `${tenderField('results_on', t.results_on, 'date')}${tenderField('results_time', t.results_time, 'time')}` : `${tenderField('auction_on', t.auction_on, 'date')}${tenderField('auction_time', t.auction_time, 'time')}`}${tenderField('due_on', t.due_on, 'date')}${tenderField('due_days', t.due_days, 'number')}${tenderField('due_unit', t.due_unit, 'select', `<option value="calendar" ${t.due_unit !== 'work' ? 'selected' : ''}>Календарные</option><option value="work" ${t.due_unit === 'work' ? 'selected' : ''}>Рабочие (проверить праздники)</option>`)}${tenderField('supply_address', t.supply_address)}${tenderField('payment_terms', t.payment_terms)}${tenderField('warranty', t.warranty)}${tenderField('security', t.security)}${tenderField('payment_status', t.payment_status)}${tenderField('payment_due_on', t.payment_due_on, 'date')}</div><label class="tender-check"><input type="checkbox" data-tender-field="is_delivered" ${t.is_delivered ? 'checked' : ''}> Поставка подтверждена документами</label>${d.caution ? `<div class="warning">⚠ ${esc(d.caution)}</div>` : ''}<div class="note">Срок в рабочих днях ориентировочный, пока не выбран официальный производственный календарь. Просрочка — предварительный сигнал, не юридический вывод.</div></div>
  <div class="panel" data-tender-panel="docs" ${panelVis('docs')}><div class="section-title"><h2>Документы</h2><span class="badge-count">${docs.length}</span></div><button class="btn primary tender-upload" data-action="tender-upload-open">＋ Добавить документ</button><button class="btn secondary" data-action="tender-auto-contract">✧ Извлечь условия и заполнить контракт</button><p class="subtitle" style="margin:8px 0">Найденные в документах однозначные условия переносятся в пустые поля. Существующие данные не перезаписываются; спорные предложения требуют проверки.</p><button class="btn secondary tender-upload" data-action="tender-package-open">⇧ Загрузить пакет ZIP</button>
  <div class="qx-eis-discovery"><div><strong>Документы закупки из ЕИС</strong><p class="subtitle">Поиск по номеру ${esc(t.number || 'закупки')} на публичных страницах ЕИС. Без логина и обхода капчи. Сначала проверьте найденные ссылки, потом загрузите файлы в карточку.</p></div>
    <div class="toolbar"><button class="btn primary" data-action="tender-eis-discover">⌕ Найти документы</button><button class="btn secondary" data-action="tender-eis-discover-import">↓ Скачать найденные</button></div>
    ${state.tenderEisDiscovery && state.tenderEisDiscovery.notice_number === t.number ? `<div class="qx-eis-discovery-results" role="status"><b>${esc(state.tenderEisDiscovery.message || '')}</b><small>Просмотрено страниц: ${Number(state.tenderEisDiscovery.checked_pages || 0)} · найдено ссылок: ${Number(state.tenderEisDiscovery.found || 0)}</small>${(state.tenderEisDiscovery.documents || []).map(d => `<div class="qx-eis-file"><span>▤ ${esc(d.title)}</span><span title="Адрес найденного файла">${esc(d.url.split('?')[0].slice(-90))}</span></div>`).join('')}<a href="${esc(state.tenderEisDiscovery.search_url)}" target="_blank" rel="noopener noreferrer">Открыть официальный поиск ЕИС ↗</a></div>` : ''}</div><div class="toolbar" style="margin-top:12px"><textarea id="tender-eis-doc-url" aria-label="Ссылки на документы ЕИС" rows="3" placeholder="Вставьте прямые HTTPS-ссылки на PDF, Word, XML или ZIP с zakupki.gov.ru (каждая с новой строки)" style="min-width:280px;flex:1;resize:vertical"></textarea><button class="btn secondary" data-action="tender-eis-document-url">↓ Загрузить из ЕИС</button></div><p class="subtitle">Вставьте до 10 прямых ссылок на файлы (каждую с новой строки). Ссылки на страницу закупки не скачивают документацию; если файл закрыт или сайт требует вход, загрузите его вручную.</p>${tenderEisImportReport()}<div class="tender-doc-list">${docs.map(doc => `<div class="activity-item"><span class="activity-icon">▤</span><div><strong>${esc(doc.filename)}</strong><small>${esc(doc.created_at?.slice(0, 16) || '')}${/\.(doc|xls|rtf|rar|7z)$/i.test(doc.filename) ? ' · Оригинал сохранён; автоматический разбор недоступен' : ''}</small></div>${/\.(docx|pdf|xlsx|xlsm|txt|csv|md)$/i.test(doc.filename) ? `<button class="btn primary small" data-action="tender-use-tz" data-id="${esc(doc.id)}">В расчёт как ТЗ</button>` : ''}<button class="btn secondary small" data-action="tender-download" data-id="${esc(doc.id)}">Скачать</button><button class="btn secondary small" data-action="tender-delete-doc" data-id="${esc(doc.id)}" title="Удалить из закупки">Удалить</button></div>`).join('') || '<p class="subtitle">Пока нет файлов. Загрузите ТЗ, проект контракта и приложения.</p>'}</div></div>
  <div class="panel" data-tender-panel="comments" ${panelVis('comments')}><div class="section-title"><h2>Комментарии и поручения</h2><span class="badge-count">${comm.length}</span></div><textarea id="tender-comment" rows="3" placeholder="Например: ожидаем реестровую запись BIOS от завода…"></textarea><div class="toolbar" style="justify-content:flex-end;margin:8px 0 14px"><button class="btn primary" data-action="tender-comment">Сохранить комментарий</button></div>${comm.map(c => `<div class="tender-comment"><small>${esc(c.created_at)}</small><textarea rows="2" data-comment-edit="${esc(c.id)}" aria-label="Текст комментария">${esc(c.body)}</textarea><div class="toolbar" style="justify-content:flex-end;margin-top:6px"><button class="btn secondary small" data-action="tender-save-comment" data-id="${esc(c.id)}">Сохранить изменения</button><button class="btn secondary small" data-action="tender-delete-comment" data-id="${esc(c.id)}">Удалить</button></div></div>`).join('')}</div>
  <div class="panel" data-tender-panel="shipments" ${panelVis('shipments')}>
    <div class="section-title"><div><h2>План поставок</h2><p class="subtitle">Разбей поставку на партии, укажи количество и крайние даты. Статусы можно отмечать по мере исполнения.</p></div><span class="badge-count">${ship.length} этапов</span></div>
    <div class="qx-shipment-summary"><div>Всего запланировано <b>${fmt(ship.reduce((sum, x) => sum + Number(x.quantity || 0), 0))} шт.</b></div><div>Принято этапов <b>${ship.filter(x => x.accepted_on).length} / ${ship.length}</b></div></div>
    <div class="qx-shipment-form"><h3>＋ Новый этап поставки</h3><div class="form-grid three">${field('Название партии', '<input id="ship-name" placeholder="Например: Партия № 1">')}${field('Количество, шт.', '<input id="ship-qty" type="number" min="1" step="1" placeholder="Например: 25">')}${field('Поставить до', '<input id="ship-due" type="date">')}</div><button class="btn primary" data-action="tender-add-shipment">＋ Добавить этап</button></div>
    <div class="qx-shipment-list">${ship.map((x, i) => `<div class="qx-shipment-item"><div class="qx-shipment-top"><span class="qx-shipment-step">${i + 1}</span><div class="qx-shipment-title"><strong>${esc(x.name || 'Этап поставки')}</strong><small>${fmt(x.quantity)} шт. · ${x.due_on ? 'до ' + esc(tenderDate(x.due_on)) : 'крайняя дата не указана'}</small></div><span class="qx-shipment-state ${x.accepted_on ? 'done' : ''}">${x.accepted_on ? '✓ Принято' : x.delivered_on ? 'Доставлено' : x.sent_on ? 'Отгружено' : 'Ожидает отгрузки'}</span><button class="btn secondary small qx-shipment-remove" data-action="tender-delete-stage" data-id="${esc(x.id)}" title="Удалить этот этап">✕ Удалить</button></div><div class="qx-shipment-buttons">${x.sent_on ? '' : `<button class="btn secondary small" data-action="tender-stage" data-id="${esc(x.id)}" data-stage="sent_on">Отметить: отгружено</button>`}${x.delivered_on ? '' : `<button class="btn secondary small" data-action="tender-stage" data-id="${esc(x.id)}" data-stage="delivered_on">Отметить: доставлено</button>`}${x.accepted_on ? '' : `<button class="btn secondary small" data-action="tender-stage" data-id="${esc(x.id)}" data-stage="accepted_on">✓ Принято заказчиком</button>`}</div></div>`).join('') || '<p class="subtitle">Этапов ещё нет. Добавь первую партию, чтобы контролировать её срок и статус.</p>'}</div>
  </div>
  <details class="panel" data-tender-panel="history" ${panelVis('history')} open><summary><strong>История изменений (${ev.length})</strong></summary>${ev.map(x => `<p class="tender-history"><small>${esc(x.created_at)}</small> ${esc(x.label)}</p>`).join('') || '<p class="subtitle">История пока пуста.</p>'}</details>
 </div><div class="tender-secondary">
  <div class="panel" data-tender-panel="overview" ${panelVis('overview')}><div class="section-title"><h2>Финансы</h2></div><div class="form-grid two">${tenderField('purchase_cost', t.purchase_cost, 'number')}${tenderField('delivery_cost', t.delivery_cost, 'number')}${tenderField('extra_cost', t.extra_cost, 'number')}${tenderField('bid_price', t.bid_price, 'number')}${tenderField('paid_amount', t.paid_amount, 'number')}</div><div class="tender-money"><span>Плановая прибыль от контракта</span><b class="${profit < 0 ? 'danger-text' : ''}">${!num(t.contract_price) ? 'Нет цены контракта' : num(t.purchase_cost) <= 0 ? 'Нет подтверждённой себестоимости' : rub(profit)}</b></div><div class="note">Без учёта налогообложения. Себестоимость синхронизируется из привязанных расчётов QX.</div></div>
  <div class="panel" data-tender-panel="docs" ${panelVis('docs')}><div class="section-title"><h2>Краткий анализ документов</h2><small>До 7 строк</small></div>${state.tenders.analysis ? `<div class="tender-summary">${(state.tenders.analysis.summary || []).map(x => `<div><span>${esc(x.label)}</span><b>${esc(x.value)}</b>${(x.evidence || []).map(v => `<small>${esc(v.file)} · ${esc(v.location)}</small>`).join('')}</div>`).join('')}</div>${(state.tenders.analysis.suggested_fields || []).length ? `<div class="tender-proposals"><h3>Найденные условия для карточки</h3><p class="subtitle">Подставим только выбранные пустые поля. Ничего не меняем без подтверждения.</p>${state.tenders.analysis.suggested_fields.map(p => { const existing = t[p.field]; const filled = existing !== null && existing !== undefined && existing !== '' && (p.field !== 'due_days' || Number(existing) > 0) && (p.field !== 'due_unit' || Number(t.due_days) > 0); return `<label class="tender-proposal"><input type="checkbox" data-analysis-field="${esc(p.field)}" ${filled ? 'disabled' : ''}><div><b>${esc(p.label)}: ${esc(String(p.value))}</b><small>${esc(p.evidence.file)} · ${esc(p.evidence.location)}${filled ? ' · Уже заполнено' : ''}</small></div></label>`; }).join('')}<button class="btn primary small" data-action="tender-apply-analysis">Применить выбранные значения</button></div>` : ''}<details><summary>Фрагменты требований и источники</summary>${(state.tenders.analysis.bios?.evidence || []).map(x => `<blockquote>${esc(x.text)}<small>${esc(x.file)} — ${esc(x.location)}</small></blockquote>`).join('') || '<p>Фрагменты не найдены.</p>'}</details><p class="subtitle">${esc(state.tenders.analysis.disclaimer || '')}</p>` : '<div class="tender-analysis-empty">Загрузите документы и нажмите «Анализ документов». Будут показаны только сведения, подтверждённые текстом файлов.</div>'}</div>
  <div class="panel" data-tender-panel="docs" ${panelVis('docs')}>
    <div class="section-title"><h2>QX AI · Работа с документами</h2></div>
    <p class="subtitle">Поиск точных цитат работает без нейросети и интернета. При желании можно выбрать Ollama или GGUF — тогда модель сформирует черновой ответ с источниками.</p>
    <div class="toolbar"><button class="btn secondary small" data-action="tender-ai-status">Проверить локальные модели</button><button class="btn secondary small" data-action="tender-ai-model-folder">Папка моделей GGUF</button><span class="subtitle">${esc(state.tenderAiStatus?.message || 'Локальная проверка доступна')}</span></div>
    ${state.tenderAiStatus?.gguf_model_directory ? `<p class="subtitle">Папка GGUF: ${esc(state.tenderAiStatus.gguf_model_directory)}</p>` : ''}
    <select id="tender-llm-model" aria-label="Режим анализа документов"><option value="offline-search" ${state.tenderAiModel === 'offline-search' ? 'selected' : ''}>Цитаты и источники — без модели</option>${(state.tenderAiStatus?.models || []).map(m => `<option value="${esc(m)}" ${m === state.tenderAiModel ? 'selected' : ''}>${esc(m)}</option>`).join('')}</select>
    <textarea id="tender-llm-question" rows="3" placeholder="Например: есть ли требование к реестровому BIOS?"></textarea>
    <button class="btn secondary" data-action="tender-local-ai" style="margin-top:10px">Найти ответ в документах</button>
    ${state.tenderLocalAnswer ? `<div class="readonly" style="margin-top:14px;white-space:pre-line">${esc(state.tenderLocalAnswer.text)}</div><p class="subtitle">${esc(state.tenderLocalAnswer.warning)}</p>${(state.tenderLocalAnswer.sources || []).length ? `<details><summary>Источники (${state.tenderLocalAnswer.sources.length})</summary>${state.tenderLocalAnswer.sources.map(s => `<small style="display:block">${esc(s.file)} · ${esc(s.location)}</small>`).join('')}</details>` : ''}` : ''}
    <details style="margin-top:12px"><summary>Установить проверенную локальную модель Qwen (~1,12 ГБ)</summary>
      <p class="subtitle">Модель Qwen2.5 1.5B Instruct Q4_K_M, Apache-2.0. Скачивается по вашему нажатию с Hugging Face. QX проверит размер и SHA-256, хранит модель в пользовательской папке; документация закупок никому не отправляется. Необходим движок GGUF в установленной версии QX.</p>
      ${state.tenderAiInstall ? `<div class="note" id="qx-model-download-progress">${esc(qxModelInstallText(state.tenderAiInstall))}</div>` : `<div class="note" id="qx-model-download-progress">Скачивание не запущено</div>`}
      <div class="toolbar"><button class="btn secondary small" data-action="tender-ai-model-download" ${state.tenderAiStatus?.gguf_runtime_ready === false ? 'disabled title="В этой сборке отсутствует llama-cpp-python"' : ''}>Скачать Qwen (1,12 ГБ)</button><button class="btn secondary small" data-action="tender-ai-model-cancel">Остановить загрузку</button></div>
      <p class="subtitle"><a href="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF" target="_blank" rel="noopener noreferrer">Официальная карточка модели и лицензия ↗</a></p>
    </details>
  </div>
  <div class="panel" data-tender-panel="projects" ${panelVis('projects')}><div class="section-title"><h2>Связанные расчёты QX</h2><span class="badge-count">${(t.projects || []).length}</span></div>${(t.projects || []).map(p => `<div class="activity-item"><div><b>${esc(p.project_name || 'Расчёт')}</b><small>${esc(p.source_name || 'Без файла')} · ${rub(p.cost)}</small></div></div>`).join('') || '<p class="subtitle">Пока нет связанных расчётов.</p>'}<div class="toolbar" style="margin-top:16px"><button class="btn primary" data-action="tender-import-project">⇧ Загрузить файл .qxproj</button><button class="btn secondary" data-action="tender-link-current">↳ Привязать открытый расчёт</button></div><p class="subtitle">Можно загрузить ранее сохранённый проект QX напрямую. Он не заменит текущий расчёт, а его стоимость будет добавлена к этой закупке.</p></div>
 </div></div><div id="tender-save-feedback" class="tender-save-feedback">Автосохранение включено</div>`;
}
function tenderCalendarView() {
    const now = new Date(), base = new Date(now.getFullYear(), now.getMonth() + state.tenders.monthDelta, 1);
    const y = base.getFullYear(), m = base.getMonth(), days = new Date(y, m + 1, 0).getDate(), first = (new Date(y, m, 1).getDay() + 6) % 7;
    const month = base.toLocaleString('ru-RU', { month: 'long', year: 'numeric' });
    const types = [['application_due_on', 'Подача заявок', 'application'], ['auction_on', 'Аукцион', 'auction'], ['results_on', 'Итоги котировки', 'results'], ['calculated_due_on', 'Поставка', 'delivery'], ['payment_due_on', 'Оплата', 'payment']];
    const active = state.tenders.calendarTypes || [...types.map(x => x[2]), 'note'];
    const events = {};
    for (const t of (state.tenders.items || []))
        for (const [key, label, type] of types) {
            if (!active.includes(type) || !t[key] || (type === 'auction' && t.is_quotation) || (type === 'results' && !t.is_quotation))
                continue;
            const iso = String(t[key]).slice(0, 10);
            if (!/^\d{4}-\d{2}-\d{2}$/.test(iso))
                continue;
            (events[iso] ??= []).push({ id: t.id, type, label, number: t.number || 'Без номера', title: t.title || 'Закупка', time: type === 'application' ? t.application_due_time || '' : type === 'auction' ? t.auction_time || '' : type === 'results' ? t.results_time || '' : '' });
        }
    // Deadlined quick notes are first-class calendar entries: their database remains
    // independent from procurement projects, and completion updates presentation.
    if (active.includes('note')) for (const note of (state.tenders.calendarNotes || [])) {
        const iso = String(note.due_on || '');
        if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) continue;
        (events[iso] ??= []).push({ id: note.id, type: 'note', label: note.completed ? '✓ Задача выполнена' : 'Задача', number: note.source || 'Быстрые заметки', title: notePreview(note), time: '', completed: !!note.completed });
    }
    for (const dayEvents of Object.values(events)) dayEvents.sort((a,b) => Number(!!a.completed) - Number(!!b.completed));
    const focus = state.tenders.calendarFocus || new Date().toLocaleDateString('sv-SE');
    const tiles = Array.from({ length: Math.ceil((first + days) / 7) * 7 }, (_, i) => {
        const day = i - first + 1;
        if (day <= 0 || day > days)
            return '<div class="tender-calendar-day outside"></div>';
        const iso = `${y}-${String(m + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const es = events[iso] || [], selected = focus === iso, today = new Date().toLocaleDateString('sv-SE') === iso;
        return `<div class="tender-calendar-day ${today ? 'today' : ''} ${selected ? 'selected' : ''}"><button class="qx-calendar-day-number" data-action="tender-calendar-day" data-date="${iso}" aria-label="Показать события ${iso}">${day}</button><div class="qx-day-events">${es.slice(0, 3).map(e => `<button class="qx-calendar-pill kind-${e.type} ${e.completed ? 'completed' : ''}" data-action="${e.type === 'note' ? 'tender-calendar-open-note' : 'tender-open'}" data-id="${esc(e.id)}" title="${esc(e.label + ' · ' + e.number + ' · ' + e.title)}">${esc(e.type === 'note' ? '✎ '+e.title.slice(0, 39) : (e.time ? e.time + ' · ' + e.label : e.label)+' · '+e.number)}</button>`).join('')}${es.length > 3 ? `<button class="qx-more-events" data-action="tender-calendar-day" data-date="${iso}">Ещё ${es.length - 3}</button>` : ''}</div></div>`;
    });
    const agenda = (events[focus] || []);
    return `<div class="panel tender-calendar"><div class="section-title"><h2>Календарь · ${esc(month)}</h2><div class="toolbar"><button class="btn secondary small" data-action="tender-prev-month" aria-label="Предыдущий месяц">‹</button><button class="btn secondary small" data-action="tender-current-month">Сегодня</button><button class="btn secondary small" data-action="tender-next-month" aria-label="Следующий месяц">›</button></div></div>
 <div class="qx-calendar-filters">${[...types, ['due_on', 'Мои задачи', 'note']].map(([, label, type]) => `<button class="qx-calendar-filter ${active.includes(type) ? 'active' : ''} kind-${type}" data-action="tender-calendar-filter" data-type="${type}">${esc(label)}</button>`).join('')}</div>
 <div class="qx-calendar-layout"><div class="tender-calendar-scroll"><div class="tender-calendar-grid">${['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map(x => `<div class="tender-calendar-weekday">${x}</div>`).join('')}${tiles.join('')}</div></div>
 <aside class="qx-calendar-agenda"><h3>${esc(tenderDate(focus))}</h3><p class="subtitle">${agenda.length} контрольных событий</p>${agenda.map(e => `<button class="qx-agenda-item kind-${e.type} ${e.completed ? 'completed' : ''}" data-action="${e.type === 'note' ? 'tender-calendar-open-note' : 'tender-open'}" data-id="${esc(e.id)}"><strong>${esc(e.label)}${e.time ? ' · ' + esc(e.time) : ''}</strong><span>${esc(e.type === 'note' ? e.title : e.number)}</span><small>${esc(e.type === 'note' ? e.number : e.title)}</small></button>`).join('') || '<div class="qx-no-events">В этот день событий нет. Выберите другую дату.</div>'}</aside></div></div>`;
}
function tenderContractsPage() {
    const entries = (state.tenders.items || []).filter(t => ['Выиграли', 'Ожидание подписания', 'Контракт подписан', 'Заказ оборудования', 'Производство', 'Комплектация', 'Готово к отправке', 'Отгружено', 'Доставлено', 'Приёмка', 'Контракт исполнен'].includes(t.status));
    const today = new Date();
    today.setHours(12, 0, 0, 0);
    const deadlines = entries.map(t => { let left = null; if (t.calculated_due_on) {
        const d = new Date(t.calculated_due_on + 'T12:00:00');
        left = Math.round((d.getTime() - today.getTime()) / 86400000);
    } return { ...t, left }; });
    return `${pageHead('Контракты и поставки', 'Подписание, сроки, отгрузка и исполнение — в одной таблице.', `<button class="btn secondary" data-action="tender-go-registry">Открыть реестр →</button>`)}<div class="panel"><div class="section-title"><h2>Контракты под контролем</h2><span class="badge-count">${entries.length}</span></div><div class="table-wrap"><table class="table"><thead><tr><th>Закупка</th><th>Статус</th><th>Цена контракта</th><th>Крайний срок подачи</th><th>Срок поставки</th><th>Контроль</th><th></th></tr></thead><tbody>${deadlines.map(t => `<tr><td class="qx-tender-ident"><b>${esc(t.number || 'Без номера')}</b><small>${esc(t.title || 'Без названия')}</small><small>${t.is_quotation ? 'Котировка · ' : ''}Подача до: ${esc(t.application_due_on ? tenderDate(t.application_due_on) + (t.application_due_time ? ' ' + t.application_due_time : '') : 'не указана')}</small></td><td><span class="status ${tenderStatusColor(t.status)}">${esc(t.status)}</span></td><td class="number">${num(t.contract_price) > 0 ? rub(t.contract_price) : 'Не указана'}</td><td>${esc(t.application_due_on ? tenderDate(t.application_due_on) + (t.application_due_time ? ' ' + t.application_due_time : '') : 'Не установлен')}</td><td>${esc(t.calculated_due_on ? tenderDate(t.calculated_due_on) : 'Не установлен')}</td><td>${t.left === null ? '<span class="status unknown">Нужна дата</span>' : t.is_delivered ? '<span class="status ok">Поставка подтверждена</span>' : t.left < 0 ? `<span class="status bad">Возможная просрочка: ${-t.left} дн.</span>` : t.left <= 7 ? `<span class="status unknown">Осталось ${t.left} дн.</span>` : `Осталось ${t.left} дн.`}</td><td><button class="btn secondary small" data-action="tender-open" data-id="${esc(t.id)}">Открыть</button></td></tr>`).join('')}</tbody></table></div>${entries.length ? '' : empty('Пока нет контрактов', 'Укажите победу, подписание или дату заключения в карточке закупки.')}</div><div class="note" style="margin-top:15px">Даты ориентировочные, пока не проверены условия каждого контракта и переносы рабочих дней. Статусы победы не устанавливаются автоматически.</div>`;
}
function tenderAnalyticsPage() {
    const list = state.tenders.items || [];
    const priced = list.filter(t => num(t.contract_price) > 0);
    const signed = priced.filter(t => t.signed_on || t.status === 'Контракт подписан' || t.status === 'Контракт исполнен');
    const total = priced.reduce((a, t) => a + num(t.contract_price), 0);
    const complete = priced.filter(t => num(t.purchase_cost) > 0);
    const profit = complete.reduce((a, t) => a + num(t.contract_price) - num(t.purchase_cost) - num(t.delivery_cost) - num(t.extra_cost), 0);
    const paid = list.reduce((a, t) => a + num(t.paid_amount), 0);
    const byOrg = new Map();
    for (const t of list) {
        const key = t.organization_name || 'Без организации';
        const row = byOrg.get(key) || { count: 0, price: 0, cost: 0 };
        row.count++;
        row.price += num(t.contract_price);
        row.cost += num(t.purchase_cost) + num(t.delivery_cost) + num(t.extra_cost);
        byOrg.set(key, row);
    }
    return `${pageHead('Аналитика тендеров', 'Краткие показатели из фактических записей; без предположений о неуказанных суммах.', `<button class="btn secondary" data-action="tender-backup">⇩ Сохранить базу</button>`)}<div class="tender-stats tender-analytics-stats"><div><span>Закупок</span><b>${list.length}</b></div><div><span>С ценой контракта</span><b>${priced.length}</b></div><div><span>С датой подписания или статусом</span><b>${signed.length}</b></div><div><span>Стоимость контрактов с ценой</span><b>${rub(total)}</b></div><div><span>Плановый результат (${complete.length} с просчётом)*</span><b class="${profit < 0 ? 'danger-text' : ''}">${rub(profit)}</b></div><div><span>Зафиксировано оплат</span><b>${rub(paid)}</b></div></div><div class="panel"><div class="section-title"><h2>Разбивка по организациям</h2></div><div class="table-wrap"><table class="table"><thead><tr><th>Организация</th><th>Закупок</th><th>Цена контрактов</th><th>Учтённые затраты</th></tr></thead><tbody>${[...byOrg.entries()].map(([name, v]) => `<tr><td>${esc(name)}</td><td>${v.count}</td><td>${rub(v.price)}</td><td>${rub(v.cost)}</td></tr>`).join('')}</tbody></table></div>${list.length ? '' : empty('Нет данных для аналитики', 'Добавьте закупку или привяжите расчёт.')}</div><div class="note" style="margin-top:15px">* Плановый результат считается только по закупкам с указанной ценой контракта: цена минус оборудование, логистика и прочие расходы. Без налогов, неустоек и неподтверждённых платежей. Контракты с нулевой или отсутствующей себестоимостью исключены из показателя прибыли. Для неподписанных контрактов это сценарий, а не фактическая прибыль.</div>`;
}
function tenderOrganizationsPage() {
    const orgs = state.tenders.organizations || [], list = state.tenders.items || [];
    return `${pageHead('Организации', 'Юридические лица и связанные закупки. Изменения сохраняются в базе.', `<button class="btn secondary" data-action="tender-backup">⇩ Резервная копия</button>`)}<div class="grid"><div class="col-8 panel"><div class="section-title"><h2>Организации</h2><span class="badge-count">${orgs.length}</span></div>${orgs.map(o => `<div class="tender-org-item" data-org-editor="${esc(o.id)}"><div class="tender-org-fields"><label class="field">Название организации<input data-org-name value="${esc(o.name)}" aria-label="Название организации"></label><label class="field">ИНН<input data-org-inn value="${esc(o.inn || '')}" aria-label="ИНН"></label><small>Связанных закупок: ${list.filter(t => t.organization_id === o.id).length}</small></div><div class="tender-org-actions"><button class="btn secondary small" data-action="tender-org-save" data-id="${esc(o.id)}">Сохранить</button><button class="btn secondary small" data-action="tender-org-filter" data-id="${esc(o.id)}">Закупки →</button></div></div>`).join('') || empty('Организации пока не добавлены', 'Создайте первую организацию в форме ниже.')}</div><div class="col-4 panel"><h2>Добавить организацию</h2><p class="subtitle">Для удобного разделения контрактов по юридическим лицам.</p><div class="field" style="margin-top:16px"><label>Название</label><input id="new-org-name" placeholder="ООО «Компания»"></div><div class="field" style="margin-top:12px"><label>ИНН</label><input id="new-org-inn" inputmode="numeric" placeholder="10 или 12 цифр"></div><button class="btn primary" style="margin-top:16px;width:100%;justify-content:center" data-action="tender-add-org">＋ Добавить</button><p class="subtitle" style="margin-top:16px">После добавления выберите организацию в карточке закупки. Ранее сохранённые расчёты не меняются автоматически.</p></div></div>`;
}
function tenderRemindersPage() {
    const all = state.tenders.reminders || [], settings = state.tenders.reminderSettings || {};
    const risks = all.filter(a => a.days < 0), week = all.filter(a => a.days >= 0 && a.days <= 7);
    const status = a => a.days < 0 ? 'bad' : a.days <= 7 ? 'unknown' : 'ok';
    const badge = a => a.days < 0 ? 'Просрочено' : a.days === 0 ? 'Сегодня' : a.days === 1 ? 'Завтра' : a.days <= 7 ? 'Скоро' : 'Предстоящий срок';
    return `${pageHead('Сроки и напоминания', 'Закупки, поставки и поручения из быстрых заметок.', `<button class="btn secondary" data-action="tender-refresh-reminders">↻ Обновить</button>`)}
  <div class="tender-reminder-stats"><div><span>Требуют внимания</span><strong>${risks.length}</strong></div><div><span>В ближайшие 7 дней</span><strong>${week.length}</strong></div><div><span>Всего контрольных событий</span><strong>${all.length}</strong></div></div>
  <div class="panel tender-reminder-config"><div><h2>Уведомления Windows</h2><p class="subtitle">Показываются только при открытом QX. Без уведомлений по закрытым или отменённым закупкам.</p></div><div class="tender-reminder-controls"><label class="tender-notify-toggle"><input type="checkbox" data-tender-notifications ${settings.enabled ? 'checked' : ''}> Включить</label><label class="field">Предупреждать за <select data-tender-lead>${[1, 3, 7, 14, 30].map(d => `<option value="${d}" ${Number(settings.advance_days) === d ? 'selected' : ''}>${d} ${d === 1 ? 'день' : 'дн.'}</option>`).join('')}</select></label><button class="btn secondary small" data-action="tender-test-reminders">Проверить напоминания</button></div></div>
  <div class="panel"><div class="section-title"><h2>Контрольные даты</h2><span class="badge-count">${all.length}</span></div><div class="table-wrap"><table class="table tender-reminder-table"><thead><tr><th>Дата</th><th>Закупка / событие</th><th>Состояние</th><th></th></tr></thead><tbody>${all.map(a => `<tr><td><b>${esc(tenderDate(a.due_on))}${a.due_time ? ' · ' + esc(a.due_time) : ''}</b><small>${a.days < 0 ? 'Прошедший срок' : 'Контрольная дата'}</small></td><td><b>${esc(a.number || a.title)}</b><small>${esc(a.event)}</small>${a.caution ? `<small class="danger-text">${esc(a.caution)}</small>` : ''}</td><td><span class="status ${status(a)}">${badge(a)}</span><small>${esc(a.message)}</small></td><td><button class="btn secondary small" data-action="${a.type === 'note' ? 'tender-calendar-open-note' : 'tender-open'}" data-id="${esc(a.type === 'note' ? a.note_id : a.tender_id)}">${a.type === 'note' ? 'Заметка' : 'Открыть'}</button></td></tr>`).join('')}</tbody></table></div>${all.length ? '' : empty('Нет ближайших сроков', 'Проверьте даты в карточках закупок и контрактах.')}</div>
  <div class="note" style="margin-top:14px">Время аукциона указывайте по часовому поясу компьютера. При включённых уведомлениях QX напомнит за 60 и за 15 минут, пока программа открыта. «Возможная просрочка» не означает установленное нарушение контракта. Учитывайте документы поставки, приёмку, изменения условий и производственный календарь РФ. Уведомления не отправляются, когда программа закрыта.</div>`;
}
function tenderCalendarPage() { return `${pageHead('Календарь и задачи', 'Закупки, котировки, поставки и дела из быстрых заметок — в одном месте.', `<button class="btn secondary" data-action="tender-current-month">Сегодня</button>`)}${tenderCalendarView()}<div class="note" style="margin-top:14px">Задачи берутся из быстрых заметок и открываются прямо из календаря. Выполненные отмечены галочкой. Календарь формируется по сохранённым датам закупок и задач. Для рабочих дней без утверждённого производственного календаря сроки требуют подтверждения.</div>`; }
function tendersPage() { if (state.tenders.selected)
    return tenderDetail(); switch (state.tenders.view) {
    case 'calendar': return tenderCalendarPage();
    case 'contracts': return tenderContractsPage();
    case 'analytics': return tenderAnalyticsPage();
    case 'reminders': return tenderRemindersPage();
    case 'organizations': return tenderOrganizationsPage();
    default: return tenderList();
} }
function filterTenderRows() { const q = state.tenders.filter.toLocaleLowerCase('ru').trim(); let shown = 0; document.querySelectorAll('[data-tender-row]').forEach(r => { r.hidden = !(String(r.dataset.query || '').toLocaleLowerCase('ru').includes(q) && (!state.tenders.statusFilter || r.dataset.status === state.tenders.statusFilter) && (!state.tenders.orgFilter || r.dataset.org === state.tenders.orgFilter)); if (!r.hidden)
    shown++; }); const msg = $('#tender-no-matches'); if (msg)
    msg.hidden = shown > 0; }
let qxModelPolling = false;
function qxModelInstallText(info) {
    if (!info)
        return 'Загрузка не запущена';
    const size = Number(info.bytes_total || 1), done = Number(info.downloaded || 0);
    const pct = Math.min(100, Math.floor(100 * done / size));
    const states = { idle: 'Не запускалась', downloading: 'Скачивание', verifying: 'Проверка SHA-256 на диске', cancelled: 'Остановлено — можно продолжить', failed: 'Ошибка загрузки', installed: 'Модель скачана и проверена SHA-256' };
    return (states[info.state] || info.state) + ' · ' + pct + '%' + (info.error ? ' · ' + info.error : '') + (info.runtime_ready ? '' : ' · GGUF-движок не установлен');
}
async function qxPollModelInstall() {
    if (qxModelPolling)
        return;
    qxModelPolling = true;
    try {
        for (let i = 0; i < 10000; i++) {
            await new Promise(resolve => setTimeout(resolve, 1000));
            try {
                const info = await api('local-ai/model-install', undefined, 'GET');
                state.tenderAiInstall = info;
                const node = $('#qx-model-download-progress');
                if (node)
                    node.textContent = qxModelInstallText(info);
                if (info.state !== 'downloading' && info.state !== 'verifying') {
                    await refreshTenderAiStatus();
                    if (info.state === 'installed')
                        toast('Модель скачана и проверена. Можно выбрать её в списке QX AI.');
                    else if (info.state === 'failed')
                        toast('Загрузка модели: ' + info.error, true);
                    return;
                }
            }
            catch (e) {
                toast('Не удалось проверить загрузку модели: ' + e.message, true);
                return;
            }
        }
    }
    finally {
        qxModelPolling = false;
    }
}
async function refreshTenderAiStatus() {
    try {
        const [aiStatus, installStatus] = await Promise.all([api('local-ai/status', undefined, 'GET'), api('local-ai/model-install', undefined, 'GET')]);
        state.tenderAiStatus = aiStatus;
        state.tenderAiInstall = installStatus;
        const installedModels = aiStatus.models || [];
        if (installedModels.includes('qx-lite:1.5b') && (!state.tzAiModel || !installedModels.includes(state.tzAiModel)))
            state.tzAiModel='qx-lite:1.5b';
        if ((!state.tenderAiModel || !installedModels.includes(state.tenderAiModel)) && installedModels.includes('qx-lite:1.5b'))
            state.tenderAiModel = 'qx-lite:1.5b';
        if (state.tenderAiModel !== 'offline-search' && installedModels.length && !installedModels.includes(state.tenderAiModel))
            state.tenderAiModel = 'offline-search';
        if (state.tenders.detailTab === 'docs' || state.tab === 'tz')
            render();
        if (['downloading', 'verifying'].includes(installStatus.state))
            void qxPollModelInstall();
    }
    catch (e) {
        state.tenderAiStatus = { available: false, models: [], message: 'Не удалось проверить Ollama: ' + e.message };
        if (state.tenders.detailTab === 'docs' || state.tab === 'tz')
            render();
    }
}
async function handleTenderAction(el) {
    const act = el.dataset.action, id = state.tenders.selected;
    try {
        if (act === 'tender-detail-tab') {
            state.tenders.detailTab = el.dataset.view || 'overview';
            render(true);
            if (state.tenders.detailTab === 'docs' && !state.tenderAiStatus)
                await refreshTenderAiStatus();
            return;
        }
        if (act === 'tender-upload-open') {
            const file = await openNativeFile('tender');
            if (file)
                await tenderUpload(file);
            return;
        }
        if (act === 'tender-package-open') {
            const file = await openNativeFile('tender_package');
            if (file)
                await tenderImportPackage(file);
            return;
        }
        if (act === 'tender-refresh-reminders') {
            await loadTenders();
            return;
        }
        if (act === 'tender-test-reminders') {
            const r = await api('tenders/reminders/check', {});
            toast(!r.enabled ? 'Сначала включите уведомления' : r.available ? `Отправлено уведомлений: ${r.sent}` : 'Windows-уведомления доступны только на Windows');
            return;
        }
        if (act === 'tender-calendar') {
            gotoTender(state.tenders.view === 'calendar' ? 'registry' : 'calendar');
            return;
        }
        if (act === 'tender-calendar-open-note') {
            const noteId = el.dataset.id;
            await loadNotes();
            if (!notesState.items.some(n => n.id === noteId)) return toast('Заметка уже удалена', true);
            notesState.selected = noteId;
            notesState.showDone = true;
            state.tab = 'notes';
            render(true);
            return;
        }
        if (act === 'tender-calendar-day') {
            state.tenders.calendarFocus = el.dataset.date;
            render();
            return;
        }
        if (act === 'tender-calendar-filter') {
            const type = el.dataset.type;
            const list = state.tenders.calendarTypes || ['application', 'auction', 'results', 'delivery', 'payment', 'note'];
            state.tenders.calendarTypes = list.includes(type) ? list.filter(x => x !== type) : [...list, type];
            render();
            return;
        }
        if (act === 'tender-prev-month') {
            state.tenders.monthDelta--;
            render();
            return;
        }
        if (act === 'tender-next-month') {
            state.tenders.monthDelta++;
            render();
            return;
        }
        if (act === 'tender-current-month') {
            state.tenders.monthDelta = 0;
            render();
            return;
        }
        if (act === 'tender-stage') {
            await api('tenders/' + id + '/shipments/' + el.dataset.id, { [el.dataset.stage]: new Date().toISOString().slice(0, 10) }, 'PATCH');
            await openTender(id);
            return;
        }
        if (act === 'tender-backup') {
            await download('tenders/backup', undefined, 'QX_Tenders_Backup.zip');
            return;
        }
        if (act === 'tender-restore') {
            const f = await openNativeFile('tender_backup');
            if (f)
                await tenderRestoreInspect(f);
            return;
        }
        if (act === 'tender-restore-confirm') {
            const f = state.tenderRestoreFile;
            if (!f) {
                toast('Сначала выберите резервную копию', true);
                return;
            }
            await busy(async () => {
                const r = await api('tenders/backup/restore', f, 'POST', { 'X-QX-Confirm-Restore': 'REPLACE_EXISTING_TENDERS' });
                state.tenderRestoreFile = null;
                state.tenderRestorePreview = null;
                state.modal = '';
                state.tenders.selected = null;
                state.tenders.current = null;
                state.tenders.view = 'registry';
                await loadTenders();
                render(true);
                toast('Закупки восстановлены. Текущая база сохранена в защитной копии. Для надёжности перезапустите QX.');
            });
            return;
        }
        if (act === 'tender-new') {
            const r = await api('tenders', { title: 'Новая закупка', status: 'Черновик' });
            await loadTenders();
            await openTender(r.tender.id);
            return;
        }
        if (act === 'tender-open') {
            state.tab = 'tenders';
            await openTender(el.dataset.id);
            return;
        }
        if (act === 'tender-delete') {
            const item = (state.tenders.items || []).find(t => t.id === el.dataset.id) || (state.tenders.current?.id === el.dataset.id ? state.tenders.current : null);
            if (!item)
                return toast('Не удалось найти закупку. Обновите реестр.', true);
            state.tenders.deleteCandidate = item;
            state.modal = 'tender-delete';
            render();
            return;
        }
        if (act === 'tender-delete-confirm') {
            const item = state.tenders.deleteCandidate;
            if (state.modal !== 'tender-delete' || !item || item.id !== el.dataset.id)
                return;
            await busy(async () => {
                await flushTenderFields(item.id);
                await api('tenders/' + encodeURIComponent(item.id), undefined, 'DELETE');
                discardTenderFieldEdits(item.id);
                if (state.tenders.selected === item.id) {
                    state.tenders.selected = null;
                    state.tenders.current = null;
                    state.tenders.analysis = null;
                }
                if (state.tenderId === item.id)
                    state.tenderId = '';
                state.tenders.deleteCandidate = null;
                state.tenders.view = 'registry';
                state.modal = '';
                await loadTenders();
                toast('Закупка удалена из реестра');
            });
            return;
        }
        if (act === 'tender-back') {
            state.tenders.selected = null;
            state.tenders.current = null;
            state.tenders.analysis = null;
            await loadTenders();
            return;
        }
        if (act === 'tender-org-filter') {
            state.tenders.orgFilter = el.dataset.id || '';
            gotoTender('registry');
            return;
        }
        if (act === 'tender-add-org') {
            const name = $('#new-org-name')?.value?.trim();
            const inn = $('#new-org-inn')?.value?.trim() || '';
            if (!name) {
                toast('Введите название организации', true);
                return;
            }
            await api('tenders/organizations', { name, inn });
            await loadTenders();
            toast('Организация добавлена');
            return;
        }
        if (act === 'tender-org-save') {
            const card = el.closest('[data-org-editor]');
            const name = card?.querySelector('[data-org-name]')?.value.trim();
            const inn = card?.querySelector('[data-org-inn]')?.value.trim() || '';
            if (!name) {
                toast('Введите название организации', true);
                return;
            }
            await api('tenders/organizations/' + encodeURIComponent(el.dataset.id), { name, inn }, 'PATCH');
            await loadTenders();
            toast('Реквизиты организации сохранены');
            return;
        }
        if (act === 'tender-save-comment') {
            const area = Array.from(document.querySelectorAll('[data-comment-edit]')).find(a => a.dataset.commentEdit === el.dataset.id);
            if (!area?.value?.trim())
                return toast('Введите комментарий', true);
            await api('tenders/' + id + '/comments/' + encodeURIComponent(el.dataset.id), { body: area.value }, 'PATCH');
            await openTender(id);
            state.tenders.detailTab = 'comments';
            render(true);
            toast('Комментарий сохранён');
            return;
        }
        if (act === 'tender-delete-comment') {
            if (!window.confirm('Удалить этот комментарий? Запись об удалении сохранится в истории.'))
                return;
            await api('tenders/' + id + '/comments/' + encodeURIComponent(el.dataset.id), undefined, 'DELETE');
            await openTender(id);
            state.tenders.detailTab = 'comments';
            render(true);
            toast('Комментарий удалён');
            return;
        }
        if (act === 'tender-delete-doc') {
            if (!window.confirm('Удалить документ из карточки закупки? Перед удалением сделайте резервную копию.'))
                return;
            await api('tenders/' + id + '/documents/' + encodeURIComponent(el.dataset.id), undefined, 'DELETE');
            await openTender(id);
            state.tenders.detailTab = 'docs';
            render(true);
            toast('Документ удалён');
            return;
        }
        if (act === 'tender-comment') {
            const body = $('#tender-comment')?.value;
            if (!body?.trim())
                return toast('Напишите комментарий', true);
            await api('tenders/' + id + '/comments', { body });
            await openTender(id);
            return;
        }
        if (act === 'tender-add-shipment') {
            const name = $('#ship-name')?.value?.trim();
            const qty = Number($('#ship-qty')?.value);
            const date = $('#ship-due')?.value || '';
            if (!name || !Number.isInteger(qty) || qty <= 0 || !date) return toast('Заполните название, положительное количество и дату этапа', true);
            await api('tenders/' + id + '/shipments', { name, quantity: qty, due_on: date });
            await openTender(id); state.tenders.detailTab = 'shipments'; render();
            return;
        }
        if (act === 'tender-delete-stage') {
            const stage = state.tenders.current?.shipments?.find(x => x.id === el.dataset.id);
            if (!stage || !window.confirm('Удалить этап «' + (stage.name || 'Без названия') + '»? Сама закупка и остальные партии останутся.')) return;
            await api('tenders/' + id + '/shipments/' + encodeURIComponent(stage.id), undefined, 'DELETE');
            await openTender(id); state.tenders.detailTab = 'shipments'; render();
            toast('Этап удалён'); return;
        }
        if (act === 'tender-ai-model-download') {
            const info = await api('local-ai/model-install', {}, 'POST');
            state.tenderAiInstall = info;
            const node = $('#qx-model-download-progress');
            if (node)
                node.textContent = qxModelInstallText(info);
            if (info.state === 'downloading')
                void qxPollModelInstall();
            return;
        }
        if (act === 'tender-ai-model-cancel') {
            state.tenderAiInstall = await api('local-ai/model-install/cancel', {}, 'POST');
            const node = $('#qx-model-download-progress');
            if (node)
                node.textContent = qxModelInstallText(state.tenderAiInstall);
            return;
        }
        if (act === 'tender-ai-model-folder') {
            const bridge = bridgeApi();
            if (bridge?.open_ai_models) {
                const r = await bridge.open_ai_models();
                if (r?.message)
                    toast(r.message);
            }
            else {
                toast('Папка моделей: ' + (state.tenderAiStatus?.gguf_model_directory || 'данные QX / models'));
            }
            return;
        }
        if (act === 'tender-ai-status') {
            await refreshTenderAiStatus();
            return;
        }
        if (act === 'tender-local-ai') {
            const model = $('#tender-llm-model')?.value || state.tenderAiModel;
            state.tenderAiModel = model;
            await busy(async () => { const r = await api('tenders/' + id + '/local-ai', { question: $('#tender-llm-question')?.value, model }); state.tenderLocalAnswer = r.answer; render(); });
            return;
        }
        if (act === 'tender-apply-analysis') {
            const fields = [...document.querySelectorAll('[data-analysis-field]:checked')].map(e => e.dataset.analysisField);
            if (!fields.length) {
                toast('Выберите поля, которые нужно заполнить', true);
                return;
            }
            const r = await api('tenders/' + id + '/apply-suggestions', { fields });
            await openTender(id);
            state.tenders.detailTab = 'contract';
            render(true);
            toast(r.applied.length ? 'Заполнено полей: ' + r.applied.length : 'Ничего не изменено: поля уже заполнены');
            return;
        }
        if (act === 'tender-export-report') {
            window.open('/api/tenders/' + encodeURIComponent(id) + '/report.docx', '_blank');
            return;
        }
        if (act === 'tender-analyze') {
            state.tenders.detailTab = 'docs';
            await busy(async () => { state.tenders.analysis = (await api('tenders/' + id + '/analyze', {}, 'POST')).analysis; render(); });
            return;
        }
        if (act === 'tender-use-tz') {
            const tender = state.tenders.current;
            const doc = tender?.documents?.find(d => d.id === el.dataset.id);
            if (!doc) return toast('Документ не найден. Обновите карточку.', true);
            if (state.reqs.length && state.tenderLinkEnabled && state.tenderNoticeNumber !== tender.number)
                return toast('Текущий расчёт связан с другой закупкой. Создайте новый расчёт перед загрузкой этого ТЗ.', true);
            const blob = await api('tenders/' + encodeURIComponent(id) + '/documents/' + encodeURIComponent(doc.id), undefined, 'GET');
            state.tenderLinkEnabled = true;
            state.tenderNoticeNumber = tender.number;
            state.tenderId = id;
            await uploadTzFiles([new File([blob], doc.filename, { type: blob.type })], id);
            return;
        }
        if (act === 'tender-download') {
            const url = '/api/tenders/' + encodeURIComponent(id) + '/documents/' + encodeURIComponent(el.dataset.id);
            window.open(url, '_blank');
            return;
        }
        if (act === 'tender-eis-discover') {
            await busy(async () => {
                state.tenderEisDiscovery = await api('tenders/' + id + '/eis/discover', {});
                state.tenders.detailTab = 'docs'; render();
                toast(state.tenderEisDiscovery.message, !state.tenderEisDiscovery.available);
            }); return;
        }
        if (act === 'tender-eis-discover-import') {
            if (!state.tenderEisDiscovery?.documents?.length || state.tenderEisDiscovery.notice_number !== state.tenders.current?.number)
                return toast('Сначала нажми «Найти документы», чтобы посмотреть найденные файлы.', true);
            await busy(async () => {
                const urls = state.tenderEisDiscovery.documents.map(x => x.url);
                const result = await api('tenders/' + id + '/eis/documents-from-urls', {urls});
                state.tenderEisUpload = result;
                await openTender(id); state.tenders.detailTab = 'docs'; render();
                toast('Загружено файлов: ' + (result.imported || []).length + (result.failed_count ? '. Ошибок: ' + result.failed_count : ''), Boolean(result.failed_count));
            }); return;
        }
        if (act === 'tender-eis-document-url') {
            const raw = $('#tender-eis-doc-url')?.value?.trim() || '';
            const urls = raw.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
            if (!urls.length) {
                toast('Вставьте ссылки на файлы с zakupki.gov.ru', true);
                return;
            }
            if (urls.length > 10) {
                toast('За один раз можно загрузить не больше 10 файлов', true);
                return;
            }
            await busy(async () => {
                const result = await api('tenders/' + id + (urls.length > 1 ? '/eis/documents-from-urls' : '/eis/document-from-url'), urls.length > 1 ? { urls } : { url: urls[0] });
                state.tenderEisUpload = result;
                await openTender(id);
                state.tenders.detailTab = 'docs';
                if ((result.imported || []).length) {
                    try {
                        state.tenders.analysis = (await api('tenders/' + id + '/analyze', {}, 'POST')).analysis;
                    }
                    catch (e) {
                        console.warn('Не удалось разобрать загруженный документ:', e);
                    }
                }
                render(true);
                const warnings = (result.warnings || []).length;
                toast(`ЕИС: ${result.imported?.length || 0} файлов загружено. ${result.failed_count ? 'Ошибок: ' + result.failed_count + ' (строки ' + (result.failures || []).map(f => f.line).join(', ') + '). ' : ''}${warnings ? 'Без текста: ' + warnings + '.' : ''} Анализ — во вкладке «Документы».`, Boolean(result.failed_count));
            });
            return;
        }
        if (act === 'tender-eis-lookup') {
            await busy(async () => { state.tenderEisLookup = await api('tenders/' + id + '/eis/lookup', {}, 'POST'); render(true); });
            return;
        }
        if (act === 'tender-eis-open-match') {
            const u = String(el.dataset.url || '');
            const parsed = new URL(u);
            if (parsed.protocol !== 'https:' || parsed.hostname !== 'zakupki.gov.ru')
                throw new Error('Недопустимая ссылка ЕИС');
            const native = bridgeApi();
            if (native?.open_external)
                await native.open_external(u);
            else
                window.open(u, '_blank', 'noopener');
            return;
        }
        if (act === 'tender-eis') {
            const response = await api('tenders/' + id + '/eis', undefined, 'GET');
            const url = response.url;
            const native = bridgeApi();
            if (native?.open_external)
                await native.open_external(url);
            else
                window.open(url, '_blank', 'noopener');
            toast('Открываем официальный поиск ЕИС — проверьте результат');
            return;
        }
        if (act === 'tender-go-registry') {
            gotoTender('registry');
            return;
        }
        if (act === 'tender-import-project') {
            const file = await openNativeFile('tender_project');
            if (file) await tenderImportProject(file);
            return;
        }
        if (act === 'tender-auto-contract') {
            await busy(async () => {
                const r = await api('tenders/' + id + '/analyze-and-fill', {}, 'POST');
                await openTender(id);
                state.tenders.detailTab = 'contract';
                render(true);
                toast(r.applied.length ? 'Заполнены поля: ' + r.applied.map(x => tenderLabels[x] || x).join(', ') : 'Новых однозначных условий не найдено. Проверьте документ вручную.');
            });
            return;
        }
        if (act === 'tender-link-current') {
            await syncTenderProject(true);
            await openTender(state.tenderId);
            return;
        }
    }
    catch (e) {
        console.error(e);
        toast('Ошибка в разделе «Тендеры»: ' + e.message, true);
    }
}
function synchronizeTenderSoon() { clearTimeout(tenderSyncTimer); tenderSyncTimer = setTimeout(() => syncTenderProject().catch(e => console.warn('Tender link', e)), 1800); }
async function syncTenderProject(showNotice = false) {
    if (!state.tenderLinkEnabled && !showNotice)
        return;
    if (state.tenderLinkEnabled && !/^(?:\d{11}|\d{19,20})$/.test(String(state.tenderNoticeNumber || ''))) {
        if (showNotice)
            toast('Укажите номер ЕИС', true);
        return;
    }
    if (!state.reqs?.length || !state.tenderProjectKey)
        return;
    const positions = state.reqs.map((r, i) => ({ title: r.item_name || r.title || ('Позиция ' + (i + 1)), quantity: num(r.quantity), unit_cost: unitCost(state.plans[i]) }));
    const r = await api('tenders/link-project', { project_key: state.tenderProjectKey, project_name: state.name, source_name: state.source_filename, source_text: state.source_text?.slice(0, 12000), positions, cost: purchase(), notice_number: state.tenderNoticeNumber || '', tender_id: state.tenderId || '', manual: Boolean(showNotice) });
    state.tenderId = r.tender_id || '';
    if (showNotice)
        toast('Текущий расчёт привязан к закупке');
}
// A separate queue per card keeps rapid edits together and serializes PATCHes.
const tenderFieldSaves = new Map();
function tenderFieldFeedback(id, message) {
    if (state.tenders.current?.id !== id) return;
    const feedback = $('#tender-save-feedback');
    if (feedback) feedback.textContent = message;
}
function discardTenderFieldEdits(id) {
    const queue = tenderFieldSaves.get(id);
    if (queue) { clearTimeout(queue.timer); queue.cancelled = true; }
    tenderFieldSaves.delete(id);
}
async function flushTenderFields(id) {
    const queue = tenderFieldSaves.get(id);
    if (!queue || queue.cancelled) return;
    clearTimeout(queue.timer);
    if (queue.saving) return queue.saving;
    const merge = (saved) => {
        // Responses to older edits must not replace values entered while waiting.
        Object.assign(queue.target, saved || {}, queue.pending);
        if (state.tenders.current?.id === id)
            Object.assign(state.tenders.current, saved || {}, queue.pending);
        const listed = (state.tenders.items || []).find(t => t.id === id);
        if (listed) Object.assign(listed, saved || {}, queue.pending);
    };
    queue.saving = (async () => {
        let refresh = false, redraw = false;
        do {
        while (!queue.cancelled && Object.keys(queue.pending).length) {
            const patch = queue.pending;
            queue.pending = {};
            try {
                const result = await api('tenders/' + encodeURIComponent(id), patch, 'PATCH');
                if (queue.cancelled) return;
                merge(result.tender);
                refresh ||= Object.keys(patch).some(name => ['due_days', 'due_on', 'due_unit', 'signed_on', 'is_delivered', 'status', 'contract_price', 'application_due_on', 'auction_on', 'payment_due_on', 'is_quotation', 'results_on', 'results_time', 'purchase_cost', 'delivery_cost', 'extra_cost'].includes(name));
            }
            catch (error) {
                // Keep the failed values, but newer edits win if a field changed again.
                queue.pending = { ...patch, ...queue.pending };
                throw error;
            }
        }
        if (queue.cancelled) return;
        if (refresh && state.tenders.current?.id === id) {
            // Fetch derived deadlines without resetting tabs or changing selected card.
            refresh = false;
            redraw = true;
            try {
                const result = await api('tenders/' + encodeURIComponent(id), undefined, 'GET');
                if (!queue.cancelled) merge(result.tender);
            }
            catch (error) { toast('Изменения сохранены, но итоги не обновились: ' + error.message, true); }
        }
        } while (!queue.cancelled && Object.keys(queue.pending).length);
        if (!queue.cancelled && !Object.keys(queue.pending).length) {
            tenderFieldFeedback(id, '✓ Изменения сохранены');
            if (redraw && state.tenders.current?.id === id && !document.activeElement?.dataset?.tenderField)
                render();
        }
    })();
    try { await queue.saving; }
    catch (error) {
        if (!queue.cancelled) {
            tenderFieldFeedback(id, 'Ошибка сохранения: ' + error.message + '. Введённые значения оставлены; повторите изменение или сохранение.');
            toast(error.message, true);
        }
        throw error;
    }
    finally { queue.saving = null; }
    if (!queue.cancelled && Object.keys(queue.pending).length) return flushTenderFields(id);
    if (tenderFieldSaves.get(id) === queue) tenderFieldSaves.delete(id);
}
function tenderChanged(el) {
    const name = el.dataset.tenderField;
    if (!name) return false;
    const t = state.tenders.current;
    if (!t) return true;
    const value = ['is_delivered', 'is_quotation'].includes(name) ? el.checked : (el.type === 'number' ? num(el.value) : el.value);
    t[name] = value;
    let queue = tenderFieldSaves.get(t.id);
    if (!queue) {
        queue = { target: t, pending: {}, timer: null, saving: null, cancelled: false };
        tenderFieldSaves.set(t.id, queue);
    }
    queue.pending[name] = value;
    clearTimeout(queue.timer);
    tenderFieldFeedback(t.id, 'Сохранение…');
    queue.timer = setTimeout(() => { void flushTenderFields(t.id).catch(() => {}); }, 550);
    return true;
}
async function previewTenderRepair(file) {
    if (!file || !String(file.name || '').toLowerCase().endsWith('.zip')) {
        toast('Выберите ZIP-копию тендеров QX', true);
        return;
    }
    await busy(async () => {
        state.tenderRepairFile = null;
        state.tenderRepairPreview = null;
        const r = await api('tenders/backup/repair-preview', file, 'POST');
        state.tenderRepairFile = file;
        state.tenderRepairPreview = r.preview;
        state.modal = 'tender-repair';
        render();
    });
}
async function tenderRestoreInspect(file) {
    if (!file || !String(file.name || '').toLowerCase().endsWith('.zip')) {
        toast('Выберите ZIP-архив QX', true);
        return;
    }
    await busy(async () => {
        const r = await api('tenders/backup/preview', file, 'POST');
        state.tenderRestoreFile = file;
        state.tenderRestorePreview = r.preview;
        state.modal = 'tender-restore';
        render();
    });
}
async function tenderImportPackage(file) {
    const id = state.tenders.selected;
    if (!id)
        return;
    if (!String(file.name || '').toLowerCase().endsWith('.zip')) {
        toast('Выберите ZIP-пакет документации', true);
        return;
    }
    await busy(async () => {
        const r = await api('tenders/' + id + '/documents/import-package', file, 'POST', { 'X-File-Name': encodeURIComponent(file.name) });
        const count = (r.imported || []).length, skipped = (r.ignored || []).length, duplicates = (r.duplicates || []).length, warn = (r.warnings || []).length;
        await openTender(id);
        state.tenders.detailTab = 'docs';
        render();
        toast('Добавлено: ' + count + '. Уже были: ' + duplicates + '. Пропущено: ' + skipped + '. Без читаемого текста: ' + warn + '.');
        if (skipped)
            console.info('Пропущенные файлы ZIP:', r.ignored);
        if (warn)
            console.info('Документы без текстового слоя:', r.warnings);
    });
}
async function tenderImportProject(file) {
    const id = state.tenders.selected;
    if (!id) return;
    if (!file.name.toLowerCase().endsWith('.qxproj')) return toast('Выберите проект .qxproj', true);
    await busy(async () => {
        const r = await api('tenders/' + encodeURIComponent(id) + '/projects/import', file, 'POST', { 'X-File-Name': encodeURIComponent(file.name) });
        await loadTenders();
        await openTender(id);
        state.tenders.detailTab = 'projects';
        render(true);
        toast('Проект привязан: ' + r.positions + ' поз. · себестоимость ' + rub(r.purchase_cost));
    });
}
async function tenderUpload(file) {
    const id = state.tenders.selected;
    if (!id)
        return;
    await busy(async () => { const r = await api('tenders/' + id + '/documents', file, 'POST', { 'X-File-Name': encodeURIComponent(file.name) }); let applied = []; if (/(?:контракт|договор|contract)/i.test(file.name)) { const result = await api('tenders/' + id + '/analyze-and-fill', {}, 'POST'); applied = result.applied || []; } await openTender(id); toast('Документ добавлен: ' + file.name + (applied.length ? ' · Автозаполнено полей: ' + applied.length : ''));  });
}
init();
