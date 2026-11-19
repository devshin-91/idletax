"""StallMeter logic. No GUI imports; standard library only.

Two kinds of item lose money while nothing happens:

  decision      people wait for it.  loss = daily cost x working days it stays open
  subscription  paid for, not used.  loss = price of each day of the weekly goal that was missed

doc/how-it-works.md explains both rules; test_core.py checks them.
"""

import calendar
import csv
import io
import json
import os
from datetime import date, datetime, time, timedelta

DATA_FILE = "stallmeter-data.json"
APP_NAME = "StallMeter"
VERSION = "0.3.0"
ZERO_DECIMAL_CURRENCIES = ("\u20a9", "\uc6d0", "\u00a5", "KRW", "JPY")
# monthly:     a price every month, until cancelled
# yearly:      one payment a year, renewed every year until cancelled
# prepaid:     one payment for a fixed term (start to end)
# installment: one total for a fixed term, paid in monthly installments
BILLINGS = ("monthly", "yearly", "prepaid", "installment")
FIXED_TERM = ("prepaid", "installment")
WASTE_WINDOW_DAYS = 90

DEFAULT_SETTINGS = {"currency": "$", "lang": "", "default_rate": 50.0, "default_hours": 2.0}
DECISION_KEYS = ("id", "kind", "category", "title", "owner", "people", "rate", "hours", "extra", "opened", "due",
                 "decided", "outcome")
SUB_KEYS = ("id", "kind", "category", "title", "billing", "amount", "months", "start", "end", "target", "used")


class FieldError(ValueError):
    """Bad user input. `key` is an i18n key that explains which field is wrong."""

    def __init__(self, key):
        super().__init__(key)
        self.key = key


# ---------- time ----------

def business_seconds(start, end):
    """Seconds between two datetimes that fall on Monday-Friday."""
    if end <= start:
        return 0.0
    total = 0.0
    cur = start
    while cur < end:
        next_midnight = datetime.combine(cur.date() + timedelta(days=1), time.min)
        seg_end = min(next_midnight, end)
        if cur.weekday() < 5:
            total += (seg_end - cur).total_seconds()
        cur = seg_end
    return total


def business_days(start, end):
    return business_seconds(start, end) / 86400.0


def parse_datetime(text):
    """Accepts 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM' and ISO strings. Raises ValueError."""
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return datetime.fromisoformat(text)


def monday(day):
    return day - timedelta(days=day.weekday())


def window_starts(now):
    """Start of this week (Monday), this month and this year, as datetimes."""
    today = datetime.combine(now.date(), time.min)
    return monday(today), today.replace(day=1), today.replace(month=1, day=1)


# ---------- decisions ----------

def daily_cost(d):
    return d["people"] * d["rate"] * d["hours"] + d["extra"]


def end_time(d, now):
    return parse_datetime(d["decided"]) if d["decided"] else now


def age_days(d, now):
    """Working days the decision has been (or was) open."""
    return business_days(parse_datetime(d["opened"]), end_time(d, now))


def accrued(d, now):
    return daily_cost(d) * age_days(d, now)


def is_overdue(item, now):
    if item["kind"] != "decision" or item["decided"] or not item["due"]:
        return False
    # due is a date; the decision is overdue once that whole day has passed
    return now >= parse_datetime(item["due"]) + timedelta(days=1)


# ---------- subscriptions ----------

def sub_start(s):
    return date.fromisoformat(s["start"])


def sub_end(s):
    return date.fromisoformat(s["end"]) if s["end"] else None


def add_months(day, months):
    """The same day of the month `months` later; the last day of that month if it is shorter."""
    year, month = divmod(day.month - 1 + months, 12)
    year += day.year
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def year_period(start, day):
    """The paid year that contains `day`: (first day, first day of the next paid year)."""
    years = day.year - start.year
    if add_months(start, 12 * years) > day:
        years -= 1
    return add_months(start, 12 * years), add_months(start, 12 * (years + 1))


