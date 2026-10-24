"""All tunable settings live here."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
PROMPT_DIR = ROOT / "prompts"
EXAMPLES_DIR = PROMPT_DIR / "examples"
EVAL_DIR = ROOT / "eval"

# ---------------------------------------------------------------- LLM
# LLM_MODE=mock runs the whole pipeline with canned responses (no API needed).
LLM_MODE = os.getenv("LLM_MODE", "api")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://your-internal-llm-gateway/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "your-model-name")
LLM_TEMPERATURE = 0.0
LLM_TIMEOUT = 180
LLM_MAX_RETRIES = 2
MAX_WORKERS = 5          # companies processed in parallel

# ---------------------------------------------------------------- Parsing
# Main sections in document order. `code` is used in paragraph IDs, e.g. [RR-3].
# `patterns` are case-insensitive regexes matched against bold heading lines.
SECTIONS = [
    {"code": "OV", "title": "Company Overview",
     "patterns": [r"^company overview"]},
    {"code": "RR", "title": "Reason for Rating",
     "patterns": [r"^reason[s]? for (the )?rating", r"^rating rationale"]},
    {"code": "TU", "title": "Transactional Updates",
     "patterns": [r"^transaction(al)? updates?", r"^recent (developments|updates)"]},
    {"code": "PR", "title": "Provision Rationale & Accounting Impact",
     "patterns": [r"^provision(ing)? rationale", r"^accounting impact"]},
    {"code": "OL", "title": "Outlook and Action Plan",
     "patterns": [r"^outlook", r"^action plan"]},
]
# Parsing stops at the first heading/line matching any of these.
END_PATTERNS = [r"^sign[- ]?off", r"^approvals?$", r"^account officer\b"]

# Lines in the top/bottom margin (fraction of page height) are treated as header/footer.
HEADER_FOOTER_MARGIN = 0.06
# Company name from the header block (falls back to the PDF file name).
COMPANY_NAME_REGEX = r"Borrower\s*:?\s*(.+?)(?=\s+(?:Memo Date|Industry|Risk Rating)\b|\s{2,}|$)"
# A bold line shorter than this (chars) and not ending in '.' is treated as a heading.
MAX_HEADING_CHARS = 90

# ---------------------------------------------------------------- Output
# Number of bullet points requested per output section.
POINTS_PER_SECTION = "2-4"
HIGHLIGHT_FLAGS_IN_WORD = True     # yellow highlight on points that failed a check
WRITE_HIGHLIGHTED_PDF = True       # copy of the source PDF with cited paragraphs highlighted
