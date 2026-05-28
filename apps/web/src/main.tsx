import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
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
    <App />
  </React.StrictMode>,
);