def sub_daily_price(s, day):
    """Monthly: the month's price over that month's days. Yearly: the year's price over that paid year's days.
    Prepaid and installment: the whole amount over the days of the term, however it is paid."""
    if s["billing"] == "monthly":
        return s["amount"] / calendar.monthrange(day.year, day.month)[1]
    if s["billing"] == "yearly":
        first, after = year_period(sub_start(s), day)
        return s["amount"] / (after - first).days
    return s["amount"] / ((sub_end(s) - sub_start(s)).days + 1)


def installment_state(s, today):
    """(payments made, payments in all, amount still to pay). Payments fall on the start day of each month."""
    count = s["months"]
    paid = sum(1 for k in range(count) if add_months(sub_start(s), k) <= today)
    return paid, count, s["amount"] * (count - paid) / count


def sub_missed(s, today):
    """[(day, loss)] for every goal day that can no longer be made up.

    Weeks run Monday to Sunday. A week with a goal of N use days allows 7 - N days off; each unused day after
    those is a missed day. Today is never missed, because the day is not over. A missed day costs the week's
    price divided by the goal, so a week with no use at all loses exactly that week's price.
    In a first or last week that the term only partly covers, the goal shrinks in proportion.
    """
    start, end = sub_start(s), sub_end(s)
    last = today - timedelta(days=1)
    if end is not None and end < last:
        last = end
    used = set(s["used"])
    out = []
    week = monday(start)
    while week <= last:
        days = [week + timedelta(days=i) for i in range(7)]
        days = [d for d in days if d >= start and (end is None or d <= end)]
        n = len(days)
        goal = min(n, int(s["target"] * n / 7 + 0.5))
        skips = 0
        for d in days:
            if d > last:
                break
            if d.isoformat() not in used:
                skips += 1
                if skips > n - goal:
                    out.append((d, sub_daily_price(s, d) * n / goal))
        week += timedelta(days=7)
    return out


def sub_paid(s, first, last):
    """Price of the days from first to last (inclusive) that fall inside the term."""
    first = max(first, sub_start(s))
    end = sub_end(s)
    if end is not None:
        last = min(last, end)
    total = 0.0
    day = first
    while day <= last:
        total += sub_daily_price(s, day)
        day += timedelta(days=1)
    return total


def sub_can_mark(s, day, today):
    end = sub_end(s)
    return sub_start(s) <= day <= today and (end is None or day <= end)


def set_use(data, item_id, day, used, today):
    """Marks one day as used or not used. Returns False when the day is outside the term or in the future."""
    s = find(data, item_id)
    if s["kind"] != "sub" or not sub_can_mark(s, day, today):
        return False
    days = set(s["used"])
    (days.add if used else days.discard)(day.isoformat())
    s["used"] = sorted(days)
    return True


# ---------- every item ----------

def is_open(item, now):
    if item["kind"] == "decision":
        return not item["decided"]
    end = sub_end(item)
    return end is None or end >= now.date()


def losses(item, now):
    """Loss this week, this month, this year and in total, plus the share of the last 90 days' price that was
    lost (subscriptions only, else None)."""
    week, month, year = window_starts(now)
    if item["kind"] == "decision":
        opened, end, per_day = parse_datetime(item["opened"]), end_time(item, now), daily_cost(item)
        since = lambda a: per_day * business_days(max(opened, a), end)  # noqa: E731
        return {"week": since(week), "month": since(month), "year": since(year), "total": since(opened), "wasted": None}
    missed = sub_missed(item, now.date())
    since = lambda a: sum(loss for day, loss in missed if day >= a)  # noqa: E731
    cutoff = now.date() - timedelta(days=WASTE_WINDOW_DAYS)
    paid = sub_paid(item, cutoff, now.date() - timedelta(days=1))
    return {"week": since(week.date()), "month": since(month.date()), "year": since(year.date()),
            "total": since(date.min), "wasted": min(1.0, since(cutoff) / paid) if paid > 0 else None}


