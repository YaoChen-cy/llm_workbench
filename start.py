"""
Start LLM Workbench (Windows, macOS, Linux):

    python start.py            Windows: py start.py   (or double-click if .py opens with Python)

First run creates a .venv folder and installs requirements.txt with pip (exact versions from constraints.txt).
Behind a company proxy or mirror, pip's usual settings apply (HTTPS_PROXY, PIP_INDEX_URL, or a pip.ini / pip.conf).
Settings for the company LLM can go in env.txt (copy env.example.txt) or be entered in the app.

Options:  --port 8000   --no-browser   --reinstall
"""
import argparse
import os
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
REQS = ROOT / "requirements.txt"
CONSTRAINTS = ROOT / "constraints.txt"           # exact versions of all dependencies
STAMP = VENV / "requirements.installed.txt"      # copy of requirements + constraints from the last successful install


def ensure_env(reinstall: bool):
    if sys.version_info < (3, 11):
        sys.exit(f"Python 3.11 or newer is required (this is {sys.version.split()[0]}).")
    if not PY.exists():
        print("Creating the Python environment in .venv ...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    wanted = REQS.read_text("utf-8") + CONSTRAINTS.read_text("utf-8")
    if reinstall or not STAMP.exists() or STAMP.read_text("utf-8") != wanted:
        print("Installing dependencies (first run only, a few minutes) ...")
        cmd = [str(PY), "-m", "pip", "install", "--only-binary=pymupdf", "-r", str(REQS), "-c", str(CONSTRAINTS)]
        if subprocess.call(cmd) != 0:
            sys.exit("\npip install failed. If you are behind a proxy, set HTTPS_PROXY or PIP_INDEX_URL and run again.")
        STAMP.write_text(wanted, "utf-8")


def load_env_file():
    """KEY=VALUE lines from env.txt or .env (existing environment variables win)."""
    for name in ("env.txt", ".env"):
        f = ROOT / name
        if not f.exists():
            continue
        for line in f.read_text("utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if value.strip():
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def open_browser_when_ready(url: str):
    for _ in range(120):
        try:
            urllib.request.urlopen(url + "/api/projects", timeout=1)
            webbrowser.open(url)
            return
        except Exception:
            time.sleep(1)


def main():
    ap = argparse.ArgumentParser(description="Start LLM Workbench")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--reinstall", action="store_true", help="reinstall dependencies")
    args = ap.parse_args()

    ensure_env(args.reinstall)
    load_env_file()
    url = f"http://localhost:{args.port}"
    if not args.no_browser:
        threading.Thread(target=open_browser_when_ready, args=(url,), daemon=True).start()
    print(f"\nLLM Workbench: {url}   (press Ctrl+C to stop)\n")
    try:
        sys.exit(subprocess.call([str(PY), "-m", "uvicorn", "backend.app:app", "--port", str(args.port)], cwd=ROOT))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
