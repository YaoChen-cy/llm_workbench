"""
PDF -> list of paragraphs from "Company Overview" up to the sign-off block.

Each paragraph gets a stable ID like "RR-3" (3rd paragraph of "Reason for Rating"),
plus its subheading, page number and bounding boxes (used to highlight the PDF).
Tables anywhere in the document are skipped.
"""
import re
from dataclasses import dataclass, field

import pymupdf

import config


@dataclass
class Paragraph:
    id: str
    section_code: str
    section_title: str
    subheading: str
    page: int                      # 1-based
    text: str
    rects: list = field(default_factory=list)   # [(page_index, (x0, y0, x1, y1)), ...]

    @property
    def location(self) -> str:
        loc = self.section_title + (f" > {self.subheading}" if self.subheading else "")
        return f"{loc}, p.{self.page}"


@dataclass
class ParsedDoc:
    path: str
    paragraphs: list
    header_text: str               # raw text before Company Overview (for metadata)
    missing_sections: list

    def by_id(self) -> dict:
        return {p.id: p for p in self.paragraphs}

    def to_prompt_text(self) -> str:
        """Render as the text the LLM sees, with IDs in front of every paragraph."""
        out, cur_sec, cur_sub = [], None, None
        for p in self.paragraphs:
            if p.section_title != cur_sec:
                out.append(f"\n## {p.section_title}")
                cur_sec, cur_sub = p.section_title, None
            if p.subheading and p.subheading != cur_sub:
                out.append(f"### {p.subheading}")
                cur_sub = p.subheading
            out.append(f"[{p.id}] {p.text}")
        return "\n".join(out).strip()


# ---------------------------------------------------------------- helpers

def _match_section(text):
    t = _norm(text)
    for sec in config.SECTIONS:
        if any(re.search(p, t, re.I) for p in sec["patterns"]):
            return sec
    return None


def _is_end(text):
    return any(re.search(p, _norm(text), re.I) for p in config.END_PATTERNS)


def _norm(s):
    return re.sub(r"\s+", " ", s.replace("“", '"').replace("”", '"')).strip()


def _overlaps(r, rects, thresh=0.5):
    r = pymupdf.Rect(r)
    if r.is_empty:
        return False
    return any((r & t).get_area() / r.get_area() > thresh for t in rects)


def _block_text(block):
    """Join lines of a block; repair hyphenation at line ends."""
    lines = []
    for ln in block["lines"]:
        lines.append("".join(s["text"] for s in ln["spans"]).strip())
    text = ""
    for ln in lines:
        if not ln:
            continue
        if text.endswith("-") and ln[:1].islower():
            text = text[:-1] + ln
        else:
            text = f"{text} {ln}" if text else ln
    return _norm(text)


def _is_bold_block(block):
    spans = [s for ln in block["lines"] for s in ln["spans"] if s["text"].strip()]
    return bool(spans) and all((s["flags"] & 16) or "bold" in s["font"].lower() for s in spans)


def _is_heading(block, text):
    return (_is_bold_block(block) and len(text) <= config.MAX_HEADING_CHARS
            and not text.endswith((".", ";", ",")))


# ---------------------------------------------------------------- main

def parse_pdf(path) -> ParsedDoc:
    doc = pymupdf.open(path)
    paragraphs, header_lines = [], []
    sec, sub, started, ended = None, "", False, False
    counters = {}
    seen_codes = set()

    for pno, page in enumerate(doc):
        if ended:
            break
        h = page.rect.height
        try:
            table_rects = [pymupdf.Rect(t.bbox) for t in page.find_tables().tables]
        except Exception:
            table_rects = []

        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            x0, y0, x1, y1 = block["bbox"]
            if y1 < h * config.HEADER_FOOTER_MARGIN or y0 > h * (1 - config.HEADER_FOOTER_MARGIN):
                continue
            text = _block_text(block)
            if not text:
                continue
            in_table = _overlaps(block["bbox"], table_rects)

            if not started:
                hit = _match_section(text) if _is_heading(block, text) else None
                if hit and hit["code"] == config.SECTIONS[0]["code"]:
                    started, sec, sub = True, hit, ""
                    seen_codes.add(hit["code"])
                else:
                    header_lines.append(text)     # header fields incl. tables, for metadata
                continue

            if _is_end(text):
                ended = True
                break
            if in_table:
                continue

            if _is_heading(block, text):
                hit = _match_section(text)
                if hit:
                    sec, sub = hit, ""
                    seen_codes.add(hit["code"])
                else:
                    sub = text          # company-specific subheading
                continue

            # Continuation of a paragraph split across a page break.
            prev = paragraphs[-1] if paragraphs else None
            if (prev and prev.rects[-1][0] < pno and prev.section_code == sec["code"]
                    and not prev.text.endswith((".", ":", ";", "!", "?", ")", '"'))
                    and not text.startswith("•")):
                prev.text = f"{prev.text} {text}"
                prev.rects.append((pno, tuple(block["bbox"])))
                continue

            counters[sec["code"]] = counters.get(sec["code"], 0) + 1
            paragraphs.append(Paragraph(
                id=f"{sec['code']}-{counters[sec['code']]}",
                section_code=sec["code"], section_title=sec["title"], subheading=sub,
                page=pno + 1, text=text, rects=[(pno, tuple(block["bbox"]))]))

    missing = [s["title"] for s in config.SECTIONS if s["code"] not in seen_codes]
    return ParsedDoc(path=str(path), paragraphs=paragraphs,
                     header_text="\n".join(header_lines), missing_sections=missing)


def guess_company_name(parsed: ParsedDoc, fallback: str) -> str:
    m = re.search(config.COMPANY_NAME_REGEX, parsed.header_text, re.M)
    return m.group(1).strip() if m else fallback


if __name__ == "__main__":
    import sys
    d = parse_pdf(sys.argv[1])
    print(d.to_prompt_text())
    if d.missing_sections:
        print("\n!! missing sections:", d.missing_sections)
