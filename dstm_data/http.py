"""HTTP layer: polite live fetching (1 req/s, retries) and a replay transport for tests.

Both transports return the same FetchResult and report every attempt to an `on_attempt`
callback, which the pipeline writes to the audit log.
"""
from __future__ import annotations

import gzip
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

import requests

from .config import BASE_URL, USER_AGENT, Settings


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- URL builders
def page_url(symbol: str, consolidated: bool) -> str:
    s = quote(symbol, safe="")          # GVT&D -> GVT%26D, M&M -> M%26M
    return f"{BASE_URL}/company/{s}/consolidated/" if consolidated else f"{BASE_URL}/company/{s}/"


def schedule_url(company_id: str, parent: str, section: str, consolidated: bool) -> str:
    # Verified 2026-11-23: Screener treats `consolidated` as PRESENCE-based.
    # Any value (even "false" or "0") returns consolidated numbers; omitting the
    # parameter returns standalone numbers. So never send consolidated=false.
    url = (f"{BASE_URL}/api/company/{company_id}/schedules/"
           f"?parent={quote(parent, safe='')}&section={quote(section, safe='')}")
    return url + "&consolidated=" if consolidated else url


def price_url(company_id: str) -> str:
    """Screener chart API: weekly closing prices (split-adjusted, price only - no dividends), ~2005 onwards."""
    return f"{BASE_URL}/api/company/{company_id}/chart/?q=Price&days=10000"


def normalize_url(url: str) -> str:
    """Canonical form used to match URLs (replay, cache keys)."""
    p = urlsplit(url)
    q = sorted(parse_qsl(p.query, keep_blank_values=True))
    path = quote(unquote(p.path), safe="/-_.~")
    return f"{p.scheme}://{p.netloc.lower()}{path}" + (f"?{urlencode(q, quote_via=quote)}" if q else "")


# ---------------------------------------------------------------- results
@dataclass
class FetchResult:
    url: str
    status: int                  # HTTP status; 0 = network error / not available
    body: Optional[str]
    fetched_at: str              # UTC ISO time the response was obtained
    elapsed_ms: int
    attempts: int
    mode: str                    # live | replay
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == 200 and self.body is not None


AttemptCallback = Callable[[dict], None]

RETRY_STATUS = {429, 500, 502, 503, 504}
NO_RETRY_STATUS = {400, 401, 403, 404, 410}   # 403 = login-only content; 404 = no such page


class RateLimiter:
    def __init__(self, min_interval_s: float):
        self.min_interval_s = min_interval_s
        self._last = 0.0

    def wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.min_interval_s:
            time.sleep(self.min_interval_s - gap)
        self._last = time.monotonic()


class LiveTransport:
    mode = "live"

    def __init__(self, settings: Settings, on_attempt: Optional[AttemptCallback] = None,
                 session: Optional[requests.Session] = None, sleep=time.sleep):
        self.s = settings
        self.on_attempt = on_attempt or (lambda rec: None)
        self.limiter = RateLimiter(settings.min_interval_s)
        self.sleep = sleep
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-IN,en;q=0.9",
            "Referer": BASE_URL + "/",
        })

    def get(self, url: str) -> FetchResult:
        is_api = "/api/" in url
        headers = {"Accept": "application/json, text/plain, */*"} if is_api else {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        last_err, status, body = None, 0, None
        t_start = time.monotonic()
        attempt = 0
        for attempt in range(1, self.s.max_retries + 2):
            self.limiter.wait()
            t0 = time.monotonic()
            ts = utcnow()
            retry_after = None
            try:
                r = self.session.get(url, headers=headers, timeout=self.s.timeout_s)
                status = r.status_code
                body = r.text if status == 200 else None
                last_err = None if status == 200 else f"HTTP {status}"
                retry_after = r.headers.get("Retry-After")
                nbytes = len(r.content)
            except requests.RequestException as e:   # timeouts, DNS, connection reset
                status, body, nbytes = 0, None, 0
                last_err = f"{type(e).__name__}: {e}"[:300]
            self.on_attempt({"url": url, "ts_utc": ts, "status": status, "bytes": nbytes,
                             "elapsed_ms": int((time.monotonic() - t0) * 1000), "attempt": attempt,
                             "mode": self.mode, "error": last_err})
            if status == 200 or status in NO_RETRY_STATUS:
                break
            if attempt <= self.s.max_retries and (status == 0 or status in RETRY_STATUS):
                wait = self.s.backoff_base_s * (2 ** (attempt - 1))
                if retry_after and retry_after.isdigit():
                    wait = max(wait, float(retry_after))
                self.sleep(min(wait, 120))
                continue
            break
        return FetchResult(url, status, body, utcnow(), int((time.monotonic() - t_start) * 1000),
                           attempt, self.mode, last_err)


class ReplayTransport:
    """Serves responses captured earlier (e.g. in a browser) so the unchanged pipeline can run offline.

    Capture file format: {"<url>": {"status": 200, "body": "...", "fetched_at": "...", "content_type": "..."}}
    """
    mode = "replay"

    def __init__(self, capture_files, on_attempt: Optional[AttemptCallback] = None):
        self.on_attempt = on_attempt or (lambda rec: None)
        self.items: dict[str, dict] = {}
        for f in ([capture_files] if isinstance(capture_files, (str, bytes)) or hasattr(capture_files, "read_text") else capture_files):
            opener = gzip.open if str(f).endswith(".gz") else open
            with opener(f, "rt", encoding="utf-8") as fh:
                data = json.load(fh)
            data = data.get("items", data)
            for u, rec in data.items():
                self.items[normalize_url(u)] = rec

    def get(self, url: str) -> FetchResult:
        rec = self.items.get(normalize_url(url))
        if rec is None:
            res = FetchResult(url, 0, None, utcnow(), 0, 1, self.mode, "not in capture file")
        else:
            st = int(rec.get("status") or 0)
            res = FetchResult(url, st, rec.get("body") if st == 200 else None,
                              rec.get("fetched_at") or utcnow(), 0, 1, self.mode,
                              None if st == 200 else f"HTTP {st}")
        self.on_attempt({"url": url, "ts_utc": res.fetched_at, "status": res.status,
                         "bytes": len(res.body or ""), "elapsed_ms": 0, "attempt": 1,
                         "mode": self.mode, "error": res.error})
        return res
