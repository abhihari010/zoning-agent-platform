import type { AnalyzeResponse, PipelineStageReport } from "@zoning-agent/shared-schema";
import type { IntakeResponse } from "../api";

export type Workspace = "assistant" | "admin";
export type Phase = "idle" | "intake" | "analyzing" | "done" | "error";
export type FeedbackState = "idle" | "submitting" | "submitted";
export type ResultView = "checklist" | "evidence" | "trace";
export type LegalPage = "terms" | "privacy" | "disclaimer" | null;

export interface IntakeFacts {
  useType: string;
  constructionScope: string;
  operatingHours: string;
  employeeCount: string;
  parkingLoading: string;
  foodService: string;
}

export type Decision = AnalyzeResponse["feasibility"]["decision"];
export type StageStatus = PipelineStageReport["status"];
export type SupportStatus = IntakeResponse["supportStatus"];
