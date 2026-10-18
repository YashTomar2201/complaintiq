import pandas as pd

from src.ai.clusters import detect_growth


def counts(**series):
    rows = []
    for key, vals in series.items():
        for i, n in enumerate(vals):
            rows.append(dict(key=key, year_month=str(pd.Period("2025-01", "M") + i), n=n))
    return pd.DataFrame(rows)


def test_spike_is_flagged_with_growth():
    out = detect_growth(counts(a=[5, 5, 5, 30]))
    assert len(out) == 1 and out.iloc[0].year_month == "2025-04" and out.iloc[0].growth_pct == 500


def test_needs_both_doubling_and_minimum_count():
    assert detect_growth(counts(a=[1, 1, 1, 3])).empty          # 3x growth but only 3 complaints: noise
    assert detect_growth(counts(a=[20, 20, 20, 25])).empty      # 25 complaints but not 2x
    assert len(detect_growth(counts(a=[20, 20, 20, 40]))) == 1  # exactly 2x and >= 10


def test_too_little_history_and_missing_months():
    assert detect_growth(counts(a=[1, 50, 50])).empty           # fewer than 3 earlier months: skipped
    gap = counts(a=[10, 10, 10, 10]).drop(index=[1, 2])         # months 2 and 3 missing = zero complaints
    assert len(detect_growth(gap)) == 1                         # 10 now vs average 3.3 before


def test_each_group_is_judged_separately():
    out = detect_growth(counts(spiking=[4, 4, 4, 40], steady=[30, 30, 30, 31]))
    assert list(out.key) == ["spiking"]
