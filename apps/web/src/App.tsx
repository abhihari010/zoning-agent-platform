import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { createClient, type Session } from "@supabase/supabase-js";
import type {
  AnalyzeResponse,
  AuditEvent,
  FollowUpQuestion,
  PipelineStageReport,
} from "@zoning-agent/shared-schema";
import {
  clearAdminAccessKey,
  analyzeProject,
  authMode,
  clearBetaAccessKey,
  createSession,
  fetchCurrentUser,
  fetchJurisdictionCoverage,
  fetchJurisdictionRequestSummaries,
  fetchProjectResult,
  fetchSourceIndexStatus,
  fetchTrace,
  getAdminAccessKey,
  getBetaAccessKey,
  importLocalDocuments,
  importSourcePacks,
  intakeProject,
  listProjects,
  listSources,
  reindexSources,
  requiresBetaAccess,
  requestJurisdictionSupport,
  saveSource,
  setAdminAccessKey,
  setAuthToken,
  setBetaAccessKey,
  supabaseConfig,
  suggestAddresses,
  submitFeedback,
  type IntakeResponse,
  type CurrentUser,
  type CoverageStatus,
  type JurisdictionCoverage,
  type JurisdictionRequestSummary,
  type ProjectSummary,
  type SourceIndexStatus,
  type SourceRegistryEntry,
} from "./api";
import { EvidencePanel, TrustIndicatorBar, UnsupportedJurisdiction } from "./components/ResultTrust";

const DISCLAIMER =
  "Educational guidance only. Zoning rules, permit triggers, and code interpretations must be verified with the official planning department before you rely on this result.";
const PIPELINE_STAGE_COUNT = 5;
const supabase =
  authMode === "supabase" && supabaseConfig.url && supabaseConfig.anonKey
    ? createClient(supabaseConfig.url, supabaseConfig.anonKey)
    : null;

type Workspace = "assistant" | "admin";
type Phase = "idle" | "intake" | "analyzing" | "done" | "error";
type FeedbackState = "idle" | "submitting" | "submitted";
type ResultView = "checklist" | "evidence" | "trace";
type LegalPage = "terms" | "privacy" | "disclaimer" | null;

interface IntakeFacts {
  useType: string;
  constructionScope: string;
  operatingHours: string;
  employeeCount: string;
  parkingLoading: string;
  foodFireHealth: boolean;
}

function emptySourceForm(): SourceRegistryEntry {
  return {
    sourceId: "",
    title: "",
    excerpt: "",
    sectionRef: "",
    jurisdictionId: "blacksburg-va",
    url: "",
    effectiveDate: "",
    districts: [],
    uses: [],
  };
}

function parseTagList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function emptyIntakeFacts(): IntakeFacts {
  return {
    useType: "",
    constructionScope: "",
    operatingHours: "",
    employeeCount: "",
    parkingLoading: "",
    foodFireHealth: false,
  };
}

function buildProjectContext(projectDescription: string, facts: IntakeFacts): string {
  const factLines = [
    ["Use type", facts.useType],
    ["Construction scope", facts.constructionScope],
    ["Operating hours", facts.operatingHours],
    ["Number of employees", facts.employeeCount],
    ["Parking/loading", facts.parkingLoading],
    ["Food/fire/health triggers", facts.foodFireHealth ? "Yes" : ""],
  ]
    .filter(([, value]) => value.trim())
    .map(([label, value]) => `- ${label}: ${value.trim()}`);

  if (factLines.length === 0) {
    return projectDescription.trim();
  }

  return [
    projectDescription.trim(),
    "",
    "Structured zoning facts:",
    ...factLines,
  ].join("\n");
}

function formatDateTime(value?: string | null): string {
  if (!value) {
    return "Not recorded";
  }
  return new Date(value).toLocaleString();
}

function formatLocationParts(...parts: Array<string | null | undefined>): string {
  const values = parts.map((part) => part?.trim()).filter(Boolean);
  return values.length > 0 ? values.join(" / ") : "Location not recorded";
}

