"""
Finding source citations in model answers.

The model is asked to write [C1-p2-13] / [D2-b14] (document label + block id), but models, and the examples
they imitate, vary: (C1-p2-13), [C1 – p2-13], [C1, p2-13], [C1-P2-13], [Source: C1-p2-13], [C1-p2-13; p3-1],
[C1 page 2-13]. `find` accepts these and returns canonical (label, block) pairs. A bracket or parenthesis is
only treated as a citation when everything inside it is one, so ordinary text like [Company] or (2026) is left alone.
"""
import re

_GROUP = re.compile(r"\[([^\[\]\n]{2,160})\]|\(([^()\n]{2,160})\)")
_PART = re.compile(r"""^\s*(?:(?:sources?|refs?|see)\s*:?\s*)?
    (?:([CD])\s*(\d+)\s*[-–—:.]?\s*)?                     # document label (may be left out after the first)
    (?:(?:p|page|pg)\s*\.?\s*(\d+)\s*[-–—.,]\s*(t?\s*\d+)  # PDF block: p2-13, p2-t1, page 2-13
     |b\s*(\d+)                                            # text block: b14
     |(\d+)\s*[-–]\s*(t?\d+))                              # 2-13 (the p left out)
    \s*$""", re.I | re.X)
_NUMBERED = re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]")
_SOURCES_SECTION = re.compile(r"\n#{0,4}\s*\**\s*(sources|references)\s*\**:?\s*\n.*\Z", re.I | re.S)


def _part(text: str, last_label: str | None):
    m = _PART.match(text)
    if not m:
        return None
    label = f"{m.group(1).upper()}{m.group(2)}" if m.group(1) else last_label
    if m.group(3):
        block = f"p{m.group(3)}-{m.group(4).replace(' ', '').lower()}"
    elif m.group(5):
        block = f"b{m.group(5)}"
    else:
        block = f"p{m.group(6)}-{m.group(7).lower()}"
    return label, block


def find(text: str):
    """Yield (start, end, [(label or None, block_id), ...]) for each bracket/parenthesis group of citations."""
    for m in _GROUP.finditer(text):
        paren = m.group(1) is None
        inner = m.group(2) if paren else m.group(1)
        if not paren and text[m.end():m.end() + 1] == "(":
            continue                                       # a Markdown link: [text](url)
        inner = re.sub(r"\b([CD]\d+)\s*,\s*(?=(?:p|page|pg|b)\s*\.?\s*\d)", r"\1-", inner, flags=re.I)
        parts, last = [], None
        for piece in re.split(r"\s*(?:[,;]|\band\b|&)\s*", inner):
            if not piece.strip():
                continue
            r = _part(piece, last)
            if r is None:
                parts = None
                break
            parts.append(r)
            last = r[0] or last
        if not parts:
            continue
        if paren and not any(label for label, _ in parts):
            continue                                       # "(2-13)" without a document label is too ambiguous
        yield m.start(), m.end(), parts


def has_citations(text: str) -> bool:
    return next(find(text), None) is not None


def strip(text: str) -> str:
    """Text without citations, numbered references ([1]) or a trailing Sources/References list: used for
    example summaries, so the model learns their format but not another document's sources."""
    out, at = [], 0
    for s, e, _ in find(text):
        out.append(text[at:s].rstrip(" "))
        at = e
    out.append(text[at:])
    text = "".join(out)
    text = _SOURCES_SECTION.sub("\n", text)
    text = _NUMBERED.sub("", text)
    return re.sub(r"[ \t]+([.,;:])", r"\1", text).strip()
