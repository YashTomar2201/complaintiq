"""Read-only database access for the Streamlit app, with caching."""
import re

import duckdb
import streamlit as st

from src.ingest.cfpb import DB_PATH


@st.cache_resource
def connection():
    # read_only: the app can never change the data
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(show_spinner=False)
def query(sql, params=None):
    """Run SQL (named parameters like $start) and return a DataFrame. Results are cached."""
    return run_sql(connection(), sql, params)


def run_sql(con, sql, params=None):
    """DuckDB rejects named parameters a query does not use, so pass only the ones it references."""
    used = set(re.findall(r"\$(\w+)", sql))
    return con.execute(sql, {k: v for k, v in (params or {}).items() if k in used}).df()
