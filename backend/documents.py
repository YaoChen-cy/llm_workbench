"""
Generic document parsing (PDF / DOCX / TXT / MD) into citable blocks, cached by file hash.

A parsed document is stored as data/docs/<doc_id>/doc.json:
    {id, name, kind, source_path, pages, warnings, blocks: [...]}
Each block:
    {id, type: heading|paragraph|table, page, heading, text, rects}
  - id      "p3-2" = 2nd citable block on page 3 (PDF);  "b14" = 14th block (DOCX/TXT/MD).
            Headings carry no id: they only set the `heading` path of the blocks below them.
  - rects   [[page_index, x0, y0, x1, y1], ...]  (PDF only; used to highlight sources later)

In a chat, documents get labels D1, D2..., so the LLM cites e.g. [D1-p3-2].
"""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pymupdf

from .settings import DOCS_DIR

PARSER_VERSION = 1
HEADER_FOOTER_BAND = 0.08      # top/bottom fraction of the page checked for running headers/footers
MAX_HEADING_CHARS = 120


# ---------------------------------------------------------------- cache

def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def get(doc_id: str) -> dict:
    f = DOCS_DIR / doc_id / "doc.json"
    if not f.exists():
        raise FileNotFoundError(f"unknown document {doc_id}")
    return json.loads(f.read_text("utf-8"))


def meta(doc: dict) -> dict:
    cit = [b for b in doc["blocks"] if b.get("id")]
    return {"id": doc["id"], "name": doc["name"], "kind": doc["kind"], "pages": doc["pages"],
            "blocks": len(cit), "tables": sum(b["type"] == "table" for b in cit),
            "chars": sum(len(b["text"]) for b in cit), "warnings": doc["warnings"]}


def ingest(path: Path, name: str | None = None) -> dict:
    """Parse `path` (or return the cached parse) and return the document."""
    doc_id = file_hash(path)
    f = DOCS_DIR / doc_id / "doc.json"
    if f.exists():
        doc = json.loads(f.read_text("utf-8"))
        if doc.get("parser_version") == PARSER_VERSION:
            return doc
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        blocks, pages, warnings = parse_pdf(path)
        kind = "pdf"
    elif suffix == ".docx":
        blocks, pages, warnings, kind = parse_docx(path), 1, [], "docx"
    elif suffix in (".txt", ".md"):
        blocks, pages, warnings, kind = parse_text(path.read_text("utf-8", "replace")), 1, [], "text"
    else:
        raise ValueError(f"unsupported file type: {suffix}")
    doc = {"id": doc_id, "parser_version": PARSER_VERSION, "name": name or path.name, "kind": kind,
           "source_path": str(path), "pages": pages, "warnings": warnings, "blocks": blocks}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")
    (f.parent / "doc.md").write_text(to_markdown(doc, "D"), "utf-8")
    return doc


# ---------------------------------------------------------------- rendering for the LLM

def render_block(b: dict, label: str) -> str:
    tag = f"[{label}-{b['id']}]"
    if b["type"] == "table":
        return f"{tag} (table)\n{b['text']}"
    return f"{tag} {b['text']}"


def to_markdown(doc: dict, label: str, keep_ids: set | None = None) -> str:
    """Document as the LLM sees it. With `keep_ids`, only those blocks are shown and gaps marked."""
    out = [f"# Document {label}: {doc['name']}"]
    cur_heading, skipped = None, False
    for b in doc["blocks"]:
        if b["type"] == "heading":
            continue
        if keep_ids is not None and b["id"] not in keep_ids:
            skipped = True
            continue
        if skipped:
            out.append("[...]")
            skipped = False
        if b["heading"] and b["heading"] != cur_heading:
            out.append(f"\n## {b['heading']}")
            cur_heading = b["heading"]
        out.append(render_block(b, label))
    if skipped:
        out.append("[...]")
    return "\n".join(out)


# ---------------------------------------------------------------- PDF

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\u00ad", "")).strip()


def _block_text(block) -> str:
    """Join the lines of a text block, repairing end-of-line hyphenation."""
    text = ""
    for ln in block["lines"]:
        t = "".join(s["text"] for s in ln["spans"]).strip()
        if not t:
            continue
        text = text[:-1] + t if text.endswith("-") and t[:1].islower() else (f"{text} {t}" if text else t)
    return _norm(text)


def _spans(block):
    return [s for ln in block["lines"] for s in ln["spans"] if s["text"].strip()]


def _is_page_number(t: str) -> bool:
    return bool(re.fullmatch(r"(page\s*)?\d+(\s*(of|/)\s*\d+)?|[-–]\s*\d+\s*[-–]", t, re.I))


