import pandas as pd

from evals.gold import load_labels, save_label
from evals.run_eval import compute, confusion, worst_errors
from src.ai.schema import ROOT_CAUSE_HELP, ROOT_CAUSES, SEVERITY_HELP, VULNERABLE_HELP


def test_labels_are_saved_and_replaced(tmp_path):
    path = tmp_path / "labels.csv"
    save_label("1", "billing_error", 3, False, path=path)
    save_label("2", "fraud_scam", 5, True, "unclear", path=path)
    save_label("1", "fees_interest", 2, False, path=path)  # editing an earlier label replaces it
    labels = load_labels(path)
    assert len(labels) == 2
    assert labels["1"]["root_cause"] == "fees_interest" and labels["1"]["severity"] == "2"
    assert labels["2"]["vulnerable_consumer"] == "True" and labels["2"]["notes"] == "unclear"


def make_df():
    return pd.DataFrame({
        "complaint_id": list("abcd"),
        "root_cause": ["billing_error", "billing_error", "fraud_scam", "other"],
        "ai_root_cause": ["billing_error", "fees_interest", "fraud_scam", "other"],
        "severity": [5, 3, 4, 1], "ai_severity": [3, 3, 5, 1],      # human 5 missed (AI 3); gaps 2, 0, 1, 0
        "vulnerable_consumer": [True, False, False, False], "ai_vulnerable": [False, False, True, False],
        "summary": ["s"] * 4})


def test_metrics_on_a_tiny_known_example():
    m = compute(make_df())
    assert m["root_cause_accuracy"] == 75.0
    assert m["severity_exact"] == 50.0 and m["severity_within_1"] == 75.0 and m["severity_mean_abs_error"] == 0.75
    assert m["critical_human_5"] == 1 and m["critical_missed_ai_le3"] == 1
    assert m["vulnerable_precision"] == 0.0 and m["vulnerable_recall"] == 0.0
    assert m["vulnerable_false_pos"] == 1 and m["vulnerable_false_neg"] == 1
    assert m["root_cause_per_category"]["billing_error"] == {"precision": 1.0, "recall": 0.5, "human_count": 2}


def test_confusion_matrix_and_worst_errors():
    cm = confusion(make_df())
    assert cm.loc["billing_error", "fees_interest"] == 1 and cm.loc["billing_error", "billing_error"] == 1
    worst = worst_errors(make_df(), 2)
    assert list(worst.complaint_id) == ["a", "b"] or list(worst.complaint_id)[0] == "a"  # the severity-5 miss ranks first


def test_human_rubric_matches_prompt_v1():
    """The labeling page shows the human the same definitions the AI was given."""
    prompt = open("prompts/triage_v1.txt", encoding="utf-8").read()
    assert set(ROOT_CAUSE_HELP) == set(ROOT_CAUSES)
    for text in list(ROOT_CAUSE_HELP.values()) + list(SEVERITY_HELP.values()) + [VULNERABLE_HELP]:
        assert text in prompt, text
