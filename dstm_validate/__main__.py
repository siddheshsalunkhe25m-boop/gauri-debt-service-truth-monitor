"""python -m dstm_validate [--db data/dstm.db] [--out data/validation] [--synthetic] [--paths 2000]

Runs: point-in-time back-test (cohorts 2017-2024 scored each 30 June; outcomes over the next 2 years),
leakage test, Breach Clock single-cohort test, case studies, sensitivity; writes CSVs, PNG charts and
validation_tables.md (tables only - the narrative is written from them).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

from dstm_rts.config import RTSConfig

from . import charts
from .backtest import (OUTCOMES, auc_table, breach_clock_test, calibration, cohort_auc, leakage_check,
                       quintile_table, rate_table, run_backtest)
from .cases import CASES, case_table, lead_times
from .sensitivity import JUDGEMENT_SCENARIOS, WEIGHT_SCENARIOS, covenant_table, scenario_table

STAT_YEARS = list(range(2017, 2025))      # outcomes fully observable (2 fiscal years + 24 months of prices)
CASE_YEARS = list(range(2016, 2027))


def md(df: pd.DataFrame, floatfmt=3) -> str:
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else f"{v:.{floatfmt}f}")
    return d.to_markdown(index=False)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dstm_validate")
    ap.add_argument("--db", default="data/dstm.db")
    ap.add_argument("--universe", default="ind_nifty200list.csv")
    ap.add_argument("--out", default="data/validation")
    ap.add_argument("--synthetic", action="store_true", help="planted synthetic history (machinery check only)")
    ap.add_argument("--paths", type=int, default=2000, help="Monte Carlo paths for sensitivity runs")
    ap.add_argument("--boot", type=int, default=1000)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    if a.synthetic:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        from make_synthetic_history import synthetic_history
        cl, px = synthetic_history()
        universe = set(cl.symbol)
    else:
        with sqlite3.connect(a.db) as con:
            cl = pd.read_sql_query("SELECT * FROM credit_lines", con)
            px = pd.read_sql_query("SELECT symbol, date, close FROM prices", con)
        u = pd.read_csv(a.universe)
        universe = set(u.loc[u["Industry"] != "Financial Services", "Symbol"])
    cfg = RTSConfig()
    cfg_fast = replace(cfg, n_paths=a.paths)
    tables = []

    # ---------------------------------------------------------------- back-test
    panel_all = run_backtest(cl, px, CASE_YEARS, cfg)
    panel_all["in_universe"] = panel_all.symbol.isin(universe)
    panel_all.to_csv(out / "backtest_panel_all.csv", index=False)
    panel = panel_all[panel_all.in_universe & panel_all.cohort.isin(STAT_YEARS)]
    panel.to_csv(out / "backtest_panel.csv", index=False)
    cov = panel.groupby("cohort").agg(n=("symbol", "size"), any_new=("any_new_event", "mean"),
                                      icr_fall=("icr_fall", "mean"), new_loss=("new_loss", "mean"),
                                      drawdown50=("drawdown50", "mean")).reset_index()
    tables.append(("Cohort coverage and event rates (universe, cohorts 2017-2024)", md(cov)))

    aucs = pd.concat([auc_table(panel, o, n_boot=a.boot) for o in OUTCOMES], ignore_index=True)
    aucs.to_csv(out / "auc_table.csv", index=False)
    tables.append(("AUC by outcome and risk score (company-cluster bootstrap 95% CI)", md(aucs)))
    rates = pd.concat([rate_table(panel, "rts_class", o) for o in OUTCOMES], ignore_index=True)
    rates.to_csv(out / "rates_by_class.csv", index=False)
    tables.append(("Event rates by RTS class", md(rates)))
    st = pd.concat([rate_table(panel, "minsky_state", o) for o in OUTCOMES], ignore_index=True)
    st.to_csv(out / "rates_by_minsky_state.csv", index=False)
    tables.append(("Event rates by Minsky state", md(st)))
    mig = pd.concat([rate_table(panel, "migrated_down", o) for o in OUTCOMES], ignore_index=True)
    mig.to_csv(out / "rates_by_migration_down.csv", index=False)
    tables.append(("Event rates: migrated down into Speculative/Ponzi (1) vs not (0)", md(mig)))
    ca = pd.concat([cohort_auc(panel, o) for o in ["any_new_event", "icr_fall", "new_loss", "drawdown50"]], ignore_index=True)
    ca.to_csv(out / "auc_by_cohort.csv", index=False)
    tables.append(("AUC by cohort", md(ca)))
    qt = pd.concat([quintile_table(panel, o) for o in ["any_new_event", "icr_fall", "new_loss", "drawdown50"]], ignore_index=True)
    qt.to_csv(out / "rates_by_quintile.csv", index=False)
    tables.append(("Event rate by RTS quintile within cohort (1 = lowest RTS)", md(qt)))

    # survivorship check: universe + stressed case names
    aug = panel_all[panel_all.cohort.isin(STAT_YEARS)]
    aug_auc = auc_table(aug, "any_new_event", n_boot=200)
    tables.append(("Augmented sample (universe + case companies), any_new_event", md(aug_auc)))

    # ---------------------------------------------------------------- leakage
    leak = pd.DataFrame([leakage_check(cl, y, cfg_fast) for y in STAT_YEARS])
    leak.to_csv(out / "leakage_check.csv", index=False)
    tables.append(("Leakage test (future values scrambled; scores must not move)", md(leak)))

    # ---------------------------------------------------------------- Breach Clock single cohort
    bt = breach_clock_test(cl[cl.symbol.isin(universe)], cfg)
    bt.to_csv(out / "breach_clock_test.csv", index=False)
    cal = calibration(bt)
    tables.append(("Breach Clock out-of-sample (as of 15 Nov 2025 -> next 4 quarters)",
                   md(pd.DataFrame([cal]))))

    # ---------------------------------------------------------------- cases
    ct = case_table(panel_all)
    ct.to_csv(out / "case_studies.csv", index=False)
    lt = lead_times(panel_all)
    lt.to_csv(out / "case_lead_times.csv", index=False)
    tables.append(("Case studies: did RTS flag before the event?", md(lt)))
    keep = ["case", "role", "symbol", "cohort", "latest_fy", "rts", "rts_class", "minsky_state", "migration",
            "fa_dscr_3y", "naive_dscr_3y", "refi_dependence_3y", "loss", "max_drawdown_24m"]
    tables.append(("Case study paths", md(ct[[c for c in keep if c in ct]])))

    # ---------------------------------------------------------------- sensitivity
    today_syms = sorted(universe & set(cl.symbol))
    ws = scenario_table(cl[cl.symbol.isin(universe)], px, STAT_YEARS, cfg_fast, WEIGHT_SCENARIOS, today_syms)
    ws.to_csv(out / "sensitivity_weights.csv", index=False)
    tables.append(("Sensitivity: weights", md(ws)))
    js = scenario_table(cl[cl.symbol.isin(universe)], px, STAT_YEARS, cfg_fast,
                        {"base": {}, **JUDGEMENT_SCENARIOS}, today_syms)
    js.to_csv(out / "sensitivity_judgement.csv", index=False)
    tables.append(("Sensitivity: judgement calls / proxies", md(js)))
    cv = covenant_table(cl[cl.symbol.isin(universe)], cfg_fast, today_syms)
    cv.to_csv(out / "sensitivity_covenants.csv", index=False)
    tables.append(("Sensitivity: covenant thresholds (today + Breach Clock test)", md(cv)))

    # ---------------------------------------------------------------- charts
    head = aucs[aucs.outcome == "any_new_event"]
    charts.auc_dots(head, str(out / "chart_auc_any_new_event.png"), "a new credit event within 2 years")
    r0 = rates[rates.outcome == "any_new_event"]
    if len(r0):
        charts.class_event_rates(r0, str(out / "chart_rates_by_class.png"), "New credit event")
    charts.case_paths(ct, CASES, str(out / "chart_case_paths.png"))
    charts.scenario_dots(ws, "backtest_auc_any_new_event", str(out / "chart_sensitivity_weights.png"),
                         "Back-test AUC under different weights (any new event)")

    (out / "validation_tables.md").write_text("\n\n".join(f"## {t}\n\n{body}" for t, body in tables))
    (out / "run_config.json").write_text(json.dumps({"cfg": json.loads(cfg.to_json()), "stat_years": STAT_YEARS,
                                                     "case_years": CASE_YEARS, "synthetic": a.synthetic}, indent=1))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
