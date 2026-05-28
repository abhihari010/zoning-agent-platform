import type { LegalPage } from "../types/app";
import { legalCopy } from "../constants/legal";

export function LegalModal({
  page,
  onClose,
  onAcknowledge,
}: {
  page: Exclude<LegalPage, null>;
  onClose: () => void;
  onAcknowledge?: () => void;
}) {
  const legal = legalCopy(page);
  const isMandatory = !!onAcknowledge;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
      <section className="w-full max-w-2xl rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
          {isMandatory ? "Required Acknowledgment" : "Public Disclosure"}
        </p>
        <h2 className="mt-2 font-heading text-3xl text-pine">{legal.title}</h2>
        <div className="mt-5 space-y-4 text-sm leading-7 text-slate-700">
          {legal.paragraphs.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>
        <div className="mt-6 flex gap-3">
          {isMandatory ? (
            <>
              <button
                type="button"
                onClick={() => {
                  onAcknowledge();
                  onClose();
                }}
                className="rounded-2xl bg-pine px-4 py-3 font-semibold text-white"
              >
                I understand — continue
              </button>
              <button
                type="button"
                onClick={onClose}
                className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-600"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="rounded-2xl bg-pine px-4 py-3 font-semibold text-white"
            >
              Close
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
