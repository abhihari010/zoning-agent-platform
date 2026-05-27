import type { LegalPage } from "../types/app";

export const DISCLAIMER =
  "Educational guidance only. Zoning rules, permit triggers, and code interpretations must be verified with the official planning department before you rely on this result.";

export function legalCopy(page: Exclude<LegalPage, null>): { title: string; paragraphs: string[] } {
  if (page === "privacy") {
    return {
      title: "Privacy Policy",
      paragraphs: [
        "We store account identity, project addresses, project descriptions, generated analyses, feedback, and jurisdiction support requests so users can return to their work and so we can improve coverage.",
        "Do not submit confidential legal, financial, medical, or highly sensitive personal information. Signed-in users can delete saved projects in the app and can request full account deletion from the app operator.",
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
