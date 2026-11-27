"""Synthetic Screener pages that copy the real markup (checked against live pages on 2026-11-23):
th[data-date-key], 'Label&nbsp;<span>+</span>' buttons, hidden growth rows, an info tooltip inside the
CFO/EBITDA label, a 'Raw PDF' row, two shareholding tables, '(S)' and '10m' header markers."""
from __future__ import annotations

import json
import calendar

from dstm_data.http import page_url, price_url, schedule_url

MON = {m: i for i, m in enumerate(calendar.month_abbr) if m}


def _key(label):
    if label == "TTM":
        return "TTM"
    mon, year = label.split()[:2]
    m = MON[mon]
    return f"{year}-{m:02d}-{calendar.monthrange(int(year), m)[1]:02d}"


def _table(heads, rows, expandable=(), section=""):
    th = "".join(f'<th data-date-key="{_key(h)}"> {h} </th>' for h in heads)
    body = []
    for label, vals in rows:
        if label in expandable:
            lab = (f"<button onclick=\"Company.showSchedule('{label}', '{section}', this)\"> "
                   f"{label}&nbsp;<span>+</span> </button>")
        elif label == "CFO/EBITDA":
            lab = ('CFO/EBITDA <span> <i class="icon-info sub"></i> <span style="width: 250px">Share of operating '
                   'profit converting into cash</span> </span>')
        else:
            lab = label
        body.append("<tr><td> " + lab + " </td>" + "".join(f"<td> {v} </td>" for v in vals) + "</tr>")
    return f'<table class="data-table responsive-text-nowrap"><thead><tr><th></th>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def make_page(cid="3373", name="Test Steel Ltd", consolidated=True, fy=("Mar 2024", "Mar 2025", "Mar 2026"),
              lender=False, interest=(100, 110, 120), s_cols=0, partial_first=None):
    """A compact but structurally faithful company page."""
    fy = list(fy)
    heads_fy = [h + (" (S)" if i < s_cols else "") for i, h in enumerate(fy)]
    if partial_first:
        heads_fy[0] = heads_fy[0] + f" {partial_first}m"
    n = len(fy)
    q_heads = ["Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"]
    if lender:
        pl_rows = [("Revenue", ["1,000"] * (n + 1)), ("Financing Profit", ["100"] * (n + 1)),
                   ("Net Profit", ["50"] * (n + 1))]
    else:
        pl_rows = [("Sales", ["1,000", "1,100", "1,200", "1,250"]), ("Sales growth", ["5%", "10%", "+9%", "4%"]),
                   ("Expenses", ["800", "880", "960", "1,000"]), ("Operating Profit", ["200", "220", "240", "250"]),
                   ("OPM %", ["20%", "20%", "20%", "20%"]), ("Other Income", ["10", "-5", "12", "12"]),
                   ("Interest", [*map(str, interest), "125"]), ("Depreciation", ["50", "55", "60", "60"]),
                   ("Profit before tax", ["60", "50", "72", "77"]), ("Tax %", ["25%", "25%", "25%", ""]),
                   ("Net Profit", ["45", "37", "54", "58"]), ("EPS in Rs", ["4.50", "3.70", "5.40", "5.80"]),
                   ("Dividend Payout %", ["20%", "20%", "20%", ""])]
        pl_rows = [(l, v[:n] + [v[-1]]) for l, v in pl_rows]
    bs_heads = heads_fy + ["Sep 2026"]
    bs_rows = [("Equity Capital", ["10"] * (n + 1)), ("Reserves", ["490", "520", "560", "580"][:n] + ["580"]),
               ("Borrowings", ["1,000", "1,050", "1,100", "1,150"][:n] + ["1,150"]),
               ("Other Liabilities", ["300"] * (n + 1)), ("Total Liabilities", ["1,800"] * (n + 1)),
               ("Fixed Assets", ["1,000"] * (n + 1)), ("CWIP", ["50"] * (n + 1)), ("Investments", ["20"] * (n + 1)),
               ("Other Assets", ["730"] * (n + 1)), ("Total Assets", ["1,800"] * (n + 1))]
    cf_rows = [("Cash from Operating Activity", ["150", "90", "210"][:n]),
               ("Cash from Investing Activity", ["-100", "-120", "-80"][:n]),
               ("Cash from Financing Activity", ["-40", "20", "-120"][:n]), ("Net Cash Flow", ["10", "-10", "10"][:n]),
               ("Free Cash Flow", ["50", "-30", "130"][:n]), ("CFO/EBITDA", ["90%", "50%", "100%"][:n])]
    ratio_rows = [("Debtor Days", ["30", "35", "40"][:n]), ("ROCE %", ["12%", "11%", "12%"][:n])]
    q_rows = [("Sales", ["300", "310", "320", "330"]), ("YoY Sales growth", ["5%", "6%", "7%", "8%"]),
              ("Operating Profit", ["60", "62", "64", "66"]), ("Other Income", ["3", "-2", "4", "5"]),
              ("Interest", ["30", "31", "32", "33"]), ("Depreciation", ["15", "15", "16", "16"]),
              ("Profit before tax", ["18", "14", "20", "22"]), ("Net Profit", ["13", "10", "15", "16"]),
              ("Raw PDF", ["", "", "", ""])]
    sh = _table(["Jun 2026", "Sep 2026"], [("Promoters", ["33.19%", "32.94%"]), ("No. of Shareholders", ["51,79,576", "51,41,801"])])
    sh_y = _table(["Mar 2026"], [("Promoters", ["31.00%"])])
    sub = "Consolidated Figures in Rs. Crores" if consolidated else "Standalone Figures in Rs. Crores"
    return f"""<html><body>
<div data-company-id="{cid}" data-warehouse-id="1" data-consolidated="{'true' if consolidated else ''}" id="company-info"></div>
<h1> <span>{name}</span> </h1>
<ul id="top-ratios">
 <li><span class="name"> Market Cap </span><span class="nowrap value"> ₹ <span class="number">2,01,921</span> Cr. </span></li>
 <li><span class="name"> High / Low </span><span class="nowrap value">₹ <span class="number">224</span> / <span class="number">160</span></span></li>
 <li><span class="name"> ROCE </span><span class="nowrap value"> <span class="number">12.5</span> % </span></li>
</ul>
<section id="quarters"><p class="sub">{sub}</p>{_table(q_heads, q_rows, ("Other Income", "Net Profit"), "quarters")}</section>
<section id="profit-loss"><p class="sub">{sub}</p>{_table(heads_fy + ["TTM"], pl_rows, ("Expenses", "Other Income", "Net Profit"), "profit-loss")}
 <table><tbody><tr><th colspan="2">Compounded Sales Growth</th></tr><tr><td>10 Years:</td><td>9%</td></tr></tbody></table></section>
<section id="balance-sheet">{_table(bs_heads, bs_rows, ("Borrowings", "Other Liabilities", "Other Assets"), "balance-sheet")}</section>
<section id="cash-flow">{_table(heads_fy, cf_rows, ("Cash from Operating Activity", "Cash from Investing Activity", "Cash from Financing Activity"), "cash-flow")}</section>
<section id="ratios">{_table(heads_fy, ratio_rows)}</section>
<section id="shareholding"><div id="quarterly-shp">{sh}</div><div id="yearly-shp">{sh_y}</div></section>
</body></html>"""


