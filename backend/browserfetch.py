"""
"From web" for pages that need a sign-in (SharePoint, Confluence, other intranet sites), through the browser installed
on this computer (Microsoft Edge, else Google Chrome), driven by Playwright.

    session = BrowserSession()
    await session.scan(url, status)            -> same shape as webfetch.scan()
    await session.download(item, folder, ...)  -> same shape as webfetch.download()
    await session.close()

How it works:
- the page is opened in the background (no window). When it asks for a sign-in, a browser window opens on it and the
  user signs in there; once the page is back on its own site the window closes and the work goes on in the background
  with that sign-in. If the site refuses the background browser even then, the window stays open until the end.
- SharePoint document libraries and Confluence pages are listed through their own REST interfaces, called from the
  signed-in page (so with the user's own permissions); other pages through their links after their JavaScript has run.
- files are downloaded by the browser itself, then checked like plain downloads (type, first bytes, chosen folder).

Nothing is kept: each session is a fresh in-memory browser profile, closed when the From web steps end. Passwords
are typed in the browser window only and never reach the app. The AI model is not involved, and the allowed-websites
rule (Settings → Web) applies to the page and the files as in webfetch. Playwright's own browsers are never
downloaded (`playwright install` is not used): only the installed Edge or Chrome.
"""
import asyncio
import re
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit

from . import webfetch
from .webfetch import FetchError

CHANNELS = ("msedge", "chrome")         # installed browsers, in order of preference
SIGN_IN_TIMEOUT = 600                   # seconds the user has to sign in
NAV_TIMEOUT = 60_000                    # ms


class _Loop:
    """Playwright runs on its own thread and event loop: the web server's loop can't start processes on Windows."""

    def __init__(self):
        self.loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True, name="browserfetch").start()

    async def run(self, coro):
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro, self.loop))


_loop: _Loop | None = None


def _runner() -> _Loop:
    global _loop
    if _loop is None:
        _loop = _Loop()
    return _loop


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


# JavaScript run in the page (our own code, not the site's)
_FETCH_JSON = """async (url) => {
    const r = await fetch(url, {credentials: 'include', headers: {Accept: 'application/json;odata=nometadata'}});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
}"""
_PAGE_INFO = """() => {
    const meta = n => document.querySelector(`meta[name="${n}"]`)?.content || '';
    const sp = window._spPageContextInfo || {};
    return {title: document.title, spWeb: sp.webAbsoluteUrl || '',
            confPage: meta('ajs-page-id'), confBase: meta('ajs-base-url'), confPath: meta('ajs-context-path')};
}"""
_LINKS = "() => [...document.querySelectorAll('a[href]')].map(a => [a.href, (a.innerText || a.title || '').trim()])"
_CLICK_DOWNLOAD = """(url) => {
    const a = document.createElement('a');
    a.href = url; a.download = ''; a.style.display = 'none';
    document.body.appendChild(a); a.click(); a.remove();
}"""


