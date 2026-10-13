export const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "section-anything_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session-only login */
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function readError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: string | { msg?: string }[] };
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  } catch {
    /* not JSON */
  }
  return `Request failed (${res.status})`;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers });
  if (!res.ok) throw new ApiError(await readError(res), res.status);
  return (await res.json()) as T;
}

export type Progress = { fraction: number; message: string } | null;

export type DocumentInfo = {
  id: number;
  filename: string;
  n_pages: number;
  n_chars: number | null;
  pages_without_text: number | null;
  status: "extracting" | "ready" | "failed";
  error: string | null;
  progress: Progress;
  has_gold: boolean;
  created_at: string;
};

export type StrategyInfo = { id: string; label: string; description: string; uses_llm: boolean };

export type Catalog = {
  strategies: StrategyInfo[];
  models: string[];
  limits: { max_pages: number; max_upload_mb: number; run_cost_cap_usd: number };
};

export type Estimate = {
  strategy: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: Record<string, number>;
};

export type Section = {
  id: number;
  number: string;
  title: string;
  title_from_text: boolean;
  level: number;
  start: number;
  end: number;
  span_end: number;
  first_line: number;
  last_line: number;
  page_start: number;
  page_end: number;
  start_marker: string;
  end_marker: string;
  end_marker_found: boolean | null;
  model_end: number | null;
  end_agrees: boolean | null;
  title_verified: boolean | null;
  flags: string[];
};

export type Metrics = {
  sections: number;
  max_depth: number;
  coverage: number;
  start_marker_exact: number | null;
  start_marker_found: number | null;
  end_marker_found: number | null;
  end_agreement: number | null;
  title_verified: number | null;
  flagged: number;
  seconds: number;
  calls: number;
  input_tokens: number;
  cached_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cost_usd: number | null;
};

export type Accuracy = {
  gold_headings: number;
  precision: number;
  recall: number;
  f1: number;
  level_agreement: number | null;
  missed?: string[];
  extra?: string[];
};

export type RunInfo = {
  id: number;
  document_id: number;
  strategy: string;
  model: string;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  metrics: Metrics | null;
  accuracy: Accuracy | null;
  progress: Progress;
  created_at: string;
  sections?: Section[];
};

/** [line index, char start, x0, y0, x1, y1] in PDF user space. */
export type LineBox = [number, number, number, number, number, number];
