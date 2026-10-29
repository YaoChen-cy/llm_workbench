"""
Downloading documents from a web page the user names (the "Download from web" workflow).

    scan(url)                -> the page's document links (or the document itself when the URL is one)
    read(url, folder)        -> the page as a Markdown file (or the document the URL points to), for the chat
    probe(items)             -> sizes from HEAD requests, where the server answers them
    download(item, folder)   -> one file saved into `folder`

Safety rules (the LLM is not involved; the user types the URL and ticks the files):
- http/https only, no user:password in URLs, only plain GET/HEAD requests: no JavaScript, no cookies kept,
  no forms, no links followed beyond the one page
- every redirect hop is checked again (at most 5), and against the domain allowlist when one is set
- only document types (PDF, Word, Excel, PowerPoint, CSV, text); the file's first bytes must match its type,
  so a login page saved as "report.pdf" is refused
- files are written only into the chosen folder (no size or count limits)
Uses the system proxy settings (company proxy) unless Settings → Web says otherwise, and the system's trusted
certificates (Windows certificate store / macOS Keychain), so internal sites signed by the company's own root
certificate open as they do in the browser. Certificates are always verified.
"""
import asyncio
import re
import ssl
from pathlib import Path
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

import httpx

from . import settings

USER_AGENT = "LLM-Workbench/1.0 (document download)"
MAX_REDIRECTS = 5
MAX_PAGE_BYTES = 5 * 1024 * 1024
TIMEOUT = httpx.Timeout(connect=15, read=60, write=30, pool=15)

# suffix -> (label, first bytes the file must start with; None = text, checked separately)
DOC_TYPES = {
    ".pdf": ("PDF", (b"%PDF",)),
    ".docx": ("Word", (b"PK\x03\x04",)),
    ".xlsx": ("Excel", (b"PK\x03\x04",)),
    ".pptx": ("PowerPoint", (b"PK\x03\x04",)),
    ".doc": ("Word 97", (b"\xd0\xcf\x11\xe0",)),
    ".xls": ("Excel 97", (b"\xd0\xcf\x11\xe0",)),
    ".ppt": ("PowerPoint 97", (b"\xd0\xcf\x11\xe0",)),
    ".csv": ("CSV", None),
    ".txt": ("Text", None),
    ".md": ("Markdown", None),
}
_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.ms-powerpoint": ".ppt",
    "text/csv": ".csv",
}


class FetchError(Exception):
    pass


class SignInNeeded(FetchError):
    """The page asks for a sign-in: the From web steps then open it in the browser (browserfetch)."""


# Sign-in services a company site may send the browser to
LOGIN_HOSTS = ("login.microsoftonline.com", "login.microsoft.com", "login.windows.net", "login.live.com",
               "id.atlassian.com", "okta.com", "oktapreview.com", "onelogin.com", "pingone.com", "duosecurity.com",
               "accounts.google.com")


def is_login_host(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in LOGIN_HOSTS) or \
        bool(re.match(r"^(adfs|sts|sso|login|auth|signin)\d*[.-]", host))


# ---------------------------------------------------------------- rules

def options() -> dict:
    return settings.load()["web"]


def host_allowed(host: str, allowlist: list[str]) -> bool:
    host = host.lower().rstrip(".")
    return not allowlist or any(host == d or host.endswith("." + d) for d in
                                (a.lower().strip().lstrip("*.").rstrip(".") for a in allowlist if a.strip()))


def check_url(url: str, opts: dict | None = None) -> str:
    """The URL without its #fragment, or FetchError when the rules refuse it."""
    opts = opts or options()
    url = urldefrag(url.strip())[0]
    if "://" not in url and re.match(r"^[a-z][a-z0-9+.-]*:(?!\d)", url, re.I):
        raise FetchError("Only http:// and https:// addresses can be opened.")     # javascript:, mailto:, data:…
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url if "://" not in url else url
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        raise FetchError("Only http:// and https:// addresses can be opened.")
    if not parts.hostname:
        raise FetchError("This is not a web address.")
    if parts.username or parts.password:
        raise FetchError("Addresses with a user name or password in them are not opened.")
    if not host_allowed(parts.hostname, opts["allowed_domains"]):
        raise FetchError(f"{parts.hostname} is not in the allowed websites (Settings → Web).")
    return url


def _ssl_context() -> ssl.SSLContext | bool:
    """The operating system's certificate store (what the browser trusts), else Python's own list (certifi)."""
    try:
        import truststore
    except ImportError:
        return True
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def network_error(e: Exception, prefix: str) -> str:
    """A readable message for a failed connection."""
    text = str(e)
    if "certificate" in text.lower() or "CERTIFICATE_VERIFY_FAILED" in text:
        return ("The site's security certificate is not trusted by this computer, so it was not opened. If the page "
                f"opens in your browser without a warning, ask IT to install the company's root certificate. ({text})")
    return f"{prefix}: {e.__class__.__name__} {text}".strip()


