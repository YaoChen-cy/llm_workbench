import { useState } from "react";
import { api } from "./api";
import { TypeBadge } from "./fileinfo";
import Markdown, { type OnCite } from "./Markdown";

type Part =
  | { kind: "text"; text: string }
  | { kind: "file"; path: string; content: string; complete: boolean };

const BLOCK = /<file\s+(?:path|name)\s*=\s*["']([^"']+)["']\s*>\n?([\s\S]*?)\n?<\/file>/gi;
const OPEN = /<file\s+(?:path|name)\s*=\s*["']([^"']+)["']\s*>\n?/i;
const CITE = /\[[CD]\d+-[a-z]?\d+/i;

/** Split an answer into prose and <file path="..."> blocks (the last one may still be streaming). */
function splitAnswer(text: string): Part[] {
  const parts: Part[] = [];
  let at = 0;
  for (const m of text.matchAll(BLOCK)) {
    if (m.index! > at) parts.push({ kind: "text", text: text.slice(at, m.index) });
    parts.push({ kind: "file", path: m[1].trim(), content: m[2].replace(/^\n+|\n+$/g, "") + "\n", complete: true });
    at = m.index! + m[0].length;
  }
  const rest = text.slice(at);
  const open = OPEN.exec(rest);
  if (open) {
    if (open.index) parts.push({ kind: "text", text: rest.slice(0, open.index) });
    parts.push({ kind: "file", path: open[1].trim(), content: rest.slice(open.index + open[0].length), complete: false });
  } else if (rest) parts.push({ kind: "text", text: rest });
  return parts;
}

function FileCard({
  part,
  chatId,
  inProject,
  resolve,
  onCite,
  onNotice,
}: {
  part: Extract<Part, { kind: "file" }>;
  chatId?: string;
  inProject: boolean;
  resolve: Parameters<typeof Markdown>[0]["resolve"];
  onCite?: OnCite;
  onNotice: (s: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState("");
  const ext = part.path.split(".").pop()?.toLowerCase() ?? "";
  const ready = part.complete && !!chatId && !busy;

  const save = async () => {
    setBusy(true);
    try {
      let r;
      try {
        r = await api.saveChatFile(chatId!, part.path, part.content);
      } catch (e) {
        if (!(e as Error).message.includes("already exists") || !confirm(`${part.path} already exists in the project folder. Overwrite it?`))
          throw e;
        r = await api.saveChatFile(chatId!, part.path, part.content, true);
      }
      setSaved(r.path);
      onNotice(`✓ Saved to ${r.path}`);
    } catch (e) {
      onNotice(`✗ ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    setBusy(true);
    try {
      const blob = await api.downloadChatFile(chatId!, part.path, part.content);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = part.path.split("/").pop() || "file";
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (e) {
      onNotice(`✗ ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="file-card">
      <div className="file-card-head">
        <span className="file-icon" aria-hidden>
          📄
        </span>
        <TypeBadge name={part.path} />
        <span className="grow fs-name" title={part.path}>
          {part.path}
        </span>
        <span className="muted small">
          {part.complete ? `${part.content.length.toLocaleString()} characters` : "writing…"}
        </span>
      </div>
      {ext === "docx" && <div className="muted small">Written in Markdown; saved as a Word document.</div>}
      <div className="row wrap">
        {inProject && (
          <button className="btn primary small-btn" disabled={!ready} onClick={save}>
            {saved ? "Saved ✓ — save again" : "Save to project folder"}
          </button>
        )}
        <button className="btn small-btn" disabled={!ready} onClick={download}>
          Download
        </button>
        <button className="link small" onClick={() => setOpen((v) => !v)}>
          {open ? "Hide preview" : "Preview"}
        </button>
        {CITE.test(part.content) && (
          <span className="muted small">Citations become numbered references with a Sources list.</span>
        )}
      </div>
      {!inProject && part.complete && (
        <div className="muted small">To save straight into a folder, chat inside a project.</div>
      )}
      {saved && <div className="small ok">Saved to {saved}</div>}
      {open &&
        (ext === "md" || ext === "docx" || ext === "txt" ? (
          <div className="file-preview">
            <Markdown text={part.content} resolve={resolve} onCite={onCite} />
          </div>
        ) : (
          <pre className="file-preview code">{part.content}</pre>
        ))}
    </div>
  );
}

/** An assistant answer: Markdown prose plus a card for each file the model wrote. */
export default function Answer({
  text,
  resolve,
  onCite,
  chatId,
  inProject,
  onNotice,
}: {
  text: string;
  resolve: Parameters<typeof Markdown>[0]["resolve"];
  onCite?: OnCite;
  chatId?: string;
  inProject: boolean;
  onNotice: (s: string) => void;
}) {
  return (
    <>
      {splitAnswer(text).map((p, i) =>
        p.kind === "text" ? (
          p.text.trim() && <Markdown key={i} text={p.text} resolve={resolve} onCite={onCite} />
        ) : (
          <FileCard
            key={i}
            part={p}
            chatId={chatId}
            inProject={inProject}
            resolve={resolve}
            onCite={onCite}
            onNotice={onNotice}
          />
        ),
      )}
    </>
  );
}
