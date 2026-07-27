import React from "react";
import ReactDOM from "react-dom/client";
import { MotionConfig } from "motion/react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth } from "./routes/RequireAuth";
import { MarketingShell } from "./shells/MarketingShell";
import { AuthShell } from "./shells/AuthShell";
import { DemoPage } from "./pages/DemoPage";
import { Home } from "./pages/Home";
import { Login } from "./pages/Login";
import { Signup } from "./pages/Signup";
import { ResetPassword } from "./pages/ResetPassword";
import { NotFound } from "./pages/NotFound";
import "./styles.css";

// The deployed DSN arrived with a UTF-8 BOM, which Sentry rejects as an invalid
// DSN -- error reporting was silently dead in production for two weeks. Fixing
// the env var is the real fix; stripping here stops it recurring silently,
// because the tooling that writes these vars keeps emitting BOMs.
const sentryDsn = (import.meta.env.VITE_SENTRY_DSN as string | undefined)
  ?.replace(/^\uFEFF/, "")
  .trim();

// Keep preview-deploy noise out of the 5k events/month budget.
//
// Do NOT try to pattern-match the preview hash: "zoning-agent-platform" ends in
// "-platform", which is indistinguishable from a hash suffix and silently
// disabled Sentry in production. Name the production host instead, and treat
// anything off vercel.app as production too so a custom domain still reports.
const host = window.location.hostname;
const isProductionHost =
  host === "zoning-agent-platform.vercel.app" ||
  !/(^localhost$|^127\.|\.vercel\.app$)/i.test(host);

if (sentryDsn && import.meta.env.PROD && isProductionHost) {
  import("@sentry/react").then(({ init }) => {
    init({
      dsn: sentryDsn,
      environment: "production",
      // ponytail: errors only. Tracing spans bill against a separate and much
      // smaller free-tier quota, and there is not enough traffic yet for the
      // performance data to be worth the budget. Re-add
      // browserTracingIntegration when the plan or the traffic justifies it.
      tracesSampleRate: 0,
      sendDefaultPii: false,
      // On a 5k events/month budget, noise is what hides the one real error.
      ignoreErrors: [
        "ResizeObserver loop limit exceeded",
        "ResizeObserver loop completed with undelivered notifications",
        "Non-Error promise rejection captured",
        /^AbortError/,
        /^NetworkError/,
        "Failed to fetch",
      ],
      denyUrls: [/extensions\//i, /^chrome-extension:\/\//i, /^moz-extension:\/\//i],
    });
  });
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route element={<MarketingShell />}>
              <Route index element={<Home />} />
            </Route>

            <Route element={<AuthShell />}>
              <Route path="login" element={<Login />} />
              <Route path="signup" element={<Signup />} />
              <Route path="reset-password" element={<ResetPassword />} />
            </Route>

            <Route
              path="review"
              element={
                <RequireAuth>
                  <App />
                </RequireAuth>
              }
            />
            <Route
              path="reviews"
              element={
                <RequireAuth>
                  <App />
                </RequireAuth>
              }
            />
            <Route
              path="reviews/:projectId"
              element={
                <RequireAuth>
                  <App />
                </RequireAuth>
              }
            />
            <Route
              path="admin"
              element={
                <RequireAuth>
                  <App />
                </RequireAuth>
              }
            />

            {/* Logged-out demo: no RequireAuth, no shell — renders for anonymous visitors. */}
            <Route path="demo" element={<DemoPage />} />

            <Route path="app" element={<Navigate to="/review" replace />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </MotionConfig>
  </React.StrictMode>,
);
