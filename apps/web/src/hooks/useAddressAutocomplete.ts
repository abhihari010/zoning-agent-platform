import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { suggestAddresses } from "../api";

export function useAddressAutocomplete() {
  const [address, setAddress] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [autocompleteSession] = useState(() => crypto.randomUUID());
  const addressSectionRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const trimmed = address.trim();
    if (trimmed.length < 3) {
      setSuggestions([]);
      setActiveSuggestionIndex(-1);
      return;
    }

    const handle = setTimeout(async () => {
      try {
        setSuggestionLoading(true);
        const options = await suggestAddresses(trimmed, autocompleteSession);
        setSuggestions(options);
        setActiveSuggestionIndex(options.length > 0 ? 0 : -1);
      } finally {
        setSuggestionLoading(false);
      }
    }, 200);

    return () => clearTimeout(handle);
  }, [address, autocompleteSession]);

  useEffect(() => {
    const onDocumentPointerDown = (event: MouseEvent) => {
      const container = addressSectionRef.current;
      if (container && !container.contains(event.target as Node)) {
        setSuggestions([]);
        setActiveSuggestionIndex(-1);
      }
    };

    document.addEventListener("mousedown", onDocumentPointerDown);
    return () => document.removeEventListener("mousedown", onDocumentPointerDown);
  }, []);

  function selectSuggestion(option: string) {
    setAddress(option);
    setSuggestions([]);
    setActiveSuggestionIndex(-1);
  }

  function onAddressKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (suggestions.length === 0) {
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveSuggestionIndex((current) => (current + 1) % suggestions.length);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSuggestionIndex((current) =>
        current <= 0 ? suggestions.length - 1 : current - 1,
      );
      return;
    }

    if (event.key === "Enter" && activeSuggestionIndex >= 0) {
      event.preventDefault();
      selectSuggestion(suggestions[activeSuggestionIndex]);
      return;
    }

    if (event.key === "Escape") {
      setSuggestions([]);
      setActiveSuggestionIndex(-1);
    }
  }

  function resetAddress() {
    setAddress("");
    setSuggestions([]);
    setActiveSuggestionIndex(-1);
  }

  return {
    address,
    setAddress,
    suggestions,
    setSuggestions,
    activeSuggestionIndex,
    suggestionLoading,
    addressSectionRef,
    selectSuggestion,
    onAddressKeyDown,
    resetAddress,
  };
}
