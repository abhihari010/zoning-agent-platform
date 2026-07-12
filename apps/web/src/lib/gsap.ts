import { useLayoutEffect, type RefObject } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Scoped gsap.context that auto-reverts on unmount and no-ops under reduced
 * motion. All selectors inside `setup` resolve within `scope`, so effects are
 * self-contained and clean up after themselves.
 */
export function useGsap(
  scope: RefObject<HTMLElement | null>,
  setup: (self: gsap.Context) => void,
  deps: unknown[] = [],
) {
  useLayoutEffect(() => {
    if (prefersReducedMotion() || !scope.current) {
      return;
    }
    const ctx = gsap.context(setup, scope);
    return () => ctx.revert();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export { gsap, ScrollTrigger };
