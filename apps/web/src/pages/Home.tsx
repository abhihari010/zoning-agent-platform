import {
  Fragment,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { useAuth } from "../auth/AuthContext";
import { useCoverage } from "../hooks/useCoverage";
import { DISCLAIMER } from "../constants/legal";
import { DeterminationCard } from "../features/landing/DeterminationCard";
import { Reveal } from "../features/landing/Reveal";

const EASE_OUT_EXPO = [0.16, 1, 0.3, 1] as const;

const DUSK_FIELD =
  "mt-0 flex-1 rounded-sm border border-dusk-line bg-dusk-panel px-3.5 py-2.5 font-mono text-[13px] text-paper placeholder:text-dusk-faint transition-[border-color,box-shadow] duration-fast ease-out focus:border-amber focus:outline-none focus:shadow-[0_0_0_2px_rgba(231,162,78,0.3)]";

const DUSK_OUTLINE =
  "inline-flex items-center justify-center gap-2 rounded-sm border border-dusk-line bg-transparent font-semibold text-paper transition-[transform,border-color,background-color] duration-fast ease-out hover:-translate-y-px hover:border-dusk-soft hover:bg-dusk-raised active:scale-[0.98]";

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-amber">
      {children}
    </span>
  );
}

/** One-shot IntersectionObserver — toggles a class when the node enters view. */
function useInViewOnce<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node || shown) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setShown(true);
            observer.disconnect();
          }
        }
      },
      { threshold: 0.6, rootMargin: "0px 0px -10% 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [shown]);
  return [ref, shown] as const;
}

/** The hairline that draws between pipeline steps (one pass through the code). */
function PipeLine({ delay = 0 }: { delay?: number }) {
  const [ref, shown] = useInViewOnce<HTMLSpanElement>();
  return (
    <span
      ref={ref}
      aria-hidden="true"
      className={`pipe-line block h-px w-full bg-gradient-to-r from-dusk-line via-amber/50 to-dusk-line ${shown ? "is-visible" : ""}`}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
    />
  );
}

