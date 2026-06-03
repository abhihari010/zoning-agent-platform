# Franklin TN Eval Scenario Rationale

Candidate labels for `apps/api/tests/eval/datasets/franklin-tn.json`.
All ordinance references are to the scraped corpus at
`apps/api/app/data/source_packs/tn/franklin-tn/manifest.json` (24 chapters, chapter-level section_refs).
**These are CANDIDATE labels. Human sign-off required at Gate 1 before they become the eval gate.**

---

## Known limitation — Ch5 use-table fidelity

Franklin's zoning ordinance was published exclusively via a FlippingBook viewer
(`web.franklintn.gov/flippingbook/FranklinZoningOrdinance`). The Chapter 5 permitted-use table
renders per-district permission markers (solid dots, half-black dots, blank cells) as image-only
glyphs in the page image layer. The FlippingBook HTML text layer contains the use names and section
headers (e.g. "AGRICULTURAL USES", "INDUSTRIAL USES") but **zero** permission glyphs for any
district column. FlippingBook download is disabled (403/404 on asset paths), so the matrix is not
recoverable by re-scraping.

**Part A search result (2026-06-02):** Checked four sources — (1) `franklintn.gov` planning/zoning
page returns only the FlippingBook viewer; (2) Granicus/Legistar BOMA agenda packets for Ordinance
2025-25 — no direct PDF surfaced in search results; (3) Municode Title 14 — previously confirmed to
be an MTAS stub, not the 2026 ordinance; (4) Williamson County GIS / APA knowledgebase — no
text-layer export found. **No qualifying text-layer PDF was found.** The FlippingBook viewer is the
sole published source for the adopted ordinance.

**How scenarios compensate:** The pipeline can reason from (a) use classification (section header
grouping in the text layer), (b) §5.1.4 additional use regulation prose (full text in corpus),
(c) Chapter 20 review-procedure lists, and (d) Chapter 3 district purpose statements and dimensional
standards. Scenarios are grounded in one or more of these text-readable sources. No scenario relies
on reading a specific dot in the use-table matrix. See per-scenario rationale below.

**Promotion blocker:** `coverage_status` stays `source_indexed`. Promotion to `public_supported`
requires a text-layer use table (structured permission-matrix feed) — a deferred future workstream
separate from this pilot.

---

### franklin-tn-sfr-r3
- **Project:** Build a new single-family home on a 10,500 sq ft lot in a residential subdivision.
- **Expected:** `likely_allowed`
- **Basis:** Chapter 3 (§3.6 R3 district — minimum lot size 9,000 sq ft, house building type permitted); Chapter 5 (§5.1.3 permitted principal uses table — "Single-Family Residential" is a residential use listed in the table; house building type is the permitted type in R3).
- **Why this decision:** R3 is explicitly an SFR district; a 10,500 sq ft lot exceeds the 9,000 sq ft minimum. SFR is the canonical permitted use in R3 — no additional use regulations apply per §5.1.4. A building permit is required but no site plan is needed for a single house per §20.12.4.A.

---

### franklin-tn-restaurant-dd
- **Project:** Open a full-service sit-down restaurant with a bar in an existing Downtown District storefront.
- **Expected:** `likely_allowed`
- **Basis:** Chapter 5 (§5.1.3 — "Restaurants" listed as a principal commercial use; DD is one of the districts in the use table); Chapter 3 (§3.15 DD district purpose — "vibrant downtown core with a variety of pedestrian-scale commercial, civic, and residential uses").
- **Why this decision:** A restaurant in the DD is a textbook permitted use; the DD purpose clause explicitly envisions commercial uses. No use-specific additional regulations in §5.1.4 apply to basic sit-down restaurants. Occupying an *existing* storefront requires a building permit but is exempt from site plan review per §20.12.4.

---

### franklin-tn-retail-nc
- **Project:** Open a small clothing boutique in a neighborhood commercial strip center.
- **Expected:** `likely_allowed`
- **Basis:** Chapter 5 (§5.1.3 — "Retail" listed as a principal commercial use; NC is included in the permitted districts column); Chapter 3 (§3.13 NC purpose — "pedestrian-oriented, small-scale commercial nodes that serve surrounding residential neighborhoods").
- **Why this decision:** A small retail shop is precisely the use the NC district is designed for. No use-specific additional regulations in §5.1.4 apply to standard retail. The NC district lists commercial/mixed-use building types as permitted.

