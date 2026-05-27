import type { PipelineStageReport } from "@zoning-agent/shared-schema";

export const PIPELINE_STAGE_COUNT = 5;

export const LOADING_PIPELINE_STAGES: PipelineStageReport[] = [
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
