"""Read-only browsing, limited to the allowed folders (or, inside a project, to its folder)."""
import os
import string
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


LOCATIONS = "::locations::"      # pseudo-path for the list of drives and common folders


def _abs(path: str) -> Path:
    """Absolute path without resolving links: mapped network drives keep their letter on Windows."""
    return Path(os.path.abspath(os.path.expanduser(path.strip().strip('"'))))


def locations() -> list[dict]:
    """Drives (including mapped network drives), mounted volumes and common user folders."""
    out, seen = [], set()

    def add(path, label, kind):
        try:
            p = Path(path)
            if str(p) not in seen and p.is_dir():
                seen.add(str(p))
                out.append({"name": label, "path": str(p), "kind": kind})
        except OSError:
            pass

    home = Path.home()
    add(home, f"Home ({home.name})", "home")
    for sub in ("Desktop", "Documents", "Downloads"):
        add(home / sub, sub, "folder")
    if os.name == "nt":
        for var in ("OneDriveCommercial", "OneDrive"):            # OneDrive / SharePoint sync folders
            if os.environ.get(var):
                add(os.environ[var], Path(os.environ[var]).name, "cloud")
        for entry in home.iterdir() if home.is_dir() else []:
            if entry.name.startswith("OneDrive"):
                add(entry, entry.name, "cloud")
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if os.path.exists(root):
                kind = "network" if _drive_type(root) == 4 else "drive"
                add(root, f"{letter}: {'(network drive)' if kind == 'network' else ''}".strip(), kind)
    else:
        add("/", "Computer (/)", "drive")
        for base in ("/Volumes", "/mnt", "/media"):
            try:
                for v in sorted(Path(base).iterdir()):
                    add(v, v.name, "drive")
            except OSError:
                pass
    return out


def _drive_type(root: str) -> int:
    """Windows drive type (4 = network drive); 0 elsewhere."""
    try:
        import ctypes
        return ctypes.windll.kernel32.GetDriveTypeW(root)
    except Exception:
        return 0


def list_dirs(path: str | None) -> dict:
    """Subfolders and files of `path` for the project folder picker (names, types and sizes only,
    never file contents). path=None or LOCATIONS lists drives and common folders instead."""
    common = {"home": str(Path.home()), "locations": LOCATIONS}
    if not path or path == LOCATIONS:
        return {**common, "path": LOCATIONS, "parent": None, "is_project": False, "dirs": [
            {"name": loc["name"], "path": loc["path"], "is_project": False, "kind": loc["kind"]} for loc in locations()
        ], "files": []}
    p = _abs(path)
    try:
        if not p.is_dir():
            raise FileNotFoundError(f"Folder not found or not reachable: {p}")
        entries = list(p.iterdir())
    except PermissionError:
        raise AccessDenied(f"No permission to open {p}. Check that you can open it in File Explorer / Finder.")
    except OSError as e:
        if isinstance(e, FileNotFoundError):
            raise
        raise FileNotFoundError(f"Cannot open {p}: {e.strerror or e}")
    dirs, file_list = [], []
    for e in entries:
        if e.name.startswith((".", "$", "~")):
            continue
        try:
            if e.is_dir():
                dirs.append({"name": e.name, "path": str(e), "is_project": None})
            elif e.is_file():
                file_list.append({"name": e.name, "size": e.stat().st_size,
                                  "supported": e.suffix.lower() in SUPPORTED})
        except OSError:
            continue
    # Checking for .workbench in every subfolder is slow on network shares; only do it for small folders.
    if len(dirs) <= 200:
        for d in dirs:
            try:
                d["is_project"] = (Path(d["path"]) / ".workbench" / "project.json").exists()
            except OSError:
                d["is_project"] = False
    dirs.sort(key=lambda d: d["name"].lower())
    file_list.sort(key=lambda f: f["name"].lower())
    parent = str(p.parent) if p.parent != p else LOCATIONS      # from a drive / share root, go up to Locations
    try:
        is_project = (p / ".workbench" / "project.json").exists()
    except OSError:
        is_project = False
    return {**common, "path": str(p), "parent": parent, "is_project": is_project, "dirs": dirs, "files": file_list}