---

### franklin-tn-manufacturing-r2
- **Project:** Establish a metal fabrication and light manufacturing shop in an R2 residential neighborhood.
- **Expected:** `restricted`
- **Basis:** Chapter 5 (§5.1.3 — industrial uses including "Light Industrial Uses" and "Machinery Assembly and Repair Facilities" appear in the industrial uses section of the table; R2 is a residential district not in the permitted columns for industrial uses); Chapter 3 (§3.5 R2 purpose — "single-family residential with lot sizes of at least 15,000 sq ft").
- **Why this decision:** Light manufacturing / metal fabrication falls squarely under the industrial use classification. The R2 district permits only house building types and SFR uses. The use table shows a blank (not permitted) cell for industrial uses in residential districts. §5.1.4 additional regulations for light industrial uses confirm they must be within 500 feet of a residential lot only in PD district.

---

### franklin-tn-vape-nc
- **Project:** Open a vape shop and e-cigarette store in a Neighborhood Commercial strip mall.
- **Expected:** `restricted`
- **Basis (re-anchored from dot lookup to prose):**
  - Chapter 5 §5.1.3 text layer: "Vape Shops" is listed under the **INDUSTRIAL USES** section header alongside Machinery Assembly and Repair Facilities, Self-Storage Facilities, Vehicle Repair Facilities, and Wrecker Service. Section headers are present as text (unlike the dots); this classification is corpus-readable.
  - Chapter 5 §5.1.4.AB: Vape shops carry a mandatory 500-foot setback from any dwelling or residential lot, any CI-zoned property, any recreation use, any day care center, any funeral home, or another vape shop.
  - Chapter 3 §3.13 NC purpose: "pedestrian-oriented, small-scale commercial nodes that **serve surrounding residential neighborhoods**." By design, NC sites are proximate to residential lots.
- **Why this decision:** The specific scenario — a strip mall at 720 Hillsboro Rd in an NC district that serves nearby residents — cannot comply with the §5.1.4.AB 500-foot residential setback. NC districts are expressly sited to serve surrounding residential neighborhoods, making the proximity requirement practically unmet. The industrial use classification (readable from the §5.1.3 section header) additionally signals this is not a commercial use the NC district is designed to accommodate. Together, these produce a `restricted` outcome grounded entirely in corpus prose and use classification text, without relying on the missing per-district dot.
- **Changed from prior label?** The `decision_in: ["restricted"]` is unchanged. The rationale is re-anchored from the unavailable use-table dot to §5.1.4.AB + §3.13 prose (both text-readable). Uncertainty flag removed.

---

### franklin-tn-gas-station-rc4
- **Project:** Develop a new gas station with fuel pumps and convenience store in a regional commercial corridor.
- **Expected:** `conditional` — requires FMPC site plan + additional use regulations
- **Basis:** Chapter 5 (§5.1.4.I — gas stations have 6 specific additional use requirements: no arterial-intersection lots, design constraints for pumps/canopies, no adjacency to residential without BOMA approval, pitched roof requirements, canopy clearance limits, exterior materials); Chapter 20 (§20.12.2.C.9 — site plans for gas stations shall be submitted for approval by the FMPC, not administrative DRT).
- **Why this decision:** The use may be permitted in RC4 but it is subject to named additional use regulations per §5.1.4 AND explicitly requires an FMPC (Franklin Municipal Planning Commission) site plan per §20.12. Both conditions must be satisfied before a building permit issues.

---

### franklin-tn-event-venue-dd
- **Project:** Convert a historic Downtown District building into an event/wedding venue for up to 250 guests.
- **Expected:** `conditional` — requires FMPC site plan + adverse-impact findings
- **Basis:** Chapter 5 (§5.1.4.G — event venues must not create substantial adverse impact on adjacent property; must be constructed, arranged, and operated to not dominate the vicinity; must not cause undue traffic congestion through residential streets; conditions may include hours, soundproofing, and landscaping); Chapter 20 (§20.12.2.C.8 — event venues explicitly require site plan approval by the FMPC).
- **Why this decision:** The DD district permits event venues, but this use carries one of the most detailed additional-use regulation blocks in §5.1.4, including a mandatory FMPC site plan. The conversion also involves a historic building, which may trigger HPO/HZC review under §20.12.2.C.3.

