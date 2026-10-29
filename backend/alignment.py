"""
How a summary relates to its source documents, measured in code (no LLM):

- alignment: each summary sentence -> the source block it comes from (section, page), how similar they are,
  the share of its words copied verbatim (shared runs of 4+ words), and whether its numbers are in the source
- coverage: which source sections the summary draws on and which it skips
- metrics: length, points per section, compression, verbatim share, bolding
- pairs: a few "source sentence -> summary sentence" examples showing how the writer rewrites

Used to learn from examples (knowledge.py) and to check a new draft against the learned targets.
"""
import math
import re
from collections import Counter

from . import citations, documents

ALIGN_VERSION = 1
MIN_SCORE = 1.2          # below this a sentence has no clear source (the writer's own addition)
_TOKEN = re.compile(r"\$?\d[\d,.]*%?x?|[a-z][a-z'’-]+", re.I)
_STOP = set("the a an and or of to in on for with by is are was were be been this that these its as at from which "
            "has have had it their than into while after before about over under per".split())
_MONTHS = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"


# ---------------------------------------------------------------- text helpers

def _tokens(text: str) -> list[str]:
    return [t.lower().rstrip(".,;:").replace(",", "") for t in _TOKEN.findall(text.replace("**", ""))]


def _content(text: str) -> list[str]:
    return [t for t in _tokens(text) if t not in _STOP and len(t) > 1]


def _words(text: str) -> int:
    return len(re.findall(r"[\w$%][\w.,%$'’-]*", re.sub(r"[#*`>|]", " ", text)))


def leaf(heading: str) -> str:
    return heading.split("›")[-1].strip() or "(no heading)"


def summary_points(md: str) -> list[dict]:
    """Bullets / paragraphs of a summary with the section (heading or bold-only line) they belong to."""
    md = citations.strip(md)
    points, section = [], ""
    for line in md.splitlines():
        t = line.strip()
        if not t or re.fullmatch(r"[-*_]{3,}", t):
            continue
        if t.startswith("#") or re.fullmatch(r"\*\*[^*]{1,80}\*\*:?", t):
            section = re.sub(r"[#*:]", "", t).strip()
            continue
        text = re.sub(r"^([-*•+]|\d+[.)])\s+", "", t)
        points.append({"section": section, "text": text, "bold": re.findall(r"\*\*([^*]+)\*\*", text)})
    return points


# ---------------------------------------------------------------- numbers (tolerant matching)

_SCALE = {"bn": 1e9, "billion": 1e9, "mm": 1e6, "m": 1e6, "million": 1e6, "k": 1e3, "": 1}
_NUM = re.compile(r"(?<![\w.])(?P<cur>\$)?(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<dec>\.\d+)?"
                  r"(?:\s?(?P<unit>%|x\b|bn\b|billion\b|mm\b|million\b|m\b|k\b))?(?![\w%])", re.I)


def numbers(text: str) -> list[dict]:
    out = []
    for m in _NUM.finditer(text.replace("**", "")):
        unit = (m.group("unit") or "").lower()
        num = float(m.group("num").replace(",", "") + (m.group("dec") or ""))
        dec = len(m.group("dec")) - 1 if m.group("dec") else 0
        if unit == "%":
            kind, scale = "pct", 1
        elif unit == "x":
            kind, scale = "mult", 1
        elif m.group("cur") or unit:
            kind, scale = "money", _SCALE.get(unit, 1)
        else:
            kind, scale = "plain", 1
        out.append({"raw": m.group(0).strip(), "kind": kind, "value": num * scale, "num": num, "scale": scale,
                    "decimals": dec})
    return out


def _same(s: dict, src: dict) -> bool:
    if s["kind"] != src["kind"] and "plain" not in (s["kind"], src["kind"]):
        return False
    if "plain" in (s["kind"], src["kind"]):
        return abs(s["num"] - src["num"]) < 1e-9
    return round(src["value"] / s["scale"], s["decimals"]) == round(s["num"], s["decimals"])   # $1.4bn ~ $1.42bn


def missing_numbers(text: str, source_text: str) -> list[str]:
    src = numbers(source_text)
    return [n["raw"] for n in numbers(text) if not any(_same(n, x) for x in src)]


# ---------------------------------------------------------------- alignment

class _Index:
    """Source blocks of several documents with IDF weights for matching summary sentences."""

    def __init__(self, docs: list[tuple[str, dict]]):
        self.blocks = []
        for label, doc in docs:
            for b in doc["blocks"]:
                if b.get("id") and b["text"].strip():
                    self.blocks.append({"label": label, "doc_id": doc["id"], "doc": doc["name"], "kind": doc["kind"],
                                        **b, "terms": set(_content(b["text"]))})
        df = Counter(t for b in self.blocks for t in b["terms"])
        n = len(self.blocks) or 1
        self.idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}

    def score(self, terms: set, block: dict) -> float:
        w = lambda t: self.idf.get(t, math.log(len(self.blocks) + 2)) * (2 if re.search(r"\d", t) else 1)
        total = sum(w(t) for t in terms)
        return sum(w(t) for t in terms & block["terms"]) / (1 + total) ** 0.5 if total else 0.0

    def best(self, sentence: str):
        terms = set(_content(sentence))
        ranked = sorted(((self.score(terms, b), b) for b in self.blocks), key=lambda x: -x[0])
        return ranked[0] if ranked else (0.0, None)


