"""Automatic number check: every number the model writes must come from the fact pack.

Rules
  * Numbers are found with their unit (%, x, Rs .. Cr, days, quarters, years, bps or none).
  * A sentence's citations [F#] are the facts its numbers must match. A cited number passes if it equals the
    cited fact's value (in display units: 0.42 -> 42%) or a number printed in that fact's label/text, within the
    rounding the model used (writes 1.3x -> +/-0.05; writes 1.31x -> +/-0.005). Units must be compatible.
  * An uncited number passes only if it matches some fact the same way; it is reported as "uncited".
  * Four-digit years 2000-2040 with no unit are allowed (fiscal-year references). Citation ids themselves
    (F12) are not numbers.
  * Anything else fails: new calculations, outside figures, wrong precision, wrong unit.
Covenant items must cite at least one policy or tailored-level fact and state its level.
Limitation: this proves numbers come from the data, not that surrounding words ("rose", "below") are right.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .facts import Pack

CITE_RE = re.compile(r"\[(F\d+(?:\s*[,;/]\s*F\d+)*)\]")
NUM_RE = re.compile(r"(?<![A-Za-z0-9_.])(?P<rs>(?:Rs\.?|INR|₹)\s*)?(?P<num>[-−+]?\d[\d,]*(?:\.\d+)?)"
                    r"(?P<unit>\s*(?:%|per\s?cent\b|x\b|×|times\b|crore\b|Cr\b|days?\b|quarters?\b|years?\b|bps\b))?",
                    re.IGNORECASE)
SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'•\-])|\n+")
UNIT_OF_FACT = {"pct": "%", "x": "x", "rs_cr": "rs", "days": "days", "quarters": "quarters", "years": "years",
                "score": "", "count": ""}


@dataclass
class NumCheck:
    field: str
    text: str
    value: float
    unit: str
    cited: list
    status: str          # ok | ok_uncited | structural | mismatch | unmatched
    matched: str
    context: str


def _unit(m) -> str:
    u = (m.group("unit") or "").strip().lower()
    if m.group("rs") or u in ("crore", "cr"):
        return "rs"
    if u in ("%", "per cent", "percent", "percent"):
        return "%"
    if u.startswith("per"):
        return "%"
    if u in ("x", "×", "times"):
        return "x"
    if u.startswith("day"):
        return "days"
    if u.startswith("quarter"):
        return "quarters"
    if u.startswith("year"):
        return "years"
    if u == "bps":
        return "bps"
    return ""


def _decimals(raw: str) -> int:
    return len(raw.split(".")[1]) if "." in raw else 0


def _candidates(f) -> list:
    out = []
    if f.value is not None:
        v = f.value * 100 if f.unit == "pct" else f.value
        out.append((v, UNIT_OF_FACT.get(f.unit, ""), f"{f.id} value {f.display}"))
    for n in f.numbers:
        out.append((n, "*", f"{f.id} label/text"))
    return out


def _match(val, unit, dec, cands):
    tol = 0.5 * 10 ** (-dec) + 1e-9
    for cv, cu, desc in cands:
        if cu not in ("*", unit) and unit != "" and not (unit in ("quarters", "years") and cu == ""):
            continue
        if unit == "" and cu not in ("*", "", "x", "%", "rs", "days", "quarters", "years"):
            continue
        if abs(val - cv) <= tol or abs(round(cv, dec) - val) <= 1e-9:
            return desc
    return None


def check_text(text: str, field: str, pack: Pack) -> list[NumCheck]:
    facts = {f.id: f for f in pack.facts}
    all_cands = [c for f in pack.facts for c in _candidates(f)]
    out = []
    names = [f.display for f in pack.facts if f.key in ("company", "sector") and f.display]
    for nm in sorted(names, key=len, reverse=True):                 # digits inside names are not figures
        if re.search(r"\d", nm):
            text = re.sub(r"(?<!\w)" + re.escape(nm) + r"(?!\w)", lambda m: "#" * len(m.group(0)), text or "")
    for sent in SENT_RE.split(text or ""):
        if not sent.strip():
            continue
        cited = []
        for m in CITE_RE.finditer(sent):
            cited += [x.strip() for x in re.split(r"[,;/]", m.group(1))]
        clean = CITE_RE.sub(lambda m: " " * len(m.group(0)), sent)
        clean = re.sub(r"\b(?:Q[1-4]|H[12]|FY|F)(?=\d)", "", clean)          # FY2026 -> 2026 ; Q1 stays out
        for m in NUM_RE.finditer(clean):
            raw = m.group("num")
            try:
                val = float(raw.replace(",", "").replace("−", "-").replace("+", ""))
            except ValueError:
                continue
            unit, dec = _unit(m), _decimals(raw)
            ctx = sent.strip()[:160]
            if unit == "" and dec == 0 and 2000 <= val <= 2040 and "," not in raw:
                out.append(NumCheck(field, m.group(0).strip(), val, unit, cited, "structural", "year", ctx))
                continue
            known = [facts[c] for c in cited if c in facts]
            if known:
                hit = _match(val, unit, dec, [c for f in known for c in _candidates(f)])
                if hit:
                    out.append(NumCheck(field, m.group(0).strip(), val, unit, cited, "ok", hit, ctx))
                    continue
                alt = _match(val, unit, dec, all_cands)
                out.append(NumCheck(field, m.group(0).strip(), val, unit, cited, "mismatch",
                                    f"does not match cited {', '.join(cited)}" + (f" (matches {alt})" if alt else ""), ctx))
                continue
            hit = _match(val, unit, dec, all_cands)
            out.append(NumCheck(field, m.group(0).strip(), val, unit, cited, "ok_uncited" if hit else "unmatched",
                                hit or "no fact has this number", ctx))
    return out


def iter_fields(out: dict):
    note = out.get("credit_note") or {}
    for k, v in note.items():
        yield f"credit_note.{k}", v
    for i, c in enumerate(out.get("covenants") or [], 1):
        for k in ("covenant", "level", "rationale"):
            yield f"covenants[{i}].{k}", c.get(k, "")
    for i, t in enumerate(out.get("monitoring_triggers") or [], 1):
        for k in ("trigger", "threshold", "action"):
            yield f"monitoring_triggers[{i}].{k}", t.get(k, "")
    for i, q in enumerate(out.get("dd_questions") or [], 1):
        for k in ("question", "red_flag", "why"):
            yield f"dd_questions[{i}].{k}", q.get(k, "")


def check_output(out: dict, pack: Pack) -> dict:
    items = []
    for field, text in iter_fields(out):
        if isinstance(text, str):
            items += check_text(text, field, pack)
    problems = [asdict(i) for i in items if i.status in ("mismatch", "unmatched")]
    level_keys = {f.id for f in pack.facts if f.key.startswith(("cov_", "policy_"))}
    struct = []
    for i, c in enumerate(out.get("covenants") or [], 1):
        cites = set(re.findall(r"F\d+", " ".join(str(c.get(k, "")) for k in ("covenant", "level", "rationale"))))
        if not cites & level_keys:
            struct.append(f"covenants[{i}] does not cite a policy or tailored-level fact")
    for k in ("credit_note", "covenants", "monitoring_triggers", "dd_questions"):
        if not out.get(k):
            struct.append(f"missing section: {k}")
    n = len(items)
    return {"passed": not problems and not struct, "n_numbers": n,
            "n_verified": sum(i.status in ("ok", "ok_uncited", "structural") for i in items),
            "n_uncited": sum(i.status == "ok_uncited" for i in items), "problems": problems, "structure": struct,
            "items": [asdict(i) for i in items]}
