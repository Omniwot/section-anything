import { useCallback, useEffect, useRef, useState } from "react";

import { api, type Catalog, type DocumentInfo } from "../api";

type Props = { catalog: Catalog; onOpen: (d: DocumentInfo) => void };

export default function Library({ catalog, onOpen }: Props) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => setDocs(await api<DocumentInfo[]>("/documents")), []);

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

  useEffect(() => {
    if (!docs.some((d) => d.status === "extracting")) return;
    const t = window.setInterval(() => void refresh().catch(() => undefined), 1200);
    return () => window.clearInterval(t);
  }, [docs, refresh]);

  async function upload(file: File) {
    setError("");
    if (file.size > catalog.limits.max_upload_mb * 1024 * 1024) {
      setError(`That file is over ${catalog.limits.max_upload_mb} MB.`);
      return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api<DocumentInfo>("/documents", { method: "POST", body: fd });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="library">
      <div
        className={`dropzone${drag ? " drag" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          const f = e.dataTransfer.files[0];
          if (f) void upload(f);
        }}
        onClick={() => input.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
      >
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
            e.target.value = "";
          }}
        />
        <strong>{uploading ? "Uploading…" : "Drop a PDF here, or click to choose one"}</strong>
        <span className="muted small">
          Up to {catalog.limits.max_pages} pages and {catalog.limits.max_upload_mb} MB. Text is sent to OpenAI only when you run an LLM
          strategy.
        </span>
      </div>
      {error && <p className="error">{error}</p>}

      {docs.length > 0 && (
        <ul className="docs">
          {docs.map((d) => (
            <li key={d.id}>
              <button disabled={d.status !== "ready"} onClick={() => onOpen(d)}>
                <span className="doc-name">{d.filename}</span>
                <span className="muted small">
                  {d.status === "ready" &&
                    `${d.n_pages} pages${d.pages_without_text ? ` · ${d.pages_without_text} without text` : ""}${d.has_gold ? " · golden corpus" : ""}`}
                  {d.status === "extracting" &&
                    (d.progress ? `${d.progress.message} (${Math.round(d.progress.fraction * 100)}%)` : "Reading…")}
                  {d.status === "failed" && <span className="err">{d.error}</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