def _client(opts: dict) -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=False, timeout=TIMEOUT, trust_env=bool(opts.get("use_system_proxy", True)),
                             verify=_ssl_context(),
                             headers={"User-Agent": USER_AGENT})


async def _open(client: httpx.AsyncClient, url: str, opts: dict, method: str = "GET") -> httpx.Response:
    """Send the request, following redirects by hand so every hop is checked. The caller closes the response."""
    for _ in range(MAX_REDIRECTS + 1):
        url = check_url(url, opts)
        r = await client.send(client.build_request(method, url), stream=True)
        client.cookies.clear()                          # nothing is remembered between requests
        if r.status_code in (301, 302, 303, 307, 308) and "location" in r.headers:
            await r.aclose()
            url = urljoin(url, r.headers["location"])
            if is_login_host(urlsplit(url).hostname or ""):
                raise SignInNeeded("The site sends you to a sign-in page.")
            continue
        if r.status_code in (401, 403):
            await r.aclose()
            raise SignInNeeded(f"The site refused access (HTTP {r.status_code}); it needs a sign-in.")
        if r.status_code >= 400:
            await r.aclose()
            raise FetchError(f"The site answered HTTP {r.status_code}.")
        return r
    raise FetchError(f"Too many redirects (more than {MAX_REDIRECTS}).")


def _suffix_of(url: str, content_type: str = "") -> str:
    suffix = Path(unquote(urlsplit(url).path)).suffix.lower()
    if suffix in DOC_TYPES:
        return suffix
    return _CONTENT_TYPES.get(content_type.split(";")[0].strip().lower(), "")


def _name_of(url: str, suffix: str) -> str:
    name = Path(unquote(urlsplit(url).path)).name or "download"
    return name if Path(name).suffix.lower() == suffix else f"{Path(name).stem or 'download'}{suffix}"


def _item(url: str, suffix: str, text: str, page_host: str, opts: dict) -> dict:
    host = (urlsplit(url).hostname or "").lower()
    return {"url": url, "name": _name_of(url, suffix), "suffix": suffix, "type": DOC_TYPES[suffix][0],
            "text": re.sub(r"\s+", " ", text).strip()[:160], "host": host, "other_site": host != page_host,
            "allowed": host_allowed(host, opts["allowed_domains"]), "size": None}


# ---------------------------------------------------------------- scan / probe / download

async def scan(url: str) -> dict:
    """{"url", "title", "direct": bool, "items": [...]}: the document links on the page at `url`."""
    import lxml.html

    opts = options()
    url = check_url(url, opts)
    async with _client(opts) as client:
        r = await _open(client, url, opts)
        try:
            final = str(r.url)
            ctype = r.headers.get("content-type", "")
            suffix = _suffix_of(final, ctype)
            host = (urlsplit(final).hostname or "").lower()
            if suffix and "html" not in ctype:
                item = _item(final, suffix, "", host, opts)
                item["size"] = int(r.headers["content-length"]) if r.headers.get("content-length", "").isdigit() else None
                return {"url": final, "title": item["name"], "direct": True, "items": [item]}
            if "html" not in ctype and ctype:
                raise FetchError(f"This address is neither a web page nor a supported document ({ctype.split(';')[0]}).")
            charset = r.charset_encoding
            body = bytearray()
            async for chunk in r.aiter_bytes():
                body += chunk
                if len(body) > MAX_PAGE_BYTES:
                    break
        finally:
            await r.aclose()
    try:            # the server's charset, else UTF-8 (lxml alone would guess Latin-1 without a <meta charset>)
        page = lxml.html.document_fromstring(bytes(body).decode(charset or "utf-8", "replace") or "<html></html>",
                                             base_url=final)
    except (ValueError, LookupError):
        page = lxml.html.document_fromstring(bytes(body) or b"<html></html>", base_url=final)
    if page.xpath("//input[@type='password']"):
        raise SignInNeeded("The page is a sign-in form.")
    page.make_links_absolute(final, resolve_base_href=True)
    title = (page.findtext(".//title") or "").strip() or host
    items, seen = [], set()
    for a in page.iter("a"):
        href = urldefrag(a.get("href") or "")[0]
        if not href.lower().startswith(("http://", "https://")) or href in seen:
            continue
        suffix = _suffix_of(href)
        if not suffix:
            continue
        seen.add(href)
        items.append(_item(href, suffix, a.text_content() or a.get("title") or "", host, opts))
    return {"url": final, "title": re.sub(r"\s+", " ", title)[:200], "direct": False, "items": items}


