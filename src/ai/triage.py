"""AI triage: read each complaint narrative and fill a validated, structured form (see src/ai/schema.py).

Pipeline per complaint:  pick sample -> mask PII -> prompt -> LLM (JSON) -> validate with Pydantic
                         (retry once if invalid, then mark 'failed') -> save to complaint_triage.

Safe to re-run: complaints already done for this prompt version are skipped (idempotent), so a run can stop
(rate limit, crash, Ctrl+C) and continue later.

Usage:
  python -m src.ai.triage sample [N]            # choose N complaints (default 1500) once, reproducibly
  python -m src.ai.triage run [v1] [--limit K]  # triage up to K not-yet-done complaints with prompt triage_<version>.txt
  python -m src.ai.triage summary [v1]          # counts, validity and cost
"""
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from src.ai.pii import mask_pii
from src.ai.schema import Triage
from src.ingest.cfpb import ROOT, connect

load_dotenv(ROOT / ".env")
log = logging.getLogger("triage")
PROMPT_DIR = ROOT / "prompts"
MAX_CHARS = 4000     # long narratives are cut: median is ~730 chars, a few reach 30,000; keeps cost bounded
SAMPLE_SEED = 42
SYSTEM = "You are a careful complaint triage assistant. Answer only with JSON matching the schema."


