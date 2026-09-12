import { logClipSuccess, type ClipSuccessFormat } from "@/hooks/successLog";
import { processClips } from "@/hooks/processClips";
import {
  useClipProcessingStore,
  type ClipLogLine,
  type ClipProcessingResult,
  type ClipStage,
} from "@/stores/clipProcessingStore";

type ClipProcessingRequest = Parameters<typeof processClips>[0];

const STAGE_PROGRESS: Record<ClipStage, number> = {
  download: 5,
  portrait: 25,
  hook: 45,
  caption: 65,
  watermark: 85,
  finalizing: 95,
};

interface ActiveRun {
  jobId: string;
  promise: Promise<void>;
}

let activeRun: ActiveRun | null = null;

function makeJobId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `clip-job-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function logLine(message: string): ClipLogLine {
  const lower = message.toLowerCase();
  const level: ClipLogLine["level"] = lower.includes("error") || lower.includes("failed")
    ? "error"
    : lower.includes("warning") || lower.includes("unavailable")
      ? "warn"
      : lower.includes("success") || lower.includes("complete") || lower.includes("saved")
        ? "success"
        : "info";
  return { level, message, ts: Date.now() };
}

function stageFromLog(message: string): ClipStage | null {
  const lower = message.toLowerCase();
  if (lower.includes("downloading video section") || lower.includes("batch download") || lower.includes("cached source")) return "download";
  if (lower.includes("section downloaded") || lower.includes("converting to portrait")) return "portrait";
  if (lower.includes("portrait conversion complete") || lower.includes("portrait complete")) return "hook";
  if (lower.includes("hook generation") || lower.includes("hook complete")) return "caption";
  if (lower.includes("caption generation") || lower.includes("caption complete")) return "watermark";
  if (lower.includes("watermark overlay") || lower.includes("watermark complete")) return "finalizing";
  return null;
}

function updateFromLog(jobId: string, message: string): void {
  const store = useClipProcessingStore.getState();
  const job = store.job;
  if (!job || job.jobId !== jobId) return;

  store.appendLog(jobId, logLine(message));

  const clipMatch = message.match(/processing clip\s+(\d+)\s*\/\s*(\d+)/i);
  const stage = stageFromLog(message);
  const update: Parameters<typeof store.updateProgress>[1] = {};

  if (clipMatch) {
    update.currentClip = Number(clipMatch[1]);
    update.totalClips = Number(clipMatch[2]);
    update.stage = "download";
  } else if (stage) {
    update.stage = stage;
  }

  if (message.toLowerCase().includes("clip saved")) {
    const total = update.totalClips ?? job.totalClips;
    const completed = Math.min(total, job.completedClips + 1);
    update.completedClips = completed;
    update.progress = total > 0 ? Math.min(99, Math.round((completed / total) * 95)) : job.progress;
  } else if (update.stage) {
    const total = update.totalClips ?? job.totalClips;
    const clipBase = total > 0 ? (Math.max(0, (update.currentClip ?? job.currentClip) - 1) / total) * 95 : 0;
    update.progress = Math.max(job.progress, Math.min(99, Math.round(clipBase + STAGE_PROGRESS[update.stage] / Math.max(total, 1))));
  }

  if (Object.keys(update).length > 0) store.updateProgress(jobId, update);
}

function successFormat(request: ClipProcessingRequest): ClipSuccessFormat {
  return request.options.reframeMode === "face"
    ? "face-tracking"
    : request.options.centeredBackground === "blurred"
      ? "centered-blur"
      : "centered-black";
}

async function recordTelemetry(request: ClipProcessingRequest, result: ClipProcessingResult): Promise<void> {
  const durationByIndex = new Map<number, number>();
  request.highlights.forEach((highlight) => {
    const item = highlight as { _highlight_index?: number; duration_seconds?: number };
    if (typeof item._highlight_index === "number" && typeof item.duration_seconds === "number") {
      durationByIndex.set(item._highlight_index, item.duration_seconds);
    }
  });

  for (const clip of result.results ?? []) {
    if (clip.skipped) continue;
    const duration = durationByIndex.get(clip.clip_index ?? -1);
    if (typeof duration === "number" && duration > 0) {
      void logClipSuccess({ duration, format: successFormat(request) });
    }
  }
}

async function runJob(jobId: string, request: ClipProcessingRequest): Promise<void> {
  const store = useClipProcessingStore.getState();
  updateFromLog(jobId, "Starting clip processing...");

  try {
    const result = (await processClips({
      ...request,
      options: { ...request.options, processingJobId: jobId },
      onLog: (message) => updateFromLog(jobId, message),
    })) as ClipProcessingResult;
    await recordTelemetry(request, result);
    store.completeJob(jobId, result);
  } catch (error) {
    const detail = error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : JSON.stringify(error);
    updateFromLog(jobId, `Error: ${detail}`);
    store.failJob(jobId, detail);
  }
}

export interface StartClipProcessingResult {
  started: boolean;
  jobId: string;
}

export function startClipProcessing(request: ClipProcessingRequest): StartClipProcessingResult {
  if (activeRun) return { started: false, jobId: activeRun.jobId };

  const jobId = makeJobId();
  const store = useClipProcessingStore.getState();
  const selectedHighlightIndices = request.highlights.map((highlight, index) => {
    const value = (highlight as { _highlight_index?: number })._highlight_index;
    return typeof value === "number" ? value : index;
  });

  store.beginJob({
    jobId,
    sessionDir: request.sessionDir,
    url: request.url,
    selectedHighlightIndices,
    options: request.options,
    status: "running",
    stage: "download",
    currentClip: 0,
    totalClips: request.highlights.length,
    completedClips: 0,
    progress: 0,
    logLines: [],
    error: null,
    result: null,
    startedAt: Date.now(),
    finishedAt: null,
    acknowledged: false,
  });

  const promise = runJob(jobId, request);
  activeRun = { jobId, promise };
  void promise.then(() => {
    if (activeRun?.jobId === jobId) activeRun = null;
  });
  return { started: true, jobId };
}

export function getActiveClipJobId(): string | null {
  return activeRun?.jobId ?? null;
}

export function getActiveClipSessionDir(): string | null {
  const state = useClipProcessingStore.getState();
  return state.job?.status === "running" ? state.job.sessionDir : null;
}
