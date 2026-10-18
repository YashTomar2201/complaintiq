"""Regulation lookup (RAG = retrieve, then generate).

1. Index: every regulation section (split into chunks) is embedded and stored in ChromaDB.
2. Retrieve: for a complaint, search with its summary + root cause and take the 5 most similar sections.
3. Generate: the LLM is shown ONLY those 5 sections and asked which, if any, may be relevant.
4. Guardrail: code rejects any section the LLM cites that was not among the 5 retrieved (invented citations).
   The title, citation and quoted text shown to users come from our stored regulation text, never from the LLM.

Always shown with: "Suggestion for compliance review - not legal advice."

Usage: python -m src.ai.regulations_rag index
"""
import json
import logging
import re
import sys
from typing import List

from pydantic import BaseModel, Field

from src.ai.embeddings import collection, embed
from src.ingest.cfpb import ROOT
from src.ingest.regulations import PARTS, REG_DIR, chunk, parse_part

log = logging.getLogger("regulations_rag")
DISCLAIMER = "Suggestion for compliance review - not legal advice."
PROMPT_VERSION = "v1"
SECTION_ID = re.compile(r"\b(10\d\d\.\d+)\b")


class SectionPick(BaseModel):
    section: str = Field(description="section number exactly as listed, e.g. 1005.11")
    explanation: str = Field(description="two sentences: why this section may be relevant")


class RegSuggestion(BaseModel):
    sections: List[SectionPick] = Field(default_factory=list, max_length=3)


# ---------- index ----------
def index_regulations(coll=None, embed_fn=embed):
    coll = coll or collection("regulations")
    ids, docs, metas = [], [], []
    for part in PARTS:
        for s in parse_part(REG_DIR / f"part_{part}.xml", part):
            for i, piece in enumerate(chunk(s)):
                ids.append(f"{s['section']}#{i}")
                docs.append(piece)
                metas.append(dict(section=s["section"], part=part, regulation=s["regulation"], title=s["title"],
                                  citation=s["citation"], chunk=i))
    for lo in range(0, len(ids), 128):
        sl = slice(lo, lo + 128)
        coll.upsert(ids=ids[sl], documents=docs[sl], metadatas=metas[sl], embeddings=embed_fn(docs[sl]))
    return len(ids)


# ---------- retrieve ----------
def retrieve(query, k=5, coll=None, embed_fn=embed):
    """Top-k DIFFERENT sections (a long section may match with several chunks; keep its best one)."""
    coll = coll or collection("regulations")
    res = coll.query(query_embeddings=embed_fn([query]), n_results=k * 4)
    seen, out = set(), []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        if meta["section"] in seen:
            continue
        seen.add(meta["section"])
        out.append(dict(section=meta["section"], title=meta["title"], citation=meta["citation"],
                        regulation=meta["regulation"], excerpt=doc, similarity=round(1 - dist, 3)))
        if len(out) == k:
            break
    return out


# ---------- generate + guardrail ----------
def build_prompt(summary, root_cause, product, sections):
    block = "\n\n".join(f"SECTION {s['section']} ({s['regulation']}): {s['title']}\n{s['excerpt'][:900]}" for s in sections)
    template = (ROOT / "prompts" / f"regulations_{PROMPT_VERSION}.txt").read_text(encoding="utf-8")
    return (template.replace("{product}", str(product)).replace("{root_cause}", str(root_cause))
            .replace("{sections}", block).replace("{summary}", summary))


def check_citations(picks, retrieved):
    """Keep only picks whose section was actually retrieved. Returns (accepted list, rejected citation strings)."""
    by_id = {s["section"]: s for s in retrieved}
    accepted, rejected, used = [], [], set()
    for p in picks:
        m = SECTION_ID.search(p.section)
        sid = m.group(1) if m else None
        if sid in by_id and sid not in used:
            used.add(sid)
            s = by_id[sid]
            accepted.append(dict(section=sid, title=s["title"], citation=s["citation"], regulation=s["regulation"],
                                 explanation=p.explanation.strip(), quoted_text=s["excerpt"][:500]))
        elif sid not in by_id:
            rejected.append(p.section)  # invented or not retrieved: never shown
    return accepted, rejected


def suggest(client, summary, root_cause, product, coll=None, embed_fn=embed, k=5):
    retrieved = retrieve(f"{summary} {root_cause.replace('_', ' ')}", k, coll, embed_fn)
    res = client.complete("You help a compliance team. Answer only with JSON matching the schema.",
                          build_prompt(summary, root_cause, product, retrieved), RegSuggestion)
    try:
        picks = RegSuggestion.model_validate_json(res.text).sections
    except Exception:
        picks = []
    accepted, rejected = check_citations(picks, retrieved)
    return dict(suggestions=accepted, rejected=rejected, retrieved=[s["section"] for s in retrieved],
                disclaimer=DISCLAIMER, input_tokens=res.input_tokens, output_tokens=res.output_tokens)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    if sys.argv[1:] == ["index"]:
        log.info("indexed %d regulation chunks", index_regulations())
    else:
        raise SystemExit(__doc__)
