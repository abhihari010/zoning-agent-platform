import type { Variants } from "motion/react";

/** ease-out-expo — the house curve. No bounce, no elastic. */
export const EASE = [0.16, 1, 0.3, 1] as const;

/** Fade + rise. Pair with `staggerParent` on a container for sequenced reveals. */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: EASE },
  },
};

export const staggerParent: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.05 } },
};

/** Micro-interaction props for interactive cards / buttons (transform-only). */
export const hoverLift = {
  whileHover: { y: -3 },
  whileTap: { scale: 0.985 },
  transition: { duration: 0.2, ease: EASE },
} as const;

/** In-view config shared by scroll reveals — fire once, a touch before center. */
export const inViewOnce = {
  once: true,
  margin: "0px 0px -12% 0px",
} as const;
