import type {
  AnalyzeResponse,
  AuditEvent,
  FollowUpQuestion,
} from "@zoning-agent/shared-schema";

const RAW_API_URL = import.meta.env.VITE_API_URL ?? "";
if (import.meta.env.PROD && !RAW_API_URL) {
  throw new Error(
    "VITE_API_URL is not configured. Set it explicitly for production builds.",
  );
}
const API_ORIGIN = (RAW_API_URL || "http://localhost:8000").replace(/\/$/, "");
const API_BASE = `${API_ORIGIN}/api/v1`;
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL ?? "";
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY ?? "";
if (import.meta.env.PROD && (!SUPABASE_URL || !SUPABASE_ANON_KEY)) {
  throw new Error(
    "VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY must be set for production builds.",
  );
}
const ADMIN_ACCESS_STORAGE_KEY = "zoning-agent.adminAccessKey";
let authToken = "";

export const authMode: "disabled" | "supabase" =
  SUPABASE_URL && SUPABASE_ANON_KEY ? "supabase" : "disabled";
export const supabaseConfig = {
  url: SUPABASE_URL,
  anonKey: SUPABASE_ANON_KEY,
};

export function setAuthToken(value: string): void {
  authToken = value;
}

export function getAdminAccessKey(): string {
  return window.sessionStorage.getItem(ADMIN_ACCESS_STORAGE_KEY) ?? "";
}

export function setAdminAccessKey(value: string): void {
  const trimmed = value.trim();
  if (trimmed) {
    window.sessionStorage.setItem(ADMIN_ACCESS_STORAGE_KEY, trimmed);
  } else {
    window.sessionStorage.removeItem(ADMIN_ACCESS_STORAGE_KEY);
  }
}

export function clearAdminAccessKey(): void {
  window.sessionStorage.removeItem(ADMIN_ACCESS_STORAGE_KEY);
}

function requestHeaders(
  headers: Record<string, string> = {},
  options: { includeAdminAccess?: boolean } = {},
): HeadersInit {
  const adminAccessKey = options.includeAdminAccess ? getAdminAccessKey() : "";
  return {
    ...headers,
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...(adminAccessKey ? { "X-Admin-Access-Key": adminAccessKey } : {}),
  };
}

export interface CurrentUser {
  userId?: string | null;
  email?: string | null;
  role: "anonymous" | "user" | "admin";
  authMode: "disabled" | "supabase";
  publicSignupsEnabled: boolean;
}

