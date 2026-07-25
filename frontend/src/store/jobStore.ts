import { create } from "zustand";
import {
  subscribeToJob,
  type JobStatus,
  type JobUpdate,
} from "../apis/styleJob";

export interface ActiveJob {
  jobId: number;
  resumeId: number;
  resumeLabel: string;
  style: string;
  status: JobStatus;
  pdfUrl?: string;
  errorMessage?: string;
}

interface JobStore {
  jobs: ActiveJob[];
  /** Start tracking a newly created job */
  addJob: (job: Omit<ActiveJob, "status"> & { status?: JobStatus }) => void;
  /** Update a tracked job from an SSE/poll update */
  updateJob: (jobId: number, update: Partial<ActiveJob>) => void;
  /** Remove a job (after user dismisses the toast) */
  dismissJob: (jobId: number) => void;
  /** Subscribe to SSE for a job and wire updates into the store */
  connectSSE: (jobId: number) => () => void;
}

export const useJobStore = create<JobStore>((set, get) => ({
  jobs: [],

  addJob: (job) => {
    set((s) => ({
      jobs: [
        ...s.jobs.filter((j) => j.jobId !== job.jobId),
        { status: "pending", ...job },
      ],
    }));
  },

  updateJob: (jobId, update) => {
    set((s) => ({
      jobs: s.jobs.map((j) => (j.jobId === jobId ? { ...j, ...update } : j)),
    }));
  },

  dismissJob: (jobId) => {
    set((s) => ({ jobs: s.jobs.filter((j) => j.jobId !== jobId) }));
  },

  connectSSE: (jobId) => {
    return subscribeToJob(
      jobId,
      (update: JobUpdate) => {
        get().updateJob(jobId, {
          status: update.status,
          pdfUrl: update.pdf_url ?? undefined,
          errorMessage: update.error_message ?? undefined,
        });
      },
      (err) => {
        console.error("SSE error for job", jobId, err);
        get().updateJob(jobId, {
          status: "failed",
          errorMessage: "Connection lost",
        });
      },
    );
  },
}));
