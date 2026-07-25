import { useState } from "react";
import { ApiError, createCheckoutSession } from "../api";

// Single source of truth for "start a Stripe checkout redirect", reused by
// the locked-deliverable panel, the daily-limit banner, and the header plan
// badge. Success navigates away (pending stays true); failure resets pending
// so the button never gets stuck in a spinner.
export function useCheckout() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setPending(true);
    setError(null);
    try {
      const url = await createCheckoutSession();
      window.location.assign(url);
    } catch (checkoutError) {
      setPending(false);
      if (checkoutError instanceof ApiError && checkoutError.status === 503) {
        setError("Upgrade isn't available yet — check back soon.");
        return;
      }
      setError(
        checkoutError instanceof Error
          ? checkoutError.message
          : "Failed to start checkout.",
      );
    }
  }

  return { pending, error, start };
}
