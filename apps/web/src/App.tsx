import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import type {
  AnalyzeResponse,
  FollowUpQuestion,
} from "@zoning-agent/shared-schema";
import {
  analyzeProject,
  authMode,
  createSession,
  deleteProject,
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
import { useAuth } from "./auth/AuthContext";
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
import { CaseSnapshot } from "./features/projects/CaseSnapshot";
import { ReviewSignalsPanel } from "./features/projects/ReviewSignalsPanel";
import { SavedReviewsPage } from "./features/projects/SavedReviewsPage";
import { ClarificationModal } from "./features/results/ClarificationModal";
import { ResultSection } from "./features/results/ResultSection";
import { ReviewRecordPage } from "./features/results/ReviewRecordPage";
import { useAddressAutocomplete } from "./hooks/useAddressAutocomplete";
import { useCoverage } from "./hooks/useCoverage";
import { useFeedback } from "./hooks/useFeedback";
import { useLegalAck } from "./hooks/useLegalAck";
import { useSourcesAdmin } from "./hooks/useSourcesAdmin";
import { useTrace } from "./hooks/useTrace";

export function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsMessage, setProjectsMessage] = useState("");
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(
    null,
  );
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { authSession, currentUser, signOut } = useAuth();
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
  // Workspace is driven by the route (/review vs /admin) so navigation and the
  // header tabs stay in sync and deep links work. /reviews/:projectId renders
  // the saved-review record under the Saved reviews tab.
  const { projectId: recordProjectId } = useParams<{ projectId: string }>();
  const workspace: Workspace =
    location.pathname === "/admin"
      ? "admin"
      : location.pathname.startsWith("/reviews")
        ? "saved"
        : "assistant";
  const setWorkspace = (next: Workspace) =>
    navigate(
      next === "admin" ? "/admin" : next === "saved" ? "/reviews" : "/review",
    );
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
  const canLoadPrivateData =
    authMode === "supabase" ? Boolean(authSession) : true;
  const canUseAdminTools =
    authMode === "supabase" ? currentUser?.role === "admin" : true;
  const {
    sources,
    sourcesTotal,
    sourcesLoadingMore,
    loadMoreSources,
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
      setActiveStageIndex((current) =>
        Math.min(current + 1, PIPELINE_STAGE_COUNT - 1),
      );
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

  // Bounce non-admins off /admin, but only once we actually know their role —
  // otherwise an admin deep-linking /admin gets kicked before currentUser loads.
  useEffect(() => {
    if (workspace !== "admin") {
      return;
    }
    if (authMode === "supabase" && currentUser && currentUser.role !== "admin") {
      navigate("/review", { replace: true });
    }
  }, [workspace, currentUser, navigate]);

  // Seed the address from the hero CTA or a saved-review re-run (?address=…),
  // then drop the param so it doesn't re-apply on later renders. Runs on every
  // param change because App stays mounted across /review and /reviews routes.
  useEffect(() => {
    const seeded = searchParams.get("address");
    if (seeded) {
      setAddress(seeded);
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete("address");
      setSearchParams(nextParams, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

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
    navigate("/");
  }

  async function runAnalysis(
    projectId: string,
    answers?: Record<string, string>,
  ) {
    setPhase("analyzing");
    setActiveStageIndex(0);
    const analysis = await analyzeProject(projectId, answers);

    if (
      analysis.status === "needs_clarification" &&
      analysis.followUpQuestions.length > 0
    ) {
      setResult(analysis);
      setPhase("done");
      void refreshProjects();
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
      return;
    }

    // Final determination: hand off to the permanent record page and clear
    // the runner so /review is a fresh form next time. Saved reviews only
    // exist for Supabase accounts; other auth modes keep the in-place result.
    if (authMode === "supabase") {
      await refreshProjects();
      navigate(`/reviews/${projectId}`, { state: { result: analysis } });
      resetWorkspace();
      return;
    }

    setResult(analysis);
    setPhase("done");
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

  const railHasCase = Boolean(intake || result);
  const railHasSignals = assistantPrompts.length > 0;

  return (
    <main className="min-h-screen">
      <div className="enter">
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
      </div>

      <div className="mx-auto max-w-[1040px] px-4 py-8 md:px-6 md:py-10">
        {workspace === "assistant" ? (
          <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
            <section className="enter enter-1 min-w-0 space-y-6">
              <ProjectIntakePanel
                phase={phase}
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

              <AnimatePresence initial={false}>
                {phase !== "idle" && phase !== "error" && (
                  <motion.div
                    key="pipeline"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <PipelineProgress
                      phase={phase}
                      activeStageIndex={activeStageIndex}
                      stages={displayedStages}
                    />
                  </motion.div>
                )}
              </AnimatePresence>

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

            <aside className="enter enter-2 space-y-5 lg:sticky lg:top-6 lg:self-start">
              <AnimatePresence initial={false}>
                {!railHasCase && !railHasSignals && (
                  <motion.section
                    key="case-file-empty"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="sheet p-5"
                  >
                    <h2 className="text-sm font-bold text-ink">Case file</h2>
                    <p className="mt-2 text-sm leading-6 text-ink-soft">
                      Details appear here as the review runs.
                    </p>
                  </motion.section>
                )}

                {railHasCase && (
                  <motion.div
                    key="case-snapshot"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
                  >
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
                  </motion.div>
                )}

                {railHasSignals && (
                  <motion.div
                    key="review-signals"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.45, delay: 0.07, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <ReviewSignalsPanel prompts={assistantPrompts} />
                  </motion.div>
                )}
              </AnimatePresence>
            </aside>
          </div>
        ) : workspace === "saved" ? (
          recordProjectId ? (
            <ReviewRecordPage
              projectId={recordProjectId}
              projects={projects}
              projectsLoading={projectsLoading}
              coverage={coverage}
              isAdmin={canUseAdminTools}
              onDeleted={() => {
                setProjects((current) =>
                  current.filter(
                    (item) => item.projectId !== recordProjectId,
                  ),
                );
                setProjectsMessage("Review deleted.");
                navigate("/reviews");
              }}
            />
          ) : (
            <SavedReviewsPage
              projects={projects}
              projectsLoading={projectsLoading}
              projectsMessage={projectsMessage}
              onRefresh={() => {
                void refreshProjects();
              }}
              onOpenProject={(project) => {
                navigate(`/reviews/${project.projectId}`);
              }}
            />
          )
        ) : (
          <section className="enter enter-1 grid gap-6 xl:grid-cols-[400px_minmax(0,1fr)]">
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
              total={sourcesTotal}
              onLoadMore={() => {
                void loadMoreSources();
              }}
              loadingMore={sourcesLoadingMore}
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
