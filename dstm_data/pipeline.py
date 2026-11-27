"""Refresh pipeline: decide what is stale, fetch politely, choose the basis, parse, store.

Flow per company
  1. GET /company/{SYMBOL}/consolidated/ (and /company/{SYMBOL}/ when basis="both", or when
     consolidated is missing / stale / only standalone-filled).
  2. Primary basis = consolidated if it has its own figures at least as recent as standalone,
     otherwise standalone (reason stored in company_status.basis_note).
  3. Lender layout (Screener "Financing Profit") -> excluded, no schedules fetched.
  4. Schedules for the primary basis (and the secondary basis when basis="both").
  5. Rebuild tidy rows from the cache (last good copy of every URL), so a failed request
     falls back to cached data instead of losing it.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from .cache import Cache
from .canonical import build_credit_lines
from .config import Settings
from .http import FetchResult, LiveTransport, ReplayTransport, page_url, price_url, schedule_url
from .parse import CompanyPage, parse_prices, parse_schedule, schedule_children

OBS_COLS = ["symbol", "basis", "basis_role", "statement", "parent", "line_item", "period_label", "period_end",
            "period_type", "period_months", "value", "unit", "is_standalone_fill", "source_url", "fetched_at"]
CL_COLS = ["symbol", "basis", "basis_role", "frequency", "period_end", "period_label", "period_months",
           "field", "value", "unit", "source", "flag", "source_url", "fetched_at"]
NOT_AVAILABLE = {403, 404}      # schedule exists on page but is login-only / absent: not a fetch failure


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Pipeline:
    def __init__(self, settings: Settings, cache: Optional[Cache] = None, transport=None,
                 replay_files: Optional[list] = None, offline: bool = False):
        self.s = settings
        self.cache = cache or Cache(settings.db_path)
        self.run_id = _now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        self._symbol = None
        self.offline = offline
        if transport is not None:
            self.t = transport
        elif replay_files:
            self.t = ReplayTransport(replay_files, on_attempt=self._log)
        else:
            self.t = LiveTransport(settings, on_attempt=self._log)
        if hasattr(self.t, "on_attempt"):
            self.t.on_attempt = self._log

    # ------------------------------------------------------------------ helpers
    def _log(self, rec: dict):
        self.cache.log_attempt(self.run_id, self._symbol, rec)

    def _get(self, url: str) -> FetchResult:
        res = self.t.get(url)
        self.cache.put_response(url, res.status, res.body, res.fetched_at, res.mode)
        self.cache.con.commit()
        return res

    def _cached_page(self, symbol: str, consolidated: bool) -> Optional[CompanyPage]:
        rec = self.cache.get_response(page_url(symbol, consolidated))
        return CompanyPage(rec["body"]) if rec else None

    def is_stale(self, symbol: str) -> bool:
        st = self.cache.get_status(symbol)
        if not st or not st.get("last_success") or st.get("status") not in ("ok", "excluded_lender"):
            return True
        age = _now() - datetime.fromisoformat(st["last_success"])
        return age > timedelta(days=self.s.max_age_days)

    # ------------------------------------------------------------------ basis choice
    def choose_basis(self, cons: Optional[CompanyPage], stand: Optional[CompanyPage]) -> tuple[Optional[str], str]:
        def has_own(p):
            return p is not None and p.latest_annual(own_only=True) is not None
        if not has_own(cons) and not has_own(stand):
            return None, "no annual figures on either page"
        if not has_own(cons):
            return "standalone", "consolidated page missing or only standalone-filled '(S)' columns"
        c_last = cons.latest_annual(own_only=True)
        if stand is not None and has_own(stand):
            s_last = stand.latest_annual()
            if c_last < s_last:
                return "standalone", f"consolidated stale (latest own FY {c_last} vs standalone {s_last})"
            return "consolidated", f"consolidated current (latest FY {c_last})"
        cutoff = (date.today() - timedelta(days=30.5 * self.s.stale_consolidated_months)).isoformat()
        if c_last < cutoff:
            return "standalone", f"consolidated stale (latest own FY {c_last} older than {self.s.stale_consolidated_months} months)"
        return "consolidated", f"consolidated current (latest FY {c_last}; standalone not checked)"

    # ------------------------------------------------------------------ one company
    def refresh_company(self, symbol: str, name: str = None, industry: str = None) -> dict:
        self._symbol = symbol
        started = _now().isoformat(timespec="seconds")
        planned, failed, not_avail, msgs = 0, 0, 0, []

        def fetch(url, schedule=False):
            nonlocal planned, failed, not_avail
            planned += 1
            r = self._get(url)
            if not r.ok:
                if schedule and r.status in NOT_AVAILABLE:
                    not_avail += 1
                    msgs.append(f"not available ({r.status}): {url}")
                else:
                    failed += 1
                    msgs.append(f"failed ({r.error}): {url}")
            return r

        if not self.offline:
            rc = fetch(page_url(symbol, True))
            need_stand = self.s.basis == "both" or not rc.ok
            if not need_stand:
                cons_tmp = CompanyPage(rc.body)
                basis_tmp, _ = self.choose_basis(cons_tmp, None)
                need_stand = basis_tmp != "consolidated"
            if need_stand:
                fetch(page_url(symbol, False))

        cons, stand = self._cached_page(symbol, True), self._cached_page(symbol, False)
        if cons is None and stand is None:
            all_404 = all("404" in m for m in msgs[:2]) and msgs
            status = "not_found" if all_404 else "failed_no_data"
            self.cache.set_status(symbol=symbol, company_name=name, industry=industry, last_attempt=started,
                                  status=status, message="; ".join(msgs)[:2000], n_requests=planned, n_failed=failed)
            return {"symbol": symbol, "status": status, "failed": failed, "messages": msgs}

        primary, note = self.choose_basis(cons, stand)
        page = (cons if primary == "consolidated" else stand) or cons or stand
        layout = page.layout
        cid = page.company_id
        if layout == "lender":
            self.cache.set_status(symbol=symbol, company_name=name, industry=industry, company_id=cid,
                                  primary_basis=primary, basis_note=note, layout=layout, last_attempt=started,
                                  last_success=started if failed == 0 else None, status="excluded_lender",
                                  message="Screener lender layout (Financing Profit); excluded from non-financial universe",
                                  n_requests=planned, n_failed=failed)
            self.rebuild(symbol)
            return {"symbol": symbol, "status": "excluded_lender", "failed": failed, "messages": msgs}

        bases = self.bases_for(primary, cons, stand)
        if not self.offline and cid and primary:
            for b in bases:
                for parent, section in self.s.schedules:
                    fetch(schedule_url(cid, parent, section, b == "consolidated"), schedule=True)
            if self.s.fetch_prices:
                fetch(price_url(cid), schedule=True)

        if primary is None:
            status = "failed_no_data"
        elif self.offline:
            status = (self.cache.get_status(symbol) or {}).get("status") or "offline_cache"
        elif failed == 0:
            status = "ok"
        elif failed < planned:
            status = "partial"          # cached copies used for the failed URLs where available
        else:
            status = "failed_served_cache"
        upd = dict(symbol=symbol, company_name=name, industry=industry, company_id=cid, primary_basis=primary,
                   basis_note=note, layout=layout, status=status,
                   message=("; ".join(msgs)[:2000] or None), n_requests=planned, n_failed=failed)
        if not self.offline:
            upd["last_attempt"] = started
            if failed == 0:
                upd["last_success"] = started
        self.cache.set_status(**upd)
        n_obs, n_cl = self.rebuild(symbol)
        return {"symbol": symbol, "status": status, "basis": primary, "note": note, "requests": planned,
                "failed": failed, "not_available": not_avail, "observations": n_obs, "credit_lines": n_cl,
                "messages": msgs}

    def bases_for(self, primary, cons, stand) -> list[str]:
        if primary is None:
            return []
        bases = [primary]
        if self.s.basis == "both" and primary == "consolidated" and stand is not None \
                and stand.latest_annual(own_only=True):
            bases.append("standalone")
        return bases

    # ------------------------------------------------------------------ parse cache -> tidy
    def rebuild(self, symbol: str) -> tuple[int, int]:
        st = self.cache.get_status(symbol) or {}
        primary = st.get("primary_basis")
        cons, stand = self._cached_page(symbol, True), self._cached_page(symbol, False)
        obs_all, cl_all = [], []
        if primary and st.get("layout") != "lender":
            for basis in self.bases_for(primary, cons, stand):
                page = cons if basis == "consolidated" else stand
                role = "primary" if basis == primary else "secondary"
                prec = self.cache.get_response(page_url(symbol, basis == "consolidated"))
                rows = []
                for r in page.rows() + page.top_ratios():
                    rows.append({**r, "source_url": prec["url"], "fetched_at": prec["fetched_at"]})
                fetched = {}
                for parent, section in self.s.schedules:
                    url = schedule_url(page.company_id, parent, section, basis == "consolidated")
                    rec = self.cache.get_response(url)
                    if rec is None:
                        continue
                    try:
                        srows = parse_schedule(rec["body"], section, parent, page)
                    except (ValueError, json.JSONDecodeError):
                        continue
                    fetched[(section, parent)] = set(schedule_children(rec["body"]))
                    rows += [{**r, "source_url": rec["url"], "fetched_at": rec["fetched_at"]} for r in srows]
                for r in rows:
                    obs_all.append({**r, "symbol": symbol, "basis": basis, "basis_role": role})
                for c in build_credit_lines(rows, fetched):
                    cl_all.append({**c, "symbol": symbol, "basis": basis, "basis_role": role})
        px = []
        cid = (cons or stand).company_id if (cons or stand) else None
        prec = self.cache.get_response(price_url(cid)) if cid else None
        if prec:
            try:
                px = [{**r, "symbol": symbol, "source_url": prec["url"], "fetched_at": prec["fetched_at"]}
                      for r in parse_prices(prec["body"])]
            except (ValueError, json.JSONDecodeError, KeyError, IndexError):
                px = []
        self.cache.replace_rows("prices", symbol, px, ["symbol", "date", "close", "source_url", "fetched_at"])
        self.cache.replace_rows("observations", symbol, obs_all, OBS_COLS)
        self.cache.replace_rows("credit_lines", symbol, cl_all, CL_COLS)
        return len(obs_all), len(cl_all)

    # ------------------------------------------------------------------ many companies
    def refresh(self, universe: pd.DataFrame, force: bool = False, progress=print) -> pd.DataFrame:
        self.cache.start_run(self.run_id, "offline" if self.offline else self.t.mode,
                             json.dumps({"n": len(universe), "force": force, "basis": self.s.basis}))
        results = []
        for i, row in enumerate(universe.itertuples(index=False), 1):
            sym = row.symbol
            if not force and not self.offline and not self.is_stale(sym):
                results.append({"symbol": sym, "status": "fresh_skipped"})
                progress(f"[{i}/{len(universe)}] {sym}: fresh, skipped")
                continue
            try:
                res = self.refresh_company(sym, getattr(row, "company_name", None), getattr(row, "industry", None))
            except Exception as e:          # never let one company stop the run
                res = {"symbol": sym, "status": "error", "messages": [f"{type(e).__name__}: {e}"]}
                self.cache.set_status(symbol=sym, status="error", message=str(e)[:2000],
                                      last_attempt=_now().isoformat(timespec="seconds"))
            results.append(res)
            progress(f"[{i}/{len(universe)}] {sym}: {res['status']}"
                     + (f" basis={res.get('basis')} req={res.get('requests')} failed={res.get('failed')}"
                        f" obs={res.get('observations')}" if "requests" in res else ""))
        df = pd.DataFrame(results)
        self.cache.finish_run(self.run_id, df["status"].value_counts().to_json() if len(df) else "{}")
        return df
