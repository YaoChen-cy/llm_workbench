"""
App settings, stored in data/settings.json (git-ignored, may contain API keys).

Environment variables override the "company" provider so keys never need to be typed into the UI:
    LLM_BASE_URL, LLM_API_KEY, LLM_MODEL   -> providers.company
    LLM_PROVIDER                           -> active_provider ("ollama" | "company")
"""
import copy
import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("WORKBENCH_DATA", ROOT / "data"))
DOCS_DIR = DATA_DIR / "docs"
CHATS_DIR = DATA_DIR / "chats"
UPLOADS_DIR = DATA_DIR / "uploads"
SETTINGS_FILE = DATA_DIR / "settings.json"
for d in (DOCS_DIR, CHATS_DIR, UPLOADS_DIR):
    d.mkdir(parents=True, exist_ok=True)

DEFAULTS = {
    "active_provider": "ollama",
    "providers": {
        "ollama": {
            "label": "Local Ollama",
            "type": "ollama",                    # native /api/chat (lets us set num_ctx)
            "base_url": "http://localhost:11434",
            "model": "llama3.2",
            "api_key": "",
            "extra_headers": {},
            "verify_ssl": True,
            "bypass_proxy": True,
            "context_tokens": 16384,
            "temperature": 0.1,
        },
        "company": {
            "label": "Company API",
            "type": "openai",                    # OpenAI-compatible /chat/completions
            "base_url": "",
            "model": "gemma-4-31b-it",
            "api_key": "",
            "extra_headers": {"x-goog-api-key": "{api_key}"},   # {api_key} is substituted
            "verify_ssl": False,
            "bypass_proxy": True,
            "context_tokens": 32000,
            "temperature": 0.1,
        },
    },
    # Folders the file browser may read. Everything outside them is refused.
    "allowed_folders": [],
}

_lock = threading.Lock()


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load() -> dict:
    with _lock:
        saved = json.loads(SETTINGS_FILE.read_text("utf-8")) if SETTINGS_FILE.exists() else {}
    s = _merge(DEFAULTS, saved)
    co = s["providers"]["company"]
    for env, key in (("LLM_BASE_URL", "base_url"), ("LLM_API_KEY", "api_key"), ("LLM_MODEL", "model")):
        if os.getenv(env):
            co[key] = os.environ[env]
    if os.getenv("LLM_PROVIDER") in s["providers"]:
        s["active_provider"] = os.environ["LLM_PROVIDER"]
    return s


def save(s: dict):
    with _lock:
        SETTINGS_FILE.write_text(json.dumps(s, indent=2), "utf-8")


def public(s: dict) -> dict:
    """Settings as sent to the browser: API keys replaced by a has_api_key flag."""
    out = copy.deepcopy(s)
    for p in out["providers"].values():
        p["has_api_key"] = bool(p.pop("api_key", ""))
    return out


def update(incoming: dict) -> dict:
    """Apply a settings update from the browser. An empty api_key keeps the stored one."""
    s = load()
    for name, p in incoming.get("providers", {}).items():
        cur = s["providers"].setdefault(name, copy.deepcopy(DEFAULTS["providers"]["company"]))
        key = p.pop("api_key", "")
        if p.pop("clear_api_key", False):
            cur["api_key"] = ""
        elif key:
            cur["api_key"] = key
        p.pop("has_api_key", None)
        cur.update(p)
    if incoming.get("active_provider") in s["providers"]:
        s["active_provider"] = incoming["active_provider"]
    if "allowed_folders" in incoming:
        s["allowed_folders"] = [str(Path(f).expanduser().resolve()) for f in incoming["allowed_folders"] if f.strip()]
    save(s)
    return s


def provider(name: str | None = None) -> dict:
    s = load()
    return s["providers"][name or s["active_provider"]]
