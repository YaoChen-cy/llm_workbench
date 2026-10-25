"""
FastAPI server.  Run from the repo root:

    python start.py                 (or: .venv/bin/uvicorn backend.app:app --port 8000)

Serves the REST API under /api and the NiceGUI user interface (backend/ui.py) at /.
"""
import json
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from . import chats, documents, llm, projects, settings
from . import files as fs

app = FastAPI(title="LLM Workbench")


def _err(e: Exception):
    if isinstance(e, fs.AccessDenied):
        raise HTTPException(403, str(e))
    if isinstance(e, FileExistsError):
        raise HTTPException(409, f"{e} already exists")
    if isinstance(e, FileNotFoundError):
        raise HTTPException(404, str(e) or "not found")
    if isinstance(e, ValueError):
        raise HTTPException(400, str(e))
    raise e


# ---------------------------------------------------------------- settings / models

@app.get("/api/settings")
def get_settings():
    return settings.public(settings.load())


@app.put("/api/settings")
def put_settings(body: dict):
    return settings.public(settings.update(body))


@app.get("/api/models")
async def models(provider: str | None = None):
    try:
        return {"models": await llm.list_models(settings.provider(provider))}
    except llm.LLMError as e:
        raise HTTPException(502, str(e))


@app.post("/api/settings/test")
async def test_provider(provider: str | None = None):
    p = settings.provider(provider)
    t0 = time.time()
    try:
        reply = await llm.complete([{"role": "user", "content": "Reply with exactly: OK"}],
                                   {**p, "context_tokens": 512})
        return {"ok": True, "reply": reply.strip()[:200], "seconds": round(time.time() - t0, 1), "model": p["model"]}
    except llm.LLMError as e:
        return {"ok": False, "error": str(e), "seconds": round(time.time() - t0, 1)}


# ---------------------------------------------------------------- files / documents

@app.get("/api/fs/roots")
def fs_roots():
    return fs.roots()


def _roots(project_id: str | None):
    """Folders readable in this context: the project folder, or the global allowed folders."""
    return [projects.get(project_id)["folder"]] if project_id else None


@app.get("/api/fs/list")
def fs_list(path: str, project_id: str | None = None):
    try:
        return fs.list_dir(path, _roots(project_id))
    except Exception as e:
        _err(e)


@app.get("/api/fs/dirs")
def fs_dirs(path: str | None = None):
    try:
        return fs.list_dirs(path)
    except Exception as e:
        _err(e)


class IngestReq(BaseModel):
    paths: list[str]
    project_id: str | None = None


@app.post("/api/documents")
def ingest(req: IngestReq):
    out = []
    roots = _roots(req.project_id)
    for path in req.paths:
        try:
            p = fs.check(path, roots)
            out.append({"ok": True, **documents.meta(documents.ingest(p))})
        except Exception as e:
            out.append({"ok": False, "name": Path(path).name, "error": str(e)})
    return out


@app.post("/api/upload")
async def upload(files: list[UploadFile]):
    out = []
    for f in files:
        name = Path(f.filename or "upload").name
        if Path(name).suffix.lower() not in fs.SUPPORTED:
            out.append({"ok": False, "name": name, "error": "unsupported file type"})
            continue
        safe = re.sub(r"[^\w.\- ]", "_", name)
        dest = settings.UPLOADS_DIR / f"{uuid.uuid4().hex[:8]}_{safe}"
        dest.write_bytes(await f.read())
        try:
            out.append({"ok": True, **documents.meta(documents.ingest(dest, name=name)), "name": name})
        except Exception as e:
            out.append({"ok": False, "name": name, "error": str(e)})
    return out


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    try:
        return documents.get(doc_id)
    except Exception as e:
        _err(e)


@app.get("/api/documents/{doc_id}/locate")
def locate_citation(doc_id: str, block: str, claim: str = ""):
    try:
        return documents.locate(doc_id, block, claim[:1000])
    except Exception as e:
        _err(e)


@app.get("/api/documents/{doc_id}/page/{page}.png")
def page_image(doc_id: str, page: int, zoom: float = 1.5, block: str = "", claim: str = ""):
    try:
        png = documents.render_page(doc_id, page, max(0.5, min(zoom, 4.0)), block, claim[:1000])
        return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
    except Exception as e:
        _err(e)


@app.get("/api/documents/{doc_id}/file")
def get_document_file(doc_id: str):
    try:
        return FileResponse(documents.get(doc_id)["source_path"])
    except Exception as e:
        _err(e)


# ---------------------------------------------------------------- projects

class ProjectReq(BaseModel):
    name: str = ""
    folder: str
    instructions: str = ""
    create_folder: bool = False


class ProjectPatch(BaseModel):
    name: str | None = None
    instructions: str | None = None