---

### franklin-tn-multifamily-cc
- **Project:** Build a 45-unit residential apartment building in the Central Commercial district.
- **Expected:** `conditional` — multifamily requires ground-floor commercial along street frontage in CC
- **Basis:** Chapter 5 (§5.1.4.R.1 — "In the CC and DD districts, where buildings containing multifamily residential are along a street frontage, they must have ground-floor commercial uses along the street frontage"); Chapter 20 (§20.12 — site plan required for new multi-story residential construction).
- **Why this decision:** Multifamily is listed as a permitted use in CC, but §5.1.4.R imposes a mandatory design condition: ground-floor commercial along all street-facing frontages. A stand-alone apartment building without ground-floor commercial would not comply. The pipeline should flag this condition rather than returning a clean likely_allowed.

---

### franklin-tn-stvr-r4
- **Project:** List my historic R4 home as an Airbnb short-term vacation rental while I continue to live there as my primary residence.
- **Expected:** `conditional` — permitted subject to owner-occupancy rules and Municipal Code compliance
- **Basis:** Chapter 5 (§5.1.4.W — short-term vacation rentals require the owner to be a permanent occupant; on a dwelling-only lot where owner vacates, nightly rentals cannot exceed 113 nights in any 12-month rolling period; must comply with applicable Municipal Code requirements).
- **Why this decision:** STVR is a listed use in the principal uses table and the owner-occupancy condition is satisfied as described. However, significant conditions apply (night limits, municipal licensing, etc.) so the correct decision is conditional rather than likely_allowed. The pipeline should surface the permit path through the Municipal Code.

---

### franklin-tn-craft-brewery-standalone
- **Project:** Open a standalone craft brewery as a primary business, producing beer on-site and serving it through an on-site taproom.
- **Expected:** `unknown` — `should_abstain: true` (this is the *correct* expected behavior given the readable corpus; see "Ground truth vs. expected label" below).
- **Basis:** Chapter 5. "Microbreweries/Craft Distilleries" appears only in §5.2.7.I as an *accessory* use permitted when serving a restaurant principal use (≤10% of the restaurant's floor area); §5.2.7.I.3 states that beer/alcohol production exceeding those accessory limits "shall be considered under the industrial use classification." There is **no** standalone brewery/taproom/brewpub principal-use row anywhere in the §5.1.3 permitted-use table.
- **Ground truth (human-verified from the §5.1.3 use-table image during Gate 1 review):** A standalone production brewery is an **industrial** use (§5.2.7.I.3). On the use-table image (page 88, Industrial Uses block), the general industrial rows it would map to — Light Industrial Uses and Heavy Industrial Uses — carry permission markers only in the **LI and HI** columns (Light Industrial also shows the half-black "additional requirements" mark in **PD**, resolved at development-plan approval), with nothing in NC/CC/DD or any commercial column. So the *true* answer for a brewery at a commercial address like 1250 Murfreesboro Rd is **`restricted`** (industrial-only; not permitted in the proposed commercial location). **This determination was read from the page image for labeling only — the per-district dots are image-only and are NOT in the scraped corpus, and were NOT ingested as machine ground truth.**
- **Why the expected label is `abstain`, not `restricted`:** The gate scores what the pipeline produces from the *readable text*. From text alone, §5.2.7.I.3 only establishes "industrial classification" — the LI/HI district placement lives entirely in the image-only use-table dots the pipeline cannot read. The honest pipeline behavior is therefore `unknown`/low-confidence, not a fabricated district determination. Labeling this `restricted` would penalize correct abstention and reward guessing — the opposite of the orchestrator's core invariant ("no citations → return unknown, never synthesize a conclusion"). This row is the dataset's deliberate test of correct abstention when the use-table-fidelity gap makes an exact answer unreachable from text.
- **§5.1.1.C caveat:** A standalone brewery is an unlisted principal use, so the Department of Building & Neighborhood Services (in consultation with Planning) "may make a determination whether such use is substantially similar to a listed use" (§5.1.1.C). A realistic determination would more likely **split** the operation (production = industrial; on-site taproom = accessory/commercial) than reclassify the whole business as commercial. If Franklin has issued such a determination, the ground truth could shift — but it does not change the `abstain` expected label, which reflects pipeline capability against the readable corpus, not the off-ordinance determination.
