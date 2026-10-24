export type Provider = {
  label: string;
  type: "ollama" | "openai";
  base_url: string;
  model: string;
  api_key?: string;
  clear_api_key?: boolean;
  has_api_key?: boolean;
  extra_headers: Record<string, string>;
  verify_ssl: boolean;
  bypass_proxy: boolean;
  context_tokens: number;
  temperature: number;
};

export type Settings = {
  active_provider: string;
  providers: Record<string, Provider>;
  allowed_folders: string[];
};

export type ChatDoc = { doc_id: string; label: string; name: string };

export type ContextInfo = {
  docs: number;
  truncated: boolean;
  history_messages: number;
  prompt_tokens_est: number;
  model?: string;
};

export type Message = {
  role: "user" | "assistant";
  content: string;
  created: number;
  model?: string;
  error?: string;
  context?: ContextInfo;
};

export type ContextEntry = { doc_id: string; label: string; name: string; source: "folder" | "upload" | "text"; path: string };

export type Project = {
  id: string;
  name: string;
  instructions: string;
  folder: string;
  created: number;
  updated: number;
  context: ContextEntry[];
  reopened?: boolean;
};

export type ProjectSummary = { id: string; name: string; folder: string; updated: number; n_context: number; missing: boolean };

export type DirListing = {
  path: string;
  parent: string | null;
  home: string;
  is_project: boolean;
  dirs: { name: string; path: string; is_project: boolean }[];
  files: { name: string; size: number; supported: boolean }[];
};

export type Chat = {
  id: string;
  project_id?: string | null;
  title: string;
  created: number;
  updated: number;
  docs: ChatDoc[];
  messages: Message[];
};

export type ChatSummary = { id: string; title: string; updated: number; n_docs: number };

export type Block = {
  id: string | null;
  type: "heading" | "paragraph" | "table";
  page: number;
  heading: string;
  text: string;
};

export type Doc = {
  id: string;
  name: string;
  kind: string;
  pages: number;
  warnings: string[];
  blocks: Block[];
};

export type DocMeta = {
  ok: boolean;
  id?: string;
  name: string;
  kind?: string;
  duplicate?: boolean;
  pages?: number;
  blocks?: number;
  tables?: number;
  warnings?: string[];
  error?: string;
};

export type FsEntry = { name: string; path: string; is_dir: boolean; size: number | null; supported: boolean };
export type FsListing = { path: string; root: string; parent: string | null; entries: FsEntry[] };
export type FsRoot = { path: string; name: string; exists: boolean };

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: body instanceof FormData || body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* not JSON */
    }
    throw new Error(msg);
  }
  return r.json();
}

export const api = {
  settings: () => req<Settings>("GET", "/api/settings"),
  saveSettings: (s: Partial<Settings>) => req<Settings>("PUT", "/api/settings", s),
  testProvider: (name: string) =>
    req<{ ok: boolean; reply?: string; error?: string; seconds: number }>(
      "POST",
      `/api/settings/test?provider=${encodeURIComponent(name)}`,
    ),
  models: (name: string) => req<{ models: string[] }>("GET", `/api/models?provider=${encodeURIComponent(name)}`),

  roots: () => req<FsRoot[]>("GET", "/api/fs/roots"),
  list: (path: string, projectId?: string) =>
    req<FsListing>(
      "GET",
      `/api/fs/list?path=${encodeURIComponent(path)}${projectId ? `&project_id=${projectId}` : ""}`,
    ),
  dirs: (path?: string) => req<DirListing>("GET", `/api/fs/dirs${path ? `?path=${encodeURIComponent(path)}` : ""}`),
  ingest: (paths: string[], projectId?: string) =>
    req<DocMeta[]>("POST", "/api/documents", { paths, project_id: projectId ?? null }),
  upload: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return req<DocMeta[]>("POST", "/api/upload", fd);
  },
  doc: (id: string) => req<Doc>("GET", `/api/documents/${id}`),

  projects: () => req<ProjectSummary[]>("GET", "/api/projects"),
  project: (id: string) => req<Project>("GET", `/api/projects/${id}`),
  createProject: (p: { name: string; folder: string; instructions: string; create_folder: boolean }) =>
    req<Project>("POST", "/api/projects", p),
  patchProject: (id: string, p: { name?: string; instructions?: string }) =>
    req<Project>("PATCH", `/api/projects/${id}`, p),
  deleteProject: (id: string) => req<{ ok: boolean }>("DELETE", `/api/projects/${id}`),
  addContextPaths: (id: string, paths: string[]) =>
    req<DocMeta[]>("POST", `/api/projects/${id}/context/paths`, { paths }),
  addContextUpload: (id: string, files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return req<DocMeta[]>("POST", `/api/projects/${id}/context/upload`, fd);
  },
  addContextText: (id: string, title: string, text: string) =>
    req<DocMeta>("POST", `/api/projects/${id}/context/text`, { title, text }),
  removeContext: (id: string, docId: string) => req<Project>("DELETE", `/api/projects/${id}/context/${docId}`),
  writeFile: (id: string, name: string, content: string, overwrite = false) =>
    req<{ ok: boolean; path: string }>("POST", `/api/projects/${id}/files`, { name, content, overwrite }),

  chats: (projectId?: string) => req<ChatSummary[]>("GET", `/api/chats${projectId ? `?project_id=${projectId}` : ""}`),
  chat: (id: string) => req<Chat>("GET", `/api/chats/${id}`),
  newChat: (projectId?: string) => req<Chat>("POST", "/api/chats", { project_id: projectId ?? null }),
  deleteChat: (id: string) => req<{ ok: boolean }>("DELETE", `/api/chats/${id}`),
  patchChat: (id: string, p: { title?: string; attach?: string[]; detach?: string[] }) =>
    req<Chat>("PATCH", `/api/chats/${id}`, p),
};

export type StreamEvent =
  | { type: "info"; data: ContextInfo }
  | { type: "token"; data: { t: string } }
  | { type: "error"; data: { message: string } }
  | { type: "done"; data: object };

/** POST a message and read the server-sent events (EventSource can't POST). */
export async function streamMessage(
  chatId: string,
  content: string,
  onEvent: (e: StreamEvent) => void,
  signal: AbortSignal,
) {
  const r = await fetch(`/api/chats/${chatId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
    signal,
  });
  if (!r.ok || !r.body) throw new Error(`${r.status} ${r.statusText}`);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const ev = /^event: (.*)$/m.exec(raw)?.[1];
      const data = /^data: (.*)$/m.exec(raw)?.[1];
      if (ev && data) onEvent({ type: ev, data: JSON.parse(data) } as StreamEvent);
    }
  }
}
