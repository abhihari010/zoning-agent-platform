import { useMemo, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { authMode } from "../api";
import { useAuth } from "../auth/AuthContext";
import { EASE } from "../lib/motion";
import { scorePassword, STRENGTH } from "../lib/password";

function safeNext(next: string | null): string {
  if (next && next.startsWith("/") && !next.startsWith("//")) {
    return next;
  }
  return "/review";
}

export function Signup() {
  const { signUp, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const reduce = useReducedMotion();
  const [params] = useSearchParams();

  const intendedAddress = params.get("address");
  const hasReviewIntent = params.get("intent") === "review";
  const postTarget = intendedAddress
    ? `/review?address=${encodeURIComponent(intendedAddress)}`
    : safeNext(params.get("next"));

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [shakeKey, setShakeKey] = useState(0);

  const score = useMemo(() => scorePassword(password), [password]);
  const meter = STRENGTH[score];
  const valid = email.trim().length > 3 && password.length >= 8 && accepted;

  if (isAuthenticated) {
    return <Navigate to={postTarget} replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setError("");
    setNotice("");
    if (password.length < 8) {
      setError("Use a password with at least 8 characters.");
      setShakeKey((k) => k + 1);
      return;
    }
    setSubmitting(true);
    const result = await signUp({ name, email, password });
    setSubmitting(false);
    if (!result.ok) {
      setError(result.message ?? "We couldn’t create your account. Try again.");
      setShakeKey((k) => k + 1);
      return;
    }
    if (result.message) {
      // Email confirmation required — no session yet.
      setNotice(result.message);
      return;
    }
    navigate(postTarget, { replace: true });
  }

  return (
    <div key={shakeKey} className={error ? "shake" : undefined}>
      {hasReviewIntent && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-spruce/30 bg-spruce/10 px-3.5 py-2.5 text-[13px] leading-5 text-spruce-bright">
          <span className="status-dot h-1.5 w-1.5 shrink-0 rounded-full bg-spruce-bright" />
          We’ll take you straight to your review after you sign up.
        </div>
      )}

      <motion.div
        initial={reduce ? false : { opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE }}
        className="rounded-xl border border-dusk-line bg-dusk-panel p-6 shadow-raised md:p-8"
      >
        <h1 className="font-display text-2xl font-bold tracking-display text-paper">
          Create your account
        </h1>
        <p className="mt-2 text-sm font-light leading-6 text-dusk-soft">
          Free while in beta. Save reviews and request new jurisdictions.
        </p>

        {authMode !== "supabase" && (
          <p className="mt-5 rounded-lg border border-dusk-line bg-dusk-raised/60 px-3 py-2.5 text-[13px] leading-5 text-dusk-soft">
            This deployment runs without sign-up. Head straight to{" "}
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
          <label className="field-label-dusk" htmlFor="signup-name">
            Name
            <input
              id="signup-name"
              className="field-dusk"
              autoComplete="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>

          <label className="field-label-dusk mt-4 block">
            Email
            <input
              id="signup-email"
              className="field-dusk"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label className="field-label-dusk mt-4 block">
            Password
            <input
              id="signup-password"
              className="field-dusk"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          <div className="mt-2 flex items-center gap-3" aria-hidden="true">
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-dusk-line">
              <div
                className={`h-full rounded-full transition-all duration-fast ease-out ${password ? meter.tone : "bg-transparent"}`}
                style={{ width: password ? meter.width : "0%" }}
              />
            </div>
            <span className="w-16 text-right font-mono text-[11px] uppercase tracking-wide text-dusk-faint">
              {password ? meter.label : ""}
            </span>
          </div>

          <label className="mt-5 flex cursor-pointer items-start gap-2.5 text-sm leading-6 text-dusk-soft">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4 shrink-0 accent-spruce"
              checked={accepted}
              onChange={(event) => setAccepted(event.target.checked)}
            />
            <span>
              I understand this tool gives educational guidance, not legal
              approval.
            </span>
          </label>

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
            disabled={!valid || submitting}
            className="btn-primary mt-6 w-full py-3"
          >
            {submitting ? "Creating account…" : "Create account"}
          </button>
        </form>
      </motion.div>

      <p className="mt-5 text-center text-sm text-dusk-soft">
        Already have an account?{" "}
        <Link
          to="/login"
          className="font-semibold text-spruce-bright hover:underline"
        >
          Log in
        </Link>
      </p>
    </div>
  );
}
