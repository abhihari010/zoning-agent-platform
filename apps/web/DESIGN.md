---
name: Zoning Review
description: An ordinance-backed zoning-feasibility tool that reads like an instrument panel for the built environment.
colors:
  dusk: "#0A0B0F"
  dusk-deep: "#060709"
  sheet: "#101319"
  well: "#171B23"
  ink: "#F4F6FB"
  ink-soft: "#A7AEBE"
  ink-faint: "#828A9B"
  rule: "#232833"
  rule-strong: "#333A47"
  dusk-line: "#FFFFFF12"
  azure: "#5B8CFF"
  azure-deep: "#456FE6"
  azure-bright: "#93B2FF"
  azure-wash: "#141B2E"
  verdict-ok: "#4ADE9E"
  verdict-okwash: "#0E211B"
  verdict-hold: "#F2B44C"
  verdict-holdwash: "#241C0E"
  verdict-stop: "#F27A5C"
  verdict-stopwash: "#251310"
typography:
  display:
    fontFamily: "Public Sans, system-ui, -apple-system, sans-serif"
    fontSize: "clamp(2.5rem, 6vw, 4.25rem)"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Public Sans, system-ui, sans-serif"
    fontSize: "clamp(1.9rem, 4vw, 2.9rem)"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Public Sans, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.375
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Public Sans, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.65
    letterSpacing: "normal"
  label:
    fontFamily: "Public Sans, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.16em"
  data:
    fontFamily: "JetBrains Mono, SFMono-Regular, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "normal"
rounded:
  sm: "2px"
  md: "6px"
  lg: "8px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "16px"
  lg: "24px"
  shell: "1180px"
components:
  button-primary:
    backgroundColor: "{colors.azure}"
    textColor: "{colors.dusk-deep}"
    rounded: "{rounded.md}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.azure-bright}"
    textColor: "{colors.dusk-deep}"
    rounded: "{rounded.md}"
    padding: "10px 16px"
  button-outline:
    backgroundColor: "{colors.well}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "10px 16px"
  button-quiet:
    backgroundColor: "{colors.dusk}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.md}"
    padding: "10px 16px"
  button-danger:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.verdict-stop}"
    rounded: "{rounded.md}"
    padding: "10px 16px"
  sheet:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
  field:
    backgroundColor: "{colors.well}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "10px 14px"
  chip:
    backgroundColor: "{colors.well}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  chip-selected:
    backgroundColor: "{colors.azure-wash}"
    textColor: "{colors.azure-bright}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  tag-ok:
    backgroundColor: "{colors.verdict-okwash}"
    textColor: "{colors.verdict-ok}"
    rounded: "{rounded.md}"
    padding: "2px 8px"
  tag-hold:
    backgroundColor: "{colors.verdict-holdwash}"
    textColor: "{colors.verdict-hold}"
    rounded: "{rounded.md}"
    padding: "2px 8px"
  tag-stop:
    backgroundColor: "{colors.verdict-stopwash}"
    textColor: "{colors.verdict-stop}"
    rounded: "{rounded.md}"
    padding: "2px 8px"
  stamp:
    textColor: "{colors.verdict-ok}"
    typography: "{typography.data}"
    rounded: "{rounded.sm}"
    padding: "12px 24px"
---

# Design System: Zoning Review

## 1. Overview

**Creative North Star: "The Instrument Panel"**

This is a reading instrument for the built environment. The surface is a cool near-black panel, unlit except where it has something to tell you, and the one thing it lights up in is azure. The reference object is neither a document nor a dashboard: it is a precision instrument whose display stays dark until a measurement lands. Everything on screen is the reading, the evidence behind the reading, or the control that produced it.

Density is calm rather than packed. Structure comes from whitespace and alignment first and containers second, which is why the determination record is the only element that earns a card. Colour is rationed hard: one azure accent carries every interactive affordance across the entire product, and the only other colours permitted on the surface are the three verdict semantics. That rationing is the whole system. Because azure never means "permitted", a green chip can only ever mean permitted.