export interface ProjectSummary {
  projectId: string;
  normalizedAddress: string;
  jurisdictionId?: string | null;
  jurisdictionName?: string | null;
  district: string;
  status: "created" | "analyzed";
  decision?: AnalyzeResponse["feasibility"]["decision"] | null;
  confidence?: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface IntakeResponse {
  projectId: string;
  normalizedAddress: string;
  district: string;
  placeId?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  status: "created" | "invalid_address";
  supportStatus: "supported" | "unsupported" | "invalid";
  jurisdictionId?: string | null;
  jurisdictionName?: string | null;
  coverageStatus?: CoverageStatus | null;
  planningContact?: Record<string, string>;
  officialSourceUrls?: string[];
  followUpQuestions: FollowUpQuestion[];
}

export type CoverageStatus =
  | "unsupported"
  | "source_discovery"
  | "source_indexed"
  | "qa_ready"
  | "public_supported";

export interface JurisdictionCoverage {
  jurisdictionId: string;
  name: string;
  state?: string | null;
  jurisdictionType: string;
  coverageStatus: CoverageStatus;
  supported: boolean;
  officialSourceUrls: string[];
  zoningMapUrl?: string | null;
  planningContact: Record<string, string>;
  lastVerifiedAt?: string | null;
}

export interface SourceRegistryEntry {
  sourceId: string;
  title: string;
  excerpt: string;
  sectionRef: string;
  jurisdictionId?: string | null;
  url?: string | null;
  effectiveDate?: string | null;
  districts: string[];
  uses: string[];
  sourceType?: string | null;
  retrievedAt?: string | null;
  sourceVersion?: string | null;
  contentHash?: string | null;
  fullText?: string | null;
  metadata?: Record<string, unknown>;
}

export interface SourceIndexStatus {
  sourceCount: number;
  chunkCount: number;
  hasIndex: boolean;
  indexReady: boolean;
  autoSeedSources: boolean;
  autoReindexOnEmpty: boolean;
  sourceRegistryVersion?: string | null;
  staleSourceIds: string[];
  missingChunkSourceIds: string[];
  readinessWarnings: string[];
  vectorProvider: string;
  vectorIndexReady: boolean;
  vectorCount: number;
  vectorCollection?: string | null;
  vectorReadinessWarnings: string[];
  sourcePackCount: number;
  sourcePackJurisdictionIds: string[];
  lastImportAt?: string | null;
  lastReindexAt?: string | null;
  sourcesMissingMetadata: Array<{
    sourceId: string;
    missingFields: string[];
  }>;
}

export interface LocalDocumentImportResult {
  status: string;
  importedCount: number;
  sourceCount: number;
  importedSourceIds: string[];
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function toFollowUpQuestions(questions: string[]): FollowUpQuestion[] {
  return questions.map((question) => ({
    id: slugify(question) || crypto.randomUUID(),
    question,
    reason: "More detail improves feasibility confidence and permit guidance.",
  }));
}

async function parseError(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail || fallback;
  } catch {
    return fallback;
  }
}

async function parseAdminActionError(
  response: Response,
  action: string,
): Promise<string> {
  const detail = await parseError(response, `${action} failed`);
  if (response.status === 401) {
    return `${detail} Enter the source admin key, then retry ${action.toLowerCase()}.`;
  }
  if (response.status === 403) {
    return `${detail} Check the source admin key or ask an administrator to rotate it.`;
  }
  return detail;
}

export async function suggestAddresses(
  query: string,
  sessionToken?: string,
): Promise<string[]> {
  const params = new URLSearchParams({ query });
  if (sessionToken) {
    params.set("session_token", sessionToken);
  }

  const response = await fetch(
    `${API_BASE}/address/suggest?${params.toString()}`,
    { headers: requestHeaders() },
  );
  if (!response.ok) {
    return [];
  }

  const payload = (await response.json()) as { suggestions: string[] };
  return payload.suggestions;
}

export async function createSession(): Promise<string> {
  const response = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: requestHeaders(),
  });
  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to create session"));
  }
  const payload = (await response.json()) as { session_id: string };
  return payload.session_id;
}

export interface JurisdictionRequestResult {
  status: "created" | "existing";
  jurisdictionId?: string | null;
  jurisdictionName?: string | null;
  requestCount: number;
}

export interface JurisdictionRequestSummary {
  jurisdictionId?: string | null;
  jurisdictionName?: string | null;
  state?: string | null;
  county?: string | null;
  locality?: string | null;
  requestCount: number;
  lastRequestedAt: string;
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  const response = await fetch(`${API_BASE}/me`, {
    headers: requestHeaders(),
  });
  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to load user"));
  }
  const payload = (await response.json()) as {
    user_id?: string | null;
    email?: string | null;
    role: CurrentUser["role"];
    auth_mode: CurrentUser["authMode"];
    public_signups_enabled: boolean;
  };
  return {
    userId: payload.user_id,
    email: payload.email,
    role: payload.role,
    authMode: payload.auth_mode,
    publicSignupsEnabled: payload.public_signups_enabled,
  };
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const response = await fetch(`${API_BASE}/projects`, {
    headers: requestHeaders(),
  });
  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to load projects"));
  }
  const payload = (await response.json()) as {
    projects: Array<{
      project_id: string;
      normalized_address: string;
      jurisdiction_id?: string | null;
      jurisdiction_name?: string | null;
      district: string;
      status: "created" | "analyzed";
      decision?: AnalyzeResponse["feasibility"]["decision"] | null;
      confidence?: number | null;
      created_at: string;
      updated_at: string;
    }>;
  };
  return payload.projects.map((project) => ({
    projectId: project.project_id,
    normalizedAddress: project.normalized_address,
    jurisdictionId: project.jurisdiction_id,
    jurisdictionName: project.jurisdiction_name,
    district: project.district,
    status: project.status,
    decision: project.decision,
    confidence: project.confidence,
    createdAt: project.created_at,
    updatedAt: project.updated_at,
  }));
}