def _running_lines(doc) -> set:
    """Texts that repeat in the header/footer band on many pages (running headers/footers)."""
    if doc.page_count < 3:
        return set()
    counts = Counter()
    for page in doc:
        h = page.rect.height
        seen = set()
        for b in page.get_text("dict")["blocks"]:
            if b["type"] == 0 and (b["bbox"][3] < h * HEADER_FOOTER_BAND or b["bbox"][1] > h * (1 - HEADER_FOOTER_BAND)):
                seen.add(re.sub(r"\d+", "#", _block_text(b)))
        counts.update(seen)
    return {t for t, n in counts.items() if t and n >= max(3, doc.page_count // 2)}


def parse_pdf(path: Path):
    doc = pymupdf.open(path)
    running = _running_lines(doc)

    # Body font size = most common span size weighted by characters.
    sizes = Counter()
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            if b["type"] == 0:
                for s in _spans(b):
                    sizes[round(s["size"], 1)] += len(s["text"])
    body = sizes.most_common(1)[0][0] if sizes else 10

    blocks, heads = [], {}          # heads: level -> heading text
    warnings, empty_pages = [], 0

    for pno, page in enumerate(doc):
        h = page.rect.height
        try:
            tables = [t for t in page.find_tables().tables if t.row_count >= 2 and t.col_count >= 2]
        except Exception:
            tables = []
        t_rects = [pymupdf.Rect(t.bbox) for t in tables]
        pending_tables = sorted(zip(t_rects, tables), key=lambda x: x[0].y0)
        n = 0
        page_items = []

        raw = [b for b in page.get_text("dict")["blocks"] if b["type"] == 0]
        if not any(_block_text(b) for b in raw):
            empty_pages += 1

        def emit_table(rect, table):
            md = table.to_markdown(clean=False).strip()
            if md:
                page_items.append(("table", md, [[pno, *rect]], None))

        for b in raw:
            text = _block_text(b)
            if not text:
                continue
            r = pymupdf.Rect(b["bbox"])
            in_band = r.y1 < h * HEADER_FOOTER_BAND or r.y0 > h * (1 - HEADER_FOOTER_BAND)
            if in_band and (_is_page_number(text) or re.sub(r"\d+", "#", text) in running):
                continue
            if any(not (r & t).is_empty and (r & t).get_area() > 0.5 * max(r.get_area(), 1) for t in t_rects):
                continue
            while pending_tables and pending_tables[0][0].y0 <= r.y0:
                emit_table(*pending_tables.pop(0))
            spans = _spans(b)
            max_size = max(s["size"] for s in spans)
            bold = all((s["flags"] & 16) or "bold" in s["font"].lower() for s in spans)
            looks_heading = (len(text) <= MAX_HEADING_CHARS and not text.endswith((".", ",", ";"))
                             and (bold or max_size >= body * 1.15) and len(text.split()) <= 16)
            level = (1 if max_size >= body * 1.3 else 2) if looks_heading else None
            page_items.append(("heading" if looks_heading else "paragraph", text, [[pno, *b["bbox"]]], level))
        for rect, table in pending_tables:
            emit_table(rect, table)

        for kind, text, rects, level in page_items:
            if kind == "heading":
                heads[level] = text
                for deeper in [k for k in heads if k > level]:
                    del heads[deeper]
                blocks.append({"id": None, "type": "heading", "page": pno + 1, "heading": "", "text": text,
                               "level": level, "rects": rects})
                continue
            heading = " › ".join(heads[k] for k in sorted(heads))
            prev = next((x for x in reversed(blocks) if x["type"] != "heading"), None)
            # Paragraph split across a page break: previous block on an earlier page, no sentence end.
            if (kind == "paragraph" and n == 0 and prev and prev["type"] == "paragraph"
                    and prev["rects"][-1][0] < pno and blocks[-1] is prev
                    and not prev["text"].endswith((".", ":", ";", "!", "?", '"', "”", ")"))
                    and not text[:1] in "•-–*" and text[:1].islower()):
                prev["text"] = f"{prev['text']} {text}"
                prev["rects"] += rects
                continue
            n += 1
            bid = f"p{pno + 1}-{'t' if kind == 'table' else ''}{n}"
            blocks.append({"id": bid, "type": kind, "page": pno + 1, "heading": heading, "text": text,
                           "rects": rects})

    if empty_pages:
        warnings.append(f"{empty_pages} page(s) have no text layer (scanned?) — OCR is not enabled yet.")
    return blocks, doc.page_count, warnings


# ---------------------------------------------------------------- DOCX / text

def _table_md(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    w = max(len(r) for r in rows)
    rows = [[c.replace("|", "\\|").replace("\n", " ") for c in r] + [""] * (w - len(r)) for r in rows]
    return "\n".join(["| " + " | ".join(rows[0]) + " |", "|" + "---|" * w]
                     + ["| " + " | ".join(r) + " |" for r in rows[1:]])


def _finish(items) -> list[dict]:
    """items: (kind, text, level) -> blocks with heading paths and b<n> ids."""
    blocks, heads, n = [], {}, 0
    for kind, text, level in items:
        if kind == "heading":
            heads[level] = text
            for deeper in [k for k in heads if k > level]:
                del heads[deeper]
            blocks.append({"id": None, "type": "heading", "page": 1, "heading": "", "text": text,
                           "level": level, "rects": []})
        else:
            n += 1
            blocks.append({"id": f"b{n}", "type": kind, "page": 1,
                           "heading": " › ".join(heads[k] for k in sorted(heads)), "text": text, "rects": []})
    return blocks


def parse_docx(path: Path) -> list[dict]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(str(path))
    items = []
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(el, d)
            text = _norm(p.text)
            if not text:
                continue
            m = re.match(r"heading\s*(\d)", (p.style.name or "").lower())
            if m or (p.style.name or "").lower() == "title":
                items.append(("heading", text, int(m.group(1)) if m else 1))
            else:
                items.append(("paragraph", text, None))
        elif tag == "tbl":
            rows = [[_norm(c.text) for c in r.cells] for r in Table(el, d).rows]
            if md := _table_md(rows):
                items.append(("table", md, None))
    return _finish(items)


def parse_text(text: str) -> list[dict]:
    items = []
    for chunk in re.split(r"\n\s*\n", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"^(#{1,6})\s+(.+)$", chunk)
        if m and "\n" not in chunk:
            items.append(("heading", m.group(2).strip(), len(m.group(1))))
        elif chunk.startswith("|"):
            items.append(("table", chunk, None))
        else:
            items.append(("paragraph", _norm(chunk), None))
    return _finish(items)


if __name__ == "__main__":
    import sys
    d = ingest(Path(sys.argv[1]))
    print(json.dumps(meta(d), indent=1))
    print(to_markdown(d, "D1"))
