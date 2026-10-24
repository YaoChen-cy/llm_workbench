"""Build the prompt (system + style guide + few-shot examples + memo) and get the summary JSON."""
import config
from llm_client import call_llm, parse_json

PARTS = {"situation_recap": "SR", "recent_development": "RD"}


def _read(name):
    return (config.PROMPT_DIR / name).read_text(encoding="utf-8")


def load_examples():
    """prompts/examples/<case>/source.txt + summary.md  (human summary, no citations needed)."""
    out = []
    if config.EXAMPLES_DIR.exists():
        for d in sorted(p for p in config.EXAMPLES_DIR.iterdir() if p.is_dir()):
            src, summ = d / "source.txt", d / "summary.md"
            if src.exists() and summ.exists():
                out.append((d.name, src.read_text(encoding="utf-8"), summ.read_text(encoding="utf-8")))
    return out


def build_prompts(source_text: str, examples=None):
    system = _read("system.md").format(points_per_section=config.POINTS_PER_SECTION)
    system += "\n\n" + _read("style_guide.md")

    blocks = []
    for i, (name, src, summ) in enumerate(examples if examples is not None else load_examples(), 1):
        blocks.append(f"<example id=\"{i}\">\n<source>\n{src.strip()}\n</source>\n"
                      f"<human_summary>\n{summ.strip()}\n</human_summary>\n</example>")
    user = ""
    if blocks:
        user += "Examples of past memos and the summaries our analysts wrote:\n\n" + "\n\n".join(blocks) + "\n\n"
    user += f"Now summarize this memo. Return JSON only.\n\n<source>\n{source_text}\n</source>"
    return system, user


def validate_shape(obj, valid_ids):
    problems = []
    for part in PARTS:
        pts = obj.get(part)
        if not isinstance(pts, list) or not pts:
            problems.append(f"'{part}' missing or empty")
            continue
        for j, p in enumerate(pts, 1):
            if not isinstance(p, dict) or not p.get("text"):
                problems.append(f"{part}[{j}] has no text")
                continue
            bad = [c for c in p.get("cites", []) if c not in valid_ids]
            if bad:
                problems.append(f"{part}[{j}] cites unknown IDs {bad}")
            if not p.get("cites"):
                problems.append(f"{part}[{j}] has no citations")
    return problems


def summarize(parsed, examples=None) -> dict:
    """Returns {"situation_recap": [...], "recent_development": [...]} with point IDs added."""
    system, user = build_prompts(parsed.to_prompt_text(), examples)
    valid_ids = set(parsed.by_id())

    raw = call_llm(system, user, task="summarize")
    try:
        obj = parse_json(raw)
        problems = validate_shape(obj, valid_ids)
    except Exception as e:
        obj, problems = None, [f"invalid JSON: {e}"]

    if problems:   # one repair round
        fix = (user + "\n\nYour previous answer had these problems:\n- " + "\n- ".join(problems)
               + f"\n\nPrevious answer:\n{raw}\n\nReturn the corrected JSON only.")
        raw = call_llm(system, fix, task="summarize")
        obj = parse_json(raw)

    for part, prefix in PARTS.items():
        for j, p in enumerate(obj.get(part, []), 1):
            p["id"] = f"{prefix}-{j}"
            p["cites"] = [c for c in p.get("cites", []) if c in valid_ids] or p.get("cites", [])
    return obj
