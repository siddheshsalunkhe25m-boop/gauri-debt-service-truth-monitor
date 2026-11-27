"""SYNTHETIC demo universe in the data layer's credit_lines format (for building / checking the workbook
before real Screener data is available). Symbols start with DEMO_ and every source URL says demo."""
from __future__ import annotations

import numpy as np
import pandas as pd

FY = [f"{y}-03-31" for y in range(2019, 2027)]
QE = pd.period_range("2023-09", periods=13, freq="Q-DEC").to_timestamp(how="end").strftime("%Y-%m-%d").tolist()


def _rows(sym, fy_data, q_data, debt_now, debt_date="2026-09-30"):
    out = []
    url = f"demo://synthetic/{sym}"

    def add(freq, pend, field, val, source, flag=""):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return
        out.append({"symbol": sym, "basis": "consolidated", "basis_role": "primary", "frequency": freq,
                    "period_end": pend, "period_label": pend[:7] if pend else None, "period_months": 12 if freq == "FY" else 3,
                    "field": field, "value": float(val), "unit": "Rs Cr", "source": source, "flag": flag,
                    "source_url": url, "fetched_at": "2026-11-23T07:20:00+00:00"})
    src = {"cfo": "cash-flow:Cash from Operating Activity", "operating_expenses": "profit-loss:Expenses",
           "revenue": "profit-loss:Sales", "ebitda": "profit-loss:Operating Profit", "depreciation": "profit-loss:Depreciation",
           "net_profit": "profit-loss:Net Profit", "interest_expense": "profit-loss:Interest",
           "trade_payables": "balance-sheet:Other Liabilities > Trade Payables",
           "exceptional_items": "profit-loss:Other Income > Exceptional items",
           "other_income_recurring": "profit-loss:Other Income > Other income normal",
           "interest_received": "cash-flow:Cash from Investing Activity > Interest received",
           "dividends_received": "cash-flow:Cash from Investing Activity > Dividends received",
           "interest_paid": "cash-flow:Cash from Financing Activity > Interest paid fin",
           "principal_repaid": "cash-flow:Cash from Financing Activity > Repayment of borrowings",
           "financial_liabilities_paid": "cash-flow:Cash from Financing Activity > Financial liabilities",
           "borrowings_raised": "cash-flow:Cash from Financing Activity > Proceeds from borrowings",
           "other_financing_items": "cash-flow:Cash from Financing Activity > Other financing items",
           "total_borrowings": "balance-sheet:Borrowings", "total_assets": "balance-sheet:Total Assets",
           "cash_and_equivalents": "balance-sheet:Other Assets > Cash Equivalents",
           "lease_liabilities": "balance-sheet:Borrowings > Lease Liabilities"}
    for i, pend in enumerate(FY):
        for f, series in fy_data.items():
            if f == "interest_paid_flag":
                continue
            flag = fy_data.get("interest_paid_flag", [""] * len(FY))[i] if f == "interest_paid" else ""
            s = "profit-loss:Interest (P&L expense)" if flag == "fallback_pnl_interest" and f == "interest_paid" else src[f]
            add("FY", pend, f, series[i], s, flag)
    for j, pend in enumerate(QE):
        add("Q", pend, "ebitda", q_data[0][j], "quarters:Operating Profit")
        add("Q", pend, "interest_expense", q_data[1][j], "quarters:Interest")
    add("interim", debt_date, "total_borrowings", debt_now, "balance-sheet:Borrowings")
    return out


