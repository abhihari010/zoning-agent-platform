import type { SourceRegistryEntry } from "../api";

export function emptySourceForm(): SourceRegistryEntry {
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

export function parseTagList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