export function Home() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const reduce = useReducedMotion();
  const [heroAddress, setHeroAddress] = useState("");

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

  // Headline lands one line at a time — a clip reveal, not letter-by-letter.
  const headline = ["Know what you can build", "— before you file."];

  return (
    <>
      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="mx-auto max-w-shell px-4 pb-16 pt-14 md:px-8 md:pb-28 md:pt-20">
        <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,480px)] lg:gap-16">
          <div>
            <div className="enter">
              <Eyebrow>Ordinance-backed feasibility</Eyebrow>
            </div>
            <h1 className="mt-4 max-w-xl font-display text-[2.5rem] font-extrabold leading-[1.04] tracking-[-0.03em] text-paper md:text-[3.4rem]">
              {headline.map((line, i) => (
                <span key={line} className="block overflow-hidden pb-[0.06em]">
                  <motion.span
                    className="block"
                    initial={reduce ? false : { y: "110%" }}
                    animate={{ y: "0%" }}
                    transition={{
                      duration: 0.7,
                      ease: EASE_OUT_EXPO,
                      delay: 0.12 + i * 0.11,
                    }}
                  >
                    {line}
                  </motion.span>
                </span>
              ))}
            </h1>
            <p className="enter enter-1 mt-5 max-w-md text-[17px] leading-7 text-dusk-soft">
              Type an address and what you want to build. Get a determination with
              the exact ordinance sections it’s based on — not a guess.
            </p>

            <form onSubmit={startReview} className="enter enter-2 mt-8 max-w-md">
              <div className="flex flex-col gap-2.5 sm:flex-row">
                <input
                  aria-label="Property address"
                  value={heroAddress}
                  onChange={(event) => setHeroAddress(event.target.value)}
                  placeholder="412 Draper Rd SW, Blacksburg, VA"
                  className={DUSK_FIELD}
                />
                <button type="submit" className="btn-primary shrink-0 px-5 py-2.5">
                  Check a property
                </button>
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
            </form>
          </div>

          <div className="enter enter-2 lg:justify-self-end">
            <DeterminationCard dusk />
          </div>
        </div>
      </section>

      {/* ── §1 How it reads the code — open sequence, no cards ── */}
      <section id="how" className="border-t border-dusk-line/60">
        <div className="mx-auto max-w-shell px-4 py-16 md:px-8 md:py-24">
          <Reveal>
            <Eyebrow>How it reads the code</Eyebrow>
            <h2 className="mt-3 max-w-2xl font-display text-3xl font-bold tracking-[-0.02em] text-paper md:text-[2.3rem]">
              From a parcel to a permit path in one pass.
            </h2>
            <p className="mt-4 max-w-xl text-[15px] leading-7 text-dusk-soft">
              Every review runs the same disciplined pipeline. Nothing is
              synthesized — if the ordinance doesn’t say it, neither do we.
            </p>
          </Reveal>

          {/* Desktop: horizontal sequence with a line that draws left→right. */}
          <div className="mt-16 hidden items-start md:flex">
            {PIPELINE.map((stage, index) => (
              <Fragment key={stage.title}>
                <Reveal delay={index * 110} className="flex-1">
                  <PipeStep index={index} stage={stage} />
                </Reveal>
                {index < PIPELINE.length - 1 && (
                  <div className="w-14 shrink-0 pt-9 lg:w-20">
                    <PipeLine delay={index * 350} />
                  </div>
                )}
              </Fragment>
            ))}
          </div>

          {/* Mobile: stacked, ghosted numbers running down the left. */}
          <div className="mt-12 space-y-10 md:hidden">
            {PIPELINE.map((stage, index) => (
              <Reveal key={stage.title} delay={index * 80} className="flex gap-4">
                <span className="font-mono text-3xl font-semibold leading-none text-dusk-line">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-amber">
                    {stage.tag}
                  </p>
                  <h3 className="mt-1.5 font-display text-lg font-bold tracking-[-0.01em] text-paper">
                    {stage.title}
                  </h3>
                  <p className="mt-1.5 text-sm leading-6 text-dusk-soft">
                    {stage.body}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── §2 Citations, not vibes — open pull-quote, no card ── */}
      <section className="border-t border-dusk-line/60">
        <div className="mx-auto grid max-w-shell items-center gap-12 px-4 py-16 md:px-8 md:py-24 lg:grid-cols-2 lg:gap-20">
          <Reveal>
            <Eyebrow>Citations, not vibes</Eyebrow>
            <h2 className="mt-3 font-display text-3xl font-bold tracking-[-0.02em] text-paper md:text-[2.3rem]">
              Every answer points to the section it came from.
            </h2>
            <p className="mt-4 max-w-md text-[15px] leading-7 text-dusk-soft">
              A determination isn’t worth much if you can’t check it. Each result
              cites the ordinance sections behind it, so you — or your planner —
              can verify the reasoning in minutes.
            </p>
            <ul className="mt-6 space-y-3">
              {CITATION_POINTS.map((point) => (
                <li
                  key={point}
                  className="flex gap-3 text-sm leading-6 text-paper"
                >
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber" />
                  {point}
                </li>
              ))}
            </ul>
          </Reveal>

          <Reveal delay={90}>
            <figure className="border-l border-amber/30 pl-6 md:pl-8">
              <figcaption className="font-mono text-[10px] uppercase tracking-[0.18em] text-dusk-faint">
                Excerpt · Home occupations
              </figcaption>
              <blockquote className="mt-4 font-display text-xl font-semibold leading-8 tracking-[-0.01em] text-paper md:text-[1.6rem] md:leading-10">
                “Home occupations are{" "}
                <mark className="rounded-[2px] bg-[#2E8B76]/25 px-1 text-[#9FE3CD]">
                  permitted
                </mark>{" "}
                in residential districts subject to performance standards,
                including limits on non-resident employees and customer traffic.”
              </blockquote>
              <figcaption className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px]">
                <span className="font-medium text-amber">§ 5-2(b)</span>
                <span className="text-dusk-faint">
                  Blacksburg Zoning Ordinance · retrieved 2026-07-01
                </span>
              </figcaption>
            </figure>
          </Reveal>
        </div>
      </section>

      {/* ── Testimonial — large pull-quote on a deeper band ────── */}
      <section className="border-t border-dusk-line/60 bg-dusk-deep">
        <div className="mx-auto max-w-shell px-4 py-20 md:px-8 md:py-24">
          <Reveal className="mx-auto max-w-3xl">
            <p className="font-display text-[1.7rem] font-semibold leading-[1.42] tracking-[-0.015em] text-paper md:text-[2.35rem] md:leading-[1.35]">
              <span className="text-amber">“</span>I used to spend an afternoon
              reading code and calling the county before telling a client whether
              their idea was even legal. Now I get the sections in front of me in a
              minute.<span className="text-amber">”</span>
            </p>
            <div className="mt-8 flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-sm bg-amber font-display text-sm font-bold text-dusk-deep">
                DM
              </span>
              <div>
                <p className="text-sm font-semibold text-paper">Dana Merritt</p>
                <p className="text-xs text-dusk-faint">
                  Land-use consultant · Roanoke, VA
                </p>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── §3 Coverage — a flowing list, not a grid of boxes ─── */}
      <CoverageSection />

      {/* ── §4 The honest disclaimer, up front ───────────────── */}
      <section id="disclaimer" className="border-t border-dusk-line/60">
        <div className="mx-auto max-w-shell px-4 py-16 md:px-8 md:py-24">
          <Reveal className="max-w-2xl border-l-2 border-amber/50 pl-6 md:pl-8">
            <Eyebrow>Read this first</Eyebrow>
            <h2 className="mt-3 font-display text-2xl font-bold tracking-[-0.02em] text-paper md:text-[1.8rem]">
              We tell you when we’re not sure.
            </h2>
            <p className="mt-4 text-[15px] leading-7 text-dusk-soft">
              {DISCLAIMER}
            </p>
            <p className="mt-4 text-[15px] leading-7 text-dusk-soft">
              When source coverage is incomplete, the review says so and abstains
              rather than inventing an answer. Treat every result as a well-cited
              starting point to confirm with the planning department.
            </p>
          </Reveal>
        </div>
      </section>

      {/* ── CTA band ─────────────────────────────────────────── */}
      <section className="border-t border-dusk-line/60">
        <div className="mx-auto max-w-shell px-4 py-24 text-center md:px-8">
          <Reveal className="mx-auto max-w-2xl">
            <h2 className="font-display text-3xl font-extrabold tracking-[-0.02em] text-paper md:text-[2.6rem]">
              Check a property in the next minute.
            </h2>
            <p className="mt-4 text-[15px] leading-7 text-dusk-soft">
              Free while in beta. No card required.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Link
                to={isAuthenticated ? "/review" : "/signup?intent=review"}
                className="btn-primary px-6 py-3 text-[15px]"
              >
                {isAuthenticated ? "Go to review" : "Sign up"}
              </Link>
              <a href="#how" className={`${DUSK_OUTLINE} px-6 py-3 text-[15px]`}>
                See how it works
              </a>
            </div>
          </Reveal>
        </div>
      </section>
    </>
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
      <span className="font-mono text-[3.5rem] font-semibold leading-none text-dusk-line">
        {String(index + 1).padStart(2, "0")}
      </span>
      <p className="mt-5 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-amber">
        {stage.tag}
      </p>
      <h3 className="mt-2 font-display text-xl font-bold tracking-[-0.01em] text-paper">
        {stage.title}
      </h3>
      <p className="mt-2 max-w-[26ch] text-sm leading-6 text-dusk-soft">
        {stage.body}
      </p>
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

