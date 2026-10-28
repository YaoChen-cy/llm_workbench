"""
Project knowledge base: examples (source documents + the expected summary) and the summary profile
learned from them. Everything lives in the project folder so it travels with it:

    <folder>/.workbench/knowledge/
        examples/<id>/example.json   {id, name, created, origin: upload|chat, sources: [file names], summary_file}
        examples/<id>/<source files>, summary.md   (the expected summary as Markdown)
        profile.json                 {text, stats, version, updated, history: [older versions]}

`learn` asks the LLM to compare each source with its summary, then merges the analyses into one profile
(a draft: the user reviews and confirms it before it is saved). A confirmed profile is added to the
system prompt of every chat in the project.
"""
import json
import re
import shutil
import time
import uuid
from pathlib import Path

import pymupdf

from . import citations, documents, llm, projects
from . import files as fs

SUMMARY_TYPES = {".md", ".txt", ".docx", ".pdf"}

ANALYZE_PROMPT = """You are studying how an analyst turns a source document into a summary, so that the same kind of summary can be written for new documents.

<source>
{source}
</source>

<summary>
{summary}
</summary>

Describe precisely and concretely (quote short phrases from the summary as evidence):
1. Structure: the sections or headings in order, bullets vs. paragraphs, number of points per section, what each point covers.
2. Content selection: which kinds of information from the source appear in the summary, as reusable categories (e.g. "provision amount and % of exposure"), and which notable source content is left out.
3. Length: overall and per section.
4. Tone and phrasing: tense, voice, formality, how points typically start, abbreviations, number/currency/date formats, what gets bolded.
5. Required information: the facts this kind of summary always needs.
Do not summarise the document's content itself; describe the summary's pattern."""

MERGE_PROMPT = """Below are analyses of {n} example(s) of the same summary task, each comparing a source document with the summary an analyst wrote.

Current project instructions:
<instructions>
{instructions}
</instructions>

Measured from the example summaries (these numbers are exact; use them for length rules):
{stats}

<analyses>
{analyses}
</analyses>

Write ONE summary profile that another writer could follow to produce indistinguishable summaries for new documents. Only state patterns supported by the examples; be concrete, and quote a short example phrase for each style rule. Do not include any rule about citations, reference numbers, footnotes or source lists: the app adds source citations itself. Output exactly this Markdown and nothing else:

## Summary profile
### Structure
### Required information
(bullet list of facts every summary needs; the assistant asks the user when one is missing from the documents)
### Content selection
### Length
### Tone and phrasing
### Formatting
### Template
(a skeleton of the summary with [placeholders])

## Suggested additions to the project instructions
(3-6 bullets the user may add to the instructions; skip anything the current instructions already say)"""


# ---------------------------------------------------------------- storage

def _kdir(project: dict) -> Path:
    d = Path(project["folder"]) / projects.META / "knowledge"
    (d / "examples").mkdir(parents=True, exist_ok=True)
    return d


def _safe(name: str) -> str:
    return re.sub(r'[^\w.\- ]', "_", Path(name).name).strip() or "file"


def list_examples(pid: str) -> list[dict]:
    d = _kdir(projects.get(pid)) / "examples"
    out = []
    for f in sorted(d.glob("*/example.json")):
        ex = json.loads(f.read_text("utf-8"))
        ex["summary"] = (f.parent / ex["summary_file"]).read_text("utf-8") if (f.parent / ex["summary_file"]).exists() else ""
        out.append(ex)
    return sorted(out, key=lambda e: e["created"])


def add_example(pid: str, name: str, sources: list[tuple[str, bytes]], summary_md: str,
                origin: str = "upload") -> dict:
    """Store an example: source files (copied) + the expected summary (Markdown text)."""
    if not summary_md.strip():
        raise ValueError("The expected summary is empty.")
    for fname, _ in sources:
        if Path(fname).suffix.lower() not in fs.SUPPORTED:
            raise ValueError(f"{fname}: source documents must be PDF, Word, Text or Markdown files.")
    eid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    d = _kdir(projects.get(pid)) / "examples" / eid
    d.mkdir(parents=True)
    names = []
    for fname, data in sources:
        target = d / _safe(fname)
        if target.name == "summary.md" or target.exists():
            target = d / f"source-{len(names) + 1}-{_safe(fname)}"
        target.write_bytes(data)
        names.append(target.name)
    (d / "summary.md").write_text(summary_md.strip() + "\n", "utf-8")
    ex = {"id": eid, "name": name.strip() or (Path(sources[0][0]).stem if sources else f"Example {eid}"),
          "created": time.time(), "origin": origin, "sources": names, "summary_file": "summary.md"}
    (d / "example.json").write_text(json.dumps(ex, indent=1, ensure_ascii=False), "utf-8")
    return {**ex, "summary": summary_md}


