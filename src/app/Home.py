"""ComplaintIQ entry page. Run with:  streamlit run src/app/Home.py"""
import streamlit as st

from src.app.db import query

st.set_page_config(page_title="ComplaintIQ", page_icon=":material/analytics:", layout="wide")

st.title("ComplaintIQ")
st.write("Complaint intelligence for a bank's complaints and compliance team, built on **real public CFPB complaint data** "
         "about Capital One.")
st.caption("Portfolio project. Not affiliated with Capital One or the CFPB.")

stats = query("""SELECT count(*) AS n, min(date_received) AS first_day, max(date_received) AS last_day,
                        count(*) FILTER (WHERE has_narrative) AS narratives
                 FROM complaints""").iloc[0]
c1, c2, c3 = st.columns(3)
c1.metric("Complaints loaded", f"{int(stats.n):,}")
c2.metric("Date range", f"{stats.first_day:%b %Y} to {stats.last_day:%b %Y}")
c3.metric("With a consumer narrative", f"{int(stats.narratives):,}")

st.subheader("Where to go")
st.page_link("pages/1_Dashboard.py", label="Dashboard: trends, issues, states and response rates",
             icon=":material/dashboard:")
st.write("More pages (triage queue, complaint detail, risk alerts) are added in later phases.")
