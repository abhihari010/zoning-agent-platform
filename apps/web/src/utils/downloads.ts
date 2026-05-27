import type { AnalyzeResponse } from "@zoning-agent/shared-schema";
import type { IntakeResponse } from "../api";
import { decisionLabel } from "./resultLabels";

export function buildChecklistDownload(
  intake: IntakeResponse | null,
  result: AnalyzeResponse,
  projectContext: string,
): string {
  return [
    "Zoning Agent Checklist",
    "",
    `Project: ${projectContext.trim()}`,
    `Address: ${intake?.normalizedAddress ?? "Not available"}`,
    `District: ${intake?.district ?? "Unknown"}`,
    `Verdict: ${decisionLabel(result.feasibility.decision)}`,
    `Confidence: ${(result.feasibility.confidence * 100).toFixed(0)}%`,
    "",
    "Summary",
    result.feasibility.summary,
    "",
    "Permits",
    ...result.checklist.permits.map((permit) => `- ${permit}`),
    "",
    "Checklist",
    ...result.checklist.steps.map(
      (step) =>
        `${step.order}. ${step.action} | ${step.department} | Documents: ${step.requiredDocs.join(", ")}`,
    ),
    "",
    "Sources",
    ...result.citations.map((citation) => `- ${citation.title} (${citation.sectionRef})`),
    "",
    "Disclaimers",
    ...result.disclaimers.map((disclaimer) => `- ${disclaimer}`),
  ].join("\n");
}

export function downloadTextFile(filename: string, contents: string): void {
  const blob = new Blob([contents], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
