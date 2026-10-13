import { useEffect, useMemo, useRef, useState } from "react";

import type { Section } from "../api";
import { sectionColor } from "../colors";
import { flagText } from "../format";

type Props = {
  sections: Section[];
  activeId: number | null;
  onSelect: (s: Section) => void;
};

export default function SectionList({ sections, activeId, onSelect }: Props) {
  const [maxDepth, setMaxDepth] = useState(8);
  const [query, setQuery] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const listRef = useRef<HTMLOListElement>(null);
  const depth = useMemo(() => Math.max(1, ...sections.map((s) => s.level)), [sections]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sections.filter(
      (s) =>
        s.level <= maxDepth &&
        (!flaggedOnly || s.flags.length > 0) &&
        (!q || `${s.number} ${s.title}`.toLowerCase().includes(q)),
    );
  }, [sections, maxDepth, query, flaggedOnly]);

  useEffect(() => {
    if (activeId === null) return;
    listRef.current?.querySelector(`[data-sid="${activeId}"]`)?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  if (!sections.length) return <p className="muted pad">No sections yet. Pick a strategy and run it.</p>;

  return (
    <div className="section-list">
      <div className="section-tools">
        <input
          type="search"
          placeholder="Filter sections"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Filter sections"
        />
        <label className="depth">
          Depth
          <select value={Math.min(maxDepth, depth)} onChange={(e) => setMaxDepth(Number(e.target.value))}>
            {Array.from({ length: depth }, (_, i) => i + 1).map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={flaggedOnly} onChange={(e) => setFlaggedOnly(e.target.checked)} />
          Flagged
        </label>
      </div>
      <ol className="sections" ref={listRef}>
        {shown.map((s) => (
          <li key={s.id} data-sid={s.id}>
            <button
              className={`section-row${s.id === activeId ? " active" : ""}`}
              style={{ paddingLeft: 10 + (s.level - 1) * 16, ["--c" as string]: sectionColor(s.id) }}
              onClick={() => onSelect(s)}
            >
              <span className="swatch" aria-hidden />
              <span className="section-text">
                <span className="section-title">
                  {s.number && <span className="section-num">{s.number}</span>}
                  {s.title || <em>Untitled</em>}
                  {!s.title_from_text && <span className="badge" title="No printed heading; title written by the model">inferred</span>}
                </span>
                <span className="section-meta">
                  {s.page_start === s.page_end ? `p. ${s.page_start}` : `pp. ${s.page_start}–${s.page_end}`}
                  {s.flags.length > 0 && (
                    <span className="flag" title={s.flags.map(flagText).join("\n")}>
                      ⚠ {s.flags.length}
                    </span>
                  )}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
