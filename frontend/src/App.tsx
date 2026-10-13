import { type FormEvent, useEffect, useState } from "react";

import { ApiError, API_URL, api, getToken, setToken, type Catalog, type DocumentInfo, type UsageInfo } from "./api";
import Library from "./components/Library";
import Workspace from "./components/Workspace";
import { usd } from "./format";
import "./App.css";

function BetaBanner() {
  return (
    <div className="beta" role="note">
      <strong>Beta</strong>
      <span>
        Section Anything is an experimental application for testing approaches to parsing and sectioning documents. Results can be
        wrong; don't rely on them.
      </span>
    </div>
  );
}

function Login({ onToken }: { onToken: (t: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/api/v1/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${res.status})`);
      onToken(data.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="login" onSubmit={submit}>
      <h2>{mode === "login" ? "Sign in" : "Create an account"}</h2>
      <label>
        Email
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
      </label>
      <label>
        Password
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <button className="primary" disabled={busy}>
        {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
      </button>
      <button type="button" className="ghost" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
      </button>
    </form>
  );
}

export default function App() {
  const [token, setTok] = useState<string | null>(() => getToken());
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [doc, setDoc] = useState<DocumentInfo | null>(null);
  const [usage, setUsage] = useState<UsageInfo | null>(null);

  useEffect(() => {
    setToken(token);
    if (!token) return;
    api<Catalog>("/catalog")
      .then(setCatalog)
      .catch((e) => e instanceof ApiError && e.status === 401 && setTok(null));
  }, [token]);

  useEffect(() => {
    if (!token) return setUsage(null);
    const load = () => void api<UsageInfo>("/usage").then(setUsage).catch(() => undefined);
    load();
    const t = window.setInterval(load, 10_000);
    return () => window.clearInterval(t);
  }, [token, doc]);

  return (
    <div className="app">
      <BetaBanner />
      <header className="top">
        <h1>
          Section <span>Anything</span>
        </h1>
        {token && usage && (
          <span className="usage small muted" title="Total model cost across all your documents and runs">
            Spent {usd(usage.spent_usd)} · {usage.runs} runs · {usage.llm_calls} model calls
          </span>
        )}
        {token && (
          <button
            className="ghost"
            onClick={() => {
              setTok(null);
              setDoc(null);
            }}
          >
            Sign out
          </button>
        )}
      </header>
      <main>
        {!token && <Login onToken={setTok} />}
        {token && catalog && !doc && (
          <>
            <p className="lede">
              Upload a PDF. Pick a strategy on the slider, run it, and see each section highlighted on the page, with its cost and,
              for golden-corpus documents, its accuracy.
            </p>
            <Library catalog={catalog} onOpen={setDoc} />
          </>
        )}
        {token && catalog && doc && <Workspace doc={doc} catalog={catalog} onBack={() => setDoc(null)} />}
      </main>
    </div>
  );
}