def summary(items, now, cache=None):
    """Sums of losses(). `cache` maps item id to an already computed losses() result."""
    out = {"week": 0.0, "month": 0.0, "year": 0.0, "total": 0.0, "count": len(items),
           "open_count": sum(1 for i in items if is_open(i, now)),
           "overdue_count": sum(1 for i in items if is_overdue(i, now))}
    for item in items:
        part = (cache or {}).get(item["id"]) or losses(item, now)
        for key in ("week", "month", "year", "total"):
            out[key] += part[key]
    return out


def sorted_items(items, now, include_closed=False, cache=None):
    """Open items first, largest total loss first; then closed ones."""
    total = lambda i: ((cache or {}).get(i["id"]) or losses(i, now))["total"]  # noqa: E731
    ranked = sorted(items, key=lambda i: (not is_open(i, now), -total(i), i["id"]))
    return ranked if include_closed else [i for i in ranked if is_open(i, now)]


def categories(data):
    """Tab names in the order they were added. A tab can be empty."""
    return list(data["categories"])


def in_category(data, category):
    return [i for i in data["items"] if category is None or i["category"] == category]


def format_money(value, currency, decimals=None):
    if decimals is None:
        decimals = 0 if currency in ZERO_DECIMAL_CURRENCIES else 2
    return f"{currency}{value:,.{decimals}f}"


# ---------- input ----------

def _number(text, key, minimum, maximum=None, integer=False, exclusive_min=False):
    try:
        value = float(str(text).strip().replace(",", ""))
    except ValueError:
        raise FieldError(key) from None
    if value != value or value in (float("inf"), float("-inf")):
        raise FieldError(key)
    if integer and value != int(value):
        raise FieldError(key)
    if value < minimum or (exclusive_min and value == minimum) or (maximum is not None and value > maximum):
        raise FieldError(key)
    return int(value) if integer else value


def _common(fields):
    title = str(fields.get("title", "")).strip()
    if not title:
        raise FieldError("err_title")
    category = str(fields.get("category", "")).strip()
    if not category:
        raise FieldError("err_category")
    return title, category


def clean_decision(fields):
    """Validates raw text fields and returns the stored form (without id). Raises FieldError."""
    title, category = _common(fields)
    people = _number(fields.get("people", ""), "err_people", 1, 100000, integer=True)
    rate = _number(fields.get("rate", ""), "err_rate", 0)
    hours = _number(fields.get("hours", ""), "err_hours", 0, 24, exclusive_min=True)
    extra = _number(fields.get("extra", "") or "0", "err_extra", 0)
    try:
        opened = parse_datetime(fields.get("opened", ""))
    except ValueError:
        raise FieldError("err_opened") from None
    due_text = str(fields.get("due", "")).strip()
    due = ""
    if due_text:
        try:
            due = parse_datetime(due_text).date().isoformat()
        except ValueError:
            raise FieldError("err_due") from None
    return {"kind": "decision", "category": category, "title": title, "owner": str(fields.get("owner", "")).strip(),
            "people": people, "rate": rate, "hours": hours, "extra": extra,
            "opened": opened.isoformat(timespec="minutes"), "due": due, "decided": "", "outcome": ""}


def clean_sub(fields):
    """Validates a subscription's raw text fields. Raises FieldError."""
    title, category = _common(fields)
    billing = fields.get("billing", "")
    if billing not in BILLINGS:
        raise FieldError("err_billing")
    amount = _number(fields.get("amount", ""), "err_amount", 0, exclusive_min=True)
    months = 0
    if billing == "installment":
        months = _number(fields.get("months", ""), "err_months", 2, 120, integer=True)
    try:
        start = parse_datetime(fields.get("start", "")).date()
    except ValueError:
        raise FieldError("err_start") from None
    end_text = str(fields.get("end", "")).strip()
    end = ""
    if end_text:
        try:
            end_day = parse_datetime(end_text).date()
        except ValueError:
            raise FieldError("err_end") from None
        if end_day < start:
            raise FieldError("err_end")
        end = end_day.isoformat()
    elif billing == "installment":
        # with no end date, what was bought lasts as long as the installments do
        end = (add_months(start, months) - timedelta(days=1)).isoformat()
    elif billing == "prepaid":
        raise FieldError("err_end_needed")
    target = _number(fields.get("target", ""), "err_target", 1, 7, integer=True)
    return {"kind": "sub", "category": category, "title": title, "billing": billing, "amount": amount,
            "months": months, "start": start.isoformat(), "end": end, "target": target, "used": []}


