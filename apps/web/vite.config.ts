import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// OG tags need absolute URLs, so index.html interpolates %VITE_SITE_URL%. Set it
// in the host's env when the origin changes (custom domain) rather than editing
// the meta tags; this default keeps local and preview builds resolvable.
process.env.VITE_SITE_URL ??= "https://zoning-agent-platform.vercel.app";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  build: {
    rollupOptions: {
      output: {
        // Split the heavy marketing-motion libs out of the app entry so routes
        // that don't need them aren't blocked on a single ~790kB chunk.
        manualChunks: {
          motion: ["gsap", "lenis", "motion"],
        },
      },
    },
  },
});
