"""Static report charts (PNG). Palette: dataviz reference instance (light surface); status colours for classes
always paired with the class name, categorical slots 1-2 for stressed vs peer."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"
STATUS = {"Safe": "#0ca30c", "Watch": "#fab219", "Escalate": "#d03b3b"}


def _style(ax, title, sub=None):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.set_title(title, loc="left", fontsize=10, color=INK, fontweight="bold")
    if sub:
        ax.text(0, 1.01, sub, transform=ax.transAxes, fontsize=7.5, color=INK2, va="bottom")


def class_event_rates(rates: pd.DataFrame, path: str, outcome_label: str):
    fig, ax = plt.subplots(figsize=(6.2, 3.2), facecolor=SURFACE)
    order = [c for c in ["Safe", "Watch", "Escalate"] if c in set(rates.rts_class)]
    r = rates.set_index("rts_class").loc[order]
    x = np.arange(len(order))
    ax.bar(x, r["rate"] * 100, width=0.55, color=[STATUS[c] for c in order], edgecolor=SURFACE, linewidth=2)
    for i, c in enumerate(order):
        ax.text(i, r.loc[c, "rate"] * 100 + 1, f"{r.loc[c, 'rate']:.0%}\n{int(r.loc[c, 'events'])} of {int(r.loc[c, 'n'])}",
                ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_xticks(x, order)
    ax.set_ylabel("Event rate within 2 years (%)", fontsize=8, color=INK2)
    ax.set_ylim(0, max(100, (r["rate"].max() * 100) + 20) if r["rate"].max() > 0.8 else r["rate"].max() * 130 + 5)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    _style(ax, f"{outcome_label} by RTS class at the as-of date", "Pooled company-years, point-in-time cohorts")
    fig.tight_layout()
    fig.savefig(path, dpi=180, facecolor=SURFACE)
    plt.close(fig)


def auc_dots(tbl: pd.DataFrame, path: str, outcome_label: str):
    t = tbl.iloc[::-1]
    fig, ax = plt.subplots(figsize=(6.2, 0.45 * len(t) + 1.2), facecolor=SURFACE)
    y = np.arange(len(t))
    ax.hlines(y, t["auc_lo95"], t["auc_hi95"], color=BLUE, linewidth=2)
    ax.scatter(t["auc"], y, s=40, color=BLUE, zorder=3, edgecolor=SURFACE, linewidth=1.5)
    for yi, v in zip(y, t["auc"]):
        ax.text(v, yi + 0.18, f"{v:.2f}", ha="center", fontsize=7.5, color=INK)
    ax.axvline(0.5, color=INK2, linestyle="--", linewidth=0.8)
    ax.text(0.5, len(t) - 0.4, "coin flip", fontsize=7, color=INK2, ha="center")
    ax.set_yticks(y, t["risk_score"])
    ax.set_xlim(0.3, 1.0)
    ax.set_xlabel("AUC (company-cluster bootstrap 95% interval)", fontsize=8, color=INK2)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    _style(ax, f"Ranking power for: {outcome_label}")
    fig.tight_layout()
    fig.savefig(path, dpi=180, facecolor=SURFACE)
    plt.close(fig)


def case_paths(cases: pd.DataFrame, case_defs: list, path: str, safe_min=70, watch_min=45):
    if "rts" not in cases.columns:
        return
    n = len(case_defs)
    fig, axes = plt.subplots(1, n, figsize=(3.0 * n, 3.0), facecolor=SURFACE, sharey=True)
    axes = np.atleast_1d(axes)
    for ax, c in zip(axes, case_defs):
        for role, col in (("stressed", BLUE), ("peer", ORANGE)):
            g = cases[(cases.case == c["stressed"]) & (cases.role == role) & cases.rts.notna()].sort_values("cohort")
            if len(g):
                ax.plot(g.cohort, g.rts, color=col, linewidth=2, marker="o", markersize=4,
                        markeredgecolor=SURFACE, label=c[role])
                ax.text(g.cohort.iloc[-1] + 0.15, g.rts.iloc[-1], c[role], fontsize=7, color=INK, va="center")
        ev = int(c["event_date"][:4]) + (int(c["event_date"][5:7]) - 0.5) / 12
        ax.axvline(ev, color=INK2, linewidth=0.8)
        ax.text(ev, 101, "event", fontsize=7, color=INK2, ha="center")
        for v in (safe_min, watch_min):
            ax.axhline(v, color=GRID, linestyle="--", linewidth=0.8)
        ax.set_ylim(0, 105)
        ax.set_xlim(2015.5, 2027.3)
        ax.legend(fontsize=7, frameon=False, loc="lower left")
        _style(ax, f"{c['stressed']} vs {c['peer']}")
    axes[0].set_ylabel("RTS as of 30 June (dashed: Safe 70 / Watch 45)", fontsize=7.5, color=INK2)
    fig.tight_layout()
    fig.savefig(path, dpi=180, facecolor=SURFACE)
    plt.close(fig)


def scenario_dots(tbl: pd.DataFrame, col: str, path: str, title: str):
    t = tbl.iloc[::-1]
    fig, ax = plt.subplots(figsize=(6.2, 0.38 * len(t) + 1.0), facecolor=SURFACE)
    y = np.arange(len(t))
    ax.scatter(t[col], y, s=36, color=BLUE, edgecolor=SURFACE, linewidth=1.5, zorder=3)
    for yi, v in zip(y, t[col]):
        if pd.notna(v):
            ax.text(v + 0.005, yi, f"{v:.2f}", va="center", fontsize=7.5, color=INK)
    ax.set_yticks(y, t["scenario"])
    ax.axvline(0.5, color=INK2, linestyle="--", linewidth=0.8)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_xlabel("Back-test AUC", fontsize=8, color=INK2)
    _style(ax, title)
    fig.tight_layout()
    fig.savefig(path, dpi=180, facecolor=SURFACE)
    plt.close(fig)