export async function deleteProject(projectId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/projects/${projectId}`, {
    method: "DELETE",
    headers: requestHeaders(),
  });
  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to delete project"));
  }
}

export async function deleteMyData(): Promise<{ deletedProjects: number }> {
  const response = await fetch(`${API_BASE}/me/data`, {
    method: "DELETE",
    headers: requestHeaders(),
  });
  if (!response.ok) {
    throw new Error(
      await parseError(response, "Failed to delete account data"),
    );
  }
  const payload = (await response.json()) as { deleted_projects: number };
  return { deletedProjects: payload.deleted_projects };
}

export async function fetchJurisdictionRequestSummaries(): Promise<
  JurisdictionRequestSummary[]
> {
  const response = await fetch(`${API_BASE}/admin/jurisdiction-requests`, {
    headers: requestHeaders({}, { includeAdminAccess: true }),
  });
  if (!response.ok) {
    throw new Error(
      await parseAdminActionError(response, "Load jurisdiction requests"),
    );
  }
  const payload = (await response.json()) as {
    requests: Array<{
      jurisdiction_id?: string | null;
      jurisdiction_name?: string | null;
      state?: string | null;
      county?: string | null;
      locality?: string | null;
      request_count: number;
      last_requested_at: string;
    }>;
  };
  return payload.requests.map((request) => ({
    jurisdictionId: request.jurisdiction_id,
    jurisdictionName: request.jurisdiction_name,
    state: request.state,
    county: request.county,
    locality: request.locality,
    requestCount: request.request_count,
    lastRequestedAt: request.last_requested_at,
  }));
}

export async function fetchJurisdictionCoverage(): Promise<
  JurisdictionCoverage[]
> {
  const response = await fetch(`${API_BASE}/jurisdictions/coverage`, {
    headers: requestHeaders(),
  });
  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to load coverage"));
  }
  const payload = (await response.json()) as {
    jurisdictions: Array<{
      jurisdiction_id: string;
      name: string;
      state?: string | null;
      jurisdiction_type: string;
      coverage_status: CoverageStatus;
      supported: boolean;
      official_source_urls: string[];
      zoning_map_url?: string | null;
      planning_contact: Record<string, string>;
      last_verified_at?: string | null;
    }>;
  };
  return payload.jurisdictions.map((jurisdiction) => ({
    jurisdictionId: jurisdiction.jurisdiction_id,
    name: jurisdiction.name,
    state: jurisdiction.state,
    jurisdictionType: jurisdiction.jurisdiction_type,
    coverageStatus: jurisdiction.coverage_status,
    supported: jurisdiction.supported,
    officialSourceUrls: jurisdiction.official_source_urls,
    zoningMapUrl: jurisdiction.zoning_map_url,
    planningContact: jurisdiction.planning_contact ?? {},
    lastVerifiedAt: jurisdiction.last_verified_at,
  }));
}

export async function requestJurisdictionSupport(input: {
  normalizedAddress: string;
  jurisdictionId?: string | null;
  jurisdictionName?: string | null;
  requestedUseType?: string | null;
  comment?: string | null;
}): Promise<JurisdictionRequestResult> {
  const response = await fetch(`${API_BASE}/jurisdiction-requests`, {
    method: "POST",
    headers: requestHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      normalized_address: input.normalizedAddress,
      jurisdiction_id: input.jurisdictionId,
      jurisdiction_name: input.jurisdictionName,
      requested_use_type: input.requestedUseType,
      comment: input.comment,
    }),
  });
  if (!response.ok) {
    throw new Error(
      await parseError(response, "Failed to request jurisdiction support"),
    );
  }
  const payload = (await response.json()) as {
    status: "created" | "existing";
    jurisdiction_id?: string | null;
    jurisdiction_name?: string | null;
    request_count: number;
  };
  return {
    status: payload.status,
    jurisdictionId: payload.jurisdiction_id,
    jurisdictionName: payload.jurisdiction_name,
    requestCount: payload.request_count,
  };
}

export async function intakeProject(input: {
  session_id: string;
  project_description: string;
  address: string;
  legal_ack_at?: string;
}): Promise<IntakeResponse> {
  const response = await fetch(`${API_BASE}/projects/intake`, {
    method: "POST",
    headers: requestHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await parseError(response, "Project intake failed"));
  }

  const payload = (await response.json()) as {
    project_id: string;
    normalized_address: string;
    district: string;
    place_id?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    status: "created" | "invalid_address";
    support_status?: "supported" | "unsupported" | "invalid";
    jurisdiction_id?: string | null;
    jurisdiction_name?: string | null;
    coverage_status?: CoverageStatus | null;
    planning_contact?: Record<string, string>;
    official_source_urls?: string[];
    follow_up_questions: string[];
  };

  return {
    projectId: payload.project_id,
    normalizedAddress: payload.normalized_address,
    district: payload.district,
    placeId: payload.place_id,
    latitude: payload.latitude,
    longitude: payload.longitude,
    status: payload.status,
    supportStatus: payload.support_status ?? "supported",
    jurisdictionId: payload.jurisdiction_id,
    jurisdictionName: payload.jurisdiction_name,
    coverageStatus: payload.coverage_status,
    planningContact: payload.planning_contact ?? {},
    officialSourceUrls: payload.official_source_urls ?? [],
    followUpQuestions: toFollowUpQuestions(payload.follow_up_questions),
  };
}

export async function analyzeProject(
  projectId: string,
  clarificationAnswers?: Record<string, string>,
): Promise<AnalyzeResponse> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/analyze`, {
    method: "POST",
    headers: requestHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      project_id: projectId,
      clarification_answers: clarificationAnswers ?? {},
    }),
  });

  if (!response.ok) {
    throw new Error(await parseError(response, "Analysis request failed"));
  }

  const payload = (await response.json()) as {
    status: AnalyzeResponse["status"];
    trace_id: string;
    pipeline?: {
      version: string;
      prompt_version: string;
      provider: string;
      rag_provider: string;
      embedding_provider: string;
      trace_id: string;
    } | null;
    trust_indicators?: {
      jurisdiction_analyzed: boolean;
      jurisdiction_supported?: boolean | null;
      jurisdiction_name?: string | null;
      zoning_district: string;
      district_confidence: number;
      district_source: string;
      source_count: number;
      citation_count: number;
      vector_readiness: boolean;
      last_source_update?: string | null;
    } | null;
    citation_validation?: {
      valid: boolean;
      citation_coverage: number;
      unsupported_claims: string[];
      invalid_citation_ids: string[];
      confidence_adjustment: "none" | "downgrade_low_confidence";
      warnings: string[];
      jurisdiction_id?: string | null;
    } | null;
    agents: Array<{
      key: "intake" | "location" | "retrieval" | "compliance" | "checklist";
      label: string;
      status: "completed" | "needs_clarification" | "warning" | "skipped";
      headline: string;
      details: string[];
    }>;
    pipeline_stages?: Array<{
      key: "intake" | "location" | "retrieval" | "compliance" | "checklist";
      label: string;
      status: "completed" | "needs_clarification" | "warning" | "skipped";
      headline: string;
      details: string[];
    }>;
    feasibility: AnalyzeResponse["feasibility"];
    compliance?: {
      feasibility: "feasible" | "conditional" | "infeasible" | "unknown";
      confidence: number;
      summary: string;
      findings: Array<{
        category: string;
        status: "compliant" | "conditional" | "non_compliant" | "unknown";
        summary: string;
        citation_ids: string[];
        confidence: number;
      }>;
      required_permits: string[];
      permit_path?: string | null;
      warnings: string[];
      unresolved_questions: string[];
      citation_chunk_ids: string[];
    } | null;
    checklist: {
      steps: Array<{
        order: number;
        action: string;
        required_docs: string[];
        department: string;
      }>;
      permits: string[];
      documents: string[];
      departments: string[];
    };
    citations: Array<{
      source_id: string;
      title: string;
      excerpt: string;
      section_ref: string;
      chunk_id?: string | null;
      jurisdiction_id?: string | null;
      source_type?: string | null;
      url?: string;
      effective_date?: string;
      retrieved_at?: string | null;
      score?: number | null;
      metadata?: Record<string, unknown>;
    }>;
    disclaimers: string[];
    follow_up_questions: string[];
    warnings: string[];
  };

  return {
    status: payload.status,
    traceId: payload.trace_id,
    pipeline: payload.pipeline
      ? {
          version: payload.pipeline.version,
          promptVersion: payload.pipeline.prompt_version,
          provider: payload.pipeline.provider,
          ragProvider: payload.pipeline.rag_provider,
          embeddingProvider: payload.pipeline.embedding_provider,
          traceId: payload.pipeline.trace_id,
        }
      : null,
    trustIndicators: payload.trust_indicators
      ? {
          jurisdictionAnalyzed: payload.trust_indicators.jurisdiction_analyzed,
          jurisdictionSupported:
            payload.trust_indicators.jurisdiction_supported,
          jurisdictionName: payload.trust_indicators.jurisdiction_name,
          zoningDistrict: payload.trust_indicators.zoning_district,
          districtConfidence: payload.trust_indicators.district_confidence,
          districtSource: payload.trust_indicators.district_source,
          sourceCount: payload.trust_indicators.source_count,
          citationCount: payload.trust_indicators.citation_count,
          vectorReadiness: payload.trust_indicators.vector_readiness,
          lastSourceUpdate: payload.trust_indicators.last_source_update,
        }
      : null,
    citationValidation: payload.citation_validation
      ? {
          valid: payload.citation_validation.valid,
          citationCoverage: payload.citation_validation.citation_coverage,
          unsupportedClaims: payload.citation_validation.unsupported_claims,
          invalidCitationIds: payload.citation_validation.invalid_citation_ids,
          confidenceAdjustment:
            payload.citation_validation.confidence_adjustment,
          warnings: payload.citation_validation.warnings,
          jurisdictionId: payload.citation_validation.jurisdiction_id,
        }
      : null,
    pipelineStages: payload.pipeline_stages,
    feasibility: payload.feasibility,
    compliance: payload.compliance
      ? {
          feasibility: payload.compliance.feasibility,
          confidence: payload.compliance.confidence,
          summary: payload.compliance.summary,
          findings: payload.compliance.findings.map((finding) => ({
            category: finding.category,
            status: finding.status,
            summary: finding.summary,
            citationIds: finding.citation_ids,
            confidence: finding.confidence,
          })),
          requiredPermits: payload.compliance.required_permits,
          permitPath: payload.compliance.permit_path,
          warnings: payload.compliance.warnings,
          unresolvedQuestions: payload.compliance.unresolved_questions,
          citationChunkIds: payload.compliance.citation_chunk_ids,
        }
      : null,
    checklist: {
      ...payload.checklist,
      steps: payload.checklist.steps.map((step) => ({
        order: step.order,
        action: step.action,
        requiredDocs: step.required_docs,
        department: step.department,
      })),
    },
    citations: payload.citations.map((citation) => ({
      sourceId: citation.source_id,
      title: citation.title,
      excerpt: citation.excerpt,
      sectionRef: citation.section_ref,
      chunkId: citation.chunk_id,
      jurisdictionId: citation.jurisdiction_id,
      sourceType: citation.source_type,
      url: citation.url,
      effectiveDate: citation.effective_date,
      retrievedAt: citation.retrieved_at,
      score: citation.score,
      metadata: citation.metadata ?? {},
    })),
    disclaimers: payload.disclaimers,
    followUpQuestions: toFollowUpQuestions(payload.follow_up_questions),
    warnings: payload.warnings,
  };
}