What this explicitly rejects: the generic AI SaaS landing in all three of its saturated forms (cream/serif/terracotta, near-black with acid-green, equal three-card feature grids), the hero-metric template, and the uppercase tracked eyebrow stacked above every section. It also rejects over-carding, a bordered box drawn around every group of content, and anything that reads as dispensing legal certainty. The product's honesty about the limits of its own coverage is a differentiator, not fine print.

**Key Characteristics:**

- Cool near-black surfaces (`#0A0B0F` page, `#101319` panel) with zero warm tint anywhere
- Exactly one brand accent (azure `#5B8CFF`), used on well under 10% of any screen
- Verdict colour is semantic and reserved; it never decorates
- One typeface (Public Sans) in many weights, plus a mono strictly for record data
- Depth from tonal layering and soft ambient shadow, never from borders drawn for effect
- Sentence case everywhere; no hype, no exclamation marks

## 2. Colors

A cool near-black instrument panel lit by a single azure accent, with three reserved verdict semantics and nothing else.

### Primary

- **Instrument Azure** (`#5B8CFF`): The only brand colour. Primary buttons, focus rings, selected chips, links, active navigation, and every interactive affordance in the product. Deliberately reused for the marketing highlight rather than introducing a second accent.
- **Azure Pressed** (`#456FE6`): Hover and pressed states on solid azure surfaces.
- **Azure Bright** (`#93B2FF`): Azure lightened for legibility as *text* or icons on dark surfaces, where the base azure is too dim to hold contrast.
- **Azure Wash** (`#141B2E`): Barely-there azure fill behind selected chips and accent surfaces on dark.

### Secondary

There is no secondary brand colour, by design. See The One Instrument Rule.

### Tertiary

- **Permitted Green** (`#4ADE9E`) over **Permitted Wash** (`#0E211B`): The project is allowed.
- **Conditional Amber** (`#F2B44C`) over **Conditional Wash** (`#241C0E`): Allowed subject to conditions, a special-use permit, or a variance.
- **Prohibited Coral** (`#F27A5C`) over **Prohibited Wash** (`#251310`): Not allowed under the cited ordinance. Coral rather than red: this reports a finding, it does not raise an alarm.

### Neutral

- **Panel Black** (`#0A0B0F`): The page. The default state of the instrument.
- **Contrast Band** (`#060709`): Footer and deliberate contrast bands, one step below the page.
- **Card Surface** (`#101319`): Raised panels and the determination record.
- **Recessed Well** (`#171B23`): Inputs, chips, and hover fills; reads as recessed against the card.
- **Signal White** (`#F4F6FB`): Primary text and headings.
- **Secondary Ink** (`#A7AEBE`): Body copy and supporting text. AA on every dark surface in the system.
- **Meta Ink** (`#828A9B`): Metadata, placeholders, and mono labels. Verified at 4.5:1 on all dark surfaces; this is the floor, not a suggestion.
- **Hairline** (`#232833`) and **Hairline Strong** (`#333A47`): Borders at rest and on hover or focus.
- **Translucent Hairline** (`#FFFFFF12`): A 7% white rule that adapts over any dark surface, used where the underlying tone varies.

### Named Rules

**The One Instrument Rule.** One accent, azure, carries every interactive affordance in the entire product. There is no secondary brand colour and none may be introduced. If a new element needs to stand out, it earns that through weight, size, or space, never a new hue.

**The Reserved Verdict Rule.** Green, amber, and coral are reserved exclusively for determination outcomes via the `verdict` tokens. The brand accent never uses them and decoration never borrows them. A green chip means permitted. It can mean nothing else.

**The No Warm Tint Rule.** Every neutral in this system is cool. Warm greys, cream, sand, and paper tones are forbidden on every surface. If a neutral looks beige next to `#0A0B0F`, it is wrong.

## 3. Typography

**Display Font:** Public Sans (with `system-ui`, `-apple-system`, `sans-serif`)
**Body Font:** Public Sans (same family, lighter weights)
**Label/Mono Font:** JetBrains Mono (with `SFMono-Regular`, `Consolas`, `monospace`)