def add_example_from_chat(pid: str, chat: dict, summary_md: str, name: str) -> dict:
    """An answer the user approved. Its sources: the documents attached to the chat, plus project context
    documents the summary cites (e.g. a memo added as C1)."""
    cited = {m.group(1).upper() for m in re.finditer(r"\b([CD]\d+)-[a-z]?\d+", summary_md, re.I)}
    entries = list(chat.get("docs", []))
    entries += [c for c in projects.get(pid)["context"] if c["label"].upper() in cited]
    sources = []
    for d in entries:
        try:
            src = documents.source_file(documents.get(d["doc_id"]))
            sources.append((d["name"], src.read_bytes()))
        except (FileNotFoundError, OSError):
            continue
    return add_example(pid, name, sources, summary_md, origin="chat")


def remove_example(pid: str, eid: str):
    d = _kdir(projects.get(pid)) / "examples" / eid
    if d.parent.name == "examples" and (d / "example.json").exists():
        shutil.rmtree(d)


def get_profile(project: dict) -> dict | None:
    f = _kdir(project) / "profile.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else None


def save_profile(pid: str, text: str, stats: dict | None = None, source: str = "learned") -> dict:
    """Save a confirmed profile as a new version; the previous one is kept in history."""
    project = projects.get(pid)
    old = get_profile(project)
    history = (old or {}).get("history", [])
    if old:
        history.append({k: old[k] for k in ("text", "version", "updated", "source") if k in old})
    prof = {"text": text.strip(), "stats": stats if stats is not None else (old or {}).get("stats", {}),
            "version": (old or {}).get("version", 0) + 1, "updated": time.time(), "source": source,
            "history": history[-20:]}
    (_kdir(project) / "profile.json").write_text(json.dumps(prof, indent=1, ensure_ascii=False), "utf-8")
    return prof


def clear_profile(pid: str):
    (_kdir(projects.get(pid)) / "profile.json").unlink(missing_ok=True)


# ---------------------------------------------------------------- reading summaries

def summary_markdown(name: str, data: bytes) -> str:
    """Text of an expected-summary file as Markdown, keeping headings, bullets and bold (Word)."""
    suffix = Path(name).suffix.lower()
    if suffix in (".md", ".txt"):
        return data.decode("utf-8", "replace")
    if suffix == ".docx":
        return _docx_markdown(data)
    if suffix == ".pdf":
        pdf = pymupdf.open(stream=data, filetype="pdf")
        return "\n\n".join(page.get_text().strip() for page in pdf)
    raise ValueError(f"{name}: the expected summary must be a Word, PDF, Text or Markdown file.")


def _docx_markdown(data: bytes) -> str:
    import io
    import docx

    d = docx.Document(io.BytesIO(data))
    lines = []
    for p in d.paragraphs:
        text = "".join(f"**{r.text}**" if r.bold and r.text.strip() else r.text for r in p.runs).strip()
        text = text.replace("****", "")
        if not text:
            continue
        style = (p.style.name or "").lower()
        m = re.match(r"heading\s*(\d)", style)
        numbered = p._p.pPr is not None and p._p.pPr.numPr is not None
        if m or style == "title":
            lines.append(f"{'#' * (int(m.group(1)) if m else 1)} {text.strip('*')}")
        elif "list" in style or numbered:
            lines.append(f"- {text}")
        else:
            lines.append(text)
        lines.append("")
    for t in d.tables:
        rows = [[c.text.strip().replace("|", "/") for c in r.cells] for r in t.rows]
        if rows:
            lines.append("| " + " | ".join(rows[0]) + " |")
            lines.append("|" + "---|" * len(rows[0]))
            lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
            lines.append("")
    return "\n".join(lines).strip()