export async function fetchProjectResult(
  projectId: string,
): Promise<AnalyzeResponse> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/result`, {
    headers: requestHeaders(),
  });
  if (!response.ok) {
    throw new Error(
      await parseError(response, "Failed to load project result"),
    );
  }
  return mapAnalyzePayload(await response.json());
}

function mapAnalyzePayload(payload: any): AnalyzeResponse {
  if (payload.traceId) {
    return payload as AnalyzeResponse;
  }
  return {
    status: payload.status,
    traceId: payload.trace_id,
    pipeline: payload.pipeline
      ? {
          version: payload.pipeline.version,
          promptVersion: payload.pipeline.prompt_version,
          provider: payload.pipeline.provider,
          ragProvider: payload.pipeline.rag_provider,
          embeddingProvider: payload.pipeline.embedding_provider,
          traceId: payload.pipeline.trace_id,
        }
      : null,
    trustIndicators: payload.trust_indicators
      ? {
          jurisdictionAnalyzed: payload.trust_indicators.jurisdiction_analyzed,
          jurisdictionSupported:
            payload.trust_indicators.jurisdiction_supported,
          jurisdictionName: payload.trust_indicators.jurisdiction_name,
          zoningDistrict: payload.trust_indicators.zoning_district,
          districtConfidence: payload.trust_indicators.district_confidence,
          districtSource: payload.trust_indicators.district_source,
          sourceCount: payload.trust_indicators.source_count,
          citationCount: payload.trust_indicators.citation_count,
          vectorReadiness: payload.trust_indicators.vector_readiness,
          lastSourceUpdate: payload.trust_indicators.last_source_update,
        }
      : null,
    citationValidation: payload.citation_validation
      ? {
          valid: payload.citation_validation.valid,
          citationCoverage: payload.citation_validation.citation_coverage,
          unsupportedClaims: payload.citation_validation.unsupported_claims,
          invalidCitationIds: payload.citation_validation.invalid_citation_ids,
          confidenceAdjustment:
            payload.citation_validation.confidence_adjustment,
          warnings: payload.citation_validation.warnings,
          jurisdictionId: payload.citation_validation.jurisdiction_id,
        }
      : null,
    pipelineStages: payload.pipeline_stages,
    feasibility: payload.feasibility,
    compliance: payload.compliance
      ? {
          feasibility: payload.compliance.feasibility,
          confidence: payload.compliance.confidence,
          summary: payload.compliance.summary,
          findings: payload.compliance.findings.map((finding: any) => ({
            category: finding.category,
            status: finding.status,
            summary: finding.summary,
            citationIds: finding.citation_ids,
            confidence: finding.confidence,
          })),
          requiredPermits: payload.compliance.required_permits,
          permitPath: payload.compliance.permit_path,
          warnings: payload.compliance.warnings,
          unresolvedQuestions: payload.compliance.unresolved_questions,
          citationChunkIds: payload.compliance.citation_chunk_ids,
        }
      : null,
    checklist: {
      ...payload.checklist,
      steps: payload.checklist.steps.map((step: any) => ({
        order: step.order,
        action: step.action,
        requiredDocs: step.required_docs,
        department: step.department,
      })),
    },
    citations: payload.citations.map((citation: any) => ({
      sourceId: citation.source_id,
      title: citation.title,
      excerpt: citation.excerpt,
      sectionRef: citation.section_ref,
      chunkId: citation.chunk_id,
      jurisdictionId: citation.jurisdiction_id,
      sourceType: citation.source_type,
      url: citation.url,
      effectiveDate: citation.effective_date,
      retrievedAt: citation.retrieved_at,
      score: citation.score,
      metadata: citation.metadata ?? {},
    })),
    disclaimers: payload.disclaimers,
    followUpQuestions: toFollowUpQuestions(payload.follow_up_questions),
    warnings: payload.warnings,
  };
}

export async function fetchTrace(projectId: string): Promise<AuditEvent[]> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/trace`, {
    headers: requestHeaders({}, { includeAdminAccess: true }),
  });
  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to load trace"));
  }

  const payload = (await response.json()) as {
    events: Array<{
      stage: string;
      project_id: string;
      details?: Record<string, unknown>;
      created_at: string;
    }>;
  };

  return payload.events.map((event) => ({
    stage: event.stage,
    projectId: event.project_id,
    details: event.details ?? {},
    createdAt: event.created_at,
  }));
}