# ---------- data ----------

def new_data():
    return {"version": 3, "settings": dict(DEFAULT_SETTINGS), "next_id": 1, "categories": [], "items": []}


def _add(data, item):
    item["id"] = data["next_id"]
    data["next_id"] += 1
    data["items"].append(item)
    add_category(data, item["category"])
    return item


# ---------- categories (tabs) ----------

def add_category(data, name):
    """Adds a tab. Returns the cleaned name, or raises FieldError when it is empty."""
    name = str(name).strip()
    if not name:
        raise FieldError("err_category")
    if name not in data["categories"]:
        data["categories"].append(name)
    return name


def rename_category(data, old, new):
    """Renames a tab and moves its items. Renaming onto an existing tab merges the two."""
    new = add_category(data, new)
    if new != old:
        for item in data["items"]:
            if item["category"] == old:
                item["category"] = new
        data["categories"].remove(old)
    return new


def remove_category(data, name, fallback):
    """Removes a tab. Its items are kept and moved to the `fallback` tab. Returns how many were moved."""
    moved = [item for item in data["items"] if item["category"] == name]
    if moved:
        if fallback == name:
            return -1  # the fallback tab cannot be removed while it holds items
        add_category(data, fallback)
        for item in moved:
            item["category"] = fallback
    data["categories"].remove(name)
    return len(moved)


# ---------- sample ----------

def has_sample(data):
    return any(item.get("sample") for item in data["items"])


def load_sample(data, spec, now):
    """Adds made-up items marked as sample, so they can be removed again without touching real items.

    spec = {"subs": [(title, category, billing, amount, months, started days ago, term days or None, goal,
                      weekdays used, latest days with no use)],
            "decisions": [(title, category, owner, people, rate, hours, extra, opened days ago, due in days)]}
    """
    today = now.date()
    before = list(data["categories"])
    if not data["items"]:  # nothing of the user's own yet: show the sample in the sample's currency
        data["sample_currency_before"] = data["settings"]["currency"]
        data["settings"]["currency"] = spec["currency"]
    for title, category, billing, amount, months, ago, term, goal, weekdays, idle in spec["subs"]:
        start = today - timedelta(days=ago)
        s = add_sub(data, {"title": title, "category": category, "billing": billing, "amount": str(amount),
                           "months": str(months), "start": start.isoformat(), "target": str(goal),
                           "end": (start + timedelta(days=term - 1)).isoformat() if term else ""})
        s["sample"] = True
        day = start
        while day <= today - timedelta(days=idle):
            if day.weekday() in weekdays:
                set_use(data, s["id"], day, True, today)
            day += timedelta(days=1)
    for title, category, owner, people, rate, hours, extra, ago, due_in in spec["decisions"]:
        d = add_decision(data, {"title": title, "category": category, "owner": owner, "people": str(people),
                                "rate": str(rate), "hours": str(hours), "extra": str(extra),
                                "opened": (today - timedelta(days=ago)).isoformat(),
                                "due": (today + timedelta(days=due_in)).isoformat()})
        d["sample"] = True
    data["sample_tabs"] = [c for c in data["categories"] if c not in before]


def clear_sample(data):
    """Removes the sample items, and the tabs the sample created if nothing else is in them."""
    data["items"] = [item for item in data["items"] if not item.get("sample")]
    if "sample_currency_before" in data:
        data["settings"]["currency"] = data.pop("sample_currency_before")
    for name in data.pop("sample_tabs", []):
        if name in data["categories"] and not in_category(data, name):
            data["categories"].remove(name)


