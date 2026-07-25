import { useState, useEffect } from "react";
import useSWR from "swr";
import { type AnalyzeEvent, type Template } from "../apis/api";
import { analyzeResume, resumeApi } from "../apis/resumes";
import { templateApi } from "../apis/templates";
import { getApiModels, getCurrentModel, modelSelection } from "../apis/setup";
import type { ResumeAnalysis } from "../schemas";
import { useResumeStore } from "../store/resumeStore";

export type StreamLine = {
  type: "progress" | "success" | "error";
  text: string;
  analysis?: ResumeAnalysis;
};

export function useResumeAnalysis() {
  const { resumeId, pdfUrl, setResumeState, latexCode, label } =
    useResumeStore();
  const [lines, setLines] = useState<StreamLine[]>([]);
  const [running, setRunning] = useState(false);
  const [isCompiling, setIsCompiling] = useState(false);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [compileError, setCompileError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [availableModels, setAvailableModels] = useState<
    Record<string, string[]>
  >({});

  const { data: modelsData } = useSWR<Record<string, string[]>>(
    "/setup/api-models",
    () => getApiModels(),
    {
      dedupingInterval: 24 * 60 * 60 * 1000,
      revalidateOnFocus: false,
    },
  );

  const { data: currentModelData } = useSWR<{
    provider: string;
    model: string;
  }>("/setup/current-model", () => getCurrentModel(), {
    dedupingInterval: 24 * 60 * 60 * 1000,
    revalidateOnFocus: false,
  });

  useEffect(() => {
    if (modelsData && currentModelData) {
      setAvailableModels(modelsData);
      if (currentModelData.provider && currentModelData.model) {
        setProvider(currentModelData.provider);
        setModel(currentModelData.model);
      } else {
        const firstProvider = Object.keys(modelsData)[0];
        if (firstProvider) {
          setProvider(firstProvider);
          const firstModel = modelsData[firstProvider][0] || "";
          setModel(firstModel);
          if (firstModel && firstProvider) {
            modelSelection(firstModel, firstProvider).catch((err) => {
              console.error(err);
              setApiError(err instanceof Error ? err.message : String(err));
            });
          }
        }
      }
    }
  }, [modelsData, currentModelData]);

  useEffect(() => {
    templateApi
      .list()
      .then((tpls) => {
        setTemplates(tpls);
        if (tpls.length > 0) {
          // Always default to the first template (jakes1); correct stale / empty selections
          const currentId = useResumeStore.getState().templateId;
          const validIds = new Set(tpls.map((t) => String(t.id)));
          if (!currentId || !validIds.has(currentId)) {
            setResumeState({ templateId: String(tpls[0].id) });
          }
        }
      })
      .catch(console.error);
  }, [setResumeState]);

  const handleProviderChange = (p: string) => {
    if (!p) return;
    setProvider(p);
    const m = availableModels[p]?.[0] || "";
    setModel(m);
    if (m) {
      modelSelection(m, p).catch((err) => {
        console.error(err);
        setApiError(err instanceof Error ? err.message : String(err));
      });
    }
  };

  const handleModelChange = (m: string) => {
    if (!m || !provider) return;
    setModel(m);
    modelSelection(m, provider).catch((err) => {
      console.error(err);
      setApiError(err instanceof Error ? err.message : String(err));
    });
  };

  const clearLines = () => setLines([]);

  const submitAnalysis = (fd: FormData, onSuccess: () => void) => {
    setLines([]);
    setRunning(true);
    setLines([
      {
        type: "progress",
        text: "Analyzing job description and extracting key requirements...",
      },
    ]);

    let accumulatedAnalysis: Partial<ResumeAnalysis> = {};

    analyzeResume(fd, (ev: AnalyzeEvent) => {
      // ── Granular streaming analysis events (sent progressively by backend) ──
      if (ev.event === "analysis_score") {
        accumulatedAnalysis = {
          ...accumulatedAnalysis,
          score: ev.score,
          match: ev.match,
          urgency: ev.urgency,
        };
        setLines((prev) => {
          const n = [...prev];
          const idx = n.findIndex((l) => l.text.includes("Analyzing"));
          if (idx >= 0) {
            n[idx] = {
              type: "progress",
              text: "Analyzing job description and extracting key requirements...",
              analysis: { ...accumulatedAnalysis } as ResumeAnalysis,
            };
          }
          return n;
        });
      } else if (ev.event === "analysis_quality") {
        accumulatedAnalysis = {
          ...accumulatedAnalysis,
          resume_quality: ev.text,
        };
        setLines((prev) => {
          const n = [...prev];
          const idx = n.findIndex((l) => l.text.includes("Analyzing"));
          if (idx >= 0)
            n[idx] = {
              ...n[idx],
              analysis: { ...accumulatedAnalysis } as ResumeAnalysis,
            };
          return n;
        });
      } else if (ev.event === "analysis_explanation") {
        accumulatedAnalysis = {
          ...accumulatedAnalysis,
          match_explanation: ev.text,
        };
        setLines((prev) => {
          const n = [...prev];
          const idx = n.findIndex((l) => l.text.includes("Analyzing"));
          if (idx >= 0)
            n[idx] = {
              ...n[idx],
              analysis: { ...accumulatedAnalysis } as ResumeAnalysis,
            };
          return n;
        });
      } else if (ev.event === "analysis_keyword") {
        accumulatedAnalysis = {
          ...accumulatedAnalysis,
          missing_keywords: [
            ...(accumulatedAnalysis.missing_keywords || []),
            ev.keyword,
          ],
        };
        setLines((prev) => {
          const n = [...prev];
          const idx = n.findIndex((l) => l.text.includes("Analyzing"));
          if (idx >= 0)
            n[idx] = {
              ...n[idx],
              analysis: { ...accumulatedAnalysis } as ResumeAnalysis,
            };
          return n;
        });
      } else if (ev.event === "analysis_negative") {
        accumulatedAnalysis = {
          ...accumulatedAnalysis,
          negative_points: [
            ...(accumulatedAnalysis.negative_points || []),
            ev.text,
          ],
        };
        setLines((prev) => {
          const n = [...prev];
          const idx = n.findIndex((l) => l.text.includes("Analyzing"));
          if (idx >= 0)
            n[idx] = {
              ...n[idx],
              analysis: { ...accumulatedAnalysis } as ResumeAnalysis,
            };
          return n;
        });
      } else if (ev.event === "analysis_improvement") {
        accumulatedAnalysis = {
          ...accumulatedAnalysis,
          potential_improvements: [
            ...(accumulatedAnalysis.potential_improvements || []),
            ev.text,
          ],
        };
        setLines((prev) => {
          const n = [...prev];
          const idx = n.findIndex((l) => l.text.includes("Analyzing"));
          if (idx >= 0)
            n[idx] = {
              ...n[idx],
              analysis: { ...accumulatedAnalysis } as ResumeAnalysis,
            };
          return n;
        });
      } else if (ev.event === "analysis_done") {
        // Mark the analysis step as complete and add next step
        setLines((prev) => {
          const n = [...prev];
          const idx = n.findIndex((l) => l.text.includes("Analyzing"));
          if (idx >= 0) {
            n[idx] = {
              type: "success",
              text: "JD analysis complete.",
              analysis: { ...accumulatedAnalysis } as ResumeAnalysis,
            };
          }
          return [
            ...n,
            {
              type: "progress",
              text: "AI is rewriting your resume to match the JD...",
            },
          ];
        });
      } else if (ev.event === "progress") {
        setLines((prev) => {
          const n = [...prev];
          const lastIdx = n.map((l) => l.type).lastIndexOf("progress");
          if (lastIdx >= 0) {
            n[lastIdx] = {
              ...n[lastIdx],
              type: "success",
            };
          }
          return [
            ...n,
            {
              type: "progress",
              text: ev.message,
              analysis: { ...accumulatedAnalysis } as ResumeAnalysis,
            },
          ];
        });
      }
      if (ev.event === "complete") {
        setRunning(false);
        const latex = ev.latexCode ?? "";
        const compileErr = ev.error; // LaTeX compile error OR upstream LLM error in complete payload
        const isError = !!compileErr || latex.startsWith("Error:");

        setResumeState({
          latexCode: latex || "% No LaTeX was generated.",
          diffLatexCode: ev.diffLatexCode || "",
          pdfUrl: isError ? null : ev.pdfUrl || pdfUrl,
          diffPdfUrl: isError ? null : ev.diffPdfUrl || null,
          resumeId: ev.resumeId || resumeId,
          label: ev.label || label,
        });

        if (compileErr) {
          // LaTeX compile errors go to the compile error modal; LLM/API errors go to apiError modal
          if (
            compileErr.toLowerCase().includes("latex") ||
            compileErr.toLowerCase().includes("compilation")
          ) {
            setCompileError(compileErr);
          } else {
            setApiError(compileErr);
          }
        }

        setLines((prev) => {
          const n = [...prev];
          const last = n.length - 1;
          if (last >= 0 && n[last].type === "progress")
            n[last] = {
              ...n[last],
              type: isError ? "error" : "success",
            };
          return [
            ...n,
            {
              type: isError ? "error" : "success",
              text: isError
                ? compileErr || "Resume generation failed."
                : "Done! Resume generated.",
            },
          ];
        });
        onSuccess();
      }
      if (ev.event === "error") {
        const msg = ev.message || "An unknown error occurred.";
        setLines((prev) => {
          const n = [...prev];
          const last = n.length - 1;
          if (last >= 0 && n[last].type === "progress") {
            n[last] = {
              ...n[last],
              type: "error",
              text: "Failed.",
            };
          }
          return [...n, { type: "error", text: msg }];
        });
        setApiError(msg); // Show in modal so it's impossible to miss
        setRunning(false);
      }
    }).catch((err) => {
      console.error("Analysis failed:", err);
      const msg = err instanceof Error ? err.message : String(err);
      setLines((prev) => {
        const n = [...prev];
        const last = n.length - 1;
        if (last >= 0 && n[last].type === "progress") {
          n[last] = {
            ...n[last],
            type: "error",
            text: "Failed.",
          };
        }
        return [...n, { type: "error", text: msg }];
      });
      setApiError(msg); // Network down / server unreachable errors shown in modal
      setRunning(false);
    });
  };

  const handleCompile = async () => {
    const isStreaming = useResumeStore.getState().isStreamingLatex;
    if (isStreaming) {
      setApiError(
        "LaTeX code is currently being generated/modified by AI. Please wait until streaming completes before compiling the PDF.",
      );
      return;
    }
    try {
      setIsCompiling(true);
      setCompileError(null);
      const res = await resumeApi.compile(latexCode, resumeId);
      setResumeState({ pdfUrl: res.pdfUrl, diffPdfUrl: null });
    } catch (e: unknown) {
      setCompileError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsCompiling(false);
    }
  };

  return {
    lines,
    clearLines,
    running,
    isCompiling,
    templates,
    provider,
    handleProviderChange,
    model,
    handleModelChange,
    availableModels,
    submitAnalysis,
    handleCompile,
    compileError,
    setCompileError,
    apiError,
    setApiError,
  };
}
