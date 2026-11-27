"""RTS calculation workbook (Excel, LIVE formulas).

Traceability chain:  Sources (one row per Screener number: value, source line, flag, URL, fetch time)
  -> Annual (each input cell is a direct link =Sources!G<row>; every step is a formula)
  -> Quarters / BreachClock (TTM covenant tests are formulas; the Monte Carlo probabilities are Python
     output, entered as blue values with seed and path count)
  -> Company (pooled FA-DSCR, Minsky, refinancing, sub-scores, RTS, class) -> Migration -> Checks.
All parameters live on Settings as named cells, so changing a threshold or weight recalculates the sheet
(except the Monte Carlo probabilities, which need a Python re-run).
"""
from __future__ import annotations

import re
from datetime import date

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from .config import RTSConfig
from .engine import RTSResult
from .inputs import ANNUAL_FIELDS

FONT = "Arial"
BLUE, GREEN, BLACK = "0000FF", "008000", "000000"
HDR_FILL = PatternFill("solid", fgColor="1F3864")
SET_FILL = PatternFill("solid", fgColor="FFFF00")
CR = '#,##0;(#,##0);"-"'
CR1 = '#,##0.0;(#,##0.0);"-"'
X = '0.00"x"'
PCT = '0.0%'
DAYS = '0'
SC = '0.0'
DATE = 'yyyy-mm-dd'
thin = Side(style="thin", color="BFBFBF")


def _d(s):
    return date.fromisoformat(s) if isinstance(s, str) and s else None


def _font(cell, color=BLACK, bold=False):
    cell.font = Font(name=FONT, color=color, bold=bold, size=9)


def _header(ws, headers, row=1, notes=None):
    for j, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=j, value=h)
        c.font = Font(name=FONT, color="FFFFFF", bold=True, size=9)
        c.fill = HDR_FILL
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if notes and h in notes:
            c.comment = Comment(notes[h], "RTS engine")
    ws.freeze_panes = ws.cell(row=row + 1, column=3)
    ws.row_dimensions[row].height = 42


# ---------------------------------------------------------------- Settings
SETTINGS = [
    # name, config attr, label, format
    ("W_DSCR", "w_dscr", "Weight: FA-DSCR", "0.00"),
    ("W_MINSKY", "w_minsky", "Weight: Minsky state / migration", "0.00"),
    ("W_REFI", "w_refi", "Weight: refinancing dependence", "0.00"),
    ("W_BREACH", "w_breach", "Weight: Breach Clock", "0.00"),
    ("PAY_NORM_YEARS", "payables_norm_years", "Payables norm: previous N fiscal years", "0"),
    ("PAY_MIN_HIST", "payables_min_history", "Payables norm: minimum prior years", "0"),
    ("DEDUCT_EXC", "deduct_exceptional_gains", "Deduct positive exceptional items (1/0)", "0"),
    ("NONCORE_MODE", "noncore_mode", "Non-core income mode (ex_investing_receipts / all_other_income / none)", "@"),
    ("ADDBACK_MODE", "interest_addback", "Interest add-back mode (auto / always / never)", "@"),
    ("FALLBACK_SHARE", "fallback_other_financing_share", "P&L-interest fallback: 'Other financing items' share", "0.00"),
    ("INCLUDE_LEASE", "include_lease_payments", "Include lease payments ('Financial liabilities') in repayments (1/0)", "0"),
    ("MIN_SERVICE", "min_debt_service", "Minimum debt service, Rs Cr (below = no debt service)", "0.0"),
    ("MIG_YEARS", "migration_years", "Migration: compare with mean state of previous N years", "0"),
    ("MIG_THR", "migration_threshold", "Migration: ordinal change threshold", "0.00"),
    ("REFI_YEARS", "refi_years", "Pooling window, fiscal years (DSCR & refinancing)", "0"),
    ("ICR_MIN", "icr_min", "Covenant: minimum ICR (TTM EBITDA / interest)", X),
    ("DE_MAX", "debt_ebitda_max", "Covenant: maximum Debt / TTM EBITDA", X),
    ("DEBT_MEASURE", "debt_measure", "Debt measure (gross / net)", "@"),
    ("MS_W", "minsky_state_weight", "Minsky component: weight on state (rest on migration)", "0.00"),
    ("BW", "breach_base_weight", "Breach component: weight on baseline P (rest on stress)", "0.00"),
    ("SAFE_MIN", "safe_min", "Class: Safe if RTS >=", SC),
    ("WATCH_MIN", "watch_min", "Class: Watch if RTS >=", SC),
    ("ESC_P", "escalate_p_breach", "Override Escalate: baseline P(breach 4q) >=", PCT),
    ("WATCH_P", "watch_p_breach", "Override Watch: baseline P(breach 4q) >=", PCT),
    ("STRETCH_THR", "watch_stretch_share", "Override Watch: payables stretch / CFO >", PCT),
    ("REFI_THR", "watch_refi_dependence", "Override Watch: refinancing dependence >", PCT),
]


