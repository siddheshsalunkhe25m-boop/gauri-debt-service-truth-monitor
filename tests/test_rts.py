"""RTS engine tests. Hand-worked numbers are written out in the docstrings.

Slide sources
  S5-6  Apex Auto Components (JPMorgan credit case): FY25 / FY26 CFO 135 / 45, EBITDA 180 / 225,
        net profit 90 / 105, total assets 1,200 / 1,500. Slide results: cash conversion 45/225 = 20%,
        accrual ratio (105-45)/1,350 = 4.4%. DSCR = CFADS / (interest + principal); < 1 = cannot service.
  S7-8  Healthy Pharma vs Growth Pharma: (NI - CFO) / average NOA = -20/1,285 = -1.6% and 180/1,640 = 11.0%.
  S9-10 credit-analyst example (used for the debt-service amounts the S5-6 case does not give):
        interest 30, debt repayment 50, FFO 130, CFO 60.
Where a number is NOT on a slide it is marked "assumed".
"""
import numpy as np
import pandas as pd
import pytest

from dstm_rts.breach import breach_clock
from dstm_rts.config import RTSConfig
from dstm_rts.engine import run_rts
from dstm_rts.metrics import annual_metrics, migration_matrices
from dstm_rts.score import company_scores, interp


def panel(rows):
    base = {"operating_expenses": np.nan, "trade_payables": np.nan, "exceptional_items": 0.0,
            "other_income_recurring": 0.0, "interest_received": 0.0, "dividends_received": 0.0,
            "interest_paid_flag": "", "interest_paid_in_cfo": np.nan, "financial_liabilities_paid": 0.0,
            "borrowings_raised": 0.0, "other_financing_items": 0.0, "depreciation": 0.0, "net_profit": np.nan,
            "ebitda": np.nan, "total_assets": np.nan, "period_months": 12, "period_label": None}
    return pd.DataFrame([{**base, **r} for r in rows])


def no_breach(symbols):
    return pd.DataFrame([{"symbol": s, "p_breach_base": 0.0, "p_breach_stress": 0.0, "median_q_base": None,
                          "median_q_stress": None, "icr_now": 10.0, "debt_ebitda_now": 1.0, "breach_now": False,
                          "breach_now_reason": "", "status": "ok", "n_quarters": 13, "debt": 100.0,
                          "debt_date": "2026-03-31"} for s in symbols])


# ---------------------------------------------------------------- Sessions 5-8 worked examples
def test_apex_auto_diagnostics_match_session_5_6():
    """S5-6: cash conversion FY26 = 45/225 = 20%; accrual ratio = (105-45)/((1500+1200)/2) = 60/1350 = 4.4%."""
    a = annual_metrics(panel([
        {"symbol": "APEX", "period_end": "2025-03-31", "cfo": 135, "ebitda": 180, "net_profit": 90, "total_assets": 1200,
         "interest_paid": 30, "principal_repaid": 50},
        {"symbol": "APEX", "period_end": "2026-03-31", "cfo": 45, "ebitda": 225, "net_profit": 105, "total_assets": 1500,
         "interest_paid": 30, "principal_repaid": 50}]), RTSConfig())
    fy26 = a.iloc[-1]
    assert fy26.cash_conversion == pytest.approx(0.20)
    assert round(fy26.sloan_ratio * 100, 1) == 4.4


def test_apex_auto_dscr_minsky_migration():
    """S5-6 CFO with S9-10 debt service (interest 30 + repayment 50 = 80); interest paid in financing,
    so CFADS = CFO (no add-back), no payables history -> no stretch adjustment.
    FY25: DSCR 135/80 = 1.6875 -> Hedge (135 >= 80).
    FY26: DSCR  45/80 = 0.5625 -> Speculative (30 <= 45 < 80).  Migration: 1 - 2 = -1 -> deteriorating.
    After maintenance capex (assumed depreciation 20): FY26 (45-20)/80 = 0.3125."""
    a = annual_metrics(panel([
        {"symbol": "APEX", "period_end": "2025-03-31", "cfo": 135, "interest_paid": 30, "principal_repaid": 50, "depreciation": 20},
        {"symbol": "APEX", "period_end": "2026-03-31", "cfo": 45, "interest_paid": 30, "principal_repaid": 50, "depreciation": 20}]),
        RTSConfig())
    assert list(a.fa_dscr.round(4)) == [1.6875, 0.5625]
    assert list(a.minsky_state) == ["Hedge", "Speculative"]
    assert a.iloc[-1].migration == "deteriorating"
    assert a.iloc[-1].fa_dscr_after_maint == pytest.approx(0.3125)