def schedules(fy=("Mar 2024", "Mar 2025", "Mar 2026"), cff=None, cfo_extra=None, scale=1.0):
    """Schedule JSON keyed by (parent, section). Shapes copied from real responses (meta keys included)."""
    fy = list(fy)

    def ser(vals, extra=None):
        d = {k: (f"{v * scale:,.0f}" if isinstance(v, (int, float)) else v) for k, v in zip(fy, vals)}
        if extra:
            d.update(extra)
        return d

    cff = cff or {"Proceeds from shares": [0, 0, 0], "Proceeds from borrowings": [200, 300, 100],
                  "Repayment of borrowings": [-150, -180, -120], "Interest paid fin": [-95, -105, -118],
                  "Dividends paid": [-9, -9, -10], "Financial liabilities": [-5, -6, -7],
                  "Other financing items": [19, 20, 35]}
    cfo = {"Profit from operations": ser([210, 230, 250], {"setAttributes": {"class": "strong"}}),
           "Receivables": ser([-20, -60, -10]), "Inventory": ser([-10, -40, 5]), "Payables": ser([5, 10, -5]),
           "Other WC items": ser([0, 0, 0]),
           "Working capital changes": ser([-25, -90, -10], {"setAttributes": {"class": "strong"}}),
           "Direct taxes": ser([-35, -50, -30])}
    for k, v in (cfo_extra or {}).items():
        cfo[k] = ser(v)
    bs_fy = fy + ["Sep 2026"]
    return {
        ("Cash from Operating Activity", "cash-flow"): cfo,
        ("Cash from Investing Activity", "cash-flow"): {"Fixed assets purchased": ser([-110, -130, -90]),
                                                        "Fixed assets sold": ser([10, 10, 10])},
        ("Cash from Financing Activity", "cash-flow"): {k: ser(v) for k, v in cff.items()},
        ("Borrowings", "balance-sheet"): {
            "Long term Borrowings": {k: v for k, v in zip(bs_fy, ["700", "720", "750", "780"])},
            "Short term Borrowings": {k: v for k, v in zip(bs_fy, ["250", "270", "290", "310"])},
            "Lease Liabilities": {k: v for k, v in zip(bs_fy, ["50", "60", "60", "60"])},
            "Other Borrowings": {k: v for k, v in zip(bs_fy, ["0", "0", "0", "0"])}},
        ("Other Liabilities", "balance-sheet"): {
            "Trade Payables": {k: v for k, v in zip(bs_fy, ["150", "160", "155", "170"])},
            "Advance from Customers": {k: "" for k in bs_fy},
            "Non controlling int": {k: v for k, v in zip(bs_fy, ["5", "5", "6", "6"])}},
        ("Other Assets", "balance-sheet"): {
            "Inventories": {k: v for k, v in zip(bs_fy, ["300", "340", "335", "350"])},
            "Trade receivables": {**{k: v for k, v in zip(bs_fy, ["200", "260", "270", "280"])},
                                  "isExpandable": "Company.showSchedule(\"Trade receivables\", \"balance-sheet\", this)"},
            "Cash Equivalents": {k: v for k, v in zip(bs_fy, ["80", "70", "80", "60"])}},
        ("Trade receivables", "balance-sheet"): {
            "Receivables over 6m": ser([20, 40, 45]), "Receivables under 6m": ser([185, 225, 230]),
            "Prov for Doubtful": ser([-5, -5, -5])},
        ("Other Income", "profit-loss"): {"Exceptional items": {**ser([0, -15, 0]), "TTM": "0"},
                                          "Other income normal": {**ser([10, 10, 12]), "TTM": "12"}},
        ("Net Profit", "profit-loss"): {"Minority share": ser([-1, -1, -1]), "Exceptional items AT": ser([0, -11, 0]),
                                        "Profit Growth %": ser(["", "-18%", "46%"])},
        ("Other Income", "quarters"): {"Exceptional items": {"Dec 2025": "0", "Mar 2026": "-5", "Jun 2026": "0", "Sep 2026": "0"},
                                       "Other income normal": {"Dec 2025": "3", "Mar 2026": "3", "Jun 2026": "4", "Sep 2026": "5"}},
    }


