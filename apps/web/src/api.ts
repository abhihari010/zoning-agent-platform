import type {
  AnalyzeResponse,
  AuditEvent,
  FollowUpQuestion,
} from "@zoning-agent/shared-schema";

const DEFAULT_API_URL = import.meta.env.PROD
  ? "https://zoning-agent-api.onrender.com"
  : "http://localhost:8000";

const API_ORIGIN = (import.meta.env.VITE_API_URL ?? DEFAULT_API_URL).replace(/\/$/, "");
const API_BASE = `${API_ORIGIN}/api/v1`;
const BETA_ACCESS_STORAGE_KEY = "zoning-agent.betaAccessKey";
const ADMIN_ACCESS_STORAGE_KEY = "zoning-agent.adminAccessKey";

function isLocalApiUrl(): boolean {
  try {
    const hostname = new URL(API_ORIGIN).hostname;
    return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
  } catch {
    return true;
  }
}

export const requiresBetaAccess = !isLocalApiUrl();

export function getBetaAccessKey(): string {
  return window.sessionStorage.getItem(BETA_ACCESS_STORAGE_KEY) ?? "";
}

export function setBetaAccessKey(value: string): void {
  const trimmed = value.trim();
  if (trimmed) {
    window.sessionStorage.setItem(BETA_ACCESS_STORAGE_KEY, trimmed);
  } else {
    window.sessionStorage.removeItem(BETA_ACCESS_STORAGE_KEY);
  }
}

export function clearBetaAccessKey(): void {
  window.sessionStorage.removeItem(BETA_ACCESS_STORAGE_KEY);
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
  const betaAccessKey = getBetaAccessKey();
  const adminAccessKey = options.includeAdminAccess ? getAdminAccessKey() : "";
  return {
    ...headers,
    ...(betaAccessKey ? { "X-Beta-Access-Key": betaAccessKey } : {}),
    ...(adminAccessKey ? { "X-Admin-Access-Key": adminAccessKey } : {}),
  };
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
  followUpQuestions: FollowUpQuestion[];
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

async function parseError(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail || fallback;
  } catch {
    return fallback;
  }
}

async function parseAdminActionError(response: Response, action: string): Promise<string> {
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

export async function intakeProject(input: {
  session_id: string;
  project_description: string;
  address: string;
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
          jurisdictionSupported: payload.trust_indicators.jurisdiction_supported,
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
          confidenceAdjustment: payload.citation_validation.confidence_adjustment,
          warnings: payload.citation_validation.warnings,
          jurisdictionId: payload.citation_validation.jurisdiction_id,
        }
      : null,
    pipelineStages: payload.pipeline_stages,
    agents: payload.agents,
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
  const response = await fetch(`${API_BASE}/projects/${input.projectId}/feedback`, {
    method: "POST",
    headers: requestHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      project_id: input.projectId,
      helpful: input.helpful,
      comment: input.comment?.trim() || null,
    }),
  });

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

export async function fetchSourceIndexStatus(): Promise<SourceIndexStatus> {
  const response = await fetch(`${API_BASE}/ingestion/status`, {
    headers: requestHeaders(),
  });
  if (!response.ok) {
    throw new Error(await parseError(response, "Failed to load source index status"));
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
    throw new Error(await parseAdminActionError(response, "Import local documents"));
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