def test_session_9_10_ffo_vs_cfo_debt_service():
    """S9-10: FFO 130, CFO 60, interest 30, repayment 50. Cash (CFO) covers interest but not principal:
    DSCR 60/80 = 0.75 -> Speculative; on FFO it would look like 130/80 = 1.625 (Hedge) - the 'why isn't
    FFO converting into cash?' gap. Refinancing dependence with assumed new borrowing 60: 60/80 = 75%."""
    a = annual_metrics(panel([{"symbol": "S910", "period_end": "2026-03-31", "cfo": 60, "interest_paid": 30,
                               "principal_repaid": 50, "borrowings_raised": 60}]), RTSConfig())
    r = a.iloc[0]
    assert r.fa_dscr == pytest.approx(0.75) and r.minsky_state == "Speculative"
    assert r.refi_dependence == pytest.approx(0.75)
    ffo = annual_metrics(panel([{"symbol": "S910", "period_end": "2026-03-31", "cfo": 130, "interest_paid": 30,
                                 "principal_repaid": 50}]), RTSConfig()).iloc[0]
    assert ffo.fa_dscr == pytest.approx(1.625) and ffo.minsky_state == "Hedge"


def test_ponzi_state():
    """Assumed: CFO 25 < interest 30 -> Ponzi (cash does not even cover interest). DSCR 25/80 = 0.3125."""
    r = annual_metrics(panel([{"symbol": "P", "period_end": "2026-03-31", "cfo": 25, "interest_paid": 30,
                               "principal_repaid": 50}]), RTSConfig()).iloc[0]
    assert r.minsky_state == "Ponzi" and r.fa_dscr == pytest.approx(0.3125)


def test_growth_pharma_accrual_logic_session_7_8():
    """S7-8: (NI - CFO)/avg NOA. Healthy Pharma (200-220)/1285 = -1.6%; Growth Pharma (200-20)/1640 = 11.0%.
    The engine's accrual diagnostic uses the same numerator over average total assets; with NOA passed as
    the asset base it must reproduce the slide."""
    a = annual_metrics(panel([
        {"symbol": "A", "period_end": "2025-03-31", "cfo": 170, "net_profit": 180, "total_assets": 1250, "interest_paid": 0, "principal_repaid": 0},
        {"symbol": "A", "period_end": "2026-03-31", "cfo": 220, "net_profit": 200, "total_assets": 1320, "interest_paid": 0, "principal_repaid": 0},
        {"symbol": "B", "period_end": "2025-03-31", "cfo": 160, "net_profit": 180, "total_assets": 1250, "interest_paid": 0, "principal_repaid": 0},
        {"symbol": "B", "period_end": "2026-03-31", "cfo": 20, "net_profit": 200, "total_assets": 2030, "interest_paid": 0, "principal_repaid": 0}]),
        RTSConfig())
    last = a.groupby("symbol").tail(1).set_index("symbol")
    assert round(last.loc["A", "sloan_ratio"] * 100, 1) == -1.6
    assert round(last.loc["B", "sloan_ratio"] * 100, 1) == 11.0


# ---------------------------------------------------------------- forensic adjustments (hand-worked, assumed data)
def stretch_case(**last):
    rows = [{"symbol": "PAY", "period_end": f"{y}-03-31", "cfo": 300, "operating_expenses": 1000, "trade_payables": 100,
             "interest_paid": 50, "principal_repaid": 100} for y in (2023, 2024, 2025)]
    rows.append({"symbol": "PAY", "period_end": "2026-03-31", "cfo": 300, "operating_expenses": 1000, "trade_payables": 200,
                 "interest_paid": 50, "principal_repaid": 100, **last})
    return annual_metrics(panel(rows), RTSConfig()).iloc[-1]