export async function submitFeedback(input: {
  projectId: string;
  helpful: boolean;
  comment?: string;
}): Promise<void> {
  const response = await fetch(
    `${API_BASE}/projects/${input.projectId}/feedback`,
    {
      method: "POST",
      headers: requestHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        project_id: input.projectId,
        helpful: input.helpful,
        comment: input.comment?.trim() || null,
      }),
    },
  );

  if (!response.ok) {
    throw new Error(await parseError(response, "Feedback request failed"));
  }
}

function mapSourceEntry(payload: {
  source_id: string;
  title: string;
  excerpt: string;
  section_ref: string;
  jurisdiction_id?: string | null;
  url?: string | null;
  effective_date?: string | null;
  districts: string[];
  uses: string[];
  source_type?: string | null;
  retrieved_at?: string | null;
  source_version?: string | null;
  content_hash?: string | null;
  full_text?: string | null;
  metadata?: Record<string, unknown>;
}): SourceRegistryEntry {
  return {
    sourceId: payload.source_id,
    title: payload.title,
    excerpt: payload.excerpt,
    sectionRef: payload.section_ref,
    jurisdictionId: payload.jurisdiction_id,
    url: payload.url,
    effectiveDate: payload.effective_date,
    districts: payload.districts,
    uses: payload.uses,
    sourceType: payload.source_type,
    retrievedAt: payload.retrieved_at,
    sourceVersion: payload.source_version,
    contentHash: payload.content_hash,
    fullText: payload.full_text,
    metadata: payload.metadata ?? {},
  };
}

