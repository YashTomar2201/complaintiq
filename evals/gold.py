"""The gold set: 100 complaints that a HUMAN labels. The AI never labels these (that would make the test meaningless).

  python -m evals.gold            # choose the 100 complaints once (refuses to overwrite: labels would no longer match)

Files:
  evals/gold_set.csv      the chosen complaint ids (position = order shown on the labeling page)
  evals/gold_labels.csv   YOUR labels (written by the labeling page)
  data/gold_texts.json    the masked narratives shown to you (gitignored, no database lock needed while labeling)
"""
import csv
import json
import random
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from src.ai.triage import prepare_text
from src.ingest.cfpb import DB_PATH, ROOT

GOLD_SET = ROOT / "evals" / "gold_set.csv"
GOLD_LABELS = ROOT / "evals" / "gold_labels.csv"
GOLD_TEXTS = ROOT / "data" / "gold_texts.json"
SEED = 7
# 100 complaints spread over the main products, so accuracy is not just "credit card accuracy"
QUOTAS = {"Credit card": 30, "Checking or savings account": 25,
          "Credit reporting or other personal consumer reports": 20, "Debt collection": 12,
          "Vehicle loan or lease": 8, "Money transfer, virtual currency, or money service": 5}
LABEL_COLUMNS = ["complaint_id", "root_cause", "severity", "vulnerable_consumer", "notes", "labeled_at"]


def make_gold(force=False):
    if GOLD_SET.exists() and not force:
        raise SystemExit(f"{GOLD_SET} already exists. Changing the gold set would orphan your labels (use --force to redo).")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    # from the saved triage sample, narratives only, first copy of duplicated texts, a length a human can read
    df = con.execute("""SELECT complaint_id, product, issue, narrative FROM triage_sample s JOIN complaints c USING (complaint_id)
                        WHERE c.has_narrative AND c.is_first_copy AND length(c.narrative) BETWEEN 60 AND 4000""").df()
    con.close()
    picked = [g.sample(min(len(g), QUOTAS[p]), random_state=SEED) for p, g in df.groupby("product") if p in QUOTAS]
    gold = pd.concat(picked).sample(frac=1, random_state=SEED).reset_index(drop=True)  # shuffled across products
    gold.insert(0, "position", range(1, len(gold) + 1))
    texts = {}
    for r in gold.itertuples():
        masked, _ = prepare_text(r.narrative)  # the exact text the AI will see
        texts[r.complaint_id] = {"product": r.product, "issue": r.issue, "text": masked}
    GOLD_TEXTS.parent.mkdir(exist_ok=True)
    GOLD_TEXTS.write_text(json.dumps(texts), encoding="utf-8")
    gold[["position", "complaint_id", "product"]].to_csv(GOLD_SET, index=False)
    return gold


# ---------- label storage ----------
def load_labels(path=GOLD_LABELS):
    if not Path(path).exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["complaint_id"]: r for r in csv.DictReader(f)}


def save_label(complaint_id, root_cause, severity, vulnerable, notes="", path=GOLD_LABELS):
    """Add or replace one label. The whole file is rewritten each time, so a refresh or crash loses nothing."""
    labels = load_labels(path)
    labels[complaint_id] = dict(complaint_id=complaint_id, root_cause=root_cause, severity=int(severity),
                                vulnerable_consumer=bool(vulnerable), notes=notes,
                                labeled_at=datetime.now().isoformat(timespec="seconds"))
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_COLUMNS)
        w.writeheader()
        w.writerows(labels.values())
    tmp.replace(path)


if __name__ == "__main__":
    import sys
    g = make_gold(force="--force" in sys.argv)
    print(f"gold set: {len(g)} complaints | " + "; ".join(f"{p[:22]} {n}" for p, n in g['product'].value_counts().items()))