def test_payables_stretch():
    """Opex 1,000 every year; payables 100 = 36.5 days for three years, then 200 = 73 days.
    Norm 36.5 days -> normal payables 36.5 x 1000/365 = 100 -> stretch 100.
    CFO_adj = 300 - 100 = 200; DSCR 200/(50+100) = 1.333 (reported CFO would give 2.0)."""
    r = stretch_case()
    assert r.payable_days == pytest.approx(73) and r.payable_days_norm == pytest.approx(36.5)
    assert r.payables_stretch == pytest.approx(100)
    assert r.cfo_adj == pytest.approx(200) and r.fa_dscr == pytest.approx(200 / 150)


def test_exceptional_and_noncore_deductions_hedge_boundary():
    """Same as above plus exceptional gain 40 and other income 30 of which interest received 20:
    non-core inside CFO = 30 - 20 = 10.  CFO_adj = 300 - 100 - 40 - 10 = 150 = debt service 150
    -> DSCR exactly 1.00 -> Hedge (boundary is inclusive)."""
    r = stretch_case(exceptional_items=40, other_income_recurring=30, interest_received=20)
    assert r.exceptional_gain_deducted == 40 and r.noncore_income_deducted == 10
    assert r.cfo_adj == pytest.approx(150) and r.fa_dscr == pytest.approx(1.0) and r.minsky_state == "Hedge"
    neg = stretch_case(exceptional_items=-40)          # exceptional LOSS: not added back, not deducted
    assert neg.exceptional_gain_deducted == 0


def test_interest_addback_modes():
    """Apex FY26 again but the company reports interest INSIDE CFO: CFO after interest = 45 - 30 = 15.
    auto   -> CFADS = 15 + 30 = 45 -> DSCR 0.5625 (same answer as the financing-reported version)
    always -> on the financing-reported firm (CFO 45) the textbook add-back double counts: (45+30)/80 = 0.9375
    never  -> 15/80 = 0.1875 on the in-CFO firm."""
    in_cfo = panel([{"symbol": "X", "period_end": "2026-03-31", "cfo": 15, "interest_paid": 30, "principal_repaid": 50,
                     "interest_paid_flag": "interest_in_cfo"}])
    in_cff = panel([{"symbol": "X", "period_end": "2026-03-31", "cfo": 45, "interest_paid": 30, "principal_repaid": 50}])
    assert annual_metrics(in_cfo, RTSConfig()).iloc[0].fa_dscr == pytest.approx(0.5625)
    assert annual_metrics(in_cff, RTSConfig(interest_addback="always")).iloc[0].fa_dscr == pytest.approx(0.9375)
    assert annual_metrics(in_cfo, RTSConfig(interest_addback="never")).iloc[0].fa_dscr == pytest.approx(0.1875)


def test_pnl_interest_fallback_location_inference():
    """P&L interest 30 used (no cash-flow interest line). 'Other financing items' -28 >= 0.8 x 30 -> taken as
    paid in financing (no add-back); 'Other financing items' -5 -> assumed inside CFO (add back 30)."""
    base = {"symbol": "F", "period_end": "2026-03-31", "cfo": 45, "interest_paid": 30, "principal_repaid": 50,
            "interest_paid_flag": "fallback_pnl_interest"}
    a = annual_metrics(panel([{**base, "other_financing_items": -28}]), RTSConfig()).iloc[0]
    b = annual_metrics(panel([{**base, "other_financing_items": -5}]), RTSConfig()).iloc[0]
    assert a.interest_addback == 0 and "financing" in a.interest_location
    assert b.interest_addback == 30 and b.fa_dscr == pytest.approx(75 / 80)


def test_lease_payments_in_debt_service():
    """Airline-style (assumed): CFO 1,000, interest 200, loan repayment 100, lease principal 500.
    With leases: 1000/800 = 1.25 (Hedge); without: 1000/300 = 3.33 - leases would flatter the borrower."""
    p = panel([{"symbol": "AIR", "period_end": "2026-03-31", "cfo": 1000, "interest_paid": 200, "principal_repaid": 100,
                "financial_liabilities_paid": 500}])
    assert annual_metrics(p, RTSConfig()).iloc[0].fa_dscr == pytest.approx(1.25)
    assert annual_metrics(p, RTSConfig(include_lease_payments=False)).iloc[0].fa_dscr == pytest.approx(1000 / 300)


