"""Systemic risk alerts: find groups of similar complaints that are growing fast.

Two detectors, one rule ("this month >= 2x the average of the previous 3 months AND at least 10 complaints"):
  A. narrative clusters: all complaints with a narrative are embedded (local MiniLM), grouped with KMeans, each group
     is named by the LLM ("Direct deposits not credited"), and counted per month.
  B. structured groups: product + issue + sub-issue counted per month. Needs no narrative, so it still works for
     recent months, when the CFPB stopped publishing narratives.
Each alert gets: name, growth, top states, severity mix (from AI-triaged complaints), 3 examples, suggested regulations.

Why embed narratives rather than the AI summaries: summaries exist only for the ~1,500 triaged complaints, which
is too few per month for the 10-complaint rule; embedding all narratives covers 26,000.

Usage: python -m src.ai.clusters build     # embed, cluster, name
       python -m src.ai.clusters alerts    # detect growth, write risk_alerts
"""
import json
import logging
import sys

import numpy as np
import pandas as pd
from pydantic import BaseModel

from src.ai.embeddings import collection, embed
from src.ingest.cfpb import connect

log = logging.getLogger("clusters")
N_CLUSTERS = 30
SEED = 42
MIN_COUNT, FACTOR, WINDOW = 10, 2.0, 3
MAX_CHARS = 1000      # narrative characters embedded


class ClusterName(BaseModel):
    name: str          # at most ~8 words
    description: str   # one sentence


