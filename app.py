"""StallMeter window. All logic lives in core.py; all text lives in i18n.py."""

import calendar
import os
import sys
from datetime import date, datetime, timedelta

import core
import i18n

BG, CARD, TEXT, MUTED, BORDER = "#f5f6f8", "#ffffff", "#1f2328", "#6b7280", "#e3e6ea"
ACCENT, ACCENT_DARK, ACCENT_SOFT = "#2563eb", "#1d4ed8", "#e6eeff"
RED, GREEN, PINK, GREY, STRIPE, SELECT, BANNER, HOVER = ("#c62828", "#2e7d32", "#f7cdc9", "#9aa0a6", "#fafbfc",
                                                         "#dbe7ff", "#fff6d6", "#eceef1")
DECISION_FORM = (("title", "f_title", "wide"), ("category", "f_category", "category"), ("owner", "f_owner", "wide"),
                 ("people", "f_people", "entry"), ("rate", "f_rate", "entry"), ("hours", "f_hours", "entry"),
                 ("extra", "f_extra", "entry"), ("opened", "f_opened", "entry"), ("due", "f_due", "entry"))
SUB_FORM = (("title", "f_sub_title", "wide"), ("category", "f_category", "category"),
            ("billing", "f_billing", "billing"), ("amount", "f_amount", "entry"), ("months", "f_months", "months"),
            ("start", "f_start", "entry"), ("end", "f_end", "entry"), ("target", "f_target", "entry"))
COLUMNS = (("title", 28, "w"), ("category", 18, "w"), ("price", 23, "e"), ("week", 11, "e"), ("month", 11, "e"),
           ("year", 12, "e"), ("total", 12, "e"), ("wasted", 13, "e"), ("status", 40, "w"))
CARDS = ("week", "month", "year", "total")


def system_language():
    try:
        import ctypes
        return "ko" if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x12 else "en"
    except Exception:  # noqa: BLE001 - not Windows, or the call is unavailable
        return "en"


