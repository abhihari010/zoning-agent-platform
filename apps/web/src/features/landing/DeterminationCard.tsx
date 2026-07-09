import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

const EASE_OUT_EXPO = [0.16, 1, 0.3, 1] as const;
const ADDRESS = "412 Draper Rd SW, Blacksburg, VA";
const PROJECT = "Bakery in an attached garage, 2 employees";

const CITATIONS = [
  {
    ref: "§ 5-2(b)",
    title: "Home occupations",
    body: "Permitted in residential districts subject to performance standards.",
  },
  {
    ref: "§ 5-3(a)",
    title: "Accessory uses",
    body: "Attached garages may house a permitted home occupation.",
  },
];

/**
 * The hero's live determination — a case-file document that plays a real
 * scenario on load: the address types in, the project line appears, a progress
 * sheen sweeps, the stamp lands (the v2 signature animation), and two ordinance
 * citations fade in. Plays once. Reduced motion shows the finished state.
 *
 * `dusk` swaps to the dark marketing palette (brief §2.5 Option B).
 */
export function DeterminationCard({ dusk = false }: { dusk?: boolean }) {
  const reduce = useReducedMotion();
  // step: 0 idle · 1 address · 2 project · 3 reviewing · 4 stamped · 5 citations
  const [step, setStep] = useState(reduce ? 5 : 0);
  const [typed, setTyped] = useState(reduce ? ADDRESS : "");
  const [impact, setImpact] = useState(false);
  const cardRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (reduce) {
      setStep(5);
      setTyped(ADDRESS);
      return;
    }
    const timers: number[] = [];
    timers.push(window.setTimeout(() => setStep(1), 450));
    timers.push(window.setTimeout(() => setStep(2), 1650));
    timers.push(window.setTimeout(() => setStep(3), 2250));
    timers.push(window.setTimeout(() => setStep(4), 3850));
    timers.push(window.setTimeout(() => setStep(5), 4250));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [reduce]);

  // Typewriter for the address once step 1 begins.
  useEffect(() => {
    if (reduce || step < 1) {
      return;
    }
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setTyped(ADDRESS.slice(0, i));
      if (i >= ADDRESS.length) {
        window.clearInterval(id);
      }
    }, 34);
    return () => window.clearInterval(id);
  }, [step, reduce]);

  const reviewing = step === 3;
  const stamped = step >= 4;

  // Theme class map — keeps the JSX readable across light/dusk.
  const t = dusk
    ? {
        shell: "border-dusk-line bg-dusk-panel dusk-halo",
        header: "border-dusk-line bg-dusk-raised/50",
        label: "text-dusk-faint",
        value: "text-paper",
        caret: "bg-paper",
        project: "text-paper/90",
        rule: "border-dusk-line",
        chip: "border-dusk-line bg-dusk-raised/60 text-dusk-soft",
        stamp: "stamp-glow border-[#2E8B76] text-[#5FC7A9] tracking-[0.22em]",
        row: "border-dusk-line bg-dusk-raised/40",
        rowRef: "text-amber",
        rowTitle: "text-paper",
        rowBody: "text-dusk-soft",
      }
    : {
        shell: "border-rule-strong bg-sheet shadow-float",
        header: "border-rule bg-well/70",
        label: "text-ink-faint",
        value: "text-ink",
        caret: "bg-ink",
        project: "text-ink",
        rule: "border-rule",
        chip: "tag tag-neutral",
        stamp: "border-spruce text-spruce",
        row: "border-rule bg-well/50",
        rowRef: "text-spruce",
        rowTitle: "text-ink",
        rowBody: "text-ink-soft",
      };

  return (
    <motion.div
      ref={cardRef}
      animate={impact ? { y: [0, 1, 0] } : undefined}
      transition={{ duration: 0.12 }}
      className={`relative w-full overflow-hidden rounded-sm border ${t.shell}`}
    >
      {reviewing && <span className="review-line" aria-hidden="true" />}

      {/* File header */}
      <div className={`flex items-center justify-between border-b px-5 py-2.5 ${t.header}`}>
        <span className={`font-mono text-[10px] uppercase tracking-[0.16em] ${t.label}`}>
          Determination
        </span>
        <span className={`font-mono text-[10px] uppercase tracking-[0.16em] ${t.label}`}>
          ZR-2026-0413
        </span>
      </div>

      <div className="p-5 md:p-6">
        {/* Parcel */}
        <p className={`font-mono text-[10px] uppercase tracking-[0.14em] ${t.label}`}>
          Parcel
        </p>
        <p className={`mt-1 min-h-[1.5rem] font-mono text-[13px] ${t.value}`}>
          {typed}
          {!reduce && step >= 1 && typed.length < ADDRESS.length && (
            <span className={`ml-0.5 inline-block h-3.5 w-px animate-pulse align-middle ${t.caret}`} />
          )}
        </p>

        {/* Project */}
        <div className="mt-4 min-h-[2.75rem]">
          <AnimatePresence>
            {step >= 2 && (
              <motion.div
                initial={reduce ? false : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: EASE_OUT_EXPO }}
              >
                <p className={`font-mono text-[10px] uppercase tracking-[0.14em] ${t.label}`}>
                  Project
                </p>
                <p className={`mt-1 text-sm leading-6 ${t.project}`}>{PROJECT}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* District + stamp */}
        <div className={`mt-4 flex items-end justify-between gap-4 border-t pt-5 ${t.rule}`}>
          <div>
            <p className={`font-mono text-[10px] uppercase tracking-[0.14em] ${t.label}`}>
              District
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <span
                className={
                  dusk
                    ? `inline-flex items-center rounded-sm border px-2 py-0.5 font-mono text-[11px] font-medium uppercase tracking-wide ${t.chip}`
                    : t.chip
                }
              >
                R-1 · Low density
              </span>
              <span
                className={
                  dusk
                    ? `inline-flex items-center rounded-sm border px-2 py-0.5 font-mono text-[11px] font-medium uppercase tracking-wide ${t.chip}`
                    : t.chip
                }
              >
                Blacksburg, VA
              </span>
            </div>
          </div>

          <div className="min-h-[3.25rem] shrink-0">
            <AnimatePresence>
              {stamped && (
                <motion.div
                  initial={reduce ? false : { scale: 1.2, rotate: -6, opacity: 0 }}
                  animate={{ scale: 1, rotate: -2, opacity: 1 }}
                  transition={{ duration: 0.4, ease: EASE_OUT_EXPO }}
                  onAnimationComplete={() => {
                    if (!reduce) {
                      setImpact(true);
                      window.setTimeout(() => setImpact(false), 160);
                    }
                  }}
                  className={`stamp px-5 py-2.5 text-[13px] ${t.stamp}`}
                >
                  Permitted
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Citations */}
        <div className="mt-5 min-h-[4.5rem] space-y-2">
          <AnimatePresence>
            {step >= 5 &&
              CITATIONS.map((citation, index) => (
                <motion.div
                  key={citation.ref}
                  initial={reduce ? false : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{
                    duration: 0.35,
                    delay: reduce ? 0 : index * 0.12,
                    ease: EASE_OUT_EXPO,
                  }}
                  className={`flex gap-3 rounded-sm border px-3 py-2 ${t.row}`}
                >
                  <span className={`mt-0.5 shrink-0 font-mono text-[11px] font-medium ${t.rowRef}`}>
                    {citation.ref}
                  </span>
                  <span className={`text-[12px] leading-5 ${t.rowBody}`}>
                    <span className={`font-medium ${t.rowTitle}`}>{citation.title}. </span>
                    {citation.body}
                  </span>
                </motion.div>
              ))}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}
