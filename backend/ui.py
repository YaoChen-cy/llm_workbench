"""
User interface written in Python with NiceGUI: no JavaScript build step and no .js/.css/.html files to ship.
NiceGUI's own browser assets come from the `nicegui` pip package.

One `Workbench` object per browser tab holds the UI state and calls the backend modules directly.
"""
import asyncio
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

from nicegui import events, ui

from . import chats, citations, documents, knowledge, llm, outputs, projects, settings
from . import files as fs

# ---------------------------------------------------------------- styling

CSS = """
:root { --wb-bg:#f7f7f5; --wb-panel:#fff; --wb-side:#efeeea; --wb-text:#1d1d1b; --wb-muted:#6b6a66; --wb-border:#e0ded8;
  --wb-accent:#2f5bea; --wb-accent-soft:#e6ecfd; --wb-user:#e9eefc; --wb-error:#b42318; --wb-code:#f1f0ec;
  --wb-hl:rgba(255,196,0,.5); --wb-hl-soft:rgba(255,214,10,.18); }
body.body--dark { --wb-bg:#18181a; --wb-panel:#1f1f22; --wb-side:#141416; --wb-text:#ececea; --wb-muted:#9c9b97;
  --wb-border:#333338; --wb-accent:#6d8dff; --wb-accent-soft:#24304f; --wb-user:#26304a; --wb-error:#ff8a80; --wb-code:#2a2a2e;
  --wb-hl:rgba(255,196,0,.35); --wb-hl-soft:rgba(255,214,10,.1); }
body { background: var(--wb-bg); color: var(--wb-text); font-size: 14px; }
.q-drawer { background: var(--wb-side) !important; }
.rightpanel .q-drawer { background: var(--wb-panel) !important; }
.wb-header { background: var(--wb-panel) !important; color: var(--wb-text) !important; border-bottom: 1px solid var(--wb-border); }
.wb-footer { background: var(--wb-bg) !important; color: var(--wb-text) !important; }
.muted { color: var(--wb-muted); }
.side-head { font-size: 11px; font-weight: 650; letter-spacing: .04em; text-transform: uppercase; color: var(--wb-muted); }
.side-item { border-radius: 7px; padding: 6px 8px; cursor: pointer; width: 100%; }
.side-item:hover { background: var(--wb-border); }
.side-item.on { background: var(--wb-panel); box-shadow: 0 0 0 1px var(--wb-border); }
.side-item.in { background: var(--wb-accent-soft); }
.ellipsis1 { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.wrap-anywhere { overflow-wrap: anywhere; }
.bubble { background: var(--wb-user); padding: 9px 14px; border-radius: 14px 14px 4px 14px; max-width: 80%; white-space: pre-wrap; overflow-wrap: anywhere; }
.card { background: var(--wb-panel); border: 1px solid var(--wb-border); border-radius: 12px; padding: 14px 16px; width: 100%; }
.notice { background: var(--wb-accent-soft); border-radius: 8px; padding: 6px 10px; white-space: pre-wrap; font-size: 12.5px; width: 100%; }
.err { color: var(--wb-error); white-space: pre-wrap; }
.chip { display: inline-flex; align-items: center; gap: 4px; font-size: 12.5px; background: var(--wb-panel); border: 1px solid var(--wb-border); border-radius: 14px; padding: 1px 4px 1px 10px; }
.chip b { color: var(--wb-accent); }
.answer .nicegui-markdown p { margin: 0 0 10px; }
.wb-resizer { position: absolute; top: 0; right: 0; width: 10px; height: 100%; cursor: col-resize; z-index: 3000; }
.wb-resizer-right { left: 0; right: auto; }
.wb-resizer:hover, body.wb-resizing .wb-resizer { background: var(--wb-accent); opacity: .35; }
body.wb-resizing, body.wb-resizing * { cursor: col-resize !important; user-select: none !important; }
.q-drawer__content { position: relative; }
.q-dialog__inner--minimized > div { max-width: 95vw; }
.q-dialog .nicegui-markdown h2, .card .nicegui-markdown h2 { font-size: 16px; font-weight: 650; margin: 10px 0 4px; line-height: 1.3; }
.q-dialog .nicegui-markdown h3, .card .nicegui-markdown h3 { font-size: 14px; font-weight: 650; margin: 8px 0 2px; line-height: 1.3; }
.q-dialog .nicegui-markdown ul, .card .nicegui-markdown ul { margin: 2px 0 6px; padding-left: 18px; }   /* Quasar caps dialogs at 560px; our cards set their own width */
.fit-row { flex-wrap: wrap; }
.fit-row > .fitchip { flex: 0 0 auto; }
.fitchip { display: inline-flex; align-items: center; gap: 3px; padding: 1px 7px; border-radius: 10px; border: 1px solid var(--wb-border); }
.fitchip > div { display: inline; }
.fit-ok { color: #18794e; } .fit-warn { color: #b54708; border-color: #f5c58b; background: #fff7ed; } .fit-info { color: var(--wb-muted); }
body.body--dark .fit-ok { color: #7fd8a4; } body.body--dark .fit-warn { color: #ffb35c; border-color: #6b4a1e; background: #2a1f12; }
.user-msg .msg-actions { opacity: 0; transition: opacity .15s; }
.user-msg:hover .msg-actions, .user-msg:focus-within .msg-actions { opacity: 1; }
.answer .file-text { border-left: 3px solid var(--wb-accent-soft); padding-left: 12px; }
.answer .nicegui-markdown table { border-collapse: collapse; }
.answer .nicegui-markdown th, .answer .nicegui-markdown td { border: 1px solid var(--wb-border); padding: 3px 8px; }
.cite { display: inline-block; font-size: 11px; font-weight: 600; line-height: 1.5; padding: 0 5px; margin: 0 1px; border-radius: 4px;
  background: var(--wb-accent-soft); color: var(--wb-accent); vertical-align: 1px; white-space: nowrap; cursor: pointer; }
.cite:hover { background: var(--wb-accent); color: #fff; }
.cite.bad { background: transparent; color: var(--wb-error); outline: 1px dashed var(--wb-error); cursor: help; }
.type-badge { display: inline-block; min-width: 46px; text-align: center; font-size: 10.5px; font-weight: 650; padding: 1px 5px; border-radius: 4px; background: var(--wb-code); color: var(--wb-muted); flex: 0 0 auto; }
.t-pdf { background: #fde8e7; color: #b42318; } .t-docx, .t-doc { background: #e6ecfd; color: #2f5bea; }
.t-md, .t-txt { background: #e7f6ec; color: #18794e; } .t-pptx { background: #fdeee4; color: #c4410f; } .t-xlsx, .t-xls, .t-csv { background: #e3f5ef; color: #0f7a55; }
body.body--dark .t-pdf { background: #4a2020; color: #ff9b94; } body.body--dark .t-docx { background: #24304f; color: #9db3ff; }
body.body--dark .t-md, body.body--dark .t-txt { background: #1d3a2a; color: #7fd8a4; }
.fs-row { display: flex; align-items: center; gap: 8px; padding: 5px 8px; border-radius: 6px; width: 100%; }
.fs-row.click { cursor: pointer; } .fs-row.click:hover { background: var(--wb-bg); }
.fs-off { opacity: .45; }
.q-drawer .q-scrollarea__content { width: 100%; max-width: 100%; }
.fs-row > * { min-width: 0; }
.quote mark, .text-view mark { background: var(--wb-hl); color: inherit; border-radius: 2px; }
.text-view { background: var(--wb-panel); border-radius: 8px; padding: 12px 14px; font-size: 13px; line-height: 1.55; }
.tb { padding: 2px 6px 2px 8px; border-left: 3px solid transparent; white-space: pre-wrap; margin-bottom: 6px; }
.tb.cited { background: var(--wb-hl-soft); border-left-color: #f0b400; }
.tb-id { float: right; font-size: 10px; color: var(--wb-muted); margin-left: 8px; }
.tb-h { font-weight: 650; margin: 8px 0 4px; }
.tb-table { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 11.5px; white-space: pre; overflow-x: auto; }
.pdf-scroll { background: var(--wb-side); }
code { background: var(--wb-code); padding: 1px 5px; border-radius: 4px; font-size: 12.5px; }
"""

# Clicking a citation chip inside rendered markdown sends a "cite" event to Python.
CITE_SCRIPT = """<script>
document.addEventListener('click', (e) => {
  const c = e.target.closest('[data-cite]');
  if (c && c.dataset.ok) emitEvent('cite', {id: c.dataset.cite, claim: c.dataset.claim || ''});
});
</script>"""

# Dragging the border of the sidebar or the right panel sends "resize_drawer" events to Python, which sets
# the drawer width (Quasar then re-lays out the chat column). Widths are remembered in this browser.
RESIZE_SCRIPT = """<script>
(() => {
  let drag = null, frame = 0;
  const key = (side) => 'wb-width-' + side;
  document.addEventListener('mousedown', (e) => {
    const h = e.target.closest('.wb-resizer');
    if (!h) return;
    const drawer = h.closest('.q-drawer');
    drag = {side: h.dataset.side, x: e.clientX, w: drawer.offsetWidth};
    document.body.classList.add('wb-resizing');
    e.preventDefault();
  });
  document.addEventListener('mousemove', (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x;
    const w = Math.round(drag.side === 'left' ? drag.w + dx : drag.w - dx);
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => { drag.last = w; emitEvent('resize_drawer', {side: drag.side, width: w}); });
  });
  document.addEventListener('mouseup', () => {
    if (!drag) return;
    try { if (drag.last) localStorage.setItem(key(drag.side), drag.last); } catch (_) {}
    drag = null;
    document.body.classList.remove('wb-resizing');
  });
  window.addEventListener('load', () => setTimeout(() => {
    for (const side of ['left', 'right']) {
      let w = null;
      try { w = localStorage.getItem(key(side)); } catch (_) {}
      if (w) emitEvent('resize_drawer', {side: side, width: +w, initial: true});
    }
  }, 300));
})();
</script>"""

INSTRUCTIONS_HINT = """Describe the task the assistant should perform in this project, e.g.

Draft a credit summary for each memo I attach.
- Two sections: "Situation Recap" and "Recent Development", 2-4 bullet points each.
- Bold the key figures. Use $mm for amounts.
- Only use facts from the attached memo; ask me if something important is missing."""

PROFILE_TEMPLATE = """## Learned rules
### Required information
- 
### Content selection
- 
### Rewriting
- 
### Tone and phrasing
- 
### Formatting
- 
### Template
"""

# ---------------------------------------------------------------- file info helpers

TYPES = {"pdf": "PDF", "docx": "Word", "doc": "Word 97", "txt": "Text", "md": "Markdown", "xlsx": "Excel",
         "xls": "Excel", "csv": "CSV", "pptx": "PowerPoint", "png": "Image", "jpg": "Image", "jpeg": "Image",
         "json": "JSON", "msg": "Outlook", "zip": "Archive"}
ACCEPT = ".pdf,.docx,.txt,.md"


