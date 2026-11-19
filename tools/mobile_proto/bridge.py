"""Glue between the mobile prototype page and StallMeter's own engine (core.py, i18n.py), run in Pyodide.

Every number the page shows comes from a core.py function called here; this file only picks and formats them.
Data lives in the same JSON format as the desktop app (core.load / core.save) at PATH in Pyodide's file system;
the page copies that file to and from the browser's localStorage.
Subscriptions only, like the mobile design.
"""
import calendar
import json
from datetime import date, datetime, timedelta

import core
import i18n

PATH = "/home/pyodide/stallmeter-data.json"
LANG = "ko"
t = i18n.translator(LANG)
DATA = core.new_data()
BROKEN = None
WEEKDAYS = t("cal_weekdays").split()


def _out(value):
    return json.dumps(value, ensure_ascii=False)


def _now(now_iso):
    return datetime.fromisoformat(now_iso)


def _money(value):
    return core.format_money(value, DATA["settings"]["currency"], 0)


def _subs():
    return [i for i in DATA["items"] if i["kind"] == "sub"]


def _save():
    core.save(PATH, DATA)


def init():
    """Loads the data file. A damaged file is kept aside by core.load and the app starts empty."""
    global DATA, BROKEN
    DATA, BROKEN = core.load(PATH)
    DATA["settings"]["lang"] = LANG
    return _out({"broken": BROKEN})


def _row(s, now, part):
    return {"id": s["id"], "title": s["title"], "initial": s["title"][:1], "tab": s["category"],
            "price": core.price_text(s, DATA["settings"]["currency"], t),
            "year": _money(part["year"]), "wasted": core.wasted_text(part),
            "alert": (part["wasted"] or 0) >= 0.5, "open": core.is_open(s, now)}


def home(now_iso, tab, show_closed):
    now = _now(now_iso)
    subs = _subs()
    cache = {s["id"]: core.losses(s, now) for s in subs}
    summ = core.summary(subs, now, cache)
    rows = [s for s in subs if (not tab or s["category"] == tab) and (show_closed or core.is_open(s, now))]
    # The mobile list is ordered by this year's loss; closed items go last.
    rows.sort(key=lambda s: (not core.is_open(s, now), -cache[s["id"]]["year"], s["id"]))
    return _out({
        "empty": not subs, "sample": core.has_sample(DATA), "tabs": core.categories(DATA),
        "cards": {k: _money(summ[k]) for k in ("week", "month", "year", "total")},
        "closed_count": sum(1 for s in subs if not core.is_open(s, now)),
        "rows": [_row(s, now, cache[s["id"]]) for s in rows],
    })


def _week_state(s, today):
    mon = core.monday(today)
    used = sum(1 for i in range((today - mon).days + 1) if (mon + timedelta(days=i)).isoformat() in s["used"])
    missed = [loss for d, loss in core.sub_missed(s, today) if d >= mon]
    return used, missed


def check(now_iso):
    now = _now(now_iso)
    today = now.date()
    subs = [s for s in _subs() if core.is_open(s, now)]
    cache = {s["id"]: core.losses(s, now) for s in subs}
    subs.sort(key=lambda s: (-cache[s["id"]]["year"], s["id"]))
    rows = []
    for s in subs:
        used, missed = _week_state(s, today)
        rows.append({"id": s["id"], "title": s["title"], "goal": s["target"], "used": used,
                     "today": today.isoformat() in s["used"], "can": core.sub_can_mark(s, today, today),
                     "missed": len(missed), "missed_cost": _money(sum(missed))})
    summ = core.summary(subs, now, cache)
    return _out({"date": today.isoformat(), "weekday": WEEKDAYS[today.weekday()], "rows": rows,
                 "goal": sum(r["goal"] for r in rows), "used": sum(r["used"] for r in rows),
                 "week_loss": _money(summ["week"])})


def _cell(s, d, today, missed):
    if d.isoformat() in s["used"]:
        return "used"
    if d in missed:
        return "missed"
    if not core.sub_can_mark(s, d, today):
        return "off"
    return "today" if d == today else "open"


