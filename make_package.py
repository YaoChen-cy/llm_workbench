"""
Build a zip to copy the app to another computer:  python make_package.py

Contains the files tracked by git, limited to types that pass strict email filters
(.py .txt .md .pdf .json .docx .xlsx). No .venv, data/, or credentials are included.
"""
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALLOWED = {".py", ".txt", ".md", ".pdf", ".json", ".docx", ".xlsx"}


def main():
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    files = [f for f in files if f and (ROOT / f).is_file()]
    keep = [f for f in files if Path(f).suffix.lower() in ALLOWED]
    skipped = sorted(set(files) - set(keep))
    out = ROOT / f"llm-workbench-{time.strftime('%Y-%m-%d')}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in keep:
            z.write(ROOT / f, f"llm-workbench/{f}")
    print(f"{out.name}: {len(keep)} files, {out.stat().st_size / 1024:.0f} KB")
    if skipped:
        print("Left out (file type not allowed):", ", ".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
