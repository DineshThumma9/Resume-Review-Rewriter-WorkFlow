import { API_URL, fetchJSON } from "./api";

export type JobStatus = "pending" | "running" | "completed" | "failed";

export interface StyleJob {
  job_id: number;
  message: string;
  status: JobStatus;
}

export interface JobStatusResponse {
  job_id: number;
  resume_id: number;
  style: string;
  status: JobStatus;
  pdf_url: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface JobUpdate {
  job_id: number;
  status: JobStatus;
  pdf_url?: string;
  error_message?: string;
}

/** POST /resumes/{id}/change-style  — starts the background job */
export async function startStyleChange(
  resumeId: number,
  style: string,
): Promise<StyleJob> {
  const fd = new FormData();
  fd.append("style", style);
  const res = await fetch(`${API_URL}/resumes/${resumeId}/change-style`, {
    method: "POST",
    body: fd,
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

/** GET /resumes/jobs/{id}/status  — poll fallback */
export async function getJobStatus(jobId: number): Promise<JobStatusResponse> {
  return fetchJSON(`/resumes/jobs/${jobId}/status`);
}

/**
 * Open an SSE stream for a job.
 * Calls onUpdate for each message. Returns a cleanup function.
 */
export function subscribeToJob(
  jobId: number,
  onUpdate: (update: JobUpdate) => void,
  onError?: (err: Error) => void,
): () => void {
  const url = `${API_URL}/resumes/jobs/${jobId}/updates`;
  const es = new EventSource(url, { withCredentials: true });

  es.onmessage = (event) => {
    try {
      const data: JobUpdate = JSON.parse(event.data);
      onUpdate(data);
      // Close automatically when terminal
      if (data.status === "completed" || data.status === "failed") {
        es.close();
      }
    } catch (e) {
      console.error("Failed to parse job update:", e);
    }
  };

  es.onerror = () => {
    onError?.(new Error("SSE connection lost"));
    es.close();
  };

  return () => es.close();
}
