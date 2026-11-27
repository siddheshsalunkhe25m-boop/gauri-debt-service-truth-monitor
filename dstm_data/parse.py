"""Parsers for Screener company pages and schedule (breakdown) JSON.

Everything is returned as tidy rows (one number per row) with its period and unit.
"""
from __future__ import annotations

import calendar
import json
import re
from collections import Counter
from typing import Optional

from bs4 import BeautifulSoup

MONTHS = {m: i for i, m in enumerate(calendar.month_abbr) if m}
PERIOD_RE = re.compile(r"^(?P<mon>[A-Z][a-z]{2})\s+(?P<year>\d{4})(?:\s+(?P<months>\d{1,2})m)?(?P<s>\s*\(S\))?"
                       r"(?:\s+(?P<months2>\d{1,2})m)?$")
META_KEYS = {"setAttributes", "tooltips", "isExpandable"}


# ---------------------------------------------------------------- small helpers
def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def parse_number(raw) -> Optional[float]:
    """'1,23,456' -> 123456.0; '-12.5%' -> -12.5; '' / '-' / None -> None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace("−", "-").replace(",", "").replace("₹", "")
    s = s.replace("Cr.", "").replace("Cr", "").replace("%", "").strip()
    if s in ("", "-", "--", "NA", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_period(label: str, date_key: Optional[str] = None) -> dict:
    """'Mar 2025 10m' -> {'base':'Mar 2025','period_end':'2025-03-31','months':10,'is_s':False,...}.
    date_key (th[data-date-key], e.g. '2025-03-31') is preferred for the date when present."""
    p = _parse_period(label)
    if date_key and re.match(r"^\d{4}-\d{2}-\d{2}$", date_key):
        p["period_end"] = date_key
    return p


def _parse_period(label: str) -> dict:
    lab = clean_text(label)
    if lab.upper() == "TTM":
        return {"label": lab, "base": "TTM", "period_end": None, "months": 12, "is_s": False, "is_ttm": True}
    m = PERIOD_RE.match(lab)
    if not m or m.group("mon") not in MONTHS:
        return {"label": lab, "base": lab, "period_end": None, "months": None, "is_s": False, "is_ttm": False}
    mon, year = MONTHS[m.group("mon")], int(m.group("year"))
    last = calendar.monthrange(year, mon)[1]
    return {"label": lab, "base": f"{m.group('mon')} {year}", "period_end": f"{year:04d}-{mon:02d}-{last:02d}",
            "months": int(m.group("months") or m.group("months2")) if (m.group("months") or m.group("months2")) else None,
            "is_s": bool(m.group("s")), "is_ttm": False}


def unit_for(section: str, label: str, raw_value: str = "") -> str:
    lab = label.lower()
    if "%" in label or str(raw_value).strip().endswith("%"):
        return "%"
    if section == "ratios" and ("days" in lab or "cycle" in lab):
        return "days"
    if section == "shareholding":
        return "count" if "no. of" in lab else "%"
    if lab.startswith("eps"):
        return "Rs/share"
    return "Rs Cr"


# ---------------------------------------------------------------- company page
class CompanyPage:
    """Parsed Screener company page (consolidated or standalone view)."""

    def __init__(self, html: str):
        self.soup = BeautifulSoup(html, "lxml")
        info = self.soup.select_one("#company-info")
        self.company_id = info.get("data-company-id") if info else None
        self.consolidated_attr = info.get("data-consolidated") if info else None
        h1 = self.soup.select_one("h1")
        self.name = clean_text(h1.get_text()) if h1 else None
        self.tables = {sec: self._table(sec) for sec in
                       ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios", "shareholding"]}

    def _table(self, section: str) -> Optional[dict]:
        sec = self.soup.select_one(f"section#{section}") or self.soup.select_one(f"#{section}")
        if sec is None:
            return None
        table = sec.select_one("table.data-table") or sec.select_one("table")
        if table is None:
            return None
        ths = table.select("thead th")
        heads = [clean_text(th.get_text(" ")) for th in ths]
        keys = [th.get("data-date-key") for th in ths]       # e.g. '2025-03-31' / 'TTM' (present on current pages)
        rows = []
        for tr in table.select("tbody tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            lab_td = tds[0]
            for sp in lab_td.find_all("span"):                # drop info tooltips, e.g. CFO/EBITDA explanation
                if sp.find("i") is not None:
                    sp.decompose()
            label = re.sub(r"\s*\+$", "", clean_text(lab_td.get_text(" ")))
            vals = [clean_text(td.get_text(" ")) for td in tds[1:]]
            rows.append((label, vals))
        return {"heads": heads[1:], "keys": keys[1:], "rows": rows}

    # -- facts about the page -----------------------------------------------------
    @property
    def layout(self) -> str:
        pl = self.tables.get("profit-loss")
        labels = {r[0] for r in pl["rows"]} if pl else set()
        if "Financing Profit" in labels or ("Revenue" in labels and "Sales" not in labels):
            return "lender"
        return "industrial"

    def annual_periods(self) -> list[dict]:
        pl = self.tables.get("profit-loss")
        if not pl:
            return []
        return [p for p in periods_of(pl) if p["period_end"] and not p["is_ttm"]]

    def latest_annual(self, own_only: bool = False) -> Optional[str]:
        """Latest FY period_end; own_only=True ignores columns Screener filled from standalone '(S)'."""
        ps = [p for p in self.annual_periods() if not (own_only and p["is_s"])]
        return max((p["period_end"] for p in ps), default=None)

    def fy_month(self) -> Optional[int]:
        ps = self.annual_periods()[-5:]
        if not ps:
            return None
        return Counter(int(p["period_end"][5:7]) for p in ps).most_common(1)[0][0]

    @property
    def ttm_end(self) -> Optional[str]:
        """TTM column = trailing four quarters to the latest quarter shown in #quarters."""
        q = self.tables.get("quarters")
        return max((p["period_end"] for p in periods_of(q) if p["period_end"]), default=None) if q else None

    def header_lookup(self, section: str) -> dict:
        """'Mar 2025' -> parsed header (carries '10m' / '(S)' markers) for schedule alignment."""
        t = self.tables.get(section)
        return {p["base"]: p for p in periods_of(t)} if t else {}

    # -- tidy rows ------------------------------------------------------------------
    def rows(self) -> list[dict]:
        out = []
        annual_bases = {p["base"] for p in self.annual_periods()}
        for sec, t in self.tables.items():
            if not t:
                continue
            periods = periods_of(t)
            for label, vals in t["rows"]:
                if label in ("Raw PDF",):
                    continue
                for p, raw in zip(periods, vals):
                    v = parse_number(raw)
                    if v is None:
                        continue
                    out.append({"statement": sec, "parent": None, "line_item": label,
                                **period_fields(sec, p, annual_bases, self.ttm_end), "value": v,
                                "unit": unit_for(sec, label, raw)})
        return out

    def top_ratios(self) -> list[dict]:
        out = []
        for li in self.soup.select("#top-ratios li"):
            name_el = li.select_one(".name")
            if not name_el:
                continue
            name = clean_text(name_el.get_text())
            value_text = clean_text((li.select_one(".value") or li).get_text(" "))
            nums = [parse_number(n.get_text()) for n in li.select(".number")]
            names = [x.strip() for x in name.split("/")] if len(nums) > 1 and "/" in name else [name]
            unit = "%" if "%" in value_text else ("Rs Cr" if "Cr" in value_text else ("Rs" if "₹" in value_text else ""))
            for n, v in zip(names, nums):
                if v is not None:
                    out.append({"statement": "top-ratios", "parent": None, "line_item": n, "period_label": "snapshot",
                                "period_end": None, "period_type": "snapshot", "period_months": None,
                                "value": v, "unit": unit, "is_standalone_fill": 0})
        return out


