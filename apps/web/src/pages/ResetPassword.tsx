import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { authMode } from "../api";
import { useAuth } from "../auth/AuthContext";
import { EASE } from "../lib/motion";
import { scorePassword, STRENGTH } from "../lib/password";

/**
 * Landing page for Supabase recovery links. supabase-js consumes the token
 * from the URL and emits a PASSWORD_RECOVERY session asynchronously, so this
 * page must NOT sit behind RequireAuth — it waits for the session itself.
 */
export function ResetPassword() {
  const { authSession, updatePassword } = useAuth();
  const navigate = useNavigate();
  const reduce = useReducedMotion();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [shakeKey, setShakeKey] = useState(0);

  const score = useMemo(() => scorePassword(password), [password]);
  const meter = STRENGTH[score];
  const hasSession = Boolean(authSession);

  useEffect(() => {
    if (hasSession) {
      setTimedOut(false);
      return;
    }
    const timer = window.setTimeout(() => setTimedOut(true), 6000);
    return () => window.clearTimeout(timer);
  }, [hasSession]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setError("");
    if (password.length < 8) {
      setError("Use a password with at least 8 characters.");
      setShakeKey((k) => k + 1);
      return;
    }
    if (password !== confirm) {
      setError("Those passwords don’t match.");
      setShakeKey((k) => k + 1);
      return;
    }
    setSubmitting(true);
    const result = await updatePassword(password);
    setSubmitting(false);
    if (!result.ok) {
      setError(result.message ?? "We couldn’t update your password. Try again.");
      setShakeKey((k) => k + 1);
      return;
    }
    navigate("/review", { replace: true });
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
          Set a new password
        </h1>
        <p className="mt-2 text-sm font-light leading-6 text-dusk-soft">
          Choose a new password for your account.
        </p>

        {authMode !== "supabase" && (
          <p className="mt-5 rounded-lg border border-dusk-line bg-dusk-raised/60 px-3 py-2.5 text-[13px] leading-5 text-dusk-soft">
            This deployment runs without sign-in, so there’s no password to
            reset.
          </p>
        )}

        {authMode === "supabase" && !hasSession && !timedOut && (
          <p className="mt-5 rounded-lg border border-dusk-line bg-dusk-raised/60 px-3 py-2.5 text-[13px] leading-5 text-dusk-soft">
            Checking your reset link…
          </p>
        )}

        {authMode === "supabase" && !hasSession && timedOut && (
          <p className="mt-5 rounded-lg border border-verdict-stop/40 bg-verdict-stop/12 px-3 py-2.5 text-sm leading-5 text-verdict-stop">
            This reset link is invalid or expired.{" "}
            <Link to="/login" className="font-semibold underline">
              Request a new one
            </Link>
            .
          </p>
        )}

        {authMode === "supabase" && hasSession && (
          <form onSubmit={onSubmit} className="mt-6" noValidate>
            <label className="field-label-dusk" htmlFor="reset-password">
              New password
              <input
                id="reset-password"
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

            <label className="field-label-dusk mt-4 block">
              Confirm new password
              <input
                id="reset-password-confirm"
                className="field-dusk"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
              />
            </label>

            {error && (
              <p className="mt-4 rounded-lg border border-verdict-stop/40 bg-verdict-stop/12 px-3 py-2.5 text-sm leading-5 text-verdict-stop">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="btn-primary mt-6 w-full py-3"
            >
              {submitting ? "Saving…" : "Save new password"}
            </button>
          </form>
        )}
      </motion.div>

      <p className="mt-5 text-center text-sm text-dusk-soft">
        Remembered it?{" "}
        <Link to="/login" className="font-semibold text-spruce-bright hover:underline">
          Back to log in
        </Link>
      </p>
    </div>
  );
}
