"""
Files the model creates in its answers, and writing them to disk.

The model writes a file as a block in its answer:
    <file path="summaries/harborline.docx">
    ...content (Markdown for .md and .docx)...
    </file>
`split_answer` separates those blocks from the prose; `to_bytes` turns a block into file bytes
(.docx files are converted from Markdown with python-docx).
"""
import io
import re
from pathlib import Path

FILE_TYPES = {".md", ".txt", ".csv", ".json", ".docx"}

FILE_INSTRUCTIONS = """
Creating files: you CAN create files for the user. Write each file inside your answer as
<file path="NAME.EXT">
full file content
</file>
{where}
- Supported types: .md, .txt, .csv, .json and .docx. For .docx, write the content in Markdown (headings, bullet lists, **bold**, tables); it is converted to a Word document.
- Use a short descriptive file name; subfolders are allowed (e.g. path="drafts/summary.docx").
- Put the complete content in the block. Outside the block, say in one sentence what the file contains.
- Inside the file, keep the source IDs after facts taken from documents (e.g. [D1-p2-13]); they become numbered references with a Sources list when the file is saved.
- Never say that you cannot create files."""

WHERE_PROJECT = "The user saves it to the project folder with one click (or downloads it)."
WHERE_CHAT = "The user downloads it with one click."

_BLOCK = re.compile(r'<file\s+(?:path|name)\s*=\s*["\']([^"\']+)["\']\s*>\n?(.*?)\n?</file>', re.S | re.I)
_OPEN = re.compile(r'<file\s+(?:path|name)\s*=\s*["\']([^"\']+)["\']\s*>\n?', re.I)


def clean_path(path: str) -> str:
    """Relative path with a supported suffix (unknown suffixes become .md)."""
    p = Path(path.strip().replace("\\", "/").lstrip("/"))
    parts = [re.sub(r'[<>:"|?*]', "_", s) for s in p.parts if s not in ("", ".", "..")]
    p = Path(*parts) if parts else Path("output.md")
    return str(p if p.suffix.lower() in FILE_TYPES else p.with_suffix(".md"))


def split_answer(text: str) -> list[dict]:
    """[{"kind": "text", "text"} | {"kind": "file", "path", "content", "complete"}] in answer order."""
    parts, at = [], 0
    for m in _BLOCK.finditer(text):
        if m.start() > at:
            parts.append({"kind": "text", "text": text[at:m.start()]})
        parts.append({"kind": "file", "path": clean_path(m.group(1)), "content": m.group(2).strip("\n") + "\n",
                      "complete": True})
        at = m.end()
    rest = text[at:]
    m = _OPEN.search(rest)
    if m:                                   # a block still being written (streaming)
        if m.start():
            parts.append({"kind": "text", "text": rest[:m.start()]})
        parts.append({"kind": "file", "path": clean_path(m.group(1)), "content": rest[m.end():], "complete": False})
    elif rest:
        parts.append({"kind": "text", "text": rest})
    return parts


def to_bytes(path: str, content: str) -> bytes:
    if Path(path).suffix.lower() == ".docx":
        return markdown_to_docx(content)
    return content.encode("utf-8")


# ---------------------------------------------------------------- Markdown -> Word

def _add_runs(paragraph, text: str):
    """Add text to a python-docx paragraph, honouring **bold** and *italic*."""
    for piece in re.split(r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)", text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            paragraph.add_run(piece[2:-2]).bold = True
        elif piece.startswith("*") and piece.endswith("*") and len(piece) > 2:
            paragraph.add_run(piece[1:-1]).italic = True
        else:
            paragraph.add_run(piece)


def markdown_to_docx(md: str) -> bytes:
    import docx

    doc = docx.Document()
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not re.match(r"^\s*\|?\s*:?-{2,}", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            width = max(len(r) for r in rows)
            table = doc.add_table(rows=len(rows), cols=width)
            table.style = "Table Grid"
            for r, row in enumerate(rows):
                for c in range(width):
                    cell = table.cell(r, c)
                    cell.text = ""
                    _add_runs(cell.paragraphs[0], row[c] if c < len(row) else "")
                    if r == 0:
                        for run in cell.paragraphs[0].runs:
                            run.bold = True
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            doc.add_heading(m.group(2).strip().strip("*"), level=min(len(m.group(1)), 4))
        elif re.match(r"^[-*+•]\s+", stripped):
            indent = len(line) - len(line.lstrip())
            style = "List Bullet 2" if indent >= 2 else "List Bullet"
            _add_runs(doc.add_paragraph(style=style), re.sub(r"^[-*+•]\s+", "", stripped))
        elif re.match(r"^\d+[.)]\s+", stripped):
            _add_runs(doc.add_paragraph(style="List Number"), re.sub(r"^\d+[.)]\s+", "", stripped))
        elif re.fullmatch(r"-{3,}|\*{3,}", stripped):
            doc.add_paragraph()
        else:
            _add_runs(doc.add_paragraph(), stripped)
        i += 1
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- citations in saved files

_CITE_ID = r"[CD]\d+-[a-z]?\d+(?:-t?\d+)?"
CITE_GROUP = re.compile(rf"\[({_CITE_ID}(?:\s*[,;]\s*{_CITE_ID})*)\]", re.I)


def with_sources(path: str, content: str, entries: list[dict]) -> str:
    """Replace citation IDs with [1], [2]... and append a Sources list (file, page, section, excerpt),
    so a saved file stays traceable outside the app. `entries` are the chat's documents and project
    context ({doc_id, label, name}). CSV/JSON files are left unchanged."""
    from . import documents

    if Path(path).suffix.lower() not in (".md", ".docx", ".txt"):
        return content
    by_label = {e["label"].upper(): e for e in entries}
    docs: dict[str, dict] = {}
    numbers: dict[str, int] = {}
    sources: list[str] = []

    def ref(m):
        out = []
        for cid in re.split(r"\s*[,;]\s*", m.group(1)):
            label, _, bid = cid.partition("-")
            entry = by_label.get(label.upper())
            if entry and entry["doc_id"] not in docs:
                try:
                    docs[entry["doc_id"]] = documents.get(entry["doc_id"])
                except FileNotFoundError:
                    docs[entry["doc_id"]] = {"blocks": [], "kind": ""}
            doc = docs.get(entry["doc_id"]) if entry else None
            block = next((b for b in doc["blocks"] if b.get("id") == bid), None) if doc else None
            if not block:
                out.append(f"[{cid}?]")
                continue
            key = f"{entry['doc_id']}:{bid}"
            if key not in numbers:
                numbers[key] = len(numbers) + 1
                where = f"p.{block['page']}" if doc["kind"] == "pdf" else f"block {bid}"
                excerpt = block["text"][:160] + ("…" if len(block["text"]) > 160 else "")
                sources.append(f"{numbers[key]}. {entry['name']}, {where}"
                               + (f" ({block['heading']})" if block["heading"] else "") + f': "{excerpt}"')
            out.append(f"[{numbers[key]}]")
        return "".join(out)

    body = CITE_GROUP.sub(ref, content).rstrip()
    if sources:
        body += "\n\n## Sources\n\n" + "\n".join(sources) + "\n"
    return body + "\n"