def test_no_debt_service_is_hedge():
    r = annual_metrics(panel([{"symbol": "CASH", "period_end": "2026-03-31", "cfo": 500, "interest_paid": 0.3,
                               "principal_repaid": 0}]), RTSConfig()).iloc[0]
    assert r.minsky_state == "Hedge" and r.no_debt_service and np.isnan(r.fa_dscr) and r.refi_dependence == 0


# ---------------------------------------------------------------- migration matrix
def test_migration_matrix():
    """Company A: H -> S -> P -> P ; Company B: S -> S -> H -> H.
    1-yr transitions: H>S 1, S>P 1, P>P 1, S>S 1, S>H 1, H>H 1.  3-yr (first -> last): A H>P, B S>H."""
    def yrs(sym, states):
        cfo = {"Hedge": 100, "Speculative": 50, "Ponzi": 10}
        return [{"symbol": sym, "period_end": f"{2023 + i}-03-31", "cfo": cfo[s], "interest_paid": 30, "principal_repaid": 50}
                for i, s in enumerate(states)]
    a = annual_metrics(panel(yrs("A", ["Hedge", "Speculative", "Ponzi", "Ponzi"]) +
                             yrs("B", ["Speculative", "Speculative", "Hedge", "Hedge"])), RTSConfig())
    m = migration_matrices(a, 3)
    one = m["one_year_counts"]
    assert one.loc["Hedge", "Speculative"] == 1 and one.loc["Speculative", "Ponzi"] == 1 and one.loc["Ponzi", "Ponzi"] == 1
    assert one.values.sum() == 6
    three = m["3_year_counts"]
    assert three.loc["Hedge", "Ponzi"] == 1 and three.loc["Speculative", "Hedge"] == 1
    last = a.groupby("symbol").tail(1).set_index("symbol")
    # A: Ponzi (0) vs mean(H,S,P)=1 -> -1 deteriorating ; B: Hedge (2) vs mean(S,S,H)=1.33 -> +0.67 improving
    assert last.loc["A", "migration"] == "deteriorating" and last.loc["B", "migration"] == "improving"


# ---------------------------------------------------------------- Breach Clock
def q(e, i):
    ends = pd.period_range("2023-09", periods=len(e), freq="Q-DEC").to_timestamp(how="end").strftime("%Y-%m-%d")
    return pd.DataFrame({"period_end": ends, "ebitda": e, "interest_expense": i})


def declining():
    """Seasonal EBITDA falling 20 per quarter year-on-year: 200,220,240,260 | 180,200,220,240 | 160,180,200,220 | 140."""
    return [200, 220, 240, 260, 180, 200, 220, 240, 160, 180, 200, 220, 140]


def test_breach_clock_deterministic_decline():
    """All YoY changes are -20 (EBITDA) and 0 (interest), so every path is identical.
    TTM EBITDA now 180+200+220+140 = 740 and falls 20 a quarter; interest TTM 200; debt 2,800.
    Debt/EBITDA: h1 2800/720 = 3.89, h2 2800/700 = 4.00 (not > 4), h3 2800/680 = 4.12 -> BREACH at h=3.
    ICR stays >= 3.4x. Baseline P(breach <= 4q) = 100%, median 3 quarters.
    Stress: drift removed (q14 = q10 = 180) and cut 25% -> 135; TTM h1 = 200+220+140+135 = 695 -> 4.03x -> h=1."""
    r = breach_clock("DEC", q(declining(), [50] * 13), 2800, "2026-09-30", RTSConfig(n_paths=200))
    assert r.status == "ok" and not r.breach_now
    assert r.ttm_ebitda == 740 and r.icr_now == pytest.approx(3.7)
    assert r.p_breach_base == 1.0 and r.median_q_base == 3
    assert r.p_breach_stress == 1.0 and r.median_q_stress == 1


