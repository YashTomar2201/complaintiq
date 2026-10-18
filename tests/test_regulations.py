import hashlib
import json
import uuid

import numpy as np
import pytest

from src.ai import regulations_rag as rag
from src.ai.llm import LLMResult
from src.ingest.regulations import chunk, keep_section, parse_part

XML = """<DIV5 N="1005" TYPE="PART">
 <DIV8 N="1005.11" TYPE="SECTION"><HEAD>&#167; 1005.11 Procedures for resolving errors.</HEAD>
   <P>(a) Definition of error. An error means an unauthorized electronic fund transfer.</P><P>(b) Notice of error from consumer.</P></DIV8>
 <DIV8 N="1005.3" TYPE="SECTION"><HEAD>&#167; 1005.3 Coverage.</HEAD><P>This part applies to financial institutions.</P></DIV8>
 <DIV8 N="1026.44-1026.50" TYPE="SECTION"><HEAD>&#167;&#167; 1026.44-1026.50 [Reserved]</HEAD><P>x</P></DIV8>
</DIV5>"""


def fake_embed(texts):
    """Deterministic bag-of-words vectors: texts that share words are close. Needs no model download."""
    out = []
    for t in texts:
        v = np.zeros(64)
        for w in t.lower().replace(":", " ").split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1
        out.append((v / (np.linalg.norm(v) or 1)).tolist())
    return out


@pytest.fixture
def coll(tmp_path, monkeypatch):
    import chromadb
    c = chromadb.EphemeralClient().get_or_create_collection(f"t{uuid.uuid4().hex}", metadata={"hnsw:space": "cosine"})
    secs = [("1005.11", "Procedures for resolving errors", "unauthorized electronic fund transfer error resolution investigate"),
            ("1026.13", "Billing error resolution", "credit card billing error duplicate charge statement dispute"),
            ("1006.6", "Communications in connection with debt collection", "debt collector calls harassment communication"),
            ("1022.43", "Direct disputes", "credit report dispute furnisher accuracy"),
            ("1026.52", "Limitations on fees", "credit card late fee penalty limit")]
    c.upsert(ids=[f"{s}#0" for s, _, _ in secs], documents=[f"{s} {t}: {x}" for s, t, x in secs], embeddings=fake_embed([x for _, _, x in secs]),
             metadatas=[dict(section=s, part=int(s[:4]), regulation="Reg", title=t, citation=f"12 CFR {s}", chunk=0) for s, t, _ in secs])
    return c


def test_parse_keeps_sections_and_skips_reserved(tmp_path):
    p = tmp_path / "p.xml"
    p.write_text(XML, encoding="utf-8")
    secs = parse_part(p, 1005)
    assert [s["section"] for s in secs] == ["1005.11", "1005.3"]
    assert secs[0]["title"] == "Procedures for resolving errors" and "unauthorized electronic fund transfer" in secs[0]["text"]
    assert secs[0]["citation"] == "12 CFR 1005.11"


def test_regulation_z_subset_and_chunking():
    assert keep_section(1026, "1026.13") and keep_section(1026, "1026.52")
    assert not keep_section(1026, "1026.35") and not keep_section(1026, "1026.44-1026.50")
    pieces = chunk(dict(section="1005.6", title="Liability", text="word " * 1000), max_chars=500)
    assert len(pieces) > 5 and all(p.startswith("1005.6 Liability: ") for p in pieces)


def test_retrieval_returns_distinct_relevant_sections(coll):
    out = rag.retrieve("credit card duplicate charge billing error", k=3, coll=coll, embed_fn=fake_embed)
    assert out[0]["section"] == "1026.13" and len({s["section"] for s in out}) == len(out)


def test_invented_citations_are_rejected(coll):
    retrieved = rag.retrieve("unauthorized transfer error", k=3, coll=coll, embed_fn=fake_embed)
    picks = [rag.SectionPick(section="12 CFR 1005.11(b)", explanation="Real and retrieved. Relevant."),
             rag.SectionPick(section="1005.99", explanation="Invented."),
             rag.SectionPick(section="Regulation E", explanation="No section number."),
             rag.SectionPick(section="1005.11", explanation="Duplicate of the first.")]
    accepted, rejected = rag.check_citations(picks, retrieved)
    assert [a["section"] for a in accepted] == ["1005.11"]
    assert accepted[0]["title"] == "Procedures for resolving errors" and accepted[0]["quoted_text"]  # text comes from OUR store
    assert rejected == ["1005.99", "Regulation E"]


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def complete(self, system, user, schema):
        self.prompts.append(user)
        return LLMResult(json.dumps(self.reply), 50, 20)


def test_suggest_end_to_end_blocks_hallucinations_and_shows_disclaimer(coll):
    llm = FakeLLM({"sections": [{"section": "1026.13", "explanation": "Billing errors. Fits."}, {"section": "1026.99", "explanation": "Made up."}]})
    out = rag.suggest(llm, "Charged twice on credit card statement", "billing_error", "Credit card", coll, fake_embed)
    assert [s["section"] for s in out["suggestions"]] == ["1026.13"] and out["rejected"] == ["1026.99"]
    assert out["disclaimer"] == "Suggestion for compliance review - not legal advice."
    assert "SECTION 1026.13" in llm.prompts[0] and "Charged twice" in llm.prompts[0]


def test_none_apply_gives_empty_list(coll):
    out = rag.suggest(FakeLLM({"sections": []}), "Rude agent", "customer_service", "Credit card", coll, fake_embed)
    assert out["suggestions"] == [] and out["rejected"] == []