**Character:** Public Sans is the US Web Design System typeface, the face of American civic documents. That is the entire reason it is here: a product whose voice is a determination letter should be set in the type of the institutions it reads. It is sturdy and unfashionable in the right way. One family carries display through body on weight alone, which avoids the muddy hierarchy of two sans-serifs that are similar without being identical.

### Hierarchy

- **Display** (700, `clamp(2.5rem, 6vw, 4.25rem)`, 1.05): The landing hero, once per page. Tracking tightens to `-0.02em` at this size.
- **Headline** (700, `clamp(1.9rem, 4vw, 2.9rem)`, 1.15): Marketing section headings. Fluid, because marketing type dominates its own layout.
- **Title** (700, 1.125rem, 1.375): Card and record titles in the product. Fixed, never fluid.
- **Body** (400, 15px, 1.65): All prose. Measure capped at 65–75ch; the landing pull-quote tightens to 27ch deliberately.
- **Label** (600, 11px, `0.16em`, uppercase): The eyebrow micro-label, set in azure-bright.
- **Data** (500, 13px, mono): Section references, addresses, dates, IDs, confidence values, and every citation. Numeric columns add `tabular-nums`.

### Named Rules

**The Mono-Is-Evidence Rule.** JetBrains Mono is reserved for record data: ordinance section references, addresses, effective dates, IDs, and confidence figures. Never for prose, never for emphasis, never decoratively. Mono on this surface is a claim that the string is quoted from a source.

**The Rationed Eyebrow Rule.** The uppercase 11px label is deliberately rare. It is forbidden above every section; that pattern is the single most saturated AI-landing tell. One per surface at most, and only where it names something real.

**The Fixed Product Rule.** Fluid `clamp()` type belongs to marketing surfaces only. Everything under `/review` and `/admin` uses a fixed rem scale, because dense container layouts need spatial predictability that fluid type destroys.

## 4. Elevation

Depth comes from tonal layering first and ambient shadow second. Surfaces step through the neutral ramp rather than being pushed apart by hard borders: page (`#0A0B0F`), card (`#101319`), recessed well (`#171B23`). Shadows are cool, wide, and very soft, and they exist to detach a panel from the page, never to draw a visible edge. Nothing on this surface casts the tight dark drop shadow of a 2014 app; if an edge is legible as a shadow rather than felt as depth, the blur is too small.

### Shadow Vocabulary

- **Sheet** (`0 1px 0 rgba(255,255,255,0.02), 0 16px 40px -32px rgba(0,0,0,0.9)`): Cards at rest. The first value is a 2% top highlight that reads as a lit edge, not a border.
- **Raised** (`0 1px 0 rgba(255,255,255,0.03), 0 28px 60px -34px rgba(0,0,0,0.9)`): Cards on hover, paired with a 1px lift.
- **Glow** (`0 0 0 1px rgba(91,140,255,0.24), 0 24px 70px -30px rgba(91,140,255,0.35)`): Azure ambient glow for focused and hero surfaces. The one place a shadow carries brand colour.
- **Float** (`0 30px 80px -40px rgba(0,0,0,0.85)`): Overlays and floating panels.

### Named Rules

**The Lit-Edge Rule.** Every raised surface carries a 2–3% white top highlight before it carries a shadow. On a near-black panel, light reads as elevation more convincingly than darkness does.

**The Response-Only Rule.** Shadows deepen only in response to state (hover, focus, elevation). A surface at rest never advertises depth it has not earned.

## 5. Components

### Buttons

- **Shape:** Softly squared (6px radius). Never pill, never sharp.
- **Primary:** Solid azure (`#5B8CFF`) with near-black text (`#060709`), 10px/16px padding, plus a 28% white inset top highlight so the fill reads as lit rather than flat.
- **Hover / Focus:** Lifts 1px, brightens to `#93B2FF`, and drops an azure glow. Transitions run 150ms on an ease-out-expo curve. Active presses to 98% scale.
- **Outline:** Strong hairline border over a 60% well fill, signal-white text. Border warms to meta ink on hover.
- **Quiet:** Transparent until hover, when it fills to the well and text steps from secondary to signal white. This is the default for anything secondary; the product should never look like a row of competing buttons.
- **Danger:** Never solid. Coral text on the card surface with a 30% coral border, filling to the prohibited wash on hover. Destructive actions are stated, not shouted.

