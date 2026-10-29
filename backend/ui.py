"""
User interface written in Python with NiceGUI: no JavaScript build step and no .js/.css/.html files to ship.
NiceGUI's own browser assets come from the `nicegui` pip package.

One `Workbench` object per browser tab holds the UI state and calls the backend modules directly.
"""
import asyncio
import base64
import html
import json
import re
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import httpx
from nicegui import background_tasks, events, ui

from . import browserfetch, chats, citations, documents, knowledge, llm, outputs, preview, projects, settings, webfetch
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
.pv-table { border-collapse: collapse; font-size: 12px; }
.pv-table td { border: 1px solid var(--wb-border); padding: 2px 6px; white-space: nowrap; }
.web-card { border: 1px solid var(--wb-accent); box-shadow: none; margin-bottom: 16px; }
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


_CODE = re.compile(r"(```.*?(?:```|$)|`[^`\n]*`)", re.S)


def safe_markdown(text: str) -> str:
    """Model output with raw HTML and images shown as text, so an answer can't make the browser load anything.
    (A web page or document could tell the model to put chat data into an image or style URL.) Code is unchanged."""
    parts = _CODE.split(text)
    for i in range(0, len(parts), 2):
        p = re.sub(r"!\[([^\]]*)\]\s*[(\[][^)\]]*[)\]]", lambda m: f"[image: {m.group(1) or 'no description'}]", parts[i])
        parts[i] = re.sub(r"<(?=[A-Za-z/!?])", "&lt;", p)
    return "".join(parts)


def render_answer(text: str, resolve) -> str:
    """Markdown with citations ([C1-p2-13] and common variants) replaced by clickable chips (HTML spans)."""
    text = safe_markdown(text)
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


URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'`，。；、！？）】」》]+", re.I)


def find_url(text: str) -> tuple[str, str] | None:
    """The first web address typed in a chat message, and the message without it."""
    m = URL_RE.search(text)
    if not m:
        return None
    url = m.group(0)
    while url and (url[-1] in ".,;:!?'\"]}>" or (url[-1] == ")" and url.count("(") < url.count(")"))):
        url = url[:-1]
    rest = re.sub(r"\s+", " ", text[:m.start()] + text[m.start() + len(url):]).strip()
    rest = rest if re.search(r"\w", rest) else ""
    return (url, rest) if len(url) > 7 else None


def release_browser(st: dict):
    """Close the From web steps' signed-in browser, if they opened one (nothing of the sign-in is kept)."""
    if st and st.get("browser"):
        background_tasks.create(st["browser"].close(), name="close browser")
        st["browser"] = None


_DOWNLOAD_STRONG = re.compile(r"\b(download|grab|scrape)\w*|\bget (?:all |the |these |those |every )*(?:files|pdfs?|"
                              r"documents|docs|attachments)\b|下载|下下来|拿下来|抓下来|批量", re.I)
_DOWNLOAD_WEAK = re.compile(r"\b(save|store|keep)\b|保存|存到|存下|存进|存入|另存", re.I)
_READ = re.compile(r"summar|extract|analy[sz]|compare|translat|explain|list|find|what|which|how|why|tell me|read|"
                   r"table|number|figure|value|总结|摘要|概括|提取|分析|对比|比较|翻译|解释|找|哪些|多少|什么|读|数值|数据|表格", re.I)


def web_intent(url: str, rest: str) -> str:
    """What a chat message with a link asks for: "download" (the download steps), "read" (the page goes to the
    model with the message), "attach" (a bare link to a document: attach it), or "choose" (a bare link to a page)."""
    if _DOWNLOAD_STRONG.search(rest) or (_DOWNLOAD_WEAK.search(rest) and not _READ.search(rest)):
        return "download"
    if not rest:
        return "attach" if webfetch._suffix_of(url) in webfetch.READABLE else "choose"
    return "read"


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