class BrowserSession:
    def __init__(self):
        self.pw = None
        self.browsers = []
        self.context = None
        self.page = None                     # the scanned page, signed in
        self.visible = False                 # the sign-in window had to stay open

    # ---------------------------------------------------------------- public (called from the web server's loop)

    async def scan(self, url: str, status=None) -> dict:
        main = asyncio.get_running_loop()
        say = (lambda text: main.call_soon_threadsafe(status, text)) if status else (lambda text: None)
        return await _runner().run(self._scan(url, say))

    async def download(self, item: dict, folder: Path, on_exists: str = "skip") -> dict:
        return await _runner().run(self._download(item, folder, on_exists))

    async def close(self):
        await _runner().run(self._close())

    # ---------------------------------------------------------------- browser

    async def _launch(self, headless: bool):
        from playwright.async_api import async_playwright
        if not self.pw:
            self.pw = await async_playwright().start()
        errors = []
        for channel in CHANNELS:
            try:
                browser = await self.pw.chromium.launch(channel=channel, headless=headless)
                self.browsers.append(browser)
                return browser
            except Exception as e:
                errors.append(f"{channel}: {str(e).splitlines()[0]}")
        raise FetchError("Pages that need a sign-in open in Microsoft Edge or Google Chrome, and neither could be "
                         "started (" + "; ".join(errors) + ").")

    async def _close(self):
        for b in self.browsers:
            try:
                await b.close()
            except Exception:
                pass
        self.browsers, self.context, self.page = [], None, None
        if self.pw:
            try:
                await self.pw.stop()
            except Exception:
                pass
            self.pw = None

    async def _goto(self, page, url: str):
        """Open url; returns (response or None, True when the URL itself is a file the browser downloads)."""
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        except Exception as e:
            if "Download is starting" in str(e) or "ERR_ABORTED" in str(e):
                return None, True
            raise FetchError(f"The page could not be opened: {str(e).splitlines()[0]}")
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass                             # pages that keep polling never go idle; what has loaded is enough
        return resp, False

    async def _needs_sign_in(self, page, resp, target: str) -> bool:
        host = _host(page.url)
        if resp is not None and resp.status in (401, 403):
            return True
        if host != target and webfetch.is_login_host(host):
            return True
        try:
            return await page.locator("input[type=password]").count() > 0
        except Exception:
            return False

    async def _sign_in(self, url: str, target: str, headless, say):
        """Let the user sign in in a visible window, then carry the sign-in over to the background browser."""
        say("This page needs a sign-in. Sign in in the browser window that opened; it closes by itself afterwards.")
        visible = await self._launch(headless=False)
        vctx = await visible.new_context(accept_downloads=True)
        vpage = await vctx.new_page()
        await self._goto(vpage, url)
        deadline = time.monotonic() + SIGN_IN_TIMEOUT
        while True:
            if vpage.is_closed() or not visible.is_connected():
                raise FetchError("The sign-in window was closed before the page opened.")
            try:
                if _host(vpage.url) == target and not await self._needs_sign_in(vpage, None, target):
                    break
            except Exception:
                pass                         # the page is navigating
            if time.monotonic() > deadline:
                raise FetchError("The sign-in was not finished in time. Try again.")
            await asyncio.sleep(1)
        try:
            await vpage.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        say("Signed in. Reading the page…")
        state = await vctx.storage_state()  # in memory only, never written to disk
        hctx = await headless.new_context(accept_downloads=True, storage_state=state)
        hpage = await hctx.new_page()
        resp, _ = await self._goto(hpage, url)
        if not await self._needs_sign_in(hpage, resp, target):
            await visible.close()
            self.browsers.remove(visible)
            return hctx, hpage
        await hctx.close()                  # the site won't accept the background browser: keep the window
        self.visible = True
        say("The site needs the browser window to stay open. Leave it open until the download is done.")
        return vctx, vpage

    # ---------------------------------------------------------------- scan

    async def _scan(self, url: str, say) -> dict:
        opts = webfetch.options()
        url = webfetch.check_url(url, opts)
        target = _host(url)
        say("Opening the page in the background browser…")
        headless = await self._launch(headless=True)
        ctx = await headless.new_context(accept_downloads=True)
        page = await ctx.new_page()
        resp, is_file = await self._goto(page, url)
        if is_file:
            self.context, self.page = ctx, page
            suffix = webfetch._suffix_of(url)
            if not suffix:
                raise FetchError("This address downloads a file that is not a supported document.")
            return {"url": url, "title": webfetch._name_of(url, suffix), "direct": True, "via": "browser",
                    "kind": "file", "items": [{**webfetch._item(url, suffix, "", target, opts), "via": "browser"}]}
        if await self._needs_sign_in(page, resp, target):
            await ctx.close()
            ctx, page = await self._sign_in(url, target, headless, say)
        self.context, self.page = ctx, page
        final = page.url
        webfetch.check_url(final, opts)     # where the page ended up must be allowed too
        say("Listing the documents…")
        info = await page.evaluate(_PAGE_INFO)
        kind, items = "page", []
        try:
            if (found := await self._sharepoint(page, final, info, opts)) is not None:
                kind, items = "sharepoint", found
            elif (found := await self._confluence(page, final, info, opts)) is not None:
                kind, items = "confluence", found
        except FetchError:
            raise
        except Exception as e:
            raise FetchError(f"The site's file list could not be read: {str(e).splitlines()[0]}")
        if kind == "page":
            items = await self._links(page, final, opts)
        title = re.sub(r"\s+", " ", info.get("title") or "").strip() or _host(final)
        return {"url": final, "title": title[:200], "direct": False, "via": "browser", "kind": kind, "items": items}

    def _browser_item(self, url, name, suffix, text, size, page_host, opts) -> dict:
        item = webfetch._item(url, suffix, text, page_host, opts)
        item.update(name=webfetch._safe_name(name, suffix), size=size, via="browser")
        return item

    async def _sharepoint(self, page, final: str, info: dict, opts) -> list[dict] | None:
        """Files in a SharePoint document library folder (None when the page isn't one)."""
        parts = urlsplit(final)
        query = parse_qs(parts.query)
        folder = (query.get("id") or query.get("RootFolder") or [""])[0]
        path = unquote(parts.path)
        if not folder and "/Forms/" in path:
            folder = path.split("/Forms/")[0]
        if not folder:
            return None
        web = info.get("spWeb") or ""
        if not web:
            m = re.match(r"(/(?:sites|teams)/[^/]+)", path)
            web = f"{parts.scheme}://{parts.netloc}{m.group(1) if m else ''}"
        q = quote(folder.replace("'", "''"), safe="/")
        data = await page.evaluate(_FETCH_JSON, f"{web}/_api/web/GetFolderByServerRelativePath(decodedurl='{q}')/Files"
                                                "?$select=Name,ServerRelativeUrl,Length&$top=5000")
        host, items = _host(final), []
        for f in data.get("value", []):
            suffix = Path(f.get("Name", "")).suffix.lower()
            if suffix not in webfetch.DOC_TYPES:
                continue
            fq = quote(f["ServerRelativeUrl"].replace("'", "''"), safe="/")
            url = f"{web}/_api/web/GetFileByServerRelativePath(decodedurl='{fq}')/$value"
            size = int(f["Length"]) if str(f.get("Length", "")).isdigit() else None
            items.append(self._browser_item(url, f["Name"], suffix, f["ServerRelativeUrl"], size, host, opts))
        return items

    async def _confluence(self, page, final: str, info: dict, opts) -> list[dict] | None:
        """Attachments of a Confluence page (None when the page isn't one)."""
        page_id = info.get("confPage") or ""
        if not page_id:
            m = re.search(r"/pages/(\d+)", final) or re.search(r"[?&]pageId=(\d+)", final)
            page_id = m.group(1) if m else ""
        if not page_id:
            return None
        parts = urlsplit(final)
        base = (info.get("confBase") or f"{parts.scheme}://{parts.netloc}{info.get('confPath') or ''}").rstrip("/")
        host, items = _host(final), []
        api = f"{base}/rest/api/content/{page_id}/child/attachment?limit=200"
        for _ in range(25):                  # 200 per page, at most 5,000 attachments
            data = await page.evaluate(_FETCH_JSON, api)
            for a in data.get("results", []):
                suffix = Path(a.get("title", "")).suffix.lower()
                link = (a.get("_links") or {}).get("download")
                if suffix not in webfetch.DOC_TYPES or not link:
                    continue
                size = (a.get("extensions") or {}).get("fileSize")
                items.append(self._browser_item(base + link, a["title"], suffix, "", size if isinstance(size, int)
                                                else None, host, opts))
            nxt = (data.get("_links") or {}).get("next")
            if not nxt:
                break
            api = base + nxt
        return items

    async def _links(self, page, final: str, opts) -> list[dict]:
        """Document links in the page as the browser shows it (after its JavaScript has run)."""
        host, items, seen = _host(final), [], set()
        for href, text in await page.evaluate(_LINKS):
            href = href.split("#")[0]
            if not href.lower().startswith(("http://", "https://")) or href in seen:
                continue
            suffix = webfetch._suffix_of(href)
            name_url = href
            if not suffix:                   # SharePoint's download.aspx?SourceUrl=/sites/x/report.pdf
                src = (parse_qs(urlsplit(href).query).get("SourceUrl") or [""])[0]
                suffix = webfetch._suffix_of(src) if src else ""
                name_url = urljoin(href, src)
            if not suffix:
                continue
            seen.add(href)
            name = webfetch._name_of(name_url, suffix)
            items.append(self._browser_item(href, name, suffix, text, None, host, opts))
        return items

    # ---------------------------------------------------------------- download

    async def _download(self, item: dict, folder: Path, on_exists: str) -> dict:
        opts = webfetch.options()
        url = webfetch.check_url(item["url"], opts)
        folder = folder.resolve()
        name = webfetch._safe_name(item["name"], item["suffix"])
        dest = webfetch.target_path(folder, name, on_exists)
        if dest is None:
            return {"status": "skipped", "path": str(folder / name)}
        if dest.resolve().parent != folder:
            raise FetchError("Refused a file name that points outside the chosen folder.")
        if not self.page or self.page.is_closed():
            raise FetchError("The browser window was closed. Scan the page again.")
        same_site = urlsplit(url)[:2] == urlsplit(self.page.url)[:2]
        page = self.page if same_site else await self.context.new_page()
        try:
            async with page.expect_download(timeout=NAV_TIMEOUT * 2) as info:
                if same_site:                # a link with "download" in the signed-in page: saved, never displayed
                    await page.evaluate(_CLICK_DOWNLOAD, url)
                else:
                    try:
                        await page.goto(url, timeout=NAV_TIMEOUT)
                    except Exception as e:
                        if "Download is starting" not in str(e) and "ERR_ABORTED" not in str(e):
                            raise
            dl = await info.value
        except FetchError:
            raise
        except Exception as e:
            raise FetchError(f"The browser did not download the file ({str(e).splitlines()[0]}).")
        finally:
            if not same_site:
                await page.close()
        if failure := await dl.failure():
            raise FetchError(f"The browser could not download the file ({failure}).")
        part = dest.with_name(dest.name + ".part")
        try:
            await dl.save_as(part)
            with open(part, "rb") as f:
                head = f.read(4096)
            if not head:
                raise FetchError("The server sent an empty file.")
            webfetch._check_start(head, item["suffix"])
            part.replace(dest)
        finally:
            part.unlink(missing_ok=True)
            try:
                await dl.delete()            # the browser's own temporary copy
            except Exception:
                pass
        return {"status": "saved", "path": str(dest)}
