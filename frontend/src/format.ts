export const usd = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : v === 0 ? "$0" : v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`;

export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

export const num = (v: number | null | undefined) => (v === null || v === undefined ? "—" : v.toLocaleString());

export const secs = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : v < 60 ? `${v.toFixed(1)}s` : `${Math.floor(v / 60)}m ${Math.round(v % 60)}s`;

export const when = (iso: string) => new Date(iso).toLocaleString();

/** Download rows as a CSV file. Values are quoted; objects become JSON. */
export function downloadCsv(filename: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return;
  const cols = Object.keys(rows[0]);
  const cell = (v: unknown) => {
    const s = v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
    return `"${s.replace(/"/g, '""')}"`;
  };
  const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => cell(r[c])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const FLAG_TEXT: Record<string, string> = {
  start_marker_not_found: "Start marker not found in the text; placed by line number",
  start_marker_fuzzy: "Start marker matched approximately",
  end_marker_not_found: "End marker not found in the text",
  end_mismatch: "End marker disagrees with the next section's start",
  title_not_in_text: "Title doesn't appear at the section start",
};
export const flagText = (f: string) => FLAG_TEXT[f] ?? f;
