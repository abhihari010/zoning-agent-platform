import { Link } from "react-router-dom";
import { BenchmarkMark } from "../components/WorkspaceHeader";

export function NotFound() {
  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center px-4 text-center">
      <BenchmarkMark className="h-10 w-10" />
      <p className="mt-6 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint">
        Record not found
      </p>
      <h1 className="mt-3 text-3xl font-bold tracking-[-0.02em] text-ink">
        This page isn’t on file.
      </h1>
      <p className="mt-3 max-w-sm text-sm leading-6 text-ink-soft">
        The address you followed doesn’t match a page. Head back and start a new
        review.
      </p>
      <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
        <Link to="/" className="btn-outline px-4 py-2.5 text-sm">
          Back to home
        </Link>
        <Link to="/review" className="btn-primary px-4 py-2.5 text-sm">
          Start a review
        </Link>
      </div>
    </div>
  );
}
