"""Case studies: stressed names outside the Nifty 200 vs clean peers, scored point-in-time each 30 June.

Event dates use the FIRST public sign of distress (so the test of "did RTS flag it before?" is strict).
Sources: Business Standard, BloombergQuint, AP/Reuters, NCLT orders; Coffee Day and ZEEL also Sessions 7-8.
"""
from __future__ import annotations

import pandas as pd

CASES = [
    {"stressed": "COFFEEDAY", "peer": "JUBLFOOD", "event_date": "2019-01-31",
     "event": "Defaults to lenders from early 2019; founder's death Jul 2019 (Business Standard); "
              "SEBI later found ~Rs 3,535 Cr moved to promoter entity MACEL (Sessions 7-8)"},
    {"stressed": "ZEEL", "peer": "SUNTV", "event_date": "2019-01-25",
     "event": "Share price fell ~30% in a day on 25 Jan 2019 on promoter-pledge fears (Business Standard, BloombergQuint)"},
    {"stressed": "RCOM", "peer": "BHARTIARTL", "event_date": "2017-09-30",
     "event": "Ericsson's insolvency petition for unpaid dues (Sep 2017); NCLT admission May 2018; CIRP from Jun 2019"},
    {"stressed": "JETAIRWAYS", "peer": "INDIGO", "event_date": "2018-12-31",
     "event": "First debt default (31 Dec 2018); operations suspended 17 Apr 2019 (AP, Reuters)"},
]

COLS = ["cohort", "asof", "latest_fy", "rts", "rts_class", "minsky_state", "migration", "fa_dscr_3y",
        "fa_dscr_latest", "refi_dependence_3y", "naive_dscr_3y", "icr_asof_bench", "debt_ebitda_asof",
        "loss", "icr_fall", "max_drawdown_24m", "triggers"]


def case_table(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in CASES:
        for role in ("stressed", "peer"):
            sym = c[role]
            g = panel[panel.symbol == sym].sort_values("cohort")
            if g.empty:
                rows.append({"case": c["stressed"], "role": role, "symbol": sym, "note": "not scored (no data)"})
                continue
            for r in g.itertuples(index=False):
                d = {k: getattr(r, k, None) for k in COLS}
                d.update({"case": c["stressed"], "role": role, "symbol": sym,
                          "pre_event": r.asof < c["event_date"]})
                rows.append(d)
    return pd.DataFrame(rows)


def lead_times(panel: pd.DataFrame) -> pd.DataFrame:
    """Did RTS flag the stressed name before the event, and did it leave the peer alone?"""
    out = []
    for c in CASES:
        s = panel[(panel.symbol == c["stressed"]) & (panel["asof"] < c["event_date"])].sort_values("cohort")
        p = panel[(panel.symbol == c["peer"]) & (panel["asof"] < c["event_date"])].sort_values("cohort")
        flagged = s[s.rts_class.isin(["Watch", "Escalate"])]
        esc = s[s.rts_class == "Escalate"]
        out.append({
            "case": c["stressed"], "peer": c["peer"], "event": c["event"], "event_date": c["event_date"],
            "pre_event_cohorts_scored": len(s),
            "first_watch_or_escalate_asof": flagged["asof"].iloc[0] if len(flagged) else None,
            "first_escalate_asof": esc["asof"].iloc[0] if len(esc) else None,
            "last_pre_event_class": s.rts_class.iloc[-1] if len(s) else None,
            "last_pre_event_rts": s.rts.iloc[-1] if len(s) else None,
            "last_pre_event_state": s.minsky_state.iloc[-1] if len(s) else None,
            "peer_last_pre_event_class": p.rts_class.iloc[-1] if len(p) else None,
            "peer_last_pre_event_rts": p.rts.iloc[-1] if len(p) else None,
            "peer_ever_flagged_pre_event": bool(p.rts_class.isin(["Watch", "Escalate"]).any()) if len(p) else None,
        })
    return pd.DataFrame(out)
