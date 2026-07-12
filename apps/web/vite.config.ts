import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

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
