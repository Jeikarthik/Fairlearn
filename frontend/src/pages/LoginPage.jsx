import { useState } from "react";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const { login, register, loading } = useAuth();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, fullName, orgName);
      }
    } catch (err) {
      setError(err.message || "Something went wrong");
    }
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="brand-mark">FL</div>
          <div>
            <p className="eyebrow">Accessible fairness operations</p>
            <h1>FairLens</h1>
          </div>
        </div>

        <div className="auth-toggle">
          <button
            type="button"
            className={`auth-toggle-btn${mode === "login" ? " auth-toggle-active" : ""}`}
            onClick={() => { setMode("login"); setError(""); }}
          >
            Sign in
          </button>
          <button
            type="button"
            className={`auth-toggle-btn${mode === "register" ? " auth-toggle-active" : ""}`}
            onClick={() => { setMode("register"); setError(""); }}
          >
            Create account
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === "register" && (
            <>
              <div className="field-block">
                <label className="field-label" htmlFor="auth-fullname">Full name</label>
                <input
                  id="auth-fullname"
                  className="text-input"
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Jane Doe"
                />
              </div>
              <div className="field-block">
                <label className="field-label" htmlFor="auth-org">Organization</label>
                <input
                  id="auth-org"
                  className="text-input"
                  type="text"
                  required
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  placeholder="Acme Corp"
                />
              </div>
            </>
          )}

          <div className="field-block">
            <label className="field-label" htmlFor="auth-email">Email</label>
            <input
              id="auth-email"
              className="text-input"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              autoComplete="email"
            />
          </div>

          <div className="field-block">
            <label className="field-label" htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              className="text-input"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </div>

          {error && <div className="auth-error">{error}</div>}

          <button className="button-primary auth-submit" type="submit" disabled={loading}>
            {loading
              ? "Please wait..."
              : mode === "login"
                ? "Sign in"
                : "Create account"
            }
          </button>
        </form>

        <p className="auth-footer">
          {mode === "login"
            ? "Don't have an account? "
            : "Already have an account? "}
          <button
            type="button"
            className="auth-switch"
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}
          >
            {mode === "login" ? "Create one" : "Sign in"}
          </button>
        </p>
      </div>
    </div>
  );
}
