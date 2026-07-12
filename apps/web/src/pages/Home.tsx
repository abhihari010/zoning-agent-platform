import {
  Fragment,
  useRef,
  useState,
  type FormEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { useAuth } from "../auth/AuthContext";
import { useCoverage } from "../hooks/useCoverage";
import { DISCLAIMER } from "../constants/legal";
import { DeterminationCard } from "../features/landing/DeterminationCard";
import { Reveal } from "../features/landing/Reveal";
import { useGsap, gsap } from "../lib/gsap";
import { EASE, fadeUp, hoverLift, inViewOnce, staggerParent } from "../lib/motion";

const DUSK_OUTLINE =
  "inline-flex items-center justify-center gap-2 rounded-md border border-dusk-line bg-transparent px-6 py-3 text-[15px] font-semibold text-paper transition-[transform,border-color,background-color] duration-fast ease-out hover:-translate-y-px hover:border-white/[0.12] hover:bg-dusk-raised active:scale-[0.98]";

/** Azure spotlight that tracks the cursor across the hero. Pointer-events-none
 *  so it never blocks the address bar; reads --mx/--my from the hero section. */
function HeroGlow() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 -z-10 overflow-hidden"
    >
      <div className="absolute inset-0 opacity-[0.5] [background-image:linear-gradient(rgba(147,178,255,0.045)_1px,transparent_1px),linear-gradient(90deg,rgba(147,178,255,0.045)_1px,transparent_1px)] [background-size:44px_44px] [mask-image:radial-gradient(120%_100%_at_50%_0%,black,transparent_74%)]" />
      <div className="absolute inset-0 transition-opacity duration-med [background:radial-gradient(340px_circle_at_var(--mx,70%)_var(--my,18%),rgba(91,140,255,0.15),transparent_66%)]" />
    </div>
  );
}

const HERO_PROOF = [
  { value: "§ cited", label: "Every determination" },
  { value: "< 60s", label: "Address to answer" },
  { value: "$0", label: "Free while in beta" },
];