def _settings_sheet(wb, cfg: RTSConfig):
    ws = wb.create_sheet("Settings")
    ws["A1"] = "Settings - every threshold and weight used by the formulas (yellow = edit here)"
    _font(ws["A1"], bold=True)
    _header(ws, ["Name", "Value", "Meaning"], row=3)
    ws.freeze_panes = None
    r = 4
    for name, attr, label, fmt in SETTINGS:
        v = getattr(cfg, attr)
        v = int(v) if isinstance(v, bool) else v
        ws.cell(r, 1, name)
        c = ws.cell(r, 2, v)
        c.number_format = fmt
        c.fill = SET_FILL
        _font(c, BLUE)
        ws.cell(r, 3, label)
        wb.defined_names[name] = DefinedName(name, attr_text=f"Settings!$B${r}")
        r += 1
    r += 1
    ws.cell(r, 1, "FA-DSCR score points (piecewise linear, flat outside)")
    _font(ws.cell(r, 1), bold=True)
    r += 1
    ws.cell(r, 1, "Point")
    ws.cell(r, 2, "DSCR (x)")
    ws.cell(r, 3, "Score")
    for k, (x, y) in enumerate(cfg.dscr_points, 1):
        r += 1
        ws.cell(r, 1, k)
        for col, v, nm in ((2, x, f"DSCR_X{k}"), (3, y, f"DSCR_Y{k}")):
            c = ws.cell(r, col, v)
            c.fill = SET_FILL
            _font(c, BLUE)
            wb.defined_names[nm] = DefinedName(nm, attr_text=f"Settings!${get_column_letter(col)}${r}")
    r += 2
    ws.cell(r, 1, "State / migration scores")
    _font(ws.cell(r, 1), bold=True)
    for nm, v in [("SC_HEDGE", cfg.minsky_state_score["Hedge"]), ("SC_SPEC", cfg.minsky_state_score["Speculative"]),
                  ("SC_PONZI", cfg.minsky_state_score["Ponzi"]), ("MG_IMPROVING", cfg.migration_score["improving"]),
                  ("MG_STABLE", cfg.migration_score["stable"]), ("MG_DETERIORATING", cfg.migration_score["deteriorating"])]:
        r += 1
        ws.cell(r, 1, nm)
        c = ws.cell(r, 2, v)
        c.fill = SET_FILL
        _font(c, BLUE)
        wb.defined_names[nm] = DefinedName(nm, attr_text=f"Settings!$B${r}")
    r += 2
    ws.cell(r, 1, "Monte Carlo (Python only - change in RTSConfig and re-run): paths, horizon, stress")
    _font(ws.cell(r, 1), bold=True)
    for lab, v in [("n_paths", cfg.n_paths), ("horizon_q", cfg.horizon_q), ("breach_window_q", cfg.breach_window_q),
                   ("stress_ebitda_haircut", cfg.stress_ebitda_haircut), ("stress_interest_uplift", cfg.stress_interest_uplift),
                   ("stress_remove_drift", int(cfg.stress_remove_drift)), ("min_yoy_pairs", cfg.min_yoy_pairs), ("seed", cfg.seed)]:
        r += 1
        ws.cell(r, 1, lab)
        _font(ws.cell(r, 2, v), BLUE)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 80


# ---------------------------------------------------------------- generic grid writer
class Grid:
    """Writes a table whose formulas refer to columns by name: [col] = same row, {col} = whole column."""

    def __init__(self, ws, cols, n_rows, first_row=2):
        self.ws, self.cols, self.first = ws, cols, first_row
        self.last = first_row + max(n_rows, 1) - 1
        self.letter = {c[0]: get_column_letter(i) for i, c in enumerate(cols, 1)}

    def rng(self, name, sheet=None):
        L = self.letter[name]
        return f"{sheet + '!' if sheet else ''}${L}${self.first}:${L}${self.last}"

    def expand(self, tmpl, r):
        tmpl = re.sub(r"\[(\w+)\]", lambda m: f"{self.letter[m.group(1)]}{r}", tmpl)
        return re.sub(r"\{(\w+)\}", lambda m: self.rng(m.group(1)), tmpl)


def _fmt(cell, kind):
    cell.number_format = {"cr": CR, "cr1": CR1, "x": X, "pct": PCT, "days": DAYS, "sc": SC, "date": DATE,
                          "int": "0", "txt": "@", "p": PCT}.get(kind, "General")


