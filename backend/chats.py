"""
Chat storage (data/chats/<id>.json) and prompt assembly.

Documents attached anywhere in a chat stay in its context with stable labels D1, D2, ...
In a project chat, the project's instructions and its context documents (C1, C2, ...) come first.
If documents don't fit the model's context budget, the blocks most relevant to the question are kept.
"""
import json
import re
import time
import uuid
from collections import Counter

from . import documents, outputs
from .settings import CHATS_DIR

SYSTEM_PROMPT = """You are a careful assistant working with the user's documents.

When documents are provided:
- Answer from the documents. Every factual statement taken from them must end with its source ID(s) in square brackets, exactly as written in the documents, e.g. "Revenue was $1.42bn [D1-p1-4]." Multiple sources: [D1-p2-3, D2-p5-1].
- IDs starting with C are project context (background material); IDs starting with D are documents attached to this chat.
- Never invent IDs. If the documents do not contain the answer, say so plainly.
- If no documents are provided, do not write any source IDs at all.
- Text marked [...] was left out to save space; say if the answer may be in the omitted parts.

Write in clear, concise English and use Markdown for structure."""

DOC_SHARE = 0.6          # fraction of the context budget available for documents
REPLY_RESERVE = 1500     # tokens kept free for the answer


def est_tokens(text: str) -> int:
    return len(text) // 4 + 1


# ---------------------------------------------------------------- storage

def _path(chat_id: str):
    if not re.fullmatch(r"[a-f0-9]{12}", chat_id):
        raise FileNotFoundError(chat_id)
    return CHATS_DIR / f"{chat_id}.json"


def create(project_id: str | None = None) -> dict:
    now = time.time()
    chat = {"id": uuid.uuid4().hex[:12], "title": "New chat", "created": now, "updated": now,
            "project_id": project_id, "docs": [], "messages": []}
    save(chat)
    return chat


def get(chat_id: str) -> dict:
    p = _path(chat_id)
    if not p.exists():
        raise FileNotFoundError(chat_id)
    return json.loads(p.read_text("utf-8"))


def save(chat: dict):
    chat["updated"] = time.time()
    _path(chat["id"]).write_text(json.dumps(chat, ensure_ascii=False, indent=1), "utf-8")


def delete(chat_id: str):
    _path(chat_id).unlink(missing_ok=True)


def delete_project_chats(project_id: str):
    for c in list_all(project_id):
        delete(c["id"])


def list_all(project_id: str | None = None) -> list[dict]:
    """Chats of one project, or (project_id=None) the chats that belong to no project."""
    out = []
    for f in CHATS_DIR.glob("*.json"):
        c = json.loads(f.read_text("utf-8"))
        if c.get("project_id") != project_id:
            continue
        out.append({"id": c["id"], "title": c["title"], "updated": c["updated"], "n_docs": len(c["docs"])})
    return sorted(out, key=lambda c: -c["updated"])


def attach(chat: dict, doc_ids: list[str]) -> list[dict]:
    """Add documents to the chat (idempotent); returns the newly attached entries."""
    have = {d["doc_id"] for d in chat["docs"]}
    added = []
    for did in doc_ids:
        if did in have:
            continue
        doc = documents.get(did)
        entry = {"doc_id": did, "label": f"D{len(chat['docs']) + 1}", "name": doc["name"]}
        chat["docs"].append(entry)
        have.add(did)
        added.append(entry)
    return added


def detach(chat: dict, doc_id: str):
    # Labels are not renumbered: earlier answers keep pointing at the right document.
    chat["docs"] = [d for d in chat["docs"] if d["doc_id"] != doc_id]


# ---------------------------------------------------------------- prompt assembly

_WORD = re.compile(r"[a-z0-9][a-z0-9.$%-]*", re.I)
_STOP = set("the a an and or of to in on for with by is are was were be been this that these those it its as at "
            "from what which who how why when where do does did can could should would will please me my i you "
            "summarize summary tell about give list document documents".split())


def _terms(text: str) -> Counter:
    return Counter(w.lower().strip(".") for w in _WORD.findall(text) if w.lower() not in _STOP and len(w) > 1)


def _select_blocks(docs: list[tuple[dict, str]], query: str, budget: int) -> dict[str, set]:
    """Pick the blocks most relevant to `query` until `budget` tokens; returns {doc_id: {block ids}}."""
    q = _terms(query)
    scored = []
    for doc, _ in docs:
        cit = [b for b in doc["blocks"] if b.get("id")]
        for i, b in enumerate(cit):
            t = _terms(b["text"] + " " + b["heading"])
            score = sum(min(t[w], 3) for w in q) / (1 + len(b["text"]) / 2000)
            score += 0.3 if i < 3 else 0        # keep each document's opening for orientation
            scored.append((score, doc["id"], b))
    scored.sort(key=lambda x: -x[0])
    keep, used = {doc["id"]: set() for doc, _ in docs}, 0
    for _, did, b in scored:
        cost = est_tokens(b["text"]) + 8
        if used + cost > budget:
            continue
        keep[did].add(b["id"])
        used += cost
    return keep


def build_messages(chat: dict, user_text: str, context_tokens: int,
                   project: dict | None = None) -> tuple[list[dict], dict]:
    entries = (project["context"] if project else []) + chat["docs"]
    docs = [(documents.get(d["doc_id"]), d["label"]) for d in entries]
    budget = int(context_tokens * DOC_SHARE)
    full = [documents.to_markdown(doc, label) for doc, label in docs]
    info = {"docs": len(docs), "truncated": False}
    if docs and est_tokens("\n\n".join(full)) > budget:
        keep = _select_blocks(docs, user_text, budget)
        full = [documents.to_markdown(doc, label, keep[doc["id"]]) for doc, label in docs]
        info["truncated"] = True
    system = SYSTEM_PROMPT
    if project:
        system += f"\n\nYou are working in the project \"{project['name']}\"."
        if project["instructions"].strip():
            system += ("\nFollow the project instructions below for every request in this project."
                       f"\n<project_instructions>\n{project['instructions'].strip()}\n</project_instructions>")
    system += "\n" + outputs.FILE_INSTRUCTIONS.format(where=outputs.WHERE_PROJECT if project else outputs.WHERE_CHAT)
    if docs:
        system += "\n\n<documents>\n" + "\n\n".join(full) + "\n</documents>"

    # Keep as much recent history as fits.
    remaining = context_tokens - est_tokens(system) - est_tokens(user_text) - REPLY_RESERVE
    history = []
    for m in reversed(chat["messages"]):
        cost = est_tokens(m["content"])
        if cost > remaining:
            break
        history.insert(0, {"role": m["role"], "content": m["content"]})
        remaining -= cost
    info["history_messages"] = len(history)
    info["prompt_tokens_est"] = context_tokens - REPLY_RESERVE - remaining
    return [{"role": "system", "content": system}, *history, {"role": "user", "content": user_text}], info