export async function listSources(): Promise<SourceRegistryEntry[]> {
  const response = await fetch(`${API_BASE}/ingestion/sources`, {
    headers: requestHeaders(),
  });
  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to load sources"));
  }

  const payload = (await response.json()) as {
    sources: Array<{
      source_id: string;
      title: string;
      excerpt: string;
      section_ref: string;
      jurisdiction_id?: string | null;
      url?: string | null;
      effective_date?: string | null;
      districts: string[];
      uses: string[];
    }>;
  };
  return payload.sources.map(mapSourceEntry);
}

// The catalog list omits full_text to keep the response small; fetch the full
// source (incl. full_text) on demand when opening it in the editor.
export async function getSource(sourceId: string): Promise<SourceRegistryEntry> {
  const response = await fetch(
    `${API_BASE}/ingestion/sources/${encodeURIComponent(sourceId)}`,
    { headers: requestHeaders() },
  );
  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to load source"));
  }
  return mapSourceEntry(await response.json());
}

export async function fetchSourceIndexStatus(): Promise<SourceIndexStatus> {
  const response = await fetch(`${API_BASE}/ingestion/status`, {
    headers: requestHeaders(),
  });
  if (!response.ok) {
    throw new Error(
      await parseError(response, "Failed to load source index status"),
    );
  }

  const payload = (await response.json()) as {
    source_count: number;
    chunk_count: number;
    has_index: boolean;
    index_ready?: boolean;
    auto_seed_sources?: boolean;
    auto_reindex_on_empty?: boolean;
    source_registry_version?: string | null;
    stale_source_ids?: string[];
    missing_chunk_source_ids?: string[];
    readiness_warnings?: string[];
    vector_provider?: string;
    vector_index_ready?: boolean;
    vector_count?: number;
    vector_collection?: string | null;
    vector_readiness_warnings?: string[];
    source_pack_count?: number;
    source_pack_jurisdiction_ids?: string[];
    last_import_at?: string | null;
    last_reindex_at?: string | null;
    sources_missing_metadata: Array<{
      source_id: string;
      missing_fields: string[];
    }>;
  };

  return {
    sourceCount: payload.source_count,
    chunkCount: payload.chunk_count,
    hasIndex: payload.has_index,
    indexReady: payload.index_ready ?? payload.has_index,
    autoSeedSources: payload.auto_seed_sources ?? true,
    autoReindexOnEmpty: payload.auto_reindex_on_empty ?? true,
    sourceRegistryVersion: payload.source_registry_version,
    staleSourceIds: payload.stale_source_ids ?? [],
    missingChunkSourceIds: payload.missing_chunk_source_ids ?? [],
    readinessWarnings: payload.readiness_warnings ?? [],
    vectorProvider: payload.vector_provider ?? "none",
    vectorIndexReady: payload.vector_index_ready ?? false,
    vectorCount: payload.vector_count ?? 0,
    vectorCollection: payload.vector_collection,
    vectorReadinessWarnings: payload.vector_readiness_warnings ?? [],
    sourcePackCount: payload.source_pack_count ?? 0,
    sourcePackJurisdictionIds: payload.source_pack_jurisdiction_ids ?? [],
    lastImportAt: payload.last_import_at,
    lastReindexAt: payload.last_reindex_at,
    sourcesMissingMetadata: payload.sources_missing_metadata.map((source) => ({
      sourceId: source.source_id,
      missingFields: source.missing_fields,
    })),
  };
}

