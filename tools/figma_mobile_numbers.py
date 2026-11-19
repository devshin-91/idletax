"""Computes every number shown in the Figma mobile mock with StallMeter's own core.py.

The mock shows the Korean sample's subscriptions on Thursday 2026-11-19 at noon.
Usage: python -X utf8 mobile_numbers.py <stallmeter folder> <out.json>
"""
import json
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, sys.argv[1])
import core  # noqa: E402
import i18n  # noqa: E402

NOW = datetime(2026, 11, 19, 12, 0)
TODAY = NOW.date()
spec = dict(i18n.SAMPLE["ko"], decisions=[])  # the mobile mock shows subscriptions only
data = core.new_data()
data["settings"]["lang"] = "ko"
core.load_sample(data, spec, NOW)
t = i18n.translator("ko")
cur = data["settings"]["currency"]
money = lambda v: core.format_money(v, cur, 0)  # noqa: E731


def nov_calendar(s):
    missed = {d for d, _ in core.sub_missed(s, TODAY)}
    used = set(s["used"])
    out = {}
    for day in range(1, 31):
        d = date(2026, 11, day)
        if d.isoformat() in used:
            st = "Used"
        elif d in missed:
            st = "Missed"
        elif d == TODAY and core.sub_can_mark(s, d, TODAY):
            st = "Today"
        elif not core.sub_can_mark(s, d, TODAY):
            st = "Off"
        else:
            st = "Open"
        out[day] = st
    return out


def week_state(s):
    mon = core.monday(TODAY)
    used = sum(1 for i in range(7) if (mon + timedelta(days=i)).isoformat() in s["used"])
    missed = [(d, loss) for d, loss in core.sub_missed(s, TODAY) if d >= mon]
    return used, missed


items = []
for s in core.sorted_items(data["items"], NOW, True):
    part = core.losses(s, NOW)
    cal = nov_calendar(s)
    month_missed = [loss for d, loss in core.sub_missed(s, TODAY) if (d.year, d.month) == (2026, 11)]
    used_w, missed_w = week_state(s)
    day = max(core.sub_start(s), min(TODAY, core.sub_end(s) or TODAY))
    item = {
        "id": s["id"], "title": s["title"], "tab": s["category"], "billing": s["billing"],
        "price": core.price_text(s, cur, t), "goal": s["target"], "start": s["start"], "end": s["end"],
        "week": money(part["week"]), "month": money(part["month"]), "year": money(part["year"]),
        "total": money(part["total"]), "wasted": part["wasted"], "wasted_text": core.wasted_text(part),
        "missed_day_cost": money(core.sub_daily_price(s, day) * 7 / s["target"]),
        "cal": cal, "nov_used": sum(1 for v in cal.values() if v == "Used"), "nov_missed": len(month_missed),
        "nov_loss": money(sum(month_missed)), "week_used": used_w,
        "week_missed": len(missed_w), "week_missed_cost": money(sum(l for _, l in missed_w)),
        "used_today": TODAY.isoformat() in s["used"],
    }
    if s["billing"] == "installment":
        paid, n, left = core.installment_state(s, TODAY)
        item["installment"] = {"paid": paid, "n": n, "left": money(left), "ratio": paid / n,
                               "per": money(s["amount"] / n), "total": money(s["amount"])}
    items.append(item)

periods = {}
for key in ("week", "month", "year", "total"):
    totals = {}
    for s in data["items"]:
        totals[s["category"]] = totals.get(s["category"], 0) + core.losses(s, NOW)[key]
    periods[key] = {"sum": money(sum(totals.values())),
                    "tabs": sorted(([k, money(v), v] for k, v in totals.items()), key=lambda r: -r[2])}
summary = core.summary(data["items"], NOW)
out = {"now": NOW.isoformat(), "items": items, "periods": periods,
       "cards": {k: money(summary[k]) for k in ("week", "month", "year", "total")},
       "week_goal": sum(s["target"] for s in data["items"]), "week_used": sum(i["week_used"] for i in items),
       "candidates": [i["title"] for i in items if (i["wasted"] or 0) >= 0.5]}
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "items"}, ensure_ascii=False))
for i in items:
    print(i["title"], i["price"], i["week"], i["month"], i["year"], i["total"], i["wasted_text"], i["missed_day_cost"],
          "nov used", i["nov_used"], "missed", i["nov_missed"], i["nov_loss"], "week", i["week_used"], "/", i["goal"],
          "wmiss", i["week_missed"], i["week_missed_cost"], "today", i["used_today"], i.get("installment", ""))
