import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  streamMessage,
  type Chat,
  type ChatSummary,
  type ContextInfo,
  type Doc,
  type DocMeta,
  type Message,
  type Project,
  type ProjectSummary,
  type Settings,
} from "./api";
import FilePanel from "./FilePanel";
import { report } from "./fileinfo";
import Answer from "./Answer";
import NewProjectModal from "./NewProjectModal";
import ProjectView from "./ProjectView";
import SettingsModal from "./SettingsModal";
import SourcePanel, { type SourceTarget } from "./SourcePanel";

type Pending = { user: string; text: string; info?: ContextInfo; error?: string; started: number };
// What the right-hand file panel adds files to.
type FilesTarget = "chat" | "context" | null;

function slug(s: string) {
  return s.replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "_").slice(0, 50) || "output";
}

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [chat, setChat] = useState<Chat | null>(null);
  const [docs, setDocs] = useState<Record<string, Doc>>({});
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [filesTarget, setFilesTarget] = useState<FilesTarget>(null);
  const [source, setSource] = useState<SourceTarget | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showNewProject, setShowNewProject] = useState(false);
  const [attaching, setAttaching] = useState(false);
  const [notice, setNotice] = useState("");
  const [projectNotice, setProjectNotice] = useState("");
  const [dragging, setDragging] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const uploadRef = useRef<HTMLInputElement>(null);

  const pid = project?.id;
  const refreshChats = useCallback(() => api.chats(pid).then(setChats), [pid]);
  const refreshProjects = useCallback(() => api.projects().then(setProjects), []);

  useEffect(() => {
    api.settings().then(setSettings);
    refreshProjects();
  }, [refreshProjects]);

  useEffect(() => {
    refreshChats();
  }, [refreshChats]);

  // Load full documents (chat attachments + project context) for citation previews and chips.
  useEffect(() => {
    const ids = [...(chat?.docs ?? []), ...(project?.context ?? [])].map((d) => d.doc_id);
    ids.forEach((id) => {
      if (!docs[id]) api.doc(id).then((doc) => setDocs((m) => ({ ...m, [doc.id]: doc })));
    });
  }, [chat, project, docs]);

  // Re-render every second while waiting so the elapsed-time counter moves.
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [pending]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [chat?.messages.length, pending?.text]);

  // ---------------------------------------------------------------- navigation

  const openProject = async (id: string | null) => {
    if (pending) return;
    setChat(null);
    setNotice("");
    setProjectNotice("");
    setFilesTarget(null);
    setSource(null);
    if (!id) return setProject(null);
    try {
      setProject(await api.project(id));
    } catch (e) {
      setNotice((e as Error).message);
    }
  };

  const openChat = async (id: string) => {
    if (pending) return;
    setChat(await api.chat(id));
    setNotice("");
    setSource(null);
    if (filesTarget === "context") setFilesTarget(null);
  };

  const newChat = async () => {
    if (pending) return;
    setNotice("");
    if (project) {
      setChat(await api.newChat(project.id));
      refreshChats();
    } else setChat(null);
  };

  const ensureChat = async () => {
    if (chat) return chat;
    const c = await api.newChat(pid);
    setChat(c);
    refreshChats();
    return c;
  };

  // ---------------------------------------------------------------- attachments

  const attachMetas = async (metas: DocMeta[]) => {
    const good = metas.filter((m) => m.ok && m.id);
    setNotice(report(metas, "Attached"));
    if (!good.length) return;
    const c = await ensureChat();
    setChat(await api.patchChat(c.id, { attach: good.map((m) => m.id!) }));
    refreshChats();
  };

  const withAttaching = async (fn: () => Promise<void>) => {
    setAttaching(true);
    try {
      await fn();
    } catch (e) {
      setNotice(String((e as Error).message));
    } finally {
      setAttaching(false);
    }
  };

  const onFilesPicked = (paths: string[]) =>
    withAttaching(async () => {
      if (filesTarget === "context" && project) {
        setProjectNotice(report(await api.addContextPaths(project.id, paths)));
        setProject(await api.project(project.id));
        refreshProjects();
      } else {
        await attachMetas(await api.ingest(paths, pid));
      }
    });

  const uploadFiles = (files: File[]) => files.length && withAttaching(async () => attachMetas(await api.upload(files)));

  // ---------------------------------------------------------------- messages

  const send = async () => {
    const text = input.trim();
    if (!text || pending) return;
    const c = await ensureChat();
    setInput("");
    setNotice("");
    const ac = new AbortController();
    abortRef.current = ac;
    let p: Pending = { user: text, text: "", started: Date.now() };
    setPending(p);
    try {
      await streamMessage(
        c.id,
        text,
        (e) => {
          if (e.type === "info") p = { ...p, info: e.data };
          else if (e.type === "token") p = { ...p, text: p.text + e.data.t };
          else if (e.type === "error") p = { ...p, error: e.data.message };
          setPending(p);
        },
        ac.signal,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") setNotice(String((e as Error).message));
    } finally {
      abortRef.current = null;
      // Give the server a moment to persist a stopped answer, then reload the chat.
      setTimeout(async () => {
        setChat(await api.chat(c.id));
        setPending(null);
        refreshChats();
      }, ac.signal.aborted ? 300 : 0);
    }
  };

  const saveToFolder = async (m: Message) => {
    if (!project || !chat) return;
    const name = prompt(`Save this answer in the project folder as:\n(${project.folder})`, `${slug(chat.title)}.md`);
    if (!name) return;
    try {
      const r = await api.writeFile(project.id, name, m.content);
      setNotice(`Saved to ${r.path}`);
    } catch (e) {
      const msg = (e as Error).message;
      if (msg.includes("already exists") && confirm(`${name} already exists. Overwrite it?`)) {
        const r = await api.writeFile(project.id, name, m.content, true);
        setNotice(`Saved to ${r.path}`);
      } else setNotice(msg);
    }
  };

  const removeChat = async (id: string) => {
    if (!confirm("Delete this chat? Attached files are not deleted.")) return;
    await api.deleteChat(id);
    if (chat?.id === id) setChat(null);
    refreshChats();
  };

  const resolve = (cid: string) => {
    const [label, ...rest] = cid.split("-");
    const bid = rest.join("-");
    const entries = [...(chat?.docs ?? []), ...(project?.context ?? [])];
    const chatDoc = entries.find((d) => d.label.toLowerCase() === label.toLowerCase());
    const doc = chatDoc ? docs[chatDoc.doc_id] : undefined;
    const block = doc?.blocks.find((b) => b.id === bid);
    return { chatDoc, doc, block };
  };

  const openSource = (cid: string, claim: string) => {
    const { chatDoc, block } = resolve(cid);
    if (!chatDoc || !block?.id) return;
    setFilesTarget(null);
    setSource({ docId: chatDoc.doc_id, label: cid, blockId: block.id, claim });
  };

  const active = settings ? settings.providers[settings.active_provider] : null;
  const elapsed = pending ? Math.round((Date.now() - pending.started) / 1000) : 0;
  const showProjectHome = project && !chat;

  return (
    <div className={`app ${source ? "with-source" : filesTarget ? "with-files" : ""}`}>
      <nav className="sidebar">
        <div className="brand">
          <span className="logo" aria-hidden />
          LLM Workbench
        </div>
        <button className="btn primary wide" onClick={newChat}>
          + New chat{project ? " in project" : ""}
        </button>

        <div className="side-scroll">
          <div className="side-head">
            <span>Projects</span>
            <button className="icon-btn" aria-label="New project" title="New project" onClick={() => setShowNewProject(true)}>
              +
            </button>
          </div>
          {projects.length === 0 && (
            <button className="link small side-empty" onClick={() => setShowNewProject(true)}>
              Create your first project
            </button>
          )}
          {projects.map((p) => (
            <div
              key={p.id}
              className={`chat-item ${project?.id === p.id ? (chat ? "in" : "on") : ""} ${p.missing ? "fs-off" : ""}`}
              onClick={() => openProject(p.id)}
              role="button"
              tabIndex={0}
              title={p.missing ? `Folder missing: ${p.folder}` : p.folder}
              onKeyDown={(e) => e.key === "Enter" && openProject(p.id)}
            >
              <span className="fs-icon">▣</span>
              <span className="chat-title">{p.name}</span>
            </div>
          ))}

          <div className="side-head">
            <span className="chat-title">{project ? `Chats · ${project.name}` : "Chats"}</span>
            {project && (
              <button className="link small" onClick={() => openProject(null)} title="Back to chats without a project">
                All chats
              </button>
            )}
          </div>
          {chats.length === 0 && <div className="muted small side-empty">No chats yet.</div>}
          {chats.map((c) => (
            <div
              key={c.id}
              className={`chat-item ${chat?.id === c.id ? "on" : ""}`}
              onClick={() => openChat(c.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && openChat(c.id)}
            >
              <span className="chat-title">{c.title}</span>
              {c.n_docs > 0 && <span className="badge">{c.n_docs}</span>}
              <button
                className="icon-btn del"
                aria-label="Delete chat"
                onClick={(e) => {
                  e.stopPropagation();
                  removeChat(c.id);
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>

        <div className="side-foot">
          <button className="btn wide" onClick={() => setShowSettings(true)}>
            ⚙ Settings
          </button>
          {active && (
            <div className="muted small model-line" title={active.base_url}>
              {active.label}: <b>{active.model}</b>
            </div>
          )}
        </div>
      </nav>

      <main
        className="main"
        onDragOver={(e) => {
          if (showProjectHome) return;
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(e) => e.currentTarget === e.target && setDragging(false)}
        onDrop={(e) => {
          if (showProjectHome) return;
          e.preventDefault();
          setDragging(false);
          uploadFiles([...e.dataTransfer.files]);
        }}
      >
        <header className="topbar">
          <div className="topbar-title">
            {project && (
              <>
                <button className="link crumb" onClick={() => openProject(project.id)}>
                  {project.name}
                </button>
                {chat && <span className="muted"> › </span>}
              </>
            )}
            {chat ? chat.title : project ? "" : "New chat"}
          </div>
          {settings && (
            <select
              className="provider-select"
              value={settings.active_provider}
              disabled={!!pending}
              onChange={async (e) => setSettings(await api.saveSettings({ active_provider: e.target.value }))}
              aria-label="Model provider"
            >
              {Object.entries(settings.providers).map(([k, p]) => (
                <option key={k} value={k}>
                  {p.label} · {p.model}
                </option>
              ))}
            </select>
          )}
          {!showProjectHome && (
            <button
              className={`btn ${filesTarget === "chat" ? "on" : ""}`}
              onClick={() => {
                setSource(null);
                setFilesTarget((v) => (v === "chat" ? null : "chat"));
              }}
            >
              📁 Files
            </button>
          )}
        </header>

        {showProjectHome ? (
          <div className="messages">
            <ProjectView
              project={project}
              chats={chats}
              docs={docs}
              onChange={(p) => {
                setProject(p);
                refreshProjects();
              }}
              onOpenChat={openChat}
              onNewChat={newChat}
              onAddFromFolder={() => {
                setSource(null);
                setFilesTarget("context");
              }}
              notice={projectNotice}
              onNotice={setProjectNotice}
              onDelete={async () => {
                await api.deleteProject(project.id);
                setProject(null);
                refreshProjects();
              }}
            />
          </div>
        ) : (
          <>
            <div className="messages">
              {!chat?.messages.length && !pending && (
                <div className="empty">
                  {project ? (
                    <>
                      <h2>New chat in {project.name}</h2>
                      <p className="muted">
                        The project instructions and {project.context.length} context document(s) are included
                        automatically. Attach files from the project folder with <b>Files</b>; use{" "}
                        <b>Save to folder</b> under an answer to keep it as a file.
                      </p>
                    </>
                  ) : (
                    <>
                      <h2>Ask anything, or attach documents to work with them</h2>
                      <p className="muted">
                        Open <b>Files</b> to pick documents from your allowed folders, drop files here, or use the 📎
                        button. Answers cite their sources like <span className="cite">D1 · p.3</span> — hover to see
                        the original text. For repeated tasks, create a <b>project</b>.
                      </p>
                    </>
                  )}
                </div>
              )}
              {chat?.messages.map((m, i) => (
                <div key={i} className={`msg ${m.role}`}>
                  {m.role === "user" ? (
                    <div className="bubble">{m.content}</div>
                  ) : (
                    <div className="answer">
                      <Answer
                        text={m.content || (m.error ? "" : "_(empty answer)_")}
                        resolve={resolve}
                        onCite={openSource}
                        chatId={chat?.id}
                        inProject={!!project}
                        onNotice={setNotice}
                      />
                      {m.error && <div className="error small">⚠ {m.error}</div>}
                      <div className="meta small muted">
                        {m.model}
                        {m.context?.truncated && " · documents trimmed to fit context"}
                        {project && m.content && (
                          <>
                            {" · "}
                            <button className="link" onClick={() => saveToFolder(m)}>
                              Save to folder
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
              {pending && (
                <>
                  <div className="msg user">
                    <div className="bubble">{pending.user}</div>
                  </div>
                  <div className="msg assistant">
                    <div className="answer">
                      {pending.text ? (
                        <Answer text={pending.text} resolve={resolve} onCite={openSource} inProject={!!project} onNotice={setNotice} />
                      ) : (
                        <div className="thinking muted">
                          <span className="pulse" /> Reading
                          {pending.info?.docs ? ` ${pending.info.docs} document(s)` : ""}
                          {pending.info ? ` (~${pending.info.prompt_tokens_est.toLocaleString()} tokens)` : ""}…{" "}
                          {elapsed}s
                        </div>
                      )}
                      {pending.error && <div className="error small">⚠ {pending.error}</div>}
                    </div>
                  </div>
                </>
              )}
              <div ref={endRef} />
            </div>

            <div className="composer-wrap">
              {notice && (
                <div className="notice small">
                  <span>{notice}</span>
                  <button className="icon-btn" onClick={() => setNotice("")} aria-label="Dismiss">
                    ×
                  </button>
                </div>
              )}
              {((chat && chat.docs.length > 0) || (project && project.context.length > 0)) && (
                <div className="doc-chips">
                  {project && project.context.length > 0 && (
                    <span className="chip ctx-chip" title={project.context.map((c) => `${c.label} ${c.name}`).join("\n")}>
                      <b>C1–C{project.context.length}</b> project context
                    </span>
                  )}
                  {chat?.docs.map((d) => {
                    const doc = docs[d.doc_id];
                    return (
                      <span key={d.doc_id} className="chip" title={doc?.warnings.join("\n") || d.name}>
                        <b>{d.label}</b> {d.name}
                        {doc && <span className="muted"> · {doc.kind === "pdf" ? `${doc.pages}p` : doc.kind}</span>}
                        {doc?.warnings.length ? <span className="warn">!</span> : null}
                        <button
                          className="icon-btn"
                          aria-label={`Remove ${d.name}`}
                          disabled={!!pending}
                          onClick={async () => setChat(await api.patchChat(chat.id, { detach: [d.doc_id] }))}
                        >
                          ×
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}
              <div className="composer">
                <button
                  className="icon-btn attach"
                  aria-label="Upload files"
                  title="Upload files"
                  disabled={attaching}
                  onClick={() => uploadRef.current?.click()}
                >
                  📎
                </button>
                <input
                  ref={uploadRef}
                  type="file"
                  multiple
                  hidden
                  accept=".pdf,.docx,.txt,.md"
                  onChange={(e) => {
                    uploadFiles([...(e.target.files ?? [])]);
                    e.target.value = "";
                  }}
                />
                <textarea
                  value={input}
                  placeholder={attaching ? "Parsing documents…" : "Message (Enter to send, Shift+Enter for a new line)"}
                  rows={Math.min(8, Math.max(1, input.split("\n").length))}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                      e.preventDefault();
                      send();
                    }
                  }}
                />
                {pending ? (
                  <button className="btn" onClick={() => abortRef.current?.abort()}>
                    Stop
                  </button>
                ) : (
                  <button className="btn primary" disabled={!input.trim() || attaching} onClick={send}>
                    Send
                  </button>
                )}
              </div>
            </div>
          </>
        )}
        {dragging && <div className="drop">Drop PDF / DOCX / TXT / MD files to attach</div>}
      </main>

      {source && (
        <SourcePanel target={source} doc={docs[source.docId]} onClose={() => setSource(null)} />
      )}
      {filesTarget && !source && (
        <FilePanel
          busy={attaching}
          onAttach={onFilesPicked}
          onClose={() => setFilesTarget(null)}
          onOpenSettings={() => setShowSettings(true)}
          projectId={project?.id}
          projectRoot={project?.folder}
          title={filesTarget === "context" ? "Add to project context" : project ? "Project files" : "Files"}
          actionLabel={filesTarget === "context" ? "Add to context" : "Attach to chat"}
        />
      )}
      {showSettings && settings && (
        <SettingsModal settings={settings} onClose={() => setShowSettings(false)} onSaved={setSettings} />
      )}
      {showNewProject && (
        <NewProjectModal
          onClose={() => setShowNewProject(false)}
          onCreated={(p, message) => {
            setShowNewProject(false);
            setChat(null);
            setProject(p);
            setProjectNotice(message);
            refreshProjects();
          }}
        />
      )}
    </div>
  );
}
