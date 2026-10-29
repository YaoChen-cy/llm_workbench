"""
Projects: a named task with instructions, context documents and a working folder.

Project data lives inside its folder so the folder is self-contained and can be copied or shared.
Several projects can use the same folder; each has its own directory:
    <folder>/.workbench/projects/<id>/project.json
    <folder>/.workbench/projects/<id>/context/      uploaded and pasted context files
    <folder>/.workbench/projects/<id>/knowledge/    examples and summary profile (knowledge.py)
Projects made by earlier versions keep the single-project layout <folder>/.workbench/project.json (+ context/,
knowledge/) and keep working. data/projects.json maps project ids to folders. Creating a project in a folder that
has an unregistered project of the same name (a copied or shared folder) re-registers that project instead.

Inside a project, documents can only be read from <folder> and outputs are only written to <folder>.
"""
import json
import os
import re
import time
import uuid
from pathlib import Path

from . import documents, outputs
from . import files as fs
from .settings import DATA_DIR

REGISTRY = DATA_DIR / "projects.json"
META = ".workbench"


def _registry() -> dict:
    return json.loads(REGISTRY.read_text("utf-8")) if REGISTRY.exists() else {}


def _save_registry(r: dict):
    REGISTRY.write_text(json.dumps(r, indent=1), "utf-8")


def _read(f: Path) -> dict:
    return json.loads(f.read_text("utf-8"))


def meta_dir(folder, pid: str) -> Path:
    """The directory holding project pid's data inside its folder."""
    folder = Path(folder)
    legacy = folder / META / "project.json"
    try:
        if legacy.exists() and _read(legacy).get("id") == pid:
            return folder / META
    except (OSError, ValueError):
        pass
    return folder / META / "projects" / pid


def _meta_file(folder, pid: str) -> Path:
    return meta_dir(folder, pid) / "project.json"


def folder_projects(folder) -> list[dict]:
    """The projects saved in a folder (registered or not)."""
    folder = Path(folder)
    files = [folder / META / "project.json"] + sorted((folder / META / "projects").glob("*/project.json"))
    out = []
    for f in files:
        try:
            if f.exists():
                out.append(_read(f))
        except (OSError, ValueError):
            continue
    return out


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.\- ]", "_", Path(name).name).strip() or "file"


def save(p: dict):
    p["updated"] = time.time()
    folder = Path(p["folder"])
    data = {k: v for k, v in p.items() if k not in ("folder", "shares_folder_with", "reopened")}  # folder may move
    meta = _meta_file(folder, p["id"])
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def create(name: str, folder: str, instructions: str = "", create_folder: bool = False) -> dict:
    f = Path(folder.strip().strip('"')).expanduser()
    if not f.is_absolute():
        raise ValueError("Folder must be an absolute path, e.g. /Users/you/Documents/memos, C:\\Work\\memos "
                         "or \\\\server\\share\\team")
    f = Path(os.path.abspath(f))
    if f == Path(f.anchor) or f == Path.home():
        raise ValueError("Pick a dedicated folder inside the drive or share, not its root or your home folder.")
    if not f.exists():
        if not create_folder:
            raise ValueError(f"Folder does not exist: {f}")
        f.mkdir(parents=True)
    if not f.is_dir():
        raise ValueError(f"Not a folder: {f}")

    reg = _registry()
    name = name.strip() or f.name
    here = folder_projects(f)
    for old in here:                              # a copied/shared project folder: reopen that project
        if old["id"] not in reg and old["name"].strip().lower() == name.lower():
            reg[old["id"]] = str(f)
            _save_registry(reg)
            return {**old, "folder": str(f), "reopened": True}

    now = time.time()
    p = {"id": uuid.uuid4().hex[:12], "name": name, "instructions": instructions,
         "created": now, "updated": now, "context": [], "next_label": 1, "folder": str(f),
         "shares_folder_with": [o["name"] for o in here]}
    save(p)
    (meta_dir(f, p["id"]) / "context").mkdir(parents=True, exist_ok=True)
    reg[p["id"]] = str(f)
    _save_registry(reg)
    return p


def get(pid: str) -> dict:
    folder = _registry().get(pid)
    if not folder:
        raise FileNotFoundError(f"unknown project {pid}")
    f = Path(folder)
    if not _meta_file(f, pid).exists():
        raise FileNotFoundError(f"Project folder is missing or was moved: {f}")
    p = _read(_meta_file(f, pid))
    p.pop("shares_folder_with", None)
    p["folder"] = str(f)
    for c in p["context"]:                       # re-parse if the doc cache was cleared
        if not (documents.DOCS_DIR / c["doc_id"] / "doc.json").exists() and Path(c["path"]).exists():
            documents.ingest(Path(c["path"]), name=c["name"])
    return p


