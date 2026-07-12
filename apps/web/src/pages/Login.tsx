import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { authMode } from "../api";
import { useAuth } from "../auth/AuthContext";
import { EASE } from "../lib/motion";

/** Only allow same-origin absolute paths as a redirect target (no open redirects). */
function safeNext(next: string | null): string {
  if (next && next.startsWith("/") && !next.startsWith("//")) {
    return next;
  }
  return "/review";
}

export function Login() {
  const { signIn, requestPasswordReset, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const reduce = useReducedMotion();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));

  const [mode, setMode] = useState<"login" | "forgot">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
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
    setNotice("");

    if (mode === "forgot") {
      if (!email.trim()) {
        setError("Enter your email address.");
        setShakeKey((k) => k + 1);
        return;
      }
      setSubmitting(true);
      const result = await requestPasswordReset(email);
      setSubmitting(false);
      if (!result.ok) {
        setError(result.message ?? "We couldn’t send the reset link. Try again.");
        setShakeKey((k) => k + 1);
        return;
      }
      // Same message whether or not the account exists — don't leak existence.
      setNotice("If that address has an account, a reset link is on its way.");
      return;
    }

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

  function switchMode(nextMode: "login" | "forgot") {
    setMode(nextMode);
    setError("");
    setNotice("");
  }

  return (
    <div key={shakeKey} className={error ? "shake" : undefined}>
      <motion.div
        initial={reduce ? false : { opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE }}
        className="rounded-xl border border-dusk-line bg-dusk-panel p-6 shadow-raised md:p-8"
      >
        <h1 className="font-display text-2xl font-bold tracking-display text-paper">
          {mode === "forgot" ? "Reset your password" : "Log in to Zoning Review"}
        </h1>
        <p className="mt-2 text-sm font-light leading-6 text-dusk-soft">
          {mode === "forgot"
            ? "Enter your email and we’ll send you a link to set a new password."
            : "Reopen saved reviews and request coverage for new jurisdictions."}
        </p>

        {authMode !== "supabase" && (
          <p className="mt-5 rounded-lg border border-dusk-line bg-dusk-raised/60 px-3 py-2.5 text-[13px] leading-5 text-dusk-soft">
            This deployment runs without sign-in. Head straight to{" "}
            <Link
              to="/review"
              className="font-medium text-spruce-bright hover:underline"
            >
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

          {mode === "login" && (
            <div className="mt-4">
              <div className="flex items-baseline justify-between">
                <label className="field-label-dusk" htmlFor="login-password">
                  Password
                </label>
                <button
                  type="button"
                  onClick={() => switchMode("forgot")}
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
          )}

          {error && (
            <p className="mt-4 rounded-lg border border-verdict-stop/40 bg-verdict-stop/12 px-3 py-2.5 text-sm leading-5 text-verdict-stop">
              {error}
            </p>
          )}
          {notice && (
            <p className="mt-4 rounded-lg border border-spruce/25 bg-spruce/10 px-3 py-2.5 text-sm leading-5 text-dusk-soft">
              {notice}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="btn-primary mt-6 w-full py-3"
          >
            {mode === "forgot"
              ? submitting
                ? "Sending link…"
                : "Send reset link"
              : submitting
                ? "Logging in…"
                : "Log in"}
          </button>
        </form>
      </motion.div>

      {mode === "forgot" ? (
        <p className="mt-5 text-center text-sm text-dusk-soft">
          Remembered it?{" "}
          <button
            type="button"
            onClick={() => switchMode("login")}
            className="font-semibold text-spruce-bright hover:underline"
          >
            Back to log in
          </button>
        </p>
      ) : (
        <p className="mt-5 text-center text-sm text-dusk-soft">
          New here?{" "}
          <Link
            to={`/signup${params.get("next") ? `?next=${encodeURIComponent(params.get("next") ?? "")}` : ""}`}
            className="font-semibold text-spruce-bright hover:underline"
          >
            Create an account
          </Link>
        </p>
      )}
    </div>
  );
}
