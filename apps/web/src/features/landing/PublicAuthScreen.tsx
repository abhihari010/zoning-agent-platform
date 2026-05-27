import type { LegalPage } from "../../types/app";
import type { JurisdictionCoverage } from "../../api";
import { DISCLAIMER } from "../../constants/legal";
import { LegalLinks } from "../../components/LegalFooter";
import { LegalModal } from "../../components/LegalModal";
import { coverageLabel, coverageTone } from "../../utils/resultLabels";

export function PublicAuthScreen({
  coverage,
  publicSupportedCoverage,
  indexedCoverage,
  coverageMessage,
  authEmail,
  authPassword,
  authMessage,
  authLoading,
  legalPage,
  onAuthEmailChange,
  onAuthPasswordChange,
  onSignIn,
  onSignUp,
  onSelectLegalPage,
  onCloseLegalPage,
}: {
  coverage: JurisdictionCoverage[];
  publicSupportedCoverage: JurisdictionCoverage[];
  indexedCoverage: JurisdictionCoverage[];
  coverageMessage: string;
  authEmail: string;
  authPassword: string;
  authMessage: string;
  authLoading: boolean;
  legalPage: LegalPage;
  onAuthEmailChange: (value: string) => void;
  onAuthPasswordChange: (value: string) => void;
  onSignIn: () => void;
  onSignUp: () => void;
  onSelectLegalPage: (page: Exclude<LegalPage, null>) => void;
  onCloseLegalPage: () => void;
}) {
  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#f8f3ea_0%,#efe5d5_100%)] px-4 py-6 text-slate-900 md:px-8">
      <div className="mx-auto grid max-w-6xl gap-5 lg:grid-cols-[minmax(0,1.2fr)_420px]">
        <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
            Public Zoning Guidance
          </p>
          <h1 className="mt-3 font-heading text-4xl leading-tight text-pine md:text-5xl">
            Zoning Review Platform
          </h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-slate-700">
            Check whether a proposed project has source-backed zoning guidance, get a permit
            checklist, and request coverage when your jurisdiction is not ready yet.
          </p>
          <div className="mt-6 grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-950">
              <p className="text-xs font-semibold uppercase tracking-[0.16em]">Supported</p>
              <p className="mt-2 text-2xl font-semibold">{publicSupportedCoverage.length}</p>
              <p className="mt-1 text-xs leading-5">Public jurisdictions with QA-backed answers.</p>
            </div>
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-950">
              <p className="text-xs font-semibold uppercase tracking-[0.16em]">Indexed</p>
              <p className="mt-2 text-2xl font-semibold">{indexedCoverage.length}</p>
              <p className="mt-1 text-xs leading-5">Source packs being prepared for QA.</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-slate-700">
              <p className="text-xs font-semibold uppercase tracking-[0.16em]">US Coverage</p>
              <p className="mt-2 text-2xl font-semibold">Request-led</p>
              <p className="mt-1 text-xs leading-5">Unsupported places become backlog signals.</p>
            </div>
          </div>
          <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              Current Coverage
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {coverage.slice(0, 8).map((item) => (
                <span
                  key={item.jurisdictionId}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold ${coverageTone(item.coverageStatus)}`}
                >
                  {item.name}: {coverageLabel(item.coverageStatus)}
                </span>
              ))}
              {coverageMessage && (
                <span className="text-sm text-slate-600">{coverageMessage}</span>
              )}
            </div>
          </div>
          <p className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
            {DISCLAIMER}
          </p>
          <LegalLinks onSelectPage={onSelectLegalPage} />
        </section>

        <section className="rounded-[28px] border border-pine/10 bg-white p-6 shadow-card md:p-8">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
            Account Access
          </p>
          <h2 className="mt-3 font-heading text-3xl text-pine">Sign in to start</h2>
          <p className="mt-3 text-sm leading-6 text-slate-700">
            Save reviews, reopen prior projects, and request support for uncovered jurisdictions.
          </p>
          <label className="mt-6 block text-sm font-semibold text-slate-700">
            Email
            <input
              className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
              type="email"
              value={authEmail}
              onChange={(event) => onAuthEmailChange(event.target.value)}
            />
          </label>
          <label className="mt-4 block text-sm font-semibold text-slate-700">
            Password
            <input
              className="mt-2 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-clay focus:ring-2 focus:ring-clay"
              type="password"
              value={authPassword}
              onChange={(event) => onAuthPasswordChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  onSignIn();
                }
              }}
            />
          </label>
          {authMessage && (
            <p className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              {authMessage}
            </p>
          )}
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={onSignIn}
              disabled={authLoading}
              className="rounded-2xl bg-pine px-4 py-3 font-semibold text-white disabled:opacity-60"
            >
              {authLoading ? "Signing in..." : "Sign in"}
            </button>
            <button
              type="button"
              onClick={onSignUp}
              disabled={authLoading}
              className="rounded-2xl border border-slate-300 px-4 py-3 font-semibold text-slate-700 disabled:opacity-60"
            >
              Create account
            </button>
          </div>
        </section>
      </div>
      {legalPage && <LegalModal page={legalPage} onClose={onCloseLegalPage} />}
    </main>
  );
}