function decisionLabel(decision: AnalyzeResponse["feasibility"]["decision"]): string {
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

function decisionTone(decision: AnalyzeResponse["feasibility"]["decision"]): string {
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

function statusTone(status: PipelineStageReport["status"], isActive: boolean): string {
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

function confidenceLabel(confidence: number): string {
  if (confidence >= 0.75) {
    return "Strong";
  }
  if (confidence >= 0.6) {
    return "Moderate";
  }
  return "Needs review";
}

function confidenceTone(confidence: number, citationCount: number): string {
  if (citationCount === 0 || confidence < 0.6) {
    return "border-red-200 bg-red-50 text-red-900";
  }
  if (confidence < 0.75) {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  return "border-emerald-200 bg-emerald-50 text-emerald-900";
}

function evidenceTone(citationCount: number): string {
  if (citationCount === 0) {
    return "border-red-200 bg-red-50 text-red-900";
  }
  if (citationCount < 2) {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  return "border-emerald-200 bg-emerald-50 text-emerald-900";
}

function evidenceLabel(citationCount: number): string {
  if (citationCount === 0) {
    return "No cited sources";
  }
  if (citationCount === 1) {
    return "1 cited source";
  }
  return `${citationCount} cited sources`;
}

function supportStatusLabel(status?: IntakeResponse["supportStatus"]): string {
  if (status === "unsupported") {
    return "Recognized, not covered";
  }
  if (status === "invalid") {
    return "Invalid or unverified";
  }
  return "Supported";
}

function supportStatusTone(status?: IntakeResponse["supportStatus"]): string {
  if (status === "unsupported") {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  if (status === "invalid") {
    return "border-red-200 bg-red-50 text-red-900";
  }
  return "border-emerald-200 bg-emerald-50 text-emerald-900";
}

function coverageLabel(status?: CoverageStatus | null): string {
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

function coverageTone(status?: CoverageStatus | null): string {
  if (status === "public_supported") {
    return "border-emerald-200 bg-emerald-50 text-emerald-900";
  }
  if (status === "qa_ready" || status === "source_indexed") {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function legalCopy(page: Exclude<LegalPage, null>): { title: string; paragraphs: string[] } {
  if (page === "privacy") {
    return {
      title: "Privacy Policy",
      paragraphs: [
        "We store account identity, project addresses, project descriptions, generated analyses, feedback, and jurisdiction support requests so users can return to their work and so we can improve coverage.",
        "Do not submit confidential legal, financial, medical, or highly sensitive personal information. You can request deletion of stored project data by contacting the app operator.",
        "Operational logs may include timestamps, route names, and non-secret status information. Access tokens, passwords, and beta keys should never be logged or printed.",
      ],
    };
  }
  if (page === "terms") {
    return {
      title: "Terms of Use",
      paragraphs: [
        "This application provides educational zoning guidance and workflow support. It is not a law firm, government office, permit issuer, or substitute for professional advice.",
        "Users are responsible for verifying every zoning conclusion, permit requirement, and citation with the official planning, building, health, or fire authority before taking action.",
        "Coverage can change as local codes, maps, source availability, and QA status change. The product may decline to answer when source coverage is incomplete.",
      ],
    };
  }
  return {
    title: "Disclaimer",
    paragraphs: [
      "Zoning Review Platform is not legal advice and is not official municipal approval.",
      "A result means the app found a source-backed educational interpretation. It does not grant permits, approvals, variances, inspections, licenses, or occupancy rights.",
      "Always verify parcel zoning, overlays, permitted-use tables, recent amendments, and procedural requirements with the official planning office.",
    ],
  };
}

function intakeErrorMessage(intakeResult: IntakeResponse): string {
  if (intakeResult.supportStatus === "unsupported") {
    const jurisdiction = intakeResult.jurisdictionName ?? "this jurisdiction";
    return `${jurisdiction} was recognized, but source coverage is not ready for zoning review yet. Try a supported jurisdiction or contact the planning office directly.`;
  }
  return "The address could not be validated. Enter a complete street address with city and state, then try again.";
}

function readinessTone(indexStatus: SourceIndexStatus | null): string {
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

function readinessLabel(indexStatus: SourceIndexStatus | null): string {
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

function buildChecklistDownload(
  intake: IntakeResponse | null,
  result: AnalyzeResponse,
  projectDescription: string,
): string {
  return [
    "Zoning Agent Checklist",
    "",
    `Project: ${projectDescription.trim()}`,
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

export function App() {
  const [authSession, setAuthSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(authMode === "supabase");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authMessage, setAuthMessage] = useState("");
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsMessage, setProjectsMessage] = useState("");
  const [coverage, setCoverage] = useState<JurisdictionCoverage[]>([]);
  const [coverageMessage, setCoverageMessage] = useState("");
  const [legalPage, setLegalPage] = useState<LegalPage>(null);
  const [jurisdictionRequestMessage, setJurisdictionRequestMessage] = useState("");
  const [jurisdictionRequestSubmitting, setJurisdictionRequestSubmitting] = useState(false);
  const [betaAccessKey, setStoredBetaAccessKey] = useState(() => getBetaAccessKey());
  const [betaAccessInput, setBetaAccessInput] = useState("");
  const [betaAccessError, setBetaAccessError] = useState("");
  const [workspace, setWorkspace] = useState<Workspace>("assistant");
  const [acceptedDisclaimer, setAcceptedDisclaimer] = useState(false);
  const [projectDescription, setProjectDescription] = useState("");
  const [intakeFacts, setIntakeFacts] = useState<IntakeFacts>(emptyIntakeFacts);
  const [address, setAddress] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [autocompleteSession] = useState(() => crypto.randomUUID());
  const [phase, setPhase] = useState<Phase>("idle");
  const [activeStageIndex, setActiveStageIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [intake, setIntake] = useState<IntakeResponse | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [trace, setTrace] = useState<AuditEvent[]>([]);
  const [traceLoading, setTraceLoading] = useState(false);
  const [feedbackNote, setFeedbackNote] = useState("");
  const [feedbackState, setFeedbackState] = useState<FeedbackState>("idle");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [resultView, setResultView] = useState<ResultView>("checklist");
  const [clarificationOpen, setClarificationOpen] = useState(false);
  const [clarificationQuestions, setClarificationQuestions] = useState<FollowUpQuestion[]>([]);
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const [clarificationSubmitting, setClarificationSubmitting] = useState(false);
  const [sources, setSources] = useState<SourceRegistryEntry[]>([]);
  const [indexStatus, setIndexStatus] = useState<SourceIndexStatus | null>(null);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourceForm, setSourceForm] = useState<SourceRegistryEntry>(emptySourceForm);
  const [sourceMessage, setSourceMessage] = useState("");
  const [sourceSaving, setSourceSaving] = useState(false);
  const [jurisdictionRequests, setJurisdictionRequests] = useState<JurisdictionRequestSummary[]>([]);
  const [jurisdictionRequestsLoading, setJurisdictionRequestsLoading] = useState(false);
  const [jurisdictionRequestsMessage, setJurisdictionRequestsMessage] = useState("");
  const [reindexMessage, setReindexMessage] = useState("");
  const [importDirectory, setImportDirectory] = useState("");
  const [importing, setImporting] = useState(false);
  const [importMessage, setImportMessage] = useState("");
  const [adminAccessKey, setStoredAdminAccessKey] = useState(() => getAdminAccessKey());
  const [adminAccessInput, setAdminAccessInput] = useState("");
  const [adminAccessMessage, setAdminAccessMessage] = useState("");
  const addressSectionRef = useRef<HTMLDivElement | null>(null);
  const isSupabaseAuthenticated = authMode !== "supabase" || Boolean(authSession);
  const canUseBetaAccess = authMode === "beta" && (!requiresBetaAccess || Boolean(betaAccessKey));
  const canLoadPrivateData =
    authMode === "supabase" ? Boolean(authSession) : authMode === "beta" ? canUseBetaAccess : true;
  const canUseAdminTools =
    authMode === "supabase" ? currentUser?.role === "admin" : true;
  const publicSupportedCoverage = useMemo(
    () => coverage.filter((item) => item.coverageStatus === "public_supported"),
    [coverage],
  );
  const indexedCoverage = useMemo(
    () => coverage.filter((item) => item.coverageStatus === "source_indexed"),
    [coverage],
  );
  const currentCoverage = useMemo(
    () => coverage.find((item) => item.jurisdictionId === intake?.jurisdictionId),
    [coverage, intake?.jurisdictionId],
  );
  const coverageByJurisdictionId = useMemo(
    () => new Map(coverage.map((item) => [item.jurisdictionId, item])),
    [coverage],
  );
  const coverageByJurisdictionName = useMemo(
    () => new Map(coverage.map((item) => [item.name.toLowerCase(), item])),
    [coverage],
  );

  useEffect(() => {
    if (!supabase) {
      setAuthLoading(false);
      return;
    }

    let cancelled = false;
    supabase.auth.getSession().then(({ data }) => {
      if (cancelled) {
        return;
      }
      const session = data.session;
      setAuthSession(session);
      setAuthToken(session?.access_token ?? "");
      setAuthLoading(false);
    });

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setAuthSession(session);
      setAuthToken(session?.access_token ?? "");
      setCurrentUser(null);
      setProjects([]);
    });

    return () => {
      cancelled = true;
      subscription.subscription.unsubscribe();
    };
  }, []);

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

  useEffect(() => {
    if (!canLoadPrivateData) {
      return;
    }

    let cancelled = false;

    async function loadCurrentUser() {
      try {
        const user = await fetchCurrentUser();
        if (!cancelled) {
          setCurrentUser(user);
        }
      } catch {
        if (!cancelled) {
          setCurrentUser(null);
        }
      }
    }

    void loadCurrentUser();
    return () => {
      cancelled = true;
    };
  }, [canLoadPrivateData, authSession, betaAccessKey]);

  useEffect(() => {
    if (!canLoadPrivateData || !canUseAdminTools) {
      setJurisdictionRequests([]);
      setJurisdictionRequestsMessage("");
      setJurisdictionRequestsLoading(false);
      return;
    }

    let cancelled = false;

    async function loadJurisdictionRequests() {
      try {
        setJurisdictionRequestsLoading(true);
        const summaries = await fetchJurisdictionRequestSummaries();
        if (!cancelled) {
          setJurisdictionRequests(summaries);
          setJurisdictionRequestsMessage("");
        }
      } catch (requestError) {
        if (!cancelled) {
          setJurisdictionRequests([]);
          setJurisdictionRequestsMessage(
            requestError instanceof Error
              ? requestError.message
              : "Failed to load jurisdiction requests.",
          );
        }
      } finally {
        if (!cancelled) {
          setJurisdictionRequestsLoading(false);
        }
      }
    }

    void loadJurisdictionRequests();
    return () => {
      cancelled = true;
    };
  }, [canLoadPrivateData, canUseAdminTools, authSession, betaAccessKey, adminAccessKey]);

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

  useEffect(() => {
    if (phase !== "analyzing") {
      return;
    }

    const interval = window.setInterval(() => {
      setActiveStageIndex((current) => (current + 1) % PIPELINE_STAGE_COUNT);
    }, 1200);

    return () => window.clearInterval(interval);
  }, [phase]);

  useEffect(() => {
    if (!intake || intake.status !== "created") {
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
  }, [intake, result, phase]);

  useEffect(() => {
    if (!canLoadPrivateData) {
      return;
    }

    let cancelled = false;

    async function loadSources() {
      try {
        setSourcesLoading(true);
        const [nextSources, nextIndexStatus] = await Promise.all([
          listSources(),
          fetchSourceIndexStatus(),
        ]);
        if (!cancelled) {
          setSources(nextSources);
          setIndexStatus(nextIndexStatus);
        }
      } catch (loadError) {
        if (!cancelled) {
          setSourceMessage(
            loadError instanceof Error ? loadError.message : "Failed to load sources.",
          );
        }
      } finally {
        if (!cancelled) {
          setSourcesLoading(false);
        }
      }
    }

    void loadSources();
    return () => {
      cancelled = true;
    };
  }, [canLoadPrivateData, authSession, betaAccessKey]);

  useEffect(() => {
    if (authMode !== "supabase" || !authSession) {
      setProjects([]);
      return;
    }

    void refreshProjects();
  }, [authSession]);

  useEffect(() => {
    if (workspace === "admin" && !canUseAdminTools) {
      setWorkspace("assistant");
    }
  }, [workspace, canUseAdminTools]);

  const canSubmit = useMemo(
    () =>
      acceptedDisclaimer &&
      projectDescription.trim().length >= 10 &&
      address.trim().length >= 5,
    [acceptedDisclaimer, projectDescription, address],
  );

  const displayedStages = useMemo(() => {
    const loadingStages: PipelineStageReport[] = [
      {
        key: "intake",
        label: "Understand Project",
        status: "completed",
        headline: "Interpreting the project, use type, and missing details.",
        details: ["Extracting the project goal from plain English."],
      },
      {
        key: "location",
        label: "Resolve Property",
        status: "completed",
        headline: "Checking jurisdiction, address validity, and zoning district context.",
        details: ["Preparing location metadata for source retrieval."],
      },
      {
        key: "retrieval",
        label: "Retrieve Sources",
        status: "completed",
        headline: "Looking up district rules, permit triggers, and ordinance excerpts.",
        details: ["Searching the municipal source registry."],
      },
      {
        key: "compliance",
        label: "Analyze Compliance",
        status: "completed",
        headline: "Evaluating the retrieved evidence against the project facts.",
        details: ["Checking whether the evidence supports a zoning conclusion."],
      },
      {
        key: "checklist",
        label: "Generate Checklist",
        status: "completed",
        headline: "Turning the zoning evidence into a permit path and plain-language answer.",
        details: ["Producing the feasibility summary and next steps."],
      },
    ];

    return result?.pipelineStages?.length
      ? result.pipelineStages
      : result?.agents.length
        ? result.agents
        : loadingStages;
  }, [result]);

  const assistantPrompts = useMemo(() => {
    const prompts: string[] = [];
    if (intake) {
      prompts.push(...intake.followUpQuestions.map((question) => question.question));
    }
    if (result) {
      prompts.push(...result.followUpQuestions.map((question) => question.question));
      prompts.push(...result.warnings);
    }
    return Array.from(new Set(prompts));
  }, [intake, result]);

  const sourceHealthById = useMemo(() => {
    const entries = indexStatus?.sourcesMissingMetadata ?? [];
    return new Map(entries.map((source) => [source.sourceId, source.missingFields]));
  }, [indexStatus]);

  const sourceIndexIssuesById = useMemo(() => {
    const issues = new Map<string, string[]>();
    for (const sourceId of indexStatus?.staleSourceIds ?? []) {
      issues.set(sourceId, [...(issues.get(sourceId) ?? []), "Stale index"]);
    }
    for (const sourceId of indexStatus?.missingChunkSourceIds ?? []) {
      issues.set(sourceId, [...(issues.get(sourceId) ?? []), "Missing chunks"]);
    }
    return issues;
  }, [indexStatus]);

  function coverageForRequest(
    request: JurisdictionRequestSummary,
  ): JurisdictionCoverage | undefined {
    if (request.jurisdictionId) {
      const byId = coverageByJurisdictionId.get(request.jurisdictionId);
      if (byId) {
        return byId;
      }
    }
    if (request.jurisdictionName) {
      return coverageByJurisdictionName.get(request.jurisdictionName.toLowerCase());
    }
    return undefined;
  }

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

  async function refreshSources(message?: string) {
    const [nextSources, nextIndexStatus] = await Promise.all([
      listSources(),
      fetchSourceIndexStatus(),
    ]);
    setSources(nextSources);
    setIndexStatus(nextIndexStatus);
    if (message) {
      setSourceMessage(message);
    }
  }

  async function refreshProjects(message?: string) {
    if (authMode !== "supabase") {
      return;
    }
    try {
      setProjectsLoading(true);
      const nextProjects = await listProjects();
      setProjects(nextProjects);
      if (message) {
        setProjectsMessage(message);
      }
    } catch (projectError) {
      setProjectsMessage(
        projectError instanceof Error ? projectError.message : "Failed to load projects.",
      );
    } finally {
      setProjectsLoading(false);
    }
  }

  async function signIn() {
    if (!supabase) {
      setAuthMessage("Supabase is not configured for this deployment.");
      return;
    }
    if (!authEmail.trim() || !authPassword) {
      setAuthMessage("Enter your email and password.");
      return;
    }

    setAuthLoading(true);
    setAuthMessage("");
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email: authEmail.trim(),
      password: authPassword,
    });
    if (signInError) {
      setAuthMessage(signInError.message);
    }
    setAuthLoading(false);
  }

  async function signUp() {
    if (!supabase) {
      setAuthMessage("Supabase is not configured for this deployment.");
      return;
    }
    if (!authEmail.trim() || authPassword.length < 8) {
      setAuthMessage("Enter an email and a password with at least 8 characters.");
      return;
    }

    setAuthLoading(true);
    setAuthMessage("");
    const { error: signUpError } = await supabase.auth.signUp({
      email: authEmail.trim(),
      password: authPassword,
    });
    setAuthMessage(
      signUpError
        ? signUpError.message
        : "Account created. Check your email if confirmation is required, then sign in.",
    );
    setAuthLoading(false);
  }

  async function signOut() {
    if (supabase) {
      await supabase.auth.signOut();
    }
    setAuthToken("");
    setCurrentUser(null);
    setProjects([]);
    resetWorkspace();
  }

  function unlockPrivateBeta() {
    if (!betaAccessInput.trim()) {
      setBetaAccessError("Enter the private beta access key.");
      return;
    }

    setBetaAccessKey(betaAccessInput);
    setStoredBetaAccessKey(betaAccessInput.trim());
    setBetaAccessInput("");
    setBetaAccessError("");
    setSourceMessage("");
  }

  function changePrivateBetaKey() {
    clearBetaAccessKey();
    setStoredBetaAccessKey("");
    setBetaAccessInput("");
    setBetaAccessError("");
    setSources([]);
    setIndexStatus(null);
  }

  function saveAdminKey() {
    if (!adminAccessInput.trim()) {
      setAdminAccessMessage("Enter the source admin key to enable write actions.");
      return;
    }

    setAdminAccessKey(adminAccessInput);
    setStoredAdminAccessKey(adminAccessInput.trim());
    setAdminAccessInput("");
    setAdminAccessMessage("Source admin key saved for this browser session.");
  }

  function clearStoredAdminKey() {
    clearAdminAccessKey();
    setStoredAdminAccessKey("");
    setAdminAccessInput("");
    setAdminAccessMessage("Source admin key cleared. Source status and catalog remain visible.");
  }

  async function runAnalysis(projectId: string, answers?: Record<string, string>) {
    setPhase("analyzing");
    setActiveStageIndex(0);
    const analysis = await analyzeProject(projectId, answers);
    setResult(analysis);
    setPhase("done");

    if (analysis.status === "needs_clarification" && analysis.followUpQuestions.length > 0) {
      const nextAnswers = analysis.followUpQuestions.reduce<Record<string, string>>(
        (accumulator, question) => {
          accumulator[question.question] = clarificationAnswers[question.question] ?? "";
          return accumulator;
        },
        {},
      );
      setClarificationQuestions(analysis.followUpQuestions);
      setClarificationAnswers(nextAnswers);
      setClarificationOpen(true);
    }
  }

  async function onSubmit() {
    if (!canSubmit) {
      return;
    }

    setError(null);
    setResult(null);
    setIntake(null);
    setTrace([]);
    setFeedbackNote("");
    setFeedbackState("idle");
    setFeedbackMessage("");
    setJurisdictionRequestMessage("");
    setResultView("checklist");
    setClarificationOpen(false);
    setClarificationQuestions([]);
    setClarificationAnswers({});

    try {
      setPhase("intake");
      const sessionId = await createSession();
      const projectContext = buildProjectContext(projectDescription, intakeFacts);
      const intakeResult = await intakeProject({
        session_id: sessionId,
        project_description: projectContext,
        address: address.trim(),
      });
      setIntake(intakeResult);

      if (intakeResult.status !== "created") {
        setPhase("error");
        setError(intakeErrorMessage(intakeResult));
        return;
      }

      if (intakeResult.supportStatus === "unsupported") {
        setPhase("error");
        setError(intakeErrorMessage(intakeResult));
        return;
      }

      await runAnalysis(intakeResult.projectId);
      await refreshProjects();
    } catch (submitError) {
      setPhase("error");
      setError(
        submitError instanceof Error ? submitError.message : "Something went wrong during analysis.",
      );
    }
  }

  async function onSubmitClarifications() {
    if (!intake) {
      return;
    }

    const unanswered = clarificationQuestions.some(
      (question) => !clarificationAnswers[question.question]?.trim(),
    );
    if (unanswered) {
      setError("Please answer each clarification so we can continue the review.");
      return;
    }

    try {
      setError(null);
      setClarificationSubmitting(true);
      setClarificationOpen(false);
      await runAnalysis(intake.projectId, clarificationAnswers);
    } catch (clarificationError) {
      setPhase("error");
      setError(
        clarificationError instanceof Error
          ? clarificationError.message
          : "Clarification request failed.",
      );
    } finally {
      setClarificationSubmitting(false);
    }
  }

  async function onSubmitFeedback(helpful: boolean) {
    if (!intake || feedbackState === "submitting") {
      return;
    }

    try {
      setFeedbackState("submitting");
      await submitFeedback({
        projectId: intake.projectId,
        helpful,
        comment: feedbackNote,
      });
      setFeedbackState("submitted");
      setFeedbackMessage(
        helpful
          ? "Thanks. That tells us the workflow is landing in the right place."
          : "Thanks. We’ll treat that as a signal to tighten the workflow.",
      );
    } catch (feedbackError) {
      setFeedbackState("idle");
      setFeedbackMessage(
        feedbackError instanceof Error
          ? feedbackError.message
          : "Feedback submission failed.",
      );
    }
  }

  async function openSavedProject(project: ProjectSummary) {
    try {
      setProjectsMessage("");
      setWorkspace("assistant");
      setPhase("done");
      setError(null);
      setProjectDescription("");
      setAddress(project.normalizedAddress);
      setIntake({
        projectId: project.projectId,
        normalizedAddress: project.normalizedAddress,
        district: project.district,
        status: "created",
        supportStatus: "supported",
        jurisdictionId: project.jurisdictionId,
        jurisdictionName: project.jurisdictionName,
        followUpQuestions: [],
      });
      const savedResult = await fetchProjectResult(project.projectId);
      setResult(savedResult);
      setResultView("checklist");
    } catch (projectError) {
      setProjectsMessage(
        projectError instanceof Error ? projectError.message : "Failed to open saved project.",
      );
    }
  }

  function downloadChecklist() {
    if (!result) {
      return;
    }

    const blob = new Blob(
      [buildChecklistDownload(intake, result, buildProjectContext(projectDescription, intakeFacts))],
      { type: "text/plain;charset=utf-8" },
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "zoning-checklist.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function onSaveSource() {
    if (
      !sourceForm.sourceId.trim() ||
      !sourceForm.title.trim() ||
      !sourceForm.excerpt.trim() ||
      !sourceForm.sectionRef.trim()
    ) {
      setSourceMessage("Source ID, title, excerpt, and section reference are required.");
      return;
    }

    try {
      setSourceSaving(true);
      setSourceMessage("");
      const saved = await saveSource({
        ...sourceForm,
        sourceId: sourceForm.sourceId.trim(),
        title: sourceForm.title.trim(),
        excerpt: sourceForm.excerpt.trim(),
        sectionRef: sourceForm.sectionRef.trim(),
      });
      setSources(saved);
      setIndexStatus(await fetchSourceIndexStatus());
      setSourceForm(emptySourceForm());
      setSourceMessage("Source saved.");
    } catch (saveError) {
      setSourceMessage(
        saveError instanceof Error ? saveError.message : "Failed to save source.",
      );
    } finally {
      setSourceSaving(false);
    }
  }

  async function onReindexSources() {
    try {
      setReindexMessage("");
      const summary = await reindexSources();
      setReindexMessage(
        `Reindex ${summary.status}. ${summary.sourceCount} sources produced ${summary.chunkCount} chunks and ${summary.vectorCount} vectors.`,
      );
      await refreshSources();
    } catch (reindexError) {
      setReindexMessage(
        reindexError instanceof Error
          ? reindexError.message
          : "Failed to request reindex.",
      );
    }
  }

  async function onImportDocuments() {
    try {
      setImporting(true);
      setImportMessage("");
      const importResult = await importLocalDocuments(importDirectory);
      await refreshSources(
        `Imported ${importResult.importedCount} document(s). ${importResult.sourceCount} sources now available.`,
      );
      setImportMessage(
        importResult.importedSourceIds.length > 0
          ? `Imported: ${importResult.importedSourceIds.join(", ")}`
          : "No documents were imported.",
      );
    } catch (importError) {
      setImportMessage(
        importError instanceof Error
          ? importError.message
          : "Failed to import local documents.",
      );
    } finally {
      setImporting(false);
    }
  }

  async function onImportSourcePacks() {
    try {
      setImporting(true);
      setImportMessage("");
      const importResult = await importSourcePacks(importDirectory);
      await refreshSources(
        `Imported ${importResult.importedCount} source-pack record(s). ${importResult.sourceCount} sources now available.`,
      );
      setImportMessage(
        importResult.importedSourceIds.length > 0
          ? `Imported source packs: ${importResult.importedSourceIds.join(", ")}`
          : "No source-pack records were imported.",
      );
    } catch (importError) {
      setImportMessage(
        importError instanceof Error
          ? importError.message
          : "Failed to import source packs.",
      );
    } finally {
      setImporting(false);
    }
  }

  async function onRequestJurisdictionSupport() {
    if (!intake || intake.supportStatus !== "unsupported") {
      return;
    }
    try {
      setJurisdictionRequestSubmitting(true);
      setJurisdictionRequestMessage("");
      const requestResult = await requestJurisdictionSupport({
        normalizedAddress: intake.normalizedAddress,
        jurisdictionId: intake.jurisdictionId,
        jurisdictionName: intake.jurisdictionName,
        requestedUseType: intakeFacts.useType || null,
      });
      setJurisdictionRequestMessage(
        requestResult.status === "existing"
          ? `You're already on the request list for ${requestResult.jurisdictionName ?? "this jurisdiction"}.`
          : `Request noted. ${requestResult.requestCount} request${requestResult.requestCount === 1 ? "" : "s"} logged for ${requestResult.jurisdictionName ?? "this jurisdiction"}.`,
      );
    } catch (requestError) {
      setJurisdictionRequestMessage(
        requestError instanceof Error
          ? requestError.message
          : "Failed to request jurisdiction support.",
      );
    } finally {
      setJurisdictionRequestSubmitting(false);
    }
  }

  function loadSourceIntoForm(source: SourceRegistryEntry) {
    setWorkspace("admin");
    setSourceForm(source);
    setSourceMessage(`Loaded ${source.sourceId} into the editor.`);
  }

  function resetWorkspace() {
    setAcceptedDisclaimer(false);
    setProjectDescription("");
    setIntakeFacts(emptyIntakeFacts());
    setAddress("");
    setSuggestions([]);
    setActiveSuggestionIndex(-1);
    setPhase("idle");
    setError(null);
    setIntake(null);
    setResult(null);
    setTrace([]);
    setFeedbackNote("");
    setFeedbackState("idle");
    setFeedbackMessage("");
    setJurisdictionRequestMessage("");
    setResultView("checklist");
    setClarificationOpen(false);
    setClarificationQuestions([]);
    setClarificationAnswers({});
  }

  const showHumanFallback =
    result?.status === "low_confidence" || result?.feasibility.decision === "unknown";

  if (authMode === "supabase" && (authLoading || !isSupabaseAuthenticated)) {
    const legal = legalPage ? legalCopy(legalPage) : null;
    return (
      <main className="min-h-screen bg-[linear-gradient(180deg,#f8f3ea_0%,#efe5d5_100%)] px-4 py-6 text-slate-900 md:px-8">
        <div className="mx-auto grid max-w-6xl gap-5 lg:grid-cols-[minmax(0,1.2fr)_420px]">
          <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
              Public Zoning Guidance
            </p>
            <h1 className="mt-3 font-heading text-4xl leading-tight text-pine md:text-5xl">
              Zoning Review Platform
            </h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-slate-700">
              Check whether a proposed project has source-backed zoning guidance, get a permit
              checklist, and request coverage when your jurisdiction is not ready yet.
            </p>
            <div className="mt-6 grid gap-3 md:grid-cols-3">
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-950">
                <p className="text-xs font-semibold uppercase tracking-[0.16em]">Supported</p>
                <p className="mt-2 text-2xl font-semibold">{publicSupportedCoverage.length}</p>
                <p className="mt-1 text-xs leading-5">Public jurisdictions with QA-backed answers.</p>
              </div>
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-950">
                <p className="text-xs font-semibold uppercase tracking-[0.16em]">Indexed</p>
                <p className="mt-2 text-2xl font-semibold">{indexedCoverage.length}</p>
                <p className="mt-1 text-xs leading-5">Source packs being prepared for QA.</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-slate-700">
                <p className="text-xs font-semibold uppercase tracking-[0.16em]">US Coverage</p>
                <p className="mt-2 text-2xl font-semibold">Request-led</p>
                <p className="mt-1 text-xs leading-5">Unsupported places become backlog signals.</p>
              </div>
            </div>
            <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                Current Coverage
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {coverage.slice(0, 8).map((item) => (
                  <span
                    key={item.jurisdictionId}
                    className={`rounded-full border px-3 py-1 text-xs font-semibold ${coverageTone(item.coverageStatus)}`}
                  >
                    {item.name}: {coverageLabel(item.coverageStatus)}
                  </span>
                ))}
                {coverageMessage && (
                  <span className="text-sm text-slate-600">{coverageMessage}</span>
                )}
              </div>
            </div>
            <p className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
              {DISCLAIMER}
            </p>
            <div className="mt-5 flex flex-wrap gap-3 text-sm font-semibold text-slate-600">
              <button type="button" onClick={() => setLegalPage("terms")}>Terms</button>
              <button type="button" onClick={() => setLegalPage("privacy")}>Privacy</button>
              <button type="button" onClick={() => setLegalPage("disclaimer")}>Disclaimer</button>
            </div>
          </section>

          <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
              Account Access
            </p>
            <h2 className="mt-3 font-heading text-3xl text-pine">Sign in to start</h2>
            <p className="mt-3 text-sm leading-6 text-slate-700">
              Save reviews, reopen prior projects, and request support for uncovered jurisdictions.
            </p>
            <label className="mt-6 block text-sm font-semibold text-slate-700">
              Email
              <input
                className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
                type="email"
                value={authEmail}
                onChange={(event) => setAuthEmail(event.target.value)}
              />
            </label>
            <label className="mt-4 block text-sm font-semibold text-slate-700">
              Password
              <input
                className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
                type="password"
                value={authPassword}
                onChange={(event) => setAuthPassword(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void signIn();
                  }
                }}
              />
            </label>
            {authMessage && (
              <p className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                {authMessage}
              </p>
            )}
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => {
                  void signIn();
                }}
                disabled={authLoading}
                className="rounded-2xl bg-pine px-4 py-3 font-semibold text-white disabled:opacity-60"
              >
                {authLoading ? "Signing in..." : "Sign in"}
              </button>
              <button
                type="button"
                onClick={() => {
                  void signUp();
                }}
                disabled={authLoading}
                className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700 disabled:opacity-60"
              >
                Create account
              </button>
            </div>
          </section>
        </div>
        {legal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
            <section className="w-full max-w-2xl rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                Public Disclosure
              </p>
              <h2 className="mt-2 font-heading text-3xl text-pine">{legal.title}</h2>
              <div className="mt-5 space-y-4 text-sm leading-7 text-slate-700">
                {legal.paragraphs.map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setLegalPage(null)}
                className="mt-6 rounded-2xl bg-pine px-4 py-3 font-semibold text-white"
              >
                Close
              </button>
            </section>
          </div>
        )}
      </main>
    );
  }

  if (authMode === "beta" && requiresBetaAccess && !betaAccessKey) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[linear-gradient(180deg,#f8f3ea_0%,#efe5d5_100%)] px-4 text-slate-900">
        <section className="w-full max-w-md rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
            Private Beta
          </p>
          <h1 className="mt-3 font-heading text-3xl text-pine">Zoning Review Platform</h1>
          <p className="mt-3 text-sm leading-6 text-slate-700">
            Enter your beta access key to open the zoning review workspace.
          </p>
          <label className="mt-6 block text-sm font-semibold text-slate-700">
            Access key
            <input
              className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
              type="password"
              value={betaAccessInput}
              onChange={(event) => setBetaAccessInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  unlockPrivateBeta();
                }
              }}
            />
          </label>
          {betaAccessError && (
            <p className="mt-3 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {betaAccessError}
            </p>
          )}
          <button
            type="button"
            onClick={unlockPrivateBeta}
            className="mt-5 w-full rounded-2xl bg-pine px-4 py-3 font-semibold text-white"
          >
            Unlock beta
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(217,120,85,0.10),transparent_24%),linear-gradient(180deg,#f8f3ea_0%,#efe5d5_100%)] text-slate-900">
      <div className="mx-auto max-w-6xl px-4 py-5 md:px-8 md:py-8">
        <section className="mb-5 grid gap-5 rounded-[28px] border border-pine/10 bg-white/90 p-6 shadow-card backdrop-blur lg:grid-cols-[minmax(0,1.5fr)_320px]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
              Zoning Review Platform
            </p>
            <h1 className="mt-3 max-w-4xl font-heading text-3xl leading-tight text-pine md:text-[2.75rem]">
              Check whether a project is allowed on a property and get the next permit steps.
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-700 md:text-base">
              This workspace runs one orchestrated zoning pipeline: it understands the request,
              checks property context, retrieves municipal code evidence, and turns that into a
              feasibility summary plus a permit checklist.
            </p>
          </div>

          <div className="flex flex-col justify-between gap-4">
            <div className="rounded-3xl border border-amber-200 bg-amber-50/90 p-4 text-sm leading-6 text-amber-950">
              {DISCLAIMER}
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setWorkspace("assistant")}
                className={`flex-1 rounded-2xl px-4 py-3 text-sm font-semibold ${
                  workspace === "assistant"
                    ? "bg-pine text-white"
                    : "border border-slate-300 bg-white text-slate-700"
                }`}
              >
                Assistant
              </button>
              {canUseAdminTools && (
                <button
                  type="button"
                  onClick={() => setWorkspace("admin")}
                  className={`flex-1 rounded-2xl px-4 py-3 text-sm font-semibold ${
                    workspace === "admin"
                      ? "bg-clay text-white"
                      : "border border-slate-300 bg-white text-slate-700"
                  }`}
                >
                  Source Admin
                </button>
              )}
            </div>
            {authMode === "supabase" && (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                <p className="font-semibold text-slate-900">
                  {currentUser?.email ?? authSession?.user.email ?? "Signed in"}
                </p>
                <div className="mt-2 flex items-center justify-between gap-3">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-500">
                    {currentUser?.role ?? "user"}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      void signOut();
                    }}
                    className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500"
                  >
                    Sign out
                  </button>
                </div>
              </div>
            )}
            {authMode === "beta" && requiresBetaAccess && (
              <button
                type="button"
                onClick={changePrivateBetaKey}
                className="text-left text-xs font-semibold uppercase tracking-[0.18em] text-slate-500"
              >
                Change beta key
              </button>
            )}
          </div>
        </section>

        {workspace === "assistant" ? (
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
            <section className="space-y-6">
              <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
                <div className="mb-5 grid gap-4 rounded-3xl border border-slate-200 bg-slate-50/70 p-4 md:grid-cols-[minmax(0,1fr)_220px]">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                      Project Intake
                    </p>
                    <h2 className="mt-2 font-heading text-2xl text-pine">Tell us what you want to build</h2>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      Start with the project and the parcel address. The system will validate the
                      property, infer the likely zoning context, and run the staged review.
                    </p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-3 md:grid-cols-1">
                    <div className="rounded-2xl border border-slate-200 bg-white p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                        Stage
                      </p>
                      <p className="mt-2 text-sm font-semibold text-slate-900">
                        {phase === "analyzing"
                          ? "Analyzing"
                          : phase === "intake"
                            ? "Validating"
                            : phase === "done"
                              ? "Ready"
                              : phase === "error"
                                ? "Error"
                                : "Waiting"}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-white p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                        Workflow
                      </p>
                      <p className="mt-2 text-sm font-semibold text-slate-900">5 stages</p>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-white p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                        Registry
                      </p>
                      <p className="mt-2 text-sm font-semibold text-slate-900">{sources.length} sources</p>
                    </div>
                  </div>
                </div>

                <div className="mb-5 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50/80 p-4 text-sm text-slate-700">
                  <input
                    className="mt-1 h-4 w-4 accent-clay"
                    type="checkbox"
                    checked={acceptedDisclaimer}
                    onChange={(event) => setAcceptedDisclaimer(event.target.checked)}
                  />
                  <span>I understand this is an educational tool and not official legal approval.</span>
                </div>

                <label className="mb-4 block text-sm font-semibold text-slate-700">
                  Describe the project
                  <textarea
                    className="mt-2 min-h-[160px] w-full rounded-2xl border border-slate-300 bg-slate-50/50 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
                    value={projectDescription}
                    onChange={(event) => setProjectDescription(event.target.value)}
                    placeholder="Example: Can I open a bakery out of my attached garage with two employees, weekday pickup hours, and limited interior renovation?"
                  />
                </label>

                <div className="mb-4 grid gap-4 rounded-3xl border border-slate-200 bg-slate-50/70 p-4 md:grid-cols-2">
                  <label className="block text-sm font-semibold text-slate-700">
                    Use type
                    <select
                      className="mt-2 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm"
                      value={intakeFacts.useType}
                      onChange={(event) =>
                        setIntakeFacts((current) => ({ ...current, useType: event.target.value }))
                      }
                    >
                      <option value="">Select if known</option>
                      <option value="Home-based food business">Home-based food business</option>
                      <option value="Retail or service business">Retail or service business</option>
                      <option value="Restaurant or cafe">Restaurant or cafe</option>
                      <option value="Residential addition">Residential addition</option>
                      <option value="General construction">General construction</option>
                    </select>
                  </label>
                  <label className="block text-sm font-semibold text-slate-700">
                    Construction scope
                    <input
                      className="mt-2 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm"
                      value={intakeFacts.constructionScope}
                      onChange={(event) =>
                        setIntakeFacts((current) => ({
                          ...current,
                          constructionScope: event.target.value,
                        }))
                      }
                      placeholder="Interior renovation, addition, no construction"
                    />
                  </label>
                  <label className="block text-sm font-semibold text-slate-700">
                    Operating hours
                    <input
                      className="mt-2 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm"
                      value={intakeFacts.operatingHours}
                      onChange={(event) =>
                        setIntakeFacts((current) => ({
                          ...current,
                          operatingHours: event.target.value,
                        }))
                      }
                      placeholder="Weekdays 8 AM to 5 PM"
                    />
                  </label>
                  <label className="block text-sm font-semibold text-slate-700">
                    Employees
                    <input
                      className="mt-2 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm"
                      value={intakeFacts.employeeCount}
                      onChange={(event) =>
                        setIntakeFacts((current) => ({
                          ...current,
                          employeeCount: event.target.value,
                        }))
                      }
                      placeholder="Owner only, 2 employees, unknown"
                    />
                  </label>
                  <label className="block text-sm font-semibold text-slate-700 md:col-span-2">
                    Parking/loading
                    <input
                      className="mt-2 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm"
                      value={intakeFacts.parkingLoading}
                      onChange={(event) =>
                        setIntakeFacts((current) => ({
                          ...current,
                          parkingLoading: event.target.value,
                        }))
                      }
                      placeholder="Existing driveway, deliveries twice weekly, customer pickup"
                    />
                  </label>
                  <label className="flex items-start gap-3 text-sm font-semibold text-slate-700 md:col-span-2">
                    <input
                      className="mt-1 h-4 w-4 accent-clay"
                      type="checkbox"
                      checked={intakeFacts.foodFireHealth}
                      onChange={(event) =>
                        setIntakeFacts((current) => ({
                          ...current,
                          foodFireHealth: event.target.checked,
                        }))
                      }
                    />
                    Food, fire, or health department review may be triggered.
                  </label>
                </div>

                <div ref={addressSectionRef}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <label className="block text-sm font-semibold text-slate-700" htmlFor="address">
                      Property address
                    </label>
                    <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600">
                      US addresses accepted; answers only where coverage is public-supported
                    </span>
                  </div>
                  <input
                    id="address"
                    className="mt-2 w-full rounded-2xl border border-slate-300 bg-slate-50/50 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
                    value={address}
                    onChange={(event) => setAddress(event.target.value)}
                    onKeyDown={onAddressKeyDown}
                    placeholder="123 Main St, Blacksburg, VA"
                    autoComplete="off"
                  />
                  <div className="mt-3 flex flex-wrap gap-2">
                    {publicSupportedCoverage.slice(0, 4).map((item) => (
                      <span
                        key={item.jurisdictionId}
                        className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-900"
                      >
                        {item.name}
                      </span>
                    ))}
                    {indexedCoverage.slice(0, 3).map((item) => (
                      <span
                        key={item.jurisdictionId}
                        className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-900"
                      >
                        {item.name} source-indexed
                      </span>
                    ))}
                  </div>

                  {suggestionLoading && (
                    <p className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      Looking up addresses
                    </p>
                  )}

                  {suggestions.length > 0 && (
                    <ul className="mt-3 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
                      {suggestions.map((option, index) => (
                        <li key={`${option}-${index}`} className="border-b border-slate-200 last:border-b-0">
                          <button
                            type="button"
                            onMouseDown={(event) => {
                              event.preventDefault();
                              selectSuggestion(option);
                            }}
                            onClick={() => selectSuggestion(option)}
                            className={`w-full px-4 py-3 text-left text-sm ${
                              index === activeSuggestionIndex ? "bg-amber-100" : "bg-transparent"
                            }`}
                          >
                            {option}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                  <button
                    type="button"
                    onClick={() => {
                      void onSubmit();
                    }}
                    disabled={!canSubmit || phase === "intake" || phase === "analyzing"}
                    className="flex-1 rounded-2xl bg-gradient-to-r from-clay to-pine px-5 py-3 font-semibold text-white disabled:opacity-60"
                  >
                    {phase === "intake" || phase === "analyzing"
                      ? "Running zoning review..."
                      : "Run zoning review"}
                  </button>
                  <button
                    type="button"
                    onClick={resetWorkspace}
                    className="rounded-2xl border border-slate-300 px-5 py-3 font-semibold text-slate-700"
                  >
                    Reset
                  </button>
                </div>

                {error && (
                  <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                    <p>{error}</p>
                    {intake?.supportStatus === "unsupported" && (
                      <div className="mt-4 rounded-2xl border border-amber-200 bg-white/80 p-4 text-amber-950">
                        <p className="text-xs font-semibold uppercase tracking-[0.16em]">
                          Request Coverage
                        </p>
                        <p className="mt-2 leading-6">
                          We recognize {intake.jurisdictionName ?? "this jurisdiction"}, but it
                          is {coverageLabel(intake.coverageStatus)} rather than public-supported.
                        </p>
                        <button
                          type="button"
                          onClick={() => {
                            void onRequestJurisdictionSupport();
                          }}
                          disabled={jurisdictionRequestSubmitting || authMode !== "supabase"}
                          className="mt-3 rounded-2xl bg-pine px-4 py-3 font-semibold text-white disabled:opacity-60"
                        >
                          {jurisdictionRequestSubmitting ? "Requesting..." : "Request support"}
                        </button>
                        {authMode !== "supabase" && (
                          <p className="mt-2 text-xs leading-5">
                            Sign-in mode records demand by user; beta/local mode does not submit
                            coverage requests.
                          </p>
                        )}
                        {jurisdictionRequestMessage && (
                          <p className="mt-2 text-sm leading-6">{jurisdictionRequestMessage}</p>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                      Pipeline Progress
                    </p>
                    <h2 className="mt-2 font-heading text-2xl text-pine">Orchestrated workflow</h2>
                  </div>
                  <p className="text-sm text-slate-600">
                    {phase === "analyzing"
                      ? "Running now"
                      : phase === "done"
                        ? "Latest result"
                        : "Waiting for input"}
                  </p>
                </div>

                <div className="mt-5 grid gap-3">
                  {displayedStages.map((stage, index) => {
                    const isActive = phase === "analyzing" && index === activeStageIndex;
                    return (
                      <article
                        key={stage.key}
                        className={`rounded-2xl border p-4 ${statusTone(stage.status, isActive)}`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="font-semibold text-slate-900">{stage.label}</p>
                            <p className="mt-1 text-sm text-slate-700">{stage.headline}</p>
                          </div>
                          <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600">
                            {isActive ? "Working" : stage.status.replace("_", " ")}
                          </span>
                        </div>
                        {stage.details.length > 0 && (
                          <ul className="mt-3 space-y-1 text-sm text-slate-600">
                            {stage.details.map((detail) => (
                              <li key={detail}>{detail}</li>
                            ))}
                          </ul>
                        )}
                      </article>
                    );
                  })}
                </div>
              </div>

              {result && (
                <>
                  <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_260px]">
                    <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                            Decision Center
                          </p>
                          <h2 className="mt-2 font-heading text-3xl text-pine">
                            {decisionLabel(result.feasibility.decision)}
                          </h2>
                          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-700">
                            {result.feasibility.summary}
                          </p>
                        </div>
                        <div
                          className={`rounded-3xl border px-4 py-3 text-center ${decisionTone(
                            result.feasibility.decision,
                          )}`}
                        >
                          <p className="text-xs font-semibold uppercase tracking-[0.18em]">
                            Confidence
                          </p>
                          <p className="mt-1 font-heading text-3xl">
                            {(result.feasibility.confidence * 100).toFixed(0)}%
                          </p>
                        </div>
                      </div>

                      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Status</p>
                          <p className="mt-2 font-semibold text-slate-900">
                            {result.status.replace("_", " ")}
                          </p>
                        </div>
                        <div
                          className={`rounded-2xl border p-4 ${confidenceTone(
                            result.feasibility.confidence,
                            result.citations.length,
                          )}`}
                        >
                          <p className="text-xs uppercase tracking-[0.18em] opacity-75">Reliability</p>
                          <p className="mt-2 font-semibold">
                            {confidenceLabel(result.feasibility.confidence)}
                          </p>
                        </div>
                        <div className={`rounded-2xl border p-4 ${evidenceTone(result.citations.length)}`}>
                          <p className="text-xs uppercase tracking-[0.18em] opacity-75">Evidence</p>
                          <p className="mt-2 font-semibold">{evidenceLabel(result.citations.length)}</p>
                        </div>
                        <div
                          className={`rounded-2xl border p-4 ${
                            result.warnings.length > 0
                              ? "border-amber-200 bg-amber-50 text-amber-900"
                              : "border-slate-200 bg-slate-50 text-slate-900"
                          }`}
                        >
                          <p className="text-xs uppercase tracking-[0.18em] opacity-75">Warnings</p>
                          <p className="mt-2 font-semibold">
                            {result.warnings.length === 0
                              ? "None"
                              : `${result.warnings.length} signal${result.warnings.length === 1 ? "" : "s"}`}
                          </p>
                        </div>
                      </div>

                      {result.warnings.length > 0 && (
                        <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
                          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-800">
                            Review before relying
                          </p>
                          <ul className="mt-3 space-y-2 leading-6">
                            {result.warnings.map((warning) => (
                              <li key={warning}>{warning}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {showHumanFallback && (
                        <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
                          This review needs a human-in-the-loop follow-up. Please confirm the parcel
                          directly with the zoning or planning office before making project or spending
                          decisions.
                        </div>
                      )}
                    </section>

                    <section className="rounded-[28px] border border-pine/10 bg-slate-50/80 p-6 shadow-card">
                      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                        Evidence Snapshot
                      </p>
                      <p className="mt-3 text-sm leading-6 text-slate-700">
                        The answer is only as strong as the source coverage returned for this district and use.
                      </p>
                      <div className={`mt-5 rounded-2xl border p-4 ${evidenceTone(result.citations.length)}`}>
                        <p className="text-xs uppercase tracking-[0.18em] opacity-75">Source coverage</p>
                        <p className="mt-2 text-lg font-semibold">{evidenceLabel(result.citations.length)}</p>
                        <p className="mt-2 text-sm leading-6">
                          {result.citations.length === 0
                            ? "No ordinance excerpts were retrieved, so the result should be treated as a planning-office handoff."
                            : "Each cited source is available in the Evidence tab for review."}
                        </p>
                      </div>
                      {result.citationValidation && (
                        <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                            Citation validation
                          </p>
                          <p className="mt-2 text-sm font-semibold text-slate-900">
                            {(result.citationValidation.citationCoverage * 100).toFixed(0)}% coverage
                          </p>
                          <p className="mt-2 text-sm leading-6 text-slate-600">
                            {result.citationValidation.valid
                              ? "All returned citations passed the current validation checks."
                              : "Unsupported or invalid citation references were found."}
                          </p>
                          {result.citationValidation.unsupportedClaims.length > 0 && (
                            <ul className="mt-2 space-y-1 text-xs leading-5 text-amber-900">
                              {result.citationValidation.unsupportedClaims.map((claim) => (
                                <li key={claim}>{claim}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )}
                      {result.pipeline && (
                        <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Pipeline</p>
                          <p className="mt-2 text-sm font-semibold text-slate-900">
                            {result.pipeline.provider} / {result.pipeline.ragProvider}
                          </p>
                          <p className="mt-1 text-xs leading-5 text-slate-500">
                            {result.pipeline.version} | {result.pipeline.traceId}
                          </p>
                        </div>
                      )}
                      {result.citations.length > 0 && (
                        <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                            Primary citation
                          </p>
                          <p className="mt-2 text-sm font-semibold text-slate-900">
                            {result.citations[0].title}
                          </p>
                          <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">
                            {result.citations[0].sectionRef}
                          </p>
                        </div>
                      )}
                      <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Permit path</p>
                        <p className="mt-2 text-sm font-semibold text-slate-900">
                          {result.checklist.steps.length} step{result.checklist.steps.length === 1 ? "" : "s"}
                        </p>
                        <p className="mt-2 text-sm leading-6 text-slate-600">
                          {result.checklist.permits.length > 0
                            ? result.checklist.permits.join(", ")
                            : "No explicit permit names were returned."}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={downloadChecklist}
                        className="mt-5 w-full rounded-2xl bg-pine px-4 py-3 font-semibold text-white"
                      >
                        Download checklist
                      </button>
                    </section>
                  </div>

                  <TrustIndicatorBar result={result} />
                  <UnsupportedJurisdiction result={result} />

                  <div
                    className={`grid gap-5 ${
                      resultView === "checklist"
                        ? ""
                        : "lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]"
                    }`}
                  >
                    <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
                      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                            Supporting Detail
                          </p>
                          <h3 className="mt-2 font-heading text-2xl text-pine">
                            {resultView === "checklist"
                              ? "Checklist"
                              : resultView === "evidence"
                                ? "Source References"
                                : "Audit Trace"}
                          </h3>
                        </div>
                        <div className="inline-flex w-full max-w-full overflow-x-auto rounded-2xl border border-slate-200 bg-slate-50 p-1 lg:w-auto">
                          {[
                            { key: "checklist", label: "Checklist" },
                            { key: "evidence", label: "Evidence" },
                            { key: "trace", label: "Trace" },
                          ].map((view) => (
                            <button
                              key={view.key}
                              type="button"
                              onClick={() => setResultView(view.key as ResultView)}
                              className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${
                                resultView === view.key
                                  ? "bg-pine text-white shadow-sm"
                                  : "text-slate-600 hover:text-slate-900"
                              }`}
                            >
                              {view.label}
                            </button>
                          ))}
                        </div>
                      </div>

                      {resultView === "checklist" ? (
                        <ol className="mt-6 space-y-4">
                          {result.checklist.steps.map((step) => (
                            <li
                              key={step.order}
                              className="rounded-[24px] border border-slate-200 bg-slate-50 p-5"
                            >
                              <div className="flex items-start gap-4">
                                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-pine text-sm font-bold text-white">
                                  {step.order}
                                </span>
                                <div className="min-w-0">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <p className="text-lg font-semibold text-slate-900">{step.action}</p>
                                    <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-500">
                                      {step.department}
                                    </span>
                                  </div>
                                  <p className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                                    Required documents
                                  </p>
                                  <p className="mt-2 text-sm leading-6 text-slate-700">
                                    {step.requiredDocs.join(", ")}
                                  </p>
                                </div>
                              </div>
                            </li>
                          ))}
                        </ol>
                      ) : resultView === "evidence" ? (
                        <div className="mt-6">
                          <EvidencePanel citations={result.citations} />
                        </div>
                      ) : (
                        <div className="mt-6 grid gap-3">
                          {traceLoading ? (
                            <p className="text-sm text-slate-600">Loading trace...</p>
                          ) : trace.length > 0 ? (
                            trace.map((event) => (
                              <div
                                key={`${event.stage}-${event.createdAt}`}
                                className="rounded-2xl border border-slate-200 bg-slate-50 p-4"
                              >
                                <p className="font-semibold text-slate-900">
                                  {event.stage.replaceAll(".", " / ")}
                                </p>
                                <p className="mt-1 text-xs text-slate-500">
                                  {new Date(event.createdAt).toLocaleString()}
                                </p>
                                {Object.keys(event.details).length > 0 && (
                                  <pre className="mt-3 overflow-auto rounded-xl bg-white p-3 text-xs leading-5 text-slate-600">
                                    {JSON.stringify(event.details, null, 2)}
                                  </pre>
                                )}
                              </div>
                            ))
                          ) : (
                            <p className="text-sm text-slate-600">Trace events will appear here after a run.</p>
                          )}
                        </div>
                      )}
                    </section>

                    <div className="hidden">
                      <section
                        className={`rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8 ${
                          resultView !== "trace" ? "hidden" : ""
                        }`}
                      >
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                          Audit Trace
                        </p>
                        <div className="mt-4 grid gap-3">
                          {traceLoading ? (
                            <p className="text-sm text-slate-600">Loading trace…</p>
                          ) : trace.length > 0 ? (
                            trace.map((event) => (
                              <div
                                key={`${event.stage}-${event.createdAt}`}
                                className="rounded-2xl border border-slate-200 bg-slate-50 p-4"
                              >
                                <p className="font-semibold text-slate-900">
                                  {event.stage.replaceAll(".", " / ")}
                                </p>
                                <p className="mt-1 text-xs text-slate-500">
                                  {new Date(event.createdAt).toLocaleString()}
                                </p>
                              </div>
                            ))
                          ) : (
                            <p className="text-sm text-slate-600">Trace events will appear here after a run.</p>
                          )}
                        </div>
                      </section>
                    </div>
                  </div>

                  <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
                    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_220px]">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                          Workflow Feedback
                        </p>
                        <p className="mt-3 text-sm leading-6 text-slate-700">
                          Tell us whether this result felt clear enough to act on, and where the
                          structure or explanation still needs work.
                        </p>
                        <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-800">
                            Legal reminder
                          </p>
                          <ul className="mt-3 space-y-3 text-sm leading-6 text-amber-950">
                            {result.disclaimers.map((disclaimer) => (
                              <li key={disclaimer}>{disclaimer}</li>
                            ))}
                          </ul>
                        </div>
                        <textarea
                          className="mt-4 min-h-[120px] w-full rounded-2xl border border-slate-300 bg-slate-50/60 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
                          value={feedbackNote}
                          onChange={(event) => setFeedbackNote(event.target.value)}
                          placeholder="What was clear, missing, or confusing?"
                        />
                      </div>

                      <div className="flex flex-col justify-between gap-4">
                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-700">
                          Use this note box for missing citations, unclear checklist steps, or anything
                          that made the answer harder to trust.
                        </div>
                        <div className="flex flex-wrap gap-3">
                          <button
                            type="button"
                            onClick={() => {
                              void onSubmitFeedback(true);
                            }}
                            disabled={feedbackState === "submitting"}
                            className="rounded-2xl bg-pine px-4 py-3 font-semibold text-white disabled:opacity-60"
                          >
                            Helpful
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              void onSubmitFeedback(false);
                            }}
                            disabled={feedbackState === "submitting"}
                            className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700 disabled:opacity-60"
                          >
                            Needs work
                          </button>
                        </div>
                        {feedbackMessage && <p className="text-sm text-slate-700">{feedbackMessage}</p>}
                      </div>
                    </div>
                  </section>
                </>
              )}
            </section>

            <aside className="space-y-5 xl:sticky xl:top-5 xl:self-start">
              {authMode === "supabase" && (
                <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                      Saved Projects
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        void refreshProjects();
                      }}
                      className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500"
                    >
                      Refresh
                    </button>
                  </div>
                  <div className="mt-4 space-y-3">
                    {projectsLoading ? (
                      <p className="text-sm text-slate-600">Loading projects...</p>
                    ) : projects.length > 0 ? (
                      projects.slice(0, 6).map((project) => (
                        <button
                          key={project.projectId}
                          type="button"
                          onClick={() => {
                            void openSavedProject(project);
                          }}
                          className="w-full rounded-2xl border border-slate-200 bg-slate-50 p-4 text-left transition hover:border-clay"
                        >
                          <p className="text-sm font-semibold text-slate-900">
                            {project.normalizedAddress}
                          </p>
                          <p className="mt-1 text-xs uppercase tracking-[0.14em] text-slate-500">
                            {project.jurisdictionName ?? project.jurisdictionId ?? "Unknown"} ·{" "}
                            {project.decision ? decisionLabel(project.decision) : project.status}
                          </p>
                        </button>
                      ))
                    ) : (
                      <p className="text-sm leading-6 text-slate-600">
                        Saved zoning reviews will appear here after your first run.
                      </p>
                    )}
                    {projectsMessage && (
                      <p className="text-sm leading-6 text-slate-600">{projectsMessage}</p>
                    )}
                  </div>
                </section>
              )}

              <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                  Case Snapshot
                </p>
                {intake ? (
                  <div className="mt-4 space-y-3 text-sm text-slate-700">
                    {result && (
                      <button
                        type="button"
                        onClick={downloadChecklist}
                        className="w-full rounded-2xl bg-pine px-4 py-3 text-sm font-semibold text-white"
                      >
                        Download checklist
                      </button>
                    )}
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                        Normalized address
                      </p>
                      <p className="mt-2 font-semibold text-slate-900">{intake.normalizedAddress}</p>
                    </div>
                    <div className={`rounded-2xl border p-4 ${supportStatusTone(intake.supportStatus)}`}>
                      <p className="text-xs uppercase tracking-[0.18em] opacity-75">Jurisdiction</p>
                      <p className="mt-2 font-semibold">
                        {intake.jurisdictionName ?? intake.jurisdictionId ?? "Unknown jurisdiction"}
                      </p>
                      <p className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] opacity-80">
                        {coverageLabel(intake.coverageStatus ?? currentCoverage?.coverageStatus)}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                        Coverage Trust
                      </p>
                      <p className="mt-2 text-sm font-semibold text-slate-900">
                        {supportStatusLabel(intake.supportStatus)}
                      </p>
                      <p className="mt-2 text-xs leading-5 text-slate-600">
                        Last verified: {currentCoverage?.lastVerifiedAt ?? "Not recorded"}
                      </p>
                      {(intake.planningContact?.url || currentCoverage?.planningContact.url) && (
                        <a
                          className="mt-3 inline-flex text-sm font-semibold text-clay underline-offset-2 hover:underline"
                          href={intake.planningContact?.url ?? currentCoverage?.planningContact.url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Planning office
                        </a>
                      )}
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">District</p>
                        <p className="mt-2 font-semibold text-slate-900">
                          {intake.district.replace(/-/g, " ")}
                        </p>
                      </div>
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Coordinates</p>
                        <p className="mt-2 font-semibold text-slate-900">
                          {intake.latitude != null && intake.longitude != null
                            ? `${intake.latitude.toFixed(4)}, ${intake.longitude.toFixed(4)}`
                            : "Unavailable"}
                        </p>
                      </div>
                    </div>
                    {result && (
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Decision</p>
                        <div className="mt-2 flex items-center justify-between gap-3">
                          <p className="font-semibold text-slate-900">
                            {decisionLabel(result.feasibility.decision)}
                          </p>
                          <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600">
                            {(result.feasibility.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="mt-4 text-sm leading-6 text-slate-600">
                    Normalized parcel context appears here after intake succeeds.
                  </p>
                )}
              </section>

              <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                  Review Signals
                </p>
                <div className="mt-4 space-y-3">
                  {assistantPrompts.length > 0 ? (
                    assistantPrompts.map((prompt) => (
                      <div key={prompt} className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                        <p className="text-sm text-amber-900">{prompt}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm leading-6 text-slate-600">
                      Follow-up questions and confidence warnings will appear here when the review needs more detail.
                    </p>
                  )}
                </div>
              </section>
            </aside>
          </div>
        ) : (
          <section className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
            <div className="space-y-6">
              <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                  Source Health
                </p>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className={`rounded-2xl border p-4 ${readinessTone(indexStatus)}`}>
                    <p className="text-xs uppercase tracking-[0.18em] opacity-75">Readiness</p>
                    <p className="mt-2 text-2xl font-semibold">{readinessLabel(indexStatus)}</p>
                    <p className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] opacity-80">
                      {indexStatus?.sourceRegistryVersion
                        ? `Registry ${indexStatus.sourceRegistryVersion}`
                        : "Registry version unset"}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Sources</p>
                    <p className="mt-2 text-2xl font-semibold text-pine">
                      {indexStatus?.sourceCount ?? sources.length}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Source Packs</p>
                    <p className="mt-2 text-2xl font-semibold text-pine">
                      {indexStatus?.sourcePackCount ?? 0}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-slate-600">
                      {(indexStatus?.sourcePackJurisdictionIds ?? []).join(", ") || "No packs found"}
                    </p>
                  </div>
                  <div
                    className={`rounded-2xl border p-4 ${readinessTone(indexStatus)}`}
                  >
                    <p className="text-xs uppercase tracking-[0.18em] opacity-75">Index</p>
                    <p className="mt-2 text-2xl font-semibold">
                      {indexStatus?.chunkCount ?? 0} chunks
                    </p>
                  </div>
                  <div
                    className={`rounded-2xl border p-4 ${
                      indexStatus?.vectorIndexReady
                        ? "border-emerald-200 bg-emerald-50 text-emerald-950"
                        : "border-amber-200 bg-amber-50 text-amber-950"
                    }`}
                  >
                    <p className="text-xs uppercase tracking-[0.18em] opacity-75">Vectors</p>
                    <p className="mt-2 text-2xl font-semibold">
                      {indexStatus?.vectorCount ?? 0} vectors
                    </p>
                    <p className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] opacity-80">
                      {indexStatus?.vectorProvider ?? "none"}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Last import</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">
                      {formatDateTime(indexStatus?.lastImportAt)}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Last reindex</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">
                      {formatDateTime(indexStatus?.lastReindexAt)}
                    </p>
                  </div>
                </div>
                {indexStatus && indexStatus.sourcesMissingMetadata.length > 0 && (
                  <p className="mt-4 text-sm leading-6 text-amber-900">
                    {indexStatus.sourcesMissingMetadata.length} source
                    {indexStatus.sourcesMissingMetadata.length === 1 ? "" : "s"} need metadata before the
                    index is fully auditable.
                  </p>
                )}
                {indexStatus && (
                  <div className="mt-4 grid gap-3">
                    {(indexStatus.staleSourceIds.length > 0 ||
                      indexStatus.missingChunkSourceIds.length > 0) && (
                      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
                        <p className="font-semibold">Index refresh needed</p>
                        {indexStatus.staleSourceIds.length > 0 && (
                          <p className="mt-2 leading-6">
                            Stale sources: {indexStatus.staleSourceIds.join(", ")}
                          </p>
                        )}
                        {indexStatus.missingChunkSourceIds.length > 0 && (
                          <p className="mt-2 leading-6">
                            Missing chunks: {indexStatus.missingChunkSourceIds.join(", ")}
                          </p>
                        )}
                      </div>
                    )}
                    {indexStatus.readinessWarnings.length > 0 && (
                      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
                        <p className="font-semibold">Readiness warnings</p>
                        <ul className="mt-2 space-y-1 leading-6">
                          {indexStatus.readinessWarnings.map((warning) => (
                            <li key={warning}>{warning}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {indexStatus.vectorReadinessWarnings.length > 0 && (
                      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
                        <p className="font-semibold">Vector warnings</p>
                        <ul className="mt-2 space-y-1 leading-6">
                          {indexStatus.vectorReadinessWarnings.map((warning) => (
                            <li key={warning}>{warning}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-xs leading-5 text-slate-600">
                      Auto seed: {indexStatus.autoSeedSources ? "on" : "off"} · Auto reindex empty:{" "}
                      {indexStatus.autoReindexOnEmpty ? "on" : "off"}
                    </div>
                  </div>
                )}
              </div>

              <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                      Demand Backlog
                    </p>
                    <h2 className="mt-2 font-heading text-2xl text-pine">
                      Jurisdiction Requests
                    </h2>
                  </div>
                  <span className="rounded-full bg-mist px-3 py-1 text-xs font-semibold text-pine">
                    {jurisdictionRequests.length} queued
                  </span>
                </div>
                <div className="mt-5 space-y-3">
                  {jurisdictionRequestsLoading ? (
                    <p className="text-sm text-slate-600">Loading request backlog...</p>
                  ) : jurisdictionRequestsMessage ? (
                    <p className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
                      {jurisdictionRequestsMessage}
                    </p>
                  ) : jurisdictionRequests.length === 0 ? (
                    <p className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                      No jurisdiction requests have been logged yet.
                    </p>
                  ) : (
                    jurisdictionRequests.map((request) => {
                      const matchedCoverage = coverageForRequest(request);
                      const coverageStatus = matchedCoverage?.coverageStatus;
                      const title =
                        request.jurisdictionName ??
                        request.jurisdictionId ??
                        "Unknown jurisdiction";
                      return (
                        <article
                          key={`${request.jurisdictionId ?? "unknown"}-${request.jurisdictionName ?? "unnamed"}-${request.state ?? "na"}`}
                          className="rounded-2xl border border-slate-200 bg-slate-50 p-4"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="font-semibold text-slate-900">{title}</p>
                              <p className="mt-1 text-xs uppercase tracking-[0.14em] text-slate-500">
                                {formatLocationParts(
                                  request.state,
                                  request.county,
                                  request.locality,
                                )}
                              </p>
                            </div>
                            <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-700">
                              {request.requestCount} request
                              {request.requestCount === 1 ? "" : "s"}
                            </span>
                          </div>
                          <div className="mt-4 flex flex-wrap items-center gap-2">
                            <span
                              className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                                matchedCoverage
                                  ? coverageTone(coverageStatus)
                                  : "border-slate-200 bg-white text-slate-600"
                              }`}
                            >
                              {matchedCoverage ? coverageLabel(coverageStatus) : "Coverage unknown"}
                            </span>
                            <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-600">
                              Last requested {formatDateTime(request.lastRequestedAt)}
                            </span>
                          </div>
                        </article>
                      );
                    })
                  )}
                </div>
              </div>

              <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                  Admin Access
                </p>
                <p className="mt-3 text-sm leading-6 text-slate-600">
                  Source status and catalog load with beta access. Save the separate admin key here
                  before editing sources, importing documents, or reindexing.
                </p>
                <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Write access</p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">
                    {adminAccessKey ? "Admin key saved for this session" : "No admin key saved"}
                  </p>
                </div>
                <label className="mt-4 block text-sm font-semibold text-slate-700">
                  Source admin key
                  <input
                    className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                    type="password"
                    value={adminAccessInput}
                    onChange={(event) => setAdminAccessInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        saveAdminKey();
                      }
                    }}
                  />
                </label>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={saveAdminKey}
                    className="rounded-2xl bg-clay px-4 py-3 font-semibold text-white"
                  >
                    Save admin key
                  </button>
                  <button
                    type="button"
                    onClick={clearStoredAdminKey}
                    className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700"
                  >
                    Clear key
                  </button>
                </div>
                {adminAccessMessage && (
                  <p className="mt-4 text-sm text-slate-700">{adminAccessMessage}</p>
                )}
              </div>

              <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                  Source Editor
                </p>
                <div className="mt-4 space-y-4">
                  <label className="block text-sm font-semibold text-slate-700">
                    Source ID
                    <input
                      className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                      value={sourceForm.sourceId}
                      onChange={(event) =>
                        setSourceForm((current) => ({ ...current, sourceId: event.target.value }))
                      }
                    />
                  </label>
                  <label className="block text-sm font-semibold text-slate-700">
                    Title
                    <input
                      className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                      value={sourceForm.title}
                      onChange={(event) =>
                        setSourceForm((current) => ({ ...current, title: event.target.value }))
                      }
                    />
                  </label>
                  <label className="block text-sm font-semibold text-slate-700">
                    Excerpt
                    <textarea
                      className="mt-2 min-h-[140px] w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                      value={sourceForm.excerpt}
                      onChange={(event) =>
                        setSourceForm((current) => ({ ...current, excerpt: event.target.value }))
                      }
                    />
                  </label>
                  <label className="block text-sm font-semibold text-slate-700">
                    Section reference
                    <input
                      className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                      value={sourceForm.sectionRef}
                      onChange={(event) =>
                        setSourceForm((current) => ({ ...current, sectionRef: event.target.value }))
                      }
                    />
                  </label>
                  <label className="block text-sm font-semibold text-slate-700">
                    Jurisdiction ID
                    <input
                      className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                      value={sourceForm.jurisdictionId ?? ""}
                      onChange={(event) =>
                        setSourceForm((current) => ({
                          ...current,
                          jurisdictionId: event.target.value,
                        }))
                      }
                      placeholder="blacksburg-va"
                    />
                  </label>
                  <label className="block text-sm font-semibold text-slate-700">
                    URL
                    <input
                      className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                      value={sourceForm.url ?? ""}
                      onChange={(event) =>
                        setSourceForm((current) => ({ ...current, url: event.target.value }))
                      }
                    />
                  </label>
                  <label className="block text-sm font-semibold text-slate-700">
                    Effective date
                    <input
                      className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                      value={sourceForm.effectiveDate ?? ""}
                      onChange={(event) =>
                        setSourceForm((current) => ({
                          ...current,
                          effectiveDate: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label className="block text-sm font-semibold text-slate-700">
                    Districts
                    <input
                      className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                      value={sourceForm.districts.join(", ")}
                      onChange={(event) =>
                        setSourceForm((current) => ({
                          ...current,
                          districts: parseTagList(event.target.value),
                        }))
                      }
                    />
                  </label>
                  <label className="block text-sm font-semibold text-slate-700">
                    Uses
                    <input
                      className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                      value={sourceForm.uses.join(", ")}
                      onChange={(event) =>
                        setSourceForm((current) => ({
                          ...current,
                          uses: parseTagList(event.target.value),
                        }))
                      }
                    />
                  </label>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    void onSaveSource();
                  }}
                  disabled={sourceSaving}
                  className="mt-5 w-full rounded-2xl bg-clay px-4 py-3 font-semibold text-white disabled:opacity-60"
                >
                  {sourceSaving ? "Saving..." : "Save source"}
                </button>
                {sourceMessage && <p className="mt-4 text-sm text-slate-700">{sourceMessage}</p>}
              </div>

              <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                  Ingestion Actions
                </p>
                <label className="mt-4 block text-sm font-semibold text-slate-700">
                  Local document directory
                  <input
                    className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm"
                    value={importDirectory}
                    onChange={(event) => setImportDirectory(event.target.value)}
                    placeholder="services/ingestion/documents"
                  />
                </label>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => {
                      void onImportDocuments();
                    }}
                    disabled={importing}
                    className="rounded-2xl bg-pine px-4 py-3 font-semibold text-white disabled:opacity-60"
                  >
                    {importing ? "Importing..." : "Import local docs"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      void onImportSourcePacks();
                    }}
                    disabled={importing}
                    className="rounded-2xl bg-clay px-4 py-3 font-semibold text-white disabled:opacity-60"
                  >
                    Import source packs
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      void onReindexSources();
                    }}
                    className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700"
                  >
                    Reindex sources
                  </button>
                </div>
                {importMessage && <p className="mt-4 text-sm text-slate-700">{importMessage}</p>}
                {reindexMessage && <p className="mt-2 text-sm text-slate-700">{reindexMessage}</p>}
              </div>
            </div>

            <div className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                    Registered Sources
                  </p>
                  <h2 className="mt-2 font-heading text-2xl text-pine">Catalog</h2>
                </div>
                <span className="rounded-full bg-mist px-3 py-1 text-xs font-semibold text-pine">
                  {sources.length} sources
                </span>
              </div>

              <div className="mt-5 space-y-3">
                {sourcesLoading ? (
                  <p className="text-sm text-slate-600">Loading sources...</p>
                ) : (
                  sources.map((source) => (
                    <article
                      key={source.sourceId}
                      className="rounded-3xl border border-slate-200 bg-slate-50 p-5"
                    >
                      {(() => {
                        const missingFields = sourceHealthById.get(source.sourceId) ?? [];
                        const indexIssues = sourceIndexIssuesById.get(source.sourceId) ?? [];
                        const hasIssues = missingFields.length > 0 || indexIssues.length > 0;
                        return hasIssues ? (
                          <div className="mb-3 flex flex-wrap gap-2">
                            {indexIssues.map((issue) => (
                              <span
                                key={issue}
                                className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-900"
                              >
                                {issue}
                              </span>
                            ))}
                            {missingFields.map((field) => (
                              <span
                                key={field}
                                className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-900"
                              >
                                Missing {field.replace(/_/g, " ")}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <div className="mb-3 inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-900">
                            Metadata complete
                          </div>
                        );
                      })()}
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-slate-900">{source.title}</p>
                          <p className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                            {source.jurisdictionId ?? "No jurisdiction"}
                          </p>
                          <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">
                            {source.sourceId} · {source.sectionRef}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => loadSourceIntoForm(source)}
                          className="rounded-2xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700"
                        >
                          Edit
                        </button>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-slate-700">{source.excerpt}</p>
                    </article>
                  ))
                )}
              </div>
            </div>
          </section>
        )}
        <footer className="mt-8 flex flex-wrap gap-4 border-t border-pine/10 pt-5 text-sm font-semibold text-slate-500">
          <button type="button" onClick={() => setLegalPage("terms")}>Terms</button>
          <button type="button" onClick={() => setLegalPage("privacy")}>Privacy</button>
          <button type="button" onClick={() => setLegalPage("disclaimer")}>Disclaimer</button>
        </footer>
      </div>

      {legalPage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
          <section className="w-full max-w-2xl rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
            {(() => {
              const legal = legalCopy(legalPage);
              return (
                <>
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                    Public Disclosure
                  </p>
                  <h2 className="mt-2 font-heading text-3xl text-pine">{legal.title}</h2>
                  <div className="mt-5 space-y-4 text-sm leading-7 text-slate-700">
                    {legal.paragraphs.map((paragraph) => (
                      <p key={paragraph}>{paragraph}</p>
                    ))}
                  </div>
                </>
              );
            })()}
            <button
              type="button"
              onClick={() => setLegalPage(null)}
              className="mt-6 rounded-2xl bg-pine px-4 py-3 font-semibold text-white"
            >
              Close
            </button>
          </section>
        </div>
      )}

      {clarificationOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
          <div className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
              Clarification Needed
            </p>
            <h2 className="mt-2 font-heading text-2xl text-pine">
              We need a bit more detail before finishing the zoning call.
            </h2>
            <div className="mt-5 space-y-4">
              {clarificationQuestions.map((question) => (
                <label key={question.id} className="block text-sm font-semibold text-slate-700">
                  {question.question}
                  <textarea
                    className="mt-2 min-h-[96px] w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
                    value={clarificationAnswers[question.question] ?? ""}
                    onChange={(event) =>
                      setClarificationAnswers((current) => ({
                        ...current,
                        [question.question]: event.target.value,
                      }))
                    }
                  />
                  <span className="mt-2 block text-xs font-normal leading-5 text-slate-500">
                    {question.reason}
                  </span>
                </label>
              ))}
            </div>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                onClick={() => {
                  void onSubmitClarifications();
                }}
                disabled={clarificationSubmitting}
                className="flex-1 rounded-2xl bg-pine px-4 py-3 font-semibold text-white disabled:opacity-60"
              >
                {clarificationSubmitting ? "Submitting..." : "Continue review"}
              </button>
              <button
                type="button"
                onClick={() => setClarificationOpen(false)}
                className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