def test_breach_clock_no_breach_and_seasonality():
    """Flat seasonal pattern (YoY change 0): TTM 400, interest 40 -> ICR 10x, debt 800 -> 2x. Never breaches."""
    e = [80, 90, 110, 120] * 3 + [80]
    r = breach_clock("FLAT", q(e, [10] * 13), 800, None, RTSConfig(n_paths=200))
    assert r.p_breach_base == 0.0 and r.median_q_base is None and r.p_breach_stress == 0.0


def test_breach_clock_already_in_breach_and_short_history():
    """ICR now = 4x10 / 4x6 = 1.67 < 2.0 -> already in breach, P = 100%, 0 quarters.
    Six quarters only -> 2 YoY pairs < 4 -> not simulated."""
    r = breach_clock("BAD", q([10] * 13, [6] * 13), 50, None, RTSConfig(n_paths=100))
    assert r.status == "already_in_breach" and r.breach_now and r.p_breach_base == 1.0 and r.median_q_base == 0
    assert "ICR 1.67x" in r.breach_now_reason
    s = breach_clock("NEW", q([100] * 6, [5] * 6), 100, None, RTSConfig(n_paths=100))
    assert s.status == "insufficient_quarters" and np.isnan(s.p_breach_base)


def test_breach_thresholds_configurable():
    """Same decline but covenant Debt/EBITDA 4.5x: 2800/TTM > 4.5 -> TTM < 622.2 -> 740-20h < 622.2 -> h = 6."""
    r = breach_clock("DEC", q(declining(), [50] * 13), 2800, None, RTSConfig(n_paths=100, debt_ebitda_max=4.5))
    assert r.p_breach_base == 0.0 and r.median_q_base == 6


# ---------------------------------------------------------------- score, classes, weights
def test_interp_dscr_points():
    pts = RTSConfig().dscr_points
    assert interp(1.0, pts) == 30 and interp(4 / 3, pts) == pytest.approx(60) and interp(0.5, pts) == 0 and interp(5, pts) == 100


def test_score_hand_worked_and_weights():
    """PAY case latest FY (2026): pooled 3-yr DSCR = (300+300+200)/(150x3) = 1.778 -> 70 + (0.278/0.5) x 15 = 78.33.
    Minsky: Hedge, prior states H,H,H -> stable -> 0.75x100 + 0.25x50 = 87.5.
    Refinancing: no new borrowing -> 100. Breach: P = 0 -> 100.
    RTS = 0.35x78.33 + 0.25x87.5 + 0.20x100 + 0.20x100 = 89.29 -> Safe, but payables stretch 100 = 33% of CFO
    -> Watch override.  Equal weights: (78.33+87.5+100+100)/4 = 91.46."""
    rows = [{"symbol": "PAY", "period_end": f"{y}-03-31", "cfo": 300, "operating_expenses": 1000, "trade_payables": 100,
             "interest_paid": 50, "principal_repaid": 100} for y in (2023, 2024, 2025)]
    rows.append({**rows[-1], "period_end": "2026-03-31", "trade_payables": 200})
    a = annual_metrics(panel(rows), RTSConfig())
    s = company_scores(a, no_breach(["PAY"]), RTSConfig()).iloc[0]
    assert s.fa_dscr_3y == pytest.approx(800 / 450)
    assert s.s_dscr == pytest.approx(78.333, abs=1e-3) and s.s_minsky == 87.5 and s.s_refi == 100 and s.s_breach == 100
    assert s.rts == pytest.approx(89.2917, abs=1e-3) and s.score_class == "Safe" and s.rts_class == "Watch"
    assert "payables stretched" in s.triggers
    eq = company_scores(a, no_breach(["PAY"]), RTSConfig(w_dscr=1, w_minsky=1, w_refi=1, w_breach=1)).iloc[0]
    assert eq.rts == pytest.approx((78.3333 + 87.5 + 100 + 100) / 4, abs=1e-3)


