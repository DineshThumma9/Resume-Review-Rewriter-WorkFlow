import { useEffect, useRef } from "react";
import { CheckCircle2, XCircle, Loader2, X, Sparkles } from "lucide-react";
import { useJobStore } from "../store/jobStore";
import { mutate } from "swr";

/**
 * GlobalJobToasts
 *
 * Renders a stack of floating toasts (bottom-right) for all active style-change
 * background jobs regardless of which page the user is on.
 * Must be mounted once, inside <AppLayout />, above the <Outlet />.
 */
export function GlobalJobToasts() {
  const { jobs, dismissJob } = useJobStore();

  // Revalidate the library ONLY when a job transitions into a terminal state.
  // Using a ref to track previously-seen statuses avoids firing on every render.
  const prevStatusRef = useRef<Record<number, string>>({});
  useEffect(() => {
    jobs.forEach((job) => {
      const prev = prevStatusRef.current[job.jobId];
      const isNowTerminal =
        job.status === "completed" || job.status === "failed";
      if (isNowTerminal && prev !== job.status) {
        mutate("resumes"); // force LibraryView to re-fetch so new preview_url appears
      }
      prevStatusRef.current[job.jobId] = job.status;
    });
  }, [jobs]);

  if (jobs.length === 0) return null;

  return (
    <div
      className="fixed bottom-5 right-5 z-[9999] flex flex-col gap-3 pointer-events-none"
      aria-live="polite"
    >
      {jobs.map((job) => {
        const isTerminal =
          job.status === "completed" || job.status === "failed";
        const isPending = job.status === "pending" || job.status === "running";

        return (
          <div
            key={job.jobId}
            className={`pointer-events-auto flex items-start gap-3 px-4 py-3 rounded-xl shadow-xl border max-w-sm w-full
              transition-all duration-300 animate-in slide-in-from-right-5 fade-in
              ${
                job.status === "completed"
                  ? "bg-green-950/90 border-green-700/60 text-green-100"
                  : job.status === "failed"
                    ? "bg-red-950/90 border-red-700/60 text-red-100"
                    : "bg-card border-border text-foreground"
              }`}
          >
            {/* Icon */}
            <div className="mt-0.5 shrink-0">
              {isPending && (
                <Loader2 className="w-5 h-5 animate-spin text-primary" />
              )}
              {job.status === "completed" && (
                <CheckCircle2 className="w-5 h-5 text-green-400" />
              )}
              {job.status === "failed" && (
                <XCircle className="w-5 h-5 text-red-400" />
              )}
            </div>

            {/* Body */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold leading-snug flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 opacity-70" />
                {job.status === "pending" && "Style change queued…"}
                {job.status === "running" && "Restyling resume…"}
                {job.status === "completed" && "Style applied!"}
                {job.status === "failed" && "Style change failed"}
              </p>
              <p className="text-xs mt-0.5 opacity-80 truncate">
                {job.resumeLabel}
                {job.style ? ` → ${job.style}` : ""}
              </p>
              {job.status === "completed" && job.pdfUrl && (
                <a
                  href={job.pdfUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block mt-1.5 text-xs font-medium text-green-300 hover:text-green-200 underline underline-offset-2"
                >
                  View updated PDF →
                </a>
              )}
              {job.status === "failed" && job.errorMessage && (
                <p className="text-xs mt-1 text-red-300 opacity-80 line-clamp-2">
                  {job.errorMessage}
                </p>
              )}
            </div>

            {/* Dismiss (only when terminal) */}
            {isTerminal && (
              <button
                onClick={() => dismissJob(job.jobId)}
                className="shrink-0 p-1 rounded hover:bg-white/10 transition-colors"
                aria-label="Dismiss"
              >
                <X className="w-4 h-4 opacity-70" />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