def _verbatim(sentence: str, source: str, n: int = 4) -> float:
    sw, bw = _tokens(sentence), _tokens(source)
    grams = {tuple(bw[i:i + n]) for i in range(len(bw) - n + 1)}
    covered = set()
    for i in range(len(sw) - n + 1):
        if tuple(sw[i:i + n]) in grams:
            covered.update(range(i, i + n))
    return len(covered) / len(sw) if sw else 0.0


def _bold_kind(phrase: str) -> str:
    if re.search(_MONTHS, phrase, re.I) or re.search(r"\b(19|20)\d\d\b", phrase) and not re.search(r"[$%]", phrase):
        return "dates"
    if re.search(r"\d", phrase):
        return "figures"
    if re.match(r"[A-Z]", phrase):
        return "names/terms"
    return "other"


def align(summary_md: str, docs: list[tuple[str, dict]]) -> dict:
    """Evidence for one summary against its sources. docs: [(label, parsed document), ...]."""
    idx = _Index(docs)
    points = summary_points(summary_md)
    sentences, unmatched = [], []
    used_blocks: set = set()
    for p in points:
        for s, e in documents.split_sentences(p["text"]) or [(0, len(p["text"]))]:
            text = p["text"][s:e].strip()
            if len(_content(text)) < 2:
                continue
            score, b = idx.best(text)
            row = {"section": p["section"], "text": text, "score": round(score, 2)}
            if b is None or score < MIN_SCORE:
                unmatched.append(row)
                continue
            spans = documents.matching_sentences(b["text"], text)
            src_sentence = " ".join(b["text"][a:z] for a, z in spans) if spans else b["text"][:400]
            # A sentence may combine facts from several paragraphs: numbers not in the main block are looked up
            # in the others, and those blocks count as additional sources.
            also = []
            for raw in missing_numbers(text, b["text"]):
                n = next(x for x in numbers(text) if x["raw"] == raw)
                terms = set(_content(text))
                hit = max((o for o in idx.blocks if any(_same(n, y) for y in numbers(o["text"]))),
                          key=lambda o: idx.score(terms, o), default=None)
                if hit and hit is not b and hit not in also:
                    also.append(hit)
            source_text = " ".join([b["text"]] + [o["text"] for o in also])
            row.update({"label": b["label"], "doc_id": b["doc_id"], "doc": b["doc"], "block_id": b["id"],
                        "page": b["page"], "kind": b["kind"], "source_section": leaf(b["heading"]),
                        "also": [{"block_id": o["id"], "doc_id": o["doc_id"], "source_section": leaf(o["heading"])}
                                 for o in also],
                        "source_sentence": src_sentence, "verbatim": round(_verbatim(text, source_text), 2),
                        "numbers_missing": missing_numbers(text, source_text), "numbers": len(numbers(text))})
            sentences.append(row)
            used_blocks.add((b["doc_id"], b["id"]))
            used_blocks.update((o["doc_id"], o["id"]) for o in also)

    # Coverage of source sections (by heading leaf).
    coverage: dict[str, dict] = {}
    for b in idx.blocks:
        c = coverage.setdefault(leaf(b["heading"]), {"used": 0, "total": 0, "words": 0})
        c["total"] += 1
        c["words"] += _words(b["text"])
        if (b["doc_id"], b["id"]) in used_blocks:
            c["used"] += 1

    sections = []
    for p in points:
        if not sections or sections[-1]["name"] != p["section"]:
            sections.append({"name": p["section"], "points": 0, "words": 0})
        sections[-1]["points"] += 1
        sections[-1]["words"] += _words(p["text"])
    source_map: dict[str, Counter] = {}
    for r in sentences:
        for sec in {r["source_section"], *(o["source_section"] for o in r["also"])}:
            source_map.setdefault(r["section"], Counter())[sec] += 1

    words = sum(_words(p["text"]) for p in points)
    src_words = sum(c["words"] for c in coverage.values()) or 1
    all_words = sum(len(_tokens(r["text"])) for r in sentences) or 1
    verbatim = sum(r["verbatim"] * len(_tokens(r["text"])) for r in sentences) / all_words
    n_numbers = sum(r["numbers"] for r in sentences) + sum(len(numbers(r["text"])) for r in unmatched)
    n_missing = sum(len(r["numbers_missing"]) for r in sentences) + sum(len(numbers(r["text"])) for r in unmatched)
    bold = [b for p in points for b in p["bold"]]

    # Rewrite examples: clearly sourced, rewritten (not copied), one per summary section first.
    candidates = sorted((r for r in sentences if 0.0 <= r["verbatim"] <= 0.7 and r["score"] >= MIN_SCORE * 1.5),
                        key=lambda r: -r["score"])
    pairs, seen = [], set()
    for r in candidates + candidates:
        if len(pairs) >= 4:
            break
        if (r["section"] in seen and len(seen) < len({c["section"] for c in candidates})) or r in pairs:
            continue
        seen.add(r["section"])
        pairs.append(r)
    return {
        "version": ALIGN_VERSION,
        "words": words, "points": len(points), "sections": sections,
        "words_per_point": round(words / len(points)) if points else 0,
        "source_words": src_words, "compression": round(words / src_words, 3),
        "verbatim": round(verbatim, 3),
        "numbers": n_numbers, "numbers_missing": n_missing,
        "bold": {"count": len(bold), "kinds": dict(Counter(_bold_kind(b) for b in bold))},
        "coverage": coverage,
        "source_map": {k: dict(v) for k, v in source_map.items()},
        "sentences": sentences, "unmatched": unmatched,
        "pairs": [{k: r[k] for k in ("section", "source_section", "source_sentence", "text", "verbatim")} for r in pairs],
    }