def list_all() -> list[dict]:
    out = []
    for pid, folder in _registry().items():
        try:
            p = get(pid)
            out.append({"id": pid, "name": p["name"], "folder": folder, "updated": p["updated"],
                        "n_context": len(p["context"]), "missing": False})
        except FileNotFoundError:
            out.append({"id": pid, "name": Path(folder).name, "folder": folder, "updated": 0,
                        "n_context": 0, "missing": True})
    return sorted(out, key=lambda p: -p["updated"])


def update(pid: str, name: str | None = None, instructions: str | None = None) -> dict:
    p = get(pid)
    if name is not None and name.strip():
        p["name"] = name.strip()[:80]
    if instructions is not None:
        p["instructions"] = instructions
    save(p)
    return p


def forget(pid: str):
    """Remove the project from the app. Its folder, including .workbench/, is left untouched."""
    reg = _registry()
    reg.pop(pid, None)
    _save_registry(reg)


# ---------------------------------------------------------------- context

def _add(p: dict, path: Path, name: str, source: str) -> dict:
    doc = documents.ingest(path, name=name)
    # The parse cache is keyed by content, so report the name this file was added under.
    m = {**documents.meta(doc), "name": name}
    if any(c["doc_id"] == doc["id"] for c in p["context"]):
        return {"ok": True, "duplicate": True, **m}
    p["context"].append({"doc_id": doc["id"], "label": f"C{p['next_label']}", "name": name,
                         "source": source, "path": str(path)})
    p["next_label"] += 1
    return {"ok": True, **m}


def _context_dest(p: dict, name: str) -> Path:
    d = meta_dir(p["folder"], p["id"]) / "context"
    d.mkdir(parents=True, exist_ok=True)
    dest, stem, n = d / name, Path(name).stem, 2
    while dest.exists():
        dest = d / f"{stem} ({n}){Path(name).suffix}"
        n += 1
    return dest


def add_paths(pid: str, paths: list[str]) -> list[dict]:
    p = get(pid)
    out = []
    for path in paths:
        try:
            f = fs.check(path, [p["folder"]])
            out.append(_add(p, f, f.name, "folder"))
        except Exception as e:
            out.append({"ok": False, "name": Path(path).name, "error": str(e)})
    save(p)
    return out


def add_upload(pid: str, name: str, data: bytes) -> dict:
    p = get(pid)
    name = _safe_name(name)
    if Path(name).suffix.lower() not in fs.SUPPORTED:
        return {"ok": False, "name": name, "error": "unsupported file type"}
    dest = _context_dest(p, name)
    dest.write_bytes(data)
    try:
        r = _add(p, dest, name, "upload")
    except Exception as e:
        dest.unlink(missing_ok=True)
        return {"ok": False, "name": name, "error": str(e)}
    if r.get("duplicate"):
        dest.unlink(missing_ok=True)       # same content is already in context; don't keep a second copy
    save(p)
    return r


def add_text(pid: str, title: str, text: str) -> dict:
    p = get(pid)
    if not text.strip():
        raise ValueError("Text is empty")
    name = _safe_name((title.strip() or "Pasted text")[:60]) + ".md"
    dest = _context_dest(p, name)
    dest.write_text(text, "utf-8")
    r = _add(p, dest, name, "text")
    save(p)
    return r


def remove_context(pid: str, doc_id: str) -> dict:
    p = get(pid)
    for c in [c for c in p["context"] if c["doc_id"] == doc_id]:
        p["context"].remove(c)
        # Files the app copied into .workbench/context are removed; files in the project folder are not.
        if c["source"] in ("upload", "text"):
            Path(c["path"]).unlink(missing_ok=True)
    save(p)
    return p


# ---------------------------------------------------------------- outputs

def write_output(pid: str, name: str, content: str, overwrite: bool = False) -> str:
    """Write an output file inside the project folder (subfolders allowed, .workbench is not).
    .docx files are converted from Markdown; other supported types are written as text."""
    p = get(pid)
    folder = Path(p["folder"]).resolve()
    rel = Path(outputs.clean_path(name))
    dest = (folder / rel).resolve()
    if folder not in dest.parents or META in dest.relative_to(folder).parts:
        raise fs.AccessDenied(f"{name} is outside the project folder.")
    if dest.exists() and not overwrite:
        raise FileExistsError(str(dest.relative_to(folder)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(outputs.to_bytes(str(rel), content))
    return str(dest)
