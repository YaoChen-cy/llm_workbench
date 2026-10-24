import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Block, Doc } from "./api";

// [D1-p3-2], [C2-b4] or [D1-p3-2, D2-b14]  ->  markdown links the renderer turns into citation chips.
const ID = String.raw`[CD]\d+-[a-z]?\d+(?:-t?\d+)?`;
const CITE_GROUP = new RegExp(String.raw`\[(${ID}(?:\s*[,;]\s*${ID})*)\]`, "gi");

/** The sentence a citation backs: text since the previous sentence end / citation / line break. */
function claimBefore(md: string) {
  const line = md.slice(md.lastIndexOf("\n") + 1).replace(CITE_GROUP, "\u0000");
  const sentences = line.split(/\u0000|(?<=[.!?])\s+(?=[A-Z*"(])/).map((s) => s.trim());
  let claim = "";
  for (let i = sentences.length - 1; i >= 0 && claim.length < 40; i--) claim = `${sentences[i]} ${claim}`;
  return claim.replace(/[*_`#>|]/g, "").replace(/^\s*([-+]|\d+\.)\s+/, "").trim().slice(0, 600);
}

function linkCitations(md: string) {
  return md.replace(CITE_GROUP, (_, group: string, offset: number) => {
    const claim = encodeURIComponent(claimBefore(md.slice(0, offset)));
    return group
      .split(/\s*[,;]\s*/)
      .map((id) => `[${id}](#cite-${id}~${claim})`)
      .join("");
  });
}

type Resolve = (id: string) => { chatDoc?: { name: string }; block?: Block; doc?: Doc };
export type OnCite = (id: string, claim: string) => void;

function Cite({ id, claim, resolve, onCite }: { id: string; claim: string; resolve: Resolve; onCite?: OnCite }) {
  const [open, setOpen] = useState(false);
  const { chatDoc, block, doc } = resolve(id);
  const label = id.split("-")[0];
  const loc = block ? (doc?.kind === "pdf" ? `p.${block.page}` : `¶${block.id?.slice(1)}`) : "?";
  const clickable = !!(block && onCite);
  return (
    <span
      className={`cite ${block ? "" : "cite-bad"} ${clickable ? "cite-click" : ""}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      tabIndex={0}
      role={clickable ? "button" : undefined}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onClick={() => clickable && onCite!(id, claim)}
      onKeyDown={(e) => clickable && (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onCite!(id, claim))}
    >
      {label} · {loc}
      {open && (
        <span className="cite-pop" role="tooltip">
          {block && chatDoc ? (
            <>
              <span className="cite-pop-head">
                {chatDoc.name} — {doc?.kind === "pdf" ? `page ${block.page}` : `block ${block.id}`}
              </span>
              {block.heading && <span className="cite-pop-sub">{block.heading}</span>}
              <span className="cite-pop-text">
                {block.text.length > 420 ? block.text.slice(0, 420) + "…" : block.text}
              </span>
              {clickable && <span className="cite-pop-sub">Click to open the source</span>}
            </>
          ) : (
            <span className="cite-pop-head">Source {id} not found in the attached documents.</span>
          )}
        </span>
      )}
    </span>
  );
}

export default function Markdown({ text, resolve, onCite }: { text: string; resolve: Resolve; onCite?: OnCite }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children }) {
            if (href?.startsWith("#cite-")) {
              const [id, claim = ""] = href.slice(6).split("~");
              return <Cite id={id} claim={decodeURIComponent(claim)} resolve={resolve} onCite={onCite} />;
            }
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {linkCitations(text)}
      </ReactMarkdown>
    </div>
  );
}
