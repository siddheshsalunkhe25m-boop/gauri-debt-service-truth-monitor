"""Map Screener line items to a fixed set of credit-analysis fields ("credit lines").

No ratios or scores here: only the raw building blocks a debt-service analysis needs, each with
its source and a flag when a fallback or a zero-fill was used.

Sign convention: cash OUTFLOWS that are named "..._paid", "capex", "principal_repaid",
"acquisitions" and "taxes_paid" are stored as POSITIVE amounts (Screener shows them negative).
Everything else keeps Screener's sign.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

PL, BS, CF, Q = "profit-loss", "balance-sheet", "cash-flow", "quarters"
CFO_P, CFI_P, CFF_P = "Cash from Operating Activity", "Cash from Investing Activity", "Cash from Financing Activity"

# field, statement, parent (None = main table row), exact line item, transform
SIMPLE = [
    # profit & loss (FY + TTM)
    ("revenue", PL, None, "Sales", "raw"),
    ("operating_expenses", PL, None, "Expenses", "raw"),
    ("ebitda", PL, None, "Operating Profit", "raw"),
    ("ebitda_margin_pct", PL, None, "OPM %", "raw"),
    ("other_income", PL, None, "Other Income", "raw"),
    ("interest_expense", PL, None, "Interest", "raw"),
    ("depreciation", PL, None, "Depreciation", "raw"),
    ("pbt", PL, None, "Profit before tax", "raw"),
    ("tax_rate_pct", PL, None, "Tax %", "raw"),
    ("net_profit", PL, None, "Net Profit", "raw"),
    ("dividend_payout_pct", PL, None, "Dividend Payout %", "raw"),
    ("exceptional_items", PL, "Other Income", "Exceptional items", "raw"),
    ("other_income_recurring", PL, "Other Income", "Other income normal", "raw"),
    ("minority_share_of_profit", PL, "Net Profit", "Minority share", "raw"),
    ("profit_from_associates", PL, "Net Profit", "Profit from Associates", "raw"),
    ("exceptional_items_after_tax", PL, "Net Profit", "Exceptional items AT", "raw"),
    ("net_profit_excl_exceptional", PL, "Net Profit", "Profit excl Excep", "raw"),
    # balance sheet (FY + interim)
    ("equity_capital", BS, None, "Equity Capital", "raw"),
    ("reserves", BS, None, "Reserves", "raw"),
    ("total_borrowings", BS, None, "Borrowings", "raw"),
    ("other_liabilities", BS, None, "Other Liabilities", "raw"),
    ("balance_sheet_total", BS, None, "Total Liabilities", "raw"),
    ("net_fixed_assets", BS, None, "Fixed Assets", "raw"),
    ("cwip", BS, None, "CWIP", "raw"),
    ("investments", BS, None, "Investments", "raw"),
    ("other_assets", BS, None, "Other Assets", "raw"),
    ("total_assets", BS, None, "Total Assets", "raw"),
    ("lt_borrowings", BS, "Borrowings", "Long term Borrowings", "raw"),
    ("st_borrowings", BS, "Borrowings", "Short term Borrowings", "raw"),
    ("lease_liabilities", BS, "Borrowings", "Lease Liabilities", "raw"),
    ("preference_capital", BS, "Borrowings", "Preference Capital", "raw"),
    ("other_borrowings", BS, "Borrowings", "Other Borrowings", "raw"),
    ("trade_payables", BS, "Other Liabilities", "Trade Payables", "raw"),
    ("customer_advances", BS, "Other Liabilities", "Advance from Customers", "raw"),
    ("minority_interest", BS, "Other Liabilities", "Non controlling int", "raw"),
    ("inventories", BS, "Other Assets", "Inventories", "raw"),
    ("trade_receivables", BS, "Other Assets", "Trade receivables", "raw"),
    ("cash_and_equivalents", BS, "Other Assets", "Cash Equivalents", "raw"),
    ("loans_and_advances", BS, "Other Assets", "Loans n Advances", "raw"),
    ("receivables_over_6m", BS, "Trade receivables", "Receivables over 6m", "raw"),
    ("receivables_under_6m", BS, "Trade receivables", "Receivables under 6m", "raw"),
    ("provision_doubtful_debts", BS, "Trade receivables", "Prov for Doubtful", "raw"),
    # cash flow (FY)
    ("cfo", CF, None, "Cash from Operating Activity", "raw"),
    ("cfi", CF, None, "Cash from Investing Activity", "raw"),
    ("cff", CF, None, "Cash from Financing Activity", "raw"),
    ("net_cash_flow", CF, None, "Net Cash Flow", "raw"),
    ("cfo_before_wc", CF, CFO_P, "Profit from operations", "raw"),
    ("wc_chg_receivables", CF, CFO_P, "Receivables", "raw"),
    ("wc_chg_inventory", CF, CFO_P, "Inventory", "raw"),
    ("wc_chg_payables", CF, CFO_P, "Payables", "raw"),
    ("wc_chg_loans_advances", CF, CFO_P, "Loans Advances", "raw"),
    ("wc_chg_other", CF, CFO_P, "Other WC items", "raw"),
    ("wc_change_total", CF, CFO_P, "Working capital changes", "raw"),
    ("taxes_paid", CF, CFO_P, "Direct taxes", "neg"),
    ("capex", CF, CFI_P, "Fixed assets purchased", "neg"),
    ("asset_sale_proceeds", CF, CFI_P, "Fixed assets sold", "raw"),
    ("acquisitions", CF, CFI_P, "Acquisition of companies", "neg"),
    ("interest_received", CF, CFI_P, "Interest received", "raw"),
    ("dividends_received", CF, CFI_P, "Dividends received", "raw"),
    ("equity_raised", CF, CFF_P, "Proceeds from shares", "raw"),
    ("dividends_paid", CF, CFF_P, "Dividends paid", "neg"),
    ("financial_liabilities_paid", CF, CFF_P, "Financial liabilities", "neg"),   # mostly lease-liability payments (Ind AS 116)
    ("other_financing_items", CF, CFF_P, "Other financing items", "raw"),
    # quarters
    ("revenue", Q, None, "Sales", "raw"),
    ("operating_expenses", Q, None, "Expenses", "raw"),
    ("ebitda", Q, None, "Operating Profit", "raw"),
    ("ebitda_margin_pct", Q, None, "OPM %", "raw"),
    ("other_income", Q, None, "Other Income", "raw"),
    ("interest_expense", Q, None, "Interest", "raw"),
    ("depreciation", Q, None, "Depreciation", "raw"),
    ("pbt", Q, None, "Profit before tax", "raw"),
    ("tax_rate_pct", Q, None, "Tax %", "raw"),
    ("net_profit", Q, None, "Net Profit", "raw"),
    ("exceptional_items", Q, "Other Income", "Exceptional items", "raw"),
]

# Children of the financing schedule, matched by pattern (firms add lines such as
# "Redemption of debentures"). Matching is case-insensitive on the child name.
RE_REPAY = re.compile(r"repay|redemp|redeem", re.I)
RE_RAISE = re.compile(r"proceeds from (borrow|debenture|loan|deposit)|issue of debenture|proceeds.*borrow", re.I)
RE_INTEREST = re.compile(r"interest", re.I)
RE_SHARES = re.compile(r"share|equity", re.I)
KNOWN_CFF = {"Proceeds from shares", "Dividends paid", "Financial liabilities", "Other financing items"}

TOP_RATIOS = {"Market Cap": "market_cap", "Current Price": "current_price", "Stock P/E": "stock_pe",
              "Book Value": "book_value_per_share", "Dividend Yield": "dividend_yield_pct",
              "ROCE": "roce_pct", "ROE": "roe_pct", "Face Value": "face_value"}


def _freq(ptype: str) -> str:
    return {"FY": "FY", "TTM": "TTM", "Q": "Q", "interim": "interim"}.get(ptype, ptype)


def build_credit_lines(rows: list[dict], fetched_schedules: dict) -> list[dict]:
    """rows: tidy rows of ONE symbol and ONE basis.
    fetched_schedules: {(section, parent): {child names in the JSON}} for schedules available (live or cached).
    A child ABSENT from a fetched schedule is a real zero ("absent_line_zero"); a child that is present
    but blank stays unknown; a schedule that could not be fetched leaves its lines unknown."""
    fetched_schedules = {k: set(v) for k, v in (fetched_schedules.items() if isinstance(fetched_schedules, dict)
                                                 else ((k, set()) for k in fetched_schedules))}
    has_period = set()
    idx = {}
    periods = defaultdict(dict)      # statement -> period_end -> (label, ptype, months)
    children = defaultdict(set)      # (statement, parent) -> child names
    refs = {}                        # (statement, parent) -> (source_url, fetched_at)
    for r in rows:
        refs.setdefault((r["statement"], r["parent"]), (r.get("source_url"), r.get("fetched_at")))
        if r["statement"] == "top-ratios":
            continue
        key = (r["statement"], r["parent"], r["line_item"], r["period_type"], r["period_end"])
        idx[key] = r
        if r["parent"] is None and (r["period_end"] or r["period_type"] == "TTM"):
            periods[r["statement"]][(r["period_type"], r["period_end"])] = (r["period_label"], r["period_months"])
        if r["parent"]:
            children[(r["statement"], r["parent"])].add(r["line_item"])
            has_period.add((r["statement"], r["parent"], r["period_type"], r["period_end"]))

    out = []

    def emit(field, stmt, ptype, pend, val, unit, source, flag="", parent=None):
        label, months = periods[stmt].get((ptype, pend), (None, None))
        url, ts = refs.get((stmt, parent)) or refs.get((stmt, None)) or (None, None)
        out.append({"frequency": _freq(ptype), "period_end": pend, "period_label": label, "period_months": months,
                    "field": field, "value": val, "unit": unit, "source": source, "flag": flag,
                    "source_url": url, "fetched_at": ts})

    # 1) one-to-one fields --------------------------------------------------------------
    for field, stmt, parent, item, tr in SIMPLE:
        for (ptype, pend) in periods.get(stmt, {}):
            r = idx.get((stmt, parent, item, ptype, pend))
            src = f"{stmt}:{parent + ' > ' if parent else ''}{item}"
            if r is not None:
                v = -r["value"] if tr == "neg" else r["value"]
                emit(field, stmt, ptype, pend, v, r["unit"], src, "standalone_fill" if r["is_standalone_fill"] else "", parent)
            elif parent and (stmt, parent) in fetched_schedules and item not in fetched_schedules[(stmt, parent)] \
                    and (stmt, parent, ptype, pend) in has_period:
                emit(field, stmt, ptype, pend, 0.0, "Rs Cr", src, "absent_line_zero", parent)

    # 2) derived balance-sheet lines ------------------------------------------------------
    for (ptype, pend) in periods.get(BS, {}):
        eq = idx.get((BS, None, "Equity Capital", ptype, pend))
        rs = idx.get((BS, None, "Reserves", ptype, pend))
        if eq and rs:
            emit("net_worth", BS, ptype, pend, eq["value"] + rs["value"], "Rs Cr", "Equity Capital + Reserves")
        tb = idx.get((BS, None, "Borrowings", ptype, pend))
        ll = idx.get((BS, "Borrowings", "Lease Liabilities", ptype, pend))
        if tb is not None and (ll is not None or (BS, "Borrowings") in fetched_schedules):
            emit("borrowings_ex_leases", BS, ptype, pend, tb["value"] - (ll["value"] if ll else 0.0), "Rs Cr",
                 "Borrowings - Lease Liabilities", "" if ll else "lease_line_absent", "Borrowings" if ll else None)

    # 3) financing-flow lines with pattern matching + interest-paid fallback ---------------
    cff_children = children.get((CF, CFF_P), set())
    cfo_children = children.get((CF, CFO_P), set())
    have_cff = (CF, CFF_P) in fetched_schedules
    have_cfo = (CF, CFO_P) in fetched_schedules
    repay = sorted(c for c in cff_children if RE_REPAY.search(c) and not RE_SHARES.search(c))
    raise_ = sorted(c for c in cff_children if RE_RAISE.search(c))
    int_cff = sorted(c for c in cff_children if RE_INTEREST.search(c) and "received" not in c.lower())
    int_cfo = sorted(c for c in cfo_children if RE_INTEREST.search(c) and "received" not in c.lower())

    for (ptype, pend) in periods.get(CF, {}):
        if ptype != "FY":
            continue

        def total(names, parent):
            vals = [idx[(CF, parent, n, ptype, pend)]["value"] for n in names if (CF, parent, n, ptype, pend) in idx]
            return (sum(vals), True) if vals else (0.0, False)

        if have_cff:
            v, found = total(repay, CFF_P)
            emit("principal_repaid", CF, ptype, pend, -v, "Rs Cr", "cash-flow:" + CFF_P + " > " + (" + ".join(repay) or "(no repayment line)"),
                 "" if found else "absent_line_zero", CFF_P)
            v, found = total(raise_, CFF_P)
            emit("borrowings_raised", CF, ptype, pend, v, "Rs Cr", "cash-flow:" + CFF_P + " > " + (" + ".join(raise_) or "(no proceeds line)"),
                 "" if found else "absent_line_zero", CFF_P)

        # interest actually paid: financing CF -> operating CF -> P&L interest expense
        v_cff, f_cff = total(int_cff, CFF_P) if have_cff else (0.0, False)
        v_cfo, f_cfo = total(int_cfo, CFO_P) if have_cfo else (0.0, False)
        f_cff, f_cfo = f_cff and v_cff != 0, f_cfo and v_cfo != 0
        pl_int = idx.get((PL, None, "Interest", "FY", pend))
        if f_cfo:   # portion of interest already deducted inside CFO (needed to rebuild pre-interest cash flow)
            emit("interest_paid_in_cfo", CF, ptype, pend, -v_cfo, "Rs Cr", f"cash-flow:{CFO_P} > {' + '.join(int_cfo)}", "", CFO_P)
        if f_cff and f_cfo:
            emit("interest_paid", CF, ptype, pend, -(v_cff + v_cfo), "Rs Cr",
                 f"cash-flow:{CFF_P} > {' + '.join(int_cff)} + {CFO_P} > {' + '.join(int_cfo)}", "interest_split_cfo_cff", CFF_P)
        elif f_cff:
            emit("interest_paid", CF, ptype, pend, -v_cff, "Rs Cr", f"cash-flow:{CFF_P} > {' + '.join(int_cff)}", "", CFF_P)
        elif f_cfo:
            emit("interest_paid", CF, ptype, pend, -v_cfo, "Rs Cr", f"cash-flow:{CFO_P} > {' + '.join(int_cfo)}", "interest_in_cfo", CFO_P)
        elif pl_int is not None:
            url, ts = refs.get((PL, None), (None, None))
            out.append({"frequency": "FY", "period_end": pend, "period_label": periods[CF].get((ptype, pend), (None,))[0],
                        "period_months": periods[CF].get((ptype, pend), (None, None))[1], "field": "interest_paid",
                        "value": pl_int["value"], "unit": "Rs Cr", "source": "profit-loss:Interest (P&L expense)",
                        "flag": "fallback_pnl_interest", "source_url": url, "fetched_at": ts})

    # 4) snapshot ratios ---------------------------------------------------------------------
    for r in rows:
        if r["statement"] == "top-ratios" and r["line_item"] in TOP_RATIOS:
            out.append({"frequency": "snapshot", "period_end": None, "period_label": "snapshot", "period_months": None,
                        "field": TOP_RATIOS[r["line_item"]], "value": r["value"], "unit": r["unit"],
                        "source": f"top-ratios:{r['line_item']}", "flag": "", "source_url": r.get("source_url"), "fetched_at": r.get("fetched_at")})
        elif r["statement"] == "top-ratios" and r["line_item"] in ("High", "Low"):
            out.append({"frequency": "snapshot", "period_end": None, "period_label": "snapshot", "period_months": None,
                        "field": f"price_52w_{r['line_item'].lower()}", "value": r["value"], "unit": r["unit"],
                        "source": "top-ratios:High / Low", "flag": "", "source_url": r.get("source_url"), "fetched_at": r.get("fetched_at")})
    return out


def unmapped_cff_children(children: set[str]) -> list[str]:
    return sorted(c for c in children if c not in KNOWN_CFF and not RE_REPAY.search(c)
                  and not RE_RAISE.search(c) and not RE_INTEREST.search(c))
