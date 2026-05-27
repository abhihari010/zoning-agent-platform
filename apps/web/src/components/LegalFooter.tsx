import type { LegalPage } from "../types/app";

export function LegalFooter({ onSelectPage }: { onSelectPage: (page: Exclude<LegalPage, null>) => void }) {
  return (
    <footer className="mt-8 flex flex-wrap gap-4 border-t border-pine/10 pt-5 text-sm font-semibold text-slate-500">
      <button type="button" onClick={() => onSelectPage("terms")}>Terms</button>
      <button type="button" onClick={() => onSelectPage("privacy")}>Privacy</button>
      <button type="button" onClick={() => onSelectPage("disclaimer")}>Disclaimer</button>
    </footer>
  );
}

export function LegalLinks({ onSelectPage }: { onSelectPage: (page: Exclude<LegalPage, null>) => void }) {
  return (
    <div className="mt-5 flex flex-wrap gap-3 text-sm font-semibold text-slate-600">
      <button type="button" onClick={() => onSelectPage("terms")}>Terms</button>
      <button type="button" onClick={() => onSelectPage("privacy")}>Privacy</button>
      <button type="button" onClick={() => onSelectPage("disclaimer")}>Disclaimer</button>
    </div>
  );
}