async def probe(items: list[dict], limit: int = 6):
    """Fill in item["size"] from HEAD requests (servers that refuse HEAD simply leave it unknown)."""
    opts = options()
    sem = asyncio.Semaphore(limit)

    async def one(client, item):
        async with sem:
            try:
                r = await _open(client, item["url"], opts, method="HEAD")
                await r.aclose()
                n = r.headers.get("content-length", "")
                item["size"] = int(n) if n.isdigit() else None
            except Exception:
                pass

    async with _client(opts) as client:
        await asyncio.gather(*(one(client, it) for it in items if it["allowed"] and it["size"] is None))


def _safe_name(name: str, suffix: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(name).name).strip(" .") or "download"
    name = name[:150]
    return name if Path(name).suffix.lower() == suffix else name + suffix


def _disposition_name(header: str) -> str:
    m = re.search(r"filename\*\s*=\s*[^']*'[^']*'([^;]+)", header, re.I) or \
        re.search(r'filename\s*=\s*"?([^";]+)"?', header, re.I)
    return unquote(m.group(1).strip()) if m else ""


def _check_start(head: bytes, suffix: str):
    magic = DOC_TYPES[suffix][1]
    looks_html = head.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html"))
    if magic is None:
        if b"\x00" in head[:2048] or looks_html:
            raise FetchError("The server sent a web page or binary data instead of a text file.")
        return
    if not head.startswith(magic):
        raise FetchError("The server sent a web page instead of the document (it may need a sign-in)." if looks_html
                         else f"The file is not a real {DOC_TYPES[suffix][0]} file.")


def target_path(folder: Path, name: str, on_exists: str) -> Path | None:
    """Where to save `name` in `folder`: None to skip it ("skip"), a free name ("keep"), or the same name ("replace")."""
    dest = folder / name
    if not dest.exists() or on_exists == "replace":
        return dest
    if on_exists == "skip":
        return None
    stem, suffix, n = dest.stem, dest.suffix, 2
    while (folder / f"{stem} ({n}){suffix}").exists():
        n += 1
    return folder / f"{stem} ({n}){suffix}"


async def download(item: dict, folder: Path, on_exists: str = "skip", progress=None) -> dict:
    """Save one checklist item into `folder`. Returns {"status": "saved"|"skipped", "path"}; raises FetchError.
    progress(done_bytes, total_bytes or None) is called while downloading."""
    opts = options()
    folder = folder.resolve()
    async with _client(opts) as client:
        r = await _open(client, item["url"], opts)
        try:
            total = int(r.headers["content-length"]) if r.headers.get("content-length", "").isdigit() else None
            name = _safe_name(_disposition_name(r.headers.get("content-disposition", "")) or item["name"], item["suffix"])
            dest = target_path(folder, name, on_exists)
            if dest is None:
                return {"status": "skipped", "path": str(folder / name)}
            if dest.resolve().parent != folder:
                raise FetchError("Refused a file name that points outside the chosen folder.")
            part = dest.with_name(dest.name + ".part")
            done, checked = 0, False
            try:
                with open(part, "wb") as f:
                    async for chunk in r.aiter_bytes():
                        if not checked:
                            _check_start(chunk, item["suffix"])
                            checked = True
                        done += len(chunk)
                        f.write(chunk)
                        if progress:
                            progress(done, total)
                if not checked:
                    raise FetchError("The server sent an empty file.")
                part.replace(dest)
            finally:
                part.unlink(missing_ok=True)
        finally:
            await r.aclose()
    return {"status": "saved", "path": str(dest)}


# ---------------------------------------------------------------- reading a page (for the chat, not the download steps)

READABLE = (".pdf", ".docx", ".txt", ".md")      # what the chat can read (documents.py)
_DROP = ("script", "style", "noscript", "template", "svg", "canvas", "iframe", "nav", "footer", "aside", "form",
         "button", "select", "dialog")
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCKS = _HEADINGS | {"p", "div", "section", "article", "main", "header", "ul", "ol", "li", "table", "pre",
                       "blockquote", "dl", "dt", "dd", "figure", "figcaption", "hr", "br", "address", "details",
                       "summary", "tr", "td", "th", "tbody", "thead"}


def _ws(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def _has_block(el) -> bool:
    return any(isinstance(d.tag, str) and d.tag in _BLOCKS for d in el.iterdescendants())


def _table_md(table) -> str:
    rows = []
    for tr in table.xpath(".//tr"):
        cells = [_ws(c.text_content()).replace("|", "\\|") for c in tr.xpath("./th|./td")]
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    if width == 1:
        return "\n\n".join(r[0] for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows[1:]])


