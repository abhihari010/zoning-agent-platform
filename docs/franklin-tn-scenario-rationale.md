# Franklin TN Eval Scenario Rationale

Candidate labels for `apps/api/tests/eval/datasets/franklin-tn.json`.
All ordinance references are to the scraped corpus at
`apps/api/app/data/source_packs/tn/franklin-tn/manifest.json` (24 chapters, chapter-level section_refs).
**These are CANDIDATE labels. Human sign-off required at Gate 1 before they become the eval gate.**

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
- **Basis:** Chapter 5 (§5.1.3 — "Vape Shops" appears in the INDUSTRIAL USES section of the principal use table, alongside uses like Self-Storage Facilities, Vehicle Repair Facilities, and Wrecker Service — not in the commercial use section); NC is a commercial district and would not permit industrial uses.
- **Why this decision:** The Ch5 table explicitly categorizes Vape Shops as an industrial use, not a commercial/retail use. NC district permits commercial and civic uses; it does not permit industrial uses. A blank cell in the table for NC × Vape Shops means not permitted.
- **Uncertainty flag:** The actual dot-pattern in the scraped PDF table is not machine-readable; the industrial classification is inferred from the section header grouping. **Human reviewer: verify which districts show a dot for Vape Shops in the physical ordinance.**

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
- **Expected:** `unknown` — `should_abstain: true`
- **Basis:** Chapter 5 (§5.2 accessory uses table — "Microbreweries/Craft Distilleries" is listed as an *accessory* use, not as a principal use in §5.1.3); there is no principal use category in the Ch5 table for craft brewery as a standalone operation.
- **Why this decision:** The ordinance classifies microbreweries/craft distilleries as accessory uses only. A standalone craft brewery as a primary business does not map cleanly to any principal use category. It is not "restaurants" (production-focused), not "retail" (manufacturing element), and not "light industrial uses" (taproom serving the public). Per §5.1.1.C, an unlisted-use determination would be required from the Department of Building and Neighborhood Services. The pipeline should return unknown/low-confidence rather than fabricate a classification.
- **Uncertainty flag:** If the pipeline classifies it as Light Industrial Uses (LI/HI district only) or as a restaurant (commercial districts), the label may need revision based on what similar-use determination Franklin actually applies.
