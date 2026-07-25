import { useState } from "react";
import useSWR from "swr";
import {
  Upload,
  Loader2,
  Image as ImageIcon,
  Trash,
  Edit2,
  Eye,
  FileText,
} from "lucide-react";
import { templateApi } from "../apis/templates";
import type { Template } from "../schemas";
import { Button } from "../components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../components/ui/dialog";
import { Input } from "../components/ui/input";

import { API_URL } from "../apis/api";
import { useNavigate } from "react-router-dom";
import { useResumeStore } from "../store/resumeStore";

export function TemplatesView() {
  const navigate = useNavigate();
  const setResumeState = useResumeStore((s) => s.setResumeState);
  const {
    data: templates = [],
    isLoading,
    mutate,
  } = useSWR<Template[]>("templates", () => templateApi.list());

  const [deleteTemplateId, setDeleteTemplateId] = useState<number | null>(null);
  const [renameTemplateId, setRenameTemplateId] = useState<number | null>(null);
  const [renameName, setRenameName] = useState("");

  const handleConfirmDelete = async () => {
    if (deleteTemplateId === null) return;
    const id = deleteTemplateId;
    setDeleteTemplateId(null);

    // Optimistic UI update
    mutate(
      templates.filter((t) => t.id !== id),
      false,
    );
    try {
      await templateApi.delete(id);
      mutate();
    } catch (err) {
      mutate();
      console.error("Failed to delete template:", err);
    }
  };

  const handleRenameSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (renameTemplateId === null || !renameName.trim()) return;

    const id = renameTemplateId;
    const template = templates.find((t) => t.id === id);
    if (!template) return;

    const newName = renameName.trim();
    setRenameTemplateId(null);

    // Optimistic UI update
    mutate(
      templates.map((t) => (t.id === id ? { ...t, name: newName } : t)),
      false,
    );

    try {
      await templateApi.update(id, newName, template.tex_source || "");
      mutate();
    } catch (err) {
      mutate();
      console.error("Failed to rename template:", err);
    }
  };

  return (
    <div className="px-4 py-6 md:px-6 md:py-10 flex flex-col gap-4 md:gap-6 overflow-y-auto h-full w-full">
      <div className="flex flex-col sm:flex-row items-start sm:items-end justify-between gap-4 sm:gap-0">
        <div>
          <h1 className="font-['EB_Garamond'] text-[36px] font-semibold text-foreground tracking-tight">
            My Templates
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Built-in and custom LaTeX templates for your resumes.
          </p>
        </div>
        <Button className="flex items-center justify-center gap-2 text-sm font-semibold shadow-sm w-full sm:w-auto">
          <Upload size={15} />
          Upload .tex
        </Button>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center gap-4 py-24 text-center text-muted-foreground">
          <Loader2 size={32} className="animate-spin" />
          <p className="font-medium">Loading templates...</p>
        </div>
      ) : templates.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-muted flex items-center justify-center">
            <ImageIcon
              size={32}
              strokeWidth={1}
              className="text-muted-foreground"
            />
          </div>
          <div>
            <p className="font-semibold text-foreground">No templates yet</p>
            <p className="text-sm text-muted-foreground mt-1">
              Upload a custom template to get started.
            </p>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map((t) => (
            <div
              key={t.id}
              className="border border-border bg-card rounded-xl p-5 flex flex-col gap-3 hover:border-primary/40 hover:shadow-md transition-all group"
            >
              {/* Full-page preview — A4 aspect ratio (1:1.414), full image visible */}
              <div
                className="w-full rounded-lg bg-muted overflow-hidden border border-border relative"
                style={{ aspectRatio: "1 / 1.414" }}
              >
                {t.preview_url ? (
                  <img
                    src={t.preview_url}
                    alt={t.name}
                    className="w-full h-full object-contain transition-transform duration-300 group-hover:scale-[1.02]"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <ImageIcon
                      size={36}
                      strokeWidth={1}
                      className="text-muted-foreground opacity-30"
                    />
                  </div>
                )}
              </div>
              <div className="flex items-center justify-between">
                <span
                  className="font-semibold text-sm text-foreground truncate max-w-[150px]"
                  title={t.name}
                >
                  {t.name}
                </span>
                <div className="flex items-center gap-1.5">
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      t.is_builtin
                        ? "bg-primary/10 text-primary"
                        : "bg-secondary text-secondary-foreground"
                    }`}
                  >
                    {t.is_builtin ? "Built-in" : "Custom"}
                  </span>
                  {!t.is_builtin && (
                    <>
                      <button
                        onClick={() => {
                          setRenameTemplateId(t.id);
                          setRenameName(t.name);
                        }}
                        className="p-1 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                        title="Rename template"
                      >
                        <Edit2 size={14} />
                      </button>
                      <button
                        onClick={() => {
                          setDeleteTemplateId(t.id);
                        }}
                        className="p-1 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                        title="Delete custom template"
                      >
                        <Trash size={14} />
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Action buttons: View PDF / Edit */}
              <div className="grid grid-cols-2 gap-2 mt-2 w-full">
                {t.preview_url ? (
                  <button
                    onClick={() => {
                      const targetUrl = t.preview_url;
                      if (
                        targetUrl &&
                        targetUrl.includes("res.cloudinary.com")
                      ) {
                        const pdfUrl = targetUrl
                          .replace(/\.(jpg|png)(\?.*)?$/i, ".pdf")
                          .replace(/\/c_scale,[^/]+\//, "/")
                          .replace(/\/f_jpg[^/]*\//, "/")
                          .replace(/\/w_\d+[^/]*\//, "/");
                        window.open(pdfUrl, "_blank");
                      } else {
                        const token = localStorage.getItem("token");
                        const pdfUrl =
                          `${API_URL}/templates/${t.id}/pdf` +
                          (token ? `?token=${encodeURIComponent(token)}` : "");
                        window.open(pdfUrl, "_blank");
                      }
                    }}
                    className="w-full inline-flex items-center justify-center gap-1.5 px-2 py-2 text-xs font-semibold rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors h-9 min-w-0"
                    title="View PDF Preview"
                  >
                    <Eye size={14} className="shrink-0" />
                    <span className="hidden md:inline truncate">View PDF</span>
                  </button>
                ) : (
                  <div
                    className="w-full h-9 bg-muted/30 rounded-lg flex items-center justify-center text-[10px] text-muted-foreground/60 font-medium border border-dashed border-border/50"
                    title="No PDF preview available"
                  >
                    <Eye size={14} className="opacity-40" />
                  </div>
                )}
                <button
                  onClick={() => {
                    setResumeState({
                      latexCode: t.tex_source || "",
                      pdfUrl: t.preview_url || null,
                      templateId: String(t.id),
                      label: t.name,
                    });
                    navigate("/analyze", { state: { tab: "editor" } });
                  }}
                  className="w-full inline-flex items-center justify-center gap-1.5 px-2 py-2 text-xs font-semibold rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-colors h-9 min-w-0"
                  title="Use Template in Editor"
                >
                  <FileText size={14} className="shrink-0" />
                  <span className="hidden md:inline truncate">
                    Use Template
                  </span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* DELETE CONFIRMATION DIALOG */}
      <Dialog
        open={deleteTemplateId !== null}
        onOpenChange={(open) => !open && setDeleteTemplateId(null)}
      >
        <DialogContent className="sm:max-w-md">
          <div className="text-center p-2">
            <h3 className="font-['EB_Garamond'] text-2xl font-semibold mb-2">
              Delete Template
            </h3>
            <p className="text-xs text-muted-foreground mb-6">
              Are you sure you want to delete this custom template? This action
              cannot be undone.
            </p>
            <div className="flex justify-center gap-3">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setDeleteTemplateId(null)}
              >
                Cancel
              </Button>
              <Button
                variant="default"
                size="sm"
                className="bg-red-600 hover:bg-red-700 text-white font-semibold"
                onClick={handleConfirmDelete}
              >
                Delete
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* RENAME DIALOG */}
      <Dialog
        open={renameTemplateId !== null}
        onOpenChange={(open) => !open && setRenameTemplateId(null)}
      >
        <DialogContent className="sm:max-w-md">
          <form onSubmit={handleRenameSubmit} className="space-y-4">
            <DialogHeader>
              <DialogTitle>Rename Template</DialogTitle>
              <DialogDescription>
                Enter a new name/label for this custom template.
              </DialogDescription>
            </DialogHeader>
            <div className="py-2">
              <Input
                value={renameName}
                onChange={(e) => setRenameName(e.target.value)}
                placeholder="Template name..."
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setRenameTemplateId(null)}
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
