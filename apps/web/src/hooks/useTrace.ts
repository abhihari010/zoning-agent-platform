import { useEffect, useState } from "react";
import type { AnalyzeResponse, AuditEvent } from "@zoning-agent/shared-schema";
import { fetchTrace, type IntakeResponse } from "../api";
import type { Phase } from "../types/app";

export function useTrace({
  intake,
  result,
  phase,
  isAdmin = false,
}: {
  intake: IntakeResponse | null;
  result: AnalyzeResponse | null;
  phase: Phase;
  isAdmin?: boolean;
}) {
  const [trace, setTrace] = useState<AuditEvent[]>([]);
  const [traceLoading, setTraceLoading] = useState(false);

  useEffect(() => {
    if (!isAdmin || !intake || intake.status !== "created") {
      setTrace([]);
      return;
    }

    const projectId = intake.projectId;
    let cancelled = false;

    async function loadTrace() {
      try {
        setTraceLoading(true);
        const events = await fetchTrace(projectId);
        if (!cancelled) {
          setTrace(events);
        }
      } catch {
        if (!cancelled) {
          setTrace([]);
        }
      } finally {
        if (!cancelled) {
          setTraceLoading(false);
        }
      }
    }

    void loadTrace();
    return () => {
      cancelled = true;
    };
  }, [intake, result, phase, isAdmin]);

  return { trace, setTrace, traceLoading };
}
