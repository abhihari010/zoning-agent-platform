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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4 backdrop-blur-sm">
      <section className="sheet rise max-h-[90dvh] w-full max-w-2xl overflow-auto shadow-raised">
        <div className="border-b border-rule bg-well/70 px-6 py-2.5 md:px-8">
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
            {isMandatory ? "Required acknowledgment" : "Public disclosure"}
          </p>
        </div>
        <div className="p-6 md:p-8">
          <h2 className="text-2xl font-bold tracking-tight text-ink">{legal.title}</h2>
          <div className="mt-4 space-y-4 text-sm leading-7 text-ink-soft">
            {legal.paragraphs.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </div>
          <div className="mt-6 flex flex-wrap gap-2.5">
            {isMandatory ? (
              <>
                <button
                  type="button"
                  onClick={() => {
                    onAcknowledge();
                    onClose();
                  }}
                  className="btn-primary"
                >
                  I understand, continue
                </button>
                <button type="button" onClick={onClose} className="btn-outline">
                  Cancel
                </button>
              </>
            ) : (
              <button type="button" onClick={onClose} className="btn-primary">
                Close
              </button>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
