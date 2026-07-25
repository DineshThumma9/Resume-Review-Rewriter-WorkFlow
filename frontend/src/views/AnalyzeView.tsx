import { useState } from "react";
import { useLocation } from "react-router-dom";
import Editor from "@monaco-editor/react";
import { useResumeStore } from "../store/resumeStore";

import { useResumeAnalysis } from "../hooks/useResumeAnalysis";
import { API_URL } from "../apis/api";
import { resumeApi } from "../apis/resumes";
import { templateApi } from "../apis/templates";
import { AnalysisForm } from "../components/analyze/AnalysisForm";
import { EditorToolbar } from "../components/analyze/EditorToolbar";
import { PdfPreviewPanel } from "../components/analyze/PdfPreviewPanel";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "../components/ui/tabs";
import { Button } from "../components/ui/button";
import { ProgressStream } from "../components/analyze/ProgressStream";
import Ai from "../components/ai-input";

export function AnalyzeView() {
  const {
    latexCode,
    setResumeState,
    pdfUrl,
    diffPdfUrl,
    resumeId,
    label,
    isStreamingLatex,
  } = useResumeStore();

  const [showDiff, setShowDiff] = useState(false);

  const {
    running,
    isCompiling,
    provider,
    handleProviderChange: setProvider,
    model,
    handleModelChange: setModel,
    availableModels,
    submitAnalysis: handleAnalysisSubmit,
    handleCompile,
    templates,
    compileError,
    setCompileError,
    apiError,
    setApiError,
    lines,
    clearLines,
  } = useResumeAnalysis();

  const location = useLocation();
  const [activeTab, setActiveTab] = useState<string>(
    (location.state as { tab?: string })?.tab || "analysis",
  );

  // Custom states for the new toolbar buttons
  const [isSaving, setIsSaving] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [isSavingTemplate, setIsSavingTemplate] = useState(false);

  const [showShareModal, setShowShareModal] = useState(false);
  const [isDownloadingAnonymous, setIsDownloadingAnonymous] = useState(false);
  const [maskOptions, setMaskOptions] = useState<Record<string, boolean>>({
    name: true,
    email: true,
    phone: true,
    location: true,
    github: true,
    linkedin: true,
    leetcode: true,
    portfolio: true,
    project_name: true,
    company_name: true,
    education: true,
  });

  const handleDownloadTex = () => {
    if (latexCode) {
      const blob = new Blob([latexCode], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${label || "resume"}.tex`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      if (resumeId) {
        await resumeApi.update(resumeId, label || "Untitled Resume", latexCode);
      } else {
        const newResume = await resumeApi.create(
          label || "Untitled Resume",
          latexCode,
        );
        setResumeState({ resumeId: newResume.id });
      }
    } catch (err) {
      console.error("Failed to save resume:", err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveTemplate = async () => {
    if (!latexCode || !templateName.trim()) return;
    setIsSavingTemplate(true);
    try {
      await templateApi.create(templateName.trim(), latexCode);
      setShowTemplateModal(false);
      setTemplateName("");
    } catch (err) {
      console.error("Failed to save template:", err);
    } finally {
      setIsSavingTemplate(false);
    }
  };

  const handleDownloadAnonymousSubmit = async () => {
    if (!resumeId) return;
    setIsDownloadingAnonymous(true);
    try {
      const response = await fetch(
        `${API_URL}/share/${resumeId}/download-anonymous`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "include",
          body: JSON.stringify({ ...maskOptions, latex_code: latexCode }),
        },
      );

      if (!response.ok) {
        throw new Error("Failed to download anonymous PDF");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `masked_resume_${resumeId}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
      setShowShareModal(false);
    } catch (err) {
      console.error("Failed to download anonymous resume:", err);
    } finally {
      setIsDownloadingAnonymous(false);
    }
  };

  const handleUploadTex = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      setResumeState({ latexCode: content });
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  return (
    <div className="flex flex-col md:flex-row flex-1 w-full bg-background overflow-hidden font-sans h-full relative">
      {/* LEFT PANEL: Tabs (Analysis, Editor) */}
      <div
        className={
          activeTab === "editor"
            ? "w-full md:w-1/2 flex flex-col bg-background h-[50vh] md:h-full shrink-0"
            : "w-full flex flex-col bg-background h-full"
        }
      >
        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex flex-col h-full"
        >
          <div className="flex items-center justify-between p-2 bg-background">
            <div className="flex items-center gap-2">
              <TabsList className="bg-transparent p-0 gap-4">
                <TabsTrigger
                  value="analysis"
                  className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none px-0 font-medium"
                >
                  Analysis
                </TabsTrigger>
                <TabsTrigger
                  value="editor"
                  className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none px-0 font-medium"
                >
                  Editor
                </TabsTrigger>
              </TabsList>
            </div>

            {activeTab === "editor" && (
              <EditorToolbar
                onCompile={handleCompile}
                onDownloadTex={handleDownloadTex}
                onUploadTex={handleUploadTex}
                onSave={handleSave}
                onSaveAsTemplate={() => setShowTemplateModal(true)}
                onShareAnonymous={() => setShowShareModal(true)}
                isCompiling={isCompiling}
                isSaving={isSaving}
                hasResumeId={!!resumeId}
                showDiff={showDiff}
                onToggleDiff={() => setShowDiff(!showDiff)}
                hasDiff={!!diffPdfUrl}
                isStreamingLatex={isStreamingLatex}
              />
            )}
          </div>

          <TabsContent
            value="analysis"
            className="flex-1 overflow-y-auto min-h-0 p-4 md:p-6 m-0 flex flex-col items-start justify-start w-full"
          >
            {lines.length > 0 || running ? (
              <ProgressStream
                logs={lines}
                running={running}
                onReset={clearLines}
              />
            ) : (
              <AnalysisForm
                running={running}
                templates={templates}
                provider={provider}
                model={model}
                availableModels={availableModels}
                onProviderChange={setProvider}
                onModelChange={setModel}
                onSubmit={(fd) => {
                  handleAnalysisSubmit(fd, () => {
                    setActiveTab("editor");
                  });
                }}
              />
            )}
          </TabsContent>

          <TabsContent
            value="editor"
            className="flex-1 m-0 bg-[#1e1e1e] h-full overflow-hidden relative"
          >
            <Editor
              height="100%"
              language="latex"
              theme="vs-dark"
              value={latexCode}
              onChange={(v) => setResumeState({ latexCode: v || "" })}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                wordWrap: "on",
                lineNumbers: "on",
                folding: true,
                scrollBeyondLastLine: false,
                smoothScrolling: true,
                padding: { top: 16, bottom: 80 },
              }}
            />
            <div className="absolute bottom-6 left-1/2 -translate-x-1/2 w-full max-w-2xl px-4 z-10 pointer-events-none">
              <div className="pointer-events-auto">
                <Ai provider={provider} model={model} />
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>

      {/* RIGHT PANEL: PDF Preview */}
      {activeTab === "editor" && (
        <div className="w-full md:w-1/2 flex flex-col h-[50vh] md:h-full bg-[#525659]">
          <PdfPreviewPanel
            pdfUrl={showDiff ? diffPdfUrl || pdfUrl : pdfUrl}
            isCompiling={isCompiling}
          />
        </div>
      )}

      {/* SAVE AS TEMPLATE MODAL */}
      {showTemplateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs">
          <div className="bg-background rounded-xl shadow-xl w-full max-w-md p-6 animate-in fade-in zoom-in-95 duration-200">
            <h3 className="font-['EB_Garamond'] text-2xl font-semibold text-foreground mb-2">
              Save as Template
            </h3>
            <p className="text-xs text-muted-foreground mb-6">
              Enter a name to save the current LaTeX code as a reusable
              template.
            </p>
            <input
              type="text"
              placeholder="e.g. My Custom Jake Template"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              className="w-full text-sm border-0 border-b border-border bg-transparent placeholder:text-muted-foreground/45 py-2 outline-none mb-6 text-foreground focus:border-primary transition-colors"
            />
            <div className="flex justify-end gap-3">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowTemplateModal(false)}
              >
                Cancel
              </Button>
              <Button
                variant="default"
                size="sm"
                className="font-semibold"
                disabled={!templateName.trim() || isSavingTemplate}
                onClick={handleSaveTemplate}
              >
                {isSavingTemplate ? "Saving..." : "Save Template"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* SHARE ANONYMOUS MODAL */}
      {showShareModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs">
          <div className="bg-background rounded-xl shadow-xl w-full max-w-lg p-6 animate-in fade-in zoom-in-95 duration-200">
            <h3 className="font-['EB_Garamond'] text-2xl font-semibold text-foreground mb-2">
              Download Anonymized Resume
            </h3>
            <p className="text-xs text-muted-foreground mb-6">
              Select the personal details and sections to redact before
              downloading the PDF.
            </p>

            <div className="grid grid-cols-2 gap-4 mb-8">
              {Object.keys(maskOptions).map((key) => (
                <label
                  key={key}
                  className="flex items-center gap-3 cursor-pointer select-none text-sm text-foreground"
                >
                  <input
                    type="checkbox"
                    checked={maskOptions[key]}
                    onChange={(e) =>
                      setMaskOptions({
                        ...maskOptions,
                        [key]: e.target.checked,
                      })
                    }
                    className="accent-primary h-4 w-4"
                  />
                  <span className="capitalize">{key.replace("_", " ")}</span>
                </label>
              ))}
            </div>

            <div className="flex justify-end gap-3 border-t border-border pt-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowShareModal(false)}
              >
                Cancel
              </Button>
              <Button
                variant="default"
                size="sm"
                className="font-semibold"
                disabled={isDownloadingAnonymous}
                onClick={handleDownloadAnonymousSubmit}
              >
                {isDownloadingAnonymous
                  ? "Generating..."
                  : "Download Anonymous PDF"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* COMPILATION ERROR MODAL */}
      {compileError && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs">
          <div className="bg-background rounded-xl shadow-xl w-full max-w-2xl p-6 animate-in fade-in zoom-in-95 duration-200">
            <h3 className="font-['EB_Garamond'] text-2xl font-semibold text-red-500 mb-2">
              Compilation Failed
            </h3>
            <div className="text-xs text-foreground/90 bg-muted/50 border border-border rounded-lg p-3 max-h-[50vh] overflow-y-auto font-mono mb-6 whitespace-pre-wrap">
              {compileError}
            </div>
            <div className="flex justify-end">
              <Button
                variant="default"
                size="sm"
                onClick={() => setCompileError(null)}
              >
                Dismiss
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* API ERROR MODAL */}
      {apiError && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs">
          <div className="bg-background rounded-xl shadow-xl w-full max-w-2xl p-6 animate-in fade-in zoom-in-95 duration-200">
            <h3 className="font-['EB_Garamond'] text-2xl font-semibold text-red-500 mb-2">
              API Error
            </h3>
            <div className="text-xs text-foreground/90 bg-muted/50 border border-border rounded-lg p-3 max-h-[50vh] overflow-y-auto font-mono mb-6 whitespace-pre-wrap">
              {apiError}
            </div>
            <div className="flex justify-end">
              <Button
                variant="default"
                size="sm"
                onClick={() => setApiError(null)}
              >
                Dismiss
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
