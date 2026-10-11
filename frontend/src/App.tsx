
import { FormEvent, useEffect, useMemo, useState } from "react";

import "./App.css";

const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

type GenerateResponse = {
  result: string;
  job_id: number;
};

type ApiError = {
  detail?: string | { msg?: string }[];
};

async function readError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as ApiError;
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    }
  } catch {
    /* ignore */
  }
  return `Request failed (${res.status})`;
}


const TOKEN_KEY = "section-anything_token";

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}


export default function App() {
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState("");
  const [jobId, setJobId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setTokenState] = useState<string | null>(() => getToken());
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authLoading, setAuthLoading] = useState(false);

  useEffect(() => {
    setToken(token);
  }, [token]);

  const authed = useMemo(() => Boolean(token), [token]);

  async function onAuth(e: FormEvent) {
    e.preventDefault();
    setAuthLoading(true);
    setError("");
    try {
      const path = authMode === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register";
      const res = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) throw new Error(await readError(res));
      const data = (await res.json()) as { access_token: string };
      setTokenState(data.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auth failed");
    } finally {
      setAuthLoading(false);
    }
  }


  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult("");
    setJobId(null);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 120_000);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };

      if (!token) throw new Error("Sign in first");
      headers.Authorization = `Bearer ${token}`;

      const res = await fetch(`${API_URL}/api/v1/generate`, {
        method: "POST",
        headers,
        body: JSON.stringify({ prompt }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(await readError(res));
      const data = (await res.json()) as GenerateResponse;
      setResult(data.result);
      setJobId(data.job_id);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setError("Request timed out");
      } else {
        setError(err instanceof Error ? err.message : "Request failed");
      }
    } finally {
      window.clearTimeout(timer);
      setLoading(false);
    }
  }

  return (
    <div className="shell">
      <header className="hero">
        <p className="brand">section-anything</p>
        <h1>Ask anything.</h1>
        <p className="lede">
          FastAPI + LiteLLM, with Langfuse tracing and Sentry error reporting.
        </p>
      </header>


      {!authed ? (
        <form className="panel auth" onSubmit={onAuth}>
          <div className="auth-toggle">
            <button
              type="button"
              className={authMode === "login" ? "active" : ""}
              onClick={() => setAuthMode("login")}
            >
              Sign in
            </button>
            <button
              type="button"
              className={authMode === "register" ? "active" : ""}
              onClick={() => setAuthMode("register")}
            >
              Create account
            </button>
          </div>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete={authMode === "login" ? "current-password" : "new-password"}
          />
          <button type="submit" disabled={authLoading}>
            {authLoading ? "Please wait…" : authMode === "login" ? "Sign in" : "Register"}
          </button>
        </form>
      ) : (
        <div className="session">
          <span>Signed in</span>
          <button type="button" className="ghost" onClick={() => setTokenState(null)}>
            Sign out
          </button>
        </div>
      )}


      <form className="panel" onSubmit={onSubmit}>
        <label htmlFor="prompt">Prompt</label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={5}
          placeholder="Describe what you need…"
          required
          maxLength={20000}

          disabled={!authed}

        />
        <button type="submit" disabled={loading || !authed}>
          {loading ? "Generating…" : "Generate"}
        </button>
      </form>

      {error ? <p className="error" role="alert">{error}</p> : null}
      {result ? (
        <section className="result">
          <h2>Result{jobId != null ? ` · job #${jobId}` : ""}</h2>
          <pre>{result}</pre>
        </section>
      ) : null}
    </div>
  );
}
