import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { authMode } from "../api";
import { useAuth } from "../auth/AuthContext";

/** Only allow same-origin absolute paths as a redirect target (no open redirects). */
function safeNext(next: string | null): string {
  if (next && next.startsWith("/") && !next.startsWith("//")) {
    return next;
  }
  return "/review";
}

export function Login() {
  const { signIn, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [shakeKey, setShakeKey] = useState(0);

  if (isAuthenticated) {
    return <Navigate to={next} replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setError("");
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      setShakeKey((k) => k + 1);
      return;
    }
    setSubmitting(true);
    const result = await signIn({ email, password });
    setSubmitting(false);
    if (!result.ok) {
      setError(
        result.message?.toLowerCase().includes("invalid")
          ? "That email and password don’t match."
          : result.message ?? "We couldn’t sign you in. Try again.",
      );
      setShakeKey((k) => k + 1);
      return;
    }
    navigate(next, { replace: true });
  }

  return (
    <div key={shakeKey} className={error ? "shake" : undefined}>
      <div className="rise rounded-sm border border-dusk-line bg-dusk-panel p-6 shadow-[0_24px_70px_-44px_rgba(0,0,0,0.8),inset_0_1px_0_rgba(255,242,224,0.05)] md:p-8">
        <h1 className="font-display text-2xl font-bold tracking-[-0.02em] text-paper">
          Log in to Zoning Review
        </h1>
        <p className="mt-1.5 text-sm leading-6 text-dusk-soft">
          Reopen saved reviews and request coverage for new jurisdictions.
        </p>

        {authMode !== "supabase" && (
          <p className="mt-5 rounded-sm border border-dusk-line bg-dusk-raised/60 px-3 py-2.5 text-[13px] leading-5 text-dusk-soft">
            This deployment runs without sign-in. Head straight to{" "}
            <Link to="/review" className="font-medium text-amber hover:underline">
              the review tool
            </Link>
            .
          </p>
        )}

        <form onSubmit={onSubmit} className="mt-6" noValidate>
          <label className="field-label-dusk" htmlFor="login-email">
            Email
            <input
              id="login-email"
              className="field-dusk"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <div className="mt-4">
            <div className="flex items-baseline justify-between">
              <label className="field-label-dusk" htmlFor="login-password">
                Password
              </label>
              <button
                type="button"
                onClick={() => setError("Password reset isn’t available yet — contact the operator.")}
                className="text-[13px] font-medium text-dusk-faint transition-colors duration-fast hover:text-dusk-soft"
              >
                Forgot password?
              </button>
            </div>
            <input
              id="login-password"
              className="field-dusk"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>

          {error && (
            <p className="mt-4 rounded-sm border border-verdict-stop/40 bg-verdict-stop/15 px-3 py-2.5 text-sm leading-5 text-[#F0A895]">
              {error}
            </p>
          )}

          <button type="submit" disabled={submitting} className="btn-primary mt-6 w-full py-3">
            {submitting ? "Logging in…" : "Log in"}
          </button>
        </form>
      </div>

      <p className="mt-5 text-center text-sm text-dusk-soft">
        New here?{" "}
        <Link
          to={`/signup${params.get("next") ? `?next=${encodeURIComponent(params.get("next") ?? "")}` : ""}`}
          className="font-semibold text-amber hover:underline"
        >
          Create an account
        </Link>
      </p>
    </div>
  );
}