export function Home() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const reduce = useReducedMotion();
  const [heroAddress, setHeroAddress] = useState("");
  const pageRef = useRef<HTMLDivElement>(null);
  const heroRef = useRef<HTMLElement>(null);
  const { publicSupportedCoverage } = useCoverage();
  const liveCount = publicSupportedCoverage.length;

  // GSAP scroll-scrub layer — reserved for effects Framer can't cleanly do:
  // hero parallax, staggered feature slide-in, and the scale-up preview. All
  // scoped to the page and no-op under reduced motion (see useGsap).
  useGsap(pageRef, () => {
    gsap.to(".gsap-parallax", {
      yPercent: -12,
      ease: "none",
      scrollTrigger: {
        trigger: ".gsap-hero",
        start: "top top",
        end: "bottom top",
        scrub: 0.6,
      },
    });

    gsap.from(".gsap-feature", {
      y: 52,
      opacity: 0,
      duration: 0.85,
      ease: "expo.out",
      stagger: 0.12,
      scrollTrigger: { trigger: ".gsap-features", start: "top 78%", once: true },
    });

    gsap.fromTo(
      ".gsap-dashboard",
      { scale: 0.9, yPercent: 6, opacity: 0.5 },
      {
        scale: 1,
        yPercent: 0,
        opacity: 1,
        ease: "none",
        scrollTrigger: {
          trigger: ".gsap-dashboard",
          start: "top 88%",
          end: "top 42%",
          scrub: 0.6,
        },
      },
    );
  }, []);

  function onHeroMove(event: ReactPointerEvent<HTMLElement>) {
    const el = heroRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${event.clientX - rect.left}px`);
    el.style.setProperty("--my", `${event.clientY - rect.top}px`);
  }

  function startReview(event: FormEvent) {
    event.preventDefault();
    const addr = heroAddress.trim();
    const query = addr ? `?address=${encodeURIComponent(addr)}` : "";
    if (isAuthenticated) {
      navigate(`/review${query}`);
    } else {
      const sep = query ? "&" : "?";
      navigate(`/signup${query}${sep}intent=review`);
    }
  }

  const headline = ["Know what you can build", "before you file."];

  return (
    <div ref={pageRef}>
      {/* ── Hero ───────────────────────────────────────────────── */}
      <section
        ref={heroRef}
        onPointerMove={reduce ? undefined : onHeroMove}
        className="gsap-hero relative overflow-hidden"
      >
        <HeroGlow />
        <div className="mx-auto max-w-shell px-4 pb-20 pt-14 md:px-8 md:pb-32 md:pt-24">
          <div className="grid items-center gap-14 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)] lg:gap-14">
            <div>
              <motion.div
                initial={reduce ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, ease: EASE }}
              >
                <a
                  href="#coverage"
                  className="group inline-flex items-center gap-2 rounded-full border border-dusk-line bg-dusk-panel/60 py-1 pl-1.5 pr-3 text-[12px] text-dusk-soft backdrop-blur transition-colors duration-fast ease-out hover:border-spruce/[0.35]"
                >
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-spruce/15 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-spruce-bright">
                    <span className="status-dot h-1.5 w-1.5 rounded-full bg-spruce-bright" />
                    Live
                  </span>
                  {liveCount > 0
                    ? `${liveCount} Virginia jurisdictions`
                    : "Virginia jurisdictions"}
                  <span className="text-dusk-faint transition-transform duration-fast ease-out group-hover:translate-x-0.5">
                    →
                  </span>
                </a>
              </motion.div>

              {/* Two-line hero: Space Grotesk, -0.02em, weight 600, tight leading. */}
              <h1 className="mt-6 font-display text-[clamp(2.5rem,6vw,4.25rem)] font-semibold leading-[1.02] tracking-display text-paper [text-wrap:balance]">
                {headline.map((line, i) => (
                  <span key={line} className="block overflow-hidden pb-[0.06em]">
                    <motion.span
                      className="block"
                      initial={reduce ? false : { y: "110%" }}
                      animate={{ y: "0%" }}
                      transition={{
                        duration: 0.75,
                        ease: EASE,
                        delay: 0.1 + i * 0.11,
                      }}
                    >
                      {i === 1 ? (
                        <span className="text-dusk-soft">{line}</span>
                      ) : (
                        line
                      )}
                    </motion.span>
                  </span>
                ))}
              </h1>

              <motion.p
                initial={reduce ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, ease: EASE, delay: 0.34 }}
                className="mt-6 max-w-md text-[17px] font-normal leading-[1.8] text-dusk-soft"
              >
                Type an address and what you want to build. Get a determination
                backed by the ordinance sections. Not a guess.
              </motion.p>

              <motion.form
                onSubmit={startReview}
                initial={reduce ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, ease: EASE, delay: 0.42 }}
                className="mt-8 max-w-md"
              >
                <div className="group flex flex-col gap-2 rounded-lg border border-dusk-line bg-dusk-panel/60 p-2 backdrop-blur transition-[border-color,box-shadow] duration-med ease-out focus-within:border-spruce focus-within:shadow-[0_0_0_4px_rgba(91,140,255,0.14)] sm:flex-row sm:items-center">
                  <input
                    aria-label="Property address"
                    value={heroAddress}
                    onChange={(event) => setHeroAddress(event.target.value)}
                    placeholder="412 Draper Rd SW, Blacksburg, VA"
                    className="min-w-0 flex-1 bg-transparent px-3 py-2 font-mono text-[13px] text-paper placeholder:text-dusk-faint focus:outline-none"
                  />
                  <motion.button
                    type="submit"
                    whileHover={reduce ? undefined : { y: -2 }}
                    whileTap={reduce ? undefined : { scale: 0.98 }}
                    transition={{ duration: 0.2, ease: EASE }}
                    className="btn-primary min-h-11 shrink-0 px-5 py-2.5"
                  >
                    Check a property
                  </motion.button>
                </div>
                <p className="mt-2.5 text-xs leading-5 text-dusk-faint">
                  US addresses only. Free while in beta.{" "}
                  <Link
                    to="/login"
                    className="font-medium text-dusk-soft underline-offset-2 hover:text-paper hover:underline"
                  >
                    Already have an account?
                  </Link>
                </p>
              </motion.form>

              <motion.dl
                initial={reduce ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.6, ease: EASE, delay: 0.5 }}
                className="mt-12 flex flex-wrap items-end gap-x-8 gap-y-5"
              >
                {HERO_PROOF.map((stat, i) => (
                  <Fragment key={stat.label}>
                    {i > 0 && (
                      <span
                        aria-hidden="true"
                        className="hidden h-9 w-px self-center bg-dusk-line sm:block"
                      />
                    )}
                    <div>
                      <dt className="font-display text-xl font-semibold tracking-[-0.02em] text-paper md:text-[1.5rem]">
                        {stat.value}
                      </dt>
                      <dd className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-dusk-faint">
                        {stat.label}
                      </dd>
                    </div>
                  </Fragment>
                ))}
              </motion.dl>
            </div>

            <div className="gsap-parallax lg:justify-self-end">
              <DeterminationCard dusk />
            </div>
          </div>
        </div>
      </section>

      {/* ── How it reads the code — 3-step sequence ────────────── */}
      <section
        id="how"
        className="gsap-features border-t border-dusk-line"
      >
        <div className="mx-auto max-w-shell px-4 py-20 md:px-8 md:py-28">
          <Reveal>
            <h2 className="max-w-2xl font-display text-[clamp(1.9rem,4vw,2.9rem)] font-semibold leading-[1.05] tracking-display text-paper">
              From a parcel to a permit path in one pass.
            </h2>
            <p className="mt-5 max-w-xl text-[16px] font-normal leading-[1.8] text-dusk-soft">
              Every review runs the same disciplined pipeline. Nothing is
              synthesized. If the ordinance doesn&rsquo;t say it, neither do we.
            </p>
          </Reveal>

          {/* Desktop: horizontal 3-step sequence with connectors. */}
          <div className="mt-16 hidden items-start md:flex">
            {PIPELINE.map((stage, index) => (
              <Fragment key={stage.title}>
                <div className="gsap-feature flex-1">
                  <PipeStep index={index} stage={stage} />
                </div>
                {index < PIPELINE.length - 1 && (
                  <div
                    aria-hidden="true"
                    className="mt-2 h-px w-14 shrink-0 bg-gradient-to-r from-dusk-line via-spruce/[0.35] to-dusk-line lg:w-20"
                  />
                )}
              </Fragment>
            ))}
          </div>

          {/* Mobile: stacked with ghosted numbers. */}
          <div className="mt-12 space-y-10 md:hidden">
            {PIPELINE.map((stage, index) => (
              <div key={stage.title} className="gsap-feature">
                <p className="font-mono text-[11px] font-medium uppercase tracking-label text-spruce-bright">
                  {String(index + 1).padStart(2, "0")} · {stage.tag}
                </p>
                <h3 className="mt-1.5 font-display text-lg font-semibold tracking-display text-paper">
                  {stage.title}
                </h3>
                <p className="mt-1.5 text-sm font-normal leading-[1.7] text-dusk-soft">
                  {stage.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── The record — scale-up product preview ──────────────── */}
      <section id="preview" className="border-t border-dusk-line">
        <div className="mx-auto max-w-shell px-4 py-20 md:px-8 md:py-28">
          <Reveal className="mx-auto max-w-2xl text-center">
            <h2 className="font-display text-[clamp(1.9rem,4vw,2.9rem)] font-semibold leading-[1.05] tracking-display text-paper">
              A record you can hand to a planner.
            </h2>
            <p className="mx-auto mt-5 max-w-lg text-[16px] font-normal leading-[1.8] text-dusk-soft">
              Not a chat bubble. A structured determination: verdict,
              confidence, checklist, and the sections behind it.
            </p>
          </Reveal>

          <div className="gsap-dashboard mx-auto mt-14 max-w-3xl">
            <RecordPreview />
          </div>
        </div>
      </section>

      {/* ── Citations, not vibes ───────────────────────────────── */}
      <section className="border-t border-dusk-line">
        <div className="mx-auto grid max-w-shell items-center gap-12 px-4 py-20 md:px-8 md:py-28 lg:grid-cols-2 lg:gap-20">
          <Reveal>
            <h2 className="font-display text-[clamp(1.9rem,4vw,2.9rem)] font-semibold leading-[1.05] tracking-display text-paper">
              Every answer points to the section it came from.
            </h2>
            <p className="mt-5 max-w-md text-[16px] font-normal leading-[1.8] text-dusk-soft">
              A determination isn&rsquo;t worth much if you can&rsquo;t check it.
              Each result cites the ordinance sections behind it, so you, or
              your planner, can verify the reasoning in minutes.
            </p>
            <motion.ul
              variants={staggerParent}
              initial="hidden"
              whileInView="show"
              viewport={inViewOnce}
              className="mt-8 space-y-3.5"
            >
              {CITATION_POINTS.map((point) => (
                <motion.li
                  key={point}
                  variants={fadeUp}
                  className="flex gap-3 text-[15px] leading-6 text-paper"
                >
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-spruce-bright" />
                  {point}
                </motion.li>
              ))}
            </motion.ul>
          </Reveal>

          <Reveal delay={90}>
            <figure className="rounded-xl border border-dusk-line bg-dusk-panel/60 p-7 md:p-9">
              <figcaption className="font-mono text-[10px] uppercase tracking-label text-dusk-faint">
                Excerpt · Home occupations
              </figcaption>
              <blockquote className="mt-5 font-display text-xl font-semibold leading-8 tracking-[-0.01em] text-paper md:text-[1.6rem] md:leading-10">
                &ldquo;Home occupations are{" "}
                <mark className="rounded-[3px] bg-verdict-okwash px-1.5 text-verdict-ok">
                  permitted
                </mark>{" "}
                in residential districts subject to performance standards,
                including limits on non-resident employees and customer
                traffic.&rdquo;
              </blockquote>
              <figcaption className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px]">
                <span className="font-medium text-spruce-bright">§ 5-2(b)</span>
                <span className="text-dusk-faint">
                  Blacksburg Zoning Ordinance · retrieved 2026-07-01
                </span>
              </figcaption>
            </figure>
          </Reveal>
        </div>
      </section>

      {/* ── Coverage ───────────────────────────────────────────── */}
      <CoverageSection />

      {/* ── Disclaimer ─────────────────────────────────────────── */}
      <section id="disclaimer" className="border-t border-dusk-line">
        <div className="mx-auto max-w-shell px-4 py-20 md:px-8 md:py-28">
          <Reveal className="mx-auto max-w-2xl text-center">
            <h2 className="font-display text-[clamp(1.6rem,3.5vw,2.2rem)] font-semibold leading-[1.1] tracking-display text-paper">
              We tell you when we&rsquo;re not sure.
            </h2>
            <p className="mx-auto mt-5 max-w-xl text-[15px] font-normal leading-[1.8] text-dusk-soft">
              {DISCLAIMER}
            </p>
            <p className="mx-auto mt-4 max-w-xl text-[15px] font-normal leading-[1.8] text-dusk-soft">
              When source coverage is incomplete, the review says so and abstains
              rather than inventing an answer. Treat every result as a well-cited
              starting point to confirm with the planning department.
            </p>
          </Reveal>
        </div>
      </section>

      {/* ── CTA ────────────────────────────────────────────────── */}
      <section className="border-t border-dusk-line">
        <div className="mx-auto max-w-shell px-4 py-24 text-center md:px-8">
          <Reveal className="mx-auto max-w-2xl">
            <h2 className="font-display text-[clamp(2.1rem,5vw,3.4rem)] font-semibold leading-[1.02] tracking-display text-paper">
              Check a property in the next minute.
            </h2>
            <p className="mt-5 text-[16px] font-normal leading-[1.8] text-dusk-soft">
              Free while in beta. No card required.
            </p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <motion.div {...hoverLift}>
                <Link
                  to={isAuthenticated ? "/review" : "/signup?intent=review"}
                  className="btn-primary px-6 py-3 text-[15px]"
                >
                  {isAuthenticated ? "Go to review" : "Sign up"}
                </Link>
              </motion.div>
              <a href="#how" className={DUSK_OUTLINE}>
                See how it works
              </a>
            </div>
          </Reveal>
        </div>
      </section>
    </div>
  );
}

function PipeStep({
  index,
  stage,
}: {
  index: number;
  stage: (typeof PIPELINE)[number];
}) {
  return (
    <div>
      <p className="font-mono text-[11px] font-medium uppercase tracking-label text-spruce-bright">
        {String(index + 1).padStart(2, "0")} · {stage.tag}
      </p>
      <h3 className="mt-2 font-display text-xl font-semibold tracking-display text-paper">
        {stage.title}
      </h3>
      <p className="mt-2 max-w-[27ch] text-sm font-normal leading-[1.7] text-dusk-soft">
        {stage.body}
      </p>
    </div>
  );
}

/** A compact, real-looking determination record — the scale-up preview. Uses
 *  the product tokens so it doubles as an honest screenshot of the output. */
function RecordPreview() {
  return (
    <div className="overflow-hidden rounded-xl border border-dusk-line bg-dusk-panel shadow-float">
      <div className="flex items-center justify-between border-b border-dusk-line bg-dusk-raised/40 px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-verdict-ok" />
          <span className="font-mono text-[11px] uppercase tracking-label text-dusk-faint">
            Determination · ZR-2026-0413
          </span>
        </div>
        <span className="tag tag-ok">Permitted</span>
      </div>

      <div className="grid gap-6 p-6 md:grid-cols-[1.1fr_1fr] md:p-8">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-label text-dusk-faint">
            Property
          </p>
          <p className="mt-1.5 font-mono text-[13px] text-paper">
            412 Draper Rd SW, Blacksburg, VA
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <span className="inline-flex items-center rounded-md border border-dusk-line bg-dusk-raised/60 px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide text-dusk-soft">
              R-1 · Low density
            </span>
          </div>

          <p className="mt-6 font-mono text-[10px] uppercase tracking-label text-dusk-faint">
            Confidence
          </p>
          <div className="mt-2 flex items-center gap-3">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-dusk-raised">
              <div className="h-full w-[86%] rounded-full bg-verdict-ok" />
            </div>
            <span className="font-mono text-[12px] text-verdict-ok">High</span>
          </div>
        </div>

        <div>
          <p className="font-mono text-[10px] uppercase tracking-label text-dusk-faint">
            Permit checklist
          </p>
          <ul className="mt-2.5 space-y-2">
            {CHECKLIST.map((item) => (
              <li
                key={item}
                className="flex items-start gap-2.5 text-[13px] leading-5 text-dusk-soft"
              >
                <svg
                  viewBox="0 0 16 16"
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-verdict-ok"
                  aria-hidden="true"
                >
                  <path
                    d="M3.5 8.5l3 3 6-7"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="border-t border-dusk-line px-6 py-4 md:px-8">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px]">
          <span className="font-medium text-spruce-bright">§ 5-2(b)</span>
          <span className="text-dusk-faint">
            Home occupations: permitted subject to performance standards.
          </span>
        </div>
      </div>
    </div>
  );
}

const PIPELINE = [
  {
    tag: "Parcel",
    title: "Resolve the property",
    body: "Geocode the address, find the parcel, and read its zoning district from local GIS.",
  },
  {
    tag: "Ordinance",
    title: "Retrieve the code",
    body: "Pull the ordinance sections that govern the district and the use you described.",
  },
  {
    tag: "Determination",
    title: "Decide with citations",
    body: "Weigh the evidence into a determination, a confidence, and a permit checklist.",
  },
];

const CHECKLIST = [
  "Business license (Town of Blacksburg)",
  "Home occupation zoning permit",
  "≤ 1 non-resident employee",
  "No customer traffic increase",
];

const CITATION_POINTS = [
  "Section references you can look up, not paraphrased summaries.",
  "Retrieval date and source on every excerpt.",
  "No cited source means no confident answer, by design.",
];

function NameFlow({ names, tone }: { names: string[]; tone: string }) {
  return (
    <p className={`font-mono text-[13px] leading-8 ${tone}`}>
      {names.map((name, index) => (
        <Fragment key={name}>
          {index > 0 && <span className="px-2 text-dusk-line">·</span>}
          {name}
        </Fragment>
      ))}
    </p>
  );
}

function CoverageSection() {
  const { publicSupportedCoverage, indexedCoverage, coverageMessage } =
    useCoverage();
  const supported = publicSupportedCoverage.map((item) => item.name);
  const indexing = indexedCoverage.slice(0, 12).map((item) => item.name);

  return (
    <section id="coverage" className="border-t border-dusk-line">
      <div className="mx-auto max-w-shell px-4 py-20 md:px-8 md:py-28">
        <Reveal>
          <h2 className="max-w-2xl font-display text-[clamp(1.9rem,4vw,2.9rem)] font-semibold leading-[1.05] tracking-display text-paper">
            Honest about what we can and can&rsquo;t answer.
          </h2>
          <p className="mt-5 max-w-xl text-[16px] font-normal leading-[1.8] text-dusk-soft">
            Each jurisdiction is only marked supported once its ordinance is
            ingested and QA-checked. The rest are in progress, and you can
            request the ones you need.
          </p>
        </Reveal>

        <div className="mt-12 space-y-10">
          <Reveal>
            <p className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-label text-verdict-ok">
              <span className="h-1.5 w-1.5 rounded-full bg-verdict-ok" />
              Supported now
            </p>
            <div className="mt-3 max-w-3xl">
              {supported.length > 0 ? (
                <NameFlow names={supported} tone="text-paper" />
              ) : (
                <p className="text-sm text-dusk-soft">
                  {coverageMessage || "Loading coverage…"}
                </p>
              )}
            </div>
          </Reveal>

          <Reveal delay={80}>
            <p className="font-mono text-[11px] uppercase tracking-label text-dusk-faint">
              Being prepared
            </p>
            <div className="mt-3 max-w-3xl">
              <NameFlow names={indexing} tone="text-dusk-soft" />
            </div>
            <p className="mt-5 text-sm text-dusk-soft">
              Don&rsquo;t see your city?{" "}
              <Link
                to="/signup?intent=review"
                className="font-medium text-spruce-bright underline-offset-2 hover:underline"
              >
                Request coverage
              </Link>
              .
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