def periods_of(t: dict) -> list[dict]:
    keys = t.get("keys") or [None] * len(t["heads"])
    return [parse_period(h, k) for h, k in zip(t["heads"], keys)]


def period_fields(section: str, p: dict, annual_bases: set, ttm_end: Optional[str] = None) -> dict:
    if p["is_ttm"]:
        ptype, months = "TTM", 12
        p = {**p, "period_end": ttm_end}
    elif section in ("quarters", "shareholding"):
        ptype, months = "Q", 3 if section == "quarters" else None
    elif section == "balance-sheet" and p["base"] not in annual_bases:
        ptype, months = "interim", None        # e.g. 'Sep 2026' half-year balance sheet
    else:
        ptype, months = "FY", (p["months"] or 12)
    return {"period_label": p["label"], "period_end": p["period_end"], "period_type": ptype,
            "period_months": months, "is_standalone_fill": int(p["is_s"])}


# ---------------------------------------------------------------- schedules
def parse_schedule(body: str, section: str, parent: str, page: Optional[CompanyPage]) -> list[dict]:
    """Schedule JSON -> tidy rows. Child rows with blank values are skipped (value unknown)."""
    data = json.loads(body)
    lookup = page.header_lookup(section) if page else {}
    annual_bases = {p["base"] for p in page.annual_periods()} if page else set()
    out = []
    for child, series in data.items():
        if not isinstance(series, dict):
            continue
        for lab, raw in series.items():
            if lab in META_KEYS or isinstance(raw, (dict, list)):
                continue
            v = parse_number(raw)
            if v is None:
                continue
            p = parse_period(lab)
            page_p = lookup.get(p["base"])
            if page_p:                       # carry '10m' / '(S)' markers from the page header
                p = {**p, "months": page_p["months"], "is_s": page_p["is_s"], "label": page_p["label"]}
            out.append({"statement": section, "parent": parent, "line_item": child,
                        **period_fields(section, p, annual_bases, page.ttm_end if page else None), "value": v,
                        "unit": unit_for(section, child, raw)})
    return out


def schedule_children(body: str) -> list[str]:
    try:
        return [k for k, v in json.loads(body).items() if isinstance(v, dict)]
    except Exception:
        return []


def parse_prices(body: str) -> list[dict]:
    """Chart API JSON -> [{'date': 'YYYY-MM-DD', 'close': float}] from the 'Price' dataset."""
    data = json.loads(body)
    for ds in data.get("datasets", []):
        if ds.get("metric") == "Price":
            out = []
            for v in ds.get("values", []):
                c = parse_number(v[1]) if len(v) > 1 else None
                if c is not None:
                    out.append({"date": str(v[0])[:10], "close": c})
            return out
    return []
