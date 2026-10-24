"""
Two checks per summary point:
  1. number_check (deterministic): every number in the point must appear in its cited paragraphs.
  2. llm_check: a second LLM call judges whether the cited paragraphs support the point.
Results are written onto each point as point["checks"].
"""
import json
import re

import config
from llm_client import call_llm, parse_json

_SCALE = {"bn": 1e9, "billion": 1e9, "mm": 1e6, "m": 1e6, "million": 1e6, "k": 1e3, "": 1}
_NUM = re.compile(
    r"(?<![\w.])(?P<cur>\$)?(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<dec>\.\d+)?"
    r"(?:\s?(?P<unit>%|x\b|bn\b|billion\b|mm\b|million\b|m\b|k\b))?"
    r"(?![\w%])",
    re.I,
)


def extract_numbers(text):
    """-> list of dicts {raw, kind: pct|mult|money|plain, value, decimals}"""
    out = []
    for m in _NUM.finditer(text.replace("**", "")):
        unit = (m.group("unit") or "").lower()
        num = float(m.group("num").replace(",", "") + (m.group("dec") or ""))
        dec = len(m.group("dec") or "") - 1 if m.group("dec") else 0
        if unit == "%":
            kind, scale = "pct", 1
        elif unit == "x":
            kind, scale = "mult", 1
        elif m.group("cur") or unit in _SCALE and unit:
            kind, scale = "money", _SCALE.get(unit, 1)
        else:
            kind, scale = "plain", 1
        out.append({"raw": m.group(0).strip(), "kind": kind, "value": num * scale,
                    "num": num, "scale": scale, "decimals": max(dec, 0)})
    return out


def _matches(s, src):
    if s["kind"] != src["kind"] and "plain" not in (s["kind"], src["kind"]):
        return False
    if s["kind"] == "plain" or src["kind"] == "plain":
        return abs(s["num"] - src["num"]) < 1e-9
    # Same kind: compare in the summary's unit, rounded to the summary's precision ($1.4bn ~ $1.42bn).
    src_in_s_unit = src["value"] / s["scale"]
    return round(src_in_s_unit, s["decimals"]) == round(s["num"], s["decimals"])


def number_check(point, by_id):
    cited_text = " ".join(by_id[c].text for c in point["cites"] if c in by_id)
    src_nums = extract_numbers(cited_text)
    missing = [n["raw"] for n in extract_numbers(point["text"])
               if not any(_matches(n, s) for s in src_nums)]
    return missing


def llm_check(summary, by_id):
    items = []
    for part in ("situation_recap", "recent_development"):
        for p in summary.get(part, []):
            cited = "\n".join(f"[{c}] {by_id[c].text}" for c in p["cites"] if c in by_id)
            items.append(f"### {p['id']}\nPOINT: {p['text']}\nCITED PARAGRAPHS:\n{cited}")
    system = (config.PROMPT_DIR / "verify.md").read_text(encoding="utf-8")
    raw = call_llm(system, "\n\n".join(items), task="verify")
    try:
        return {r["point_id"]: r for r in parse_json(raw)}
    except Exception as e:
        return {"_error": {"verdict": "error", "issue": f"verifier output unreadable: {e}"}}


def verify(summary, parsed):
    by_id = parsed.by_id()
    llm = llm_check(summary, by_id)
    for part in ("situation_recap", "recent_development"):
        for p in summary.get(part, []):
            missing = number_check(p, by_id)
            v = llm.get(p["id"], llm.get("_error", {"verdict": "not_checked", "issue": ""}))
            p["checks"] = {
                "numbers_not_found": missing,
                "llm_verdict": v.get("verdict", ""),
                "llm_issue": v.get("issue", ""),
            }
            p["flagged"] = bool(missing) or v.get("verdict") != "supported"
    return summary


if __name__ == "__main__":
    print(json.dumps(extract_numbers("increased from $18.0mm to **$29.3mm** (65%), 19.3x, $1.42bn, 1st Lien, Q1 2027"), indent=1))
