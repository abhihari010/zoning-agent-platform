# Product

## Register

product

The marketing landing (`/`, `MarketingShell` + `pages/Home`) is a **brand** surface — override to `brand` per-task when working on it. Everything under `/review` and `/admin`, plus the auth pages, is **product**. Pick register from the surface in focus.

## Users

- **Primary:** property owners and small-scale developers evaluating whether a project (a home bakery, an ADU, a use change, an addition) is even legal at a given address — before spending on architects, attorneys, or permit filings. Often non-experts, intimidated by zoning code, working early and exploratory.
- **Secondary:** land-use consultants and realtors who vet feasibility for clients and want the ordinance sections in front of them fast (the Dana Merritt persona on the landing).
- **Context / job to be done:** "Tell me what I can build at this address, backed by the actual ordinance, and be honest when you don't know." They want a fast, trustworthy read with sources they — or their planner — can verify in minutes.

## Product Purpose

A staged zoning-feasibility pipeline: an address plus a plain-language project description becomes an ordinance-backed determination — with the exact code sections it rests on, a confidence level, and a permit checklist. It exists because reading zoning code is slow, jurisdiction-specific, and error-prone. Success is a user getting a correct, well-cited determination (or an honest abstention) in about a minute, and trusting it enough to act. It is educational guidance, not legal approval — a well-cited starting point to confirm with the planning department.

## Brand Personality

Authoritative and honest. It speaks like a determination letter, not a marketing bot: precise, plain-spoken, calm. Confident about what the ordinance actually says; explicit and unembarrassed when coverage is incomplete. Sentence case, active voice, no hype, no exclamation marks. Three words: **precise, trustworthy, candid.**

## Anti-references

- **Generic AI SaaS landing.** The three saturated defaults — cream/serif/terracotta; near-black + acid-green; equal three-card feature grids — plus the hero-metric template and an uppercase tracked eyebrow above every section. The whole redesign was a reaction to "boring, mundane, templated."
- **Over-carded UI.** A bordered box around every content group. Only the determination record earns a card; everything else is structured with space and alignment.
- **Overconfident legal-tech.** Anything that looks like it dispenses legal certainty or approval. The honesty about uncertainty is a differentiator, not fine print to bury.

## Design Principles

1. **Show the receipts.** Every determination points to the ordinance section it came from; never assert without a citation. (Also a hard backend invariant — no citation, no confident answer.)
2. **Honest about the edges.** When source coverage is incomplete, say so and abstain rather than synthesize. Uncertainty is shown plainly, not hidden.
3. **The record is the hero.** The product's one real-world object is the determination record. Earn every other container; structure with whitespace and alignment, not boxes.
4. **Plain-spoken expertise.** Write like a determination letter: precise, sentence case, active voice, zero hype. Name things by what the user controls, not by how the system is built.
5. **Restraint with one signature.** One accent per surface, one signature moment (the stamp landing). Nothing loops or decorates without purpose, and reduced motion is always honored.

## Accessibility & Inclusion

WCAG 2.1 AA. Body text ≥4.5:1 against its background (verify `ink.soft` #A7AEBE and `ink.faint` #828A9B on every dark surface); large text ≥3:1. Visible keyboard focus everywhere — a 3px azure ring, since there is one accent and one surface family. All motion gated behind a single `prefers-reduced-motion: reduce` block that falls back to the finished state (no gated-visibility reveals). Not colorblind-dependent: verdicts carry a text label, not color alone.
