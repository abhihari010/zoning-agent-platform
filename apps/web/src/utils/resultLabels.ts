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
      return "border-emerald-200 bg-emerald-50 text-emerald-800";
    case "conditional":
      return "border-amber-200 bg-amber-50 text-amber-800";
    case "restricted":
      return "border-red-200 bg-red-50 text-red-800";
    default:
      return "border-slate-200 bg-slate-50 text-slate-800";
  }
}

export function statusTone(status: StageStatus, isActive: boolean): string {
  if (isActive) {
    return "border-clay bg-clay/10";
  }
  if (status === "completed") {
    return "border-emerald-200 bg-emerald-50";
  }
  if (status === "warning") {
    return "border-amber-200 bg-amber-50";
  }
  if (status === "needs_clarification") {
    return "border-clay/40 bg-clay/10";
  }
  return "border-slate-200 bg-white";
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
    return "border-red-200 bg-red-50 text-red-900";
  }
  if (confidence < 0.75) {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  return "border-emerald-200 bg-emerald-50 text-emerald-900";
}

export function evidenceTone(citationCount: number): string {
  if (citationCount === 0) {
    return "border-red-200 bg-red-50 text-red-900";
  }
  if (citationCount < 2) {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  return "border-emerald-200 bg-emerald-50 text-emerald-900";
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
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  if (status === "invalid") {
    return "border-red-200 bg-red-50 text-red-900";
  }
  return "border-emerald-200 bg-emerald-50 text-emerald-900";
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
    return "border-emerald-200 bg-emerald-50 text-emerald-900";
  }
  if (status === "qa_ready" || status === "source_indexed") {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  return "border-slate-200 bg-slate-50 text-slate-700";
}

export function readinessTone(indexStatus: SourceIndexStatus | null): string {
  if (!indexStatus) {
    return "border-slate-200 bg-slate-50 text-slate-900";
  }
  if (indexStatus.indexReady) {
    return "border-emerald-200 bg-emerald-50 text-emerald-900";
  }
  if (indexStatus.hasIndex) {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  return "border-red-200 bg-red-50 text-red-900";
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
