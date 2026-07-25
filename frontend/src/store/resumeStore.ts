import { create } from "zustand";

interface ResumeState {
  resumeId: number | null;
  latexCode: string;
  diffLatexCode: string;
  pdfUrl: string | null;
  diffPdfUrl: string | null;
  label: string;
  templateId: string;
  jd: string;
  tone: string;
  file: File | null;
  isStreamingLatex: boolean;
  setResumeState: (state: Partial<ResumeState>) => void;
  resetResumeState: () => void;
}

const initialState = {
  resumeId: null,
  latexCode: "",
  diffLatexCode: "",
  pdfUrl: null,
  diffPdfUrl: null,
  label: "",
  templateId: "",
  jd: "",
  tone: "Professional",
  file: null,
  isStreamingLatex: false,
};

export const useResumeStore = create<ResumeState>((set) => ({
  ...initialState,
  setResumeState: (state) => set((prev) => ({ ...prev, ...state })),
  resetResumeState: () => set(initialState),
}));
