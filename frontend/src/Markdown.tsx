import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Block, Doc } from "./api";

// [D1-p3-2], [C2-b4] or [D1-p3-2, D2-b14]  ->  markdown links the renderer turns into citation chips.
const ID = String.raw`[CD]\d+-[a-z]?\d+(?:-t?\d+)?`;
const CITE_GROUP = new RegExp(String.raw`\[(${ID}(?:\s*[,;]\s*${ID})*)\]`, "gi");

function linkCitations(md: string) {
  return md.replace(CITE_GROUP, (_, group: string) =>
    group
      .split(/\s*[,;]\s*/)
      .map((id) => `[${id}](#cite-${id})`)
      .join(""),
  );
}

type Resolve = (id: string) => { chatDoc?: { name: string }; block?: Block; doc?: Doc };

function Cite({ id, resolve }: { id: string; resolve: Resolve }) {
  const [open, setOpen] = useState(false);
  const { chatDoc, block, doc } = resolve(id);
  const label = id.split("-")[0];
  const loc = block ? (doc?.kind === "pdf" ? `p.${block.page}` : `¶${block.id?.slice(1)}`) : "?";
  return (
    <span
      className={`cite ${block ? "" : "cite-bad"}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      tabIndex={0}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
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
            </>
          ) : (
            <span className="cite-pop-head">Source {id} not found in the attached documents.</span>
          )}
        </span>
      )}
    </span>
  );
}

export default function Markdown({ text, resolve }: { text: string; resolve: Resolve }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children }) {
            if (href?.startsWith("#cite-")) return <Cite id={href.slice(6)} resolve={resolve} />;
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
