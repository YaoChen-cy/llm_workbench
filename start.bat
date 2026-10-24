@echo off
rem Build the frontend if needed, then serve everything at http://localhost:8000  (Windows)
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\pip install -q --only-binary=pymupdf -r requirements.txt
)
if not exist frontend\dist (
  pushd frontend
  if not exist node_modules call npm install --no-audit --no-fund
  call npm run build
  popd
)
if exist .env for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
echo Open http://localhost:8000
.venv\Scripts\uvicorn backend.app:app --port 8000