def test_ponzi_escalates_and_missing_component_reweights():
    """Apex-like Ponzi year with no Breach Clock: weights re-normalised over 3 components, class Escalate."""
    a = annual_metrics(panel([{"symbol": "P", "period_end": "2025-03-31", "cfo": 135, "interest_paid": 30, "principal_repaid": 50},
                              {"symbol": "P", "period_end": "2026-03-31", "cfo": 25, "interest_paid": 30, "principal_repaid": 50,
                               "borrowings_raised": 80}]), RTSConfig())
    br = no_breach(["P"]).assign(p_breach_base=np.nan, p_breach_stress=np.nan, status="insufficient_quarters")
    s = company_scores(a, br, RTSConfig()).iloc[0]
    assert s.minsky_state == "Ponzi" and s.rts_class == "Escalate" and s.missing_components == "breach"
    # pooled DSCR (135+25)/160 = 1.0 -> 30; Minsky 0.75x0 + 0.25x0 = 0; refi 80/160 = 50% -> 50
    assert s.rts == pytest.approx((0.35 * 30 + 0.25 * 0 + 0.20 * 50) / 0.80)


# ---------------------------------------------------------------- end to end from the data layer
def test_end_to_end_from_data_layer(tmp_path):
    from dstm_data.config import Settings
    from dstm_data.pipeline import Pipeline
    from tests.fixtures import FakeTransport, company_responses, make_page, schedules
    resp = company_responses("TSTL", "3373", make_page(), make_page(consolidated=False), schedules(), schedules())
    p = Pipeline(Settings(data_dir=tmp_path, min_interval_s=0), transport=FakeTransport(resp))
    p.refresh(pd.DataFrame({"symbol": ["TSTL"], "company_name": "x", "industry": "y"}), force=True, progress=lambda *_: None)
    cl = p.cache.table("credit_lines")
    assert cl.source_url.notna().all()
    res = run_rts(cl, RTSConfig(n_paths=500))
    fy26 = res.annual[res.annual.period_end == "2026-03-31"].iloc[0]
    # fixture FY26: CFO 210, interest paid 118 (financing), repayment 120 + lease 7 -> service 245.
    # exceptional 0; other income normal 12, interest/dividends received not in fixture -> non-core 12.
    # payables 155 vs opex 960 -> 58.9 days; norm mean(150/800, 160/880 x365) = 67.4 -> no stretch.
    assert fy26.cfo_adj == pytest.approx(210 - 12) and fy26.debt_service == pytest.approx(245)
    assert fy26.fa_dscr == pytest.approx(198 / 245) and fy26.minsky_state == "Speculative"
    s = res.scores.iloc[0]
    assert s.symbol == "TSTL" and s.rts_class in {"Safe", "Watch", "Escalate"} and 0 <= s.rts <= 100
    # fixture quarters: TTM EBITDA 60+62+64+66 = 252, debt (Sep 2026 interim) 1,150 -> 4.56x > 4x:
    # already outside the covenant, which needs no simulation (only 4 quarters exist)
    b = res.breach.iloc[0]
    assert b.status == "already_in_breach" and b.debt_date == "2026-09-30" and b.debt_ebitda_now == pytest.approx(1150 / 252)
    assert s.rts_class == "Escalate"


def test_workbook_traceability(tmp_path):
    """Every Annual input is a link to one Sources row carrying source line, URL and fetch time."""
    import sys
    from pathlib import Path
    from openpyxl import load_workbook
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from make_demo_credit_lines import demo_credit_lines
    from dstm_rts.workbook import build_workbook
    cl = demo_credit_lines()
    res = run_rts(cl, RTSConfig(n_paths=200))
    p = build_workbook(res, cl, str(tmp_path / "rts.xlsx"), "test")
    wb = load_workbook(p)
    assert wb.sheetnames[:2] == ["README", "Settings"]
    assert {"Sources", "Annual", "Quarters", "BreachClock", "Company", "Migration", "Checks"} <= set(wb.sheetnames)
    src = wb["Sources"]
    hdr = [c.value for c in src[1]]
    assert {"Source line", "Source URL", "Fetched at (UTC)", "Flag"} <= set(hdr)
    ann = wb["Annual"]
    h = [c.value for c in ann[1]]
    cfo = ann.cell(2, h.index("cfo") + 1).value
    assert cfo.startswith("=Sources!$G$")
    row = int(cfo.split("$")[-1])
    assert src.cell(row, hdr.index("Field") + 1).value == "cfo"
    assert ann.cell(2, h.index("FA-DSCR = CFADS / debt service") + 1).value.startswith("=IF(")
    assert "ICR_MIN" in wb.defined_names and "W_DSCR" in wb.defined_names
