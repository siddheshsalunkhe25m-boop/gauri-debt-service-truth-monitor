"""Plotly figures. Palette = dataviz reference instance (validated light + dark steps); status colours are
always paired with a text label; one y-axis per chart; hover on every mark."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

LIGHT = {"surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781", "grid": "#e1e0d9",
         "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a", "neutral": "#f0efec"}
DARK = {"surface": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#898781", "grid": "#2c2c2a",
        "s1": "#3987e5", "s2": "#d95926", "s3": "#199e70", "neutral": "#383835"}
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
CLASS_STATUS = {"Safe": "good", "Watch": "warning", "Escalate": "critical"}
STATE_STATUS = {"Hedge": "good", "Speculative": "warning", "Ponzi": "critical"}
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def pal(dark: bool) -> dict:
    return DARK if dark else LIGHT


def _layout(fig, P, title=None, height=320, yfmt=None, ytitle=None):
    fig.update_layout(
        template="none", height=height, margin=dict(l=56, r=24, t=48 if title else 16, b=40),
        paper_bgcolor=P["surface"], plot_bgcolor=P["surface"],
        font=dict(family="Arial, sans-serif", size=12, color=P["ink2"]),
        title=dict(text=title, x=0, xanchor="left", font=dict(size=14, color=P["ink"])) if title else None,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=1, xanchor="right", font=dict(color=P["ink2"]),
                    bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=P["surface"], font=dict(color=P["ink"]), bordercolor=P["grid"]),
    )
    fig.update_xaxes(showgrid=False, linecolor=P["grid"], tickcolor=P["grid"], zeroline=False)
    fig.update_yaxes(gridcolor=P["grid"], gridwidth=1, zeroline=False, linecolor=P["grid"],
                     tickformat=yfmt, title=dict(text=ytitle, font=dict(color=P["ink2"], size=11)))
    return fig


# ------------------------------------------------------------------ portfolio
def transition_heatmap(m_counts: pd.DataFrame, P, title):
    order = ["Hedge", "Speculative", "Ponzi"]
    m = m_counts.reindex(index=order, columns=order, fill_value=0)
    pct = m.div(m.sum(axis=1).replace(0, np.nan), axis=0)
    text = [[f"{int(m.iloc[i, j])}<br>{pct.iloc[i, j]:.0%}" if pd.notna(pct.iloc[i, j]) else "0"
             for j in range(3)] for i in range(3)]
    z = pct.fillna(0).to_numpy()
    fig = go.Figure(go.Heatmap(
        z=z, x=[f"to {c}" for c in order], y=[f"from {r}" for r in order], text=text, colorscale=[[k / (len(SEQ_BLUE) - 1), c] for k, c in enumerate(SEQ_BLUE)],
        zmin=0, zmax=1, xgap=2, ygap=2, showscale=True,
        colorbar=dict(title=dict(text="row %", side="right"), tickformat=".0%", thickness=10, len=0.8),
        hovertemplate="%{y} → %{x}<br>%{text}<extra></extra>"))
    # cell labels: dark text on light cells, light text on dark cells
    for i in range(3):
        for j in range(3):
            fig.add_annotation(x=f"to {order[j]}", y=f"from {order[i]}", text=text[i][j], showarrow=False,
                               font=dict(size=13, color="#0b0b0b" if z[i][j] < 0.55 else "#ffffff"))
    _layout(fig, P, title, height=300)
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    return fig


def state_grid(annual: pd.DataFrame, symbols: list, P, max_rows=40):
    """Company x fiscal year Minsky states (status colours + H/S/P letters)."""
    a = annual[annual.symbol.isin(symbols) & annual.minsky_state.notna()].copy()
    if a.empty:
        return None
    a["fy"] = a.period_end.str[:4]
    piv = a.pivot_table(index="symbol", columns="fy", values="state_ord", aggfunc="first")
    piv = piv.loc[[s for s in symbols if s in piv.index]][:max_rows]
    lab = piv.map(lambda v: "" if pd.isna(v) else {2: "H", 1: "S", 0: "P"}[int(v)])
    names = piv.map(lambda v: "" if pd.isna(v) else {2: "Hedge", 1: "Speculative", 0: "Ponzi"}[int(v)])
    cs = [[0, STATUS["critical"]], [0.33, STATUS["critical"]], [0.34, STATUS["warning"]], [0.66, STATUS["warning"]],
          [0.67, STATUS["good"]], [1, STATUS["good"]]]
    fig = go.Figure(go.Heatmap(z=piv.to_numpy(), x=list(piv.columns), y=list(piv.index), zmin=0, zmax=2,
                               colorscale=cs, showscale=False, xgap=2, ygap=2, text=lab.to_numpy(),
                               customdata=names.to_numpy(), texttemplate="%{text}", textfont=dict(color="#0b0b0b", size=10),
                               hovertemplate="%{y} FY%{x}: %{customdata}<extra></extra>"))
    _layout(fig, P, None, height=max(220, 22 * len(piv) + 60))
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)", tickfont=dict(size=10))
    fig.update_xaxes(side="top")
    return fig


# ------------------------------------------------------------------ company
def dscr_history(a: pd.DataFrame, P):
    a = a[a.fa_dscr.notna() | a.reported_dscr.notna()].sort_values("period_end")
    if a.empty:
        return None
    x = a.period_end.str[:4]
    fig = go.Figure()
    fig.add_hline(y=1.0, line=dict(color=P["muted"], width=1, dash="dash"),
                  annotation_text="1.0x: cash just covers debt service", annotation_position="bottom right",
                  annotation_font=dict(size=10, color=P["ink2"]))
    for col, name, color in (("reported_dscr", "Reported DSCR (CFO, no adjustments)", P["s2"]),
                             ("fa_dscr", "Forensic-adjusted DSCR", P["s1"])):
        fig.add_trace(go.Scatter(x=x, y=a[col], name=name, mode="lines+markers", line=dict(color=color, width=2),
                                 marker=dict(size=8, line=dict(color=P["surface"], width=2)),
                                 hovertemplate="FY%{x}: %{y:.2f}x<extra>" + name + "</extra>"))
        last = a[col].dropna()
        if len(last):
            fig.add_annotation(x=x.loc[last.index[-1]], y=last.iloc[-1], text=f"{last.iloc[-1]:.2f}x", showarrow=False,
                               xanchor="left", xshift=8, font=dict(size=11, color=P["ink"]))
    _layout(fig, P, "Forensic-adjusted vs reported DSCR by fiscal year", height=330, yfmt=".1f", ytitle="times (x)")
    return fig


def cfo_bridge(r: dict, P):
    steps = [("Reported CFO", r.get("cfo"), "absolute"),
             ("Payables stretch", -(r.get("payables_stretch") or 0), "relative"),
             ("Exceptional gains", -(r.get("exceptional_gain_deducted") or 0), "relative"),
             ("Non-core income", -(r.get("noncore_income_deducted") or 0), "relative"),
             ("Interest add-back", r.get("interest_addback") or 0, "relative"),
             ("CFADS", None, "total")]
    if steps[0][1] is None or pd.isna(steps[0][1]):
        return None
    total = sum(v for _, v, m in steps[:-1] if v is not None)
    labels = [f"{v:,.0f}" if m == "absolute" else ("–" if not v else f"{v:+,.0f}") for _, v, m in steps[:-1]] + [f"{total:,.0f}"]
    fig = go.Figure(go.Waterfall(
        x=[s[0] for s in steps], y=[s[1] if s[1] is not None else 0 for s in steps], measure=[s[2] for s in steps],
        connector=dict(line=dict(color=P["grid"], width=1)), increasing=dict(marker=dict(color=P["s3"])),
        decreasing=dict(marker=dict(color=P["s2"])), totals=dict(marker=dict(color=P["s1"])),
        text=labels, textposition="outside", hovertemplate="%{x}: Rs %{y:,.0f} Cr<extra></extra>"))
    ds = r.get("debt_service")
    if ds is not None and not pd.isna(ds) and ds > 0:
        fig.add_hline(y=ds, line=dict(color=P["ink2"], width=1, dash="dot"),
                      annotation_text=f"debt service Rs {ds:,.0f} Cr", annotation_position="top right",
                      annotation_font=dict(size=10, color=P["ink2"]))
    _layout(fig, P, f"From reported CFO to cash available for debt service (FY{str(r.get('period_end'))[:4]})",
            height=340, ytitle="Rs Cr", yfmt=",")
    return fig


def minsky_history(a: pd.DataFrame, P):
    a = a[a.minsky_state.notna()].sort_values("period_end")
    if a.empty:
        return None
    x = a.period_end.str[:4]
    fig = go.Figure()
    for col, name, color, dash in (("debt_service", "Interest + repayments (Hedge line)", P["ink2"], "dot"),
                                   ("interest_paid", "Interest paid (Ponzi line)", P["s2"], "dash"),
                                   ("cfads", "Cash available for debt service", P["s1"], "solid")):
        fig.add_trace(go.Scatter(x=x, y=a[col], name=name, mode="lines+markers",
                                 line=dict(color=color, width=2, dash=dash), marker=dict(size=8),
                                 hovertemplate="FY%{x}: Rs %{y:,.0f} Cr<extra>" + name + "</extra>"))
    top = np.nanmax(a[["debt_service", "cfads", "interest_paid"]].to_numpy(dtype=float))
    for xi, st in zip(x, a.minsky_state):
        fig.add_annotation(x=xi, y=1.0, yref="paper", yanchor="bottom", text=f"<b>{st[0]}</b>", showarrow=False,
                           bgcolor=STATUS[STATE_STATUS[st]], font=dict(color="#0b0b0b", size=11), borderpad=3,
                           hovertext=st)
    _layout(fig, P, None, height=360, ytitle="Rs Cr", yfmt=",")
    fig.update_yaxes(rangemode="tozero")
    fig.update_layout(margin=dict(t=70), legend=dict(y=1.12))
    return fig


def fan_chart(f: dict, metric: str, scenario: str, cov: float, P, higher_is_better: bool):
    q = f[f"{scenario}_{metric}_q"]
    hist = f["hist_icr" if metric == "icr" else "hist_de"]
    cap = 25.0 if metric == "icr" else 15.0
    clip = lambda v: np.clip(np.where(np.isfinite(v), v, cap), -cap, cap)
    hx, fx = f["hist_end"], f["fut_end"]
    fig = go.Figure()
    bandcol = P["s1"] if scenario == "base" else P["s2"]
    rgba = lambda h, a: f"rgba({int(h[1:3], 16)},{int(h[3:5], 16)},{int(h[5:7], 16)},{a})"
    x0 = [hx[-1]] + fx
    last = clip(np.array([hist[-1]]))[0]
    for lo, hi, a, name in ((0, 4, 0.15, "5th-95th percentile"), (1, 3, 0.30, "25th-75th percentile")):
        fig.add_trace(go.Scatter(x=x0 + x0[::-1], y=list(np.r_[last, clip(q[hi])]) + list(np.r_[last, clip(q[lo])])[::-1],
                                 fill="toself", fillcolor=rgba(bandcol, a), line=dict(width=0), name=name,
                                 hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x0, y=np.r_[last, clip(q[2])], name="Median projection", mode="lines",
                             line=dict(color=bandcol, width=2, dash="dash"),
                             hovertemplate="%{x}: median %{y:.2f}x<extra></extra>"))
    fig.add_trace(go.Scatter(x=hx, y=clip(np.array(hist)), name="Actual (TTM)", mode="lines+markers",
                             line=dict(color=P["ink"], width=2), marker=dict(size=8),
                             hovertemplate="%{x}: %{y:.2f}x<extra>actual TTM</extra>"))
    fig.add_hline(y=cov, line=dict(color=STATUS["critical"], width=1.5),
                  annotation_text=f"covenant {'≥' if higher_is_better else '≤'} {cov:.1f}x",
                  annotation_position="top left", annotation_font=dict(size=10, color=P["ink2"]))
    title = ("Interest cover (TTM EBITDA / interest)" if metric == "icr" else "Debt / TTM EBITDA") + \
        (" - baseline" if scenario == "base" else " - stress")
    _layout(fig, P, title, height=380, yfmt=".1f", ytitle="times (x)")
    fig.update_yaxes(rangemode="tozero")
    fig.update_layout(legend=dict(orientation="h", y=-0.18, x=0, xanchor="left", yanchor="top"), margin=dict(b=90))
    return fig


def breach_curve(f: dict, P, window: int):
    x = list(range(1, len(f["base_p_breach_by_q"]) + 1))
    fig = go.Figure()
    for k, name, color, dash in (("base", "Baseline", P["s1"], "solid"), ("stress", "Stress", P["s2"], "dash")):
        fig.add_trace(go.Scatter(x=x, y=f[f"{k}_p_breach_by_q"], name=name, mode="lines+markers",
                                 line=dict(color=color, width=2, dash=dash), marker=dict(size=8),
                                 hovertemplate="by quarter %{x}: %{y:.0%}<extra>" + name + "</extra>"))
    fig.add_vline(x=window, line=dict(color=P["muted"], width=1, dash="dot"),
                  annotation_text=f"{window}-quarter window", annotation_font=dict(size=10, color=P["ink2"]))
    _layout(fig, P, "Probability of a first covenant breach by quarter", height=300, yfmt=".0%",
            ytitle="cumulative probability")
    fig.update_xaxes(title=dict(text="quarters ahead", font=dict(size=11)), dtick=1)
    fig.update_yaxes(range=[0, 1.02])
    return fig


def percentile_dots(b: pd.DataFrame, P):
    b = b[b.sector_pct.notna() | b.universe_pct.notna()].iloc[::-1]
    if b.empty:
        return None
    fig = go.Figure()
    for col, name, color, sym in (("universe_pct", "vs universe", P["s2"], "diamond"), ("sector_pct", "vs sector", P["s1"], "circle")):
        fig.add_trace(go.Scatter(x=b[col], y=b.label, mode="markers", name=name,
                                 marker=dict(size=11, color=color, symbol=sym, line=dict(color=P["surface"], width=2)),
                                 hovertemplate="%{y}: %{x:.0f}th percentile<extra>" + name + "</extra>"))
    fig.add_vline(x=50, line=dict(color=P["muted"], width=1, dash="dash"), annotation_text="median",
                  annotation_font=dict(size=10, color=P["ink2"]))
    _layout(fig, P, "Percentile rank (100 = best in group, whatever the direction)", height=60 + 34 * len(b))
    fig.update_xaxes(range=[-3, 103], showgrid=True, gridcolor=P["grid"], title=dict(text="percentile", font=dict(size=11)))
    return fig


def subscores(row: dict, weights: dict, P):
    items = [("FA-DSCR", "s_dscr", "dscr"), ("Minsky state / migration", "s_minsky", "minsky"),
             ("Refinancing dependence", "s_refi", "refi"), ("Breach Clock", "s_breach", "breach")]
    names = [f"{n} (w {weights[k]:.0%})" for n, _, k in items]
    vals = [row.get(c) for _, c, _ in items]
    fig = go.Figure(go.Bar(x=[0 if v is None or pd.isna(v) else v for v in vals], y=names, orientation="h",
                           marker=dict(color=P["s1"], line=dict(color=P["surface"], width=2)),
                           text=["not scored" if v is None or pd.isna(v) else f"{v:.0f}" for v in vals],
                           textposition="outside", hovertemplate="%{y}: %{x:.0f} / 100<extra></extra>"))
    _layout(fig, P, None, height=190)
    fig.update_xaxes(range=[0, 115], showgrid=True, gridcolor=P["grid"])
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=30))
    return fig
