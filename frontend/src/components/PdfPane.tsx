import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type Ref } from "react";
import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist";

import { API_URL, api, getToken, type LineBox, type Section } from "../api";
import { sectionColor } from "../colors";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

export type PdfPaneHandle = { scrollToSection: (s: Section) => void };

type Props = {
  docId: number;
  sections: Section[];
  activeId: number | null;
  onSelect: (id: number) => void;
  handleRef: Ref<PdfPaneHandle>;
};

/** PDF user-space box → viewport box [x1, y1, x2, y2] (handles rotation and crop). */
function toViewportRect(vp: pdfjs.PageViewport, x0: number, y0: number, x1: number, y1: number): number[] {
  const [ax, ay] = vp.convertToViewportPoint(x0, y0);
  const [bx, by] = vp.convertToViewportPoint(x1, y1);
  return [ax, ay, bx, by];
}

/** Index of the last section starting at or before `pos`, or -1 (preamble). */
function sectionIndexAt(starts: number[], pos: number): number {
  let lo = 0;
  let hi = starts.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (starts[mid] <= pos) {
      ans = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return ans;
}

export default function PdfPane({ docId, sections, activeId, onSelect, handleRef }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState("");
  const [width, setWidth] = useState(800);
  const [baseSize, setBaseSize] = useState<{ w: number; h: number }>({ w: 612, h: 792 });
  const linesCache = useRef(new Map<number, Promise<LineBox[]>>());
  const pageEls = useRef(new Map<number, HTMLDivElement>());

  useEffect(() => {
    let cancelled = false;
    linesCache.current.clear();
    const task = pdfjs.getDocument({
      url: `${API_URL}/api/v1/documents/${docId}/file`,
      httpHeaders: { Authorization: `Bearer ${getToken() ?? ""}` },
    });
    task.promise
      .then(async (doc) => {
        if (cancelled) return;
        const first = await doc.getPage(1);
        const vp = first.getViewport({ scale: 1 });
        setBaseSize({ w: vp.width, h: vp.height });
        setPdf(doc);
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : "Could not load PDF"));
    return () => {
      cancelled = true;
      void task.destroy();
    };
  }, [docId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(320, entry.contentRect.width - 32)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const scale = width / baseSize.w;

  const getLines = useCallback(
    (page: number) => {
      let p = linesCache.current.get(page);
      if (!p) {
        p = api<LineBox[]>(`/documents/${docId}/lines?page=${page}`).catch(() => []);
        linesCache.current.set(page, p);
      }
      return p;
    },
    [docId],
  );

  const starts = useMemo(() => sections.map((s) => s.start), [sections]);
  const active = sections.find((s) => s.id === activeId) ?? null;

  useImperativeHandle(
    handleRef,
    () => ({
      async scrollToSection(s: Section) {
        const container = scrollRef.current;
        const pageEl = pageEls.current.get(s.page_start);
        if (!container || !pageEl || !pdf) return;
        container.scrollTo({ top: pageEl.offsetTop - 12, behavior: "smooth" });
        const [lines, page] = await Promise.all([getLines(s.page_start), pdf.getPage(s.page_start)]);
        const line = lines.find((l) => l[0] === s.first_line);
        if (!line) return;
        const vp = page.getViewport({ scale });
        const [, y1, , y2] = toViewportRect(vp, line[2], line[3], line[4], line[5]);
        container.scrollTo({ top: pageEl.offsetTop + Math.min(y1, y2) - 48, behavior: "smooth" });
      },
    }),
    [pdf, getLines, scale],
  );

  if (error) return <div className="pane-message">Couldn't load the PDF: {error}</div>;

  return (
    <div className="pdf-scroll" ref={scrollRef}>
      {!pdf && <div className="pane-message">Loading PDF…</div>}
      {pdf &&
        Array.from({ length: pdf.numPages }, (_, i) => i + 1).map((n) => (
          <PageView
            key={n}
            n={n}
            pdf={pdf}
            scale={scale}
            placeholder={{ w: width, h: baseSize.h * scale }}
            root={scrollRef}
            getLines={getLines}
            sections={sections}
            starts={starts}
            active={active}
            onSelect={onSelect}
            registerEl={(el) => (el ? pageEls.current.set(n, el) : pageEls.current.delete(n))}
          />
        ))}
    </div>
  );
}

type PageProps = {
  n: number;
  pdf: PDFDocumentProxy;
  scale: number;
  placeholder: { w: number; h: number };
  root: React.RefObject<HTMLDivElement | null>;
  getLines: (page: number) => Promise<LineBox[]>;
  sections: Section[];
  starts: number[];
  active: Section | null;
  onSelect: (id: number) => void;
  registerEl: (el: HTMLDivElement | null) => void;
};

function PageView({ n, pdf, scale, placeholder, root, getLines, sections, starts, active, onSelect, registerEl }: PageProps) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);
  const [page, setPage] = useState<PDFPageProxy | null>(null);
  const [lines, setLines] = useState<LineBox[]>([]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), {
      root: root.current,
      rootMargin: "1200px 0px",
    });
    io.observe(el);
    return () => io.disconnect();
  }, [root]);

  // Page and line boxes load independently: tying them to one effect let the
  // page's state update cancel the lines request before it landed.
  useEffect(() => {
    if (!visible || page) return;
    let live = true;
    void pdf.getPage(n).then((p) => live && setPage(p));
    return () => {
      live = false;
    };
  }, [visible, page, pdf, n]);

  useEffect(() => {
    if (!visible) return;
    let live = true;
    void getLines(n).then((l) => live && setLines(l));
    return () => {
      live = false;
    };
  }, [visible, n, getLines]);

  const viewport = useMemo(() => page?.getViewport({ scale }) ?? null, [page, scale]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!visible || !page || !viewport || !canvas) return;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.floor(viewport.width * ratio);
    canvas.height = Math.floor(viewport.height * ratio);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let task: RenderTask | null = page.render({
      canvas,
      canvasContext: ctx,
      viewport,
      transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
    });
    task.promise.catch(() => undefined).finally(() => (task = null));
    return () => task?.cancel();
  }, [visible, page, viewport]);

  const boxes = useMemo(() => {
    if (!viewport) return [];
    return lines.map((l) => {
      const [x1, y1, x2, y2] = toViewportRect(viewport, l[2], l[3], l[4], l[5]);
      const idx = sectionIndexAt(starts, l[1]);
      return {
        i: l[0],
        start: l[1],
        left: Math.min(x1, x2),
        top: Math.min(y1, y2),
        width: Math.abs(x2 - x1),
        height: Math.abs(y2 - y1),
        section: idx >= 0 ? sections[idx] : null,
      };
    });
  }, [lines, viewport, starts, sections]);

  const w = viewport?.width ?? placeholder.w;
  const h = viewport?.height ?? placeholder.h;

  return (
    <div
      className="pdf-page"
      ref={(el) => {
        wrapRef.current = el;
        registerEl(el);
      }}
      style={{ width: w, height: h }}
      data-page={n}
    >
      {visible && <canvas ref={canvasRef} style={{ width: w, height: h }} />}
      {visible &&
        boxes.map((b) => {
          if (!b.section) return null;
          const s = b.section;
          const inActive = active !== null && b.start >= active.start && b.start < active.span_end;
          const trailing = s.model_end !== null && b.start >= s.model_end;
          const isStart = b.i === s.first_line;
          return (
            <div
              key={b.i}
              className={`hl${inActive ? " hl-active" : ""}${trailing ? " hl-trailing" : ""}${isStart ? " hl-start" : ""}`}
              style={{
                left: b.left - 3,
                top: b.top - 1,
                width: b.width + 6,
                height: b.height + 2,
                ["--c" as string]: sectionColor(s.id),
              }}
              title={`${s.number ? s.number + " " : ""}${s.title}`}
              onClick={() => onSelect(s.id)}
            >
              {isStart && <span className="hl-tag">{s.number || "§"}</span>}
            </div>
          );
        })}
      <span className="page-num">{n}</span>
    </div>
  );
}
