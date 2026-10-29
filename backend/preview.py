"""
A quick look at a downloaded file before keeping it (the From web checklist). Read locally, nothing is sent anywhere.

    show(path) -> {"kind": "pages", "pages": [png bytes], "total": n}      PDF: the first pages as images
                  {"kind": "text", "text": str, "more": bool}               Word, PowerPoint, CSV, text
                  {"kind": "table", "sheets": [(name, rows)], "more": bool} Excel
                  {"kind": "none", "reason": str}
"""
import csv
import io
from pathlib import Path

MAX_PAGES = 3
MAX_CHARS = 6000
MAX_ROWS, MAX_COLS, MAX_SHEETS = 40, 12, 3


def show(path: Path) -> dict:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return _pdf(path)
        if suffix == ".docx":
            return _docx(path)
        if suffix == ".pptx":
            return _pptx(path)
        if suffix == ".xlsx":
            return _xlsx(path)
        if suffix == ".csv":
            return _csv(path)
        if suffix in (".txt", ".md"):
            return _text(path.read_text("utf-8", errors="replace"))
    except Exception as e:
        return {"kind": "none", "reason": f"The file could not be read ({e})."}
    return {"kind": "none", "reason": "No preview for this older Office format; download it to open it."}


def _text(text: str) -> dict:
    text = text.strip()
    return {"kind": "text", "text": text[:MAX_CHARS], "more": len(text) > MAX_CHARS}


def _pdf(path: Path) -> dict:
    import pymupdf
    with pymupdf.open(path) as doc:
        pages = [doc[i].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), alpha=False).tobytes("png")
                 for i in range(min(MAX_PAGES, doc.page_count))]
        return {"kind": "pages", "pages": pages, "total": doc.page_count}


def _docx(path: Path) -> dict:
    import docx
    d = docx.Document(str(path))
    lines = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables[:3]:
        lines += [" | ".join(c.text.strip() for c in row.cells) for row in t.rows[:MAX_ROWS]]
    return _text("\n\n".join(lines))


def _pptx(path: Path) -> dict:
    from pptx import Presentation
    out = []
    for n, slide in enumerate(Presentation(str(path)).slides, 1):
        texts = [s.text_frame.text.strip() for s in slide.shapes if s.has_text_frame and s.text_frame.text.strip()]
        out.append(f"— Slide {n} —\n" + "\n".join(texts))
    return _text("\n\n".join(out))


def _xlsx(path: Path) -> dict:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheets, more = [], len(wb.worksheets) > MAX_SHEETS
        for ws in wb.worksheets[:MAX_SHEETS]:
            rows = []
            for row in ws.iter_rows(values_only=True):
                if len(rows) >= MAX_ROWS:
                    more = True
                    break
                cells = ["" if v is None else str(v) for v in row[:MAX_COLS]]
                if any(cells):
                    rows.append(cells)
            sheets.append((ws.title, rows))
        return {"kind": "table", "sheets": sheets, "more": more}
    finally:
        wb.close()


def _csv(path: Path) -> dict:
    text = path.read_bytes()[:200_000].decode("utf-8", errors="replace")
    rows = [r[:MAX_COLS] for r in csv.reader(io.StringIO(text))][:MAX_ROWS + 1]
    return {"kind": "table", "sheets": [(path.name, rows[:MAX_ROWS])], "more": len(rows) > MAX_ROWS}
