import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { AnalyzeResponse } from "@zoning-agent/shared-schema";
import { parseAnalysisPayload, type CoverageStatus, type IntakeResponse } from "../api";
import { BenchmarkMark } from "../components/WorkspaceHeader";
import {
  LOADING_PIPELINE_STAGES,
  PIPELINE_STAGE_COUNT,
} from "../constants/pipeline";
import { PipelineProgress } from "../features/assistant/PipelineProgress";
import { ResultSection } from "../features/results/ResultSection";
import type { Phase, ResultView } from "../types/app";
import { buildChecklistDownload, downloadTextFile } from "../utils/downloads";
import demoAnalysisPayload from "../features/landing/demoAnalysis.json";
import demoIntakePayload from "../features/landing/demoIntake.json";

// ponytail: demoAnalysis.json / demoIntake.json are a real captured deterministic-
// provider response (Blacksburg, VA bakery-in-garage scenario), replayed through the
// SAME parseAnalysisPayload() the live analyzeProject()/fetchProjectResult() calls
// use — one parser, no divergence between the demo and a real run's shape.
const DEMO_RESULT: AnalyzeResponse = parseAnalysisPayload(demoAnalysisPayload);
const DEMO_PROJECT_DESCRIPTION =
  "Open a small bakery with 2 employees inside an existing attached garage.";
const DEMO_INTAKE: IntakeResponse = {
  projectId: demoIntakePayload.project_id,
  normalizedAddress: demoIntakePayload.normalized_address,
  district: demoIntakePayload.district,
  placeId: demoIntakePayload.place_id,
  latitude: demoIntakePayload.latitude,
  longitude: demoIntakePayload.longitude,
  status: "created",
  supportStatus: "supported",
  jurisdictionId: demoIntakePayload.jurisdiction_id,
  jurisdictionName: demoIntakePayload.jurisdiction_name,
  coverageStatus: demoIntakePayload.coverage_status as CoverageStatus,
  planningContact: demoIntakePayload.planning_contact,
  officialSourceUrls: demoIntakePayload.official_source_urls,
  followUpQuestions: [],
};
const STAGE_INTERVAL_MS = 600;

// Logged-out demo: replays a cached real analysis client-side, no /analyze
// call and zero provider spend. Rendered outside RequireAuth in main.tsx.
export function DemoPage() {
  const [phase, setPhase] = useState<Extract<Phase, "analyzing" | "done">>(
    "analyzing",
  );
  const [activeStageIndex, setActiveStageIndex] = useState(0);
  const [resultView, setResultView] = useState<ResultView>("checklist");

  useEffect(() => {
    setPhase("analyzing");
    setActiveStageIndex(0);
    let index = 0;
    const interval = window.setInterval(() => {
      index += 1;
      if (index >= PIPELINE_STAGE_COUNT - 1) {
        setActiveStageIndex(PIPELINE_STAGE_COUNT - 1);
        window.clearInterval(interval);
        window.setTimeout(() => setPhase("done"), STAGE_INTERVAL_MS);
        return;
      }
      setActiveStageIndex(index);
    }, STAGE_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, []);

  const stages = useMemo(
    () =>
      phase === "done" && DEMO_RESULT.pipelineStages?.length
        ? DEMO_RESULT.pipelineStages
        : LOADING_PIPELINE_STAGES,
    [phase],
  );

  const showHumanFallback =
    DEMO_RESULT.status === "low_confidence" ||
    DEMO_RESULT.feasibility.decision === "unknown";

  return (
    <div className="min-h-[100dvh]">
      <header className="border-b border-rule bg-sheet">
        <div className="mx-auto flex max-w-[1040px] items-center justify-between gap-4 px-4 py-3.5 md:px-6">
          <Link
            to="/"
            className="flex items-center gap-3"
            aria-label="Zoning Review home"
          >
            <BenchmarkMark className="h-7 w-7" />
            <p className="font-display text-[15px] font-bold tracking-[-0.01em] text-ink">
              Zoning Review
            </p>
          </Link>
          <Link
            to="/signup?intent=review"
            className="btn-primary px-4 py-2 text-sm"
          >
            Sign in to run your own address
          </Link>
        </div>
      </header>

      <div className="mx-auto max-w-[760px] space-y-6 px-4 py-8 md:px-6 md:py-10">
        <div className="sheet p-5">
          <span className="tag tag-neutral">Demo — sample result, not live</span>
          <p className="mt-3 font-mono text-[13px] font-medium text-ink">
            {DEMO_INTAKE.normalizedAddress}
          </p>
          <p className="mt-1 text-sm leading-6 text-ink-soft">
            {DEMO_PROJECT_DESCRIPTION}
          </p>
        </div>

        <PipelineProgress
          phase={phase}
          activeStageIndex={activeStageIndex}
          stages={stages}
        />

        {phase === "done" && (
          <ResultSection
            result={DEMO_RESULT}
            resultView={resultView}
            trace={[]}
            traceLoading={false}
            feedbackNote=""
            feedbackState="idle"
            feedbackMessage=""
            showHumanFallback={showHumanFallback}
            showTrace={false}
            showFeedback={false}
            onResultViewChange={setResultView}
            onFeedbackNoteChange={() => {}}
            onSubmitFeedback={() => {}}
            onDownloadChecklist={() => {
              downloadTextFile(
                "zoning-checklist-demo.txt",
                buildChecklistDownload(
                  DEMO_INTAKE,
                  DEMO_RESULT,
                  DEMO_PROJECT_DESCRIPTION,
                ),
              );
            }}
          />
        )}
      </div>
    </div>
  );
}
