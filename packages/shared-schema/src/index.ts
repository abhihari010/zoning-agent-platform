export type AnalyzeStatus =
  | "success"
  | "needs_clarification"
  | "low_confidence"
  | "error";

export interface SourceCitation {
  sourceId: string;
  title: string;
  excerpt: string;
  sectionRef: string;
  chunkId?: string | null;
  jurisdictionId?: string | null;
  sourceType?: string | null;
  url?: string;
  effectiveDate?: string;
  retrievedAt?: string | null;
  score?: number | null;
  metadata?: Record<string, unknown>;
}

export interface FollowUpQuestion {
  id: string;
  question: string;
  reason: string;
}

export interface AuditEvent {
  stage: string;
  projectId: string;
  details: Record<string, unknown>;
  createdAt: string;
}

export interface PipelineStageReport {
  key: "intake" | "location" | "retrieval" | "compliance" | "checklist";
  label: string;
  status: "completed" | "needs_clarification" | "warning" | "skipped";
  headline: string;
  details: string[];
}

/** @deprecated Use PipelineStageReport. Kept for older API consumers. */
export type AgentReport = PipelineStageReport;

export interface PipelineMetadata {
  version: string;
  promptVersion: string;
  provider: string;
  ragProvider: string;
  embeddingProvider: string;
  traceId: string;
}

export interface CitationValidation {
  valid: boolean;
  citationCoverage: number;
  unsupportedClaims: string[];
  invalidCitationIds: string[];
  confidenceAdjustment: "none" | "downgrade_low_confidence";
  warnings: string[];
  jurisdictionId?: string | null;
}

export interface FeasibilityOutput {
  decision: "likely_allowed" | "conditional" | "restricted" | "unknown";
  confidence: number;
  summary: string;
}

export interface ChecklistStep {
  order: number;
  action: string;
  requiredDocs: string[];
  department: string;
}

export interface AnalyzeResponse {
  status: AnalyzeStatus;
  traceId: string;
  pipeline?: PipelineMetadata | null;
  citationValidation?: CitationValidation | null;
  pipelineStages?: PipelineStageReport[];
  /** @deprecated Use pipelineStages. Kept as a compatibility alias. */
  agents: PipelineStageReport[];
  feasibility: FeasibilityOutput;
  checklist: {
    steps: ChecklistStep[];
    permits: string[];
    documents: string[];
    departments: string[];
  };
  citations: SourceCitation[];
  disclaimers: string[];
  followUpQuestions: FollowUpQuestion[];
  warnings: string[];
}