def detail(now_iso, item_id, year, month):
    now = _now(now_iso)
    today = now.date()
    s = core.find(DATA, item_id)
    cur = DATA["settings"]["currency"]
    part = core.losses(s, now)
    missed_list = core.sub_missed(s, today)
    missed = {d for d, _ in missed_list}
    first = date(year, month, 1)
    days = calendar.monthrange(year, month)[1]
    cells = [{"day": n, "iso": date(year, month, n).isoformat(), "state": _cell(s, date(year, month, n), today, missed),
              "can": core.sub_can_mark(s, date(year, month, n), today)} for n in range(1, days + 1)]
    month_missed = [loss for d, loss in missed_list if (d.year, d.month) == (year, month)]
    used_month = sum(1 for c in cells if c["state"] == "used")
    end = core.sub_end(s)
    if s["billing"] in core.FIXED_TERM or (end and not core.is_open(s, now)):
        term = f"{s['start']} ~ {s['end']}"
    else:
        term = f"{s['start']} ~"
    inst = None
    if s["billing"] == "installment":
        paid, n, left = core.installment_state(s, today)
        inst = {"text": t("st_installment", paid=paid, n=n, left=core.format_money(left, cur, 0)), "ratio": paid / n}
    day = max(core.sub_start(s), min(today, end or today))
    return _out({
        "id": s["id"], "title": s["title"], "tab": s["category"], "price": core.price_text(s, cur, t),
        "goal": t("st_goal", n=s["target"]), "term": term, "installment": inst,
        "losses": {k: _money(part[k]) for k in ("week", "month", "year", "total")},
        "wasted": core.wasted_text(part), "wasted_ratio": part["wasted"],
        "missed_day_cost": _money(core.sub_daily_price(s, day) * 7 / s["target"]),
        "year": year, "month": month, "lead": first.weekday(), "cells": cells,
        "summary": t("cal_summary", used=used_month, missed=len(month_missed), cost=_money(sum(month_missed))),
        "today_can": core.sub_can_mark(s, today, today), "today_used": today.isoformat() in s["used"],
        "open": core.is_open(s, now), "fixed": s["billing"] in core.FIXED_TERM, "billing": s["billing"],
        "ended": t("st_ended", date=s["end"]) if end and not core.is_open(s, now) else "",
        "confirm_cancel": t("confirm_cancel_yearly" if s["billing"] == "yearly" else "confirm_cancel", title=s["title"]),
        "confirm_delete": t("confirm_delete", title=s["title"]), "fixed_note": t("prepaid_no_end"),
    })


def report(now_iso, period):
    now = _now(now_iso)
    subs = _subs()
    cache = {s["id"]: core.losses(s, now) for s in subs}
    summ = core.summary(subs, now, cache)
    tabs = {}
    for s in subs:
        tabs[s["category"]] = tabs.get(s["category"], 0) + cache[s["id"]][period]
    top = max(tabs.values(), default=0)
    cands = [s for s in subs if core.is_open(s, now) and (cache[s["id"]]["wasted"] or 0) >= 0.5]
    cands.sort(key=lambda s: -(cache[s["id"]]["wasted"] or 0))
    return _out({
        "sum": _money(summ[period]), "count": len(subs),
        "tabs": [{"name": k, "value": _money(v), "ratio": (v / top) if top else 0}
                 for k, v in sorted(tabs.items(), key=lambda kv: -kv[1])],
        "candidates": [dict(_row(s, now, cache[s["id"]]), loss=_money(cache[s["id"]][period])) for s in cands],
        "formula": t("r_formula"),
    })


# ---------- actions (each saves the data file) ----------

def toggle_day(now_iso, item_id, iso):
    today = _now(now_iso).date()
    s = core.find(DATA, item_id)
    ok = core.set_use(DATA, item_id, date.fromisoformat(iso), iso not in s["used"], today)
    if ok:
        _save()
    return _out({"ok": ok})


def _fields(raw):
    fields = json.loads(raw)
    fields["months"] = fields.get("months") or "0"
    return fields


def preview(now_iso, raw):
    """The add form's live line: what one missed day costs, or the first input error."""
    today = _now(now_iso).date()
    try:
        s = core.clean_sub(_fields(raw))
    except core.FieldError as e:
        return _out({"error": t(e.key)})
    end = core.sub_end(s)
    day = max(core.sub_start(s), min(today, end or today))
    cost = _money(core.sub_daily_price(s, day) * 7 / s["target"])
    if s["billing"] == "installment":
        text = t("preview_installment", cost=cost, per=_money(s["amount"] / s["months"]), n=s["months"])
    else:
        text = t("preview_sub", cost=cost)
    return _out({"text": text, "end": s["end"]})


def add(now_iso, raw):
    try:
        if not _subs() and not DATA["items"]:
            DATA["settings"]["currency"] = i18n.SAMPLE[LANG]["currency"]
        s = core.add_sub(DATA, _fields(raw))
    except core.FieldError as e:
        return _out({"error": t(e.key)})
    _save()
    return _out({"id": s["id"], "title": s["title"]})


def cancel(now_iso, item_id):
    ok = core.cancel_sub(DATA, item_id, _now(now_iso).date())
    if ok:
        _save()
    return _out({"ok": ok})


def reopen(item_id):
    core.reopen(DATA, item_id)
    _save()
    return _out({"ok": True})


def delete(item_id):
    core.delete(DATA, item_id)
    _save()
    return _out({"ok": True})


def load_sample(now_iso):
    core.load_sample(DATA, dict(i18n.SAMPLE[LANG], decisions=[]), _now(now_iso))
    _save()
    return _out({"ok": True})


def clear_sample():
    core.clear_sample(DATA)
    _save()
    return _out({"ok": True})


def reset():
    global DATA
    DATA = core.new_data()
    DATA["settings"]["lang"] = LANG
    _save()
    return _out({"ok": True})


def about():
    import sys
    return _out({"version": core.VERSION, "python": sys.version.split()[0], "currency": DATA["settings"]["currency"]})


def form_options():
    names = core.categories(DATA)
    names += [n for n in i18n.presets(LANG) if n not in names and n != t("cat_decisions")]
    return _out({"tabs": names, "currency": DATA["settings"]["currency"] if DATA["items"] else
                 i18n.SAMPLE[LANG]["currency"]})
