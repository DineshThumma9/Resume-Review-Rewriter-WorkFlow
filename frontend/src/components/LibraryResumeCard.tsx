import { useState, useEffect, useRef } from "react";
import {
  FileText,
  Calendar,
  Trash2,
  Edit2,
  Sparkles,
  Loader2,
  Copy,
  Eye,
} from "lucide-react";
import type { Resume } from "../schemas";
import { useNavigate } from "react-router-dom";
import { useResumeStore } from "../store/resumeStore";
import { resumeApi } from "../apis/resumes";
import { templateApi } from "../apis/templates";
import { startStyleChange } from "../apis/styleJob";
import { useJobStore } from "../store/jobStore";
import useSWR from "swr";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "./ui/dialog";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger } from "./ui/select";

// ── Skeleton shimmer overlay for the thumbnail ───────────────────────────────
function SkeletonOverlay({ label }: { label: string }) {
  return (
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-background/80 backdrop-blur-sm rounded-lg">
      {/* Animated gradient shimmer */}
      <div className="absolute inset-0 rounded-lg overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-primary/10 to-transparent animate-[shimmer_1.6s_infinite]" />
        {/* Fake line skeletons */}
        <div className="p-5 flex flex-col gap-2 mt-6">
          {[80, 60, 70, 55, 65, 50, 60].map((w, i) => (
            <div
              key={i}
              className="h-2 rounded-full bg-muted-foreground/20"
              style={{ width: `${w}%` }}
            />
          ))}
        </div>
      </div>
      {/* Spinner + label */}
      <div className="relative z-10 flex flex-col items-center gap-2">
        <div className="w-10 h-10 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center">
          <Loader2 className="w-5 h-5 text-primary animate-spin" />
        </div>
        <p className="text-xs font-medium text-foreground/80 text-center px-2">
          Restyling with{" "}
          <span className="text-primary font-semibold">{label}</span>…
        </p>
        <p className="text-[10px] text-muted-foreground text-center">
          You can navigate away — we'll notify you when it's ready
        </p>
      </div>
    </div>
  );
}

