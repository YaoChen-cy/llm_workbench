import type { DocMeta } from "./api";

const TYPES: Record<string, string> = {
  pdf: "PDF",
  docx: "Word",
  doc: "Word 97",
  txt: "Text",
  md: "Markdown",
  xlsx: "Excel",
  xls: "Excel",
  csv: "CSV",
  pptx: "PowerPoint",
  png: "Image",
  jpg: "Image",
  jpeg: "Image",
  msg: "Outlook",
  zip: "Archive",
};

export const ACCEPT = ".pdf,.docx,.txt,.md";

export function ext(name: string) {
  const i = name.lastIndexOf(".");
  return i > 0 ? name.slice(i + 1).toLowerCase() : "";
}

export function fileType(name: string) {
  const e = ext(name);
  return TYPES[e] ?? (e ? e.toUpperCase() : "File");
}

export function isSupported(name: string) {
  return ["pdf", "docx", "txt", "md"].includes(ext(name));
}

export function fileSize(n: number | null | undefined) {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1 << 20) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1 << 20)).toFixed(1)} MB`;
}

/** "memo.pdf (PDF, 3 pages)" */
export function describe(m: DocMeta) {
  const pages = m.kind === "pdf" && m.pages ? `, ${m.pages} page${m.pages === 1 ? "" : "s"}` : "";
  return `${m.name} (${fileType(m.name)}${pages})`;
}

/** One-line report of an upload/add result: successes, duplicates, failures and parse warnings. */
export function report(metas: DocMeta[], verb = "Added") {
  const ok = metas.filter((m) => m.ok && !m.duplicate);
  const dup = metas.filter((m) => m.ok && m.duplicate);
  const bad = metas.filter((m) => !m.ok);
  const lines: string[] = [];
  if (ok.length) lines.push(`✓ ${verb} ${ok.length} file${ok.length === 1 ? "" : "s"}: ${ok.map(describe).join(", ")}`);
  if (dup.length) lines.push(`Already in context: ${dup.map((m) => m.name).join(", ")}`);
  bad.forEach((m) => lines.push(`✗ Could not add ${m.name}: ${m.error}`));
  metas.forEach((m) => (m.warnings ?? []).forEach((w) => lines.push(`⚠ ${m.name}: ${w}`)));
  return lines.join("\n");
}

export function TypeBadge({ name }: { name: string }) {
  return <span className={`type-badge t-${ext(name) || "file"}`}>{fileType(name)}</span>;
}