class TextReq(BaseModel):
    title: str = ""
    text: str


class OutputReq(BaseModel):
    name: str
    content: str
    overwrite: bool = False


@app.get("/api/projects")
def list_projects():
    return projects.list_all()


@app.post("/api/projects")
def create_project(req: ProjectReq):
    try:
        return projects.create(req.name, req.folder, req.instructions, req.create_folder)
    except Exception as e:
        _err(e)


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    try:
        return projects.get(pid)
    except Exception as e:
        _err(e)


@app.patch("/api/projects/{pid}")
def patch_project(pid: str, body: ProjectPatch):
    try:
        return projects.update(pid, body.name, body.instructions)
    except Exception as e:
        _err(e)


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    chats.delete_project_chats(pid)
    projects.forget(pid)
    return {"ok": True}


@app.post("/api/projects/{pid}/context/paths")
def add_context_paths(pid: str, req: IngestReq):
    try:
        return projects.add_paths(pid, req.paths)
    except Exception as e:
        _err(e)


@app.post("/api/projects/{pid}/context/upload")
async def add_context_upload(pid: str, files: list[UploadFile]):
    try:
        return [projects.add_upload(pid, f.filename or "upload", await f.read()) for f in files]
    except Exception as e:
        _err(e)


@app.post("/api/projects/{pid}/context/text")
def add_context_text(pid: str, req: TextReq):
    try:
        return projects.add_text(pid, req.title, req.text)
    except Exception as e:
        _err(e)


@app.delete("/api/projects/{pid}/context/{doc_id}")
def remove_context(pid: str, doc_id: str):
    try:
        return projects.remove_context(pid, doc_id)
    except Exception as e:
        _err(e)


@app.post("/api/projects/{pid}/files")
def write_project_file(pid: str, req: OutputReq):
    try:
        return {"ok": True, "path": projects.write_output(pid, req.name, req.content, req.overwrite)}
    except Exception as e:
        _err(e)


# ---------------------------------------------------------------- chats

class NewChatReq(BaseModel):
    project_id: str | None = None


@app.get("/api/chats")
def list_chats(project_id: str | None = None):
    return chats.list_all(project_id)


@app.post("/api/chats")
def new_chat(req: NewChatReq | None = None):
    pid = req.project_id if req else None
    if pid:
        try:
            projects.get(pid)
        except Exception as e:
            _err(e)
    return chats.create(pid)


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str):
    try:
        return chats.get(chat_id)
    except Exception as e:
        _err(e)


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str):
    chats.delete(chat_id)
    return {"ok": True}


class ChatPatch(BaseModel):
    title: str | None = None
    attach: list[str] = []
    detach: list[str] = []


@app.patch("/api/chats/{chat_id}")
def patch_chat(chat_id: str, body: ChatPatch):
    try:
        chat = chats.get(chat_id)
        if body.title is not None:
            chat["title"] = body.title.strip()[:80] or chat["title"]
        chats.attach(chat, body.attach)
        for d in body.detach:
            chats.detach(chat, d)
        chats.save(chat)
        return chat
    except Exception as e:
        _err(e)


class MessageReq(BaseModel):
    content: str
    provider: str | None = None


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chats/{chat_id}/messages")
async def send_message(chat_id: str, req: MessageReq):
    try:
        chat = chats.get(chat_id)
    except Exception as e:
        _err(e)
    p = settings.provider(req.provider)
    project = None
    if chat.get("project_id"):
        try:
            project = projects.get(chat["project_id"])
        except Exception as e:
            _err(e)
    messages, info = chats.build_messages(chat, req.content, p.get("context_tokens", 8192), project)
    user_msg = {"role": "user", "content": req.content, "created": time.time()}
    chat["messages"].append(user_msg)
    if chat["title"] == "New chat":
        chat["title"] = re.sub(r"\s+", " ", req.content).strip()[:60] or "New chat"
    chats.save(chat)

    async def gen():
        parts, error = [], None
        yield _sse("info", {**info, "model": p["model"]})
        try:
            async for chunk in llm.stream_chat(messages, p):
                parts.append(chunk)
                yield _sse("token", {"t": chunk})
        except llm.LLMError as e:
            error = str(e)
            yield _sse("error", {"message": error})
        finally:
            # Also runs when the browser aborts (Stop button): keep what was generated.
            if parts or error:
                msg = {"role": "assistant", "content": "".join(parts), "created": time.time(),
                       "model": p["model"], "context": info}
                if error:
                    msg["error"] = error
                fresh = chats.get(chat_id)
                fresh["messages"].append(msg)
                chats.save(fresh)
        yield _sse("done", {})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- user interface (NiceGUI, pure Python)

from . import ui  # noqa: E402  (registers the pages and mounts NiceGUI on this app)

ui.attach(app)