export async function saveSource(
  source: SourceRegistryEntry,
): Promise<SourceRegistryEntry[]> {
  const response = await fetch(`${API_BASE}/ingestion/sources`, {
    method: "POST",
    headers: requestHeaders(
      { "Content-Type": "application/json" },
      { includeAdminAccess: true },
    ),
    body: JSON.stringify({
      source: {
        source_id: source.sourceId,
        title: source.title,
        excerpt: source.excerpt,
        section_ref: source.sectionRef,
        jurisdiction_id: source.jurisdictionId?.trim() || null,
        url: source.url?.trim() || null,
        effective_date: source.effectiveDate?.trim() || null,
        districts: source.districts,
        uses: source.uses,
      },
    }),
  });
  if (!response.ok) {
    throw new Error(await parseAdminActionError(response, "Save source"));
  }

  const payload = (await response.json()) as {
    sources: Array<{
      source_id: string;
      title: string;
      excerpt: string;
      section_ref: string;
      jurisdiction_id?: string | null;
      url?: string | null;
      effective_date?: string | null;
      districts: string[];
      uses: string[];
    }>;
  };
  return payload.sources.map(mapSourceEntry);
}

export async function reindexSources(): Promise<{
  status: string;
  sourceCount: number;
  chunkCount: number;
  vectorProvider: string;
  vectorCount: number;
  vectorIndexReady: boolean;
  vectorWarnings: string[];
}> {
  const response = await fetch(`${API_BASE}/ingestion/reindex`, {
    method: "POST",
    headers: requestHeaders({}, { includeAdminAccess: true }),
  });
  if (!response.ok) {
    throw new Error(await parseAdminActionError(response, "Reindex sources"));
  }

  const payload = (await response.json()) as {
    status: string;
    source_count: number;
    chunk_count: number;
    vector_provider?: string;
    vector_count?: number;
    vector_index_ready?: boolean;
    vector_warnings?: string[];
  };
  return {
    status: payload.status,
    sourceCount: payload.source_count,
    chunkCount: payload.chunk_count,
    vectorProvider: payload.vector_provider ?? "none",
    vectorCount: payload.vector_count ?? 0,
    vectorIndexReady: payload.vector_index_ready ?? false,
    vectorWarnings: payload.vector_warnings ?? [],
  };
}

