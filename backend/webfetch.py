"""
Downloading documents from a web page the user names (the "Download from web" workflow).

    scan(url)                -> the page's document links (or the document itself when the URL is one)
    probe(items)             -> sizes from HEAD requests, where the server answers them
    download(item, folder)   -> one file saved into `folder`

Safety rules (the LLM is not involved; the user types the URL and ticks the files):
- http/https only, no user:password in URLs, only plain GET/HEAD requests: no JavaScript, no cookies kept,
  no forms, no links followed beyond the one page
- every redirect hop is checked again (at most 5), and against the domain allowlist when one is set
- only document types (PDF, Word, Excel, PowerPoint, CSV, text); the file's first bytes must match its type,
  so a login page saved as "report.pdf" is refused
- size limit per file, a limit on files per run; files are written only into the chosen folder
Uses the system proxy settings (company proxy) unless Settings → Web says otherwise.
"""
import asyncio
import re
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


def _client(opts: dict) -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=False, timeout=TIMEOUT, trust_env=bool(opts.get("use_system_proxy", True)),
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
            continue
        if r.status_code in (401, 403):
            await r.aclose()
            raise FetchError(f"The site refused access (HTTP {r.status_code}); it may need a sign-in. "
                             "Download it in your browser and upload it instead.")
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
    limit = int(opts["max_file_mb"]) * 1024 * 1024
    folder = folder.resolve()
    async with _client(opts) as client:
        r = await _open(client, item["url"], opts)
        try:
            total = int(r.headers["content-length"]) if r.headers.get("content-length", "").isdigit() else None
            if total and total > limit:
                raise FetchError(f"The file is {total / 1048576:.0f} MB; the limit is {opts['max_file_mb']} MB.")
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
                        if done > limit:
                            raise FetchError(f"The file is larger than the {opts['max_file_mb']} MB limit.")
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
