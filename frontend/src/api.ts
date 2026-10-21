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

export type Progress = { fraction: number; message: string; cost_usd?: number; calls?: number } | null;

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
  extractor_version: number | null;
  spent_usd: number;
  llm_calls: number;
  created_at: string;
};

export type StrategyInfo = { id: string; label: string; description: string; uses_llm: boolean; default_model?: string | null };

export type Catalog = {
  strategies: StrategyInfo[];
  /** Server-side (paid) models this account may use; empty when paid models are not enabled for it. */
  models: string[];
  paid_models: boolean;
  /** Runs can use the visitor's own model: model id `${prefix}<name>`, for these strategies. */
  local_models: { prefix: string; strategies: string[] };
  limits: { max_pages: number; max_upload_mb: number; run_cost_cap_usd: number };
};

export type BridgeNext = { status: string; request: import("./localLlm").BridgeRequest | null };

export function bridgeNext(runId: number, signal?: AbortSignal) {
  return api<BridgeNext>(`/runs/${runId}/bridge/next?wait=10`, { signal });
}

export function bridgeReply(runId: number, requestId: string, body: { content?: string; error?: string }) {
  return api<{ ok: boolean }>(`/runs/${runId}/bridge/${requestId}`, { method: "POST", body: JSON.stringify(body) });
}

export type Estimate = {
  strategy: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: Record<string, number>;
  /** Estimate is over the per-run cost cap: the run would be refused. */
  blocked: Record<string, boolean>;
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
  sections?: number;
  max_depth?: number;
  coverage?: number;
  start_marker_exact?: number | null;
  start_marker_found?: number | null;
  end_marker_found?: number | null;
  end_agreement?: number | null;
  title_verified?: number | null;
  flagged?: number;
  seconds?: number;
  calls: number;
  input_tokens: number;
  cached_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cost_usd: number | null;
  cost_by_step?: Record<string, number>;
  /** Set on failed runs: totals up to the point the run stopped. */
  partial?: boolean;
};

export type RunEstimate = { calls: number; input_tokens: number; output_tokens: number; cost_usd: number };

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
  estimate: RunEstimate | null;
  extractor_version: number | null;
  /** Sections refer to an older extraction whose text differs from the current one. */
  stale: boolean;
  accuracy: Accuracy | null;
  progress: Progress;
  created_at: string;
  sections?: Section[];
};

export type LlmCallInfo = {
  id: number;
  created_at: string;
  run_id: number;
  seq: number;
  step: string;
  attempt: number;
  model: string;
  reasoning_effort: string | null;
  status: "ok" | "refused" | "invalid" | "error";
  error: string | null;
  input_tokens: number;
  cached_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cost_usd: number | null;
  latency_ms: number;
  prompt_sha256: string;
  prompt_chars: number;
  images: number;
};

export type AuditEventInfo = {
  id: number;
  created_at: string;
  kind: string;
  document_id: number | null;
  run_id: number | null;
  details: Record<string, unknown>;
};

export type UsageInfo = { spent_usd: number; llm_calls: number; runs: number };

/**
 * [line index, char start, char end, x0, y0, x1, y1, words] in PDF user space.
 * `words` is flat [start, end, x0, x1, ...] with char offsets relative to the line start.
 */
export type LineBox = [number, number, number, number, number, number, number, number[]];