export async function importLocalDocuments(
  directory?: string,
): Promise<LocalDocumentImportResult> {
  const response = await fetch(`${API_BASE}/ingestion/import-local-docs`, {
    method: "POST",
    headers: requestHeaders(
      { "Content-Type": "application/json" },
      { includeAdminAccess: true },
    ),
    body: JSON.stringify({ directory: directory?.trim() || null }),
  });
  if (!response.ok) {
    throw new Error(
      await parseAdminActionError(response, "Import local documents"),
    );
  }

  const payload = (await response.json()) as {
    status: string;
    imported_count: number;
    source_count: number;
    imported_source_ids: string[];
  };
  return {
    status: payload.status,
    importedCount: payload.imported_count,
    sourceCount: payload.source_count,
    importedSourceIds: payload.imported_source_ids,
  };
}

export async function importSourcePacks(
  directory?: string,
): Promise<LocalDocumentImportResult> {
  const response = await fetch(`${API_BASE}/ingestion/import-source-packs`, {
    method: "POST",
    headers: requestHeaders(
      { "Content-Type": "application/json" },
      { includeAdminAccess: true },
    ),
    body: JSON.stringify({ directory: directory?.trim() || null }),
  });
  if (!response.ok) {
    throw new Error(
      await parseAdminActionError(response, "Import source packs"),
    );
  }

  const payload = (await response.json()) as {
    status: string;
    imported_count: number;
    source_count: number;
    imported_source_ids: string[];
  };
  return {
    status: payload.status,
    importedCount: payload.imported_count,
    sourceCount: payload.source_count,
    importedSourceIds: payload.imported_source_ids,
  };
}
