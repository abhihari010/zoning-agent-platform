export function formatDateTime(value?: string | null): string {
  if (!value) {
    return "Not recorded";
  }
  return new Date(value).toLocaleString();
}

export function formatLocationParts(...parts: Array<string | null | undefined>): string {
  const values = parts.map((part) => part?.trim()).filter(Boolean);
  return values.length > 0 ? values.join(" / ") : "Location not recorded";
}