def stats(summaries: list[str]) -> dict:
    """Length and structure measured in code (the LLM is bad at counting)."""
    per = []
    for md in summaries:
        lines = [ln.strip() for ln in md.splitlines() if ln.strip()]
        sections = [re.sub(r"[#*:]", "", ln).strip() for ln in lines
                    if ln.startswith("#") or re.fullmatch(r"\*\*[^*]{1,80}\*\*:?", ln)]
        bullets = [ln for ln in lines if re.match(r"^([-*•]|\d+[.)])\s+", ln)]
        words = len(re.findall(r"\w+", re.sub(r"[#*]", "", md)))
        per.append({"words": words, "sections": sections, "bullets": len(bullets),
                    "words_per_bullet": round(sum(len(b.split()) for b in bullets) / len(bullets)) if bullets else 0,
                    "bold": md.count("**") // 2})
    if not per:
        return {}

    def rng(key):
        vals = [p[key] for p in per]
        return f"{min(vals)}–{max(vals)}" if min(vals) != max(vals) else str(vals[0])

    return {"examples": len(per), "words": rng("words"), "bullets": rng("bullets"),
            "words_per_bullet": rng("words_per_bullet"), "bold_phrases": rng("bold"),
            "sections": per[-1]["sections"]}


def stats_text(st: dict) -> str:
    if not st:
        return "(no examples)"
    return (f"- examples: {st['examples']}\n- total words per summary: {st['words']}\n"
            f"- bullet points per summary: {st['bullets']} (about {st['words_per_bullet']} words each)\n"
            f"- bold phrases per summary: {st['bold_phrases']}\n"
            f"- sections (latest example): {', '.join(st['sections']) or 'none'}")


# ---------------------------------------------------------------- learning

def _source_text(folder: Path, names: list[str], budget_chars: int) -> str:
    parts = []
    for i, n in enumerate(names, 1):
        try:
            doc = documents.ingest(folder / n, name=n)
            parts.append(documents.to_markdown(doc, f"S{i}"))
        except Exception as e:
            parts.append(f"# Document S{i}: {n}\n(could not be read: {e})")
    text = "\n\n".join(parts)
    if len(text) > budget_chars:
        text = text[:budget_chars] + "\n[... rest of the source omitted for length ...]"
    return text or "(no source document was provided for this example)"


async def learn(pid: str, provider: dict, progress=lambda msg: None) -> dict:
    """Draft a summary profile from the examples. Returns {profile, suggestions, stats}; nothing is saved."""
    project = projects.get(pid)
    examples = list_examples(pid)
    if not examples:
        raise ValueError("Add at least one example (source document + expected summary) first.")
    kdir = _kdir(project) / "examples"
    budget = int(provider.get("context_tokens", 8192) * 0.55) * 4
    analyses = []
    for i, ex in enumerate(examples, 1):
        progress(f"Analyzing example {i} of {len(examples)}: {ex['name']}…")
        summary = citations.strip(ex["summary"])
        source = _source_text(kdir / ex["id"], ex["sources"], budget - len(summary))
        prompt = ANALYZE_PROMPT.format(source=source, summary=summary)
        analyses.append(f"### Example {i}: {ex['name']}\n" +
                        await llm.complete([{"role": "user", "content": prompt}], provider))
    progress("Combining the analyses into a summary profile…")
    st = stats([citations.strip(ex["summary"]) for ex in examples])
    prompt = MERGE_PROMPT.format(n=len(examples), instructions=project["instructions"].strip() or "(none)",
                                 stats=stats_text(st), analyses="\n\n".join(analyses))
    out = await llm.complete([{"role": "user", "content": prompt}], provider)
    profile, suggestions = _split_suggestions(out)
    return {"profile": profile, "suggestions": suggestions, "stats": st}


def _split_suggestions(text: str) -> tuple[str, str]:
    m = re.search(r"^#{1,3}\s*Suggested additions.*$", text, re.M | re.I)
    if not m:
        return text.strip(), ""
    profile = text[:m.start()].strip()
    suggestions = text[m.end():].strip()
    return profile, suggestions


# ---------------------------------------------------------------- prompt

def prompt_section(project: dict, max_example_chars: int = 2500) -> str:
    """What a chat in this project gets from the knowledge base: the confirmed profile + one example."""
    prof = get_profile(project)
    if not prof:
        return ""
    out = ("\n\nThis project has a confirmed summary profile. When the user asks for a summary, follow it exactly: "
           "same structure, length, tone and content selection. If information listed under 'Required information' "
           "is missing from the documents, ask the user for it before drafting (list exactly what is missing); if "
           "the user asks you to go ahead anyway, mark the gaps as [MISSING: ...]."
           f"\n<summary_profile>\n{prof['text']}\n</summary_profile>")
    try:
        examples = list_examples(project["id"])
    except FileNotFoundError:
        examples = []
    if examples:
        ex = citations.strip(examples[-1]["summary"])
        if len(ex) > max_example_chars:
            ex = ex[:max_example_chars] + "\n[...]"
        out += ("\nAn approved summary from this project, as a format reference only (do not reuse its facts; its "
                "source citations were removed, so still cite every fact as instructed):"
                f"\n<example_summary>\n{ex}\n</example_summary>")
    return out
