"""Plain-English insights computed with SQL comparisons (no AI: numbers must be exact and repeatable).

`run(sql, params)` returns a DataFrame; in the app it is the cached query helper, in tests a plain connection.
`f` holds the sidebar filters: start, end (dates), products, states (lists).
"""
import pandas as pd

WHERE = "date_received BETWEEN $start AND $end AND list_contains($products, product) AND list_contains($states, state)"
MIN_BASE = 100  # ignore products with fewer complaints than this in the earlier period (percentages would mislead)


def last_complete_month(end):
    """First day of the latest month fully covered by data ending on `end`."""
    end = pd.Timestamp(end)
    month_start = end.replace(day=1)
    is_month_end = end == end + pd.offsets.MonthEnd(0)
    return month_start if is_month_end else month_start - pd.DateOffset(months=1)


def trend_insight(run, f, data_end):
    """Biggest product change: last 3 complete months vs the 3 months before, plus the issue driving it."""
    m = last_complete_month(min(pd.Timestamp(f["end"]), pd.Timestamp(data_end)))
    cur_start, cur_end = m - pd.DateOffset(months=2), m + pd.offsets.MonthEnd(0)
    prev_start, prev_end = m - pd.DateOffset(months=5), m - pd.DateOffset(months=3) + pd.offsets.MonthEnd(0)
    if prev_start < pd.Timestamp(f["start"]):
        return "Not enough history in the selected dates to compare the last 3 months with the 3 before."
    p = {**f, "cs": cur_start.date(), "ce": cur_end.date(), "ps": prev_start.date(), "pe": prev_end.date()}
    period = """sum(complaints) FILTER (WHERE date_received BETWEEN $cs AND $ce) AS cur,
                sum(complaints) FILTER (WHERE date_received BETWEEN $ps AND $pe) AS prev"""
    prod = run(f"""SELECT product, {period} FROM v_dashboard_facts WHERE {WHERE} GROUP BY product
                   HAVING prev >= {MIN_BASE} ORDER BY abs(cur - prev) DESC LIMIT 1""", p)
    if prod.empty:
        return "No product has enough complaints in the earlier period to compare."
    r = prod.iloc[0]
    pct = 100 * (r.cur - r.prev) / r.prev
    verb = "rose" if r.cur >= r.prev else "fell"
    sign = 1 if r.cur >= r.prev else -1
    iss = run(f"""SELECT issue, {period} FROM v_dashboard_facts WHERE {WHERE} AND product = $prod GROUP BY issue
                  ORDER BY {sign} * (coalesce(sum(complaints) FILTER (WHERE date_received BETWEEN $cs AND $ce), 0)
                                   - coalesce(sum(complaints) FILTER (WHERE date_received BETWEEN $ps AND $pe), 0)) DESC
                  LIMIT 1""", {**p, "prod": r["product"]})
    driver = ""
    if not iss.empty:
        row = iss.iloc[0].fillna(0)  # an issue missing from one period has no sum there (NaN)
        d = int(row.cur - row.prev)
        driver = f", driven by '{iss.iloc[0].issue}' ({d:+,})"
    return (f"{r['product']} complaints {verb} {abs(pct):.0f}% ({int(r.prev):,} to {int(r.cur):,}) "
            f"in {cur_start:%b %Y}-{cur_end:%b %Y} vs the 3 months before{driver}.")


def peak_insight(run, f, data_end):
    """Busiest complete month vs the typical (median) month, and what drove it."""
    last_ok = last_complete_month(min(pd.Timestamp(f["end"]), pd.Timestamp(data_end)))
    p = {**f, "last_ok": last_ok.date()}
    months = run(f"""SELECT year_month, sum(complaints) AS n FROM v_dashboard_facts
                     WHERE {WHERE} AND year_month <= strftime($last_ok, '%Y-%m') GROUP BY 1 ORDER BY 1""", p)
    if len(months) < 3:
        return "Not enough complete months in the selected dates to find a peak."
    median = months.n.median()
    top = months.loc[months.n.idxmax()]
    issue = run(f"""SELECT issue, sum(complaints) AS n FROM v_dashboard_facts WHERE {WHERE} AND year_month = $m
                    GROUP BY 1 ORDER BY 2 DESC LIMIT 1""", {**f, "m": top.year_month}).iloc[0]
    label = pd.Timestamp(top.year_month + "-01").strftime("%B %Y")
    ratio = top.n / median
    if ratio < 1.5:
        return f"Volume is steady: the busiest month ({label}, {int(top.n):,}) is only {ratio:.1f}x the typical month ({int(median):,})."
    return (f"{label} was the busiest month: {int(top.n):,} complaints, {ratio:.1f}x the typical month ({int(median):,}). "
            f"Main issue: '{issue.issue}' ({int(issue.n):,}).")


def relief_insight(run, f):
    """Share of closed complaints that ended with monetary relief, overall and for the product with the highest rate."""
    tot = run(f"SELECT sum(monetary_relief) AS m, sum(final_responses) AS d FROM v_dashboard_facts WHERE {WHERE}", f).iloc[0]
    if not tot.d:
        return "No closed complaints in the selected filters."
    overall = 100 * tot.m / tot.d
    best = run(f"""SELECT product, 100.0 * sum(monetary_relief) / sum(final_responses) AS pct
                   FROM v_dashboard_facts WHERE {WHERE} GROUP BY product HAVING sum(final_responses) >= 200
                   ORDER BY pct DESC LIMIT 1""", f)
    text = f"{overall:.1f}% of closed complaints ended with monetary relief."
    if not best.empty and best.iloc[0].pct > overall * 1.2:
        text += f" Highest: {best.iloc[0]['product']} at {best.iloc[0].pct:.1f}%."
    return text


def compute(run, f, data_end):
    return [trend_insight(run, f, data_end), peak_insight(run, f, data_end), relief_insight(run, f)]
