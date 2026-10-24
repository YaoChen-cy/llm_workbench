import { useState } from "react";
import { api, type Provider, type Settings } from "./api";

function ProviderForm({
  name,
  p,
  onChange,
}: {
  name: string;
  p: Provider;
  onChange: (p: Provider) => void;
}) {
  const [models, setModels] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [headers, setHeaders] = useState(JSON.stringify(p.extra_headers ?? {}, null, 0));
  const set = <K extends keyof Provider>(k: K, v: Provider[K]) => onChange({ ...p, [k]: v });

  return (
    <div className="form">
      <label>
        Type
        <select value={p.type} onChange={(e) => set("type", e.target.value as Provider["type"])}>
          <option value="ollama">Ollama (native API)</option>
          <option value="openai">OpenAI-compatible</option>
        </select>
      </label>
      <label>
        Base URL
        <input
          value={p.base_url}
          placeholder={p.type === "ollama" ? "http://localhost:11434" : "https://gateway/v1"}
          onChange={(e) => set("base_url", e.target.value)}
        />
      </label>
      <label>
        Model
        <div className="row">
          <input value={p.model} list={`models-${name}`} onChange={(e) => set("model", e.target.value)} />
          <datalist id={`models-${name}`}>
            {models.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          <button
            className="btn"
            type="button"
            onClick={() =>
              api
                .models(name)
                .then((r) => {
                  setModels(r.models);
                  setStatus(`${r.models.length} models available (save first if you changed the URL).`);
                })
                .catch((e) => setStatus(e.message))
            }
          >
            List
          </button>
        </div>
      </label>
      <label>
        API key {p.has_api_key && <span className="muted small">(stored — leave blank to keep)</span>}
        <input
          type="password"
          autoComplete="off"
          value={p.api_key ?? ""}
          placeholder={p.has_api_key ? "••••••••" : "optional; or set LLM_API_KEY"}
          onChange={(e) => set("api_key", e.target.value)}
        />
      </label>
      <label>
        <span>
          Extra headers (JSON; <code>{"{api_key}"}</code> is replaced by the key)
        </span>
        <input
          value={headers}
          onChange={(e) => {
            setHeaders(e.target.value);
            try {
              set("extra_headers", JSON.parse(e.target.value || "{}"));
            } catch {
              /* keep typing */
            }
          }}
        />
      </label>
      <div className="row wrap">
        <label className="inline">
          <input type="checkbox" checked={p.verify_ssl} onChange={(e) => set("verify_ssl", e.target.checked)} />
          Verify SSL
        </label>
        <label className="inline">
          <input type="checkbox" checked={p.bypass_proxy} onChange={(e) => set("bypass_proxy", e.target.checked)} />
          Bypass proxy
        </label>
      </div>
      <div className="row">
        <label>
          Context window (tokens)
          <input
            type="number"
            min={1024}
            step={1024}
            value={p.context_tokens}
            onChange={(e) => set("context_tokens", Number(e.target.value))}
          />
        </label>
        <label>
          Temperature
          <input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={p.temperature}
            onChange={(e) => set("temperature", Number(e.target.value))}
          />
        </label>
      </div>
      {status && <div className="muted small">{status}</div>}
    </div>
  );
}

export default function SettingsModal({
  settings,
  onClose,
  onSaved,
}: {
  settings: Settings;
  onClose: () => void;
  onSaved: (s: Settings) => void;
}) {
  const [draft, setDraft] = useState<Settings>(structuredClone(settings));
  const [tab, setTab] = useState<string>(settings.active_provider);
  const [newFolder, setNewFolder] = useState("");
  const [test, setTest] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const s = await api.saveSettings(draft);
      onSaved(s);
      setDraft(structuredClone(s));
      return s;
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-label="Settings">
        <div className="panel-head">
          <span>Settings</span>
          <button className="icon-btn" onClick={onClose} aria-label="Close settings">
            ×
          </button>
        </div>
        <div className="tabs">
          {Object.entries(draft.providers).map(([name, p]) => (
            <button key={name} className={tab === name ? "on" : ""} onClick={() => setTab(name)}>
              {p.label}
              {draft.active_provider === name && <span className="dot" title="Active" />}
            </button>
          ))}
          <button className={tab === "_folders" ? "on" : ""} onClick={() => setTab("_folders")}>
            Folders
          </button>
        </div>

        <div className="modal-body">
          {tab === "_folders" ? (
            <div className="form">
              <p className="muted small">
                The file browser can only read inside these folders. Subfolders are included.
              </p>
              {draft.allowed_folders.map((f) => (
                <div key={f} className="row folder-row">
                  <code className="grow">{f}</code>
                  <button
                    className="btn"
                    onClick={() => setDraft({ ...draft, allowed_folders: draft.allowed_folders.filter((x) => x !== f) })}
                  >
                    Remove
                  </button>
                </div>
              ))}
              <div className="row">
                <input
                  className="grow"
                  value={newFolder}
                  placeholder="/Users/you/Documents/memos  or  ~/Documents/memos"
                  onChange={(e) => setNewFolder(e.target.value)}
                />
                <button
                  className="btn"
                  disabled={!newFolder.trim()}
                  onClick={() => {
                    setDraft({ ...draft, allowed_folders: [...draft.allowed_folders, newFolder.trim()] });
                    setNewFolder("");
                  }}
                >
                  Add
                </button>
              </div>
            </div>
          ) : (
            <>
              <ProviderForm
                key={tab}
                name={tab}
                p={draft.providers[tab]}
                onChange={(p) => setDraft({ ...draft, providers: { ...draft.providers, [tab]: p } })}
              />
              <div className="row wrap">
                {draft.active_provider !== tab && (
                  <button className="btn" onClick={() => setDraft({ ...draft, active_provider: tab })}>
                    Use this provider
                  </button>
                )}
                <button
                  className="btn"
                  onClick={async () => {
                    setTest("Saving and testing…");
                    await save();
                    const r = await api.testProvider(tab);
                    setTest(r.ok ? `✓ Replied "${r.reply}" in ${r.seconds}s` : `✗ ${r.error}`);
                  }}
                >
                  Save & test connection
                </button>
              </div>
              {test && <div className={`small ${test.startsWith("✗") ? "error" : "muted"}`}>{test}</div>}
            </>
          )}
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn primary"
            disabled={saving}
            onClick={async () => {
              await save();
              onClose();
            }}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