# ---------- step 1: embeddings ----------
def prepare_embeddings(con, coll, embed_fn=embed, batch=256):
    df = con.execute("""SELECT complaint_id, year_month, product, issue, coalesce(state, 'Unknown') AS state, narrative
                        FROM complaints WHERE has_narrative""").df()
    have = set(coll.get(include=[])["ids"])
    todo = df[~df.complaint_id.isin(have)]
    for lo in range(0, len(todo), batch):
        b = todo.iloc[lo:lo + batch]
        docs = [t[:MAX_CHARS] for t in b.narrative]
        coll.upsert(ids=list(b.complaint_id), documents=docs, embeddings=embed_fn(docs),
                    metadatas=[dict(year_month=r.year_month, product=r.product, issue=r.issue, state=r.state)
                               for r in b.itertuples()])
        if (lo // batch) % 20 == 0:
            log.info("embedded %d/%d", lo + len(b), len(todo))
    return len(todo)


def load_vectors(coll, ids, page=4000):
    vecs = []
    for lo in range(0, len(ids), page):
        got = coll.get(ids=ids[lo:lo + page], include=["embeddings"])
        order = {i: k for k, i in enumerate(got["ids"])}
        vecs.append(np.array(got["embeddings"])[[order[i] for i in ids[lo:lo + page]]])
    return np.vstack(vecs)


# ---------- step 2: cluster + name ----------
def cluster(con, coll, k=N_CLUSTERS):
    from sklearn.cluster import KMeans
    ids = con.execute("SELECT complaint_id FROM complaints WHERE has_narrative ORDER BY complaint_id").df().complaint_id.tolist()
    X = load_vectors(coll, ids)
    km = KMeans(n_clusters=k, n_init=3, random_state=SEED).fit(X)
    dist = km.transform(X)
    con.execute("CREATE OR REPLACE TABLE complaint_clusters (complaint_id VARCHAR PRIMARY KEY, cluster_id INTEGER, dist DOUBLE)")
    con.register("cc", pd.DataFrame({"complaint_id": ids, "cluster_id": km.labels_, "dist": dist[np.arange(len(ids)), km.labels_]}))
    con.execute("INSERT INTO complaint_clusters SELECT * FROM cc")
    con.unregister("cc")
    return len(ids)


def name_clusters(con, client, n_examples=10):
    from src.ai.triage import prepare_text
    con.execute("CREATE TABLE IF NOT EXISTS clusters (cluster_id INTEGER PRIMARY KEY, name VARCHAR, description VARCHAR, size INTEGER)")
    done = set(r[0] for r in con.execute("SELECT cluster_id FROM clusters").fetchall())
    for cid, size in con.execute("SELECT cluster_id, count(*) FROM complaint_clusters GROUP BY 1 ORDER BY 1").fetchall():
        if cid in done:
            continue
        ex = con.execute("""SELECT c.narrative FROM complaint_clusters k JOIN complaints c USING (complaint_id)
                            WHERE k.cluster_id = ? ORDER BY k.dist LIMIT ?""", [cid, n_examples]).df().narrative
        shown = "\n".join(f"- {prepare_text(t)[0][:300]}" for t in ex)
        res = client.complete(
            "You name groups of similar consumer complaints. Answer only with JSON matching the schema.",
            "Below are example complaints from one group (the most typical ones). Give the group a short specific name "
            "(at most 8 words, like 'Autopay charged twice after card replacement') and one sentence describing it.\n\n" + shown,
            ClusterName)
        n = ClusterName.model_validate_json(res.text)
        con.execute("INSERT INTO clusters VALUES (?,?,?,?)", [cid, n.name.strip(), n.description.strip(), size])
        log.info("cluster %d (%d complaints): %s", cid, size, n.name)


# ---------- step 3: growth rule (pure function, easy to test) ----------
def detect_growth(counts, min_count=MIN_COUNT, factor=FACTOR, window=WINDOW):
    """counts: DataFrame [key, year_month, n]. Flags (key, month) where n >= min_count and n >= factor x mean of
    the previous `window` calendar months (missing months count as 0; fewer than `window` months of history: skipped)."""
    out = []
    for key, g in counts.groupby("key"):
        s = g.set_index(pd.PeriodIndex(g.year_month, freq="M")).n.sort_index()
        s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"), fill_value=0)
        for i in range(window, len(s)):
            prev = s.iloc[i - window:i].mean()
            if s.iloc[i] >= min_count and s.iloc[i] >= factor * prev:
                out.append(dict(key=key, year_month=str(s.index[i]), n=int(s.iloc[i]), prev_avg=round(float(prev), 1),
                                growth_pct=round(100 * (s.iloc[i] / prev - 1), 0) if prev else None))
    return pd.DataFrame(out, columns=["key", "year_month", "n", "prev_avg", "growth_pct"])


def last_complete_month(con):
    mx = con.execute("SELECT max(date_received) FROM complaints").fetchone()[0]
    mx = pd.Timestamp(mx)
    m = mx.replace(day=1)
    return str((m if mx == mx + pd.offsets.MonthEnd(0) else m - pd.DateOffset(months=1)).to_period("M"))


# ---------- step 4: alert cards ----------
def build_alerts(con, client=None, coll=None, embed_fn=embed, max_regs=20):
    """Detect growth with both detectors and write risk_alerts (one row per alert)."""
    last_ok = last_complete_month(con)
    cl = con.execute("""SELECT k.cluster_id::VARCHAR AS key, c.year_month, count(*) AS n FROM complaint_clusters k
                        JOIN complaints c USING (complaint_id) GROUP BY 1, 2""").df()
    st = con.execute("""SELECT product || ' | ' || issue || ' | ' || coalesce(sub_issue, '(none)') AS key, year_month,
                               count(*) AS n FROM complaints GROUP BY 1, 2""").df()
    alerts = []
    for source, counts in (("narrative_cluster", cl), ("structured", st)):
        found = detect_growth(counts[counts.year_month <= last_ok])
        for r in found.itertuples():
            alerts.append(dict(source=source, **r._asdict()))
    alerts.sort(key=lambda a: -a["n"])  # alert 1 is the biggest; only the largest `max_regs` get (LLM-based) regulation suggestions
    con.execute("""CREATE OR REPLACE TABLE risk_alerts (alert_id INTEGER, source VARCHAR, key VARCHAR, name VARCHAR,
        description VARCHAR, year_month VARCHAR, n INTEGER, prev_avg DOUBLE, growth_pct DOUBLE, top_states VARCHAR,
        severity_mix VARCHAR, n_triaged INTEGER, examples VARCHAR, regulations VARCHAR, is_latest BOOLEAN)""")
    for i, a in enumerate(alerts, 1):
        enrich(con, a, client if i <= max_regs else None, coll, embed_fn)
        con.execute("INSERT INTO risk_alerts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            i, a["source"], a["key"], a["name"], a["description"], a["year_month"], a["n"], a["prev_avg"],
            a["growth_pct"], json.dumps(a["top_states"]), json.dumps(a["severity_mix"]), a["n_triaged"],
            json.dumps(a["examples"]), json.dumps(a["regulations"]), a["year_month"] == last_ok])
    return len(alerts), last_ok


