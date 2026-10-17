"""Labeling page for the gold set. YOU label each complaint; the AI's answer is never shown here.

Run:  streamlit run evals/label_app.py
Labels are saved to evals/gold_labels.csv after every click, so you can stop and continue any time.
"""
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `src` and `evals` import when run by streamlit

import pandas as pd
import streamlit as st

from evals.gold import GOLD_SET, GOLD_TEXTS, load_labels, save_label
from src.ai.schema import ROOT_CAUSE_HELP, SEVERITY_HELP, VULNERABLE_HELP

st.set_page_config(page_title="Label complaints", page_icon=":material/edit_note:", layout="wide")

if not GOLD_SET.exists() or not GOLD_TEXTS.exists():
    st.error("Gold set not found. Run: python -m evals.gold")
    st.stop()

gold = pd.read_csv(GOLD_SET, dtype=str)
texts = json.loads(GOLD_TEXTS.read_text(encoding="utf-8"))
labels = load_labels()
total = len(gold)

# ---- which complaint are we on? start at the first one without a label
if "pos" not in st.session_state:
    done = set(labels)
    st.session_state.pos = next((i for i, c in enumerate(gold.complaint_id) if c not in done), 0)
pos = min(max(st.session_state.pos, 0), total - 1)


def go(i):
    st.session_state.pos = i


# ---- sidebar: progress + rubric (the same definitions the AI is given)
with st.sidebar:
    st.header("Progress")
    st.progress(len(labels) / total, text=f"{len(labels)} of {total} labeled")
    unlabeled = [i for i, c in enumerate(gold.complaint_id) if c not in labels]
    st.button("Go to next unlabeled", on_click=lambda: go(unlabeled[0]), disabled=not unlabeled)
    st.session_state.jump = pos  # keep the dropdown in step with Previous/Next/Save
    st.selectbox("Jump to complaint", range(total), format_func=lambda i: f"{i + 1}" + ("  (done)" if gold.complaint_id[i] in labels else ""),
                 key="jump", on_change=lambda: go(st.session_state.jump))
    st.divider()
    st.caption("Label from your own reading of the complaint. Do not ask an AI: the test is only meaningful if the answers are yours.")

cid = gold.complaint_id[pos]
item = texts[cid]
existing = labels.get(cid)

st.title(f"Complaint {pos + 1} of {total}")
if len(labels) == total:
    st.success("All 100 complaints are labeled. Tell Claude you are done.")

left, right = st.columns([5, 6], gap="large")

with left:
    st.markdown(f"**Product:** {item['product']}")
    st.markdown(f"**Issue the consumer chose:** {item['issue']}")
    with st.container(border=True):
        # plain escaped text: st.write/markdown would read "$...$" in {$92.00} as maths and colour the text
        st.html(f'<div style="white-space: pre-wrap; line-height: 1.5">{html.escape(item["text"])}</div>')
    st.caption("Text is masked (XXXX and <PERSON> are privacy masks). Dollar amounts look like {$123.45}.")

with right:
    st.subheader("Your label")
    root_options = list(ROOT_CAUSE_HELP)
    with st.form(key=f"form_{cid}"):
        root = st.radio("Root cause: what went wrong, in one category", root_options, key=f"rc_{cid}",
                        index=root_options.index(existing["root_cause"]) if existing else None,
                        format_func=lambda k: f"{k}  ({ROOT_CAUSE_HELP[k]})")
        sev = st.radio("Severity (pick the HIGHEST level that applies)", [5, 4, 3, 2, 1], key=f"sev_{cid}",
                       index=[5, 4, 3, 2, 1].index(int(existing["severity"])) if existing else None,
                       format_func=lambda k: f"{k}  ({SEVERITY_HELP[k]})")
        st.caption(f"Vulnerable consumer = {VULNERABLE_HELP}.")
        vul = st.radio("Vulnerable consumer?", ["No", "Yes"], key=f"vul_{cid}", horizontal=True,
                       index=(1 if existing["vulnerable_consumer"] == "True" else 0) if existing else None)
        notes = st.text_input("Notes (optional)", value=existing["notes"] if existing else "", key=f"notes_{cid}")
        saved = st.form_submit_button("Save and next", type="primary")
    if saved:
        if root is None or sev is None or vul is None:
            st.warning("Please answer all three questions.")
        else:
            save_label(cid, root, sev, vul == "Yes", notes)
            go(min(pos + 1, total - 1))
            st.rerun()

    nav1, nav2, _ = st.columns([1, 1, 3])
    nav1.button("Previous", on_click=lambda: go(pos - 1), disabled=pos == 0)
    nav2.button("Skip", on_click=lambda: go(pos + 1), disabled=pos == total - 1)
    if existing:
        st.caption(f"Saved earlier: {existing['root_cause']}, severity {existing['severity']}, "
                   f"vulnerable {existing['vulnerable_consumer']}.")