def add_decision(data, fields):
    return _add(data, clean_decision(fields))


def add_sub(data, fields):
    return _add(data, clean_sub(fields))


def find(data, item_id):
    for item in data["items"]:
        if item["id"] == item_id:
            return item
    raise KeyError(item_id)


def update_item(data, item_id, fields):
    """Replaces the editable fields. Keeps the id, the decided state and the use days."""
    old = find(data, item_id)
    if old["kind"] == "decision":
        new = clean_decision(fields)
        new["decided"], new["outcome"] = old["decided"], old["outcome"]
        if new["decided"] and parse_datetime(new["decided"]) < parse_datetime(new["opened"]):
            raise FieldError("err_opened")
    else:
        new = clean_sub(fields)
        new["used"] = old["used"]
    new["id"] = old["id"]
    if old.get("sample"):
        new["sample"] = True
    data["items"][data["items"].index(old)] = new
    add_category(data, new["category"])
    return new


def decide(data, item_id, outcome, now):
    d = find(data, item_id)
    d["decided"] = max(now, parse_datetime(d["opened"])).isoformat(timespec="minutes")
    d["outcome"] = (outcome or "").strip()
    return d


def cancel_sub(data, item_id, today):
    """Ends a subscription you cancelled. Monthly ends today. Yearly ends when the paid year runs out.
    A fixed term keeps its end date: the money is already spent."""
    s = find(data, item_id)
    if s["billing"] in FIXED_TERM:
        return False
    day = max(today, sub_start(s))
    if s["billing"] == "yearly":
        day = year_period(sub_start(s), day)[1] - timedelta(days=1)
    s["end"] = day.isoformat()
    return True


def reopen(data, item_id):
    item = find(data, item_id)
    if item["kind"] == "decision":
        item["decided"], item["outcome"] = "", ""
    elif item["billing"] not in FIXED_TERM:
        item["end"] = ""
    return item


def delete(data, item_id):
    data["items"].remove(find(data, item_id))


def data_path():
    """Next to the exe (or this file). If that folder is read-only, %APPDATA%\\StallMeter."""
    import sys
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    path = os.path.join(base, DATA_FILE)
    if os.access(path, os.W_OK) or (not os.path.exists(path) and os.access(base, os.W_OK)):
        return path
    alt = os.path.join(os.environ.get("APPDATA", base), APP_NAME)
    os.makedirs(alt, exist_ok=True)
    return os.path.join(alt, DATA_FILE)


def _check_shape(data):
    if not isinstance(data, dict):
        raise ValueError("bad shape")
    if "items" not in data and isinstance(data.get("decisions"), list):  # version 1 had decisions only
        data["items"] = [dict(d, kind="decision", category="Decisions") for d in data.pop("decisions")]
    if not isinstance(data.get("items"), list):
        raise ValueError("bad shape")
    for item in data["items"]:  # version 2 had one fixed-term kind called "total" and no installments
        if item.get("kind") == "sub":
            if item.get("billing") == "total":
                item["billing"] = "prepaid"
            item.setdefault("months", 0)
    names = [str(c) for c in data.get("categories") or []]
    for item in data["items"]:  # version 2 had no stored tab list
        if item["category"] not in names:
            names.append(item["category"])
    data["categories"] = names
    data["version"] = 3
    settings = dict(DEFAULT_SETTINGS)
    settings.update(data.get("settings") or {})
    data["settings"] = settings
    probe = datetime(2026, 1, 1)
    for item in data["items"]:
        keys = {"decision": DECISION_KEYS, "sub": SUB_KEYS}[item["kind"]]
        for key in keys:
            if key not in item:
                raise ValueError("missing " + key)
        if item["kind"] == "sub":
            if item["billing"] not in BILLINGS or (item["billing"] in FIXED_TERM and not item["end"]):
                raise ValueError("bad billing")
            if item["billing"] == "installment" and not 2 <= item["months"] <= 120:
                raise ValueError("bad installment")
            if not 1 <= item["target"] <= 7 or not isinstance(item["used"], list):
                raise ValueError("bad subscription")
            for day in item["used"]:
                date.fromisoformat(day)
        losses(item, probe)  # fails on any field the maths cannot read
    highest = max([item["id"] for item in data["items"]], default=0)
    data["next_id"] = max(int(data.get("next_id", 1)), highest + 1)
    return data