def init_tables(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS triage_sample (complaint_id VARCHAR PRIMARY KEY, selected_at TIMESTAMP DEFAULT now());
        CREATE TABLE IF NOT EXISTS complaint_triage (
            complaint_id VARCHAR, prompt_version VARCHAR, status VARCHAR,       -- 'ok' or 'failed'
            summary VARCHAR, root_cause VARCHAR, severity INTEGER, monetary_harm_usd DOUBLE,
            vulnerable_consumer BOOLEAN, requested_remedy VARCHAR, confidence DOUBLE,
            model_name VARCHAR, processed_at TIMESTAMP, input_tokens INTEGER, output_tokens INTEGER,
            cost_usd DOUBLE, error VARCHAR, pii_found VARCHAR,
            PRIMARY KEY (complaint_id, prompt_version));""")


# ---------- sample ----------
def make_sample(con, n=1500):
    """Random sample spread over products, only complaints with a narrative and only the first copy of
    duplicated texts (see Phase 1: one template appears 578 times). Saved so the sample never changes."""
    init_tables(con)
    have = con.execute("SELECT count(*) FROM triage_sample").fetchone()[0]
    if have:
        return have
    df = con.execute("SELECT complaint_id, product FROM complaints WHERE has_narrative AND is_first_copy").df()
    # proportional to product size, but at least one complaint from every product
    share = df["product"].value_counts(normalize=True)
    picked = [g.sample(min(len(g), max(round(n * share[p]), 1)), random_state=SAMPLE_SEED) for p, g in df.groupby("product")]
    ids = [(i,) for part in picked for i in part.complaint_id]
    con.executemany("INSERT INTO triage_sample (complaint_id) VALUES (?)", ids)
    return len(ids)


# ---------- prompt ----------
def load_prompt(version):
    return (PROMPT_DIR / f"triage_{version}.txt").read_text(encoding="utf-8")


def build_prompt(template, product, issue, narrative):
    # str.replace, not str.format: the template and narratives contain curly braces ({$12.34}, JSON examples)
    return (template.replace("{product}", str(product)).replace("{issue}", str(issue))
            .replace("{narrative}", narrative))


# ---------- one complaint ----------
def triage_one(client, template, row, retries=1):
    """Returns (Triage or None, error text or None, input_tokens, output_tokens, pii counter)."""
    text = " ".join(str(row.narrative).split())[:MAX_CHARS]
    masked, pii = mask_pii(text)
    prompt = build_prompt(template, row.product, row.issue, masked)
    tin = tout = 0
    error = None
    for _ in range(retries + 1):
        res = client.complete(SYSTEM, prompt, Triage)
        tin, tout = tin + res.input_tokens, tout + res.output_tokens
        try:
            return Triage.model_validate_json(res.text), None, tin, tout, pii
        except ValidationError as e:
            error = str(e).splitlines()[0][:200] + " | " + res.text[:120].replace("\n", " ")
    return None, error, tin, tout, pii


def run(version="v1", limit=None, client=None):
    con = connect()
    init_tables(con)
    template = load_prompt(version)
    if client is None:
        from src.ai.llm import get_client
        client = get_client()
    todo = con.execute("""
        SELECT c.complaint_id, c.product, c.issue, c.narrative
        FROM triage_sample s JOIN complaints c USING (complaint_id)
        WHERE NOT EXISTS (SELECT 1 FROM complaint_triage t WHERE t.complaint_id = s.complaint_id
                          AND t.prompt_version = $v AND t.status = 'ok')
        ORDER BY hash(c.complaint_id)   -- fixed pseudo-random order: a partial run is still an unbiased sample
        """, {"v": version}).df()
    if limit:
        todo = todo.head(limit)
    ok = failed = 0
    for i, row in enumerate(todo.itertuples(), 1):
        try:
            t, err, tin, tout, pii = triage_one(client, template, row)
        except Exception as e:  # network / quota problem: stop cleanly, progress is already saved
            log.error("stopped after %d complaints: %s", i - 1, str(e)[:200])
            break
        fields = t.model_dump() if t else {}
        con.execute("INSERT OR REPLACE INTO complaint_triage VALUES (?,?,?,?,?,?,?,?,?,?,?,now(),?,?,?,?,?)", [
            row.complaint_id, version, "ok" if t else "failed", fields.get("summary"), fields.get("root_cause"),
            fields.get("severity"), fields.get("monetary_harm_usd"), fields.get("vulnerable_consumer"),
            fields.get("requested_remedy"), fields.get("confidence"), client.model_name, tin, tout,
            estimate_cost(tin, tout), err, json.dumps(dict(pii))])
        ok, failed = ok + bool(t), failed + (not t)
        if i % 50 == 0:
            log.info("%d/%d done (%d failed)", i, len(todo), failed)
    log.info("run finished: %d ok, %d failed, %d still to do", ok, failed, max(len(todo) - ok - failed, 0))
    con.close()


def estimate_cost(tokens_in, tokens_out):
    """Paid-tier list price per 1M tokens (set GEMINI_PRICE_IN_PER_M / GEMINI_PRICE_OUT_PER_M in .env to estimate).
    On the free tier the real bill is 0; this shows what the same run would cost on a paid plan."""
    pin, pout = os.getenv("GEMINI_PRICE_IN_PER_M"), os.getenv("GEMINI_PRICE_OUT_PER_M")
    if not (pin and pout):
        return None
    return (tokens_in * float(pin) + tokens_out * float(pout)) / 1_000_000


def summary(version="v1"):
    con = connect()
    init_tables(con)
    r = con.execute("""
        SELECT count(*) AS n, count(*) FILTER (WHERE status = 'ok') AS ok, sum(input_tokens) AS tin,
               sum(output_tokens) AS tout, sum(cost_usd) AS cost, any_value(model_name) AS model
        FROM complaint_triage WHERE prompt_version = $v""", {"v": version}).df().iloc[0]
    sample = con.execute("SELECT count(*) FROM triage_sample").fetchone()[0]
    if not r.n:
        log.info("nothing processed yet for %s (sample size %d)", version, sample)
        return
    cost = estimate_cost(r.tin, r.tout)  # from stored token counts, so older rows are covered too
    log.info("%s | model %s | processed %d of %d sampled | valid %.1f%% | tokens in/out per complaint %d/%d | %s",
             version, r.model, r.n, sample, 100 * r.ok / r.n, r.tin / r.n, r.tout / r.n,
             f"est. paid-tier cost ${cost / r.n:.5f} per complaint (${cost:.3f} total; free tier bill is $0)"
             if cost is not None else "cost n/a (set GEMINI_PRICE_* in .env)")
    con.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    for noisy in ("httpx", "google_genai", "httpcore", "presidio-analyzer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)  # one log line per API call is too much
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    nums = [x for x in a[1:] if x.isdigit()]
    version = next((x for x in a[1:] if x.startswith("v") and x[1:].isdigit()), "v1")
    if cmd == "sample":
        con = connect()
        log.info("sample size: %d", make_sample(con, int(nums[0]) if nums else 1500))
    elif cmd == "run":
        run(version, int(a[a.index("--limit") + 1]) if "--limit" in a else None)
    elif cmd == "summary":
        summary(version)
    else:
        raise SystemExit(__doc__)
