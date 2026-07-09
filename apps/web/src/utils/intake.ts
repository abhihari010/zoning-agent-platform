import type { IntakeResponse } from "../api";
import type { IntakeFacts } from "../types/app";

export function emptyIntakeFacts(): IntakeFacts {
  return {
    useType: "",
    constructionScope: "",
    operatingHours: "",
    employeeCount: "",
    parkingLoading: "",
    foodService: "",
  };
}

export function buildProjectContext(projectDescription: string, facts: IntakeFacts): string {
  const factLines = [
    ["Use type", facts.useType],
    ["Construction scope", facts.constructionScope],
    ["Operating hours", facts.operatingHours],
    ["Number of employees", facts.employeeCount],
    ["Parking/loading", facts.parkingLoading],
    ["Food preparation or service", facts.foodService],
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

export function intakeErrorMessage(intakeResult: IntakeResponse): string {
  if (intakeResult.supportStatus === "unsupported") {
    const jurisdiction = intakeResult.jurisdictionName ?? "this jurisdiction";
    return `${jurisdiction} was recognized, but source coverage is not ready for zoning review yet. Try a supported jurisdiction or contact the planning office directly.`;
  }
  return "The address could not be validated. Enter a complete street address with city and state, then try again.";
}
