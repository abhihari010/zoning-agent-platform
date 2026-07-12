import React from "react";
import ReactDOM from "react-dom/client";
import { MotionConfig } from "motion/react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth } from "./routes/RequireAuth";
import { MarketingShell } from "./shells/MarketingShell";
import { AuthShell } from "./shells/AuthShell";
import { Home } from "./pages/Home";
import { Login } from "./pages/Login";
import { Signup } from "./pages/Signup";
import { NotFound } from "./pages/NotFound";
import "./styles.css";

const sentryDsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
if (sentryDsn) {
  import("@sentry/react").then(({ init, browserTracingIntegration }) => {
    init({
      dsn: sentryDsn,
      integrations: [browserTracingIntegration()],
      tracesSampleRate: 0.1,
      sendDefaultPii: false,
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
              path="admin"
              element={
                <RequireAuth>
                  <App />
                </RequireAuth>
              }
            />

            <Route path="app" element={<Navigate to="/review" replace />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </MotionConfig>
  </React.StrictMode>,
);
