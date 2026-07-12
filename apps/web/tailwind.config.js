/** @type {import('tailwindcss').Config} */
// "Instrument" — cool premium-dark system (redesign 2026-07).
// Token NAMES are the stable API the whole app consumes; changing their VALUES
// re-skins every product surface in one move. This palette is a cool near-black
// instrument panel with ONE azure accent. Determination colour (green / amber /
// red) is reserved strictly for verdicts via the `verdict` tokens — the brand
// accent never uses them, so a green chip always means "permitted", never "brand".
//
// Legacy names kept for back-compat, repurposed values:
//   spruce  -> azure  (primary brand / CTA / interactive accent)
//   amber   -> azure  (marketing highlight — same single accent, on purpose)
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── Cool near-black neutral ramp ───────────────────────────────
        paper: "#F4F6FB", // near-white — light TEXT on dark surfaces
        sheet: "#101319", // card surface
        well: "#171B23", // recessed / raised surface
        ink: {
          DEFAULT: "#F4F6FB", // primary text on dark
          soft: "#A7AEBE", // secondary text (AA on sheet)
          faint: "#828A9B", // meta / placeholders (AA 4.5:1 on all dark surfaces)
        },
        rule: {
          DEFAULT: "#232833", // hairline border
          strong: "#333A47", // hover / input border
        },
        // ── Single azure accent (legacy name: spruce) ──────────────────
        spruce: {
          DEFAULT: "#5B8CFF", // primary brand / CTA / interactive
          deep: "#456FE6", // hover / pressed
          bright: "#93B2FF", // brightened for text / icons on dark
          wash: "#141B2E", // selected / accent fills on dark
        },
        // Marketing highlight — same single accent (legacy name: amber).
        amber: {
          DEFAULT: "#5B8CFF",
          soft: "#93B2FF",
          deep: "#456FE6",
        },
        // ── Verdict semantics — the ONLY other colour on the surface ────
        verdict: {
          ok: "#4ADE9E", // permitted
          okwash: "#0E211B",
          hold: "#F2B44C", // conditional
          holdwash: "#241C0E",
          stop: "#F27A5C", // prohibited
          stopwash: "#251310",
        },
        // ── Dusk namespace (marketing/auth surfaces) ───────────────────
        // Cool charcoal, deliberately not warm.
        dusk: {
          DEFAULT: "#0A0B0F", // page
          deep: "#060709", // footer / contrast bands
          panel: "#101319", // cards
          raised: "#171B23", // hover / raised
          line: "rgba(255,255,255,0.07)", // translucent hairline — adapts over any dark surface
          soft: "#A7AEBE", // body text on dark
          faint: "#828A9B", // meta / mono labels (AA on all dark surfaces)
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        display: ["Space Grotesk", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "SFMono-Regular", "Consolas", "monospace"],
      },
      letterSpacing: {
        display: "-0.02em", // hero / display headings
        label: "0.16em", // uppercase micro-labels
      },
      boxShadow: {
        // Soft, cool-tinted ambient depth — premium dark, not paper.
        sheet: "0 1px 0 rgba(255, 255, 255, 0.02), 0 16px 40px -32px rgba(0, 0, 0, 0.9)",
        raised:
          "0 1px 0 rgba(255, 255, 255, 0.03), 0 28px 60px -34px rgba(0, 0, 0, 0.9)",
        // Azure accent glow for focused / hero surfaces.
        glow: "0 0 0 1px rgba(91, 140, 255, 0.24), 0 24px 70px -30px rgba(91, 140, 255, 0.35)",
        float: "0 30px 80px -40px rgba(0, 0, 0, 0.85)",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.16, 1, 0.3, 1)", // ease-out-expo
        inout: "cubic-bezier(0.65, 0, 0.35, 1)",
      },
      transitionDuration: {
        fast: "150ms",
        med: "260ms",
        slow: "520ms",
      },
      maxWidth: {
        shell: "1180px",
      },
    },
  },
  plugins: [],
};