class FolderPicker:
    """Inline folder browser (drives, network drives, common folders, any folder) that fills a text input.
    Create it, call .view() where it should appear, and .toggle() from a Browse… button."""

    def __init__(self, target, on_pick=None):
        self.target, self.on_pick = target, on_pick
        self.open, self.listing, self.error = False, None, ""

    async def toggle(self):
        self.open = not self.open
        self.view.refresh()
        if self.open:
            await self.browse((self.target.value or "").strip() or None)

    async def browse(self, path):
        # Network shares can be slow: list them off the UI thread.
        try:
            self.listing, self.error = await asyncio.to_thread(fs.list_dirs, path), ""
        except Exception as e:
            self.error = str(e)
            if not self.listing:
                self.listing = await asyncio.to_thread(fs.list_dirs, None)
        self.view.refresh()

    def pick(self, path):
        self.target.value = path
        self.open = False
        self.view.refresh()
        if self.on_pick:
            self.on_pick(path)

    @ui.refreshable
    def view(self):
        if not self.open:
            return
        lst = self.listing
        with ui.column().classes("w-full gap-0").style(
                "border:1px solid var(--wb-border);border-radius:9px;background:var(--wb-bg)"):
            if self.error:
                ui.label(self.error).classes("err text-xs p-2")
            if not lst:
                return
            at_locations = lst["path"] == lst["locations"]
            with ui.row().classes("w-full items-center gap-1 p-2 no-wrap").style("border-bottom:1px solid var(--wb-border)"):
                ui.button(icon="arrow_upward", on_click=lambda: self.browse(lst["parent"])) \
                    .props("outline dense size=sm").tooltip("Up one level").set_enabled(bool(lst["parent"]))
                ui.button("Locations", icon="storage", on_click=lambda: self.browse(lst["locations"])) \
                    .props("outline dense no-caps size=sm").tooltip("Drives, network drives and common folders")
                ui.label("Drives, network drives and common folders" if at_locations else lst["path"]) \
                    .classes("text-xs muted ellipsis1").style("direction:rtl;text-align:left")
            with ui.scroll_area().classes("w-full h-56"):
                if not lst["dirs"] and not lst["files"]:
                    ui.label("This folder is empty.").classes("muted text-xs p-2")
                icons = {"home": "home", "drive": "storage", "network": "lan", "cloud": "cloud", "folder": "folder"}
                for d in lst["dirs"]:
                    with ui.element("div").classes("fs-row click").on("click", lambda p=d["path"]: self.browse(p)) \
                            .on("dblclick", lambda p=d["path"]: self.pick(p)):
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
                    ui.button("Use this folder", on_click=lambda: self.pick(lst["path"])).props("unelevated no-caps dense")
                    ui.label(f"{nd} folder{'s' if nd != 1 else ''} · {nf} file{'s' if nf != 1 else ''}"
                             + (f" ({readable} readable)" if nf else "") + " · double-click a folder to pick it") \
                        .classes("muted text-xs")


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
        self.web_state: dict | None = None      # the "From web" card in the chat, while it is open

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
        # The "From web" card for a message with a link: outside main() so refreshes leave it in place.
        self.web_slot = ui.column().classes("w-full max-w-[1100px] mx-auto gap-0")

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
        ui.button("From web", icon="travel_explore", on_click=self.web_download_dialog) \
            .props("outline no-caps").tooltip("Download documents from a web page")
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
                    ui.markdown(safe_markdown(body + sep + sources.replace("_", "\\_")))
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
        self.drop_idle_web_card()
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
        self.drop_idle_web_card()
        if self.right in ("context", "source"):
            self.toggle_right(None)
        self.refresh_all()

    def new_chat(self):
        if self.pending:
            return
        self.notice, self.editing = "", None
        self.drop_idle_web_card()
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
        if from_input and (found := find_url(text)):      # a link: download steps, or the page for the model
            url, rest = found
            intent = web_intent(url, rest)
            if intent == "download":
                if self.open_web_card(url, rest, original=text):
                    self.input.value = ""
                return
            self.input.value = ""
            if intent == "choose":
                self.web_choice(url)
                return
            if not await self.read_web(url):
                self.input.value = text
                return
            if intent == "attach":
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
                    ui.markdown(safe_markdown(prof["text"]))
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
                ui.markdown(safe_markdown(ex["summary"]))
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
        state = {"files": []}

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
                picker = FolderPicker(folder)
                ui.button("Browse…", on_click=lambda: picker.toggle()).props("outline no-caps")

            picker.view()
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
                p = projects.create(name.value or "", folder.value.strip(),
                                    instructions.value or "", create_folder.value)
                break
            except Exception as e:
                error.set_text(str(e))

        dialog.delete()
        lines = []
        if p.get("reopened"):
            lines.append(f'This folder already had a project called "{p["name"]}", so it was reopened with its saved '
                         "instructions and context.")
        elif p.get("shares_folder_with"):
            lines.append("This folder is also used by " + ", ".join(f'"{n}"' for n in p["shares_folder_with"]) +
                         ". The projects share its files; each keeps its own instructions, context and knowledge base.")
        added = [projects.add_upload(p["id"], n, d) for n, d in state["files"] if supported(n)]
        if (paste_text.value or "").strip():
            added.append(projects.add_text(p["id"], paste_title.value or "Pasted text", paste_text.value))
        if added:
            lines.append(report(added, "Added to context"))
        self.open_project(p["id"])
        self.set_project_notice("\n".join(lines))

    # ---------- settings dialog

    # ---------- download documents from a web page (no LLM involved)

    async def web_download_dialog(self):
        with self.root, ui.dialog().props("persistent") as dialog, ui.card().classes("w-[780px] max-w-full gap-1"):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                ui.label("Download documents from a web page").classes("font-semibold text-base")
                close_btn = ui.button(icon="close", on_click=lambda: dialog.close()).props("flat dense round size=sm")
            ui.label("Nothing is sent to the AI model: you choose the page and the files, and they are downloaded "
                     "straight into your folder.").classes("muted text-xs")
            st = self.web_steps(dialog.close, close_btn.set_enabled)
        dialog.on("hide", lambda: (release_browser(st), dialog.delete()))
        dialog.open()

    def open_web_card(self, url: str, rest: str, original: str) -> bool:
        """The same steps as a card at the end of the chat, for a message that contains a web address.
        The message is not sent to the model; the rest of it goes back into the box once the files are attached."""
        if self.web_state and self.web_state["running"]:
            self.notify("A download is still running in the chat. Wait for it or stop it first.", type="warning")
            return False
        self.web_slot.clear()
        with self.web_slot, ui.card().classes("w-full gap-1 web-card"):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.icon("travel_explore", color="primary")
                ui.label("Download documents from this link").classes("font-semibold grow")
                as_msg = ui.button("Read the page instead", on_click=lambda: self.web_card_as_message(original, url, rest)) \
                    .props("flat dense no-caps size=sm color=primary") \
                    .tooltip("Attach the page's text to the chat and send your message to the model")
                close_btn = ui.button(icon="close", on_click=self.close_web_card).props("flat dense round size=sm")
            ui.label("Your message asks to download from a web address, so it was not sent to the AI model. Pick "
                     "the files and a folder below; they are downloaded straight into it and can then be attached "
                     "to this chat.").classes("muted text-xs")

            def closable(on: bool):
                close_btn.set_enabled(on)
                as_msg.set_enabled(on)
            self.web_state = self.web_steps(self.close_web_card, closable, url=url, followup=rest)
        self.client.run_javascript("setTimeout(() => window.scrollTo(0, document.body.scrollHeight), 100)")
        return True

    def close_web_card(self):
        release_browser(self.web_state)
        self.web_slot.clear()
        self.web_state = None

    async def web_card_as_message(self, text: str, url: str, rest: str):
        self.close_web_card()
        if await self.read_web(url) and rest:
            await self.send(text)

    def web_choice(self, url: str):
        """A bare link to a web page: ask whether to read it or download documents from it."""
        if self.web_state and self.web_state["running"]:
            self.notify("A download is still running in the chat. Wait for it or stop it first.", type="warning")
            return
        self.close_web_card()
        self.web_state = {"running": False}
        with self.web_slot, ui.card().classes("w-full gap-2 web-card"):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.icon("link", color="primary")
                ui.label(url).classes("font-medium ellipsis1 grow")
                ui.button(icon="close", on_click=self.close_web_card).props("flat dense round size=sm")
            ui.label("What should happen with this link?").classes("text-sm")
            with ui.row().classes("gap-2"):
                ui.button("Read the page", icon="article", on_click=lambda: self.read_web(url)) \
                    .props("unelevated no-caps").tooltip("Attach the page's text so you can ask about it "
                                                         "(summaries, numbers, tables)")
                ui.button("Download documents from it", icon="download",
                          on_click=lambda: self.open_web_card(url, "", url)).props("outline no-caps")
        self.client.run_javascript("setTimeout(() => window.scrollTo(0, document.body.scrollHeight), 100)")

    async def read_web(self, url: str) -> bool:
        """Attach the web page at url (its text as Markdown, or the document the link points to) to the chat,
        so the model can answer from it with citations. Pages that need a sign-in go through the browser."""
        if self.web_state and self.web_state["running"]:
            self.notify("A download is still running in the chat. Wait for it or stop it first.", type="warning")
            return False
        self.close_web_card()
        st = self.web_state = {"running": True, "browser": None}
        with self.web_slot, ui.card().classes("w-full gap-1 web-card") as card:
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                spinner = ui.spinner(size="sm")
                status = ui.label(f"Reading {url} …").classes("text-sm ellipsis1 grow")
            ui.label("Only this page is read. Its text is attached to the chat, so the answer can cite it.") \
                .classes("muted text-xs")
        self.busy = True
        self.composer.refresh()
        self.client.run_javascript("setTimeout(() => window.scrollTo(0, document.body.scrollHeight), 100)")
        folder = settings.UPLOADS_DIR / "web" / str(time.time_ns())
        error = None
        try:
            try:
                got = await webfetch.read(url, folder)
            except webfetch.SignInNeeded:
                st["browser"] = browserfetch.BrowserSession()
                got = await st["browser"].read(url, folder, status.set_text)
            doc = await asyncio.to_thread(documents.ingest, Path(got["path"]), got["name"])
        except webfetch.FetchError as e:
            error = str(e)
        except httpx.HTTPError as e:
            error = webfetch.network_error(e, "Could not open the page")
        except Exception as e:
            error = f"Could not read the page: {e}"
        finally:
            release_browser(st)
            st["running"] = False
            self.busy = False
        if error:
            spinner.delete()
            status.set_text(f"⚠ {error}")
            status.classes(replace="text-sm err grow")
            with card, ui.row().classes("gap-2"):
                ui.button("Download documents from it instead", on_click=lambda: self.open_web_card(url, "", url)) \
                    .props("flat dense no-caps size=sm color=primary")
                ui.button("Close", on_click=self.close_web_card).props("flat dense no-caps size=sm")
            self.composer.refresh()
            return False
        self.close_web_card()
        self.attach_metas([{**documents.meta(doc), "ok": True, "name": got["name"]}])
        self.set_notice(f"Read {got['url']} and attached it as {got['name']}.")
        return True

    def drop_idle_web_card(self):
        """Switching chat or project: an unfinished card goes away, a running download stays visible."""
        if self.web_state and not self.web_state["running"]:
            self.close_web_card()

    def web_steps(self, close, closable, url: str = "", followup: str = "") -> dict:
        """The "From web" workflow as a vertical stepper in the current container (the dialog or the chat card).
        close() ends the workflow; closable(bool) enables its close controls (off while downloading)."""
        opts = webfetch.options()
        st = {"scan": None, "selected": set(), "filter": "All", "results": [], "running": False, "cancel": False,
              "dest": "project" if self.project else "other", "last_refresh": 0.0, "browser": None}

        with ui.stepper().props("vertical flat animated").classes("w-full") as stepper:
            # 1 ---------------------------------------------------------------- web address
            with ui.step("Web address", icon="link"):
                url_in = ui.input("Page or document address", value=url, placeholder="https://www.example.com/reports") \
                    .props(f"outlined dense clearable {'' if url else 'autofocus'}").classes("w-full")
                allowed = opts["allowed_domains"]
                ui.label(("Allowed websites: " + ", ".join(allowed)) if allowed else
                         "Any website you type can be opened (limit this in Settings → Web). Only that one page "
                         "is read; no links are followed.").classes("muted text-xs")
                ui.label("Pages that need a sign-in (SharePoint, Confluence, intranet) open in Microsoft Edge or "
                         "Chrome: you sign in there yourself, the app never sees your password and keeps nothing "
                         "after these steps.").classes("muted text-xs")
                scan_status = ui.label("").classes("text-xs text-primary")
                scan_msg = ui.label("").classes("err text-xs")
                with ui.stepper_navigation():
                    scan_btn = ui.button("Scan page", icon="search", on_click=lambda: do_scan()) \
                        .props("unelevated no-caps")
                    sign_btn = ui.button("Sign in first", icon="login", on_click=lambda: do_scan(browser=True)) \
                        .props("flat no-caps").tooltip("Open the page in a browser window to sign in, then scan it")
                url_in.on("keydown.enter", lambda: do_scan())

            # 2 ---------------------------------------------------------------- checklist
            with ui.step("Choose documents", icon="checklist"):
                @ui.refreshable
                def checklist():
                    sc = st["scan"]
                    if not sc:
                        return
                    items = sc["items"]
                    via = sc.get("via") == "browser"
                    with ui.column().classes("w-full gap-0"):
                        with ui.row().classes("w-full items-center gap-2 no-wrap"):
                            ui.label(sc["title"]).classes("font-medium ellipsis1")
                            if via:
                                kinds = {"sharepoint": "SharePoint library", "confluence": "Confluence attachments"}
                                ui.badge(f"signed-in browser{' · ' + kinds[sc['kind']] if sc['kind'] in kinds else ''}") \
                                    .props("outline").tooltip("Read through your own sign-in in the browser")
                        ui.label(sc["url"]).classes("muted text-xs ellipsis1 w-full")
                        if sc.get("kind") == "sharepoint":
                            ui.label("Files in this folder only; open a subfolder and scan it for its files.") \
                                .classes("muted text-xs")
                    if not items:
                        ui.label("No documents (PDF, Word, Excel, PowerPoint, CSV, text) were found on this page." +
                                 ("" if via else " If the page builds its links with JavaScript, or shows more "
                                  "after a sign-in, open it in the browser.")).classes("text-sm")
                        with ui.stepper_navigation():
                            if not via:
                                ui.button("Open in the browser", icon="open_in_browser",
                                          on_click=lambda: do_scan(browser=True)).props("unelevated no-caps")
                            ui.button("Back", on_click=stepper.previous).props("flat no-caps")
                        return
                    types = ["All"] + sorted({i["type"] for i in items})
                    shown = [i for i in items if st["filter"] in ("All", i["type"])]
                    with ui.row().classes("w-full items-center gap-1"):
                        if len(types) > 2:
                            for t in types:
                                n = len(items) if t == "All" else sum(i["type"] == t for i in items)
                                ui.button(f"{t} ({n})", on_click=lambda t=t: (st.update(filter=t), checklist.refresh())) \
                                    .props(f"{'unelevated' if st['filter'] == t else 'outline'} dense no-caps size=sm")
                        ui.space()
                        ui.button("Select all", on_click=lambda: select([i["url"] for i in shown if i["allowed"]], True)) \
                            .props("flat dense no-caps size=sm")
                        ui.button("Clear", on_click=lambda: select([i["url"] for i in shown], False)) \
                            .props("flat dense no-caps size=sm")
                    with ui.scroll_area().classes("w-full h-72").style("border:1px solid var(--wb-border);border-radius:8px"):
                        for i in shown:
                            with ui.row().classes(f"fs-row w-full no-wrap items-start {'' if i['allowed'] else 'fs-off'}"):
                                ui.checkbox(value=i["url"] in st["selected"],
                                            on_change=lambda e, u=i["url"]: select([u], e.value, whole=False)) \
                                    .props("dense").set_enabled(i["allowed"])
                                type_badge(i["name"])
                                with ui.column().classes("grow gap-0 min-w-0"):
                                    ui.label(i["name"]).classes("ellipsis1 w-full font-medium").tooltip(i["url"])
                                    if i["text"] and i["text"].lower() != i["name"].lower():
                                        ui.label(i["text"]).classes("muted text-xs ellipsis1 w-full")
                                if i["other_site"]:
                                    ui.badge(i["host"], color="orange").props("outline") \
                                        .tooltip("This file is on another website than the page")
                                if not i["allowed"]:
                                    ui.label("not an allowed website").classes("muted text-xs")
                                ui.label(file_size(i["size"]) if i["size"] else "").classes("muted text-xs w-16 text-right")
                                ui.button(icon="visibility", on_click=lambda i=i: show_preview(i)) \
                                    .props("flat dense round size=sm").tooltip("Preview").set_enabled(i["allowed"])
                    preview_view()
                    checklist_nav()

                @ui.refreshable
                def preview_view():
                    pv = st.get("preview")
                    if not pv:
                        return
                    item = pv["item"]
                    with ui.column().classes("w-full gap-1 p-2 mt-2") \
                            .style("border:1px solid var(--wb-border);border-radius:8px"):
                        with ui.row().classes("w-full items-center gap-2 no-wrap"):
                            ui.icon("visibility", size="xs").classes("muted")
                            type_badge(item["name"])
                            ui.label(item["name"]).classes("font-medium ellipsis1 grow")
                            if item["allowed"]:
                                ui.checkbox("Download this file", value=item["url"] in st["selected"],
                                            on_change=lambda e, u=item["url"]: select([u], e.value)).props("dense")
                            ui.button(icon="close", on_click=lambda: (st.update(preview=None), preview_view.refresh())) \
                                .props("flat dense round size=sm").tooltip("Close the preview")
                        if pv["status"] == "loading":
                            with ui.row().classes("items-center gap-2 p-2"):
                                ui.spinner(size="sm")
                                ui.label("Loading a preview (the file is fetched and read on this computer, not kept)…") \
                                    .classes("muted text-xs")
                            return
                        r = pv["result"]
                        with ui.scroll_area().classes("w-full h-96"):
                            if r["kind"] == "pages":
                                for png in r["pages"]:
                                    ui.image("data:image/png;base64," + base64.b64encode(png).decode()) \
                                        .classes("w-full").style("border:1px solid var(--wb-border);margin-bottom:8px")
                            elif r["kind"] == "text":
                                ui.label(r["text"] or "(no text)").classes("whitespace-pre-wrap text-xs")
                            elif r["kind"] == "table":
                                for name, rows in r["sheets"]:
                                    if len(r["sheets"]) > 1:
                                        ui.label(name).classes("font-medium text-xs pt-1")
                                    ui.html("<table class='pv-table'>" + "".join(
                                        "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>"
                                        for row in rows) + "</table>")
                            else:
                                ui.label(r["reason"]).classes("muted text-sm")
                        more = {"pages": r.get("total", 0) > len(r.get("pages", [])), "text": r.get("more"),
                                "table": r.get("more")}.get(r["kind"])
                        if more:
                            ui.label(f"First {len(r['pages'])} of {r['total']} pages." if r["kind"] == "pages"
                                     else "Only the beginning is shown.").classes("muted text-xs")

                async def show_preview(item):
                    st["preview"] = {"item": item, "status": "loading", "result": None}
                    preview_view.refresh()
                    tmp = settings.DATA_DIR / "preview" / uuid.uuid4().hex
                    try:
                        tmp.mkdir(parents=True)
                        if item.get("via") == "browser" and st["browser"]:
                            out = await st["browser"].download(item, tmp, "replace")
                        else:
                            out = await webfetch.download(item, tmp, "replace")
                        result = await asyncio.to_thread(preview.show, Path(out["path"]))
                    except webfetch.FetchError as e:
                        result = {"kind": "none", "reason": str(e)}
                    except httpx.HTTPError as e:
                        result = {"kind": "none", "reason": webfetch.network_error(e, "Network error")}
                    except Exception as e:
                        result = {"kind": "none", "reason": f"No preview: {e}"}
                    finally:
                        shutil.rmtree(tmp, ignore_errors=True)
                    if (st.get("preview") or {}).get("item") is item:      # still the file being previewed
                        st["preview"] = {"item": item, "status": "done", "result": result}
                        preview_view.refresh()

                @ui.refreshable
                def checklist_nav():
                    n = len(st["selected"])
                    with ui.stepper_navigation():
                        ui.button(f"Next ({n} selected)", on_click=stepper.next) \
                            .props("unelevated no-caps").set_enabled(n > 0)
                        ui.button("Back", on_click=stepper.previous).props("flat no-caps")

                def select(urls, on, whole=True):
                    for u in urls:
                        (st["selected"].add if on else st["selected"].discard)(u)
                    (checklist if whole else checklist_nav).refresh()

                checklist()

            # 3 ---------------------------------------------------------------- destination
            with ui.step("Save to", icon="folder"):
                project_row = None
                if self.project:
                    ui.radio({"project": f"The project folder ({self.project['name']})", "other": "Another folder"},
                             value=st["dest"], on_change=lambda e: set_dest(e.value)).props("dense")
                    with ui.row().classes("w-full items-center gap-2 no-wrap") as project_row:
                        ui.html(f"<code class='wrap-anywhere'>{html.escape(self.project['folder'])}</code>") \
                            .classes("muted text-xs")
                        ui.label("/").classes("muted")
                        sub_in = ui.input("Subfolder (optional)", value="downloads").props("outlined dense") \
                            .classes("w-56")
                with ui.column().classes("w-full gap-1") as other_box:
                    with ui.row().classes("w-full items-center gap-2 no-wrap"):
                        other_in = ui.input(placeholder="/Users/you/Documents/reports  or  S:\\Team\\reports") \
                            .props("outlined dense").classes("grow")
                        picker = FolderPicker(other_in)
                        ui.button("Browse…", on_click=picker.toggle).props("outline no-caps")
                    picker.view()
                ui.label("If a file with the same name is already there:").classes("muted text-xs pt-2")
                on_exists = ui.radio({"skip": "Skip it", "keep": "Keep both (adds “(2)” to the new name)",
                                      "replace": "Replace it"}, value="skip").props("dense inline").classes("text-sm")
                dest_msg = ui.label("").classes("err text-xs")
                with ui.stepper_navigation():
                    ui.button("Download", icon="download", on_click=lambda: start()).props("unelevated no-caps")
                    ui.button("Back", on_click=stepper.previous).props("flat no-caps")

                def set_dest(value):
                    st["dest"] = value
                    dest_msg.set_text("")
                    if project_row:
                        project_row.set_visibility(value == "project")
                    other_box.set_visibility(value == "other")
                set_dest(st["dest"])

            # 4 ---------------------------------------------------------------- download
            with ui.step("Download", icon="downloading"):
                @ui.refreshable
                def progress_view():
                    rows = st["results"]
                    if not rows:
                        return
                    finished = sum(r["status"] not in ("waiting", "downloading") for r in rows)
                    ui.linear_progress(value=finished / len(rows), show_value=False).props("rounded size=8px")
                    ui.label(f"{finished} of {len(rows)} done").classes("muted text-xs")
                    icons = {"waiting": ("schedule", "muted"), "downloading": ("downloading", "text-primary"),
                             "saved": ("check_circle", "text-positive"), "skipped": ("remove_circle_outline", "muted"),
                             "failed": ("error", "text-negative"), "cancelled": ("block", "muted")}
                    with ui.scroll_area().classes("w-full h-56"):
                        for r in rows:
                            icon, cls = icons[r["status"]]
                            with ui.row().classes("w-full items-center gap-2 no-wrap fs-row"):
                                ui.icon(icon, size="xs").classes(cls)
                                ui.label(r["item"]["name"]).classes("ellipsis1 grow")
                                if r["status"] == "downloading":
                                    ui.label((file_size(r["done"]) + (f" of {file_size(r['total'])}" if r["total"] else ""))
                                             if r["done"] else "downloading…").classes("muted text-xs")
                                elif r["msg"]:
                                    ui.label(r["msg"]).classes(f"text-xs {'err' if r['status'] == 'failed' else 'muted'} ellipsis1") \
                                        .style("max-width:60%").tooltip(r["msg"])
                    with ui.stepper_navigation():
                        ui.button("Stop", on_click=lambda: st.update(cancel=True)).props("outline no-caps") \
                            .set_enabled(st["running"] and not st["cancel"])

                progress_view()

            # 5 ---------------------------------------------------------------- result
            with ui.step("Done", icon="task_alt"):
                @ui.refreshable
                def result_view():
                    rows = st["results"]
                    saved = [r for r in rows if r["status"] == "saved"]
                    skipped = [r for r in rows if r["status"] == "skipped"]
                    failed = [r for r in rows if r["status"] in ("failed", "cancelled")]
                    parts = [f"{len(saved)} saved"] + ([f"{len(skipped)} skipped (already there)"] if skipped else []) \
                        + ([f"{len(failed)} not downloaded"] if failed else [])
                    ui.label(" · ".join(parts)).classes("font-medium")
                    if saved:
                        folder = str(Path(saved[0]["path"]).parent)
                        ui.html(f"<code class='wrap-anywhere'>{html.escape(folder)}</code>").classes("muted text-xs")
                    for r in failed:
                        ui.label(f"✗ {r['item']['name']}: {r['msg']}").classes("err text-xs")
                    readable = [r["path"] for r in saved + skipped
                                if Path(r["path"]).suffix.lower() in fs.SUPPORTED and Path(r["path"]).exists()]
                    with ui.stepper_navigation():
                        if readable:
                            ui.button(f"Attach to chat ({len(readable)})", icon="attach_file",
                                      on_click=lambda: use(readable, "chat")).props("unelevated no-caps")
                            if self.project:
                                ui.button(f"Add to project context ({len(readable)})", icon="library_add",
                                          on_click=lambda: use(readable, "context")).props("outline no-caps")
                        ui.button("Another page", on_click=lambda: restart()).props("flat no-caps")
                        ui.button("Close", on_click=close).props("flat no-caps")
                    if saved and len(readable) < len(saved + skipped):
                        ui.label("CSV, Excel, PowerPoint and older Office files are saved but can't be read in a chat "
                                 "(PDF, Word, Text and Markdown can).").classes("muted text-xs")

                result_view()

        async def do_scan(browser: bool = False):
            """The plain scan first; pages that need a sign-in (or browser=True) go through the browser."""
            scan_msg.set_text("")
            stepper.set_value("Web address")        # also when rescanning from the empty checklist
            url = (url_in.value or "").strip()
            if not url:
                scan_msg.set_text("Type or paste a web address.")
                return
            scan_btn.props("loading")
            sign_btn.set_enabled(False)
            try:
                sc = None
                if not browser:
                    try:
                        sc = await webfetch.scan(url)
                    except webfetch.SignInNeeded:
                        pass
                if sc is None:
                    release_browser(st)
                    st["browser"] = browserfetch.BrowserSession()
                    sc = await st["browser"].scan(url, scan_status.set_text)
                else:
                    try:
                        await asyncio.wait_for(webfetch.probe([i for i in sc["items"][:200]]), timeout=20)
                    except asyncio.TimeoutError:
                        pass
            except webfetch.FetchError as e:
                scan_msg.set_text(str(e))
                return
            except httpx.HTTPError as e:
                scan_msg.set_text(webfetch.network_error(e, "Could not open the page"))
                return
            except Exception as e:
                scan_msg.set_text(f"Could not read the page: {e}")
                return
            finally:
                scan_btn.props(remove="loading")
                sign_btn.set_enabled(True)
                scan_status.set_text("")
            st.update(scan=sc, preview=None, filter="All", selected={i["url"] for i in sc["items"] if sc["direct"] and i["allowed"]})
            checklist.refresh()
            stepper.next()

        def dest_folder() -> Path:
            if st["dest"] == "project":
                parts = [p for p in (sub_in.value or "").replace("\\", "/").split("/") if p.strip() not in ("", ".", "..")]
                if parts and parts[0] == projects.META:
                    raise ValueError(f"{projects.META} is reserved for the app.")
                folder = Path(self.project["folder"]).joinpath(*(re.sub(r'[<>:"|?*]', "_", p).strip() for p in parts))
                folder.mkdir(parents=True, exist_ok=True)
                return folder
            value = (other_in.value or "").strip()
            if not value:
                raise ValueError("Choose a folder (type its path or use Browse…).")
            folder = fs._abs(value)
            if not folder.is_dir():
                raise ValueError(f"{folder} doesn't exist.")
            return folder

        def refresh_progress(force=False):
            now = time.monotonic()
            if force or now - st["last_refresh"] > 0.25:
                st["last_refresh"] = now
                progress_view.refresh()

        async def start():
            try:
                folder = await asyncio.to_thread(dest_folder)
            except Exception as e:
                dest_msg.set_text(str(e))
                return
            dest_msg.set_text("")
            items = [i for i in st["scan"]["items"] if i["url"] in st["selected"]]
            st.update(results=[{"item": i, "status": "waiting", "msg": "", "path": "", "done": 0, "total": None}
                               for i in items], running=True, cancel=False)
            closable(False)
            stepper.next()
            progress_view.refresh()
            for r in st["results"]:
                if st["cancel"]:
                    r.update(status="cancelled", msg="stopped")
                    continue
                r["status"] = "downloading"
                refresh_progress(True)

                def progress(done, total, r=r):
                    r.update(done=done, total=total)
                    refresh_progress()
                try:
                    if r["item"].get("via") == "browser" and st["browser"]:
                        out = await st["browser"].download(r["item"], folder, on_exists.value)
                    else:
                        out = await webfetch.download(r["item"], folder, on_exists.value, progress)
                    r.update(status=out["status"], path=out["path"],
                             msg=Path(out["path"]).name if out["status"] == "saved" else "already there")
                except webfetch.FetchError as e:
                    r.update(status="failed", msg=str(e))
                except httpx.HTTPError as e:
                    r.update(status="failed", msg=webfetch.network_error(e, "Network error"))
                except OSError as e:
                    r.update(status="failed", msg=f"Could not write the file: {e}")
                refresh_progress(True)
            st["running"] = False
            closable(True)
            progress_view.refresh()
            result_view.refresh()
            stepper.next()

        def restart():
            release_browser(st)
            st.update(scan=None, selected=set(), results=[], preview=None)
            checklist.refresh()
            progress_view.refresh()
            result_view.refresh()
            stepper.set_value("Web address")

        async def use(paths, where):
            close()
            if where == "context":
                inside = [p for p in paths if Path(self.project["folder"]).resolve() in Path(p).resolve().parents]
                outside = [p for p in paths if p not in inside]
                metas = await asyncio.to_thread(projects.add_paths, self.project["id"], inside) if inside else []
                for p in outside:
                    metas.append(await asyncio.to_thread(projects.add_upload, self.project["id"], Path(p).name,
                                                         Path(p).read_bytes()))
                self.project_notice = report(metas)
                self.reload_project()
                self.main.refresh()
                self.composer.refresh()
                return

            def ingest(paths):
                out = []
                for p in paths:
                    try:
                        out.append({"ok": True, **documents.meta(documents.ingest(Path(p)))})
                    except Exception as e:
                        out.append({"ok": False, "name": Path(p).name, "error": str(e)})
                return out
            self.attach_metas(await asyncio.to_thread(ingest, paths))
            if followup:                        # the rest of the chat message, ready to send about the files
                self.input.value = followup
                self.client.run_javascript("document.querySelector('.wb-footer textarea')?.focus()")

        if url:
            ui.timer(0.1, lambda: do_scan(), once=True)
        return st

    async def settings_dialog(self):
        s = settings.load()
        draft = {name: {k: v for k, v in p.items() if k != "api_key"} for name, p in s["providers"].items()}
        keys = {name: "" for name in draft}
        folders = list(s["allowed_folders"])
        web = dict(s["web"])
        active = {"name": s["active_provider"]}

        with self.root, ui.dialog() as dialog, ui.card().classes("w-[600px] max-w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Settings").classes("font-semibold text-base")
                ui.button(icon="close", on_click=dialog.close).props("flat dense round size=sm")
            with ui.tabs().classes("w-full").props("dense align=left no-caps") as tabs:
                tab_objs = {name: ui.tab(name, label=p["label"]) for name, p in draft.items()}
                ui.tab("_folders", label="Folders")
                ui.tab("_web", label="Web")
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

                with ui.tab_panel("_web").classes("gap-2 px-0"):
                    ui.label("Used by “From web”: downloading documents from a web page you name. The AI model is "
                             "not involved; only plain downloads, no sign-ins or cookies.").classes("muted text-xs")
                    domains = ui.textarea("Allowed websites, one per line (empty = any website you type)",
                                          value="\n".join(web["allowed_domains"]),
                                          placeholder="intranet.company.com\nsec.gov").props("outlined autogrow") \
                        .classes("w-full")
                    domains.on("update:model-value", lambda e: web.update(
                        allowed_domains=[d for d in (e.args or "").splitlines() if d.strip()]))
                    ui.label("A website also allows its subdomains (company.com allows www.company.com).") \
                        .classes("muted text-xs")
                    ui.checkbox("Use the system proxy settings (the company proxy)").bind_value(web, "use_system_proxy") \
                        .props("dense")

            def save():
                body = {"active_provider": active["name"], "allowed_folders": folders, "web": web,
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
