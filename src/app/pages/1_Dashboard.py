"""Analytics dashboard. Every number comes from the SQL view v_dashboard_facts (defined in models.sql)."""
import plotly.express as px
import streamlit as st

from src.app.db import query
import pandas as pd

from src.app.insights import WHERE, compute, last_complete_month

st.set_page_config(page_title="Dashboard | ComplaintIQ", page_icon=":material/dashboard:", layout="wide")

# ---- chart styling: validated categorical palette, one fixed colour per product (colour follows the entity)
PRODUCT_COLORS = {
    "Credit card": "#2a78d6", "Credit reporting or other personal consumer reports": "#eb6834",
    "Checking or savings account": "#1baf7a", "Debt collection": "#eda100",
    "Vehicle loan or lease": "#e87ba4", "Other": "#898781",
}
BLUE, INK, MUTED, GRID = "#2a78d6", "#0b0b0b", "#898781", "#e1e0d9"
BLUE_RAMP = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]  # sequential, light = few, dark = many


def style(fig, height=330):
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color=INK, size=12),
                      legend=dict(orientation="h", y=-0.2, title=None))
    fig.update_xaxes(showgrid=False, linecolor=GRID, title=None)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, title=None)
    return fig


# ---- sidebar filters
bounds = query("SELECT min(date_received) AS lo, max(date_received) AS hi FROM v_dashboard_facts").iloc[0]
lo, hi = bounds.lo.date(), bounds.hi.date()
all_products = query("SELECT product FROM v_dashboard_facts GROUP BY 1 ORDER BY sum(complaints) DESC")["product"].tolist()
all_states = query("SELECT DISTINCT state FROM v_dashboard_facts ORDER BY 1")["state"].tolist()

st.sidebar.header("Filters")
picked = st.sidebar.date_input("Date received", value=(lo, hi), min_value=lo, max_value=hi)
products = st.sidebar.multiselect("Product", all_products, default=all_products)
states = st.sidebar.multiselect("State", all_states, default=all_states)

if not (isinstance(picked, tuple) and len(picked) == 2):
    st.info("Pick an end date to continue.")
    st.stop()
f = {"start": picked[0], "end": picked[1], "products": products or all_products, "states": states or all_states}

# the latest month is only partly in the data; monthly trend lines stop at the last complete month
f["last_ok"] = last_complete_month(min(pd.Timestamp(f["end"]), pd.Timestamp(hi))).date()
COMPLETE = "year_month <= strftime($last_ok, '%Y-%m')"

st.title("Complaint dashboard")
st.caption(f"Capital One complaints received {picked[0]:%d %b %Y} to {picked[1]:%d %b %Y}. "
           f"Data runs to {hi:%d %b %Y}; the partial latest month is left out of the monthly trend charts.")

# ---- KPI cards
k = query(f"""SELECT sum(complaints) AS total, sum(with_narrative) AS narr, sum(timely_complaints) AS timely,
                     sum(final_responses) AS final, sum(monetary_relief) AS relief
              FROM v_dashboard_facts WHERE {WHERE}""", f).iloc[0]
if not k.total:
    st.warning("No complaints match these filters.")
    st.stop()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total complaints", f"{int(k.total):,}")
c2.metric("With a narrative", f"{100 * k.narr / k.total:.1f}%", help="Share of complaints where the consumer's story is available. "
          "The CFPB stopped publishing narratives in Aug 2026, so recent months are lower.")
c3.metric("Responded on time", f"{100 * k.timely / k.total:.3f}%", help="Almost always ~100%, so it barely moves; "
          "the other numbers are more informative.")
c4.metric("Closed with monetary relief", f"{100 * k.relief / k.final:.1f}%" if k.final else "n/a",
          help="Of complaints with a final response (excludes 'In progress').")

# ---- insights (SQL comparisons, not AI)
with st.container(border=True):
    st.markdown("**Insights**")
    for text in compute(query, f, hi):
        st.markdown(f"- {text}")

# ---- charts
left, right = st.columns(2)

with left:
    st.subheader("Complaints per month")
    df = query(f"""WITH top AS (SELECT product FROM v_dashboard_facts WHERE {WHERE} GROUP BY 1 ORDER BY sum(complaints) DESC LIMIT 5)
                   SELECT year_month, CASE WHEN product IN (SELECT product FROM top) THEN product ELSE 'Other' END AS product,
                          sum(complaints) AS complaints
                   FROM v_dashboard_facts WHERE {WHERE} AND {COMPLETE} GROUP BY ALL ORDER BY year_month""", f)
    fig = px.line(df, x="year_month", y="complaints", color="product", color_discrete_map=PRODUCT_COLORS)
    fig.update_traces(line_width=2)
    st.plotly_chart(style(fig), use_container_width=True)
    st.caption("Spikes are real events (e.g. Jan 2025). Complete months only.")

with right:
    st.subheader("Top 10 issues")
    df = query(f"""SELECT issue, sum(complaints) AS complaints FROM v_dashboard_facts WHERE {WHERE}
                   GROUP BY 1 ORDER BY 2 DESC LIMIT 10""", f).iloc[::-1]
    fig = px.bar(df, x="complaints", y="issue", orientation="h", color_discrete_sequence=[BLUE])
    fig.update_traces(marker_cornerradius=4)
    st.plotly_chart(style(fig), use_container_width=True)

left, right = st.columns(2)

with left:
    st.subheader("Complaints by state")
    df = query(f"""SELECT state, sum(complaints) AS complaints FROM v_dashboard_facts WHERE {WHERE}
                   AND state <> 'Unknown' GROUP BY 1""", f)
    fig = px.choropleth(df, locations="state", locationmode="USA-states", scope="usa", color="complaints",
                        color_continuous_scale=BLUE_RAMP)
    fig.update_layout(coloraxis_colorbar=dict(title=None, thickness=10))
    fig.update_geos(showlakes=False, bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(style(fig), use_container_width=True)
    st.caption("Counts follow population: big states have more complaints. Territories are not drawn.")

with right:
    st.subheader("On-time response % by month")
    df = query(f"""SELECT year_month, 100.0 * sum(timely_complaints) / sum(complaints) AS pct
                   FROM v_dashboard_facts WHERE {WHERE} AND {COMPLETE} GROUP BY 1 ORDER BY 1""", f)
    fig = px.line(df, x="year_month", y="pct", color_discrete_sequence=[BLUE])
    fig.update_traces(line_width=2)
    fig.update_yaxes(range=[98, 100.2], ticksuffix="%")
    st.plotly_chart(style(fig), use_container_width=True)
    st.caption("The axis starts at 98% to show the few late responses; the rate is ~100% every month.")

st.subheader("How the company responded")
df = query(f"""SELECT company_response, sum(complaints) AS complaints FROM v_dashboard_facts WHERE {WHERE}
               GROUP BY 1 ORDER BY 2 DESC""", f)
fig = px.bar(df, x="company_response", y="complaints", color_discrete_sequence=[BLUE])
fig.update_traces(marker_cornerradius=4)
st.plotly_chart(style(fig, 280), use_container_width=True)
