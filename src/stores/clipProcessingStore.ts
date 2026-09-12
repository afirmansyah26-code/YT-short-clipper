import { create } from "zustand";
import type { ProcessOptions } from "@/hooks/processClips";

export type ClipJobStatus = "idle" | "running" | "completed" | "failed";
export type ClipStage = "download" | "portrait" | "hook" | "caption" | "watermark" | "finalizing";

export interface ClipLogLine {
  level: "info" | "warn" | "error" | "success";
  message: string;
  ts: number;
}

export interface ClipProcessingResult {
  results?: Array<{
    clip_index?: number;
    output_path?: string;
    title?: string;
    skipped?: boolean;
  }>;
  [key: string]: unknown;
}

export interface ClipProcessingJob {
  jobId: string;
  sessionDir: string;
  url: string;
  selectedHighlightIndices: number[];
  options: ProcessOptions;
  status: ClipJobStatus;
  stage: ClipStage;
  currentClip: number;
  totalClips: number;
  completedClips: number;
  progress: number;
  logLines: ClipLogLine[];
  error: string | null;
  result: ClipProcessingResult | null;
  startedAt: number;
  finishedAt: number | null;
  acknowledged: boolean;
}

interface ClipProcessingState {
  job: ClipProcessingJob | null;
  beginJob: (job: ClipProcessingJob) => void;
  appendLog: (jobId: string, line: ClipLogLine) => void;
  updateProgress: (jobId: string, update: Partial<Pick<ClipProcessingJob, "stage" | "currentClip" | "totalClips" | "completedClips" | "progress">>) => void;
  completeJob: (jobId: string, result: ClipProcessingResult) => void;
  failJob: (jobId: string, error: string) => void;
  acknowledgeJob: (jobId: string) => void;
  clearFinishedJob: (jobId: string) => void;
}

const MAX_LOG_LINES = 2000;

function withMatchingJob(
  state: ClipProcessingState,
  jobId: string,
  update: (job: ClipProcessingJob) => ClipProcessingJob,
): Pick<ClipProcessingState, "job"> {
  if (!state.job || state.job.jobId !== jobId) return { job: state.job };
  return { job: update(state.job) };
}

export const useClipProcessingStore = create<ClipProcessingState>((set) => ({
  job: null,

  beginJob: (job) => set({ job }),

  appendLog: (jobId, line) =>
    set((state) => withMatchingJob(state, jobId, (job) => ({
      ...job,
      logLines: [...job.logLines, line].slice(-MAX_LOG_LINES),
    }))),

  updateProgress: (jobId, update) =>
    set((state) => withMatchingJob(state, jobId, (job) => ({ ...job, ...update }))),

  completeJob: (jobId, result) =>
    set((state) => withMatchingJob(state, jobId, (job) => ({
      ...job,
      status: "completed",
      stage: "finalizing",
      progress: 100,
      completedClips: job.totalClips,
      result,
      finishedAt: Date.now(),
      acknowledged: false,
    }))),

  failJob: (jobId, error) =>
    set((state) => withMatchingJob(state, jobId, (job) => ({
      ...job,
      status: "failed",
      error,
      finishedAt: Date.now(),
      acknowledged: false,
    }))),

  acknowledgeJob: (jobId) =>
    set((state) => withMatchingJob(state, jobId, (job) => ({ ...job, acknowledged: true }))),

  clearFinishedJob: (jobId) =>
    set((state) => {
      if (!state.job || state.job.jobId !== jobId || state.job.status === "running") {
        return { job: state.job };
      }
      return { job: null };
    }),
}));