def ext(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def file_type(name: str) -> str:
    return TYPES.get(ext(name), ext(name).upper() or "File")


def supported(name: str) -> bool:
    return f".{ext(name)}" in fs.SUPPORTED


def file_size(n) -> str:
    if n is None:
        return ""
    return f"{n} B" if n < 1024 else f"{n / 1024:.0f} KB" if n < 1 << 20 else f"{n / (1 << 20):.1f} MB"


def type_badge(name: str):
    return ui.label(file_type(name)).classes(f"type-badge t-{ext(name) or 'file'}")


def describe(m: dict) -> str:
    pages = f", {m['pages']} page{'s' if m['pages'] != 1 else ''}" if m.get("kind") == "pdf" and m.get("pages") else ""
    return f"{m['name']} ({file_type(m['name'])}{pages})"


def report(metas: list[dict], verb: str = "Added") -> str:
    """One message for an upload/attach result: successes with name and type, duplicates, failures, warnings."""
    ok = [m for m in metas if m.get("ok") and not m.get("duplicate")]
    dup = [m for m in metas if m.get("ok") and m.get("duplicate")]
    lines = []
    if ok:
        lines.append(f"✓ {verb} {len(ok)} file{'s' if len(ok) != 1 else ''}: " + ", ".join(describe(m) for m in ok))
    if dup:
        lines.append("Already in context: " + ", ".join(m["name"] for m in dup))
    lines += [f"✗ Could not add {m['name']}: {m.get('error')}" for m in metas if not m.get("ok")]
    lines += [f"⚠ {m['name']}: {w}" for m in metas for w in (m.get("warnings") or [])]
    return "\n".join(lines)


def rejected(_e=None):
    ui.notify("Some files were skipped: only PDF, Word (.docx), Text and Markdown files can be read.", type="warning")


def slug(s: str) -> str:
    return re.sub(r"\s+", "_", re.sub(r"[^\w\- ]+", "", s).strip())[:50] or "output"


# ---------------------------------------------------------------- citations in answers

def _citation_groups(text: str, resolve):
    """Citation groups in `text` with each citation resolved: (start, end, [(cid, entry, doc, block), ...]).
    Groups whose citations have no document label and match no attached document are skipped (plain text)."""
    for s, e, parts in citations.find(text):
        resolved = []
        for label, block_id in parts:
            entry, doc, block = resolve(f"{label or '*'}-{block_id}")
            cid = f"{entry['label']}-{block_id}" if entry else f"{label or '?'}-{block_id}"
            resolved.append((cid, entry, doc, block, label))
        if all(r[4] is None and r[3] is None for r in resolved):
            continue
        yield s, e, [r[:4] for r in resolved]


def claim_before(prefix: str) -> str:
    """The sentence a citation backs: text since the previous sentence end / citation / line break."""
    line = prefix[prefix.rfind("\n") + 1:]
    pieces, at = [], 0
    for s, e, _ in citations.find(line):
        pieces += [line[at:s], "\0"]
        at = e
    line = "".join(pieces) + line[at:]
    parts = [s.strip() for s in re.split(r"\0|(?<=[.!?])\s+(?=[A-Z*\"(])", line)]
    claim = ""
    for s in reversed(parts):
        if len(claim) >= 40:
            break
        claim = f"{s} {claim}"
    claim = re.sub(r"[*_`#>|]", "", claim)
    return re.sub(r"^\s*([-+]|\d+\.)\s+", "", claim).strip()[:600]


def render_answer(text: str, resolve) -> str:
    """Markdown with citations ([C1-p2-13] and common variants) replaced by clickable chips (HTML spans)."""
    out, at = [], 0
    for start, end, items in _citation_groups(text, resolve):
        out.append(text[at:start])
        at = end
        claim = claim_before(text[:start])
        for cid, entry, doc, block in items:
            label = cid.split("-")[0].upper()
            if block:
                loc = f"p.{block['page']}" if doc["kind"] == "pdf" else f"¶{block['id'][1:]}"
                where = f"page {block['page']}" if doc["kind"] == "pdf" else f"block {block['id']}"
                tip = f"{entry['name']} — {where}\n{block['heading']}\n{block['text'][:400]}\n(click to open)"
                # Escape, and encode line breaks so a chip inside a Markdown table row doesn't break the row.
                tip = html.escape(tip, quote=True).replace("\n", "&#10;")
                out.append(f'<span class="cite" data-ok="1" data-cite="{html.escape(cid)}" '
                           f'data-claim="{html.escape(claim, quote=True)}" title="{tip}">'
                           f"{label} · {loc}</span>")
            else:
                out.append(f'<span class="cite bad" title="Source {html.escape(cid)} not found in the attached documents">'
                           f"{label} · ?</span>")
    out.append(text[at:])
    return "".join(out)


TEXT_FILES = tuple(outputs.MARKDOWN_TYPES)


CONVERTED = {".docx": "Written in Markdown; saved as a Word document.",
             ".xlsx": "Written in Markdown; saved as an Excel workbook (a sheet per ## heading, tables as cells).",
             ".pptx": "Written in Markdown; saved as a PowerPoint deck (a slide per ## heading)."}


def is_text_file(path: str) -> bool:
    return Path(path).suffix.lower() in TEXT_FILES


def streaming_view(text: str) -> str:
    """While an answer streams: Markdown-based files (.md/.docx/.xlsx/.pptx/.txt) show their text inline, other files a placeholder."""
    out = []
    for part in outputs.split_answer(text):
        if part["kind"] == "text":
            out.append(part["text"])
        elif is_text_file(part["path"]):
            out.append("\n\n" + part["content"] + ("" if part["complete"] else f"\n\n> 📄 writing **{part['path']}**…") + "\n\n")
        else:
            state = "ready" if part["complete"] else "writing…"
            out.append(f"\n\n> 📄 **{part['path']}** — {state} ({len(part['content']):,} characters)\n\n")
    return "".join(out)


def answer_summary_text(content: str) -> str:
    """The summary in an answer: the first document file's content, else the answer text without file blocks."""
    parts = outputs.split_answer(content)
    for part in parts:
        if part["kind"] == "file" and is_text_file(part["path"]):
            return part["content"].strip()
    return "".join(p["text"] for p in parts if p["kind"] == "text").strip()


def marked(text: str, spans: list) -> str:
    """HTML-escaped text with the given character spans wrapped in <mark>."""
    out, at = [], 0
    for s, e in sorted(spans):
        out += [html.escape(text[at:s]), f"<mark>{html.escape(text[s:e])}</mark>"]
        at = e
    out.append(html.escape(text[at:]))
    return "".join(out)


# ---------------------------------------------------------------- small dialogs

async def confirm(message: str, ok: str = "OK") -> bool:
    with ui.dialog() as dialog, ui.card().classes("w-[440px] max-w-full"):
        ui.label(message).classes("whitespace-pre-wrap")
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat no-caps")
            ui.button(ok, on_click=lambda: dialog.submit(True)).props("unelevated no-caps")
    result = await dialog
    dialog.delete()
    return bool(result)


async def ask_text(title: str, value: str, ok: str = "OK") -> str | None:
    with ui.dialog() as dialog, ui.card().classes("w-[480px] max-w-full"):
        ui.label(title).classes("whitespace-pre-wrap")
        inp = ui.input(value=value).classes("w-full").props("outlined dense autofocus")
        inp.on("keydown.enter", lambda: dialog.submit(inp.value))
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat no-caps")
            ui.button(ok, on_click=lambda: dialog.submit(inp.value)).props("unelevated no-caps")
    result = await dialog
    dialog.delete()
    return result


# ---------------------------------------------------------------- the page

class Workbench:
    def __init__(self):
        self.project: dict | None = None
        self.chat: dict | None = None
        self.right: str | None = None          # None | "files" | "context" | "source"
        self.source: dict | None = None        # {doc_id, label, block_id, claim, loc, page, zoom}
        self.fs_path: str | None = None        # current folder in the files panel (None = list of roots)
        self.fs_selected: set[str] = set()
        self.notice = ""
        self.project_notice = ""
        self.pending = False
        self.task: asyncio.Task | None = None
        self.busy = False
        self.docs: dict[str, dict] = {}
        self.editing: int | None = None         # index of the user message being edited
        self.fit_cache: dict = {}               # (chat, message, profile version) -> profile checks
        self.left_width = 260                   # drawer widths in px, changed by dragging their borders
        self.right_widths = {"source": 560, "files": 320}

    # ---------- feedback that survives refreshes

    def notify(self, *args, **kwargs):
        with self.root:
            ui.notify(*args, **kwargs)

    def download(self, *args, **kwargs):
        with self.root:
            ui.download(*args, **kwargs)

    # ---------- data helpers

    def doc(self, doc_id: str) -> dict | None:
        if doc_id not in self.docs:
            try:
                self.docs[doc_id] = documents.get(doc_id)
            except FileNotFoundError:
                return None
        return self.docs[doc_id]

    def entries(self) -> list[dict]:
        return (self.chat["docs"] if self.chat else []) + (self.project["context"] if self.project else [])

    def resolve(self, cid: str):
        """cid like "C1-p2-13"; label "*" means "whichever attached document has this block" (unique only)."""
        label, _, bid = cid.partition("-")
        if label == "*":
            hits = [d for d in self.entries()
                    if (doc := self.doc(d["doc_id"])) and any(b.get("id") == bid for b in doc["blocks"])]
            entry = hits[0] if len(hits) == 1 else None
        else:
            entry = next((d for d in self.entries() if d["label"].lower() == label.lower()), None)
        doc = self.doc(entry["doc_id"]) if entry else None
        block = next((b for b in doc["blocks"] if b.get("id") == bid), None) if doc else None
        return entry, doc, block

    def reload_project(self):
        if self.project:
            self.project = projects.get(self.project["id"])

    # ---------- layout

    def build(self):
        # Elements created in event handlers attach to the handler's slot, which a refresh may delete.
        # Dialogs therefore live under this stable root, and page JS runs through the client.
        self.client = ui.context.client
        self.root = ui.element("div")
        ui.add_css(CSS)
        ui.add_body_html(CITE_SCRIPT)
        ui.add_body_html(RESIZE_SCRIPT)
        ui.on("resize_drawer", self.on_resize, throttle=0.03)
        ui.page_title("LLM Workbench")
        ui.dark_mode(None)                      # follow the system setting
        ui.on("cite", lambda e: self.open_source(e.args.get("id", ""), e.args.get("claim", "")))

        self.left = ui.left_drawer(value=True, fixed=True).props(f"width={self.left_width} bordered breakpoint=700") \
            .classes("p-3")
        with self.left:
            ui.element("div").classes("wb-resizer").props('data-side=left').tooltip("Drag to resize")
            self.sidebar()
        with ui.header().classes("wb-header items-center gap-3 px-4 py-2"):
            self.topbar()
        self.drawer = ui.right_drawer(value=False, fixed=True).props("bordered breakpoint=700").classes("rightpanel p-0")
        with self.drawer:
            ui.element("div").classes("wb-resizer wb-resizer-right").props('data-side=right').tooltip("Drag to resize")
            self.right_panel()
        self.footer = ui.footer().classes("wb-footer px-4 pb-3 pt-1")
        with self.footer:
            self.composer()
        self.main()

    # ---------- sidebar

    @ui.refreshable
    def sidebar(self):
        with ui.column().classes("w-full h-full gap-1 no-wrap"):
            with ui.row().classes("items-center gap-2 px-1 pb-2"):
                ui.icon("article", color="primary").classes("text-xl")
                ui.label("LLM Workbench").classes("font-semibold")
            ui.button("+ New chat in project" if self.project else "+ New chat", on_click=self.new_chat) \
                .props("unelevated no-caps").classes("w-full")
            with ui.scroll_area().classes("w-full grow"):
                with ui.row().classes("w-full items-center justify-between px-1 pt-3"):
                    ui.label("Projects").classes("side-head")
                    ui.button(icon="add", on_click=self.new_project_dialog).props("flat dense round size=sm") \
                        .tooltip("New project")
                plist = projects.list_all()
                if not plist:
                    ui.button("Create your first project", on_click=self.new_project_dialog) \
                        .props("flat dense no-caps size=sm color=primary")
                for p in plist:
                    cls = ("in" if self.chat else "on") if self.project and self.project["id"] == p["id"] else ""
                    with ui.row().classes(f"side-item {cls} items-center gap-2 no-wrap {'fs-off' if p['missing'] else ''}") \
                            .on("click", lambda pid=p["id"]: self.open_project(pid)):
                        ui.icon("folder_special", size="xs").classes("muted")
                        ui.label(p["name"]).classes("ellipsis1")
                        ui.tooltip(f"Folder missing: {p['folder']}" if p["missing"] else p["folder"])

                with ui.row().classes("w-full items-center justify-between px-1 pt-3 no-wrap"):
                    ui.label(f"Chats · {self.project['name']}" if self.project else "Chats").classes("side-head ellipsis1")
                    if self.project:
                        ui.button("All chats", on_click=lambda: self.open_project(None)) \
                            .props("flat dense no-caps size=sm color=primary")
                clist = chats.list_all(self.project["id"] if self.project else None)
                if not clist:
                    ui.label("No chats yet.").classes("muted text-xs px-2")
                for c in clist:
                    cls = "on" if self.chat and self.chat["id"] == c["id"] else ""
                    with ui.row().classes(f"side-item {cls} items-center gap-1 no-wrap") \
                            .on("click", lambda cid=c["id"]: self.open_chat(cid)):
                        ui.label(c["title"]).classes("ellipsis1 grow")
                        if c["n_docs"]:
                            ui.badge(str(c["n_docs"])).props("outline")
                        ui.button(icon="close").props("flat dense round size=xs") \
                            .on("click.stop", lambda cid=c["id"]: self.delete_chat(cid))
            ui.button("Settings", icon="settings", on_click=self.settings_dialog).props("outline no-caps").classes("w-full")
            p = settings.provider()
            ui.label(f"{p['label']}: {p['model']}").classes("muted text-xs ellipsis1 px-1")

    # ---------- header

    @ui.refreshable
    def topbar(self):
        with ui.row().classes("grow items-center gap-1 no-wrap min-w-0"):
            if self.project:
                ui.button(self.project["name"], on_click=lambda: self.open_project(self.project["id"])) \
                    .props("flat dense no-caps color=primary").classes("font-semibold")
                if self.chat:
                    ui.label("›").classes("muted")
            title = self.chat["title"] if self.chat else ("" if self.project else "New chat")
            ui.label(title).classes("font-semibold ellipsis1")
        s = settings.load()
        ui.select({k: f"{p['label']} · {p['model']}" for k, p in s["providers"].items()}, value=s["active_provider"],
                  on_change=self.change_provider).props("dense outlined options-dense").classes("w-64")
        if self.chat or not self.project:
            ui.button("Files", icon="folder_open", on_click=lambda: self.toggle_right("files")) \
                .props(f"{'unelevated' if self.right == 'files' else 'outline'} no-caps")

    def change_provider(self, e):
        settings.update({"active_provider": e.value})
        self.sidebar.refresh()

    # ---------- main area

    @ui.refreshable
    def main(self):
        self.footer.set_visibility(not (self.project and not self.chat))
        if self.project and not self.chat:
            self.project_view()
            return
        self.msg_col = ui.column().classes("w-full max-w-[1100px] mx-auto gap-4 pb-4")
        with self.msg_col:
            if not self.chat or not self.chat["messages"]:
                with ui.column().classes("w-full items-center text-center mt-[12vh] gap-2"):
                    if self.project:
                        ui.label(f"New chat in {self.project['name']}").classes("text-xl font-semibold")
                        ui.label(f"The project instructions and {len(self.project['context'])} context document(s) are "
                                 "included automatically. Attach files from the project folder with Files; use "
                                 "Save to folder under an answer to keep it as a file.").classes("muted max-w-[540px]")
                    else:
                        ui.label("Ask anything, or attach documents to work with them").classes("text-xl font-semibold")
                        ui.label("Open Files to pick documents from your allowed folders, or use the 📎 button. "
                                 "Answers cite their sources — click a citation to see it highlighted in the original. "
                                 "For repeated tasks, create a project.").classes("muted max-w-[540px]")
            for i, m in enumerate(self.chat["messages"] if self.chat else []):
                self.render_message(m, i)

    def render_message(self, m: dict, index: int | None = None):
        if m["role"] == "user":
            if index is not None and index == self.editing:
                self.edit_box(m, index)
                return
            with ui.column().classes("w-full items-end gap-0 user-msg"):
                ui.label(m["content"]).classes("bubble")
                with ui.row().classes("msg-actions gap-0"):
                    ui.button(icon="content_copy", on_click=lambda m=m: self.copy(m["content"])) \
                        .props("flat dense round size=sm").tooltip("Copy")
                    if index is not None:
                        ui.button(icon="edit", on_click=lambda i=index: self.start_edit(i)) \
                            .props("flat dense round size=sm").tooltip("Edit and resend from here") \
                            .set_enabled(not self.pending)
            return
        with ui.column().classes("answer w-full gap-1"):
            parts = outputs.split_answer(m["content"])
            # Prose and the text of document files (with clickable citations) first …
            for part in parts:
                text = part["text"] if part["kind"] == "text" else part["content"] if is_text_file(part["path"]) else ""
                if text.strip():
                    ui.markdown(render_answer(text, self.resolve)).classes(
                        "file-text" if part["kind"] == "file" else "")
            # … then one download / preview box per file at the end.
            for part in parts:
                if part["kind"] == "file":
                    self.file_card(part)
            if self.project and m["content"] and not m.get("error"):
                self.fit_row(m)
            if not m["content"] and not m.get("error"):
                ui.label("(empty answer)").classes("muted italic")
            if m.get("error"):
                ui.label(f"⚠ {m['error']}").classes("err text-xs")
            with ui.row().classes("items-center gap-2 text-xs muted"):
                ui.label(m.get("model", ""))
                if m["content"]:
                    ui.button(icon="content_copy", on_click=lambda m=m: self.copy(m["content"])) \
                        .props("flat dense round size=xs").tooltip("Copy answer (Markdown)")
                if (m.get("context") or {}).get("truncated"):
                    ui.label("· documents trimmed to fit context")
                if self.project and m["content"]:
                    ui.button("Save to folder", on_click=lambda m=m: self.save_to_folder(m)) \
                        .props("flat dense no-caps size=sm color=primary")
                    with ui.dropdown_button("Add to knowledge base", icon="school", auto_close=True) \
                            .props("flat dense no-caps size=sm color=primary"):
                        ui.item("Save as example summary", on_click=lambda m=m: self.save_as_example(m)) \
                            .tooltip("Keep this answer (and the chat's documents) as an example the profile is learned from")
                        ui.item("Use as summary profile…", on_click=lambda m=m: self.use_as_profile(m)) \
                            .tooltip("Use this answer, e.g. a summary structure you agreed on, as the project's profile")

    def fit_row(self, m: dict):
        """How a drafted summary compares with the project's profile targets (measured in code, no LLM)."""
        prof = knowledge.get_profile(self.project)
        if not prof or not prof.get("targets"):
            return
        key = (self.chat["id"] if self.chat else "", m.get("created"), prof["version"])
        if key not in self.fit_cache:
            docs = [(e["label"], d) for e in self.entries() if (d := self.doc(e["doc_id"]))]
            try:
                self.fit_cache[key] = knowledge.check_draft(self.project, answer_summary_text(m["content"]), docs)
            except Exception:
                self.fit_cache[key] = []
        checks = self.fit_cache[key]
        if not checks:
            return
        with ui.row().classes("items-center gap-1 text-xs fit-row"):
            ui.label(f"Profile v{prof['version']} check:").classes("muted")
            for c in checks:
                icon, cls = ("check_circle", "fit-ok") if c["ok"] else ("info", "fit-info") if c["ok"] is None \
                    else ("warning", "fit-warn")
                with ui.element("span").classes(f"fitchip {cls}"):
                    ui.icon(icon, size="14px")
                    ui.label(f"{c['label']}: {c['text']}")

    def with_sources(self, path: str, content: str) -> str:
        """Replace citation IDs with [1], [2]… and append a Sources list, so a saved file stays traceable
        outside the app. CSV/JSON files are left unchanged."""
        if Path(path).suffix.lower() not in outputs.MARKDOWN_TYPES:
            return content
        numbers: dict[str, int] = {}
        sources: list[str] = []

        def ref(items):
            out = []
            for cid, entry, doc, block in items:
                if not block:
                    out.append(f"[{cid}?]")
                    continue
                key = f"{entry['doc_id']}:{block['id']}"
                if key not in numbers:
                    numbers[key] = len(numbers) + 1
                    where = f"p.{block['page']}" if doc["kind"] == "pdf" else f"block {block['id']}"
                    quote_ = block["text"][:160] + ("…" if len(block["text"]) > 160 else "")
                    sources.append(f"{numbers[key]}. {entry['name']}, {where}"
                                   + (f" ({block['heading']})" if block["heading"] else "") + f": \"{quote_}\"")
                out.append(f"[{numbers[key]}]")
            return "".join(out)

        pieces, at = [], 0
        for start, end, items in _citation_groups(content, self.resolve):
            pieces += [content[at:start], ref(items)]
            at = end
        body = ("".join(pieces) + content[at:]).rstrip()
        if sources:
            body += "\n\n## Sources\n\n" + "\n".join(sources) + "\n"
        return body

    def file_card(self, part: dict):
        """A file the model wrote in its answer: preview, Save to project folder, Download."""
        path, content = part["path"], part["content"]
        with ui.column().classes("card gap-1").style("padding:10px 12px"):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.icon("description", size="sm").classes("muted")
                type_badge(path)
                ui.label(path).classes("font-medium ellipsis1 grow")
                ui.label(f"{len(content):,} characters" + ("" if part["complete"] else " · incomplete")) \
                    .classes("muted text-xs")
            note = CONVERTED.get(Path(path).suffix.lower())
            if note:
                ui.label(note).classes("muted text-xs")
            with ui.row().classes("gap-2 items-center"):
                if self.project:
                    ui.button("Save to project folder", icon="save",
                              on_click=lambda: self.save_file(path, self.with_sources(path, content))) \
                        .props("unelevated dense no-caps size=sm")
                ui.button("Download", icon="download",
                          on_click=lambda: self.download(outputs.to_bytes(path, self.with_sources(path, content)),
                                                       Path(path).name)) \
                    .props("outline dense no-caps size=sm")
                if citations.has_citations(content):
                    ui.label("Citations become numbered references with a Sources list.").classes("muted text-xs")
            with ui.expansion("Preview as saved").classes("w-full text-sm").props("dense"):
                if Path(path).suffix.lower() in (".md", ".docx", ".xlsx", ".pptx"):
                    saved = self.with_sources(path, content)
                    body, sep, sources = saved.partition("\n## Sources\n")
                    # File names like Harborline_Home_Furnishings.pdf would render "_Home_" in italics.
                    ui.markdown(body + sep + sources.replace("_", "\\_"))
                else:
                    ui.code(content, language=None).classes("w-full text-xs")

    async def save_file(self, path: str, content: str):
        try:
            dest = projects.write_output(self.project["id"], path, content)
        except FileExistsError:
            if not await self.confirm(f"{path} already exists in the project folder. Overwrite it?", "Overwrite"):
                return
            dest = projects.write_output(self.project["id"], path, content, overwrite=True)
        except Exception as e:
            self.notify(str(e), type="negative")
            return
        self.notify(f"Saved {Path(dest).name}", type="positive")
        self.set_notice(f"✓ Saved to {dest}")

    # ---------- copy / edit sent messages

    def copy(self, text: str):
        with self.root:
            ui.clipboard.write(text)
        self.notify("Copied", position="bottom", timeout=1200)

    def start_edit(self, index: int):
        if self.pending:
            return
        self.editing = index
        self.main.refresh()
        self.client.run_javascript("document.querySelector('.edit-box textarea')?.focus()")

    def edit_box(self, m: dict, index: int):
        later = len(self.chat["messages"]) - index - 1
        with ui.column().classes("w-full items-end gap-1 edit-box"):
            box = ui.textarea(value=m["content"]).classes("w-full max-w-[85%]") \
                .props("outlined autogrow input-style='max-height:300px'")
            box.on("keydown.enter.exact.prevent", lambda: self.resend(index, box.value))
            with ui.row().classes("items-center gap-2"):
                if later:
                    ui.label(f"Sending replaces the {later} message{'s' if later != 1 else ''} after this one.") \
                        .classes("muted text-xs")
                ui.button("Cancel", on_click=self.cancel_edit).props("flat dense no-caps")
                ui.button("Send", on_click=lambda: self.resend(index, box.value)).props("unelevated dense no-caps")

    def cancel_edit(self):
        self.editing = None
        self.main.refresh()

    async def resend(self, index: int, text: str):
        """Continue the conversation from an earlier message: it and everything after it are replaced
        (kept in chat["earlier_versions"], not deleted)."""
        text = (text or "").strip()
        if not text or self.pending:
            return
        chat = chats.get(self.chat["id"])
        removed = chat["messages"][index:]
        chat.setdefault("earlier_versions", []).append({"at": time.time(), "messages": removed})
        chat["messages"] = chat["messages"][:index]
        chats.save(chat)
        self.chat, self.editing = chat, None
        await self.send(text)

    # ---------- composer

    @ui.refreshable
    def composer(self):
        with ui.column().classes("w-full max-w-[1100px] mx-auto gap-2"):
            if self.notice:
                with ui.row().classes("notice items-start justify-between no-wrap"):
                    ui.label(self.notice).classes("whitespace-pre-wrap")
                    ui.button(icon="close", on_click=lambda: self.set_notice("")).props("flat dense round size=xs")
            chips = (self.chat["docs"] if self.chat else [])
            if chips or (self.project and self.project["context"]):
                with ui.row().classes("gap-2"):
                    if self.project and self.project["context"]:
                        n = len(self.project["context"])
                        with ui.element("span").classes("chip").style("background:var(--wb-accent-soft);padding-right:10px"):
                            ui.html(f"<b>C1–C{n}</b>&nbsp;project context")
                            ui.tooltip("\n".join(f"{c['label']} {c['name']}" for c in self.project["context"])) \
                                .classes("whitespace-pre-wrap")
                    for d in chips:
                        doc = self.doc(d["doc_id"])
                        with ui.element("span").classes("chip"):
                            ui.html(f"<b>{d['label']}</b>&nbsp;{html.escape(d['name'])}")
                            if doc:
                                ui.label(f"· {doc['pages']}p" if doc["kind"] == "pdf" else f"· {doc['kind']}").classes("muted")
                            ui.button(icon="close", on_click=lambda did=d["doc_id"]: self.detach(did)) \
                                .props("flat dense round size=xs").set_enabled(not self.pending)
            with ui.row().classes("w-full items-end gap-2 no-wrap p-2 rounded-xl") \
                    .style("background:var(--wb-panel);border:1px solid var(--wb-border)"):
                up = ui.upload(multiple=True, auto_upload=True, on_multi_upload=self.on_chat_upload, on_rejected=rejected) \
                    .props(f'accept="{ACCEPT}"').classes("hidden")
                ui.button(icon="attach_file", on_click=lambda: up.run_method("pickFiles")) \
                    .props("flat round dense").tooltip("Upload files").set_enabled(not self.busy)
                self.input = ui.textarea(placeholder="Parsing documents…" if self.busy else
                                         "Message (Enter to send, Shift+Enter for a new line)") \
                    .props("autogrow borderless dense input-style='max-height:200px'").classes("grow")
                self.input.on("keydown.enter.exact.prevent", self.send)
                if self.pending:
                    ui.button("Stop", on_click=self.stop).props("outline no-caps")
                else:
                    ui.button("Send", on_click=self.send).props("unelevated no-caps").set_enabled(not self.busy)

    def set_notice(self, text: str):
        self.notice = text
        self.composer.refresh()

    # ---------- right panel

    def toggle_right(self, kind: str | None):
        self.right = None if self.right == kind or kind is None else kind
        if self.right in ("files", "context"):
            self.fs_selected = set()
            self.fs_path = self.project["folder"] if self.project else None
        self.drawer.props(f"width={self.right_width()}")
        self.drawer.set_value(self.right is not None)
        self.right_panel.refresh()
        self.topbar.refresh()

    def right_width(self) -> int:
        return self.right_widths["source" if self.right == "source" else "files"]

    def on_resize(self, e):
        """Drag handle on a drawer border: set its width (clamped so the chat column stays usable)."""
        side, width = e.args.get("side"), int(e.args.get("width") or 0)
        if side == "left":
            self.left_width = max(180, min(520, width))
            self.left.props(f"width={self.left_width}")
        elif side == "right":
            width = max(260, min(1100, width))
            if e.args.get("initial"):
                self.right_widths["source"] = width     # remembered width applies to the source panel
            else:
                self.right_widths["source" if self.right == "source" else "files"] = width
            if self.right:
                self.drawer.props(f"width={self.right_width()}")

    @ui.refreshable
    def right_panel(self):
        if self.right in ("files", "context"):
            self.files_panel()
        elif self.right == "source" and self.source:
            self.source_panel()

    def panel_head(self, title: str):
        with ui.row().classes("w-full items-center justify-between px-4 py-3 no-wrap") \
                .style("border-bottom:1px solid var(--wb-border)"):
            ui.label(title).classes("font-semibold")
            ui.button(icon="close", on_click=lambda: self.toggle_right(None)).props("flat dense round size=sm")

    def files_panel(self):
        ctx = self.right == "context"
        root_locked = bool(self.project)
        with ui.column().classes("w-full h-full no-wrap gap-0"):
            self.panel_head("Add to project context" if ctx else "Project files" if self.project else "Files")
            with ui.scroll_area().classes("grow w-full"):
                if self.fs_path is None:
                    ui.label("Allowed folders").classes("muted text-xs px-2")
                    roots = fs.roots()
                    if not roots:
                        ui.label("No folders yet — add one in Settings → Folders.").classes("muted text-xs px-2")
                    for r in roots:
                        with ui.element("div").classes(f"fs-row {'click' if r['exists'] else 'fs-off'}") \
                                .on("click", lambda p=r["path"], ok=r["exists"]: ok and self.fs_open(p)):
                            ui.icon("folder", size="xs").classes("muted")
                            ui.label(r["name"]).classes("ellipsis1 grow")
                            if not r["exists"]:
                                ui.label("missing").classes("muted text-xs")
                else:
                    try:
                        listing = fs.list_dir(self.fs_path, [self.project["folder"]] if self.project else None)
                    except Exception as e:
                        ui.label(str(e)).classes("err text-xs px-2")
                        return
                    with ui.row().classes("gap-1 items-center px-2 pb-2 text-xs"):
                        if not root_locked:
                            ui.button("Folders", on_click=lambda: self.fs_open(None)).props("flat dense no-caps size=sm")
                            ui.label("/")
                        ui.button(Path(listing["root"]).name, on_click=lambda: self.fs_open(listing["root"])) \
                            .props("flat dense no-caps size=sm")
                        rel = listing["path"][len(listing["root"]):].lstrip("/\\")
                        if rel:
                            ui.label(f"/ {rel}").classes("muted wrap-anywhere")
                    if listing["parent"]:
                        with ui.element("div").classes("fs-row click").on("click", lambda: self.fs_open(listing["parent"])):
                            ui.icon("arrow_upward", size="xs").classes("muted")
                            ui.label("..")
                    if not listing["entries"]:
                        ui.label("Empty folder.").classes("muted text-xs px-2")
                    for e in listing["entries"]:
                        if e["is_dir"]:
                            with ui.element("div").classes("fs-row click").on("click", lambda p=e["path"]: self.fs_open(p)):
                                ui.icon("folder", size="xs").classes("muted")
                                ui.label(e["name"]).classes("ellipsis1")
                        else:
                            with ui.element("div").classes(f"fs-row {'' if e['supported'] else 'fs-off'}"):
                                ui.checkbox(value=e["path"] in self.fs_selected,
                                            on_change=lambda ev, p=e["path"]: self.fs_toggle(p, ev.value)) \
                                    .props("dense").set_enabled(e["supported"])
                                type_badge(e["name"])
                                ui.label(e["name"]).classes("ellipsis1 grow").tooltip(e["name"])
                                ui.label(file_size(e["size"])).classes("muted text-xs")
            with ui.column().classes("w-full p-3 gap-1").style("border-top:1px solid var(--wb-border)"):
                n = len(self.fs_selected)
                label = ("Add to context" if ctx else "Attach to chat") + (f" ({n})" if n else "")
                ui.button("Parsing…" if self.busy else label, on_click=self.fs_attach) \
                    .props("unelevated no-caps").classes("w-full").set_enabled(bool(n) and not self.busy)
                ui.label("PDF, Word, Text, Markdown" + (" · limited to the project folder" if self.project else "")) \
                    .classes("muted text-xs")

    def fs_open(self, path):
        self.fs_path = path
        self.right_panel.refresh()

    def fs_toggle(self, path, on):
        (self.fs_selected.add if on else self.fs_selected.discard)(path)
        self.right_panel.refresh()

    async def fs_attach(self):
        paths = sorted(self.fs_selected)
        self.busy = True
        self.right_panel.refresh()
        try:
            if self.right == "context" and self.project:
                metas = await asyncio.to_thread(projects.add_paths, self.project["id"], paths)
                self.project_notice = report(metas)
                self.reload_project()
                self.main.refresh()
            else:
                metas = await asyncio.to_thread(self.ingest_paths, paths)
                self.attach_metas(metas)
            self.fs_selected = set()
        finally:
            self.busy = False
            self.right_panel.refresh()

    def ingest_paths(self, paths):
        roots = [self.project["folder"]] if self.project else None
        out = []
        for path in paths:
            try:
                out.append({"ok": True, **documents.meta(documents.ingest(fs.check(path, roots)))})
            except Exception as e:
                out.append({"ok": False, "name": Path(path).name, "error": str(e)})
        return out

    # ---------- source panel (M2)

    def open_source(self, cid: str, claim: str):
        entry, doc, block = self.resolve(cid)
        if block:
            self.open_block(entry["doc_id"], block["id"], claim, cid)

    def open_block(self, doc_id: str, block_id: str, claim: str, label: str):
        try:
            loc = documents.locate(doc_id, block_id, claim)
        except Exception as e:                 # never fail silently: say why the source can't be shown
            self.notify(f"Can't open the source of {label}: {e}", type="negative", multi_line=True,
                        timeout=0, close_button=True)
            return
        self.source = {"doc_id": doc_id, "label": label, "block_id": block_id, "claim": claim,
                       "loc": loc, "page": loc["block"]["page"], "zoom": 1.0}
        self.right = None
        self.toggle_right("source")

    def source_panel(self):
        s, loc = self.source, self.source["loc"]
        is_pdf = loc["kind"] == "pdf"
        with ui.column().classes("w-full h-full no-wrap gap-0"):
            with ui.row().classes("w-full items-center justify-between px-4 py-3 no-wrap") \
                    .style("border-bottom:1px solid var(--wb-border)"):
                with ui.row().classes("items-center gap-2"):
                    ui.label("Source").classes("font-semibold")
                    ui.html(f'<span class="cite" style="cursor:default">{html.escape(s["label"])}</span>')
                ui.button(icon="close", on_click=lambda: self.toggle_right(None)).props("flat dense round size=sm")

            with ui.column().classes("w-full px-4 py-2 gap-1").style("border-bottom:1px solid var(--wb-border)"):
                with ui.row().classes("items-center gap-2 no-wrap w-full"):
                    type_badge(loc["name"])
                    ui.label(loc["name"]).classes("font-medium ellipsis1")
                if is_pdf:
                    with ui.row().classes("items-center gap-1"):
                        ui.button(icon="chevron_left", on_click=lambda: self.source_page(-1)) \
                            .props("flat dense round size=sm").set_enabled(s["page"] > 1)
                        ui.label(f"Page {s['page']} / {loc['pages']}").classes("text-xs")
                        ui.button(icon="chevron_right", on_click=lambda: self.source_page(1)) \
                            .props("flat dense round size=sm").set_enabled(s["page"] < loc["pages"])
                        ui.separator().props("vertical").classes("mx-1")
                        ui.button(icon="remove", on_click=lambda: self.source_zoom(-0.5)) \
                            .props("flat dense round size=sm").set_enabled(s["zoom"] > 1)
                        ui.label("Fit" if s["zoom"] == 1 else f"{int(s['zoom'] * 100)}%").classes("text-xs w-9 text-center")
                        ui.button(icon="add", on_click=lambda: self.source_zoom(0.5)) \
                            .props("flat dense round size=sm").set_enabled(s["zoom"] < 3)
                        if s["page"] != loc["block"]["page"]:
                            ui.button("Back to cited page", on_click=lambda: self.source_page(0)) \
                                .props("flat dense no-caps size=sm color=primary")

            b = loc["block"]
            if is_pdf:
                with ui.scroll_area().classes("grow w-full pdf-scroll"):
                    url = (f"/api/documents/{s['doc_id']}/page/{s['page']}.png?zoom={min(4, 2 * s['zoom'])}"
                           f"&block={quote(s['block_id'])}&claim={quote(s['claim'][:800])}")
                    ui.image(url).classes("shadow").style(f"width:{int(100 * s['zoom'])}%;max-width:none")
                if s["page"] == b["page"]:
                    ys = [r[2] for r in (loc["sentence_rects"] or b["rects"]) if r[0] == s["page"] - 1]
                    size = loc["page_sizes"].get(str(s["page"] - 1)) or loc["page_sizes"].get(s["page"] - 1)
                    if ys and size:
                        # Scroll so the highlight sits near the top, once the page image has loaded (done in the
                        # browser: the image's load event does not reliably reach Python).
                        frac = max(0.0, min(ys) / size[1])
                        js = ("(() => { const c = document.querySelector('.rightpanel .pdf-scroll .q-scrollarea__container');"
                              " const img = c && c.querySelector('img'); if (!img) return;"
                              f" const go = () => {{ c.scrollTop = Math.max(0, {frac:.4f} * img.offsetHeight - 60); }};"
                              " if (img.complete && img.naturalHeight) go(); else img.addEventListener('load', go, {once: true}); })()")
                        ui.timer(0.15, lambda: self.client.run_javascript(js), once=True)
            else:
                doc = self.doc(s["doc_id"])
                parts = []
                for blk in doc["blocks"]:
                    if blk["type"] == "heading":
                        parts.append(f'<div class="tb-h">{html.escape(blk["text"])}</div>')
                        continue
                    cited = blk["id"] == b["id"]
                    body = marked(blk["text"], loc["sentence_spans"]) if cited else html.escape(blk["text"])
                    parts.append(f'<div id="tb-{blk["id"]}" class="tb {"cited" if cited else ""} '
                                 f'{"tb-table" if blk["type"] == "table" else ""}"><span class="tb-id">{blk["id"]}</span>{body}</div>')
                with ui.scroll_area().classes("grow w-full pdf-scroll"):
                    ui.html(f'<div class="text-view">{"".join(parts)}</div>')
                ui.timer(0.3, lambda: self.client.run_javascript(
                    f"document.getElementById('tb-{b['id']}')?.scrollIntoView({{block:'center'}})"), once=True)

    def source_page(self, delta: int):
        s = self.source
        s["page"] = s["loc"]["block"]["page"] if delta == 0 else max(1, min(s["loc"]["pages"], s["page"] + delta))
        self.right_panel.refresh()

    def source_zoom(self, delta: float):
        self.source["zoom"] = max(1.0, min(3.0, self.source["zoom"] + delta))
        self.right_panel.refresh()

    # ---------- navigation

    def refresh_all(self):
        self.sidebar.refresh()
        self.topbar.refresh()
        self.main.refresh()
        self.composer.refresh()

    def open_project(self, pid: str | None):
        if self.pending:
            return
        self.chat, self.notice, self.project_notice = None, "", ""
        self.editing = None
        try:
            self.project = projects.get(pid) if pid else None
        except FileNotFoundError as e:
            self.notify(str(e), type="negative")
            self.project = None
        if self.right:
            self.toggle_right(None)
        self.refresh_all()

    def open_chat(self, cid: str):
        if self.pending:
            return
        self.chat, self.notice, self.editing = chats.get(cid), "", None
        if self.right in ("context", "source"):
            self.toggle_right(None)
        self.refresh_all()

    def new_chat(self):
        if self.pending:
            return
        self.notice, self.editing = "", None
        self.chat = chats.create(self.project["id"]) if self.project else None
        if self.right == "context":
            self.toggle_right(None)
        self.refresh_all()

    def ensure_chat(self) -> dict:
        if not self.chat:
            self.chat = chats.create(self.project["id"] if self.project else None)
        return self.chat

    async def confirm(self, message: str, ok: str = "OK") -> bool:
        with self.root:
            return await confirm(message, ok)

    async def delete_chat(self, cid: str):
        if not await self.confirm("Delete this chat? Attached files are not deleted.", "Delete"):
            return
        chats.delete(cid)
        if self.chat and self.chat["id"] == cid:
            self.chat = None
        self.refresh_all()

    # ---------- attachments

    def attach_metas(self, metas: list[dict]):
        self.notice = report(metas, "Attached")
        good = [m["id"] for m in metas if m.get("ok")]
        if good:
            chat = self.ensure_chat()
            chats.attach(chat, good)
            chats.save(chat)
        self.refresh_all()

    def detach(self, doc_id: str):
        chats.detach(self.chat, doc_id)
        chats.save(self.chat)
        self.refresh_all()

    async def on_chat_upload(self, e: events.MultiUploadEventArguments):
        e.sender.run_method("reset")
        self.busy = True
        self.composer.refresh()
        try:
            metas = await asyncio.to_thread(self.save_uploads, [(n, c.read()) for n, c in zip(e.names, e.contents)])
            self.attach_metas(metas)
        finally:
            self.busy = False
            self.composer.refresh()

    @staticmethod
    def save_uploads(items) -> list[dict]:
        out = []
        for name, data in items:
            name = Path(name).name
            if not supported(name):
                out.append({"ok": False, "name": name, "error": "unsupported file type"})
                continue
            safe = re.sub(r"[^\w.\- ]", "_", name)
            dest = settings.UPLOADS_DIR / f"{time.time_ns() % 10**10}_{safe}"
            dest.write_bytes(data)
            try:
                out.append({**documents.meta(documents.ingest(dest, name=name)), "ok": True, "name": name})
            except Exception as ex:
                out.append({"ok": False, "name": name, "error": str(ex)})
        return out

    # ---------- sending

    async def send(self, text: str | None = None):
        from_input = text is None
        text = ((self.input.value or "") if from_input else text).strip()
        if not text or self.pending:
            return
        if from_input:
            self.input.value = ""
        chat = self.ensure_chat()
        p = settings.provider()
        project = projects.get(chat["project_id"]) if chat.get("project_id") else None
        messages, info = chats.build_messages(chat, text, p.get("context_tokens", 8192), project)
        chat["messages"].append({"role": "user", "content": text, "created": time.time()})
        if chat["title"] == "New chat":
            chat["title"] = re.sub(r"\s+", " ", text)[:60]
        chats.save(chat)

        self.pending, self.notice = True, ""
        self.sidebar.refresh()
        self.topbar.refresh()
        self.main.refresh()            # shows the user message
        self.composer.refresh()        # Stop button
        with self.msg_col:
            with ui.column().classes("answer w-full gap-1"):
                status = ui.label().classes("muted")
                md = ui.markdown("")
        parts: list[str] = []
        t0 = time.time()
        docs_note = f" {info['docs']} document(s)" if info["docs"] else ""

        def tick():
            if parts:
                status.set_visibility(False)
                md.set_content(render_answer(streaming_view("".join(parts)), self.resolve))
            else:
                status.set_text(f"Reading{docs_note} (~{info['prompt_tokens_est']:,} tokens)… {int(time.time() - t0)}s")
            self.client.run_javascript("window.scrollTo(0, document.body.scrollHeight)")

        tick()
        with self.msg_col:
            timer = ui.timer(0.25, tick)

        async def run():
            async for chunk in llm.stream_chat(messages, p):
                parts.append(chunk)

        error = None
        self.task = asyncio.create_task(run())
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        except llm.LLMError as e:
            error = str(e)
        except Exception as e:                  # keep the UI usable whatever happens
            error = f"{type(e).__name__}: {e}"
        finally:
            timer.cancel()
            self.task = None
            if parts or error:
                msg = {"role": "assistant", "content": "".join(parts), "created": time.time(),
                       "model": p["model"], "context": info}
                if error:
                    msg["error"] = error
                fresh = chats.get(chat["id"])
                fresh["messages"].append(msg)
                chats.save(fresh)
            self.chat = chats.get(chat["id"])
            self.pending = False
            self.refresh_all()
            self.client.run_javascript("window.scrollTo(0, document.body.scrollHeight)")

    def stop(self):
        if self.task:
            self.task.cancel()

    async def save_to_folder(self, m: dict):
        with self.root:
            name = await ask_text(f"Save this answer in the project folder as:\n{self.project['folder']}",
                                  f"{slug(self.chat['title'])}.md", "Save")
        if not name:
            return
        try:
            path = projects.write_output(self.project["id"], name, m["content"])
        except FileExistsError:
            if not await self.confirm(f"{name} already exists. Overwrite it?", "Overwrite"):
                return
            path = projects.write_output(self.project["id"], name, m["content"], overwrite=True)
        except Exception as e:
            self.notify(str(e), type="negative")
            return
        self.set_notice(f"Saved to {path}")

    # ---------- project page

    def project_view(self):
        p = self.project
        with ui.column().classes("w-full max-w-[820px] mx-auto gap-4 pb-8"):
            with ui.column().classes("gap-0 w-full"):
                name = ui.input(value=p["name"]).props("borderless dense input-class='text-2xl font-semibold'").classes("w-full")
                name.on("blur", lambda: self.rename_project(name.value))
                name.on("keydown.enter", lambda: self.rename_project(name.value))
                with ui.row().classes("items-center gap-1 muted text-xs no-wrap"):
                    ui.icon("folder", size="xs")
                    ui.html(f"<code class='wrap-anywhere'>{html.escape(p['folder'])}</code>")
                    ui.tooltip("The assistant can only read and write inside this folder")

            with ui.column().classes("card gap-2"):
                with ui.row().classes("w-full items-baseline justify-between"):
                    ui.label("Instructions").classes("font-semibold text-[15px]")
                    ui.label("Applied to every chat in this project").classes("muted text-xs")
                instr = ui.textarea(value=p["instructions"], placeholder="Describe the task, e.g. how summaries should "
                                    "be structured, their length and tone…").props("outlined autogrow").classes("w-full")
                with ui.row().classes("w-full justify-end"):
                    ui.button("Save instructions", on_click=lambda: self.save_instructions(instr.value)) \
                        .props("unelevated no-caps")

            with ui.column().classes("card gap-2"):
                with ui.row().classes("w-full items-baseline justify-between"):
                    ui.label("Context").classes("font-semibold text-[15px]")
                    ui.label("Background documents included in every chat, cited as C1, C2…").classes("muted text-xs")
                if not p["context"]:
                    ui.label("No context yet.").classes("muted text-xs")
                source_label = {"folder": "from folder", "upload": "uploaded", "text": "pasted"}
                for c in p["context"]:
                    d = self.doc(c["doc_id"])
                    with ui.row().classes("w-full items-center gap-3 no-wrap py-1").style("border-bottom:1px solid var(--wb-border)"):
                        ui.label(c["label"]).classes("font-bold w-7").style("color:var(--wb-accent)")
                        type_badge(c["name"])
                        ui.label(c["name"]).classes("ellipsis1 grow").tooltip(c["path"])
                        pages = f"{d['pages']} pages · " if d and d["kind"] == "pdf" else ""
                        ui.label(pages + source_label[c["source"]]).classes("muted text-xs")
                        ui.button(icon="close", on_click=lambda c=c: self.remove_context(c)).props("flat dense round size=xs")
                with ui.row().classes("gap-2 items-center"):
                    up = ui.upload(multiple=True, auto_upload=True, on_multi_upload=self.on_context_upload, on_rejected=rejected) \
                        .props(f'accept="{ACCEPT}"').classes("hidden")
                    ui.button("Upload files…", on_click=lambda: up.run_method("pickFiles")).props("outline no-caps")
                    ui.button("Add from project folder…", on_click=lambda: self.toggle_right("context")) \
                        .props("outline no-caps")
                    ui.button("Paste text…", on_click=self.paste_dialog).props("outline no-caps")
                    if self.busy:
                        ui.spinner(size="sm")
                if self.project_notice:
                    with ui.row().classes("notice items-start justify-between no-wrap"):
                        ui.label(self.project_notice).classes("whitespace-pre-wrap")
                        ui.button(icon="close", on_click=lambda: self.set_project_notice("")) \
                            .props("flat dense round size=xs")

            self.knowledge_card(p)

            with ui.column().classes("card gap-1"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Chats").classes("font-semibold text-[15px]")
                    ui.button("+ New chat in project", on_click=self.new_chat).props("unelevated no-caps")
                clist = chats.list_all(p["id"])
                if not clist:
                    ui.label("No chats yet.").classes("muted text-xs")
                for c in clist:
                    with ui.element("div").classes("fs-row click").on("click", lambda cid=c["id"]: self.open_chat(cid)):
                        ui.label(c["title"]).classes("ellipsis1 grow")
                        ui.label(time.strftime("%Y-%m-%d %H:%M", time.localtime(c["updated"]))).classes("muted text-xs")

            with ui.row().classes("w-full justify-end"):
                ui.button("Remove project from app", on_click=self.remove_project) \
                    .props("flat dense no-caps size=sm color=negative")

    def set_project_notice(self, text: str):
        self.project_notice = text
        self.main.refresh()

    def rename_project(self, name: str):
        if name.strip() and name != self.project["name"]:
            self.project = projects.update(self.project["id"], name=name)
            self.sidebar.refresh()
            self.topbar.refresh()

    def save_instructions(self, text: str):
        self.project = projects.update(self.project["id"], instructions=text)
        self.notify("Instructions saved", type="positive")

    async def remove_context(self, c: dict):
        msg = (f"Remove {c['name']} from context? The file stays in the folder." if c["source"] == "folder"
               else f"Remove {c['name']} from context? Its copy in .workbench/context is deleted.")
        if await self.confirm(msg, "Remove"):
            self.project = projects.remove_context(self.project["id"], c["doc_id"])
            self.main.refresh()

    async def on_context_upload(self, e: events.MultiUploadEventArguments):
        e.sender.run_method("reset")
        items = [(n, c.read()) for n, c in zip(e.names, e.contents)]
        self.busy = True
        self.main.refresh()
        try:
            metas = await asyncio.to_thread(lambda: [projects.add_upload(self.project["id"], n, d) for n, d in items])
            self.project_notice = report(metas, "Uploaded")
            self.reload_project()
        finally:
            self.busy = False
            self.main.refresh()
            self.composer.refresh()

    async def paste_dialog(self):
        with self.root, ui.dialog() as dialog, ui.card().classes("w-[560px] max-w-full"):
            ui.label("Paste text into project context").classes("font-semibold")
            title = ui.input("Title (optional)").classes("w-full").props("outlined dense")
            text = ui.textarea("Text").classes("w-full").props("outlined autogrow input-style='min-height:160px'")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat no-caps")
                ui.button("Add to context", on_click=lambda: dialog.submit((title.value, text.value))) \
                    .props("unelevated no-caps")
        result = await dialog
        dialog.delete()
        if result and result[1].strip():
            meta = projects.add_text(self.project["id"], result[0] or "Pasted text", result[1])
            self.project_notice = report([meta])
            self.reload_project()
            self.main.refresh()

    async def remove_project(self):
        p = self.project
        if await self.confirm(f'Remove "{p["name"]}" from the app? Its chats are deleted. The folder and its .workbench data '
                         "stay on disk, so you can reopen it later by creating a project on the same folder.", "Remove"):
            chats.delete_project_chats(p["id"])
            projects.forget(p["id"])
            self.open_project(None)

    # ---------- knowledge base (examples + summary profile)

    def knowledge_card(self, p: dict):
        try:
            examples = knowledge.list_examples(p["id"])
            prof = knowledge.get_profile(p)
        except Exception as e:
            ui.label(f"Knowledge base unavailable: {e}").classes("err text-xs")
            return
        with ui.column().classes("card gap-2"):
            with ui.row().classes("w-full items-baseline justify-between"):
                ui.label("Knowledge base").classes("font-semibold text-[15px]")
                ui.label("Examples teach the assistant your summary format").classes("muted text-xs")

            ui.label("Examples (source document → expected summary)").classes("text-sm font-medium")
            if not examples:
                ui.label("No examples yet. Add a source PDF with the summary you expect, or save a good answer "
                         "from a chat with Add to knowledge base.").classes("muted text-xs")
            for ex in examples:
                with ui.row().classes("w-full items-center gap-2 no-wrap py-1").style("border-bottom:1px solid var(--wb-border)"):
                    ui.icon("school", size="xs").classes("muted")
                    ui.label(ex["name"]).classes("ellipsis1 font-medium")
                    ui.label(("← " + ", ".join(ex["sources"])) if ex["sources"] else "(no source document)") \
                        .classes("muted text-xs ellipsis1 grow")
                    ui.badge("from chat" if ex["origin"] == "chat" else "uploaded").props("outline")
                    ui.button(icon="insights", on_click=lambda ex=ex: self.view_analysis(ex)) \
                        .props("flat dense round size=xs").tooltip("Analysis: where each sentence comes from, "
                                                                  "coverage, rewriting, length").set_enabled(bool(ex["sources"]))
                    ui.button(icon="visibility", on_click=lambda ex=ex: self.view_example(ex)) \
                        .props("flat dense round size=xs").tooltip("View the expected summary")
                    ui.button(icon="close", on_click=lambda ex=ex: self.remove_example(ex)) \
                        .props("flat dense round size=xs").tooltip("Remove example")
            with ui.row().classes("gap-2"):
                ui.button("Add example…", icon="add", on_click=self.add_example_dialog).props("outline no-caps")
                ui.button("Learn from examples", icon="auto_awesome", on_click=self.learn_flow) \
                    .props("unelevated no-caps").set_enabled(bool(examples))

            ui.separator()
            if prof:
                with ui.row().classes("w-full items-center gap-2 no-wrap"):
                    ui.icon("check_circle", color="positive", size="sm")
                    ui.label(f"Summary profile v{prof['version']} · confirmed "
                             f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(prof['updated']))} · used in every chat "
                             "in this project").classes("text-sm grow")
                    ui.button("View / edit", on_click=lambda: self.profile_editor(prof["learned"], prof["pinned"], None,
                                                                                 "", "edited")).props("outline dense no-caps size=sm")
                    ui.button(icon="delete", on_click=self.remove_profile).props("flat dense round size=sm") \
                        .tooltip("Stop using the profile")
                t = prof.get("targets") or {}
                facts = []
                if t.get("words"):
                    facts.append(f"target {t['words'][0]}–{t['words'][1]} words")
                if t.get("verbatim"):
                    facts.append(f"{t['verbatim'][0]}–{t['verbatim'][1]}% verbatim")
                if prof.get("pinned"):
                    facts.append(f"{sum(1 for ln in prof['pinned'].splitlines() if ln.strip())} pinned rule(s)")
                if prof.get("changes"):
                    facts.append(f"last change: {prof['changes']}")
                if facts:
                    ui.label(" · ".join(facts)).classes("muted text-xs")
                with ui.expansion("Show profile").classes("w-full text-sm").props("dense"):
                    ui.markdown(prof["text"])
            else:
                with ui.row().classes("w-full items-center gap-2"):
                    ui.icon("radio_button_unchecked", size="sm").classes("muted")
                    ui.label("No summary profile yet. Learn one from the examples, or write it yourself.") \
                        .classes("muted text-sm grow")
                    ui.button("Write manually", on_click=lambda: self.profile_editor(PROFILE_TEMPLATE, "", None, "", "manual")) \
                        .props("flat dense no-caps size=sm color=primary")

    async def view_example(self, ex: dict):
        with self.root, ui.dialog() as dialog, ui.card().classes("w-[680px] max-w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(ex["name"]).classes("font-semibold")
                ui.button(icon="close", on_click=dialog.close).props("flat dense round size=sm")
            ui.label("Sources: " + (", ".join(ex["sources"]) or "none")).classes("muted text-xs")
            with ui.scroll_area().classes("w-full h-[60vh]"):
                ui.markdown(ex["summary"])
        dialog.on("hide", dialog.delete)
        dialog.open()

    async def view_analysis(self, ex: dict):
        """What the app measured for one example: each summary sentence with its source, coverage, length."""
        pid = self.project["id"]
        try:
            ev = await asyncio.to_thread(knowledge.evidence, pid, ex)
        except Exception as e:
            self.notify(f"Could not analyse {ex['name']}: {e}", type="negative", multi_line=True)
            return
        with self.root, ui.dialog() as dialog, ui.card().classes("w-[960px] max-w-full gap-2"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(f"Analysis · {ex['name']}").classes("font-semibold text-base")
                ui.button(icon="close", on_click=dialog.close).props("flat dense round size=sm")
            facts = [f"{ev['words']} words", f"{ev['points']} points in {len(ev['sections'])} section(s)",
                     f"{round(ev['compression'] * 100)}% of the source length",
                     f"{round(ev['verbatim'] * 100)}% verbatim",
                     f"figures in source: {ev['numbers'] - ev['numbers_missing']}/{ev['numbers']}",
                     f"{ev['bold']['count']} bold phrases"]
            with ui.row().classes("gap-2"):
                for f in facts:
                    ui.badge(f).props("outline")
            with ui.scroll_area().classes("w-full h-[62vh]"):
                ui.label("Where each summary sentence comes from (click a source to see it highlighted)") \
                    .classes("text-sm font-medium")
                with ui.element("table").classes("w-full text-sm").style("border-collapse:collapse"):
                    with ui.element("tr").classes("muted text-xs"):
                        for h in ("Summary section", "Summary sentence", "Source", "Verbatim", "Figures"):
                            with ui.element("th").style("text-align:left;padding:4px 6px;border-bottom:1px solid var(--wb-border)"):
                                ui.label(h)
                    td = "padding:6px;border-bottom:1px solid var(--wb-border);vertical-align:top"
                    for r in ev["sentences"]:
                        with ui.element("tr"):
                            with ui.element("td").style(td + ";width:15%"):
                                ui.label(r["section"] or "—").classes("muted")
                            with ui.element("td").style(td):
                                ui.label(r["text"].replace("**", ""))
                            with ui.element("td").style(td + ";width:24%"):
                                where = f"{r['source_section']} · p.{r['page']}" if r["kind"] == "pdf" else r["source_section"]
                                ui.button(where, on_click=lambda r=r: (dialog.close(), self.open_block(
                                    r["doc_id"], r["block_id"], r["text"], f"{ex['name']} · {r['block_id']}"))) \
                                    .props("flat dense no-caps size=sm color=primary align=left").classes("text-left")
                                for o in r.get("also", []):
                                    ui.label(f"+ {o['source_section']}").classes("muted text-xs")
                            with ui.element("td").style(td + ";width:8%"):
                                ui.label(f"{round(r['verbatim'] * 100)}%")
                            with ui.element("td").style(td + ";width:13%"):
                                if r["numbers_missing"]:
                                    ui.label("not in source: " + ", ".join(r["numbers_missing"])).classes("err text-xs")
                                elif r["numbers"]:
                                    ui.label(f"✓ {r['numbers']}").classes("text-xs")
                if ev["unmatched"]:
                    ui.label("Sentences with no clear source (the writer's own additions)").classes("text-sm font-medium mt-3")
                    for u in ev["unmatched"]:
                        ui.label(f"• [{u['section'] or '—'}] {u['text'].replace('**', '')}").classes("text-sm")
                ui.label("Source sections").classes("text-sm font-medium mt-3")
                with ui.row().classes("gap-2"):
                    for name, c in ev["coverage"].items():
                        if c["words"] < 15:
                            continue
                        used = c["used"] > 0
                        ui.badge(f"{name}: {c['used']}/{c['total']}").props(f"{'' if used else 'outline'} "
                                                                          f"color={'positive' if used else 'grey'}")
        dialog.on("hide", dialog.delete)
        dialog.open()

    async def remove_example(self, ex: dict):
        if await self.confirm(f"Remove the example \"{ex['name']}\"? Its copied files in .workbench/knowledge are "
                              "deleted. The current profile is not changed until you learn again.", "Remove"):
            knowledge.remove_example(self.project["id"], ex["id"])
            self.main.refresh()

    async def remove_profile(self):
        if await self.confirm("Stop using the summary profile in this project's chats? (It is deleted; examples are kept.)",
                              "Remove"):
            knowledge.clear_profile(self.project["id"])
            self.main.refresh()

    async def add_example_dialog(self):
        state = {"sources": []}
        with self.root, ui.dialog().props("persistent") as dialog, ui.card().classes("w-[680px] max-w-full gap-3"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Add example").classes("font-semibold text-base")
                ui.button(icon="close", on_click=lambda: dialog.submit(None)).props("flat dense round size=sm")
            ui.label("An example is a source document plus the summary you expect for it. The assistant learns the "
                     "structure, length, tone and what information to pick from these pairs.").classes("muted text-xs")
            name = ui.input("Name", placeholder="e.g. Harborline Oct 2026").classes("w-full").props("outlined dense")

            ui.label("1. Source document(s)").classes("text-sm font-medium")

            @ui.refreshable
            def source_list():
                for i, (n, data) in enumerate(state["sources"]):
                    with ui.row().classes("w-full items-center gap-3 px-2 no-wrap"):
                        type_badge(n)
                        ui.label(n).classes("ellipsis1 grow")
                        ui.label(file_size(len(data))).classes("muted text-xs")
                        ui.button(icon="close", on_click=lambda i=i: (state["sources"].pop(i), source_list.refresh())) \
                            .props("flat dense round size=xs")

            def on_sources(e: events.MultiUploadEventArguments):
                e.sender.run_method("reset")
                state["sources"] += [(n, c.read()) for n, c in zip(e.names, e.contents)]
                if not name.value:
                    name.value = Path(e.names[0]).stem
                source_list.refresh()

            up_src = ui.upload(multiple=True, auto_upload=True, on_multi_upload=on_sources, on_rejected=rejected) \
                .props(f'accept="{ACCEPT}"').classes("hidden")
            ui.button("Upload source document(s)…", icon="upload_file", on_click=lambda: up_src.run_method("pickFiles")) \
                .props("outline no-caps")
            source_list()

            ui.label("2. Expected summary").classes("text-sm font-medium")
            summary = ui.textarea(placeholder="Upload the summary file (Word, PDF, Text, Markdown) or paste it here. "
                                  "Bullets, headings and **bold** are kept.") \
                .classes("w-full").props("outlined autogrow input-style='min-height:180px'")
            summary_note = ui.label().classes("muted text-xs")

            def on_summary(e: events.UploadEventArguments):
                e.sender.run_method("reset")
                try:
                    summary.value = knowledge.summary_markdown(e.name, e.content.read())
                    summary_note.set_text(f"✓ Read {e.name} ({file_type(e.name)}). Check the text above; you can edit it.")
                except Exception as ex:
                    summary_note.set_text(f"✗ {ex}")

            up_sum = ui.upload(auto_upload=True, on_upload=on_summary, on_rejected=rejected) \
                .props('accept=".docx,.md,.txt,.pdf"').classes("hidden")
            ui.button("Upload summary file…", icon="description", on_click=lambda: up_sum.run_method("pickFiles")) \
                .props("outline no-caps")
            error = ui.label().classes("err text-xs")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat no-caps")
                add_btn = ui.button("Add example", on_click=lambda: dialog.submit("add")).props("unelevated no-caps")
            add_btn.bind_enabled_from(summary, "value", backward=lambda v: bool((v or "").strip()))

        while True:
            if await dialog != "add":
                dialog.delete()
                return
            try:
                knowledge.add_example(self.project["id"], name.value or "", state["sources"], summary.value)
                break
            except Exception as e:
                error.set_text(str(e))
        dialog.delete()
        self.notify("Example added", type="positive")
        self.main.refresh()

    async def save_as_example(self, m: dict):
        text = answer_summary_text(m["content"])
        if not text:
            self.notify("This answer has no text to save.", type="warning")
            return
        with self.root:
            name = await ask_text("Save this answer as an example summary. The documents attached to this chat are "
                                  "saved with it as its sources.\nName:", self.chat["title"][:60], "Save example")
        if not name:
            return
        knowledge.add_example_from_chat(self.project["id"], self.chat, text, name)
        n = len(knowledge.list_examples(self.project["id"]))
        if await self.confirm(f"Saved as example ({n} in this project). Update the summary profile from all "
                              "examples now?", "Learn now"):
            await self.learn_flow()

    async def use_as_profile(self, m: dict):
        prof = knowledge.get_profile(self.project) or {}
        await self.profile_editor(answer_summary_text(m["content"]), prof.get("pinned", ""), None, "", "chat")

    async def learn_flow(self):
        pid = self.project["id"]
        with self.root, ui.dialog().props("persistent") as dlg, ui.card().classes("w-[460px] max-w-full"):
            ui.label("Learning from examples").classes("font-semibold")
            with ui.row().classes("items-center gap-3 no-wrap"):
                ui.spinner(size="md")
                msg = ui.label("Starting…").classes("text-sm")
            ui.label("New examples are measured and analysed (one LLM call each; earlier ones are reused), then "
                     "combined with one more call.").classes("muted text-xs")
        dlg.open()
        try:
            draft = await knowledge.learn(pid, settings.provider(), progress=msg.set_text)
        except Exception as e:
            dlg.close()
            dlg.delete()
            self.notify(f"Learning failed: {e}", type="negative", multi_line=True, timeout=0, close_button=True)
            return
        dlg.close()
        dlg.delete()
        prof = knowledge.get_profile(self.project) or {}
        await self.profile_editor(draft["learned"], prof.get("pinned", ""), draft, draft["suggestions"], "learned")

    async def profile_editor(self, learned: str, pinned: str, draft: dict | None, suggestions: str, source: str):
        """Review a profile: measured part (read-only, from code), learned rules (editable) and pinned rules
        (the user's own; kept when re-learning)."""
        pid = self.project["id"]
        current = knowledge.get_profile(self.project) or {}
        measured = (draft or current).get("measured_md", "")
        titles = {"learned": "Review the learned summary profile", "edited": "Edit the summary profile",
                  "chat": "Use this answer as the summary profile", "manual": "Write the summary profile"}
        with self.root, ui.dialog().props("persistent") as dialog, ui.card().classes("w-[820px] max-w-full gap-2"):
            ui.label(titles.get(source, "Summary profile")).classes("font-semibold text-base")
            note = ("The confirmed profile goes into every chat in this project; drafts are also checked against its "
                    "measured targets.")
            if draft:
                note += (f" {draft['examples']} example(s); {draft['newly_analyzed']} newly analysed, the rest reused "
                         "from earlier.")
            ui.label(note).classes("muted text-xs")
            if measured:
                with ui.expansion("Measured by the app (from the examples; read-only)", value=True) \
                        .classes("w-full text-sm").props("dense"):
                    ui.markdown(measured)
            ui.label("Learned rules — edit anything that is wrong; (k/N) shows how many examples support a rule") \
                .classes("text-sm font-medium")
            editor = ui.textarea(value=learned).classes("w-full").props(
                "outlined autogrow input-style='min-height:240px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px'")
            ui.label("Pinned rules — your own rules; always applied, override the rest, and kept when re-learning") \
                .classes("text-sm font-medium")
            pin = ui.textarea(value=pinned, placeholder="- e.g. Always state the provision as from/to and % of exposure") \
                .classes("w-full").props("outlined autogrow input-style='min-height:70px'")
            append = sugg = None
            if suggestions.strip():
                ui.label("Suggested additions to the project instructions").classes("text-sm font-medium")
                sugg = ui.textarea(value=suggestions).classes("w-full").props("outlined autogrow")
                append = ui.checkbox("Append these to the project instructions", value=True).props("dense")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat no-caps")
                ui.button("Confirm & save", on_click=lambda: dialog.submit(True)).props("unelevated no-caps")
        ok = await dialog
        dialog.delete()
        if not ok or not ((editor.value or "").strip() or (pin.value or "").strip()):
            return
        prof = knowledge.save_profile(pid, editor.value or "", pin.value or "", draft, source)
        if append is not None and append.value and (sugg.value or "").strip():
            instr = (self.project["instructions"].rstrip() + "\n\n" + sugg.value.strip()).strip()
            projects.update(pid, instructions=instr)
        self.reload_project()
        self.main.refresh()
        self.notify(f"Summary profile v{prof['version']} saved ({prof['changes']}); new messages in this project use it.",
                    type="positive", multi_line=True)

    # ---------- new project dialog

    async def new_project_dialog(self):
        state = {"picking": False, "listing": None, "files": [], "error": ""}

        with self.root, ui.dialog().props("persistent") as dialog, ui.card().classes("w-[700px] max-w-full gap-3"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("New project").classes("font-semibold text-base")
                ui.button(icon="close", on_click=lambda: dialog.submit(None)).props("flat dense round size=sm")
            name = ui.input("Name", placeholder="e.g. CIP monthly summaries").classes("w-full").props("outlined dense")
            ui.label("Folder — the assistant can only read files in this folder and save outputs here") \
                .classes("muted text-xs")
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                folder = ui.input(placeholder="/Users/you/Documents/cip  or  C:\\Work\\cip").classes("grow") \
                    .props("outlined dense")
                ui.button("Browse…", on_click=lambda: toggle_picker()).props("outline no-caps")

            @ui.refreshable
            def picker():
                if not state["picking"]:
                    return
                lst = state["listing"]
                with ui.column().classes("w-full gap-0").style(
                        "border:1px solid var(--wb-border);border-radius:9px;background:var(--wb-bg)"):
                    if state["error"]:
                        ui.label(state["error"]).classes("err text-xs p-2")
                    if not lst:
                        return
                    at_locations = lst["path"] == lst["locations"]
                    with ui.row().classes("w-full items-center gap-1 p-2 no-wrap").style("border-bottom:1px solid var(--wb-border)"):
                        ui.button(icon="arrow_upward", on_click=lambda: browse(lst["parent"])) \
                            .props("outline dense size=sm").tooltip("Up one level").set_enabled(bool(lst["parent"]))
                        ui.button("Locations", icon="storage", on_click=lambda: browse(lst["locations"])) \
                            .props("outline dense no-caps size=sm").tooltip("Drives, network drives and common folders")
                        ui.label("Drives, network drives and common folders" if at_locations else lst["path"]) \
                            .classes("text-xs muted ellipsis1").style("direction:rtl;text-align:left")
                    with ui.scroll_area().classes("w-full h-56"):
                        if not lst["dirs"] and not lst["files"]:
                            ui.label("This folder is empty.").classes("muted text-xs p-2")
                        icons = {"home": "home", "drive": "storage", "network": "lan", "cloud": "cloud", "folder": "folder"}
                        for d in lst["dirs"]:
                            with ui.element("div").classes("fs-row click").on("click", lambda p=d["path"]: browse(p)) \
                                    .on("dblclick", lambda p=d["path"]: pick(p)):
                                ui.icon(icons.get(d.get("kind"), "folder"), size="xs").classes("muted")
                                ui.label(d["name"]).classes("ellipsis1 grow")
                                if d["is_project"]:
                                    ui.badge("project").props("outline")
                        for f in lst["files"]:
                            with ui.element("div").classes(f"fs-row {'' if f['supported'] else 'fs-off'}"):
                                type_badge(f["name"])
                                ui.label(f["name"]).classes("ellipsis1 grow")
                                ui.label(file_size(f["size"])).classes("muted text-xs")
                    with ui.row().classes("w-full items-center gap-2 p-2").style("border-top:1px solid var(--wb-border)"):
                        nd, nf = len(lst["dirs"]), len(lst["files"])
                        readable = sum(f["supported"] for f in lst["files"])
                        if at_locations:
                            ui.label("Shared folder not listed? Type its path in the Folder box, e.g. "
                                     "\\\\server\\share\\team or S:\\Team, then click Browse….").classes("muted text-xs")
                        else:
                            ui.button("Use this folder", on_click=lambda: pick(lst["path"])).props("unelevated no-caps dense")
                            ui.label(f"{nd} folder{'s' if nd != 1 else ''} · {nf} file{'s' if nf != 1 else ''}"
                                     + (f" ({readable} readable)" if nf else "") + " · double-click a folder to pick it") \
                                .classes("muted text-xs")

            async def browse(path):
                # Network shares can be slow: list them off the UI thread.
                try:
                    state["listing"], state["error"] = await asyncio.to_thread(fs.list_dirs, path), ""
                except Exception as e:
                    state["error"] = str(e)
                    if not state["listing"]:
                        state["listing"] = await asyncio.to_thread(fs.list_dirs, None)
                picker.refresh()

            async def toggle_picker():
                state["picking"] = not state["picking"]
                picker.refresh()
                if state["picking"]:
                    await browse(folder.value.strip() or None)

            def pick(path):
                folder.value = path
                state["picking"] = False
                picker.refresh()

            picker()
            create_folder = ui.checkbox("Create the folder if it doesn't exist", value=True).props("dense")
            instructions = ui.textarea("Instructions — what should the assistant do in this project?",
                                       placeholder=INSTRUCTIONS_HINT).classes("w-full") \
                .props("outlined autogrow input-style='min-height:130px'")

            ui.label("Context — optional background the assistant always sees: sample summaries, glossaries, templates…") \
                .classes("muted text-xs")

            @ui.refreshable
            def upload_list():
                files = state["files"]
                if files:
                    ok = sum(supported(n) for n, _ in files)
                    ui.label(f"{ok} of {len(files)} file(s) will be added when you create the project").classes("muted text-xs")
                    with ui.column().classes("w-full gap-0").style("border:1px solid var(--wb-border);border-radius:8px"):
                        for i, (n, data) in enumerate(files):
                            good = supported(n)
                            with ui.row().classes("w-full items-center gap-3 px-3 py-1 no-wrap").style(
                                    "border-bottom:1px solid var(--wb-border)" + ("" if good else
                                    ";background:color-mix(in srgb, var(--wb-error) 8%, transparent)")):
                                type_badge(n)
                                ui.label(n).classes("ellipsis1 grow")
                                ui.label(file_size(len(data))).classes("muted text-xs")
                                ui.label("✓ ready" if good else "unsupported type").classes(
                                    "text-xs " + ("text-green-700" if good else "err"))
                                ui.button(icon="close", on_click=lambda i=i: (state["files"].pop(i), upload_list.refresh())) \
                                    .props("flat dense round size=xs")

            def on_pick(e: events.MultiUploadEventArguments):
                e.sender.run_method("reset")
                have = {(n, len(d)) for n, d in state["files"]}
                for n, c in zip(e.names, e.contents):
                    data = c.read()
                    if (n, len(data)) not in have:
                        state["files"].append((n, data))
                upload_list.refresh()

            up = ui.upload(multiple=True, auto_upload=True, on_multi_upload=on_pick, on_rejected=rejected).props(f'accept="{ACCEPT}"') \
                .classes("hidden")
            ui.button("Upload files…", on_click=lambda: up.run_method("pickFiles")).props("outline no-caps")
            upload_list()
            paste_title = ui.input("Title for pasted text (optional)").classes("w-full").props("outlined dense")
            paste_text = ui.textarea("…or paste text here").classes("w-full").props("outlined autogrow")
            ui.label("You can add more context and files from the project folder later.").classes("muted text-xs")
            error = ui.label().classes("err text-xs")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat no-caps")
                create_btn = ui.button("Create project", on_click=lambda: dialog.submit("create")).props("unelevated no-caps")
            create_btn.bind_enabled_from(folder, "value", backward=lambda v: bool((v or "").strip()))

        while True:
            if await dialog != "create":
                dialog.delete()
                return
            try:
                p = projects.create(name.value or Path(folder.value.strip()).name, folder.value.strip(),
                                    instructions.value or "", create_folder.value)
                break
            except Exception as e:
                error.set_text(str(e))

        dialog.delete()
        lines = []
        if p.get("reopened"):
            lines.append(f'This folder already had a project, so "{p["name"]}" was reopened with its saved '
                         "instructions and context.")
        added = [projects.add_upload(p["id"], n, d) for n, d in state["files"] if supported(n)]
        if (paste_text.value or "").strip():
            added.append(projects.add_text(p["id"], paste_title.value or "Pasted text", paste_text.value))
        if added:
            lines.append(report(added, "Added to context"))
        self.open_project(p["id"])
        self.set_project_notice("\n".join(lines))

    # ---------- settings dialog

    async def settings_dialog(self):
        s = settings.load()
        draft = {name: {k: v for k, v in p.items() if k != "api_key"} for name, p in s["providers"].items()}
        keys = {name: "" for name in draft}
        folders = list(s["allowed_folders"])
        active = {"name": s["active_provider"]}

        with self.root, ui.dialog() as dialog, ui.card().classes("w-[600px] max-w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Settings").classes("font-semibold text-base")
                ui.button(icon="close", on_click=dialog.close).props("flat dense round size=sm")
            with ui.tabs().classes("w-full").props("dense align=left no-caps") as tabs:
                tab_objs = {name: ui.tab(name, label=p["label"]) for name, p in draft.items()}
                ui.tab("_folders", label="Folders")
            with ui.tab_panels(tabs, value=tab_objs[active["name"]]).classes("w-full"):
                for name, p in draft.items():
                    with ui.tab_panel(name).classes("gap-2 px-0"):
                        self.provider_form(name, p, keys, active)
                with ui.tab_panel("_folders").classes("gap-2 px-0"):
                    ui.label("The file browser can only read inside these folders (subfolders included).") \
                        .classes("muted text-xs")

                    @ui.refreshable
                    def folder_list():
                        for f in folders:
                            with ui.row().classes("w-full items-center no-wrap gap-2"):
                                ui.html(f"<code class='wrap-anywhere'>{html.escape(f)}</code>").classes("grow")
                                ui.button("Remove", on_click=lambda f=f: (folders.remove(f), folder_list.refresh())) \
                                    .props("outline dense no-caps size=sm")
                    folder_list()
                    with ui.row().classes("w-full no-wrap gap-2"):
                        new = ui.input(placeholder="/Users/you/Documents/memos  or  C:\\Work\\memos").classes("grow") \
                            .props("outlined dense")

                        def add_folder():
                            if new.value.strip():
                                folders.append(new.value.strip())
                                new.value = ""
                                folder_list.refresh()
                        ui.button("Add", on_click=add_folder).props("outline no-caps")

            def save():
                body = {"active_provider": active["name"], "allowed_folders": folders,
                        "providers": {n: {**p, "api_key": keys[n]} for n, p in draft.items()}}
                settings.update(body)
                self.sidebar.refresh()
                self.topbar.refresh()

            self._settings_save = save
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                ui.button("Save", on_click=lambda: (save(), dialog.close())).props("unelevated no-caps")
        dialog.on("hide", dialog.delete)
        dialog.open()

    def provider_form(self, name: str, p: dict, keys: dict, active: dict):
        ui.select({"ollama": "Ollama (native API)", "openai": "OpenAI-compatible"}, label="Type", value=p["type"]) \
            .bind_value(p, "type").classes("w-full").props("outlined dense")
        ui.input("Base URL", placeholder="http://localhost:11434" if p["type"] == "ollama" else "https://gateway/v1") \
            .bind_value(p, "base_url").classes("w-full").props("outlined dense")
        with ui.row().classes("w-full no-wrap gap-2 items-center"):
            model = ui.input("Model").bind_value(p, "model").classes("grow").props("outlined dense")

            async def list_models():
                try:
                    names = await llm.list_models({**settings.provider(name), **p, "api_key": keys[name] or settings.provider(name).get("api_key", "")})
                    model.set_autocomplete(names)
                    self.notify(f"{len(names)} models: " + ", ".join(names[:8]) + ("…" if len(names) > 8 else ""))
                except llm.LLMError as e:
                    self.notify(str(e), type="negative", multi_line=True)
            ui.button("List", on_click=list_models).props("outline no-caps")
        ui.input("API key" + (" (stored — leave blank to keep)" if p.get("has_api_key") or settings.provider(name).get("api_key") else ""),
                 password=True, password_toggle_button=True,
                 on_change=lambda e: keys.__setitem__(name, e.value or "")).classes("w-full").props("outlined dense autocomplete=off")
        headers = ui.input("Extra headers (JSON; {api_key} is replaced by the key)",
                           value=json.dumps(p.get("extra_headers") or {})).classes("w-full").props("outlined dense")

        def set_headers(e):
            try:
                p["extra_headers"] = json.loads(e.value or "{}")
                headers.props(remove="error")
            except ValueError:
                headers.props("error error-message='Invalid JSON'")
        headers.on_value_change(set_headers)
        with ui.row().classes("gap-4"):
            ui.checkbox("Verify SSL").bind_value(p, "verify_ssl").props("dense")
            ui.checkbox("Bypass proxy").bind_value(p, "bypass_proxy").props("dense")
        with ui.row().classes("w-full no-wrap gap-2"):
            ui.number("Context window (tokens)", min=1024, step=1024, format="%d") \
                .bind_value(p, "context_tokens", forward=lambda v: int(v or 8192)).classes("grow").props("outlined dense")
            ui.number("Temperature", min=0, max=2, step=0.1).bind_value(p, "temperature") \
                .classes("grow").props("outlined dense")
        result = ui.label().classes("text-xs whitespace-pre-wrap")
        with ui.row().classes("gap-2"):
            use = ui.button("Use this provider", on_click=lambda: (active.__setitem__("name", name), use.set_visibility(False))) \
                .props("outline no-caps")
            use.set_visibility(active["name"] != name)

            async def test():
                self._settings_save()
                result.set_text("Testing…")
                result.classes(replace="text-xs whitespace-pre-wrap muted")
                t0 = time.time()
                try:
                    reply = await llm.complete([{"role": "user", "content": "Reply with exactly: OK"}],
                                               {**settings.provider(name), "context_tokens": 512})
                    result.set_text(f'✓ Replied "{reply.strip()[:80]}" in {time.time() - t0:.1f}s')
                except llm.LLMError as e:
                    result.set_text(f"✗ {e}")
                    result.classes(replace="text-xs whitespace-pre-wrap err")
            ui.button("Save & test connection", on_click=test).props("outline no-caps")


def attach(app):
    @ui.page("/")
    def index():
        Workbench().build()

    ui.run_with(app, title="LLM Workbench", favicon="🗂️", show_welcome_message=False, reconnect_timeout=30)