# ---------------------------------------------------------------- main builder
def build_workbook(res: RTSResult, credit_lines: pd.DataFrame, path: str, title_note: str = "") -> str:
    cfg = res.config
    wb = Workbook()
    readme = wb.active
    readme.title = "README"
    _settings_sheet(wb, cfg)

    # ----------------------------------------------------------- Sources
    cl = credit_lines[credit_lines.basis_role == "primary"].copy()
    need = (((cl.frequency == "FY") & cl.field.isin(ANNUAL_FIELDS + ["other_income"])) |
            ((cl.frequency == "Q") & cl.field.isin(["ebitda", "interest_expense"])) |
            (cl.frequency.isin(["FY", "interim"]) & cl.field.isin(["total_borrowings", "cash_and_equivalents"])))
    src = cl[need].sort_values(["symbol", "frequency", "period_end", "field"]).reset_index(drop=True)
    ws = wb.create_sheet("Sources")
    heads = ["ID", "Symbol", "Frequency", "Period end", "Period label", "Field", "Value", "Unit", "Source line",
             "Flag", "Source URL", "Fetched at (UTC)", "Basis"]
    _header(ws, heads)
    pos = {}
    for i, r in enumerate(src.itertuples(index=False), 2):
        vals = [i - 1, r.symbol, r.frequency, _d(r.period_end), r.period_label, r.field, r.value, r.unit, r.source,
                r.flag or "", r.source_url, r.fetched_at, r.basis]
        for j, v in enumerate(vals, 1):
            c = ws.cell(i, j, v)
            _font(c, BLUE if j == 7 else BLACK)
        ws.cell(i, 4).number_format = DATE
        ws.cell(i, 7).number_format = CR1
        pos[(r.symbol, r.frequency, r.period_end, r.field)] = i
    for j, w in enumerate([6, 13, 9, 11, 10, 24, 11, 7, 52, 20, 60, 22, 12], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.auto_filter.ref = f"A1:M{max(2, len(src) + 1)}"

    def link(sym, freq, pend, field, col="G"):
        p = pos.get((sym, freq, pend, field))
        return f"=Sources!${col}${p}" if p else None

    # ----------------------------------------------------------- Annual
    A = res.annual.sort_values(["symbol", "period_end"]).reset_index(drop=True)
    inputs = [("cfo", "cfo", "cr"), ("opex", "operating_expenses", "cr"), ("tp", "trade_payables", "cr"),
              ("exc", "exceptional_items", "cr"), ("oir", "other_income_recurring", "cr"), ("oi", "other_income", "cr"),
              ("int_rec", "interest_received", "cr"), ("div_rec", "dividends_received", "cr"),
              ("ip", "interest_paid", "cr"), ("ip_cfo", "interest_paid_in_cfo", "cr"), ("ofi", "other_financing_items", "cr"),
              ("rep", "principal_repaid", "cr"), ("fl_paid", "financial_liabilities_paid", "cr"),
              ("raised", "borrowings_raised", "cr"), ("dep", "depreciation", "cr"), ("np", "net_profit", "cr"),
              ("ebitda", "ebitda", "cr"), ("ta", "total_assets", "cr")]
    calc = [
        ("opex_ann", "Opex annualised", 'IF(AND(ISNUMBER([opex]),[months]>0),[opex]*12/[months],"")', "cr"),
        ("pay_days", "Payable days (on opex)", 'IF(AND(ISNUMBER([opex_ann]),ISNUMBER([tp])),IF([opex_ann]>0,[tp]/[opex_ann]*365,""),"")', "days"),
        ("prior_n", "Prior years in norm", 'COUNTIFS({symbol},[symbol],{fy_idx},">="&([fy_idx]-PAY_NORM_YEARS),{fy_idx},"<"&[fy_idx],{pay_days},">=0")', "int"),
        ("pay_norm", "Own payables norm (days)", 'IF([prior_n]>=PAY_MIN_HIST,AVERAGEIFS({pay_days},{symbol},[symbol],{fy_idx},">="&([fy_idx]-PAY_NORM_YEARS),{fy_idx},"<"&[fy_idx]),"")', "days"),
        ("stretch", "Payables stretch (Rs Cr)", 'IF(AND(ISNUMBER([pay_days]),ISNUMBER([pay_norm])),MAX(0,[tp]-[pay_norm]*[opex_ann]/365),0)', "cr"),
        ("exc_gain", "Exceptional gain deducted", 'IF(DEDUCT_EXC=1,MAX(N([exc]),0),0)', "cr"),
        ("oin_used", "Other income (normal) used", 'IF(ISNUMBER([oir]),[oir],N([oi])-N([exc]))', "cr"),
        ("noncore", "Non-core income deducted", 'IF(NONCORE_MODE="ex_investing_receipts",MAX([oin_used]-N([int_rec])-N([div_rec]),0),IF(NONCORE_MODE="all_other_income",MAX([oin_used],0),0))', "cr"),
        ("cfo_adj", "CFO_adj = CFO - stretch - exceptional - non-core", 'IF(ISNUMBER([cfo]),[cfo]-[stretch]-[exc_gain]-[noncore],"")', "cr"),
        ("int_in_cfo", "Interest inside CFO", 'IF(NOT(ISNUMBER([ip])),0,IF([iflag]="interest_in_cfo",[ip],IF([iflag]="interest_split_cfo_cff",N([ip_cfo]),IF([iflag]="fallback_pnl_interest",IF(-N([ofi])>=FALLBACK_SHARE*[ip],0,[ip]),0))))', "cr"),
        ("addback", "Interest add-back", 'IF(ADDBACK_MODE="auto",[int_in_cfo],IF(ADDBACK_MODE="always",N([ip]),0))', "cr"),
        ("cfads", "CFADS = CFO_adj + add-back", 'IF(ISNUMBER([cfo_adj]),[cfo_adj]+[addback],"")', "cr"),
        ("lease", "Lease payments in repayments", 'IF(INCLUDE_LEASE=1,N([fl_paid]),0)', "cr"),
        ("repay", "Repayments (borrowings + leases)", 'IF(ISNUMBER([rep]),[rep]+[lease],"")', "cr"),
        ("service", "Debt service = interest + repayments", 'IF(AND(ISNUMBER([repay]),ISNUMBER([ip])),[ip]+[repay],"")', "cr"),
        ("no_service", "No debt service (1/0)", 'IF(ISNUMBER([service]),IF([service]<MIN_SERVICE,1,0),"")', "int"),
        ("fa_dscr", "FA-DSCR = CFADS / debt service", 'IF(AND(ISNUMBER([cfads]),[no_service]=0),[cfads]/[service],"")', "x"),
        ("fa_dscr_m", "FA-DSCR after maint. capex (dep. proxy)", 'IF(AND(ISNUMBER([cfads]),[no_service]=0),([cfads]-N([dep]))/[service],"")', "x"),
        ("state", "Minsky state", 'IF(OR(NOT(ISNUMBER([cfads])),NOT(ISNUMBER([service]))),"",IF([no_service]=1,"Hedge",IF([cfads]>=[service],"Hedge",IF([cfads]>=N([ip]),"Speculative","Ponzi"))))', "txt"),
        ("ord", "State ordinal (P0 S1 H2)", 'IF([state]="","",IF([state]="Hedge",2,IF([state]="Speculative",1,0)))', "int"),
        ("prior_mean", "Mean ordinal, previous N yrs", 'IF(COUNTIFS({symbol},[symbol],{fy_idx},">="&([fy_idx]-MIG_YEARS),{fy_idx},"<"&[fy_idx],{ord},">=0")>0,AVERAGEIFS({ord},{symbol},[symbol],{fy_idx},">="&([fy_idx]-MIG_YEARS),{fy_idx},"<"&[fy_idx]),"")', "0.00"),
        ("migration", "Migration", 'IF(OR([ord]="",[prior_mean]=""),"",IF([ord]-[prior_mean]>=MIG_THR,"improving",IF([ord]-[prior_mean]<=-MIG_THR,"deteriorating","stable")))', "txt"),
        ("prev_state", "Previous year state", 'IFERROR(INDEX({state},MATCH([symbol]&"|"&([fy_idx]-1),{key},0))&"","")', "txt"),
        ("refi", "Refinancing dependence = new borrowing / debt service", 'IF([no_service]="","",IF([no_service]=1,0,IF(ISNUMBER([raised]),[raised]/[service],"")))', "pct"),
        ("cce", "Cash conversion CFO/EBITDA (S5-6)", 'IF(AND(ISNUMBER([cfo]),N([ebitda])>0),[cfo]/[ebitda],"")', "pct"),
        ("ta_prev", "Total assets, prior year", 'IFERROR(INDEX({ta},MATCH([symbol]&"|"&([fy_idx]-1),{key},0))+0,"")', "cr"),
        ("sloan", "Accrual (Sloan) ratio (S7-8)", 'IF(AND(ISNUMBER([np]),ISNUMBER([cfo]),ISNUMBER([ta])),([np]-[cfo])/IF(ISNUMBER([ta_prev]),AVERAGE([ta],[ta_prev]),[ta]),"")', "pct"),
    ]
    checks = [("py_cfo_adj", "Python CFO_adj", "cr"), ("py_fa_dscr", "Python FA-DSCR", "x"), ("py_state", "Python state", "txt"),
              ("chk", "Check (0 = Excel equals Python)", "int")]
    cols = ([("key", "Key", "txt"), ("symbol", "Symbol", "txt"), ("fy_end", "FY end", "date"), ("fy_label", "FY label", "txt"),
             ("months", "Months", "int"), ("fy_idx", "FY index", "int")] +
            [(k, f, fmt) for k, f, fmt in inputs] + [("iflag", "interest_paid flag", "txt")] +
            [(k, lab, fmt) for k, lab, _, fmt in calc] + checks)
    wsA = wb.create_sheet("Annual")
    g = Grid(wsA, cols, len(A))
    notes = {lab: f"={tmpl}" for k, lab, tmpl, _ in calc}
    _header(wsA, [c[1] for c in cols], notes=notes)
    for i, r in enumerate(A.itertuples(index=False), 2):
        vals = {"key": f'=[symbol]&"|"&[fy_idx]', "symbol": r.symbol, "fy_end": _d(r.period_end),
                "fy_label": r.period_label, "months": r.period_months,
                "fy_idx": '=COUNTIFS({symbol},[symbol],{fy_end},"<="&[fy_end])'}
        for k, f, _ in inputs:
            vals[k] = link(r.symbol, "FY", r.period_end, f)
        vals["iflag"] = link(r.symbol, "FY", r.period_end, "interest_paid", col="J")
        if vals["iflag"]:
            vals["iflag"] = vals["iflag"] + '&""'
        for k, lab, tmpl, _ in calc:
            vals[k] = "=" + tmpl
        vals["py_cfo_adj"] = None if pd.isna(r.cfo_adj) else float(r.cfo_adj)
        vals["py_fa_dscr"] = None if pd.isna(r.fa_dscr) else float(r.fa_dscr)
        vals["py_state"] = r.minsky_state or ""
        vals["chk"] = ('=IF(AND(ISNUMBER([py_cfo_adj]),ISNUMBER([cfo_adj])),IF(ABS([py_cfo_adj]-[cfo_adj])>0.01,1,0),'
                       'IF(ISNUMBER([py_cfo_adj])=ISNUMBER([cfo_adj]),0,1))'
                       '+IF(AND(ISNUMBER([py_fa_dscr]),ISNUMBER([fa_dscr])),IF(ABS([py_fa_dscr]-[fa_dscr])>0.0001,1,0),'
                       'IF(ISNUMBER([py_fa_dscr])=ISNUMBER([fa_dscr]),0,1))+IF([py_state]=[state],0,1)')
        for j, (k, lab, fmt) in enumerate(cols, 1):
            v = vals.get(k)
            if isinstance(v, str) and v.startswith("="):
                v = g.expand(v, i)
            c = wsA.cell(i, j, v)
            color = GREEN if isinstance(v, str) and v.startswith("=Sources!") else (
                BLUE if k in ("symbol", "fy_end", "fy_label", "months") or k.startswith("py_") else BLACK)
            _font(c, color)
            _fmt(c, fmt if fmt not in ("0.00",) else None)
            if fmt == "0.00":
                c.number_format = "0.00"
    for j, (k, lab, fmt) in enumerate(cols, 1):
        wsA.column_dimensions[get_column_letter(j)].width = 14 if k not in ("key",) else 16
    wsA.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{g.last}"

    # ----------------------------------------------------------- Quarters
    Q = res.quarters.dropna(subset=["ebitda", "interest_expense"]).sort_values(["symbol", "period_end"])
    Q = Q.groupby("symbol").tail(13).reset_index(drop=True)
    wsQ = wb.create_sheet("Quarters")
    qcols = [("symbol", "Symbol", "txt"), ("q_end", "Quarter end", "date"), ("q_idx", "Quarter index", "int"),
             ("ebitda", "EBITDA (Operating Profit)", "cr"), ("interest", "Interest (P&L)", "cr"),
             ("icr_q", "Quarter ICR", "x")]
    gq = Grid(wsQ, qcols, len(Q))
    _header(wsQ, [c[1] for c in qcols])
    for i, r in enumerate(Q.itertuples(index=False), 2):
        vals = {"symbol": r.symbol, "q_end": _d(r.period_end),
                "q_idx": '=COUNTIFS({symbol},[symbol],{q_end},"<="&[q_end])',
                "ebitda": link(r.symbol, "Q", r.period_end, "ebitda"),
                "interest": link(r.symbol, "Q", r.period_end, "interest_expense"),
                "icr_q": '=IF(N([interest])>0,[ebitda]/[interest],"")'}
        for j, (k, lab, fmt) in enumerate(qcols, 1):
            v = vals[k]
            if isinstance(v, str) and v.startswith("=") and not v.startswith("=Sources!"):
                v = gq.expand(v, i)
            c = wsQ.cell(i, j, v)
            _font(c, GREEN if isinstance(v, str) and v.startswith("=Sources!") else (BLUE if k in ("symbol", "q_end") else BLACK))
            _fmt(c, fmt)

    # ----------------------------------------------------------- BreachClock
    B = res.breach.sort_values("symbol").reset_index(drop=True)
    debt = res.debt.set_index("symbol") if len(res.debt) else pd.DataFrame()
    wsB = wb.create_sheet("BreachClock")
    bcols = [("symbol", "Symbol", "txt"), ("n_q", "Quarters available", "int"), ("debt_date", "Debt as of", "date"),
             ("debt_gross", "Borrowings (gross, incl. leases)", "cr"), ("cash", "Cash & equivalents", "cr"),
             ("debt", "Debt used", "cr"),
             ("ttm_e", "TTM EBITDA (last 4 q)", "cr"), ("ttm_i", "TTM interest (last 4 q)", "cr"),
             ("icr_now", "ICR now", "x"), ("de_now", "Debt / EBITDA now", "x"), ("breach_now", "Breach now (1/0)", "int"),
             ("status", "Simulation status (Python)", "txt"), ("p_base", "P(breach <= 4q) baseline (Python MC)", "p"),
             ("p_stress", "P(breach <= 4q) stress (Python MC)", "p"), ("med_base", "Median quarters to breach, baseline", "sc"),
             ("med_stress", "Median quarters to breach, stress", "sc"), ("n_paths", "Paths", "int"), ("seed", "Seed", "int")]
    gb = Grid(wsB, bcols, len(B))
    _header(wsB, [c[1] for c in bcols], notes={
        "P(breach <= 4q) baseline (Python MC)": "Monte Carlo output from dstm_rts.breach (paired seasonal YoY bootstrap). "
        "Values, not formulas: re-run Python after changing covenant thresholds.",
        "Debt used": "Held constant at the latest reported balance sheet (FY or half-year): Screener has no quarterly debt."})
    qrng = lambda name: gq.rng(name, "Quarters")
    for i, r in enumerate(B.itertuples(index=False), 2):
        dd = debt.loc[r.symbol, "debt_date"] if r.symbol in debt.index else None
        dfreq = "interim" if (r.symbol, "interim", dd, "total_borrowings") in pos else "FY"
        vals = {"symbol": r.symbol,
                "n_q": f'=COUNTIFS({qrng("symbol")},[symbol])',
                "debt_date": _d(dd) if dd else None,
                "debt_gross": link(r.symbol, dfreq, dd, "total_borrowings") or 0,
                "cash": link(r.symbol, dfreq, dd, "cash_and_equivalents"),
                "debt": '=IF(DEBT_MEASURE="net",N([debt_gross])-N([cash]),N([debt_gross]))',
                "ttm_e": f'=SUMIFS({qrng("ebitda")},{qrng("symbol")},[symbol],{qrng("q_idx")},">"&([n_q]-4))',
                "ttm_i": f'=SUMIFS({qrng("interest")},{qrng("symbol")},[symbol],{qrng("q_idx")},">"&([n_q]-4))',
                "icr_now": '=IF([n_q]<4,"",IF([ttm_i]>0,[ttm_e]/[ttm_i],"no interest"))',
                "de_now": '=IF([n_q]<4,"",IF([ttm_e]>0,[debt]/[ttm_e],"EBITDA<=0"))',
                "breach_now": '=IF([n_q]<4,0,IF(OR(AND(ISNUMBER([icr_now]),[icr_now]<ICR_MIN),AND([debt]>0,OR(NOT(ISNUMBER([de_now])),[de_now]>DE_MAX))),1,0))',
                "status": r.status,
                "p_base": None if pd.isna(r.p_breach_base) else float(r.p_breach_base),
                "p_stress": None if pd.isna(r.p_breach_stress) else float(r.p_breach_stress),
                "med_base": f">{cfg.horizon_q}" if r.median_q_base is None or pd.isna(r.median_q_base) and r.status == "ok" else (None if pd.isna(r.median_q_base) else float(r.median_q_base)),
                "med_stress": f">{cfg.horizon_q}" if r.median_q_stress is None or pd.isna(r.median_q_stress) and r.status == "ok" else (None if pd.isna(r.median_q_stress) else float(r.median_q_stress)),
                "n_paths": r.n_paths, "seed": r.seed}
        if r.status in ("insufficient_quarters",):
            vals["med_base"] = vals["med_stress"] = None
        for j, (k, lab, fmt) in enumerate(bcols, 1):
            v = vals[k]
            if isinstance(v, str) and v.startswith("=") and not v.startswith("=Sources!"):
                v = gb.expand(v, i)
            c = wsB.cell(i, j, v)
            _font(c, GREEN if isinstance(v, str) and v.startswith("=Sources!") else (
                BLUE if k in ("symbol", "debt_date", "status", "p_base", "p_stress", "med_base", "med_stress", "n_paths", "seed") else BLACK))
            _fmt(c, fmt)
    for j in range(1, len(bcols) + 1):
        wsB.column_dimensions[get_column_letter(j)].width = 14

    # ----------------------------------------------------------- Company
    S = res.scores.sort_values("symbol").reset_index(drop=True)
    wsC = wb.create_sheet("Company")
    an = lambda name: g.rng(name, "Annual")
    br = lambda name: gb.rng(name, "BreachClock")
    win = (f'{an("symbol")},[symbol],{an("fy_idx")},">"&([idx]-REFI_YEARS),{an("fy_idx")},"<="&[idx],'
           f'{an("state")},"?*",{an("no_service")},0')
    pts = list(range(1, len(cfg.dscr_points) + 1))
    pw = f"DSCR_Y{pts[-1]}"
    for k in reversed(pts[1:]):
        pw = f"IF([fa3]<=DSCR_X{k},DSCR_Y{k-1}+([fa3]-DSCR_X{k-1})/(DSCR_X{k}-DSCR_X{k-1})*(DSCR_Y{k}-DSCR_Y{k-1}),{pw})"
    pw = f"IF([fa3]<=DSCR_X1,DSCR_Y1,{pw})"
    look = lambda col: f'INDEX({an(col)},MATCH([symbol]&"|"&[idx],{an("key")},0))'
    ccols = [
        ("symbol", "Symbol", None, "txt"),
        ("idx", "Latest scored FY index", f'=IFERROR(_xlfn.MAXIFS({an("fy_idx")},{an("symbol")},[symbol],{an("state")},"?*"),0)', "int"),
        ("fy", "Latest scored FY", f'=IF([idx]>0,{look("fy_end")},"")', "date"),
        ("state", "Minsky state (latest)", f'=IF([idx]>0,{look("state")},"")', "txt"),
        ("mig", "Migration (latest)", f'=IF([idx]>0,{look("migration")}&"","")', "txt"),
        ("state3", "State 3 FY earlier", f'=IFERROR(INDEX({an("state")},MATCH([symbol]&"|"&([idx]-MIG_YEARS),{an("key")},0))&"","")', "txt"),
        ("n_serv", "Years with debt service in window", f"=COUNTIFS({win})", "int"),
        ("sum_cfads", "Sum CFADS (window)", f'=SUMIFS({an("cfads")},{win})', "cr"),
        ("sum_serv", "Sum debt service (window)", f'=SUMIFS({an("service")},{win})', "cr"),
        ("sum_dep", "Sum depreciation (window)", f'=SUMIFS({an("dep")},{win})', "cr"),
        ("sum_raised", "Sum new borrowing (window)", f'=SUMIFS({an("raised")},{win})', "cr"),
        ("fa3", "FA-DSCR 3-yr pooled", '=IF(AND([n_serv]>0,[sum_serv]>=MIN_SERVICE),[sum_cfads]/[sum_serv],"")', "x"),
        ("fa3m", "FA-DSCR after maint. capex, 3-yr", '=IF(AND([n_serv]>0,[sum_serv]>=MIN_SERVICE),([sum_cfads]-[sum_dep])/[sum_serv],"")', "x"),
        ("fa_last", "FA-DSCR latest FY", f'=IF([idx]>0,{look("fa_dscr")},"")', "x"),
        ("refi3", "Refinancing dependence 3-yr", '=IF([fa3]="",0,[sum_raised]/[sum_serv])', "pct"),
        ("cfo_last", "CFO latest", f'=IF([idx]>0,{look("cfo")},"")', "cr"),
        ("stretch_last", "Payables stretch latest", f'=IF([idx]>0,{look("stretch")},"")', "cr"),
        ("stretch_share", "Stretch / |CFO|", '=IF(AND(ISNUMBER([cfo_last]),N([cfo_last])<>0),[stretch_last]/ABS([cfo_last]),"")', "pct"),
        ("s_dscr", "S_dscr", f'=IF([idx]=0,"",IF([fa3]="",100,{pw}))', "sc"),
        ("s_minsky", "S_minsky", '=IF([state]="","",IF([mig]="",IF([state]="Hedge",SC_HEDGE,IF([state]="Speculative",SC_SPEC,SC_PONZI)),'
                                  'MS_W*IF([state]="Hedge",SC_HEDGE,IF([state]="Speculative",SC_SPEC,SC_PONZI))+(1-MS_W)*IF([mig]="improving",MG_IMPROVING,IF([mig]="stable",MG_STABLE,MG_DETERIORATING))))', "sc"),
        ("s_refi", "S_refi", '=IF(OR([idx]=0,NOT(ISNUMBER([refi3]))),"",100*(1-MIN(1,MAX(0,[refi3]))))', "sc"),
        ("pb", "P breach base", f'=IFERROR(INDEX({br("p_base")},MATCH([symbol],{br("symbol")},0))+0,"")', "p"),
        ("ps", "P breach stress", f'=IFERROR(INDEX({br("p_stress")},MATCH([symbol],{br("symbol")},0))+0,"")', "p"),
        ("bnow", "Breach now", f'=IFERROR(INDEX({br("breach_now")},MATCH([symbol],{br("symbol")},0)),0)', "int"),
        ("s_breach", "S_breach", '=IF(ISNUMBER([pb]),100*(1-(BW*[pb]+(1-BW)*[ps])),"")', "sc"),
        ("rts", "RTS (0-100)", '=IF([idx]=0,"",(W_DSCR*[s_dscr]+W_MINSKY*[s_minsky]+IF(ISNUMBER([s_refi]),W_REFI*[s_refi],0)+IF(ISNUMBER([s_breach]),W_BREACH*[s_breach],0))'
                               '/(W_DSCR+W_MINSKY+IF(ISNUMBER([s_refi]),W_REFI,0)+IF(ISNUMBER([s_breach]),W_BREACH,0)))', "sc"),
        ("score_class", "Class by score", '=IF([rts]="","Insufficient data",IF([rts]>=SAFE_MIN,"Safe",IF([rts]>=WATCH_MIN,"Watch","Escalate")))', "txt"),
        ("esc", "Escalate trigger", '=IF([idx]=0,0,IF(OR([bnow]=1,AND(ISNUMBER([pb]),N([pb])>=ESC_P),AND([state]="Ponzi",[mig]<>"improving")),1,0))', "int"),
        ("watch", "Watch trigger", '=IF([idx]=0,0,IF(OR(AND(ISNUMBER([pb]),N([pb])>=WATCH_P),AND([state]="Ponzi",[mig]="improving"),AND([state]="Speculative",[mig]="deteriorating"),'
                                  'AND(ISNUMBER([fa3m]),N([fa3m])<1),AND(ISNUMBER([refi3]),N([refi3])>REFI_THR),AND(ISNUMBER([stretch_share]),N([stretch_share])>STRETCH_THR)),1,0))', "int"),
        ("cls", "RTS class (final)", '=IF([score_class]="Insufficient data",[score_class],IF(OR([esc]=1,[score_class]="Escalate"),"Escalate",IF(OR([watch]=1,[score_class]="Watch"),"Watch","Safe")))', "txt"),
        ("py_rts", "Python RTS", None, "sc"),
        ("py_cls", "Python class", None, "txt"),
        ("chk", "Check (0 = Excel equals Python)", '=IF(AND(ISNUMBER([py_rts]),ISNUMBER([rts])),IF(ABS([py_rts]-[rts])>0.001,1,0),IF(ISNUMBER([py_rts])=ISNUMBER([rts]),0,1))+IF([py_cls]=[cls],0,1)', "int"),
        ("reasons", "Reasons (Python)", None, "txt"),
        ("triggers", "Triggers (Python)", None, "txt"),
    ]
    gc = Grid(wsC, [(c[0], c[1], c[3]) for c in ccols], len(S))
    _header(wsC, [c[1] for c in ccols], notes={c[1]: c[2] for c in ccols if c[2]})
    for i, r in enumerate(S.itertuples(index=False), 2):
        for j, (k, lab, tmpl, fmt) in enumerate(ccols, 1):
            if k == "symbol":
                v = r.symbol
            elif k == "py_rts":
                v = None if pd.isna(r.rts) else float(r.rts)
            elif k == "py_cls":
                v = r.rts_class
            elif k in ("reasons", "triggers"):
                v = getattr(r, k) if isinstance(getattr(r, k, None), str) else ""
            else:
                v = gc.expand(tmpl, i)
            c = wsC.cell(i, j, v)
            _font(c, BLUE if k in ("symbol", "py_rts", "py_cls", "reasons", "triggers") else BLACK,
                  bold=k in ("rts", "cls"))
            _fmt(c, fmt)
    for j, c in enumerate(ccols, 1):
        wsC.column_dimensions[get_column_letter(j)].width = 70 if c[0] in ("reasons", "triggers") else 13

    # ----------------------------------------------------------- Migration
    wsM = wb.create_sheet("Migration")
    order = ["Hedge", "Speculative", "Ponzi"]
    _font(wsM.cell(1, 1, "1-year Minsky transition matrix (all consecutive company-years): rows = from, columns = to"), bold=True)
    _font(wsM.cell(9, 1, f"Latest scored FY vs state {cfg.migration_years} fiscal years earlier (one row per company)"), bold=True)
    for top, frm, to in ((2, an("prev_state"), an("state")), (10, gc.rng("state3", "Company"), gc.rng("state", "Company"))):
        for j, s in enumerate(order):
            wsM.cell(top, 2 + j, s)
            wsM.cell(top, 7 + j, s + " %")
            wsM.cell(top + 1 + j, 1, s)
            wsM.cell(top + 1 + j, 6, s)
        wsM.cell(top, 5, "Total")
        for a_, s1 in enumerate(order):
            rr = top + 1 + a_
            for b_, s2 in enumerate(order):
                c = wsM.cell(rr, 2 + b_, f'=COUNTIFS({frm},"{s1}",{to},"{s2}")')
                _font(c)
                p = wsM.cell(rr, 7 + b_, f"=IF($E{rr}>0,{get_column_letter(2 + b_)}{rr}/$E{rr},\"\")")
                p.number_format = PCT
                _font(p)
            _font(wsM.cell(rr, 5, f"=SUM(B{rr}:D{rr})"))
        for col in range(1, 10):
            _font(wsM.cell(top, col), bold=True)
    wsM.column_dimensions["A"].width = 14

    # ----------------------------------------------------------- Checks
    wsK = wb.create_sheet("Checks")
    _font(wsK.cell(1, 1, "Cross-check: Excel formulas vs the Python engine (all should be 0)"), bold=True)
    rows = [("Annual rows checked", f"=COUNTA({an('symbol')})"),
            ("Annual rows where Excel differs from Python (CFO_adj, FA-DSCR, state)", f"=COUNTIF({an('chk')},\">0\")"),
            ("Companies checked", f"=COUNTA({gc.rng('symbol', 'Company')})"),
            ("Companies where Excel RTS or class differs from Python", f"=COUNTIF({gc.rng('chk', 'Company')},\">0\")"),
            ("Breach-now: Excel formula vs Python status mismatches",
             f'=SUMPRODUCT(({gb.rng("breach_now", "BreachClock")}=1)*({gb.rng("status", "BreachClock")}<>"already_in_breach"))'
             f'+SUMPRODUCT(({gb.rng("breach_now", "BreachClock")}=0)*({gb.rng("status", "BreachClock")}="already_in_breach"))')]
    for k, (lab, f) in enumerate(rows, 3):
        wsK.cell(k, 1, lab)
        _font(wsK.cell(k, 2, f), bold=True)
    wsK.column_dimensions["A"].width = 70

    # ----------------------------------------------------------- README
    _readme(readme, cfg, title_note, len(src), len(A), len(S))
    wb.save(path)
    return path


def _readme(ws, cfg, note, n_src, n_ann, n_co):
    lines = [
        ("Debt-Service Truth Monitor - Repayment Truth Score (RTS) calculation sheet", True),
        (note, True),
        ("", False),
        ("HOW TO TRACE A NUMBER", True),
        ("Every input in Annual / Quarters / BreachClock is a GREEN link to one row of Sources. Sources holds the value exactly as "
         "taken from Screener, the source line (statement > breakdown > line item), any flag, the request URL and the UTC fetch time.", False),
        ("Black cells are formulas (hover the column header for the formula). Blue cells are hard values: Sources values, "
         "Python Monte Carlo results, and Python results kept for the Checks sheet. Yellow cells on Settings are the levers.", False),
        ("", False),
        ("CALCULATION CHAIN", True),
        ("1  CFO_adj = CFO - payables stretch beyond own 3-yr norm - positive exceptional items - non-core income inside CFO.", False),
        ("2  CFADS = CFO_adj + interest add-back (auto: only interest paid INSIDE CFO; most Indian firms pay it in financing).", False),
        ("3  FA-DSCR = CFADS / (interest paid + repayments); variant after maintenance capex = (CFADS - depreciation) / same.", False),
        ("4  Minsky: Hedge CFADS >= interest + repayments; Speculative CFADS >= interest; Ponzi otherwise. Migration vs mean of prior 3 yrs.", False),
        ("5  Refinancing dependence = new borrowing / (interest + repayments), pooled over 3 fiscal years.", False),
        ("6  Breach Clock: Python Monte Carlo (paired seasonal YoY bootstrap of 13 quarters) of TTM ICR and Debt/EBITDA.", False),
        ("7  RTS = weighted sub-scores (Settings), re-normalised over available components; Safe / Watch / Escalate + overrides.", False),
        ("", False),
        ("PROXIES (stated honestly)", True),
        ("Payable days use operating expenses (Sales - Operating Profit) because cost of goods sold is not available for every company.", False),
        ("Repayments are GROSS (include roll-over of short-term debt); scheduled principal is not on Screener.", False),
        ("Lease principal = Screener 'Financial liabilities' outflow; maintenance capex = depreciation.", False),
        ("Debt in the Breach Clock is held at the latest reported balance sheet; quarterly debt is not available.", False),
        ("When no cash-flow interest line exists, P&L interest is used and its location (CFO vs financing) is inferred.", False),
        ("", False),
        (f"Contents: {n_src:,} source rows, {n_ann:,} company-years, {n_co:,} companies.", False),
        ("Recalculate after editing Settings (Excel does this automatically). Monte Carlo values need: python -m dstm_rts run.", False),
    ]
    for i, (t, b) in enumerate(lines, 1):
        c = ws.cell(i, 1, t)
        _font(c, bold=b)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 140