class App:
    def __init__(self, root, path):
        import tkinter as tk
        from tkinter import font as tkfont
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root = root
        self.path = path
        self.data, broken = core.load(path)
        if self.data["settings"]["lang"] not in i18n.LANGS:
            self.data["settings"]["lang"] = system_language()
        self.show_closed = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="")
        self.tab_category = None  # None is the "All" tab
        self.cache = {}
        self.today = date.today()
        self.resize_job = None

        family = "Segoe UI" if "Segoe UI" in tkfont.families() else tkfont.nametofont("TkDefaultFont").cget("family")
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(name).configure(family=family, size=10)
        self.f_base = tkfont.nametofont("TkDefaultFont")
        self.f_small = tkfont.Font(family=family, size=9)
        self.f_bold = tkfont.Font(family=family, size=10, weight="bold")
        self.f_title = tkfont.Font(family=family, size=15, weight="bold")
        self.f_value = tkfont.Font(family=family, size=20, weight="bold")
        self.unit = self.f_base.measure("0")
        self.width = self.unit * 205
        self.style()
        root.configure(bg=BG)
        root.geometry(f"{self.width}x{int(self.f_base.metrics('linespace') * 44)}")
        root.minsize(self.unit * 130, int(self.f_base.metrics("linespace") * 30))
        root.bind("<Configure>", self.on_resize)
        self.build()
        if broken:
            from tkinter import messagebox
            messagebox.showwarning(self.t("app_title"), self.t("broken_notice", path=broken))
        self.tick()

    def style(self):
        s = self.ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, font=self.f_base)
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=TEXT)
        s.configure("TCheckbutton", background=BG, foreground=MUTED)
        s.map("TCheckbutton", background=[("active", BG)])
        s.configure("TEntry", fieldbackground=CARD, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=5)
        s.configure("TCombobox", fieldbackground=CARD, background=CARD, bordercolor=BORDER, lightcolor=BORDER,
                    darkcolor=BORDER, arrowcolor=MUTED, padding=5)
        s.map("TCombobox", fieldbackground=[("readonly", CARD)], selectbackground=[("readonly", CARD)],
              selectforeground=[("readonly", TEXT)])
        s.map("TEntry", fieldbackground=[("disabled", BG)], foreground=[("disabled", GREY)])
        s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, borderwidth=0,
                    rowheight=int(self.f_base.metrics("linespace") * 2.1))
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # no frame around the rows
        s.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", TEXT)])
        s.configure("Treeview.Heading", background=CARD, foreground=MUTED, relief="flat", font=self.f_small,
                    padding=(8, 9), borderwidth=0)
        s.map("Treeview.Heading", background=[("active", CARD)])
        s.configure("Vertical.TScrollbar", background="#d5d9df", troughcolor=CARD, bordercolor=CARD, lightcolor=CARD,
                    darkcolor=CARD, arrowcolor=MUTED, relief="flat")

    # ----- helpers -----

    @property
    def t(self):
        return i18n.translator(self.data["settings"]["lang"])

    @property
    def lang(self):
        return self.data["settings"]["lang"]

    @property
    def currency(self):
        return self.data["settings"]["currency"]

    def money(self, value, decimals=0):
        return core.format_money(value, self.currency, decimals)

    def save(self):
        try:
            core.save(self.path, self.data)
        except OSError as exc:
            self.status.set(self.t("save_failed", error=exc))

    def selected(self, kind=None):
        """The selected item, or None after telling the user what to select."""
        sel = self.tree.selection()
        item = core.find(self.data, int(sel[0])) if sel else None
        if item is None or (kind and item["kind"] != kind):
            self.status.set(self.t("select_sub" if kind == "sub" else "select_first"))
            return None
        return item

    def button(self, parent, text, command, kind="plain", bg=None):
        """A flat button. primary: filled. plain: white with a thin border. ghost: text only. pill: a tab."""
        if bg is None:
            try:
                bg = parent.cget("bg")
            except self.tk.TclError:  # a ttk frame has no bg option; ttk frames here use the window colour
                bg = BG
        plain = ("#eef0f3", TEXT, BORDER, 0) if bg == CARD else (CARD, TEXT, HOVER, 1)  # stay visible on white
        look = {"primary": (ACCENT, "white", ACCENT_DARK, 0), "plain": plain,
                "ghost": (bg, ACCENT, ACCENT_SOFT, 0), "pill": (bg, TEXT, HOVER, 0),
                "pill_on": (ACCENT, "white", ACCENT_DARK, 0)}[kind]
        normal, fg, hover, border = look
        b = self.tk.Button(parent, text=text, command=command, relief="flat", bd=0, bg=normal, fg=fg,
                           activebackground=hover, activeforeground=fg, font=self.f_base, padx=13, pady=5,
                           cursor="hand2", highlightthickness=border, highlightbackground=BORDER, takefocus=0)
        b.bind("<Enter>", lambda e: b.configure(bg=hover))
        b.bind("<Leave>", lambda e: b.configure(bg=normal))
        return b

    def dialog(self, title):
        win = self.tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self.root)
        win.resizable(False, False)
        frame = self.ttk.Frame(win, padding=20)
        frame.pack(fill="both", expand=True)
        win.bind("<Escape>", lambda e: win.destroy())
        return win, frame

    def dialog_buttons(self, win, frame, row, ok):
        buttons = self.ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=2, sticky="e", pady=(14, 0))
        self.button(buttons, self.t("cancel"), win.destroy).pack(side="right")
        self.button(buttons, self.t("ok"), ok, "primary").pack(side="right", padx=8)
        win.bind("<Return>", ok)
        win.grab_set()
        win.focus_set()

    # ----- layout -----

    def build(self):
        tk, ttk, t = self.tk, self.ttk, self.t
        for child in self.root.winfo_children():
            child.destroy()
        self.root.title(t("app_title"))

        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=24, pady=(18, 6))
        names = tk.Frame(top, bg=BG)
        names.pack(side="left")
        tk.Label(names, text=t("app_title"), font=self.f_title, bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(names, text=t("tagline"), font=self.f_small, bg=BG, fg=MUTED).pack(anchor="w")
        for key, cmd in (("btn_lang", self.toggle_lang), ("btn_settings", self.settings),
                         ("btn_csv", self.export_csv), ("btn_report", self.export_report)):
            self.button(top, t(key), cmd, "ghost").pack(side="right", padx=(4, 0))

        self.banner_slot = tk.Frame(self.root, bg=BG)
        self.banner_slot.pack(fill="x", padx=24)

        cards = tk.Frame(self.root, bg=BG)
        cards.pack(fill="x", padx=24, pady=(8, 4))
        self.card = {}
        for index, key in enumerate(CARDS):
            box = tk.Frame(cards, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
            box.grid(row=0, column=index, sticky="nsew", padx=(0, 12) if index < 3 else 0)
            cards.columnconfigure(index, weight=1, uniform="card")
            tk.Label(box, text=t("col_" + key), font=self.f_small, bg=CARD, fg=MUTED).pack(anchor="w", padx=16,
                                                                                         pady=(12, 0))
            self.card[key] = tk.Label(box, text="", font=self.f_value, bg=CARD, fg=RED if key == "year" else TEXT)
            self.card[key].pack(anchor="w", padx=16, pady=(0, 12))

        self.tabbar = tk.Frame(self.root, bg=BG)
        self.tabbar.pack(fill="x", padx=24, pady=(12, 2))

        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=24, pady=(6, 8))
        self.button(bar, t("btn_new_sub"), self.new_sub, "primary").pack(side="left")
        self.button(bar, t("btn_new_decision"), self.new_decision).pack(side="left", padx=(8, 20))
        for key, cmd in (("btn_edit", self.edit), ("btn_calendar", self.calendar), ("btn_used", self.used_today),
                         ("btn_end", self.end), ("btn_reopen", self.reopen), ("btn_delete", self.delete)):
            self.button(bar, t(key), cmd).pack(side="left", padx=(0, 6))
        ttk.Checkbutton(bar, text=t("show_closed"), variable=self.show_closed, command=self.refresh).pack(side="right")

        # the footer is packed before the list so the list cannot push it out of a short window
        foot = tk.Frame(self.root, bg=BG)
        foot.pack(side="bottom", fill="x", padx=24, pady=(4, 12))
        tk.Label(foot, text=t("shortcuts"), font=self.f_small, bg=BG, fg=GREY).pack(side="left")
        tk.Label(foot, textvariable=self.status, font=self.f_small, bg=BG, fg=MUTED).pack(side="right")

        self.body = tk.Frame(self.root, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        self.body.pack(fill="both", expand=True, padx=24)
        self.table = tk.Frame(self.body, bg=CARD)
        self.tree = ttk.Treeview(self.table, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse")
        for key, width, anchor in COLUMNS:
            self.tree.heading(key, text=t("col_" + key), anchor=anchor)
            self.tree.column(key, width=width * self.unit, anchor=anchor, stretch=(key in ("title", "status")))
        self.tree.tag_configure("stripe", background=STRIPE)
        self.tree.tag_configure("alert", foreground=RED)
        self.tree.tag_configure("closed", foreground=GREY)
        scroll = ttk.Scrollbar(self.table, orient="vertical", command=self.tree.yview)

        def on_scroll(first, last):  # the scrollbar shows only when the rows do not fit
            scroll.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                scroll.pack_forget()
            elif not scroll.winfo_manager():
                scroll.pack(side="right", fill="y", before=self.tree)

        self.tree.configure(yscrollcommand=on_scroll)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(2, 6))

        self.empty = tk.Frame(self.body, bg=CARD)
        middle = tk.Frame(self.empty, bg=CARD)
        middle.place(relx=0.5, rely=0.45, anchor="center")
        tk.Label(middle, text=t("empty_title"), font=self.f_title, bg=CARD, fg=TEXT).pack()
        tk.Label(middle, text=t("empty_body"), font=self.f_base, bg=CARD, fg=MUTED, justify="center").pack(pady=(6, 16))
        row = tk.Frame(middle, bg=CARD)
        row.pack()
        self.button(row, t("btn_sample"), self.load_sample, "primary").pack(side="left", padx=4)
        self.button(row, t("btn_new_sub"), self.new_sub).pack(side="left", padx=4)

        r = self.root
        r.bind("<Control-n>", lambda e: self.new_sub())
        r.bind("<Control-N>", lambda e: self.new_decision())  # Ctrl+Shift+N
        r.bind("<Control-t>", lambda e: self.tab_add())
        r.bind("<Control-k>", lambda e: self.calendar())
        r.bind("<Control-u>", lambda e: self.used_today())
        r.bind("<Control-d>", lambda e: self.end())
        r.bind("<Control-e>", lambda e: self.export_report())
        r.bind("<Control-l>", lambda e: self.toggle_lang())
        self.tree.bind("<Return>", lambda e: self.edit())
        self.tree.bind("<Double-1>", lambda e: self.edit())
        self.tree.bind("<Delete>", lambda e: self.delete())
        self.refresh()

    def on_resize(self, event):
        if event.widget is self.root and event.width != self.width:
            self.width = event.width
            if self.resize_job:
                self.root.after_cancel(self.resize_job)
            self.resize_job = self.root.after(120, self.draw_tabs)  # the tab row wraps to the new width

    def draw_tabs(self):
        """All, one pill per tab, then the buttons that add, rename and remove tabs. Wraps to more rows."""
        tk, t = self.tk, self.t
        self.resize_job = None
        for child in self.tabbar.winfo_children():
            child.destroy()
        limit = self.width - 48
        state = {"row": None, "used": 0}

        def place(text, command, kind):
            need = self.f_base.measure(text) + 34
            if state["row"] is None or (state["used"] and state["used"] + need > limit):
                state["row"] = tk.Frame(self.tabbar, bg=BG)
                state["row"].pack(fill="x", anchor="w", pady=1)
                state["used"] = 0
            self.button(state["row"], text, command, kind, BG).pack(side="left", padx=(0, 4))
            state["used"] += need

        self.tab_names = [None] + core.categories(self.data)
        for name in self.tab_names:
            place(name or t("tab_all"), lambda n=name: self.select_tab(n),
                  "pill_on" if name == self.tab_category else "pill")
        place(t("btn_tab_add"), self.tab_add, "ghost")
        if self.tab_category is not None:
            place(t("btn_tab_rename"), self.tab_rename, "ghost")
            place(t("btn_tab_remove"), self.tab_remove, "ghost")

    def draw_banner(self):
        for child in self.banner_slot.winfo_children():
            child.destroy()
        if core.has_sample(self.data):
            strip = self.tk.Frame(self.banner_slot, bg=BANNER, highlightthickness=1, highlightbackground="#ecdca0")
            strip.pack(fill="x", pady=(4, 2))
            self.tk.Label(strip, text=self.t("sample_banner"), bg=BANNER, fg=TEXT, font=self.f_base).pack(
                side="left", padx=14, pady=6)
            self.button(strip, self.t("btn_sample_clear"), self.clear_sample, "ghost").pack(side="right", padx=8)
        else:
            self.tk.Frame(self.banner_slot, bg=BG, height=1).pack()  # lets the slot shrink back

    def select_tab(self, name):
        self.tab_category = name
        self.refresh()

    def part(self, item, now):
        return self.cache.get(item["id"]) or core.losses(item, now)

    def status_text(self, item, now):
        t = self.t
        if item["kind"] == "sub":
            if not core.is_open(item, now):
                return t("st_ended", date=item["end"])
            text = (t("st_goal_until", n=item["target"], date=item["end"]) if item["end"]
                    else t("st_goal", n=item["target"]))
            if item["billing"] == "installment":
                paid, count, left = core.installment_state(item, now.date())
                text += "  ·  " + t("st_installment", paid=paid, n=count, left=self.money(left))
            return text
        if item["decided"]:
            return t("status_decided", date=item["decided"][:10])
        if core.is_overdue(item, now):
            return t("overdue", date=item["due"])
        if item["due"]:
            return t("st_due", date=item["due"])
        return t("st_waiting", owner=item["owner"]) if item["owner"] else ""

    def row(self, item, now):
        part = self.part(item, now)
        values = (item["title"], item["category"], core.price_text(item, self.currency, self.t),
                  self.money(part["week"]), self.money(part["month"]), self.money(part["year"]),
                  self.money(part["total"]), core.wasted_text(part), self.status_text(item, now))
        if not core.is_open(item, now):
            tag = "closed"
        elif core.is_overdue(item, now) or (part["wasted"] or 0) >= 0.5:
            tag = "alert"
        else:
            tag = "normal"
        return values, tag

    def refresh(self, keep=None):
        now = datetime.now()
        self.today = now.date()
        if keep is None and self.tree.selection():
            keep = int(self.tree.selection()[0])
        if self.tab_category not in core.categories(self.data):
            self.tab_category = None
        self.draw_tabs()
        self.draw_banner()
        # subscription losses change only when the data or the date changes, so they are computed once here
        self.cache = {i["id"]: core.losses(i, now) for i in self.data["items"] if i["kind"] == "sub"}
        self.tree.delete(*self.tree.get_children())
        if self.data["items"]:
            self.empty.pack_forget()
            self.table.pack(fill="both", expand=True)
        else:
            self.table.pack_forget()
            self.empty.pack(fill="both", expand=True)
        items = core.in_category(self.data, self.tab_category)
        for index, item in enumerate(core.sorted_items(items, now, self.show_closed.get(), self.cache)):
            values, tag = self.row(item, now)
            self.tree.insert("", "end", iid=str(item["id"]), values=values,
                             tags=(tag, "stripe") if index % 2 else (tag,))
        if keep is not None and self.tree.exists(str(keep)):
            self.tree.selection_set(str(keep))
            self.tree.focus(str(keep))
        self.update_cards(now)

    def update_cards(self, now):
        s = core.summary(core.in_category(self.data, self.tab_category), now, self.cache)
        for key in CARDS:
            self.card[key].configure(text=self.money(s[key]))

    def tick(self):
        now = datetime.now()
        if now.date() != self.today:
            self.refresh()  # a new day can add missed days
        else:
            self.update_cards(now)
            for item in self.data["items"]:
                iid = str(item["id"])
                if item["kind"] == "decision" and not item["decided"] and self.tree.exists(iid):
                    self.tree.item(iid, values=self.row(item, now)[0])
        self.root.after(500, self.tick)

    # ----- tabs and sample -----

    def ask_name(self, title, initial, choices, apply):
        """A one-field dialog. `apply(name)` may raise FieldError."""
        win, frame = self.dialog(title)
        var = self.tk.StringVar(value=initial)
        self.ttk.Label(frame, text=self.t("f_tab_name")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        box = self.ttk.Combobox(frame, textvariable=var, values=choices, width=40)
        box.grid(row=1, column=0, columnspan=2, sticky="w")
        error = self.ttk.Label(frame, text="", foreground=RED)
        error.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def ok(*_):
            try:
                apply(var.get())
            except core.FieldError as exc:
                error.configure(text=self.t(exc.key))
                return
            self.save()
            win.destroy()
            self.refresh()

        self.dialog_buttons(win, frame, 3, ok)
        box.focus_set()
        return win

    def unused_presets(self):
        return [n for n in i18n.presets(self.lang) if n not in core.categories(self.data)]

    def tab_add(self):
        def apply(name):
            self.tab_category = core.add_category(self.data, name)
        return self.ask_name(self.t("dlg_tab_add"), "", self.unused_presets(), apply)

    def tab_rename(self):
        old = self.tab_category
        if old is None:
            self.status.set(self.t("select_tab"))
            return None

        def apply(name):
            self.tab_category = core.rename_category(self.data, old, name)
        return self.ask_name(self.t("dlg_tab_rename"), old, self.unused_presets(), apply)

    def tab_remove(self):
        from tkinter import messagebox
        name = self.tab_category
        if name is None:
            self.status.set(self.t("select_tab"))
            return
        count = len(core.in_category(self.data, name))
        fallback = self.t("tab_fallback")
        if count and name == fallback:
            self.status.set(self.t("tab_remove_fallback"))
            return
        question = (self.t("confirm_tab_remove", name=name, n=count, fallback=fallback) if count
                    else self.t("confirm_tab_remove_empty", name=name))
        if messagebox.askyesno(self.t("app_title"), question, parent=self.root):
            core.remove_category(self.data, name, fallback)
            self.tab_category = None
            self.save()
            self.refresh()

    def load_sample(self):
        if not core.has_sample(self.data):
            core.load_sample(self.data, i18n.SAMPLE[self.lang], datetime.now())
            self.save()
            self.refresh()

    def clear_sample(self):
        core.clear_sample(self.data)
        self.save()
        self.refresh()

    # ----- forms -----

    def default_tab(self, fallback):
        return self.tab_category or (core.categories(self.data) or [fallback])[0]

    def new_sub(self):
        fields = {"title": "", "category": self.default_tab(i18n.presets(self.lang)[0]), "billing": "monthly",
                  "amount": "", "months": "12", "start": date.today().isoformat(), "end": "", "target": "3"}
        return self.form(self.t("dlg_new_sub"), SUB_FORM, fields, lambda f: core.add_sub(self.data, f), "sub")

    def new_decision(self):
        s = self.data["settings"]
        fields = {"title": "", "category": self.tab_category or self.t("cat_decisions"), "owner": "", "people": "3",
                  "rate": f"{s['default_rate']:g}", "hours": f"{s['default_hours']:g}", "extra": "",
                  "opened": date.today().isoformat(), "due": ""}
        return self.form(self.t("dlg_new"), DECISION_FORM, fields, lambda f: core.add_decision(self.data, f), "decision")

    def edit(self):
        item = self.selected()
        if item is None:
            return None
        apply = lambda f: core.update_item(self.data, item["id"], f)  # noqa: E731
        if item["kind"] == "sub":
            fields = {"title": item["title"], "category": item["category"], "billing": item["billing"],
                      "amount": f"{item['amount']:g}", "months": str(item["months"] or 12), "start": item["start"],
                      "end": item["end"], "target": str(item["target"])}
            return self.form(self.t("dlg_edit_sub"), SUB_FORM, fields, apply, "sub")
        opened = item["opened"].replace("T", " ")
        if opened.endswith(" 00:00"):
            opened = opened[:10]
        fields = {"title": item["title"], "category": item["category"], "owner": item["owner"],
                  "people": str(item["people"]), "rate": f"{item['rate']:g}", "hours": f"{item['hours']:g}",
                  "extra": f"{item['extra']:g}" if item["extra"] else "", "opened": opened, "due": item["due"]}
        return self.form(self.t("dlg_edit"), DECISION_FORM, fields, apply, "decision")

    def form(self, title, spec, fields, apply, kind):
        tk, ttk, t = self.tk, self.ttk, self.t
        win, frame = self.dialog(title)
        billing_labels = {t("bill_" + b): b for b in core.BILLINGS}
        entries, months_box = {}, None
        for row, (key, label, widget) in enumerate(spec):
            ttk.Label(frame, text=t(label), foreground=MUTED).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 14))
            var = tk.StringVar(value=fields[key])
            if widget == "category":
                names = core.categories(self.data)
                names += [n for n in i18n.presets(self.lang) if n not in names]
                box = ttk.Combobox(frame, textvariable=var, values=names, width=42)
            elif widget == "billing":
                var.set(t("bill_" + fields[key]))
                box = ttk.Combobox(frame, textvariable=var, values=list(billing_labels), width=42, state="readonly")
            else:
                box = ttk.Entry(frame, textvariable=var, width=45 if widget == "wide" else 18)
                if widget == "months":
                    months_box = box
            box.grid(row=row, column=1, sticky="w", pady=4)
            entries[key] = var
        base = len(spec)
        preview = ttk.Label(frame, text="", foreground=RED)
        preview.grid(row=base, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(frame, text=t("f_sub_hint" if kind == "sub" else "f_hint"), foreground=MUTED, font=self.f_small,
                  wraplength=self.unit * 80, justify="left").grid(row=base + 1, column=0, columnspan=2, sticky="w")
        error = ttk.Label(frame, text="", foreground=RED)
        error.grid(row=base + 2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def collect():
            out = {k: v.get() for k, v in entries.items()}
            if "billing" in out:
                out["billing"] = billing_labels.get(out["billing"], "")
            return out

        def show_preview(*_):
            probe = collect()
            probe["title"] = probe["title"] or "-"
            probe["category"] = probe["category"] or "-"
            if months_box is not None:  # the installment count only matters for installments
                months_box.configure(state="normal" if probe["billing"] == "installment" else "disabled")
            try:
                if kind == "sub":
                    s = core.clean_sub(probe)
                    day = max(core.sub_start(s), min(date.today(), core.sub_end(s) or date.today()))
                    cost = self.money(core.sub_daily_price(s, day) * 7 / s["target"])
                    if s["billing"] == "installment":
                        preview.configure(text=t("preview_installment", cost=cost, n=s["months"],
                                                 per=self.money(s["amount"] / s["months"])))
                    else:
                        preview.configure(text=t("preview_sub", cost=cost))
                else:
                    preview.configure(text=t("preview", cost=self.money(core.daily_cost(core.clean_decision(probe)))))
            except core.FieldError:
                preview.configure(text="")

        for var in entries.values():
            var.trace_add("write", show_preview)
        show_preview()

        def ok(*_):
            try:
                item = apply(collect())
            except core.FieldError as exc:
                error.configure(text=t(exc.key))
                return
            self.save()
            win.destroy()
            if self.tab_category is not None:
                self.tab_category = item["category"]  # follow the item if it moved to another tab
            self.refresh(keep=item["id"])

        self.dialog_buttons(win, frame, base + 3, ok)
        return win

    # ----- calendar -----

    def calendar(self):
        tk, ttk, t = self.tk, self.ttk, self.t
        item = self.selected("sub")
        if item is None:
            return None
        item_id = item["id"]
        win, frame = self.dialog(t("cal_title", title=item["title"]))
        shown = {"month": date.today().replace(day=1)}
        nav = ttk.Frame(frame)
        nav.pack(fill="x")
        label = ttk.Label(nav, text="", font=self.f_bold, anchor="center")
        grid = tk.Frame(frame, bg=BG)
        grid.pack(pady=10)
        summary = ttk.Label(frame, text="", foreground=RED)
        summary.pack(anchor="w")
        ttk.Label(frame, text=t("cal_hint"), foreground=MUTED, font=self.f_small).pack(anchor="w")

        def move(step):
            first = shown["month"]
            shown["month"] = (first + timedelta(days=31) if step > 0 else first - timedelta(days=1)).replace(day=1)
            draw()

        self.button(nav, "‹", lambda: move(-1)).pack(side="left")
        self.button(nav, "›", lambda: move(1)).pack(side="right")
        label.pack(side="left", expand=True, fill="x")

        def toggle(day):
            s = core.find(self.data, item_id)
            if core.set_use(self.data, item_id, day, day.isoformat() not in s["used"], date.today()):
                self.save()
                draw()
                self.refresh(keep=item_id)

        def draw():
            for child in grid.winfo_children():
                child.destroy()
            s = core.find(self.data, item_id)
            today, first = date.today(), shown["month"]
            missed = dict(core.sub_missed(s, today))
            label.configure(text=first.strftime("%Y-%m"))
            for col, name in enumerate(t("cal_weekdays").split()):
                tk.Label(grid, text=name, width=5, bg=BG, fg=MUTED, font=self.f_small).grid(row=0, column=col, pady=(0, 4))
            used_count = 0
            for r, week in enumerate(calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)):
                for col, day in enumerate(week):
                    if day.month != first.month:
                        continue
                    used = day.isoformat() in s["used"]
                    used_count += used
                    bg, fg = (GREEN, "white") if used else (PINK, TEXT) if day in missed else (CARD, TEXT)
                    if day == today and not used:
                        bg, fg = ACCENT_SOFT, ACCENT  # today stands out until it is marked
                    cell = tk.Button(grid, text=str(day.day), width=4, relief="flat", bd=0, bg=bg, fg=fg,
                                     activebackground=bg, activeforeground=fg, disabledforeground="#c3c7cd",
                                     font=self.f_bold if day == today else self.f_base, pady=5, cursor="hand2",
                                     command=lambda d=day: toggle(d))
                    if not core.sub_can_mark(s, day, today):
                        cell.configure(state="disabled", cursor="arrow", bg=BG)
                    cell.grid(row=r + 1, column=col, padx=2, pady=2)
            month_missed = [loss for day, loss in missed.items() if (day.year, day.month) == (first.year, first.month)]
            summary.configure(text=t("cal_summary", used=used_count, missed=len(month_missed),
                                     cost=self.money(sum(month_missed))))

        draw()
        win.bind("<Left>", lambda e: move(-1))
        win.bind("<Right>", lambda e: move(1))
        win.grab_set()
        win.focus_set()
        return win

    # ----- actions -----

    def used_today(self):
        item = self.selected("sub")
        if item is None:
            return
        if core.set_use(self.data, item["id"], date.today(), True, date.today()):
            self.save()
            self.refresh(keep=item["id"])
            self.status.set(self.t("marked_used", title=item["title"]))

    def end(self):
        from tkinter import messagebox, simpledialog
        item = self.selected()
        if item is None or not core.is_open(item, datetime.now()):
            return
        if item["kind"] == "decision":
            outcome = simpledialog.askstring(self.t("ask_outcome_title"), self.t("ask_outcome"), parent=self.root)
            if outcome is None:
                return
            core.decide(self.data, item["id"], outcome, datetime.now())
        elif item["billing"] in core.FIXED_TERM:
            self.status.set(self.t("prepaid_no_end"))
            return
        else:
            key = "confirm_cancel_yearly" if item["billing"] == "yearly" else "confirm_cancel"
            if not messagebox.askyesno(self.t("app_title"), self.t(key, title=item["title"]), parent=self.root):
                return
            core.cancel_sub(self.data, item["id"], date.today())
        self.save()
        self.refresh()

    def reopen(self):
        item = self.selected()
        if item is None:
            return
        core.reopen(self.data, item["id"])
        self.save()
        self.refresh(keep=item["id"])

    def delete(self):
        from tkinter import messagebox
        item = self.selected()
        if item is None:
            return
        if messagebox.askyesno(self.t("app_title"), self.t("confirm_delete", title=item["title"]), parent=self.root):
            core.delete(self.data, item["id"])
            self.save()
            self.refresh()

    def toggle_lang(self):
        s = self.data["settings"]
        s["lang"] = "ko" if s["lang"] == "en" else "en"
        self.save()
        self.status.set("")
        self.build()

    def settings(self):
        tk, ttk, t = self.tk, self.ttk, self.t
        s = self.data["settings"]
        win, frame = self.dialog(t("settings_title"))
        values = {"currency": tk.StringVar(value=s["currency"]), "rate": tk.StringVar(value=f"{s['default_rate']:g}"),
                  "hours": tk.StringVar(value=f"{s['default_hours']:g}")}
        for row, key in enumerate(("currency", "rate", "hours")):
            ttk.Label(frame, text=t("s_" + key), foreground=MUTED).grid(row=row, column=0, sticky="w", pady=4,
                                                                       padx=(0, 14))
            ttk.Entry(frame, textvariable=values[key], width=12).grid(row=row, column=1, sticky="w", pady=4)
        error = ttk.Label(frame, text="", foreground=RED)
        error.grid(row=3, column=0, columnspan=2, sticky="w")

        def ok(*_):
            try:
                currency = values["currency"].get().strip()
                if not 1 <= len(currency) <= 4:
                    raise core.FieldError("err_currency")
                probe = core.clean_decision({"title": "-", "category": "-", "people": "1", "rate": values["rate"].get(),
                                             "hours": values["hours"].get(), "opened": "2026-01-01"})
            except core.FieldError as exc:
                error.configure(text=t(exc.key))
                return
            s["currency"], s["default_rate"], s["default_hours"] = currency, probe["rate"], probe["hours"]
            self.save()
            win.destroy()
            self.refresh()

        self.dialog_buttons(win, frame, 4, ok)
        return win

    def export(self, text, default_name, extension, encoding):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(parent=self.root, initialfile=default_name, defaultextension=extension,
                                            filetypes=[(extension.lstrip(".").upper(), "*" + extension)])
        if not path:
            return
        try:
            with open(path, "w", encoding=encoding, newline="") as fh:
                fh.write(text)
            self.status.set(self.t("saved_to", path=path))
        except OSError as exc:
            self.status.set(self.t("save_failed", error=exc))

    def export_report(self):
        now = datetime.now()
        text = core.report_markdown(self.data, now, self.t, self.tab_category)
        self.export(text, f"stallmeter-report-{now:%Y-%m-%d}.md", ".md", "utf-8")

    def export_csv(self):
        now = datetime.now()
        # utf-8-sig so Excel opens Korean text correctly
        self.export(core.export_csv(self.data, now), f"stallmeter-{now:%Y-%m-%d}.csv", ".csv", "utf-8-sig")


def smoke(folder):
    """Does a small piece of real work without showing a window. Returns an exit code."""
    log = os.path.join(folder, "smoke.log")
    try:
        import tkinter as tk
        path = os.path.join(folder, core.DATA_FILE)
        root = tk.Tk()
        root.withdraw()
        app = App(root, path)
        if app.table.winfo_manager() or not app.empty.winfo_manager():
            raise RuntimeError("a new file should start on the empty screen")
        for lang in i18n.LANGS:
            app.data["settings"]["lang"] = lang
            app.tab_category = None
            app.build()
            app.load_sample()
            spec = i18n.SAMPLE[lang]
            count = len(spec["subs"]) + len(spec["decisions"])
            if len(app.tree.get_children()) != count or not app.table.winfo_manager():
                raise RuntimeError("the All tab does not list every sample item")
            if not app.banner_slot.winfo_children()[0].winfo_children():
                raise RuntimeError("the sample banner is missing")
            if len(app.tab_names) != 1 + len(core.categories(app.data)):
                raise RuntimeError("tabs do not match the stored tab list")
            app.new_sub().destroy()
            app.new_decision().destroy()
            for iid in app.tree.get_children():
                app.tree.selection_set(iid)
                app.edit().destroy()
            first_sub = next(i for i in app.data["items"] if i["kind"] == "sub")
            app.tree.selection_set(str(first_sub["id"]))
            app.calendar().destroy()
            app.settings().destroy()
            app.tab_add().destroy()
            app.select_tab(first_sub["category"])
            app.tab_rename().destroy()
            wanted = len(core.in_category(app.data, first_sub["category"]))
            if len(app.tree.get_children()) != wanted or wanted == count:
                raise RuntimeError("a tab does not filter the list")
            root.update()
            app.clear_sample()
            if app.data["items"] or core.categories(app.data) or not app.empty.winfo_manager():
                raise RuntimeError("removing the sample should leave an empty file")
        gym = core.add_sub(app.data, {"title": "Gym", "category": "Health", "billing": "installment",
                                      "amount": "730000", "months": "12", "start": "2026-11-02", "end": "",
                                      "target": "3"})
        core.set_use(app.data, gym["id"], date(2026, 11, 3), True, date(2026, 11, 9))
        app.save()
        data, broken = core.load(path)
        if broken or len(data["items"]) != 1 or data["categories"] != ["Health"]:
            raise RuntimeError("saved data did not load back")
        report = core.report_markdown(data, datetime(2026, 11, 9), i18n.translator("en"), "Health")
        if "$9,333" not in report:  # two of three goal days missed in the week of Nov 2: 2 x 14000 / 3
            raise RuntimeError("report total is wrong")
        root.destroy()
        return 0
    except Exception:  # noqa: BLE001 - any failure is a failed smoke test
        import traceback
        with open(log, "w", encoding="utf-8") as fh:
            fh.write(traceback.format_exc())
        return 1


def main():
    if "--smoke" in sys.argv:
        folder = sys.argv[sys.argv.index("--smoke") + 1]
        sys.exit(smoke(folder))
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - older Windows or not Windows
        pass
    import tkinter as tk
    root = tk.Tk()
    App(root, core.data_path())
    root.mainloop()


if __name__ == "__main__":
    main()
