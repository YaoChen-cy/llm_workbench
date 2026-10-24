import { useEffect, useState } from "react";
import { api, type DirListing, type Project } from "./api";
import { ACCEPT, fileSize, isSupported, report, TypeBadge } from "./fileinfo";

const INSTRUCTIONS_HINT = `Describe the task the assistant should perform in this project, e.g.

Draft a credit summary for each memo I attach.
- Two sections: "Situation Recap" and "Recent Development", 2–4 bullet points each.
- Bold the key figures. Use $mm for amounts.
- Only use facts from the attached memo; ask me if something important is missing.`;

function FolderPicker({ start, onPick }: { start: string; onPick: (path: string) => void }) {
  const [listing, setListing] = useState<DirListing | null>(null);
  const [error, setError] = useState("");

  const open = (path?: string) =>
    api
      .dirs(path)
      .then((l) => {
        setListing(l);
        setError("");
      })
      .catch((e) => setError(e.message));

  useEffect(() => {
    open(start || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!listing) return <div className="picker muted small">{error || "Loading…"}</div>;
  return (
    <div className="picker">
      <div className="picker-head">
        <button className="btn small-btn" disabled={!listing.parent} onClick={() => open(listing.parent!)}>
          ↑ Up
        </button>
        <button className="btn small-btn" onClick={() => open(listing.home)}>
          Home
        </button>
        <code className="grow picker-path">{listing.path}</code>
      </div>
      <div className="picker-list">
        {listing.dirs.length === 0 && listing.files.length === 0 && (
          <div className="muted small picker-empty">This folder is empty.</div>
        )}
        {listing.dirs.map((d) => (
          <button key={d.path} className="fs-row" onClick={() => open(d.path)} onDoubleClick={() => onPick(d.path)}>
            <span className="fs-icon">📁</span>
            <span className="fs-name">{d.name}</span>
            {d.is_project && <span className="badge">project</span>}
          </button>
        ))}
        {listing.files.map((f) => (
          <div
            key={f.name}
            className={`fs-row file-row ${f.supported ? "" : "fs-off"}`}
            title={f.supported ? f.name : `${f.name} — this type can't be read yet`}
          >
            <TypeBadge name={f.name} />
            <span className="fs-name">{f.name}</span>
            <span className="muted small">{fileSize(f.size)}</span>
          </div>
        ))}
      </div>
      <div className="picker-count muted small">
        {listing.dirs.length} folder{listing.dirs.length === 1 ? "" : "s"} · {listing.files.length} file
        {listing.files.length === 1 ? "" : "s"}
        {listing.files.length > 0 && ` (${listing.files.filter((f) => f.supported).length} readable: PDF, Word, Text, Markdown)`}
      </div>
      {error && <div className="error small">{error}</div>}
      <div className="picker-foot">
        <button className="btn primary" onClick={() => onPick(listing.path)}>
          Use this folder
        </button>
        <span className="muted small">Double-click a folder to pick it directly.</span>
      </div>
    </div>
  );
}

export default function NewProjectModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (p: Project, message: string) => void;
}) {
  const [name, setName] = useState("");
  const [folder, setFolder] = useState("");
  const [picking, setPicking] = useState(false);
  const [createFolder, setCreateFolder] = useState(true);
  const [instructions, setInstructions] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [pasteTitle, setPasteTitle] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true);
    setError("");
    try {
      const p = await api.createProject({
        name: name || folder.split(/[\\/]/).filter(Boolean).pop() || "Untitled project",
        folder,
        instructions,
        create_folder: createFolder,
      });
      const lines: string[] = [];
      if (p.reopened) lines.push(`This folder already had a project, so "${p.name}" was reopened with its saved instructions and context.`);
      const added = [];
      const upload = files.filter((f) => isSupported(f.name));
      if (upload.length) added.push(...(await api.addContextUpload(p.id, upload)));
      if (pasteText.trim()) added.push(await api.addContextText(p.id, pasteTitle || "Pasted text", pasteText));
      if (added.length) lines.push(report(added, "Added to context"));
      onCreated(await api.project(p.id), lines.join("\n"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal wide-modal" role="dialog" aria-label="New project">
        <div className="panel-head">
          <span>New project</span>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="modal-body form">
          <label>
            Name
            <input value={name} placeholder="e.g. CIP monthly summaries" onChange={(e) => setName(e.target.value)} />
          </label>

          <div className="field">
            <label className="field-label" htmlFor="project-folder">
              Folder <span className="muted">— the assistant can only read files in this folder and save outputs here</span>
            </label>
            <div className="row">
              <input
                id="project-folder"
                className="grow"
                value={folder}
                placeholder="/Users/you/Documents/cip  or  C:\Work\cip"
                onChange={(e) => setFolder(e.target.value)}
              />
              <button className={`btn ${picking ? "on" : ""}`} type="button" onClick={() => setPicking((v) => !v)}>
                Browse…
              </button>
            </div>
          </div>
          {picking && (
            <FolderPicker
              start={folder}
              onPick={(p) => {
                setFolder(p);
                setPicking(false);
              }}
            />
          )}
          <label className="inline">
            <input type="checkbox" checked={createFolder} onChange={(e) => setCreateFolder(e.target.checked)} />
            Create the folder if it doesn't exist
          </label>

          <label>
            <span>
              Instructions <span className="muted">— what should the assistant do in this project?</span>
            </span>
            <textarea
              rows={7}
              value={instructions}
              placeholder={INSTRUCTIONS_HINT}
              onChange={(e) => setInstructions(e.target.value)}
            />
          </label>

          <div className="field">
            <span className="field-label">
              Context <span className="muted">— optional background the assistant always sees: sample summaries, glossaries, templates…</span>
            </span>
            <div className="row wrap">
              <label className="btn file-btn">
                Upload files…
                <input
                  type="file"
                  multiple
                  hidden
                  accept={ACCEPT}
                  onChange={(e) => {
                    const picked = [...(e.target.files ?? [])];
                    setFiles((f) => [...f, ...picked.filter((p) => !f.some((x) => x.name === p.name && x.size === p.size))]);
                    e.target.value = "";
                  }}
                />
              </label>
              {files.length > 0 && (
                <span className="muted small">
                  {files.filter((f) => isSupported(f.name)).length} of {files.length} file(s) will be added when you create the project
                </span>
              )}
            </div>
            {files.length > 0 && (
              <div className="upload-list">
                {files.map((f, i) => (
                  <div key={i} className={`upload-row ${isSupported(f.name) ? "" : "bad"}`}>
                    <TypeBadge name={f.name} />
                    <span className="grow fs-name" title={f.name}>
                      {f.name}
                    </span>
                    <span className="muted small">{fileSize(f.size)}</span>
                    {isSupported(f.name) ? (
                      <span className="ok small">✓ ready</span>
                    ) : (
                      <span className="error small">unsupported type</span>
                    )}
                    <button
                      className="icon-btn"
                      aria-label={`Remove ${f.name}`}
                      onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
            <input
              value={pasteTitle}
              placeholder="Title for pasted text (optional)"
              onChange={(e) => setPasteTitle(e.target.value)}
            />
            <textarea
              rows={3}
              value={pasteText}
              placeholder="…or paste text here"
              onChange={(e) => setPasteText(e.target.value)}
            />
            <span className="muted small">You can add more context and files from the project folder later.</span>
          </div>
          {error && <div className="error small">{error}</div>}
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" disabled={!folder.trim() || busy} onClick={create}>
            {busy ? "Creating…" : "Create project"}
          </button>
        </div>
      </div>
    </div>
  );
}