export function LibraryResumeCard({
  resume,
  onDelete,
  onRename,
}: {
  resume: Resume;
  onDelete: (id: number) => void;
  onRename: (id: number, label: string) => void;
}) {
  const navigate = useNavigate();
  const setResumeState = useResumeStore((s) => s.setResumeState);
  const { addJob, connectSSE, jobs } = useJobStore();

  const [isRenameOpen, setIsRenameOpen] = useState(false);
  const [newLabel, setNewLabel] = useState(resume.label);
  const [isStyleDialogOpen, setIsStyleDialogOpen] = useState(false);
  const [, setSelectedTemplateId] = useState<string | null>(null);
  const [selectedTemplateName, setSelectedTemplateName] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const sseCleanupRef = useRef<(() => void) | null>(null);

  const { data: templates } = useSWR("templates", templateApi.list);

  // Is there an active (pending/running) job for THIS resume?
  const activeJob = jobs.find(
    (j) =>
      j.resumeId === resume.id &&
      (j.status === "pending" || j.status === "running"),
  );
  const isProcessing = !!activeJob;

  // If this card mounts and there's already a job for this resume in the store,
  // make sure SSE is still connected (handles page refresh edge case via store rehydration)
  useEffect(() => {
    return () => {
      sseCleanupRef.current?.();
    };
  }, []);

  const handleRenameSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (newLabel && newLabel.trim() && newLabel.trim() !== resume.label) {
      onRename(resume.id, newLabel.trim());
    }
    setIsRenameOpen(false);
  };

  const handleViewPdf = (e: React.MouseEvent) => {
    e.preventDefault();
    if (!resume.pdf_url) return;
    if (resume.pdf_url.startsWith("data:application/pdf;base64,")) {
      try {
        const b64 = resume.pdf_url.split(",")[1];
        const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
        const url = URL.createObjectURL(
          new Blob([bytes], { type: "application/pdf" }),
        );
        window.open(url, "_blank");
      } catch {
        window.open(resume.pdf_url, "_blank");
      }
    } else {
      window.open(resume.pdf_url, "_blank");
    }
  };

  // mode: "inplace" updates this resume directly; "copy" creates a duplicate first
  const handleStyleConfirm = async (mode: "inplace" | "copy") => {
    if (!selectedTemplateName) return;
    setIsSubmitting(true);
    setStartError(null);

    try {
      let targetResumeId = resume.id;
      let targetLabel = resume.label;

      if (mode === "copy") {
        // Create a duplicate resume first, then style the copy
        const copy = await resumeApi.create(
          resume.label + " (Copy)",
          resume.tex_source || "",
          resume.content,
          resume.pdf_url ?? undefined,
        );
        targetResumeId = copy.id;
        targetLabel = copy.label;
      }

      const job = await startStyleChange(targetResumeId, selectedTemplateName);

      // Register in global store immediately (optimistic)
      addJob({
        jobId: job.job_id,
        resumeId: targetResumeId,
        resumeLabel: targetLabel,
        style: selectedTemplateName,
        status: job.status ?? "pending",
      });

      // Open SSE stream and wire updates into store
      const cleanup = connectSSE(job.job_id);
      sseCleanupRef.current = cleanup;

      setIsStyleDialogOpen(false);
    } catch (err) {
      setStartError(
        err instanceof Error ? err.message : "Failed to start style change",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 p-5 rounded-2xl border border-border bg-card shadow-sm hover:shadow-md transition-shadow relative group">
      {/* ── Thumbnail ── */}
      <div
        className="w-full rounded-lg bg-muted overflow-hidden border border-border relative"
        style={{ aspectRatio: "1 / 1.414" }}
      >
        {/* Skeleton overlay when job is active */}
        {isProcessing && <SkeletonOverlay label={activeJob!.style} />}

        {resume.preview_url ? (
          <img
            src={resume.preview_url}
            alt={resume.label}
            className={`w-full h-full object-contain transition-all duration-500 group-hover:scale-[1.02] ${isProcessing ? "opacity-30 blur-sm" : ""}`}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-muted-foreground opacity-30">
            <FileText size={48} strokeWidth={1} />
          </div>
        )}
      </div>

      {/* ── Title row ── */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="min-w-0 flex-1">
            <h3
              className="font-semibold text-foreground truncate max-w-[200px]"
              title={resume.label}
            >
              {resume.label}
            </h3>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-0.5">
              <Calendar size={12} />
              <span>
                {new Date(
                  resume.updated_at || resume.created_at,
                ).toLocaleDateString()}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all ml-2 shrink-0">
          <button
            onClick={() => {
              setNewLabel(resume.label);
              setIsRenameOpen(true);
            }}
            className="p-2 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-lg transition-all"
            title="Rename Resume"
          >
            <Edit2 size={16} />
          </button>
          <button
            onClick={() => onDelete(resume.id)}
            className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-all"
            title="Delete Resume"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      {/* ── Action buttons ── */}
      <div className="grid grid-cols-3 gap-1.5 sm:gap-2 mt-3 w-full">
        {resume.pdf_url ? (
          <button
            onClick={handleViewPdf}
            className="w-full inline-flex items-center justify-center gap-1.5 px-2 py-2 text-xs font-semibold rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors h-9 min-w-0"
            title="View Compiled PDF"
          >
            <Eye size={14} className="shrink-0" />
            <span className="hidden md:inline truncate">View PDF</span>
          </button>
        ) : (
          <div
            className="w-full h-9 bg-muted/30 rounded-lg flex items-center justify-center text-[10px] text-muted-foreground/60 font-medium border border-dashed border-border/50"
            title="No compiled PDF available"
          >
            <Eye size={14} className="opacity-40" />
          </div>
        )}

        <button
          onClick={() => {
            setResumeState({
              resumeId: resume.id,
              latexCode: resume.tex_source || "",
              pdfUrl: resume.pdf_url || null,
              templateId: resume.template_id ? String(resume.template_id) : "",
              label: resume.label,
            });
            navigate("/analyze", { state: { tab: "editor" } });
          }}
          className="w-full inline-flex items-center justify-center gap-1.5 px-2 py-2 text-xs font-semibold rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-colors h-9 min-w-0"
          title="Edit TeX & Resume Content"
        >
          <FileText size={14} className="shrink-0" />
          <span className="hidden md:inline truncate">Edit</span>
        </button>

        {/* ── Change Style button ── */}
        <Select
          onValueChange={(val) => {
            const tpl = templates?.find((t) => String(t.id) === val);
            setSelectedTemplateId(val);
            setSelectedTemplateName(tpl?.name ?? val);
            setStartError(null);
            setIsStyleDialogOpen(true);
          }}
          disabled={isProcessing || !templates || !resume.tex_source}
          value=""
        >
          <SelectTrigger
            className={`w-full inline-flex items-center justify-center gap-1.5 px-2 py-2 text-xs font-semibold rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-colors disabled:opacity-50 h-9 min-w-0 overflow-hidden ${isProcessing ? "cursor-not-allowed" : ""}`}
            title={
              !resume.tex_source
                ? "Style conversion requires a LaTeX-generated resume"
                : isProcessing
                  ? "A style change is already in progress…"
                  : "Change Style"
            }
          >
            {isProcessing ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                <span className="hidden md:inline truncate">Styling…</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5 shrink-0 text-amber-500" />
                <span className="hidden md:inline truncate">Style</span>
              </>
            )}
          </SelectTrigger>
          <SelectContent>
            {templates?.map((t) => (
              <SelectItem key={t.id} value={String(t.id)}>
                {t.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* ── Change Style Confirmation Dialog ── */}
      <Dialog open={isStyleDialogOpen} onOpenChange={setIsStyleDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-primary" />
              Change Resume Style
            </DialogTitle>
            <DialogDescription>
              Apply{" "}
              <span className="font-semibold text-foreground">
                "{selectedTemplateName}"
              </span>{" "}
              to{" "}
              <span className="font-semibold text-foreground">
                "{resume.label}"
              </span>
              ?
            </DialogDescription>
          </DialogHeader>

          {startError && (
            <p className="text-sm text-red-500 bg-red-500/10 rounded-lg px-3 py-2">
              {startError}
            </p>
          )}

          <DialogFooter className="flex flex-col sm:flex-row gap-2 mt-3">
            <Button
              type="button"
              variant="ghost"
              disabled={isSubmitting}
              onClick={() => {
                setIsStyleDialogOpen(false);
                setSelectedTemplateId(null);
              }}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={isSubmitting}
              onClick={() => handleStyleConfirm("copy")}
              className="gap-2"
            >
              {isSubmitting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Copy className="w-4 h-4" />
              )}
              Make a Copy
            </Button>
            <Button
              type="button"
              disabled={isSubmitting}
              onClick={() => handleStyleConfirm("inplace")}
              className="gap-2"
            >
              {isSubmitting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
              Save In-place
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Rename Dialog ── */}
      <Dialog open={isRenameOpen} onOpenChange={setIsRenameOpen}>
        <DialogContent className="sm:max-w-md">
          <form onSubmit={handleRenameSubmit} className="space-y-4">
            <DialogHeader>
              <DialogTitle>Rename Resume</DialogTitle>
              <DialogDescription>
                Enter a new name/label for this resume.
              </DialogDescription>
            </DialogHeader>
            <div className="py-2">
              <Input
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                placeholder="Resume name..."
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setIsRenameOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit">Save</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
