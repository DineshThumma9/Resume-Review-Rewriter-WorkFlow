import { z } from "zod";

// ─── Mirrors ResumeOut in backend/models.py ──────────────────────────────────
export const ResumeSchema = z.object({
  id: z.number(),
  label: z.string(),
  jd_snippet: z.string().nullable(),
  template_id: z.number().nullable(),
  tex_source: z.string().nullable().optional(),
  pdf_url: z.string().nullable(),
  preview_url: z.string().nullable().optional(),
  created_at: z.string(), // ISO datetime string from FastAPI
  updated_at: z.string(),
  content: z.any().optional(),
});

export type Resume = z.infer<typeof ResumeSchema>; // <-- type comes FROM the schema

// ─── SSE Event shapes ─────────────────────────────────────────────────────────
// Mirrors the event dicts yielded by the /analyze SSE endpoint in router.py.

// Analysis data shape from match_jd node
export const ResumeAnalysisSchema = z.object({
  score: z.number(),
  match: z.boolean(),
  match_explanation: z.string().optional(),
  missing_keywords: z.array(z.string()).optional(),
  negative_points: z.array(z.string()).optional(),
  potential_improvements: z.array(z.string()).optional(),
  resume_quality: z.string().optional(),
  urgency: z.string().nullable().optional(),
});

export type ResumeAnalysis = z.infer<typeof ResumeAnalysisSchema>;

export const AnalyzeEventSchema = z.discriminatedUnion("event", [
  z.object({
    event: z.literal("progress"),
    step: z.string(),
    message: z.string(),
    analysis: ResumeAnalysisSchema.optional(),
  }),
  z.object({
    event: z.literal("analysis_score"),
    score: z.number().optional(),
    match: z.boolean().optional(),
    company: z.string().optional(),
    urgency: z.string().nullable().optional(),
  }),
  z.object({
    event: z.literal("analysis_quality"),
    text: z.string(),
  }),
  z.object({
    event: z.literal("analysis_explanation"),
    text: z.string(),
  }),
  z.object({
    event: z.literal("analysis_keyword"),
    keyword: z.string(),
  }),
  z.object({
    event: z.literal("analysis_negative"),
    text: z.string(),
  }),
  z.object({
    event: z.literal("analysis_improvement"),
    text: z.string(),
  }),
  z.object({
    event: z.literal("analysis_done"),
  }),
  z.object({
    event: z.literal("complete"),
    message: z.string(),
    latexCode: z.string().optional(),
    diffLatexCode: z.string().optional(),
    pdfUrl: z.string().optional(),
    diffPdfUrl: z.string().optional(),
    resumeId: z.number().optional(),
    label: z.string().optional(),
    error: z.string().optional(), // LaTeX compile or upstream error surfaced in complete event
  }),
  z.object({
    event: z.literal("error"),
    message: z.string(),
  }),
]);

export type AnalyzeEvent = z.infer<typeof AnalyzeEventSchema>;
