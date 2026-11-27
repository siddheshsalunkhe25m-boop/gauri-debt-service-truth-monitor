"""SYNTHETIC history (FY2015-FY2026, 13 quarters, weekly prices) with a PLANTED distress pattern, used only to
test that the validation machinery works (leakage test, outcome definitions, AUC plumbing). It says nothing
about whether RTS works on real companies."""
from __future__ import annotations

import numpy as np
import pandas as pd

FY = [f"{y}-03-31" for y in range(2015, 2027)]
QE = pd.period_range("2023-09", periods=13, freq="Q-DEC").to_timestamp(how="end").strftime("%Y-%m-%d").tolist()


def synthetic_history(n: int = 60, seed: int = 11, shock_share: float = 0.35):
    rng = np.random.default_rng(seed)
    rows, prices = [], []
    weeks = pd.date_range("2014-01-03", "2026-11-20", freq="7D").strftime("%Y-%m-%d")
    for k in range(n):
        sym = f"SYN{k:03d}"
        shock = int(rng.integers(2018, 2026)) if rng.random() < shock_share else None
        rev0, g = rng.uniform(2000, 20000), rng.uniform(0.02, 0.12)
        margin, lev = rng.uniform(0.12, 0.25), rng.uniform(0.5, 3.0)
        price, px_path = rng.uniform(100, 1000), []
        for i, pend in enumerate(FY):
            y = 2015 + i
            rev = rev0 * (1 + g) ** i
            m = margin
            conv, pay_days, raised_mult = rng.uniform(0.85, 1.05), 60, 0.8
            if shock and shock - 2 <= y < shock:           # warning years: cash quality deteriorates
                conv, pay_days, raised_mult = rng.uniform(0.35, 0.6), 100, 1.4
            if shock and y >= shock:                        # shock: margins collapse
                m = rng.uniform(-0.05, 0.04)
                conv, raised_mult = rng.uniform(0.3, 0.8), 1.5
            ebitda = rev * m
            debt = rev * margin * lev
            interest = debt * 0.09
            dep = rev * 0.04
            np_ = (ebitda - interest - dep) * 0.75
            opex = rev - ebitda
            vals = {"revenue": rev, "operating_expenses": opex, "ebitda": ebitda, "depreciation": dep,
                    "net_profit": np_, "interest_expense": interest, "cfo": max(ebitda, rev * 0.01) * conv,
                    "trade_payables": opex * pay_days / 365, "exceptional_items": 0.0,
                    "other_income_recurring": rev * 0.01, "interest_received": rev * 0.005, "dividends_received": 0.0,
                    "interest_paid": interest, "principal_repaid": debt * 0.15, "financial_liabilities_paid": 0.0,
                    "borrowings_raised": debt * 0.15 * raised_mult, "other_financing_items": 0.0,
                    "total_borrowings": debt, "total_assets": rev * 1.1, "cash_and_equivalents": rev * 0.05}
            for f, v in vals.items():
                rows.append(_row(sym, "FY", pend, f, v))
        for j, qe in enumerate(QE):
            y = int(qe[:4]) + (1 if qe[5:7] in ("06", "09", "12") else 0)
            rev = rev0 * (1 + g) ** (y - 2015) / 4
            m = rng.uniform(-0.05, 0.04) if shock and y >= shock else margin
            rows.append(_row(sym, "Q", qe, "ebitda", rev * m * rng.uniform(0.9, 1.1)))
            rows.append(_row(sym, "Q", qe, "interest_expense", rev0 * (1 + g) ** (y - 2015) * margin * lev * 0.09 / 4))
        rows.append(_row(sym, "interim", "2026-09-30", "total_borrowings", rev0 * (1 + g) ** 11 * margin * lev))
        for w in weeks:
            y = int(w[:4]) + (1 if w[5:7] > "06" else 0)
            drift = -0.012 if shock and shock <= y <= shock + 1 else 0.002
            price *= float(np.exp(drift + rng.normal(0, 0.03)))
            prices.append({"symbol": sym, "date": w, "close": round(price, 2)})
    return pd.DataFrame(rows), pd.DataFrame(prices)


def _row(sym, freq, pend, field, value):
    return {"symbol": sym, "basis": "consolidated", "basis_role": "primary", "frequency": freq, "period_end": pend,
            "period_label": pend[:7], "period_months": 12 if freq == "FY" else 3, "field": field, "value": float(value),
            "unit": "Rs Cr", "source": "synthetic", "flag": "", "source_url": "synthetic://", "fetched_at": "2026-11-23"}