def load(path):
    """Returns (data, broken_copy). broken_copy is the path a damaged file was moved to, else None."""
    if not os.path.exists(path):
        return new_data(), None
    try:
        with open(path, encoding="utf-8") as fh:
            return _check_shape(json.load(fh)), None
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError, OSError):
        broken = path + ".broken"
        n = 1
        while os.path.exists(broken):
            n += 1
            broken = f"{path}.broken{n}"
        os.replace(path, broken)
        return new_data(), broken


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------- export ----------

def price_text(item, currency, t):
    if item["kind"] == "decision":
        return t("price_day", cost=format_money(daily_cost(item), currency, 0))
    if item["billing"] == "installment":
        return t("price_installment", cost=format_money(item["amount"] / item["months"], currency, 0),
                 n=item["months"])
    return t("price_" + item["billing"], cost=format_money(item["amount"], currency, 0))


def wasted_text(part):
    return "" if part["wasted"] is None else f"{part['wasted'] * 100:.0f}%"


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def report_markdown(data, now, t, category=None):
    """Loss report for every item, or for one category. `t(key, **kw)` returns text in the chosen language."""
    cur = data["settings"]["currency"]
    money = lambda v: format_money(v, cur, 0)  # noqa: E731
    items = in_category(data, category)
    s = summary(items, now)
    lines = [
        "# " + t("r_title") + (f" \u2014 {category}" if category else ""),
        "",
        t("r_generated", date=now.strftime("%Y-%m-%d %H:%M")),
        "",
        "- " + t("r_week", cost=money(s["week"])),
        "- " + t("r_month", cost=money(s["month"])),
        "- " + t("r_year", cost=money(s["year"])),
        "- " + t("r_total", cost=money(s["total"]), n=s["count"]),
        "",
        "## " + t("r_items_heading"),
        "",
    ]
    if items:
        head = [t("col_title"), t("col_category"), t("col_price"), t("col_week"), t("col_month"), t("col_year"),
                t("col_total"), t("col_wasted")]
        lines.append("| " + " | ".join(head) + " |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
        for item in sorted_items(items, now, True):
            part = losses(item, now)
            lines.append(f"| {_cell(item['title'])} | {_cell(item['category'])} | {price_text(item, cur, t)} | "
                         f"{money(part['week'])} | {money(part['month'])} | {money(part['year'])} | "
                         f"{money(part['total'])} | {wasted_text(part)} |")
    else:
        lines.append(t("r_none"))
    lines += ["", t("r_formula"), ""]
    return "\n".join(lines)


def export_csv(data, now):
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["id", "kind", "category", "title", "loss_week", "loss_month", "loss_year", "loss_total",
                "wasted_90d", "billing", "amount", "installment_months", "start", "end", "goal_days_per_week",
                "use_days",
                "owner", "people", "hourly_cost", "hours_per_day", "other_daily_loss", "opened", "due", "decided",
                "outcome"])
    for item in sorted_items(data["items"], now, True):
        part = losses(item, now)
        row = [item["id"], item["kind"], item["category"], item["title"]]
        row += [f"{part[k]:.2f}" for k in ("week", "month", "year", "total")]
        row.append("" if part["wasted"] is None else f"{part['wasted']:.3f}")
        if item["kind"] == "sub":
            row += [item["billing"], item["amount"], item["months"] or "", item["start"], item["end"],
                    item["target"], len(item["used"])]
            row += [""] * 9
        else:
            row += [""] * 7
            row += [item[k] for k in ("owner", "people", "rate", "hours", "extra", "opened", "due", "decided", "outcome")]
        w.writerow(row)
    return out.getvalue()
