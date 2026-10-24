import { useEffect, useState } from "react";
import { api, type ChatSummary, type Doc, type Project } from "./api";
import { ACCEPT, report, TypeBadge } from "./fileinfo";

const SOURCE: Record<string, string> = { folder: "from folder", upload: "uploaded", text: "pasted" };

export default function ProjectView({
  project,
  chats,
  docs,
  onChange,
  onOpenChat,
  onNewChat,
  onAddFromFolder,
  onDelete,
  notice,
  onNotice,
}: {
  project: Project;
  chats: ChatSummary[];
  docs: Record<string, Doc>;
  onChange: (p: Project) => void;
  onOpenChat: (id: string) => void;
  onNewChat: () => void;
  onAddFromFolder: () => void;
  onDelete: () => void;
  notice: string;
  onNotice: (s: string) => void;
}) {
  const [instructions, setInstructions] = useState(project.instructions);
  const [name, setName] = useState(project.name);
  const [pasting, setPasting] = useState(false);
  const [pasteTitle, setPasteTitle] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setInstructions(project.instructions);
    setName(project.name);
  }, [project.id, project.instructions, project.name]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      onNotice(`✗ ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const dirty = instructions !== project.instructions;

  return (
    <div className="project">
      <div className="project-head">
        <input
          className="project-name"
          value={name}
          aria-label="Project name"
          onChange={(e) => setName(e.target.value)}
          onBlur={() => name.trim() && name !== project.name && api.patchProject(project.id, { name }).then(onChange)}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
        />
        <div className="muted small project-folder" title="The assistant can only read and write inside this folder">
          📁 <code>{project.folder}</code>
        </div>
      </div>

      <section className="card">
        <div className="card-head">
          <h3>Instructions</h3>
          <span className="muted small">Applied to every chat in this project</span>
        </div>
        <textarea
          rows={8}
          value={instructions}
          placeholder="Describe the task, e.g. how summaries should be structured, their length and tone…"
          onChange={(e) => setInstructions(e.target.value)}
        />
        <div className="row end">
          {dirty && (
            <button className="btn" onClick={() => setInstructions(project.instructions)}>
              Discard
            </button>
          )}
          <button
            className="btn primary"
            disabled={!dirty || busy}
            onClick={() => run(async () => onChange(await api.patchProject(project.id, { instructions })))}
          >
            Save instructions
          </button>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h3>Context</h3>
          <span className="muted small">Background documents included in every chat, cited as C1, C2…</span>
        </div>
        {project.context.length === 0 && <p className="muted small">No context yet.</p>}
        <div className="ctx-list">
          {project.context.map((c) => {
            const d = docs[c.doc_id];
            return (
              <div key={c.doc_id} className="ctx-row">
                <b className="ctx-label">{c.label}</b>
                <TypeBadge name={c.name} />
                <span className="grow ctx-name" title={c.path}>
                  {c.name}
                </span>
                <span className="muted small">
                  {d ? (d.kind === "pdf" ? `${d.pages} pages · ` : "") : ""}
                  {SOURCE[c.source]}
                </span>
                <button
                  className="icon-btn"
                  aria-label={`Remove ${c.name}`}
                  disabled={busy}
                  onClick={() =>
                    confirm(
                      c.source === "folder"
                        ? `Remove ${c.name} from context? The file stays in the folder.`
                        : `Remove ${c.name} from context? Its copy in .workbench/context is deleted.`,
                    ) && run(async () => onChange(await api.removeContext(project.id, c.doc_id)))
                  }
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
        <div className="row wrap">
          <label className={`btn file-btn ${busy ? "disabled" : ""}`}>
            Upload files…
            <input
              type="file"
              multiple
              hidden
              disabled={busy}
              accept={ACCEPT}
              onChange={(e) => {
                const files = [...(e.target.files ?? [])];
                e.target.value = "";
                run(async () => {
                  onNotice(report(await api.addContextUpload(project.id, files), "Uploaded"));
                  onChange(await api.project(project.id));
                });
              }}
            />
          </label>
          <button className="btn" disabled={busy} onClick={onAddFromFolder}>
            Add from project folder…
          </button>
          <button className={`btn ${pasting ? "on" : ""}`} onClick={() => setPasting((v) => !v)}>
            Paste text…
          </button>
          {busy && <span className="muted small">Working…</span>}
        </div>
        {notice && (
          <div className="notice small" role="status">
            <span>{notice}</span>
            <button className="icon-btn" onClick={() => onNotice("")} aria-label="Dismiss">
              ×
            </button>
          </div>
        )}
        {pasting && (
          <div className="form paste">
            <input value={pasteTitle} placeholder="Title (optional)" onChange={(e) => setPasteTitle(e.target.value)} />
            <textarea rows={5} value={pasteText} placeholder="Paste text…" onChange={(e) => setPasteText(e.target.value)} />
            <div className="row end">
              <button
                className="btn primary"
                disabled={!pasteText.trim() || busy}
                onClick={() =>
                  run(async () => {
                    onNotice(report([await api.addContextText(project.id, pasteTitle || "Pasted text", pasteText)]));
                    onChange(await api.project(project.id));
                    setPasteText("");
                    setPasteTitle("");
                    setPasting(false);
                  })
                }
              >
                Add to context
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-head">
          <h3>Chats</h3>
          <button className="btn primary" onClick={onNewChat}>
            + New chat in project
          </button>
        </div>
        {chats.length === 0 && <p className="muted small">No chats yet.</p>}
        {chats.map((c) => (
          <button key={c.id} className="fs-row" onClick={() => onOpenChat(c.id)}>
            <span className="fs-name">{c.title}</span>
            <span className="muted small">{new Date(c.updated * 1000).toLocaleString()}</span>
          </button>
        ))}
      </section>

      <div className="danger">
        <button
          className="link danger-link"
          onClick={() =>
            confirm(
              `Remove "${project.name}" from the app? Its chats are deleted. The folder and its .workbench data stay on disk, so you can reopen it later by creating a project on the same folder.`,
            ) && onDelete()
          }
        >
          Remove project from app
        </button>
      </div>
    </div>
  );
}
