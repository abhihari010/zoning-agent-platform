import { useState } from "react";
import {
  clearBetaAccessKey,
  getBetaAccessKey,
  setBetaAccessKey,
} from "../api";

export function useBetaAccess() {
  const [betaAccessKey, setStoredBetaAccessKey] = useState(() => getBetaAccessKey());
  const [betaAccessInput, setBetaAccessInput] = useState("");
  const [betaAccessError, setBetaAccessError] = useState("");

  function unlockPrivateBeta() {
    if (!betaAccessInput.trim()) {
      setBetaAccessError("Enter the private beta access key.");
      return;
    }

    setBetaAccessKey(betaAccessInput);
    setStoredBetaAccessKey(betaAccessInput.trim());
    setBetaAccessInput("");
    setBetaAccessError("");
  }

  function changePrivateBetaKey() {
    clearBetaAccessKey();
    setStoredBetaAccessKey("");
    setBetaAccessInput("");
    setBetaAccessError("");
  }

  return {
    betaAccessKey,
    betaAccessInput,
    betaAccessError,
    setBetaAccessInput,
    unlockPrivateBeta,
    changePrivateBetaKey,
  };
}
