"""Score the AI triage against YOUR hand labels (evals/gold_labels.csv).

  python -m evals.run_eval v1                 # report for one prompt version
  python -m evals.run_eval v1 v2              # side-by-side comparison table
  python -m evals.run_eval v1 --errors 15     # also list the 15 worst mistakes
  python -m evals.run_eval v1 --subset 30     # only the first 30 gold complaints (fast check used in CI)
  python -m evals.run_eval v1 v2 --positions 51-100   # only gold complaints 51-100

Metrics: root cause accuracy + per-category precision/recall + confusion matrix; severity exact / within +-1 /
missed critical (human 5); vulnerable-consumer precision/recall.
"""
import json
import sys

import duckdb
import pandas as pd
from sklearn.metrics import precision_recall_fscore_support

from evals.gold import GOLD_SET, load_labels
from src.ai.schema import ROOT_CAUSES
from src.ingest.cfpb import DB_PATH, ROOT

RESULTS_DIR = ROOT / "evals" / "results"


def load_joined(version, subset=None, con=None, positions=None):
    """Human labels joined with the AI answer for `version` (only AI answers with status ok)."""
    labels = pd.DataFrame(load_labels().values())
    if labels.empty:
        raise SystemExit("No labels yet: run the labeling page first (streamlit run evals/label_app.py).")
    labels["severity"] = labels.severity.astype(int)
    labels["vulnerable_consumer"] = labels.vulnerable_consumer.astype(str) == "True"
    order = pd.read_csv(GOLD_SET, dtype=str)
    if subset:
        order = order.head(subset)
    if positions:  # (low, high), inclusive, e.g. (51, 100)
        order = order[order.position.astype(int).between(*positions)]
    labels = labels[labels.complaint_id.isin(order.complaint_id)]
    own = con is None
    con = con or duckdb.connect(str(DB_PATH), read_only=True)
    ai = con.execute("""SELECT complaint_id, root_cause AS ai_root_cause, severity AS ai_severity,
                               vulnerable_consumer AS ai_vulnerable, confidence, summary
                        FROM complaint_triage WHERE prompt_version = $v AND status = 'ok'""", {"v": version}).df()
    if own:
        con.close()
    df = labels.merge(ai, on="complaint_id", how="left")
    return df, int(df.ai_root_cause.isna().sum())


def compute(df):
    """df: rows with both a human label and an AI answer. Returns a dict of metrics."""
    n = len(df)
    h, a = df.root_cause, df.ai_root_cause
    cats = [c for c in ROOT_CAUSES if c in set(h) | set(a)]
    p, r, _, sup = precision_recall_fscore_support(h, a, labels=cats, zero_division=0)
    per_cat = {c: dict(precision=round(float(pi), 2), recall=round(float(ri), 2), human_count=int(si))
               for c, pi, ri, si in zip(cats, p, r, sup)}
    diff = (df.severity - df.ai_severity).abs()
    crit = df[df.severity == 5]
    high = df[df.severity >= 4]
    hv, av = df.vulnerable_consumer, df.ai_vulnerable.astype(bool)
    tp, fp, fn = int((hv & av).sum()), int((~hv & av).sum()), int((hv & ~av).sum())
    return {
        "n": n,
        "root_cause_accuracy": round(100 * float((h == a).mean()), 1),
        "root_cause_per_category": per_cat,
        "severity_exact": round(100 * float((diff == 0).mean()), 1),
        "severity_within_1": round(100 * float((diff <= 1).mean()), 1),
        "severity_mean_abs_error": round(float(diff.mean()), 2),
        "critical_human_5": len(crit),
        "critical_missed_ai_le3": int((crit.ai_severity <= 3).sum()),
        "high_human_ge4": len(high),
        "high_recall_ai_ge4": round(100 * float((high.ai_severity >= 4).mean()), 1) if len(high) else None,
        "vulnerable_human_yes": int(hv.sum()), "vulnerable_ai_yes": int(av.sum()),
        "vulnerable_precision": round(100 * tp / (tp + fp), 1) if tp + fp else None,
        "vulnerable_recall": round(100 * tp / (tp + fn), 1) if tp + fn else None,
        "vulnerable_false_pos": fp, "vulnerable_false_neg": fn,
    }


def confusion(df):
    cats = [c for c in ROOT_CAUSES if c in set(df.root_cause) | set(df.ai_root_cause)]
    return pd.crosstab(df.root_cause, df.ai_root_cause).reindex(index=cats, columns=cats, fill_value=0)


