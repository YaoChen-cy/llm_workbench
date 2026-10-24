import { useEffect, useLayoutEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.js?url";
import { api, type Doc, type Located, type Rect } from "./api";
import { TypeBadge } from "./fileinfo";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export type SourceTarget = { docId: string; label: string; blockId: string; claim: string };

const pdfCache = new Map<string, Promise<PDFDocumentProxy>>();
function loadPdf(docId: string) {
  if (!pdfCache.has(docId)) {
    const p = pdfjs.getDocument(api.docFileUrl(docId)).promise;
    p.catch(() => pdfCache.delete(docId));
    pdfCache.set(docId, p);
  }
  return pdfCache.get(docId)!;
}

/** One PDF page drawn to fit the panel width, with highlight boxes on top. */
function PdfPage({
  docId,
  page,
  zoom,
  block,
  sentence,
}: {
  docId: string;
  page: number;
  zoom: number;
  block: Rect[];
  sentence: Rect[];
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(0);
  const [scale, setScale] = useState(0);
  const [error, setError] = useState("");

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(Math.floor(el.parentElement!.clientWidth - 24)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!width) return;
    let task: RenderTask | null = null;
    let cancelled = false;
    (async () => {
      try {
        const pdf = await loadPdf(docId);
        const pg = await pdf.getPage(page);
        if (cancelled) return;
        const s = (width * zoom) / pg.getViewport({ scale: 1 }).width;
        const dpr = window.devicePixelRatio || 1;
        const vp = pg.getViewport({ scale: s * dpr });
        const canvas = canvasRef.current!;
        canvas.width = vp.width;
        canvas.height = vp.height;
        canvas.style.width = `${vp.width / dpr}px`;
        canvas.style.height = `${vp.height / dpr}px`;
        task = pg.render({ canvasContext: canvas.getContext("2d")!, viewport: vp });
        await task.promise;
        if (!cancelled) {
          setScale(s);
          setError("");
        }
      } catch (e) {
        if (!cancelled && (e as Error).name !== "RenderingCancelledException") setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [docId, page, width, zoom]);

  // Bring the highlight into view once the page is drawn.
  useEffect(() => {
    if (!scale) return;
    wrapRef.current?.querySelector(".hl-sentence, .hl-block")?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [scale, page, block, sentence]);

  const pageWidth = width ? width * zoom : undefined;

  const box = (r: Rect, cls: string, i: number) => (
    <div
      key={`${cls}-${i}`}
      className={cls}
      style={{
        left: r[1] * scale - 2,
        top: r[2] * scale - 2,
        width: (r[3] - r[1]) * scale + 4,
        height: (r[4] - r[2]) * scale + 4,
      }}
    />
  );
  const onPage = (rs: Rect[]) => rs.filter((r) => r[0] === page - 1);

  return (
    <div className="pdf-page" ref={wrapRef} style={{ width: pageWidth }}>
      <canvas ref={canvasRef} />
      {scale > 0 && (
        <div className="pdf-overlay">
          {onPage(block).map((r, i) => box(r, "hl-block", i))}
          {onPage(sentence).map((r, i) => box(r, "hl-sentence", i))}
        </div>
      )}
      {error && <div className="error small">Could not render the PDF: {error}</div>}
    </div>
  );
}

/** Non-PDF documents: the text, with the cited block (and sentence) highlighted. */
function TextView({ doc, loc }: { doc: Doc; loc: Located }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelector(".tb-cited")?.scrollIntoView({ block: "center" });
  }, [loc]);
  return (
    <div className="text-view" ref={ref}>
      {doc.blocks.map((b, i) =>
        b.type === "heading" ? (
          <div key={i} className="tb-heading">
            {b.text}
          </div>
        ) : (
          <div key={i} className={`tb ${b.type === "table" ? "tb-table" : ""} ${b.id === loc.block.id ? "tb-cited" : ""}`}>
            <span className="tb-id">{b.id}</span>
            {b.id === loc.block.id ? <Marked text={b.text} spans={loc.sentence_spans} /> : b.text}
          </div>
        ),
      )}
    </div>
  );
}

function Marked({ text, spans }: { text: string; spans: [number, number][] }) {
  const parts = [];
  let at = 0;
  [...spans].sort((a, b) => a[0] - b[0]).forEach(([s, e], i) => {
    parts.push(text.slice(at, s), <mark key={i}>{text.slice(s, e)}</mark>);
    at = e;
  });
  parts.push(text.slice(at));
  return <>{parts}</>;
}

export default function SourcePanel({
  target,
  doc,
  onClose,
}: {
  target: SourceTarget;
  doc?: Doc;
  onClose: () => void;
}) {
  const [loc, setLoc] = useState<Located | null>(null);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api
      .locate(target.docId, target.blockId, target.claim)
      .then((l) => {
        setLoc(l);
        setPage(l.block.page);
      })
      .catch((e) => setError(e.message));
  }, [target]);

  const isPdf = loc?.kind === "pdf";
  const where = loc ? (isPdf ? `page ${loc.block.page}` : `block ${loc.block.id}`) : "";

  return (
    <aside className="source">
      <div className="panel-head">
        <span>
          Source <span className="cite static">{target.label}</span>
        </span>
        <button className="icon-btn" onClick={onClose} aria-label="Close source panel">
          ×
        </button>
      </div>
      {error && <div className="error small source-pad">{error}</div>}
      {loc && (
        <>
          <div className="source-meta">
            <div className="source-file">
              <TypeBadge name={loc.name} />
              <span className="fs-name" title={loc.name}>
                {loc.name}
              </span>
            </div>
            {isPdf && (
              <div className="pager">
                <button className="btn small-btn" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page">
                  ‹
                </button>
                <span className="small">
                  Page {page} / {loc.pages}
                </span>
                <button
                  className="btn small-btn"
                  disabled={page >= loc.pages}
                  onClick={() => setPage(page + 1)}
                  aria-label="Next page"
                >
                  ›
                </button>
                <span className="pager-sep" />
                <button className="btn small-btn" disabled={zoom <= 1} onClick={() => setZoom(Math.max(1, zoom - 0.5))} aria-label="Zoom out">
                  −
                </button>
                <span className="small zoom-label">{zoom === 1 ? "Fit" : `${Math.round(zoom * 100)}%`}</span>
                <button className="btn small-btn" disabled={zoom >= 3} onClick={() => setZoom(Math.min(3, zoom + 0.5))} aria-label="Zoom in">
                  +
                </button>
                {page !== loc.block.page && (
                  <button className="link small" onClick={() => setPage(loc.block.page)}>
                    Back to cited page
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="source-quote">
            <div className="muted small">
              {loc.block.heading ? `${loc.block.heading} · ` : ""}
              {where}
              {loc.block.rects.some((r) => r[0] !== loc.block.rects[0][0]) && " (continues on next page)"}
            </div>
            <div className="quote-text">
              <Marked text={loc.block.text} spans={loc.sentence_spans} />
            </div>
            {target.claim && !loc.sentences.length && loc.block.type === "paragraph" && (
              <div className="muted small">No single sentence matched the claim, so the whole paragraph is highlighted.</div>
            )}
          </div>

          <div className="source-view">
            {isPdf ? (
              <PdfPage
                docId={target.docId}
                page={page}
                zoom={zoom}
                block={loc.block.rects}
                sentence={loc.sentence_rects}
              />
            ) : doc ? (
              <TextView doc={doc} loc={loc} />
            ) : (
              <div className="muted small source-pad">Loading…</div>
            )}
          </div>
        </>
      )}
      {!loc && !error && <div className="muted small source-pad">Locating source…</div>}
    </aside>
  );
}
