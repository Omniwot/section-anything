export const usd = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : v === 0 ? "$0" : v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`;

export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

export const num = (v: number | null | undefined) => (v === null || v === undefined ? "—" : v.toLocaleString());

export const secs = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : v < 60 ? `${v.toFixed(1)}s` : `${Math.floor(v / 60)}m ${Math.round(v % 60)}s`;

const FLAG_TEXT: Record<string, string> = {
  start_marker_not_found: "Start marker not found in the text; placed by line number",
  start_marker_fuzzy: "Start marker matched approximately",
  end_marker_not_found: "End marker not found in the text",
  end_mismatch: "End marker disagrees with the next section's start",
  title_not_in_text: "Title doesn't appear at the section start",
};
export const flagText = (f: string) => FLAG_TEXT[f] ?? f;
