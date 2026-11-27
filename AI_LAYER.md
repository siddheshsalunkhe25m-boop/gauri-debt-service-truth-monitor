# AI layer (`dstm_ai`)

For one company it produces a **credit pack**:
1. a one-page credit note;
2. tailored covenant suggestions;
3. monitoring triggers;
4. due-diligence questions for the borrower, based on its own red flags.

## How it runs
| Setting | Where | Default |
|---|---|---|
| API key | environment variable `ANTHROPIC_API_KEY` (never stored or logged) | missing → template mode |
| Model | `DSTM_AI_MODEL` | `claude-opus-5-5` (Anthropic's recommended default, Nov 2026); `claude-sonnet-5-5` is faster and cheaper |
| Max output tokens | `DSTM_AI_MAX_TOKENS` | 4000 |
| Log folder | `DSTM_AI_LOG_DIR` | `ai_logs/` |

On Windows, set the key for the current window before starting the dashboard: `set ANTHROPIC_API_KEY=...`, then `run_dashboard.bat`.

- **Dashboard:** Company drill-down → tab *AI credit note* → *Generate credit pack*.
- **AI usage log:** Method & data → *AI usage log*; downloads `AI_Usage_Appendix.md`, `AI_Usage_Log.xlsx` and `ai_log.jsonl`.
- **CLI:** `python -m dstm_ai note TATASTEEL` and `python -m dstm_ai appendix`.

The call uses **structured outputs**: a JSON schema in `output_config.format`, with the JSON returned in the text block. Forced tool choice is not used because it returns HTTP 400 on the newest models.

## What the model receives: computed numbers only
The model receives a **fact pack** of about 60–70 numbered facts. Each fact is built by Python from the RTS engine, with a fixed display string:
- RTS, class and sub-scores;
- FA-DSCR and reported DSCR;
- Minsky state;
- refinancing dependence;
- the latest year's CFO-to-CFADS bridge;
- Breach Clock results;
- policy covenants;
- peer percentiles;
- red flags;
- process constants;
- **tailored covenant and trigger levels**.

It never receives statements, filings, prices or web content.

The tailored levels are computed by fixed rules (`dstm_ai/facts.py`). The model **chooses and explains them; it never invents a level.**

| Level | Rule |
|---|---|
| DSCR floor (FA basis, annual) | 0.80 × 3-yr FA-DSCR, rounded down to 0.05x, within 1.00–1.30x |
| ICR floor (TTM, quarterly) | 0.70 × ICR now, rounded down to 0.25x, within policy and 2 × policy |
| Debt/EBITDA cap (TTM, quarterly) | 1.30 × now, rounded up to 0.25x, within 2.00x and policy |
| Creditor-days cap | own 3-yr norm + 15 days (payables flag only) |
| Refinancing cap / cash sweep | 50% (refinancing > 50%; sweep also for Escalate) |
| Debt-service reserve | 2 quarters of interest (floor above current FA-DSCR, or Escalate) |
| Amber triggers | ICR floor × 1.25; D/EBITDA cap × 0.85; breach probability 20%; quarterly EBITDA −15% YoY; creditor days norm + 10 |

## Number check (`dstm_ai/check.py`)
Every number in every field is extracted together with its unit: %, x, Rs/Cr, days, quarters, years.
- **Cited numbers:** a number with a citation must equal the cited fact. The fact's value is compared in display units, or a number printed in that fact's label or text is accepted. The precision is the rounding the model wrote: 1.3x is accepted for 1.31x, 1.35x is not. Units must match.
- **Uncited numbers:** these must match some fact; they are reported as "uncited".
- **Exceptions:** four-digit years and digits inside the company name are ignored.
- **Covenants:** each covenant must cite a policy or tailored-level fact.

If a draft fails:
1. Claude gets one correction round, with the exact rejected numbers.
2. If it fails again, the **rule-based template** is used. The template is written from the same facts and also passes the check.

Rejected drafts are kept in the log and shown in the dashboard.

**Limitation:** the check proves the numbers come from the data. It does not prove the surrounding words are right: "rose" vs "fell", "above" vs "below", or the soundness of the reasoning. The analyst still reads the note.

## Log for the AI-usage appendix (`dstm_ai/log.py`)
`ai_logs/ai_log.jsonl` has one line per run, containing:
- the system prompt and its SHA-256;
- the full user prompt (the fact pack);
- every API attempt: raw output, check result, tokens, latency, errors;
- the correction request;
- rejected drafts;
- the final mode and output;
- the model settings.

The log writer refuses to write anything that looks like an API key.

## Tests (`tests/test_ai.py`, no network)
- Tailored-level rules are hand-worked.
- Checker rules:
  - rounding, wrong number, wrong unit, uncited numbers;
  - years and digits in names;
  - "percentile" is not "%".
- The template passes the check for all 40 demo companies.
- The prompt contains only fact lines.
- Orchestration with a fake client covers:
  - accepted on the first attempt;
  - corrected, then accepted;
  - rejected twice → template;
  - API error;
  - invalid JSON;
  - no key.
- The log and appendix exports work, and no key appears in the log.
- The real `anthropic` SDK was run against a local mock Messages API. This checks the endpoint, the API-key header and that `output_config.format.type = json_schema` is sent.

**No live API call has been made from this workspace, because there is no key here. The first live run will be on your machine.**
