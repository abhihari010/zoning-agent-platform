/** @type {import('tailwindcss').Config} */
// "Digital plat" tokens — Warm plat palette (redesign brief v3 §2.5 Option A).
// Token names are stable across redesigns; only their values warmed up from the
// cool v2 set. Reference values:
//   paper #FAF7F0 · surface #FFFFFF · ink #241C15 · muted #6B6155
//   accent(spruce) #0F5E4E (full strength) · signal(verdict-hold) #B4540A
//   verdict-stop #8C2F1B · warm-gray borders
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#FAF7F0", // warm cream page
        sheet: "#FFFFFF", // documents on the desk
        well: "#F3EEE3", // warm recessed surface
        ink: {
          DEFAULT: "#241C15", // warm near-black
          soft: "#6B6155", // --muted, warm gray
          faint: "#938A7C", // faint warm gray (placeholders, meta)
        },
        rule: {
          DEFAULT: "#E7E0D3", // warm border ~15% ink over paper
          strong: "#D6CCBB", // warm border ~25% — hover / inputs
        },
        spruce: {
          DEFAULT: "#0F5E4E", // the single accent, full strength
          deep: "#0B4A3E",
          bright: "#12735F",
          wash: "#E6EEE9", // faintly warm spruce wash
        },
        verdict: {
          ok: "#0F5E4E",
          okwash: "#E6EEE9",
          hold: "#B4540A",
          holdwash: "#F7EDE0",
          stop: "#8C2F1B",
          stopwash: "#F6E8E2",
        },
        // Dusk palette — marketing-only dark treatment (brief §2.5 Option B).
        // Warm charcoal, never neutral gray, so it reads sunlit-at-night.
        dusk: {
          DEFAULT: "#1A1613", // page
          deep: "#120F0B", // footer / contrast bands
          panel: "#221B14", // cards
          raised: "#2B2319", // hover / raised
          line: "#3A3122", // borders on dark
          soft: "#BFB4A2", // body text on dark
          faint: "#948A7C", // meta / mono labels on dark (AA 4.5:1 on panel)
        },
        amber: {
          DEFAULT: "#E7A24E", // dusk accent
          soft: "#F3C88A",
          deep: "#C77F2E",
        },
      },
      fontFamily: {
        sans: ["Public Sans", "Segoe UI", "system-ui", "sans-serif"],
        display: ["Archivo", "Public Sans", "Segoe UI", "sans-serif"],
        mono: ["IBM Plex Mono", "SFMono-Regular", "Consolas", "monospace"],
      },
      boxShadow: {
        // Hard drafted shadows — warm-tinted, no soft blur (brief §1).
        sheet: "0 1px 0 rgba(36, 28, 21, 0.10)",
        raised:
          "0 2px 0 rgba(36, 28, 21, 0.10), 0 1px 0 rgba(36, 28, 21, 0.06)",
        stamp: "0 1px 0 rgba(36, 28, 21, 0.08)",
        // Warm ambient lift for hero / marketing surfaces.
        float:
          "0 18px 40px -24px rgba(36, 28, 21, 0.35), 0 2px 0 rgba(36, 28, 21, 0.05)",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.16, 1, 0.3, 1)", // --ease-out-expo
        inout: "cubic-bezier(0.65, 0, 0.35, 1)",
      },
      transitionDuration: {
        fast: "150ms",
        med: "250ms",
        slow: "450ms",
      },
      maxWidth: {
        shell: "1200px",
      },
    },
  },
  plugins: [],
};
