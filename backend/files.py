"""Read-only browsing, limited to the allowed folders (or, inside a project, to its folder)."""
from pathlib import Path

from . import settings

SUPPORTED = {".pdf", ".docx", ".txt", ".md"}


class AccessDenied(Exception):
    pass


def roots() -> list[dict]:
    out = []
    for f in settings.load()["allowed_folders"]:
        p = Path(f)
        out.append({"path": str(p), "name": p.name or str(p), "exists": p.is_dir()})
    return out


def _root_of(p: Path, roots: list[str]) -> Path | None:
    for r in roots:
        root = Path(r).resolve()
        if p == root or root in p.parents:
            return root
    return None


def check(path: str, roots: list[str] | None = None) -> Path:
    """Resolve `path` and make sure it lies inside one of `roots` (default: allowed folders)."""
    p = Path(path).expanduser().resolve()
    if _root_of(p, roots if roots is not None else settings.load()["allowed_folders"]) is None:
        where = "the project folder" if roots is not None else "the allowed folders (Settings → Folders)"
        raise AccessDenied(f"{p} is outside {where}.")
    return p


def list_dir(path: str, roots: list[str] | None = None) -> dict:
    roots = roots if roots is not None else settings.load()["allowed_folders"]
    p = check(path, roots)
    if not p.is_dir():
        raise FileNotFoundError(str(p))
    entries = []
    for e in p.iterdir():
        if e.name.startswith((".", "~$")):
            continue
        is_dir = e.is_dir()
        entries.append({
            "name": e.name, "path": str(e), "is_dir": is_dir,
            "size": None if is_dir else e.stat().st_size,
            "supported": is_dir or e.suffix.lower() in SUPPORTED,
        })
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    root = _root_of(p, roots)
    return {"path": str(p), "root": str(root), "parent": None if p == root else str(p.parent), "entries": entries}


def list_dirs(path: str | None) -> dict:
    """Subfolders and files of `path` (default: home), for the project folder picker.
    Names, types and sizes only, never file contents."""
    p = Path(path).expanduser().resolve() if path else Path.home()
    if not p.is_dir():
        raise FileNotFoundError(str(p))
    dirs, file_list = [], []
    try:
        for e in p.iterdir():
            if e.name.startswith((".", "$", "~")):
                continue
            try:
                if e.is_dir():
                    dirs.append({"name": e.name, "path": str(e),
                                 "is_project": (e / ".workbench" / "project.json").exists()})
                elif e.is_file():
                    file_list.append({"name": e.name, "size": e.stat().st_size,
                                      "supported": e.suffix.lower() in SUPPORTED})
            except OSError:
                continue
    except PermissionError:
        pass
    dirs.sort(key=lambda d: d["name"].lower())
    file_list.sort(key=lambda f: f["name"].lower())
    return {"path": str(p), "parent": None if p.parent == p else str(p.parent), "home": str(Path.home()),
            "is_project": (p / ".workbench" / "project.json").exists(), "dirs": dirs, "files": file_list}
