import { motion } from "motion/react";

export function ReviewSignalsPanel({ prompts }: { prompts: string[] }) {
  return (
    <section className="sheet p-5">
      <h2 className="text-sm font-bold text-ink">Review signals</h2>
      <motion.div
        initial="hidden"
        animate="visible"
        variants={{ visible: { transition: { staggerChildren: 0.05 } } }}
        className="mt-3 space-y-2.5"
      >
        {prompts.length > 0 ? (
          prompts.map((prompt) => (
            <motion.div
              key={prompt}
              variants={{
                hidden: { opacity: 0, x: -6 },
                visible: { opacity: 1, x: 0 },
              }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="border-l-2 border-verdict-hold bg-verdict-holdwash/60 py-2 pl-3 pr-2"
            >
              <p className="text-[13px] leading-5 text-ink-soft">{prompt}</p>
            </motion.div>
          ))
        ) : (
          <p className="text-sm leading-6 text-ink-soft">
            Follow-up questions and confidence warnings will appear here when the review
            needs more detail.
          </p>
        )}
      </motion.div>
    </section>
  );
}
