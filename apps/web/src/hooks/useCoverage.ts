import { useEffect, useMemo, useState } from "react";
import { fetchJurisdictionCoverage, type JurisdictionCoverage } from "../api";

export function useCoverage() {
  const [coverage, setCoverage] = useState<JurisdictionCoverage[]>([]);
  const [coverageMessage, setCoverageMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function loadCoverage() {
      try {
        const items = await fetchJurisdictionCoverage();
        if (!cancelled) {
          setCoverage(items);
          setCoverageMessage("");
        }
      } catch (coverageError) {
        if (!cancelled) {
          setCoverageMessage(
            coverageError instanceof Error ? coverageError.message : "Coverage could not be loaded.",
          );
        }
      }
    }
    loadCoverage();
    return () => {
      cancelled = true;
    };
  }, []);

  const publicSupportedCoverage = useMemo(
    () => coverage.filter((item) => item.coverageStatus === "public_supported"),
    [coverage],
  );
  const indexedCoverage = useMemo(
    () => coverage.filter((item) => item.coverageStatus === "source_indexed"),
    [coverage],
  );
  const coverageByJurisdictionId = useMemo(
    () => new Map(coverage.map((item) => [item.jurisdictionId, item])),
    [coverage],
  );
  const coverageByJurisdictionName = useMemo(
    () => new Map(coverage.map((item) => [item.name.toLowerCase(), item])),
    [coverage],
  );

  return {
    coverage,
    coverageMessage,
    publicSupportedCoverage,
    indexedCoverage,
    coverageByJurisdictionId,
    coverageByJurisdictionName,
  };
}