const CITATION_POINTS = [
  "Section references you can look up, not paraphrased summaries.",
  "Retrieval date and source on every excerpt.",
  "No cited source means no confident answer — by design.",
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
    <section id="coverage" className="border-t border-dusk-line/60">
      <div className="mx-auto max-w-shell px-4 py-16 md:px-8 md:py-24">
        <Reveal>
          <Eyebrow>Coverage you can see</Eyebrow>
          <h2 className="mt-3 max-w-2xl font-display text-3xl font-bold tracking-[-0.02em] text-paper md:text-[2.3rem]">
            Honest about where we can — and can’t — answer.
          </h2>
          <p className="mt-4 max-w-xl text-[15px] leading-7 text-dusk-soft">
            Each jurisdiction is only marked supported once its ordinance is
            ingested and QA-checked. The rest are in progress, and you can request
            the ones you need.
          </p>
        </Reveal>

        <div className="mt-12 space-y-10">
          <Reveal>
            <p className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.14em] text-[#7FD3BB]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#2E8B76]" />
              Supported now
            </p>
            <div className="mt-3 max-w-3xl">
              {supported.length > 0 ? (
                <NameFlow names={supported} tone="text-[#9FE3CD]" />
              ) : (
                <p className="text-sm text-dusk-soft">
                  {coverageMessage || "Loading coverage…"}
                </p>
              )}
            </div>
          </Reveal>

          <Reveal delay={80}>
            <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-dusk-faint">
              Being prepared
            </p>
            <div className="mt-3 max-w-3xl">
              <NameFlow names={indexing} tone="text-dusk-soft" />
            </div>
            <p className="mt-5 text-sm text-dusk-soft">
              Don’t see your city?{" "}
              <Link
                to="/signup?intent=review"
                className="font-medium text-amber underline-offset-2 hover:underline"
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
