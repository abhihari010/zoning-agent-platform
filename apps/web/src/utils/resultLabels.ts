import type { CoverageStatus, IntakeResponse, SourceIndexStatus } from "../api";
import type { Decision, StageStatus } from "../types/app";

export function decisionLabel(decision: Decision): string {
  switch (decision) {
    case "likely_allowed":
      return "Allowed";
    case "conditional":
      return "Conditional";
    case "restricted":
      return "Not Allowed";
    default:
      return "Unknown";
  }
}

export function decisionTone(decision: Decision): string {
  switch (decision) {
    case "likely_allowed":
      return "border-verdict-ok/30 bg-verdict-okwash text-verdict-ok";
    case "conditional":
      return "border-verdict-hold/30 bg-verdict-holdwash text-verdict-hold";
    case "restricted":
      return "border-verdict-stop/30 bg-verdict-stopwash text-verdict-stop";
    default:
      return "border-rule-strong bg-well text-ink-soft";
  }
}

export function statusTone(status: StageStatus, isActive: boolean): string {
  if (isActive) {
    return "border-spruce/40 bg-spruce-wash";
  }
  if (status === "completed") {
    return "border-verdict-ok/25 bg-verdict-okwash/60";
  }
  if (status === "warning") {
    return "border-verdict-hold/25 bg-verdict-holdwash/60";
  }
  if (status === "needs_clarification") {
    return "border-verdict-hold/25 bg-verdict-holdwash/60";
  }
  return "border-rule bg-sheet";
}

export function confidenceLabel(confidence: number): string {
  if (confidence >= 0.75) {
    return "Strong";
  }
  if (confidence >= 0.6) {
    return "Moderate";
  }
  return "Needs review";
}

export function confidenceTone(confidence: number, citationCount: number): string {
  if (citationCount === 0 || confidence < 0.6) {
    return "border-verdict-stop/25 bg-verdict-stopwash text-verdict-stop";
  }
  if (confidence < 0.75) {
    return "border-verdict-hold/25 bg-verdict-holdwash text-verdict-hold";
  }
  return "border-verdict-ok/25 bg-verdict-okwash text-verdict-ok";
}

export function evidenceTone(citationCount: number): string {
  if (citationCount === 0) {
    return "border-verdict-stop/25 bg-verdict-stopwash text-verdict-stop";
  }
  if (citationCount < 2) {
    return "border-verdict-hold/25 bg-verdict-holdwash text-verdict-hold";
  }
  return "border-verdict-ok/25 bg-verdict-okwash text-verdict-ok";
}

export function evidenceLabel(citationCount: number): string {
  if (citationCount === 0) {
    return "No cited sources";
  }
  if (citationCount === 1) {
    return "1 cited source";
  }
  return `${citationCount} cited sources`;
}

export function supportStatusLabel(status?: IntakeResponse["supportStatus"]): string {
  if (status === "unsupported") {
    return "Recognized, not covered";
  }
  if (status === "invalid") {
    return "Invalid or unverified";
  }
  return "Supported";
}

export function supportStatusTone(status?: IntakeResponse["supportStatus"]): string {
  if (status === "unsupported") {
    return "border-verdict-hold/25 bg-verdict-holdwash text-verdict-hold";
  }
  if (status === "invalid") {
    return "border-verdict-stop/25 bg-verdict-stopwash text-verdict-stop";
  }
  return "border-verdict-ok/25 bg-verdict-okwash text-verdict-ok";
}

export function coverageLabel(status?: CoverageStatus | null): string {
  switch (status) {
    case "public_supported":
      return "Public supported";
    case "qa_ready":
      return "QA ready";
    case "source_indexed":
      return "Sources indexed";
    case "source_discovery":
      return "Source discovery";
    default:
      return "Not covered";
  }
}

export function coverageTone(status?: CoverageStatus | null): string {
  if (status === "public_supported") {
    return "tag-ok";
  }
  if (status === "qa_ready" || status === "source_indexed") {
    return "tag-hold";
  }
  return "tag-neutral";
}

export function readinessTone(indexStatus: SourceIndexStatus | null): string {
  if (!indexStatus) {
    return "border-rule bg-well text-ink-soft";
  }
  if (indexStatus.indexReady) {
    return "border-verdict-ok/25 bg-verdict-okwash text-verdict-ok";
  }
  if (indexStatus.hasIndex) {
    return "border-verdict-hold/25 bg-verdict-holdwash text-verdict-hold";
  }
  return "border-verdict-stop/25 bg-verdict-stopwash text-verdict-stop";
}

export function readinessLabel(indexStatus: SourceIndexStatus | null): string {
  if (!indexStatus) {
    return "Unknown";
  }
  if (indexStatus.indexReady) {
    return "Ready";
  }
  if (indexStatus.hasIndex) {
    return "Needs refresh";
  }
  return "Not indexed";
}