def enrich(con, a, client, coll, embed_fn):
    from src.ai import regulations_rag as rag
    if a["source"] == "narrative_cluster":
        where, params = "k.cluster_id = ? AND c.year_month = ?", [int(a["key"]), a["year_month"]]
        join = "complaint_clusters k JOIN complaints c USING (complaint_id)"
        meta = con.execute("SELECT name, description FROM clusters WHERE cluster_id = ?", [int(a["key"])]).fetchone()
        a["name"], a["description"] = meta if meta else (f"Cluster {a['key']}", "")
    else:
        product, issue, sub = a["key"].split(" | ")
        where, params = "c.product = ? AND c.issue = ? AND coalesce(c.sub_issue, '(none)') = ? AND c.year_month = ?", [product, issue, sub, a["year_month"]]
        join = "complaints c"
        a["name"], a["description"] = f"{product}: {issue} ({sub})", "Complaints grouped by the product and issue the consumer chose."
    a["top_states"] = con.execute(f"SELECT coalesce(c.state, 'Unknown'), count(*) FROM {join} WHERE {where} GROUP BY 1 ORDER BY 2 DESC LIMIT 3", params).fetchall()
    sev = con.execute(f"""SELECT t.severity, count(*) FROM {join} JOIN complaint_triage t ON t.complaint_id = c.complaint_id
                          AND t.prompt_version = (SELECT max(prompt_version) FROM complaint_triage) AND t.status = 'ok'
                          WHERE {where} GROUP BY 1 ORDER BY 1""", params).fetchall() if _has_triage(con) else []
    a["severity_mix"], a["n_triaged"] = {str(s): n for s, n in sev}, sum(n for _, n in sev)
    a["examples"] = [dict(complaint_id=cid, snippet=(txt or "")[:220]) for cid, txt in con.execute(
        f"SELECT c.complaint_id, c.narrative FROM {join} WHERE {where} AND c.has_narrative ORDER BY c.complaint_id LIMIT 3", params).fetchall()]
    a["regulations"] = []
    if client is not None and coll is not None:
        root = "other"
        try:
            out = rag.suggest(client, f"{a['name']}. {a['description']}", root, "see name", coll, embed_fn)
            a["regulations"] = out["suggestions"]
        except Exception as e:  # an LLM hiccup must not stop alert generation
            log.warning("regulation suggestion failed for %s: %s", a["name"], str(e)[:100])


def _has_triage(con):
    return con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'complaint_triage'").fetchone()[0] > 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    for noisy in ("httpx", "google_genai", "httpcore", "presidio-analyzer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    con = connect()
    if cmd == "build":
        from src.ai.llm import get_aux_client as get_client
        n = prepare_embeddings(con, collection("complaints"))
        log.info("newly embedded %d complaints; clustered %d", n, cluster(con, collection("complaints")))
        name_clusters(con, get_client())
    elif cmd == "alerts":
        from src.ai.llm import get_aux_client as get_client
        n, last = build_alerts(con, get_client(), collection("regulations"))
        log.info("%d alerts written (latest complete month %s)", n, last)
    else:
        raise SystemExit(__doc__)
    con.close()