class FakeTransport:
    """Dict-backed transport with optional failures; records every URL requested."""
    mode = "replay"

    def __init__(self, responses: dict, fail: set = frozenset(), status_override: dict = None):
        from dstm_data.http import normalize_url
        self.norm = normalize_url
        self.responses = {normalize_url(u): b for u, b in responses.items()}
        self.fail = {normalize_url(u) for u in fail}
        self.status_override = {normalize_url(u): s for u, s in (status_override or {}).items()}
        self.requested = []
        self.on_attempt = lambda rec: None

    def get(self, url):
        from dstm_data.http import FetchResult, utcnow
        k = self.norm(url)
        self.requested.append(url)
        if k in self.fail:
            res = FetchResult(url, 0, None, utcnow(), 1, 4, self.mode, "ConnectionError: simulated")
        elif k in self.status_override:
            st = self.status_override[k]
            res = FetchResult(url, st, None, utcnow(), 1, 1, self.mode, f"HTTP {st}")
        elif k in self.responses:
            res = FetchResult(url, 200, self.responses[k], utcnow(), 1, 1, self.mode)
        else:
            res = FetchResult(url, 404, None, utcnow(), 1, 1, self.mode, "HTTP 404")
        self.on_attempt({"url": url, "ts_utc": res.fetched_at, "status": res.status, "bytes": len(res.body or ""),
                         "elapsed_ms": 1, "attempt": 1, "mode": self.mode, "error": res.error})
        return res


def company_responses(symbol, cid, cons_html=None, stand_html=None, cons_sched=None, stand_sched=None):
    from dstm_data.config import SCHEDULES
    r = {}
    if cons_html is not None:
        r[page_url(symbol, True)] = cons_html
    if stand_html is not None:
        r[page_url(symbol, False)] = stand_html
    r[price_url(cid)] = json.dumps({"datasets": [
        {"metric": "Price", "label": "Price", "values": [["2024-01-05", "100.00"], ["2024-01-12", "60.50"], ["2024-01-19", "45.00"]]},
        {"metric": "DMA50", "label": "50 DMA", "values": [["2024-01-05", "99"]]}]})
    for flag, sched in ((True, cons_sched), (False, stand_sched)):
        if sched:
            for (parent, section) in SCHEDULES:
                if (parent, section) in sched:
                    r[schedule_url(cid, parent, section, flag)] = json.dumps(sched[(parent, section)])
    return r