def worst_errors(df, k=15):
    """Biggest severity gaps first, then wrong root cause, then wrong vulnerable flag."""
    d = df.copy()
    d["sev_gap"] = (d.severity - d.ai_severity).abs()
    d["score"] = d.sev_gap * 2 + (d.root_cause != d.ai_root_cause) * 2 + (d.vulnerable_consumer != d.ai_vulnerable.astype(bool))
    return d[d.score > 0].sort_values("score", ascending=False).head(k)


def report(version, subset=None, errors=0, positions=None):
    df, missing = load_joined(version, subset, positions=positions)
    done = df.dropna(subset=["ai_root_cause"])
    if done.empty:
        raise SystemExit(f"No AI answers for {version} on your labeled complaints. Run: python -m src.ai.triage run {version} --gold")
    m = compute(done)
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"{version}.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    print(f"== {version}: {m['n']} labeled complaints scored ({missing} labeled but not yet triaged)")
    print(f"Root cause accuracy {m['root_cause_accuracy']}%")
    print(f"Severity: exact {m['severity_exact']}% | within +-1 {m['severity_within_1']}% | mean abs error {m['severity_mean_abs_error']}")
    print(f"Critical (human severity 5): {m['critical_human_5']}, AI rated <=3 on {m['critical_missed_ai_le3']} of them (missed); "
          f"human severity >=4 found at >=4: {m['high_recall_ai_ge4']}%")
    print(f"Vulnerable: human yes {m['vulnerable_human_yes']}, AI yes {m['vulnerable_ai_yes']} | precision {m['vulnerable_precision']}% "
          f"recall {m['vulnerable_recall']}% | false positives {m['vulnerable_false_pos']}, false negatives {m['vulnerable_false_neg']}")
    print("Per category (precision / recall / human count):")
    for c, v in m["root_cause_per_category"].items():
        print(f"  {c:26s} {v['precision']:.2f} / {v['recall']:.2f} / {v['human_count']}")
    print("Confusion matrix (rows = your label, columns = AI):")
    print(confusion(done).to_string())
    if errors:
        print(f"\nWorst {errors} mistakes:")
        for r in worst_errors(done, errors).itertuples():
            print(f"- {r.complaint_id}: you {r.root_cause}/sev {r.severity}/vuln {r.vulnerable_consumer} | "
                  f"AI {r.ai_root_cause}/sev {r.ai_severity}/vuln {bool(r.ai_vulnerable)} | {str(r.summary)[:110]}")


def compare(v1, v2, subset=None, positions=None):
    a, b = (compute(load_joined(v, subset, positions=positions)[0].dropna(subset=["ai_root_cause"])) for v in (v1, v2))
    rows = [("Complaints scored", "n"), ("Root cause accuracy %", "root_cause_accuracy"), ("Severity exact %", "severity_exact"),
            ("Severity within +-1 %", "severity_within_1"), ("Severity mean abs error", "severity_mean_abs_error"),
            ("Critical (human 5) missed", "critical_missed_ai_le3"), ("Vulnerable precision %", "vulnerable_precision"),
            ("Vulnerable recall %", "vulnerable_recall"), ("Vulnerable false positives", "vulnerable_false_pos")]
    print(f"{'metric':28s}{v1:>10s}{v2:>10s}")
    for label, key in rows:
        print(f"{label:28s}{a[key]!s:>10s}{b[key]!s:>10s}")
    print("per-category recall:")
    for c in sorted(set(a["root_cause_per_category"]) | set(b["root_cause_per_category"])):
        ra = a["root_cause_per_category"].get(c, {}).get("recall", "-")
        rb = b["root_cause_per_category"].get(c, {}).get("recall", "-")
        print(f"  {c:26s}{ra!s:>10s}{rb!s:>10s}")


if __name__ == "__main__":
    args = sys.argv[1:]
    subset = int(args[args.index("--subset") + 1]) if "--subset" in args else None
    errors = int(args[args.index("--errors") + 1]) if "--errors" in args else 0
    positions = tuple(int(x) for x in args[args.index("--positions") + 1].split("-")) if "--positions" in args else None
    versions = [x for x in args if x.startswith("v") and x[1:].isdigit()]
    if len(versions) == 2:
        compare(versions[0], versions[1], subset, positions)
    elif len(versions) == 1:
        report(versions[0], subset, errors, positions)
    else:
        raise SystemExit(__doc__)
