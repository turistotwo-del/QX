"""Contract and tender calendar reminders: offline, transparent, non-legal alerts.

Windows toast delivery is opt-in, while the in-app reminder list always works.
No daemon after the application closes and no network dependency.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
import hashlib
import os
import sys

from modern import tender_store as store

END_STATES = {'Проиграли', 'Отменено', 'Контракт исполнен'}
SUBMITTED_STATES = {'Заявка подана', 'Ожидание результатов', 'Выиграли',
                    'Проиграли', 'Ожидание подписания', 'Контракт подписан',
                    'Заказ оборудования', 'Производство', 'Комплектация',
                    'Готово к отправке', 'Отгружено', 'Доставлено', 'Приёмка',
                    'Контракт исполнен', 'Отменено'}
CONTRACT_STATES = {'Контракт подписан', 'Заказ оборудования', 'Производство',
                   'Комплектация', 'Готово к отправке', 'Отгружено',
                   'Доставлено', 'Приёмка'}


def preferences():
    store.initialize()
    with store.connection() as con:
        r = con.execute('SELECT enabled, advance_days FROM tender_notification_settings WHERE id=1').fetchone()
        return {'enabled':bool(r['enabled']), 'advance_days':int(r['advance_days'])}


def set_preferences(*, enabled=None, advance_days=None):
    old=preferences()
    value=old['enabled'] if enabled is None else bool(enabled)
    ahead=old['advance_days'] if advance_days is None else int(advance_days)
    if not 0 <= ahead <= 60: raise ValueError('Предупреждать можно за 0–60 дней')
    with store.transaction() as con:
        con.execute('UPDATE tender_notification_settings SET enabled=?,advance_days=? WHERE id=1',(int(value),ahead))
    return preferences()


def reminders(today:date|None=None, horizon:int=30, now_at:datetime|None=None):
    now_at=now_at or datetime.now()
    today=today or now_at.date()
    horizon=max(0,min(int(horizon),365))
    output=[]

    def add(t, typ, label, raw_date, *, mark='', confirmed=False, caution=None, due_time=''):
        if not raw_date or confirmed: return
        try:
            due=date.fromisoformat(str(raw_date))
        except ValueError: return
        days=(due-today).days
        if days>horizon: return
        kind = 'overdue' if days<0 else 'today' if days==0 else 'soon' if days<=7 else 'upcoming'
        descriptor=(f'Возможная просрочка: {-days} дн.' if typ in ('delivery','shipment') and days<0
                    else f'Просрочено на {-days} дн.' if days<0
                    else 'Сегодня' if days==0 else 'Завтра' if days==1 else f'Через {days} дн.')
        clock=''
        minutes_remaining=None
        if due_time:
            try:
                when=datetime.combine(due,time.fromisoformat(str(due_time)))
                minutes_remaining=int((when-now_at).total_seconds()//60)
                clock=str(due_time)
                if typ=='auction':
                    descriptor = (f'Через {minutes_remaining} мин. · {clock}' if minutes_remaining>=0
                                  else f'Аукцион прошёл · {clock}')
                    if minutes_remaining < 0: kind='past'
            except (TypeError,ValueError):
                pass
        aid=f"{t['id']}:{typ}:{mark or '-'}:{raw_date}:{clock}"
        output.append({'id':aid,'tender_id':t['id'],'number':t.get('number') or '',
                       'title':t.get('title') or 'Закупка без названия',
                       'note_id':t['id'][5:] if typ=='note' else '',
                       'type':typ,'event':label,'due_on':str(raw_date),
                       'days':days,'due_time':clock,'minutes_until':minutes_remaining,'severity':kind,'message':descriptor,
                       'caution':caution or ''})

    for t in store.listing():
        status=t.get('status') or ''
        if status not in SUBMITTED_STATES:
            add(t,'application','Окончание подачи заявок',t.get('application_due_on'))
        if status not in END_STATES and status not in CONTRACT_STATES and not t.get('is_quotation'):
            add(t,'auction','Аукцион',t.get('auction_on'),due_time=t.get('auction_time') or '')
        if t.get('is_quotation') and status not in END_STATES and status not in CONTRACT_STATES:
            add(t,'results','Подведение итогов котировки',t.get('results_on'),due_time=t.get('results_time') or '')
        if status not in END_STATES:
            # Only reminders from meaningful data: a date alone doesn't certify a signed contract.
            if t.get('signed_on') or status in CONTRACT_STATES:
                d=store.calculate_deadline(t,today=today)
                add(t,'delivery','Срок поставки',d.get('due_on'),confirmed=bool(t.get('is_delivered')),
                    caution=d.get('caution'))
            if float(t.get('contract_price') or 0)>0 and float(t.get('paid_amount') or 0) < float(t.get('contract_price') or 0):
                add(t,'payment','Ожидаемая оплата',t.get('payment_due_on'))
    with store.connection() as con:
        shipments=[dict(r) for r in con.execute('''SELECT s.*, t.number, t.title, t.status
          FROM tender_shipments s JOIN tenders t ON s.tender_id=t.id''').fetchall()]
    for s in shipments:
        if s.get('status') in END_STATES:continue
        add({'id':s['tender_id'],'number':s['number'],'title':s['title']},'shipment',
            'Этап поставки: '+(s.get('name') or 'без названия'),s.get('due_on'),
            mark=s['id'],confirmed=bool(s.get('delivered_on') or s.get('accepted_on')),
            caution='Проверьте условия исполнения в контракте.')

    # Note deadlines share the calendar/reminder feed, but stay in their own database.
    # Completed notes never create notifications; their history remains in the calendar.
    from modern import quick_notes
    for n in quick_notes.due_notes(include_completed=False):
        add({'id': 'note:'+n['id'], 'number':'', 'title':n.get('title') or n.get('body','')[:70] or 'Заметка'},
            'note','Задача из быстрых заметок',n['due_on'])
    output.sort(key=lambda a:(0 if a['days']<0 else 1, a['days'],a['event'],a['title']))
    return output


def notification_candidates(today:date|None=None, now_at:datetime|None=None):
    prefs=preferences()
    now_at=now_at or datetime.now()
    today=today or now_at.date()
    result=[]
    for a in reminders(today,horizon=prefs['advance_days'],now_at=now_at):
        if a['type']=='auction' and a.get('due_time'):
            left=a.get('minutes_until')
            if left is None or left < 0 or left > 60:
                continue
            # Minute-accurate milestones; dedupe each stage separately.
            a={**a,'id':a['id']+(':15m' if left<=15 else ':60m'),
               'message':f'До аукциона {left} мин. Время: {a["due_time"]} (локальное)'}
            result.append(a)
        elif a['type'] == 'auction' and a.get('due_time'):
            continue
        elif -7 <= a['days'] <= prefs['advance_days']:
            result.append(a)
    return result


def _toast(title:str, msg:str, icon_path:Path)->bool:
    """Toast provider can be replaced in tests; failures leave alert unmarked."""
    if sys.platform != 'win32':return False
    from winotify import Notification
    n=Notification(app_id='QX Подборщик Modern',title=title,msg=msg,
                   icon=str(icon_path) if icon_path.is_file() else None)
    n.show()
    return True


def dispatch(*,today:date|None=None,icon_path:Path|None=None,emit=None,now_at:datetime|None=None):
    """Send at most one toast per alert/day and persist dedupe only after success."""
    if not preferences()['enabled']:return {'enabled':False,'sent':0,'available':sys.platform=='win32'}
    emit=emit or _toast
    icon_path=icon_path or Path(__file__).resolve().parents[1]/'assets'/'qx_icon.png'
    sent=0
    today=today or date.today()
    for a in notification_candidates(today,now_at=now_at)[:5]:
        # New event date makes a new ID. Same day restarts never cause repeat alerts.
        key=hashlib.sha256((a['id']+'|'+today.isoformat()).encode('utf-8')).hexdigest()
        with store.connection() as con:
            if con.execute('SELECT 1 FROM tender_notified WHERE event_key=?',(key,)).fetchone():continue
        label=f"{a['event']} · {a['number'] or a['title'][:25]}"
        body=a['message']+' · '+a['due_on']+((' '+a['due_time']) if a.get('due_time') else '')
        try:
            if not emit(label,body,icon_path): continue
        except Exception:
            continue
        with store.transaction() as con:
            con.execute('INSERT OR IGNORE INTO tender_notified(event_key,sent_on) VALUES(?,?)',(key,today.isoformat()))
        sent+=1
    return {'enabled':True,'sent':sent,'available':sys.platform=='win32'}
