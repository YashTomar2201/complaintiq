"""Official regulation text (eCFR, 12 CFR Title 12) -> DuckDB table `regulation_sections`.

Four parts the complaints touch:
  1005 Regulation E (electronic fund transfers)   1006 Regulation F (debt collection)
  1022 Regulation V (FCRA, credit reports)        1026 Regulation Z (credit cards and loans)
Regulation Z is large and mostly about mortgages, so we keep Subpart A (general), Subpart B (open-end credit, which
holds the billing-error rule, section 1026.13) and Subpart G (special credit card rules, 1026.51-1026.60).

Usage: python -m src.ingest.regulations download   # fetch the four XML files (data/regulations/)
       python -m src.ingest.regulations load       # parse into DuckDB
"""
import logging
import re
import sys
import xml.etree.ElementTree as ET

from src.ingest.cfpb import ROOT, connect, request_with_retry

log = logging.getLogger("regulations")
REG_DIR = ROOT / "data" / "regulations"
AS_OF = "2026-10-05"   # eCFR issue date of the text we downloaded
URL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-12.xml?part={part}"
PARTS = {1005: "Regulation E (electronic fund transfers)", 1006: "Regulation F (debt collection)",
         1022: "Regulation V (FCRA, credit reports)", 1026: "Regulation Z (Truth in Lending)"}
SECTION_ID = re.compile(r"\b(10\d\d)\.(\d+)\b")


def keep_section(part, number):
    """Regulation Z: general rules, open-end credit and special credit card rules only."""
    if not re.fullmatch(r"\d{4}\.\d+", number):  # reserved ranges such as "1026.44-1026.50"
        return False
    if part != 1026:
        return True
    n = int(number.split(".")[1])
    return n <= 16 or 51 <= n <= 60


def download():
    REG_DIR.mkdir(parents=True, exist_ok=True)
    for part in PARTS:
        r = request_with_retry(URL.format(date=AS_OF, part=part), timeout=180)
        (REG_DIR / f"part_{part}.xml").write_bytes(r.content)
        log.info("part %d: %d KB", part, len(r.content) // 1024)


def parse_part(path, part):
    """Return one dict per section: number, title, text (headings and paragraphs, whitespace collapsed)."""
    root = ET.parse(path).getroot()
    out = []
    for el in root.iter():
        if el.attrib.get("TYPE") != "SECTION":
            continue
        number = el.attrib["N"]
        if not keep_section(part, number):
            continue
        head = " ".join("".join(el.find("HEAD").itertext()).split())
        title = re.sub(r"^\S*\s*" + re.escape(number) + r"\s*", "", head).rstrip(".")
        paras = ["".join(p.itertext()) for p in el.iter() if p.tag in ("P", "FP")]
        text = " ".join(" ".join(paras).split())
        if title and text:
            out.append(dict(section=number, part=part, regulation=PARTS[part], title=title,
                            citation=f"12 CFR {number}", text=text))
    return out


def chunk(section, max_chars=1800):
    """Split a long section into pieces (kept with its number and title) so each piece embeds well."""
    prefix = f"{section['section']} {section['title']}: "
    words, pieces, cur = section["text"].split(" "), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars and cur:
            pieces.append(cur)
            cur = ""
        cur = f"{cur} {w}".strip()
    if cur:
        pieces.append(cur)
    return [prefix + p for p in pieces]


def load():
    con = connect()
    con.execute("""CREATE OR REPLACE TABLE regulation_sections (
        section VARCHAR PRIMARY KEY, part INTEGER, regulation VARCHAR, title VARCHAR, citation VARCHAR,
        text VARCHAR, as_of VARCHAR)""")
    n = 0
    for part in PARTS:
        for s in parse_part(REG_DIR / f"part_{part}.xml", part):
            con.execute("INSERT OR REPLACE INTO regulation_sections VALUES (?,?,?,?,?,?,?)",
                        [s["section"], s["part"], s["regulation"], s["title"], s["citation"], s["text"], AS_OF])
            n += 1
    per = con.execute("SELECT part, count(*) FROM regulation_sections GROUP BY 1 ORDER BY 1").fetchall()
    log.info("loaded %d sections: %s", n, ", ".join(f"{p}: {c}" for p, c in per))
    con.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "download":
        download()
    elif cmd == "load":
        load()
    else:
        raise SystemExit(__doc__)
