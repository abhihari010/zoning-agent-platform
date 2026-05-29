import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  AnalyzeResponse,
  FollowUpQuestion,
} from "@zoning-agent/shared-schema";
import {
  analyzeProject,
  authMode,
  createSession,
  deleteProject,
  fetchProjectResult,
  intakeProject,
  listProjects,
  requestJurisdictionSupport,
  type IntakeResponse,
  type JurisdictionCoverage,
  type JurisdictionRequestSummary,
  type ProjectSummary,
} from "./api";
import {
  LOADING_PIPELINE_STAGES,
  PIPELINE_STAGE_COUNT,
} from "./constants/pipeline";
import type {
  IntakeFacts,
  LegalPage,
  Phase,
  ResultView,
  Workspace,
} from "./types/app";
import { buildChecklistDownload, downloadTextFile } from "./utils/downloads";
import {
  buildProjectContext,
  emptyIntakeFacts,
  intakeErrorMessage,
} from "./utils/intake";
import { LegalFooter } from "./components/LegalFooter";
import { LegalModal } from "./components/LegalModal";
import { WorkspaceHeader } from "./components/WorkspaceHeader";
import { AdminAccessPanel } from "./features/admin/AdminAccessPanel";
import { IngestionActions } from "./features/admin/IngestionActions";
import { JurisdictionRequestsPanel } from "./features/admin/JurisdictionRequestsPanel";
import { SourceCatalog } from "./features/admin/SourceCatalog";
import { SourceEditorForm } from "./features/admin/SourceEditorForm";
import { SourceHealthPanel } from "./features/admin/SourceHealthPanel";
import { PipelineProgress } from "./features/assistant/PipelineProgress";
import { ProjectIntakePanel } from "./features/assistant/ProjectIntakePanel";
import { PublicAuthScreen } from "./features/landing/PublicAuthScreen";
import { CaseSnapshot } from "./features/projects/CaseSnapshot";
import { ReviewSignalsPanel } from "./features/projects/ReviewSignalsPanel";
import { SavedProjectsPanel } from "./features/projects/SavedProjectsPanel";
import { ClarificationModal } from "./features/results/ClarificationModal";
import { ResultSection } from "./features/results/ResultSection";
import { useAddressAutocomplete } from "./hooks/useAddressAutocomplete";
import { useCoverage } from "./hooks/useCoverage";
import { useFeedback } from "./hooks/useFeedback";
import { useLegalAck } from "./hooks/useLegalAck";
import { useSourcesAdmin } from "./hooks/useSourcesAdmin";
import { useSupabaseAuth } from "./hooks/useSupabaseAuth";
import { useTrace } from "./hooks/useTrace";

