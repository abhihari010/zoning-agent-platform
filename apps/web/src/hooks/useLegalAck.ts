import { useState } from "react";

const LEGAL_ACK_KEY = "legal_ack_at";

export function useLegalAck() {
  const [ackAt, setAckAt] = useState<string | null>(() =>
    localStorage.getItem(LEGAL_ACK_KEY),
  );

  function acknowledge() {
    const now = new Date().toISOString();
    localStorage.setItem(LEGAL_ACK_KEY, now);
    setAckAt(now);
    return now;
  }

  return { ackAt, isAcknowledged: !!ackAt, acknowledge };
}
