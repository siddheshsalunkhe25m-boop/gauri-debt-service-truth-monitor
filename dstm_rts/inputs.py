"""Turn the data layer's `credit_lines` (long format) into the panels the RTS engine needs.

Only the company's PRIMARY basis is used (consolidated, or standalone when consolidated is missing or
stale; see dstm_data). Every value keeps a pointer to its source line so the calculation sheet can trace it.
"""
from __future__ import annotations

import pandas as pd

ANNUAL_FIELDS = [
    "revenue", "operating_expenses", "ebitda", "other_income", "other_income_recurring", "exceptional_items",
    "interest_expense", "depreciation", "net_profit", "cfo", "trade_payables", "interest_received",
    "dividends_received", "interest_paid", "interest_paid_in_cfo", "principal_repaid", "financial_liabilities_paid",
    "borrowings_raised", "other_financing_items", "total_borrowings", "lease_liabilities", "cash_and_equivalents",
    "total_assets", "capex",
]
QUARTER_FIELDS = ["revenue", "ebitda", "interest_expense", "depreciation", "net_profit"]
DEBT_FIELDS = ["total_borrowings", "lease_liabilities", "cash_and_equivalents"]


def primary(cl: pd.DataFrame) -> pd.DataFrame:
    return cl[cl["basis_role"] == "primary"].copy()


def annual_panel(cl: pd.DataFrame) -> pd.DataFrame:
    """One row per symbol x fiscal year with the input fields (wide) + `interest_paid_flag` + period metadata."""
    d = primary(cl)
    d = d[(d.frequency == "FY") & d.field.isin(ANNUAL_FIELDS)]
    wide = d.pivot_table(index=["symbol", "period_end"], columns="field", values="value", aggfunc="first")
    meta = d.groupby(["symbol", "period_end"]).agg(period_label=("period_label", "first"),
                                                  period_months=("period_months", "max"))
    flag = d[d.field == "interest_paid"].set_index(["symbol", "period_end"])["flag"].rename("interest_paid_flag")
    out = wide.join(meta).join(flag).reset_index()
    for f in ANNUAL_FIELDS:
        if f not in out:
            out[f] = float("nan")
    out["period_months"] = out["period_months"].fillna(12)
    return out.sort_values(["symbol", "period_end"]).reset_index(drop=True)


def quarter_panel(cl: pd.DataFrame) -> pd.DataFrame:
    d = primary(cl)
    d = d[(d.frequency == "Q") & d.field.isin(QUARTER_FIELDS)]
    wide = d.pivot_table(index=["symbol", "period_end"], columns="field", values="value", aggfunc="first").reset_index()
    for f in QUARTER_FIELDS:
        if f not in wide:
            wide[f] = float("nan")
    return wide.sort_values(["symbol", "period_end"]).reset_index(drop=True)


def latest_debt(cl: pd.DataFrame) -> pd.DataFrame:
    """Latest reported debt per symbol: the most recent of the FY and interim (half-year) balance sheets."""
    d = primary(cl)
    d = d[d.frequency.isin(["FY", "interim"]) & d.field.isin(DEBT_FIELDS) & d.period_end.notna()]
    last = d[d.field == "total_borrowings"].groupby("symbol").period_end.max().rename("debt_date")
    d = d.join(last, on="symbol")
    d = d[d.period_end == d.debt_date]
    wide = d.pivot_table(index=["symbol", "debt_date"], columns="field", values="value", aggfunc="first").reset_index()
    for f in DEBT_FIELDS:
        if f not in wide:
            wide[f] = float("nan")
    return wide


def source_index(cl: pd.DataFrame) -> pd.DataFrame:
    """(symbol, frequency, period_end, field) -> value, source line, flag: the trace table."""
    d = primary(cl)
    return d[["symbol", "basis", "frequency", "period_end", "period_label", "field", "value", "unit", "source", "flag"]]