export function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsMessage, setProjectsMessage] = useState("");
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(
    null,
  );
  const resetAuthState = useCallback(() => {
    setProjects([]);
  }, []);
  const {
    authSession,
    authLoading,
    authEmail,
    authPassword,
    authMessage,
    currentUser,
    setAuthEmail,
    setAuthPassword,
    signIn,
    signUp,
    signOut,
  } = useSupabaseAuth({
    onAuthStateReset: resetAuthState,
  });
  const {
    coverage,
    coverageMessage,
    publicSupportedCoverage,
    indexedCoverage,
    coverageByJurisdictionId,
    coverageByJurisdictionName,
  } = useCoverage();
  const [legalPage, setLegalPage] = useState<LegalPage>(null);
  const [pendingSubmit, setPendingSubmit] = useState(false);
  const { isAcknowledged, acknowledge } = useLegalAck();
  const [jurisdictionRequestMessage, setJurisdictionRequestMessage] =
    useState("");
  const [jurisdictionRequestSubmitting, setJurisdictionRequestSubmitting] =
    useState(false);
  const [workspace, setWorkspace] = useState<Workspace>("assistant");
  const [acceptedDisclaimer, setAcceptedDisclaimer] = useState(false);
  const [projectDescription, setProjectDescription] = useState("");
  const [intakeFacts, setIntakeFacts] = useState<IntakeFacts>(emptyIntakeFacts);
  const {
    address,
    setAddress,
    suggestions,
    activeSuggestionIndex,
    suggestionLoading,
    addressSectionRef,
    selectSuggestion,
    onAddressKeyDown,
    resetAddress,
  } = useAddressAutocomplete();
  const [phase, setPhase] = useState<Phase>("idle");
  const [activeStageIndex, setActiveStageIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [intake, setIntake] = useState<IntakeResponse | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const { trace, setTrace, traceLoading } = useTrace({
    intake,
    result,
    phase,
    isAdmin: authMode === "supabase" ? currentUser?.role === "admin" : true,
  });
  const {
    feedbackNote,
    setFeedbackNote,
    feedbackState,
    feedbackMessage,
    onSubmitFeedback,
    resetFeedback,
  } = useFeedback(intake);
  const [resultView, setResultView] = useState<ResultView>("checklist");
  const [clarificationOpen, setClarificationOpen] = useState(false);
  const [clarificationQuestions, setClarificationQuestions] = useState<
    FollowUpQuestion[]
  >([]);
  const [clarificationAnswers, setClarificationAnswers] = useState<
    Record<string, string>
  >({});
  const [clarificationSubmitting, setClarificationSubmitting] = useState(false);
  const isSupabaseAuthenticated =
    authMode !== "supabase" || Boolean(authSession);
  const canLoadPrivateData =
    authMode === "supabase" ? Boolean(authSession) : true;
  const canUseAdminTools =
    authMode === "supabase" ? currentUser?.role === "admin" : true;
  const {
    sources,
    indexStatus,
    sourcesLoading,
    sourceForm,
    setSourceForm,
    sourceMessage,
    sourceSaving,
    jurisdictionRequests,
    jurisdictionRequestsLoading,
    jurisdictionRequestsMessage,
    reindexMessage,
    importDirectory,
    setImportDirectory,
    importing,
    importMessage,
    adminAccessKey,
    adminAccessInput,
    setAdminAccessInput,
    adminAccessMessage,
    saveAdminKey,
    clearStoredAdminKey,
    onSaveSource,
    onReindexSources,
    onImportDocuments,
    onImportSourcePacks,
    loadSourceIntoForm,
    resetSourceState,
  } = useSourcesAdmin({
    canLoadPrivateData,
    canUseAdminTools,
    authSession,
    onWorkspaceChange: setWorkspace,
  });
  const currentCoverage = useMemo(
    () =>
      coverage.find((item) => item.jurisdictionId === intake?.jurisdictionId),
    [coverage, intake?.jurisdictionId],
  );

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
    return result?.pipelineStages?.length
      ? result.pipelineStages
      : LOADING_PIPELINE_STAGES;
  }, [result]);

  const assistantPrompts = useMemo(() => {
    const prompts: string[] = [];
    if (intake) {
      prompts.push(
        ...intake.followUpQuestions.map((question) => question.question),
      );
    }
    if (result) {
      prompts.push(
        ...result.followUpQuestions.map((question) => question.question),
      );
      prompts.push(...result.warnings);
    }
    return Array.from(new Set(prompts));
  }, [intake, result]);

  const sourceHealthById = useMemo(() => {
    const entries = indexStatus?.sourcesMissingMetadata ?? [];
    return new Map(
      entries.map((source) => [source.sourceId, source.missingFields]),
    );
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
      return coverageByJurisdictionName.get(
        request.jurisdictionName.toLowerCase(),
      );
    }
    return undefined;
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
        projectError instanceof Error
          ? projectError.message
          : "Failed to load projects.",
      );
    } finally {
      setProjectsLoading(false);
    }
  }

  async function onSignOut() {
    await signOut();
    resetWorkspace();
  }

  async function runAnalysis(
    projectId: string,
    answers?: Record<string, string>,
  ) {
    setPhase("analyzing");
    setActiveStageIndex(0);
    const analysis = await analyzeProject(projectId, answers);
    setResult(analysis);
    setPhase("done");

    if (
      analysis.status === "needs_clarification" &&
      analysis.followUpQuestions.length > 0
    ) {
      const nextAnswers = analysis.followUpQuestions.reduce<
        Record<string, string>
      >((accumulator, question) => {
        accumulator[question.question] =
          clarificationAnswers[question.question] ?? "";
        return accumulator;
      }, {});
      setClarificationQuestions(analysis.followUpQuestions);
      setClarificationAnswers(nextAnswers);
      setClarificationOpen(true);
    }
  }

  async function runSubmitFlow() {
    setError(null);
    setResult(null);
    setIntake(null);
    setTrace([]);
    resetFeedback();
    setJurisdictionRequestMessage("");
    setResultView("checklist");
    setClarificationOpen(false);
    setClarificationQuestions([]);
    setClarificationAnswers({});

    try {
      setPhase("intake");
      const sessionId = await createSession();
      const projectContext = buildProjectContext(
        projectDescription,
        intakeFacts,
      );
      const intakeResult = await intakeProject({
        session_id: sessionId,
        project_description: projectContext,
        address: address.trim(),
        legal_ack_at: localStorage.getItem("legal_ack_at") ?? undefined,
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
        submitError instanceof Error
          ? submitError.message
          : "Something went wrong during analysis.",
      );
    }
  }

  async function onSubmit() {
    if (!canSubmit) {
      return;
    }

    if (!isAcknowledged) {
      setPendingSubmit(true);
      setLegalPage("disclaimer");
      return;
    }

    await runSubmitFlow();
  }

  async function onSubmitClarifications() {
    if (!intake) {
      return;
    }

    const unanswered = clarificationQuestions.some(
      (question) => !clarificationAnswers[question.question]?.trim(),
    );
    if (unanswered) {
      setError(
        "Please answer each clarification so we can continue the review.",
      );
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
        projectError instanceof Error
          ? projectError.message
          : "Failed to open saved project.",
      );
    }
  }

  async function onDeleteCurrentProject() {
    if (!intake?.projectId) {
      return;
    }
    const confirmed = window.confirm(
      "Delete this saved zoning review? This cannot be undone.",
    );
    if (!confirmed) {
      return;
    }
    try {
      setDeletingProjectId(intake.projectId);
      setProjectsMessage("");
      await deleteProject(intake.projectId);
      setProjects((current) =>
        current.filter((item) => item.projectId !== intake.projectId),
      );
      resetWorkspace();
      setProjectsMessage("Project deleted.");
    } catch (projectError) {
      setProjectsMessage(
        projectError instanceof Error
          ? projectError.message
          : "Failed to delete project.",
      );
    } finally {
      setDeletingProjectId(null);
    }
  }

  function downloadChecklist() {
    if (!result) {
      return;
    }

    downloadTextFile(
      "zoning-checklist.txt",
      buildChecklistDownload(
        intake,
        result,
        buildProjectContext(projectDescription, intakeFacts),
      ),
    );
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

  function resetWorkspace() {
    setAcceptedDisclaimer(false);
    setProjectDescription("");
    setIntakeFacts(emptyIntakeFacts());
    resetAddress();
    setPhase("idle");
    setError(null);
    setIntake(null);
    setResult(null);
    setTrace([]);
    resetFeedback();
    setJurisdictionRequestMessage("");
    setResultView("checklist");
    setClarificationOpen(false);
    setClarificationQuestions([]);
    setClarificationAnswers({});
  }

  const showHumanFallback =
    result?.status === "low_confidence" ||
    result?.feasibility.decision === "unknown";

  if (authMode === "supabase" && (authLoading || !isSupabaseAuthenticated)) {
    return (
      <PublicAuthScreen
        coverage={coverage}
        publicSupportedCoverage={publicSupportedCoverage}
        indexedCoverage={indexedCoverage}
        coverageMessage={coverageMessage}
        authEmail={authEmail}
        authPassword={authPassword}
        authMessage={authMessage}
        authLoading={authLoading}
        legalPage={legalPage}
        onAuthEmailChange={setAuthEmail}
        onAuthPasswordChange={setAuthPassword}
        onSignIn={() => {
          void signIn();
        }}
        onSignUp={() => {
          void signUp();
        }}
        onSelectLegalPage={setLegalPage}
        onCloseLegalPage={() => setLegalPage(null)}
      />
    );
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(217,120,85,0.10),transparent_24%),linear-gradient(180deg,#f8f3ea_0%,#efe5d5_100%)] text-slate-900">
      <div className="mx-auto max-w-6xl px-4 py-5 md:px-8 md:py-8">
        <WorkspaceHeader
          workspace={workspace}
          canUseAdminTools={canUseAdminTools}
          currentUser={currentUser}
          authSession={authSession}
          onWorkspaceChange={setWorkspace}
          onSignOut={() => {
            void onSignOut();
          }}
        />

        {workspace === "assistant" ? (
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
            <section className="space-y-6">
              <ProjectIntakePanel
                phase={phase}
                sourcesCount={sources.length}
                acceptedDisclaimer={acceptedDisclaimer}
                projectDescription={projectDescription}
                intakeFacts={intakeFacts}
                address={address}
                suggestions={suggestions}
                activeSuggestionIndex={activeSuggestionIndex}
                suggestionLoading={suggestionLoading}
                addressSectionRef={addressSectionRef}
                publicSupportedCoverage={publicSupportedCoverage}
                indexedCoverage={indexedCoverage}
                canSubmit={canSubmit}
                error={error}
                intake={intake}
                jurisdictionRequestSubmitting={jurisdictionRequestSubmitting}
                jurisdictionRequestMessage={jurisdictionRequestMessage}
                onAcceptedDisclaimerChange={setAcceptedDisclaimer}
                onProjectDescriptionChange={setProjectDescription}
                onIntakeFactsChange={setIntakeFacts}
                onAddressChange={setAddress}
                onAddressKeyDown={onAddressKeyDown}
                onSelectSuggestion={selectSuggestion}
                onSubmit={() => {
                  void onSubmit();
                }}
                onReset={resetWorkspace}
                onRequestJurisdictionSupport={() => {
                  void onRequestJurisdictionSupport();
                }}
              />

              <PipelineProgress
                phase={phase}
                activeStageIndex={activeStageIndex}
                stages={displayedStages}
              />

              {result && (
                <ResultSection
                  result={result}
                  resultView={resultView}
                  trace={trace}
                  traceLoading={traceLoading}
                  feedbackNote={feedbackNote}
                  feedbackState={feedbackState}
                  feedbackMessage={feedbackMessage}
                  showHumanFallback={showHumanFallback}
                  onResultViewChange={setResultView}
                  onFeedbackNoteChange={setFeedbackNote}
                  onSubmitFeedback={(helpful) => {
                    void onSubmitFeedback(helpful);
                  }}
                  onDownloadChecklist={downloadChecklist}
                />
              )}
            </section>

            <aside className="space-y-5 xl:sticky xl:top-5 xl:self-start">
              <SavedProjectsPanel
                projects={projects}
                projectsLoading={projectsLoading}
                projectsMessage={projectsMessage}
                onRefresh={() => {
                  void refreshProjects();
                }}
                onOpenProject={(project) => {
                  void openSavedProject(project);
                }}
              />

              <CaseSnapshot
                intake={intake}
                result={result}
                currentCoverage={currentCoverage}
                deletingProjectId={deletingProjectId}
                onDownloadChecklist={downloadChecklist}
                onDeleteCurrentProject={() => {
                  void onDeleteCurrentProject();
                }}
              />

              <ReviewSignalsPanel prompts={assistantPrompts} />
            </aside>
          </div>
        ) : (
          <section className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
            <div className="space-y-6">
              <SourceHealthPanel
                indexStatus={indexStatus}
                sourceCount={sources.length}
              />

              <JurisdictionRequestsPanel
                requests={jurisdictionRequests}
                loading={jurisdictionRequestsLoading}
                message={jurisdictionRequestsMessage}
                coverageForRequest={coverageForRequest}
              />

              <AdminAccessPanel
                adminAccessKey={adminAccessKey}
                adminAccessInput={adminAccessInput}
                adminAccessMessage={adminAccessMessage}
                onAdminAccessInputChange={setAdminAccessInput}
                onSaveAdminKey={saveAdminKey}
                onClearAdminKey={clearStoredAdminKey}
              />

              <SourceEditorForm
                sourceForm={sourceForm}
                setSourceForm={setSourceForm}
                sourceSaving={sourceSaving}
                sourceMessage={sourceMessage}
                onSaveSource={() => {
                  void onSaveSource();
                }}
              />

              <IngestionActions
                importDirectory={importDirectory}
                importing={importing}
                importMessage={importMessage}
                reindexMessage={reindexMessage}
                onImportDirectoryChange={setImportDirectory}
                onImportDocuments={() => {
                  void onImportDocuments();
                }}
                onImportSourcePacks={() => {
                  void onImportSourcePacks();
                }}
                onReindexSources={() => {
                  void onReindexSources();
                }}
              />
            </div>

            <SourceCatalog
              sources={sources}
              sourcesLoading={sourcesLoading}
              sourceHealthById={sourceHealthById}
              sourceIndexIssuesById={sourceIndexIssuesById}
              onEditSource={loadSourceIntoForm}
            />
          </section>
        )}
        <LegalFooter onSelectPage={setLegalPage} />
      </div>

      {legalPage && (
        <LegalModal
          page={legalPage}
          onClose={() => {
            setLegalPage(null);
            setPendingSubmit(false);
          }}
          onAcknowledge={
            pendingSubmit && legalPage === "disclaimer"
              ? () => {
                  acknowledge();
                  setLegalPage(null);
                  setPendingSubmit(false);
                  void runSubmitFlow();
                }
              : undefined
          }
        />
      )}

      {clarificationOpen && (
        <ClarificationModal
          questions={clarificationQuestions}
          answers={clarificationAnswers}
          submitting={clarificationSubmitting}
          onAnswerChange={(question, value) =>
            setClarificationAnswers((current) => ({
              ...current,
              [question]: value,
            }))
          }
          onSubmit={() => {
            void onSubmitClarifications();
          }}
          onClose={() => setClarificationOpen(false)}
        />
      )}
    </main>
  );
}