def demo_credit_lines(seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(FY)
    rows = []

    def base(rev0, growth, margin, cfo_conv, int_, rep, raised, debt, pay_days=60, lease=0.0):
        rev = rev0 * (1 + growth) ** np.arange(n)
        ebitda = rev * margin
        opex = rev - ebitda
        return {"revenue": rev, "operating_expenses": opex, "ebitda": ebitda, "depreciation": rev * 0.04,
                "net_profit": ebitda * 0.45, "cfo": ebitda * cfo_conv, "trade_payables": opex * pay_days / 365,
                "exceptional_items": np.zeros(n), "other_income_recurring": rev * 0.01,
                "interest_received": rev * 0.006, "dividends_received": np.zeros(n),
                "interest_paid": np.full(n, int_), "principal_repaid": np.full(n, rep),
                "financial_liabilities_paid": np.full(n, lease), "borrowings_raised": np.full(n, raised),
                "other_financing_items": np.zeros(n), "total_borrowings": np.full(n, debt), "total_assets": rev * 1.2}

    def quarters(ebitda_annual, interest_annual, season=(0.22, 0.24, 0.26, 0.28), trend=0.0, noise=0.03):
        e = []
        for k in range(13):
            yr = k // 4
            e.append(ebitda_annual * season[k % 4] * (1 + trend) ** yr * (1 + rng.normal(0, noise)))
        i = [interest_annual / 4 * (1 + rng.normal(0, 0.02)) for _ in range(13)]
        return e, i

    # 1 strong, low leverage
    d = base(5000, 0.08, 0.20, 0.95, 60, 150, 50, 900)
    rows += _rows("DEMO_HEDGE", d, quarters(d["ebitda"][-1], 70, trend=0.06), 900)
    # 2 roll-over borrower: covers interest, not principal; refinances
    d = base(8000, 0.05, 0.14, 0.80, 450, 1400, 1300, 5200)
    rows += _rows("DEMO_ROLLOVER", d, quarters(d["ebitda"][-1], 480), 5300)
    # 3 deteriorating: margin collapse in the last 3 years -> Ponzi
    d = base(6000, 0.04, 0.16, 0.85, 380, 500, 600, 4200)
    for k, m in zip(range(5, 8), (0.09, 0.06, 0.035)):
        d["ebitda"][k] = d["revenue"][k] * m
        d["cfo"][k] = d["ebitda"][k] * 0.7
        d["operating_expenses"][k] = d["revenue"][k] - d["ebitda"][k]
    rows += _rows("DEMO_DECLINE", d, quarters(d["ebitda"][-1], 420, trend=-0.25, noise=0.08), 4600)
    # 4 airline-style lessee: big lease payments
    d = base(20000, 0.10, 0.22, 1.05, 900, 300, 200, 30000, lease=3200)
    d["lease_liabilities"] = np.full(n, 26000.0)
    rows += _rows("DEMO_LESSEE", d, quarters(d["ebitda"][-1], 1000, season=(0.27, 0.22, 0.25, 0.26), noise=0.06), 31000)
    # 5 payables stretch in the latest year flatters CFO
    d = base(4000, 0.06, 0.15, 0.90, 120, 250, 100, 1800, pay_days=55)
    d["trade_payables"][-1] = d["operating_expenses"][-1] * 110 / 365
    d["cfo"][-1] = d["cfo"][-1] + (d["trade_payables"][-1] - d["operating_expenses"][-1] * 55 / 365)
    d["exceptional_items"][-1] = 90.0
    rows += _rows("DEMO_STRETCH", d, quarters(d["ebitda"][-1], 125), 1850)
    # 6 debt-free cash generator
    d = base(12000, 0.09, 0.26, 0.95, 0.2, 0, 0, 0)
    d["other_income_recurring"] = d["revenue"] * 0.04
    d["interest_received"] = d["revenue"] * 0.03
    rows += _rows("DEMO_CASHRICH", d, quarters(d["ebitda"][-1], 0.4), 0)
    # 7 interest inside CFO reported via P&L fallback (no cash-flow interest line)
    d = base(3000, 0.07, 0.18, 0.75, 140, 160, 150, 1500)
    d["cfo"] = d["cfo"] - 140                       # CFO already after interest
    d["interest_paid_flag"] = ["fallback_pnl_interest"] * n
    rows += _rows("DEMO_INTCFO", d, quarters(d["ebitda"][-1], 140), 1500)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = demo_credit_lines()
    print(df.groupby("symbol").size())
