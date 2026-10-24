import { useEffect, useState } from "react";
import { api, type FsListing, type FsRoot } from "./api";

function size(n: number | null) {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1 << 20) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1 << 20)).toFixed(1)} MB`;
}

export default function FilePanel({
  onAttach,
  onClose,
  onOpenSettings,
  busy,
  projectId,
  projectRoot,
  title = "Files",
  actionLabel = "Attach selected",
}: {
  onAttach: (paths: string[]) => Promise<void>;
  onClose: () => void;
  onOpenSettings: () => void;
  busy: boolean;
  /** Inside a project, browsing is limited to its folder. */
  projectId?: string;
  projectRoot?: string;
  title?: string;
  actionLabel?: string;
}) {
  const [roots, setRoots] = useState<FsRoot[]>([]);
  const [listing, setListing] = useState<FsListing | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");

  const open = (path: string) => {
    setError("");
    api.list(path, projectId).then(setListing).catch((e) => setError(String(e.message ?? e)));
  };

  useEffect(() => {
    setSelected(new Set());
    if (projectRoot) open(projectRoot);
    else {
      setListing(null);
      api.roots().then(setRoots).catch((e) => setError(String(e.message ?? e)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, projectRoot]);

  const toggle = (path: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(path)) n.delete(path);
      else n.add(path);
      return n;
    });

  const attach = async () => {
    await onAttach([...selected]);
    setSelected(new Set());
  };

  const rel = listing ? listing.path.slice(listing.root.length).replace(/^\//, "") : "";

  return (
    <aside className="files">
      <div className="panel-head">
        <span>{title}</span>
        <button className="icon-btn" onClick={onClose} aria-label="Close files panel">
          ×
        </button>
      </div>

      {!listing ? (
        <div className="files-body">
          <div className="muted small">Allowed folders</div>
          {roots.length === 0 && (
            <p className="muted small">
              No folders yet. <button className="link" onClick={onOpenSettings}>Add one in Settings</button>.
            </p>
          )}
          {roots.map((r) => (
            <button key={r.path} className="fs-row" disabled={!r.exists} onClick={() => open(r.path)} title={r.path}>
              <span className="fs-icon">📁</span>
              <span className="fs-name">{r.name}</span>
              {!r.exists && <span className="muted small">missing</span>}
            </button>
          ))}
        </div>
      ) : (
        <div className="files-body">
          <div className="crumbs">
            {!projectRoot && (
              <>
                <button className="link" onClick={() => setListing(null)}>Folders</button>
                <span>/</span>
              </>
            )}
            <button className="link" onClick={() => open(listing.root)}>
              {listing.root.split("/").pop()}
            </button>
            {rel && <span className="crumb-rest">/ {rel}</span>}
          </div>
          {listing.parent && (
            <button className="fs-row" onClick={() => open(listing.parent!)}>
              <span className="fs-icon">↩</span>
              <span className="fs-name">..</span>
            </button>
          )}
          {listing.entries.length === 0 && <p className="muted small">Empty folder.</p>}
          {listing.entries.map((e) =>
            e.is_dir ? (
              <button key={e.path} className="fs-row" onClick={() => open(e.path)}>
                <span className="fs-icon">📁</span>
                <span className="fs-name">{e.name}</span>
              </button>
            ) : (
              <label key={e.path} className={`fs-row ${e.supported ? "" : "fs-off"}`} title={e.path}>
                <input
                  type="checkbox"
                  disabled={!e.supported}
                  checked={selected.has(e.path)}
                  onChange={() => toggle(e.path)}
                />
                <span className="fs-name">{e.name}</span>
                <span className="muted small">{size(e.size)}</span>
              </label>
            ),
          )}
        </div>
      )}

      {error && <div className="error small">{error}</div>}
      <div className="files-foot">
        <button className="btn primary" disabled={!selected.size || busy} onClick={attach}>
          {busy ? "Parsing…" : `${actionLabel}${selected.size ? ` (${selected.size})` : ""}`}
        </button>
        <div className="muted small">
          PDF, DOCX, TXT, MD{projectRoot ? " · limited to the project folder" : ""}
        </div>
      </div>
    </aside>
  );
}
