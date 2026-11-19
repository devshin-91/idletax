import json
import os
import re
import tempfile
import unittest
from datetime import date, datetime

import core
import i18n

MON = datetime(2026, 1, 5, 0, 0)  # a Monday
EN = i18n.translator("en")


def fields(**kw):
    base = {"title": "Pick a vendor", "category": "Decisions", "owner": "Kim", "people": "4", "rate": "50",
            "hours": "2", "extra": "100", "opened": "2026-01-05", "due": "2026-01-09"}
    base.update(kw)
    return base


def sub(**kw):
    # November 2026 has 30 days and starts on a Sunday; Monday is the 2nd. 30000 a month = 1000 a day.
    base = {"title": "Gym", "category": "Health", "billing": "monthly", "amount": "30000", "months": "",
            "start": "2026-11-02", "end": "", "target": "3"}
    base.update(kw)
    return base


class TimeTests(unittest.TestCase):
    def test_weekdays_count(self):
        self.assertEqual(core.business_days(MON, datetime(2026, 1, 10)), 5.0)

    def test_weekend_does_not_count(self):
        self.assertEqual(core.business_days(datetime(2026, 1, 10), datetime(2026, 1, 12)), 0.0)
        self.assertEqual(core.business_days(MON, datetime(2026, 1, 19)), 10.0)

    def test_partial_day(self):
        self.assertEqual(core.business_days(datetime(2026, 1, 5, 12), datetime(2026, 1, 6, 6)), 0.75)
        self.assertEqual(core.business_days(datetime(2026, 1, 9, 18), datetime(2026, 1, 12, 6)), 0.5)

    def test_end_before_start(self):
        self.assertEqual(core.business_days(datetime(2026, 1, 6), MON), 0.0)

    def test_long_span_matches_week_count(self):
        self.assertEqual(core.business_days(MON, datetime(2027, 1, 4)), 52 * 5)

    def test_window_starts(self):
        week, month, year = core.window_starts(datetime(2026, 11, 12, 15, 30))  # a Thursday
        self.assertEqual((week, month, year), (datetime(2026, 11, 9), datetime(2026, 11, 1), datetime(2026, 1, 1)))


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.data = core.new_data()
        self.d = core.add_decision(self.data, fields())

    def test_daily_cost(self):
        self.assertEqual(core.daily_cost(self.d), 4 * 50 * 2 + 100)

    def test_accrued_grows_then_freezes(self):
        self.assertEqual(core.accrued(self.d, datetime(2026, 1, 7)), 1000)
        core.decide(self.data, self.d["id"], "Vendor B", datetime(2026, 1, 8))
        self.assertEqual(core.accrued(self.d, datetime(2026, 3, 1)), 1500)
        self.assertFalse(core.is_open(self.d, datetime(2026, 3, 1)))
        core.reopen(self.data, self.d["id"])
        self.assertEqual(core.accrued(self.d, datetime(2026, 1, 10)), 2500)

    def test_overdue_only_after_due_day_ends(self):
        self.assertFalse(core.is_overdue(self.d, datetime(2026, 1, 9, 23, 59)))
        self.assertTrue(core.is_overdue(self.d, datetime(2026, 1, 10, 0, 0)))
        core.decide(self.data, self.d["id"], "", datetime(2026, 1, 12))
        self.assertFalse(core.is_overdue(self.d, datetime(2026, 1, 20)))

    def test_losses_by_window(self):
        d = core.add_decision(self.data, fields(opened="2025-12-29"))  # Monday of the week before
        part = core.losses(d, datetime(2026, 1, 7))  # Wednesday 00:00
        self.assertEqual(part["week"], 2 * 500)    # Mon, Tue
        self.assertEqual(part["month"], 4 * 500)   # Thu 1, Fri 2, Mon 5, Tue 6
        self.assertEqual(part["year"], 4 * 500)
        self.assertEqual(part["total"], 7 * 500)   # Dec 29-31, Jan 1-2, Jan 5-6
        self.assertIsNone(part["wasted"])