### Chips

- **Style:** Recessed well fill, strong hairline border, secondary-ink text at 13px medium, 6px/12px padding.
- **State:** Selected (`aria-pressed="true"`) shifts to a 10% azure fill with an azure border and azure-bright text. Presses to 97% scale.

### Cards / Containers

- **Corner Style:** Gently rounded (8px), one step softer than buttons and inputs.
- **Background:** Card surface (`#101319`) against the page.
- **Shadow Strategy:** `sheet` at rest, `raised` on hover with a 1px lift over 260ms.
- **Border:** A single hairline (`#232833`), strengthening on hover. Never more than 1px, and never coloured as an accent stripe.
- **Internal Padding:** 16–24px.
- **Doctrine:** Only the determination record and true document surfaces earn a card. Content groups do not.

### Inputs / Fields

- **Style:** Recessed well fill, strong hairline border, 6px radius, 15px signal-white text, meta-ink placeholder, 10px/14px padding.
- **Focus:** Border turns azure and a 3px 22% azure ring appears. The native outline is removed only because the ring replaces it; focus is never invisible.
- **Dusk variant:** On marketing and auth surfaces, the same field sits on the panel tone with a translucent hairline, so it reads correctly against a varying background.

### Navigation

- **Style:** Text-only links at 14px medium in secondary ink, transitioning to signal white on hover over 150ms. No underlines at rest, no pills, no boxes. The active workspace tab is the only navigation element permitted to carry the accent.

### The Determination Stamp

The product's one signature element and its single moment of personality. A monospaced, uppercase, `0.14em`-tracked verdict block, rotated -2°, with a 1.5px border, an inset ring at 3px, and a `currentColor` text glow. It inherits its colour entirely from the verdict semantics, so the stamp *is* the reading. It appears once, when a determination lands, and never as decoration.

## 6. Do's and Don'ts

### Do:

- **Do** ration the accent. Azure (`#5B8CFF`) appears on well under 10% of any screen; its rarity is what makes it read as a control.
- **Do** reserve green, amber, and coral for determination outcomes only, through the `verdict` tokens.
- **Do** structure with whitespace and alignment. Only the determination record earns a card.
- **Do** set every ordinance reference, address, date, and confidence value in JetBrains Mono. Mono is the visual claim that a string is quoted.
- **Do** keep body copy at 15px/1.65 in secondary ink (`#A7AEBE`), measured at 65–75ch.
- **Do** use fixed rem type in the product and fluid `clamp()` only on marketing surfaces.
- **Do** gate every animation behind `prefers-reduced-motion: reduce`, falling back to the finished state.
- **Do** carry verdict meaning in a text label as well as colour. Nothing here may be colourblind-dependent.
- **Do** give every raised surface a 2–3% white top highlight before giving it a shadow.

### Don't:

- **Don't** introduce a second brand colour. There is one accent and it is azure.
- **Don't** let the brand accent borrow verdict colours, or verdict colours decorate anything that is not a verdict.
- **Don't** use warm neutrals. Cream, sand, paper, beige, and parchment tones are forbidden on every surface, and token names for them are a tell in themselves.
- **Don't** build a **generic AI SaaS landing**: no cream/serif/terracotta, no near-black with acid-green, no equal three-card feature grid, no hero-metric template.
- **Don't** stack an uppercase tracked eyebrow above every section. One per surface at most.
- **Don't** over-card. A bordered box around every content group is the failure mode this system was built against, and nested cards are always wrong.
- **Don't** look like **overconfident legal-tech**. Nothing may imply legal certainty or approval. Uncertainty is shown plainly, never buried.
- **Don't** use `border-left` or `border-right` above 1px as a coloured accent stripe.
- **Don't** use gradient text, decorative glassmorphism, or bounce and elastic easing. Motion eases out on `cubic-bezier(0.16, 1, 0.3, 1)`.
- **Don't** set prose in mono, or set record data in the sans.
- **Don't** drop below 4.5:1 for body text. Meta ink (`#828A9B`) is the floor on every dark surface, not a starting point.