def _walk(el, out: list[str]):
    buf = [el.text or ""]

    def flush():
        t = re.sub(r" ([.,;:!?)])", r"\1", _ws(" ".join(buf)))      # "sales ." from "<a>sales</a>."
        if t:
            out.append(t)
        buf.clear()

    for child in el:
        tag = child.tag if isinstance(child.tag, str) else ""
        if tag == "br":
            flush()
        elif tag in _BLOCKS or (tag and _has_block(child)):
            flush()
            _block(child, out)
        elif tag:
            buf.append(child.text_content())
        buf.append(child.tail or "")
    flush()


def _block(el, out: list[str]):
    tag = el.tag
    if tag in _HEADINGS:
        if t := _ws(el.text_content()):
            out.append("#" * int(tag[1]) + " " + t)
    elif tag == "table":
        if t := _table_md(el):
            out.append(t)
    elif tag == "pre":
        if t := el.text_content().strip():
            out.append("```\n" + t + "\n```")
    elif tag in ("ul", "ol"):
        n = 0
        for li in el:
            if not isinstance(li.tag, str):
                continue
            sub: list[str] = []
            (_walk if li.tag == "li" else _block)(li, sub)
            if not sub:
                continue
            n += 1
            out.append(("- " if tag == "ul" else f"{n}. ") + sub[0])
            out.extend(sub[1:])
    elif tag != "hr":
        _walk(el, out)


def html_to_markdown(text: str, base_url: str = "") -> tuple[str, str]:
    """(title, Markdown) of a web page: headings, paragraphs, lists and tables; menus, scripts and forms left out."""
    import lxml.html
    from lxml import etree

    page = lxml.html.document_fromstring(text or "<html></html>", base_url=base_url or None)
    title = _ws(page.findtext(".//title") or "")
    etree.strip_elements(page, *_DROP, etree.Comment, with_tail=False)
    candidates = page.xpath("//main|//article|//*[@role='main']")
    body = page.find("body")
    root = max(candidates, key=lambda e: len(e.text_content())) if candidates else (body if body is not None else page)
    out: list[str] = []
    _block(root, out) if root.tag in _BLOCKS else _walk(root, out)
    return title, "\n\n".join(out)


def page_file(folder: Path, url: str, title: str, markdown: str) -> dict:
    """Save a page's text as a Markdown file for the chat: {"path", "name"}."""
    title = title or urlsplit(url).hostname or "Web page"
    name = _safe_name(title[:80], ".md")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(f"# {title}\n\nSource: {url}\n\n{markdown}\n", "utf-8")
    return {"path": str(path), "name": name, "url": url}


async def read(url: str, folder: Path) -> dict:
    """The page at url as a Markdown file in folder, or the document url points to: {"path", "name", "url"}.
    Raises SignInNeeded when the page asks for a sign-in (the caller then uses browserfetch)."""
    opts = options()
    url = check_url(url, opts)
    async with _client(opts) as client:
        r = await _open(client, url, opts)
        try:
            final = str(r.url)
            ctype = r.headers.get("content-type", "")
            suffix = _suffix_of(final, ctype)
        finally:
            await r.aclose()
    if suffix and "html" not in ctype:
        if suffix not in READABLE:
            raise FetchError(f"This address is a {DOC_TYPES[suffix][0]} file, which can't be read in a chat. "
                             "Ask to download it instead (for example: \"download the files from …\").")
        item = _item(final, suffix, "", (urlsplit(final).hostname or "").lower(), opts)
        out = await download(item, folder, "keep")
        return {"path": out["path"], "name": Path(out["path"]).name, "url": final}
    if "html" not in ctype and not ctype.startswith("text/"):
        raise FetchError(f"This address is neither a web page nor a readable document ({ctype.split(';')[0]}).")
    async with _client(opts) as client:          # read the page itself (the first request only looked at the type)
        r = await _open(client, url, opts)
        try:
            final, charset, body = str(r.url), r.charset_encoding, bytearray()
            async for chunk in r.aiter_bytes():
                body += chunk
                if len(body) > MAX_PAGE_BYTES:
                    break
        finally:
            await r.aclose()
    text = bytes(body).decode(charset or "utf-8", "replace")
    if "html" not in ctype:
        return page_file(folder, final, Path(urlsplit(final).path).name, text)
    if re.search(r"<input[^>]+type\s*=\s*[\"']?password", text, re.I):
        raise SignInNeeded("The page is a sign-in form.")
    title, md = html_to_markdown(text, final)
    if len(md) < 200 and re.search(r"<script", text, re.I):
        raise SignInNeeded("The page builds its content with JavaScript.")   # read it in the browser instead
    return page_file(folder, final, title, md)