class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.data = core.new_data()
        self.s = core.add_sub(self.data, sub())

    def missed(self, today):
        return core.sub_missed(self.s, today)

    def test_daily_price_monthly_and_total(self):
        self.assertEqual(core.sub_daily_price(self.s, date(2026, 11, 10)), 1000)
        self.assertEqual(core.sub_daily_price(self.s, date(2026, 12, 10)), 30000 / 31)
        two = core.add_sub(self.data, sub(billing="prepaid", amount="730000", start="2026-01-01", end="2027-12-31"))
        self.assertEqual(core.sub_daily_price(two, date(2026, 6, 1)), 1000)

    def test_yearly_price_follows_the_paid_year(self):
        y = core.add_sub(self.data, sub(billing="yearly", amount="365000", start="2026-03-01"))
        self.assertEqual(core.sub_daily_price(y, date(2026, 3, 1)), 1000)      # Mar 2026 - Feb 2027: 365 days
        self.assertEqual(core.sub_daily_price(y, date(2027, 2, 28)), 1000)
        self.assertEqual(core.sub_daily_price(y, date(2027, 3, 1)), 365000 / 366)  # next paid year holds Feb 29, 2028
        self.assertEqual(core.year_period(date(2024, 2, 29), date(2025, 2, 28)), (date(2025, 2, 28), date(2026, 2, 28)))

    def test_cancel_yearly_runs_to_the_end_of_the_paid_year(self):
        y = core.add_sub(self.data, sub(billing="yearly", amount="365000", start="2026-03-01"))
        self.assertTrue(core.cancel_sub(self.data, y["id"], date(2026, 11, 9)))
        self.assertEqual(y["end"], "2027-02-28")
        core.reopen(self.data, y["id"])
        self.assertEqual(y["end"], "")

    def test_installment_uses_the_total_over_the_term(self):
        # 12 installments from Nov 2: with no end date the term is the 12 months, Nov 2, 2026 - Nov 1, 2027 = 365 days
        inst = core.add_sub(self.data, sub(billing="installment", amount="730000", months="12"))
        self.assertEqual(inst["end"], "2027-11-01")
        self.assertEqual(core.sub_daily_price(inst, date(2026, 12, 25)), 2000)
        got = core.sub_missed(inst, date(2026, 11, 9))   # same unused week as the monthly case, twice the day price
        self.assertAlmostEqual(sum(loss for _, loss in got), 14000)
        self.assertEqual(core.price_text(inst, "$", EN), "$60,833/mo × 12")

    def test_installment_state(self):
        inst = core.add_sub(self.data, sub(billing="installment", amount="120000", months="12"))
        self.assertEqual(core.installment_state(inst, date(2026, 11, 1)), (0, 12, 120000))
        self.assertEqual(core.installment_state(inst, date(2026, 11, 2)), (1, 12, 110000))
        self.assertEqual(core.installment_state(inst, date(2027, 1, 1)), (2, 12, 100000))
        self.assertEqual(core.installment_state(inst, date(2028, 1, 1)), (12, 12, 0))

    def test_installment_term_can_differ_from_payments(self):
        # 6 installments for a 12-month membership: the loss still uses the 12-month term
        inst = core.add_sub(self.data, sub(billing="installment", amount="365000", months="6", end="2027-11-01"))
        self.assertEqual(core.sub_daily_price(inst, date(2027, 6, 1)), 1000)

    def test_add_months(self):
        self.assertEqual(core.add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(core.add_months(date(2026, 11, 2), 14), date(2028, 1, 2))

    def test_unused_week_loses_the_whole_week_price(self):
        got = self.missed(date(2026, 11, 9))
        self.assertEqual([d for d, _ in got], [date(2026, 11, 6), date(2026, 11, 7), date(2026, 11, 8)])
        self.assertAlmostEqual(sum(loss for _, loss in got), 7000)

    def test_days_off_within_goal_cost_nothing(self):
        for day in (2, 4, 6):
            self.assertTrue(core.set_use(self.data, self.s["id"], date(2026, 11, day), True, date(2026, 11, 9)))
        self.assertEqual(self.missed(date(2026, 11, 9)), [])

    def test_one_short_of_goal_is_one_missed_day(self):
        for day in (2, 3):
            core.set_use(self.data, self.s["id"], date(2026, 11, day), True, date(2026, 11, 9))
        got = self.missed(date(2026, 11, 9))
        self.assertEqual([d for d, _ in got], [date(2026, 11, 8)])
        self.assertAlmostEqual(got[0][1], 7000 / 3)

    def test_loss_only_when_goal_cannot_be_reached(self):
        self.assertEqual(self.missed(date(2026, 11, 6)), [])                       # Friday: Fri, Sat, Sun still open
        self.assertEqual([d for d, _ in self.missed(date(2026, 11, 7))], [date(2026, 11, 6)])  # Saturday

    def test_today_is_never_missed(self):
        self.assertNotIn(date(2026, 11, 9), [d for d, _ in self.missed(date(2026, 11, 9))])

    def test_every_day_goal(self):
        daily = core.add_sub(self.data, sub(title="Claude", target="7"))
        got = core.sub_missed(daily, date(2026, 11, 5))
        self.assertEqual([(d.day, loss) for d, loss in got], [(2, 1000), (3, 1000), (4, 1000)])

    def test_partial_first_week_scales_goal(self):
        late = core.add_sub(self.data, sub(start="2026-11-05"))  # Thursday: 4 days left, goal round(3*4/7) = 2
        got = core.sub_missed(late, date(2026, 11, 9))
        self.assertEqual([d.day for d, _ in got], [7, 8])
        self.assertAlmostEqual(sum(loss for _, loss in got), 4000)

    def test_end_date_stops_loss(self):
        core.cancel_sub(self.data, self.s["id"], date(2026, 11, 8))
        self.assertAlmostEqual(sum(loss for _, loss in self.missed(date(2026, 12, 25))), 7000)
        self.assertFalse(core.is_open(self.s, datetime(2026, 11, 9)))
        core.reopen(self.data, self.s["id"])
        self.assertTrue(core.is_open(self.s, datetime(2026, 11, 9)))

    def test_prepaid_cannot_end_early(self):
        for billing in core.FIXED_TERM:
            pre = core.add_sub(self.data, sub(billing=billing, months="12", end="2027-11-01"))
            self.assertFalse(core.cancel_sub(self.data, pre["id"], date(2026, 11, 8)))
            core.reopen(self.data, pre["id"])
            self.assertEqual(pre["end"], "2027-11-01")

    def test_cannot_mark_future_or_outside_term(self):
        today = date(2026, 11, 9)
        self.assertFalse(core.set_use(self.data, self.s["id"], date(2026, 11, 10), True, today))
        self.assertFalse(core.set_use(self.data, self.s["id"], date(2026, 11, 1), True, today))
        self.assertTrue(core.set_use(self.data, self.s["id"], today, True, today))
        self.assertTrue(core.set_use(self.data, self.s["id"], today, False, today))
        self.assertEqual(self.s["used"], [])

    def test_losses_windows_and_wasted(self):
        part = core.losses(self.s, datetime(2026, 11, 16, 9, 0))  # two unused weeks, then a Monday
        self.assertAlmostEqual(part["total"], 14000)
        self.assertAlmostEqual(part["month"], 14000)
        self.assertAlmostEqual(part["week"], 0)
        self.assertAlmostEqual(part["wasted"], 1.0)
        for day in (9, 11, 13):
            core.set_use(self.data, self.s["id"], date(2026, 11, day), True, date(2026, 11, 16))
        self.assertAlmostEqual(core.losses(self.s, datetime(2026, 11, 16, 9, 0))["wasted"], 0.5)

    def test_edit_keeps_use_days(self):
        core.set_use(self.data, self.s["id"], date(2026, 11, 3), True, date(2026, 11, 9))
        new = core.update_item(self.data, self.s["id"], sub(amount="40000"))
        self.assertEqual((new["id"], new["amount"], new["used"]), (self.s["id"], 40000, ["2026-11-03"]))


class AllItemsTests(unittest.TestCase):
    def setUp(self):
        self.data = core.new_data()
        self.gym = core.add_sub(self.data, sub())
        self.dec = core.add_decision(self.data, fields(opened="2026-11-09", due=""))
        self.now = datetime(2026, 11, 11)  # Wednesday 00:00

    def test_summary_adds_both_kinds(self):
        s = core.summary(self.data["items"], self.now)
        self.assertAlmostEqual(s["total"], 7000 + 1000)
        self.assertAlmostEqual(s["week"], 1000)
        self.assertEqual((s["count"], s["open_count"]), (2, 2))

    def test_summary_uses_cache(self):
        cache = {self.gym["id"]: {"week": 1, "month": 2, "year": 3, "total": 4, "wasted": None}}
        self.assertAlmostEqual(core.summary(self.data["items"], self.now, cache)["total"], 4 + 1000)

    def test_categories_and_filter(self):
        self.assertEqual(core.categories(self.data), ["Health", "Decisions"])
        self.assertEqual(core.in_category(self.data, "Health"), [self.gym])
        self.assertEqual(len(core.in_category(self.data, None)), 2)

    def test_tabs_add_rename_remove(self):
        self.assertEqual(core.add_category(self.data, "  Pets "), "Pets")
        core.add_category(self.data, "Pets")
        self.assertEqual(core.categories(self.data), ["Health", "Decisions", "Pets"])   # empty tab stays, no duplicate
        with self.assertRaises(core.FieldError):
            core.add_category(self.data, "  ")
        core.rename_category(self.data, "Health", "Fitness")
        self.assertEqual((core.categories(self.data), self.gym["category"]), (["Decisions", "Pets", "Fitness"], "Fitness"))
        core.rename_category(self.data, "Fitness", "Pets")                              # merge into an existing tab
        self.assertEqual((core.categories(self.data), self.gym["category"]), (["Decisions", "Pets"], "Pets"))
        self.assertEqual(core.remove_category(self.data, "Pets", "Other"), 1)           # the item is kept
        self.assertEqual((core.categories(self.data), self.gym["category"]), (["Decisions", "Other"], "Other"))
        self.assertEqual(core.remove_category(self.data, "Other", "Other"), -1)         # refuses, nothing lost
        self.assertEqual(len(self.data["items"]), 2)
        core.delete(self.data, self.gym["id"])
        self.assertEqual(core.remove_category(self.data, "Other", "Other"), 0)
        self.assertEqual(core.categories(self.data), ["Decisions"])

    def test_editing_into_a_new_tab_creates_it(self):
        core.update_item(self.data, self.gym["id"], sub(category="Sport"))
        self.assertEqual(core.categories(self.data), ["Health", "Decisions", "Sport"])

    def test_sample_loads_and_clears_without_touching_real_items(self):
        for lang in i18n.LANGS:
            data = core.new_data()
            mine = core.add_sub(data, sub(category=i18n.SAMPLE[lang]["subs"][0][1]))
            core.add_category(data, "My empty tab")
            core.load_sample(data, i18n.SAMPLE[lang], self.now)
            spec = i18n.SAMPLE[lang]
            self.assertEqual(len(data["items"]), 1 + len(spec["subs"]) + len(spec["decisions"]))
            self.assertTrue(core.has_sample(data))
            self.assertGreater(core.summary(data["items"], self.now)["total"], 0)
            self.assertEqual({s[2] for s in spec["subs"]}, set(core.BILLINGS))          # every way of paying is shown
            for name in {s[1] for s in spec["subs"]} | {d[1] for d in spec["decisions"]}:
                self.assertIn(name, i18n.presets(lang))                                # sample tabs are preset names
            core.clear_sample(data)
            self.assertEqual(data["items"], [mine])
            self.assertEqual(core.categories(data), [mine["category"], "My empty tab"])
            self.assertFalse(core.has_sample(data))

    def test_sample_currency_only_changes_for_an_empty_file(self):
        empty = core.new_data()
        core.load_sample(empty, i18n.SAMPLE["ko"], self.now)
        self.assertEqual(empty["settings"]["currency"], "₩")
        core.clear_sample(empty)
        self.assertEqual((empty["settings"]["currency"], empty["items"], empty["categories"]), ("$", [], []))
        core.load_sample(self.data, i18n.SAMPLE["ko"], self.now)   # self.data already holds the user's items
        self.assertEqual(self.data["settings"]["currency"], "$")

    def test_sort_open_first_by_loss(self):
        core.decide(self.data, self.dec["id"], "", self.now)
        self.assertEqual(core.sorted_items(self.data["items"], self.now), [self.gym])
        self.assertEqual(core.sorted_items(self.data["items"], self.now, True), [self.gym, self.dec])

    def test_format_money(self):
        self.assertEqual(core.format_money(1234.5, "$"), "$1,234.50")
        self.assertEqual(core.format_money(1234.5, "₩"), "₩1,234")


class InputTests(unittest.TestCase):
    def test_bad_decision_fields(self):
        for change, key in (({"title": "  "}, "err_title"), ({"category": ""}, "err_category"),
                            ({"people": "0"}, "err_people"), ({"people": "2.5"}, "err_people"),
                            ({"rate": "-1"}, "err_rate"), ({"rate": "nan"}, "err_rate"),
                            ({"hours": "0"}, "err_hours"), ({"hours": "25"}, "err_hours"),
                            ({"extra": "-5"}, "err_extra"), ({"opened": "yesterday"}, "err_opened"),
                            ({"due": "2026-13-01"}, "err_due")):
            with self.assertRaises(core.FieldError) as ctx:
                core.clean_decision(fields(**change))
            self.assertEqual(ctx.exception.key, key, change)

    def test_bad_sub_fields(self):
        for change, key in (({"title": ""}, "err_title"), ({"category": " "}, "err_category"),
                            ({"billing": "weekly"}, "err_billing"), ({"amount": "0"}, "err_amount"),
                            ({"amount": "abc"}, "err_amount"), ({"start": "soon"}, "err_start"),
                            ({"end": "2026-10-01"}, "err_end"), ({"end": "x"}, "err_end"),
                            ({"billing": "prepaid"}, "err_end_needed"), ({"billing": "total"}, "err_billing"),
                            ({"billing": "installment"}, "err_months"),
                            ({"billing": "installment", "months": "1"}, "err_months"),
                            ({"billing": "installment", "months": "121"}, "err_months"), ({"target": "0"}, "err_target"),
                            ({"target": "8"}, "err_target"), ({"target": "2.5"}, "err_target")):
            with self.assertRaises(core.FieldError) as ctx:
                core.clean_sub(sub(**change))
            self.assertEqual(ctx.exception.key, key, change)

    def test_every_error_key_has_text(self):
        with open(core.__file__, encoding="utf-8") as fh:
            source = fh.read()
        keys = set(re.findall(r'"(err_\w+)"', source))
        self.assertGreaterEqual(len(keys), 15)
        for key in keys:
            self.assertIn(key, i18n.STRINGS["en"])

    def test_update_decision_keeps_state(self):
        data = core.new_data()
        d = core.add_decision(data, fields())
        core.decide(data, d["id"], "ok", datetime(2026, 1, 8))
        new = core.update_item(data, d["id"], fields(title="Renamed"))
        self.assertEqual((new["id"], new["title"], new["outcome"]), (d["id"], "Renamed", "ok"))
        with self.assertRaises(core.FieldError):
            core.update_item(data, d["id"], fields(opened="2026-02-01"))

    def test_ids_do_not_repeat(self):
        data = core.new_data()
        a = core.add_decision(data, fields())
        core.delete(data, a["id"])
        self.assertNotEqual(core.add_sub(data, sub())["id"], a["id"])


class StorageTests(unittest.TestCase):
    def test_round_trip_and_no_tmp_left(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, core.DATA_FILE)
            data = core.new_data()
            core.add_decision(data, fields(title="한글 제목"))
            s = core.add_sub(data, sub())
            core.set_use(data, s["id"], date(2026, 11, 3), True, date(2026, 11, 9))
            core.save(path, data)
            loaded, broken = core.load(path)
            self.assertIsNone(broken)
            self.assertEqual(loaded, data)
            self.assertEqual(os.listdir(folder), [core.DATA_FILE])

    def test_version_1_file_is_upgraded(self):
        old = {"version": 1, "settings": {"currency": "$"}, "next_id": 2, "decisions": [
            {"id": 1, "title": "Old", "owner": "", "people": 2, "rate": 10.0, "hours": 1.0, "extra": 0.0,
             "opened": "2026-01-05T00:00", "due": "", "decided": "", "outcome": ""}]}
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, core.DATA_FILE)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(old, fh)
            data, broken = core.load(path)
            self.assertIsNone(broken)
            self.assertEqual((data["version"], data["items"][0]["kind"], data["items"][0]["category"]),
                             (3, "decision", "Decisions"))
            self.assertEqual(data["categories"], ["Decisions"])
            self.assertEqual(core.accrued(data["items"][0], datetime(2026, 1, 7)), 40)

    def test_version_2_file_is_upgraded(self):
        old = {"version": 2, "settings": {"currency": "$"}, "next_id": 3, "items": [
            {"id": 1, "kind": "sub", "category": "Health", "title": "Gym", "billing": "total", "amount": 365000.0,
             "start": "2026-01-01", "end": "2026-12-31", "target": 3, "used": ["2026-01-05"]},
            {"id": 2, "kind": "sub", "category": "Digital", "title": "Plan", "billing": "monthly", "amount": 30000.0,
             "start": "2026-11-02", "end": "", "target": 5, "used": []}]}
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, core.DATA_FILE)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(old, fh)
            data, broken = core.load(path)
            self.assertIsNone(broken)
            gym = data["items"][0]
            self.assertEqual((gym["billing"], gym["months"], gym["used"]), ("prepaid", 0, ["2026-01-05"]))
            self.assertEqual(core.sub_daily_price(gym, date(2026, 6, 1)), 1000)
            self.assertEqual(data["categories"], ["Health", "Digital"])

    def test_broken_file_is_kept(self):
        bad_sub = {"items": [dict(core.clean_sub(sub()), id=1, target=0)]}
        bad_inst = {"items": [dict(core.clean_sub(sub(billing="installment", months="12")), id=1, months=0)]}
        for content in ("{not json", '{"items": [{"id": 1, "kind": "sub"}]}', "[]", '{"items": [{"id": 1}]}',
                        json.dumps(bad_sub), json.dumps(bad_inst)):
            with tempfile.TemporaryDirectory() as folder:
                path = os.path.join(folder, core.DATA_FILE)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content)
                data, broken = core.load(path)
                self.assertEqual(data["items"], [], content)
                with open(broken, encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), content)
                self.assertFalse(os.path.exists(path))


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.data = core.new_data()
        core.add_sub(self.data, sub(title="Gym | downtown"))
        core.add_decision(self.data, fields(opened="2026-11-09", due=""))
        self.now = datetime(2026, 11, 11)

    def test_report_in_both_languages(self):
        for lang in i18n.LANGS:
            text = core.report_markdown(self.data, self.now, i18n.translator(lang))
            self.assertIn("$8,000", text)             # total: 7000 + 1000
            self.assertIn("Gym \\| downtown", text)   # table cell is escaped
            self.assertIn("78%", text)                # 7000 lost of the 9000 paid for Nov 2-10

    def test_report_for_one_category(self):
        text = core.report_markdown(self.data, self.now, EN, "Health")
        self.assertIn("$7,000", text)
        self.assertNotIn("Pick a vendor", text)

    def test_csv(self):
        rows = core.export_csv(self.data, self.now).strip().split("\n")
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(rows[0].split(",")), 25)
        self.assertEqual(len(rows[1].split(",")), 25)
        self.assertEqual(len(rows[2].split(",")), 25)
        self.assertIn(",7000.00,0.778,monthly,30000.0,,2026-11-02,", rows[1])
        self.assertIn(",1000.00,1000.00,1000.00,1000.00,,", rows[2])

    def test_price_text(self):
        gym, dec = self.data["items"]
        self.assertEqual(core.price_text(gym, "$", EN), "$30,000/mo")
        self.assertEqual(core.price_text(dec, "$", EN), "$500/day")


class I18nTests(unittest.TestCase):
    def test_same_keys_and_placeholders(self):
        en, ko = i18n.STRINGS["en"], i18n.STRINGS["ko"]
        self.assertEqual(set(en), set(ko))
        for key in en:
            self.assertEqual(sorted(re.findall(r"\{(\w+)\}", en[key])), sorted(re.findall(r"\{(\w+)\}", ko[key])), key)

    def test_weekday_labels(self):
        for lang in i18n.LANGS:
            self.assertEqual(len(i18n.STRINGS[lang]["cal_weekdays"].split()), 7)

    def test_presets_and_billing_labels(self):
        self.assertEqual(len(i18n.presets("en")), len(i18n.presets("ko")))
        for lang in i18n.LANGS:
            names = i18n.presets(lang)
            self.assertEqual(len(names), len(set(names)))
            self.assertIn(i18n.STRINGS[lang]["cat_decisions"], names)
            for billing in core.BILLINGS:
                self.assertIn("bill_" + billing, i18n.STRINGS[lang])
                self.assertIn("price_" + billing, i18n.STRINGS[lang])


if __name__ == "__main__":
    unittest.main()
