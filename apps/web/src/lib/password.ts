// Password strength maps to verdict semantics: weak = stop, fair = hold,
// strong = ok — the same colour language the product uses for determinations.
export const STRENGTH = [
  { label: "Too short", tone: "bg-verdict-stop", width: "20%" },
  { label: "Weak", tone: "bg-verdict-stop", width: "40%" },
  { label: "Fair", tone: "bg-verdict-hold", width: "62%" },
  { label: "Good", tone: "bg-verdict-ok", width: "82%" },
  { label: "Strong", tone: "bg-verdict-ok", width: "100%" },
];

export function scorePassword(pw: string): number {
  if (!pw) return 0;
  let score = 0;
  if (pw.length >= 8) score += 1;
  if (pw.length >= 12) score += 1;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score += 1;
  if (/\d/.test(pw) || /[^A-Za-z0-9]/.test(pw)) score += 1;
  return Math.min(score, 4);
}
