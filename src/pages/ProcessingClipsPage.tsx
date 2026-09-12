import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { AlertCircle, ArrowLeft, Check, CheckCircle2, Copy, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useClipProcessingStore, type ClipStage } from "@/stores/clipProcessingStore";
import { formatLogTime } from "@/utils/format";

const STAGES: Array<{ key: ClipStage; label: string; option?: "addHook" | "addCaptions" | "addWatermark" | "addCreditWatermark" }> = [
  { key: "download", label: "Download video sections" },
  { key: "portrait", label: "Portrait conversion (9:16)" },
  { key: "hook", label: "Hook generation", option: "addHook" },
  { key: "caption", label: "Caption generation", option: "addCaptions" },
  { key: "watermark", label: "Watermark overlay", option: "addWatermark" },
];

const STAGE_INDEX: Record<ClipStage, number> = {
  download: 0,
  portrait: 1,
  hook: 2,
  caption: 3,
  watermark: 4,
  finalizing: 5,
};

export function ProcessingClipsPage() {
  const navigate = useNavigate();
  const job = useClipProcessingStore((state) => state.job);
  const acknowledgeJob = useClipProcessingStore((state) => state.acknowledgeJob);
  const [copied, setCopied] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (job && job.status !== "running" && !job.acknowledged) {
      acknowledgeJob(job.jobId);
    }
  }, [job?.jobId, job?.status, job?.acknowledged, acknowledgeJob]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [job?.logLines.length]);

  const copyLog = useCallback(async () => {
    if (!job) return;
    const text = job.logLines
      .map((line) => `[${formatLogTime(line.ts)}] ${line.level.toUpperCase()}: ${line.message}`)
      .join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access is optional.
    }
  }, [job]);

  if (!job) return <Navigate to="/library" replace />;

  const isRunning = job.status === "running";
  const isComplete = job.status === "completed";
  const isFailed = job.status === "failed";
  const currentStep = STAGE_INDEX[job.stage];

  return (
    <div className="space-y-5">
      <Button
        variant="ghost"
        onClick={() => navigate(isComplete ? "/library" : "/")}
        className="gap-2 text-[var(--color-text-secondary)]"
        disabled={isRunning}
      >
        <ArrowLeft className="w-4 h-4" />
        {isRunning ? "Processing..." : isComplete ? "Back to Library" : "Back to Create"}
      </Button>

      <div>
        <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
          {isComplete ? "Processing complete!" : isFailed ? "Processing failed" : "Processing clips..."}
        </h2>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          {isComplete
            ? "All clips have been processed and saved."
            : `Processing ${job.totalClips} clips with selected enhancements.`}
        </p>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-[var(--color-text-secondary)]">
            Progress {isRunning && job.currentClip > 0 ? `(${job.currentClip}/${job.totalClips})` : ""}
          </span>
          <span className="text-sm text-[var(--color-text-muted)]">{Math.round(job.progress)}%</span>
        </div>
        <Progress value={job.progress} />
      </div>

      <Card className="p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3">Enhancements</h3>
        <div className="space-y-2">
          {STAGES.map((item) => {
            const enabled = item.option
              ? item.option === "addWatermark"
                ? job.options.addWatermark || job.options.addCreditWatermark
                : job.options[item.option]
              : true;
            const isActive = isRunning && currentStep === STAGE_INDEX[item.key];
            const isDone = isComplete || currentStep > STAGE_INDEX[item.key];
            return (
              <div key={item.key} className="flex items-center gap-3">
                {!enabled ? (
                  <span className="w-5 h-5 shrink-0 flex items-center justify-center text-[var(--color-text-muted)] text-xs">-</span>
                ) : isDone ? (
                  <CheckCircle2 className="w-5 h-5 text-[var(--color-success)] shrink-0" />
                ) : isActive ? (
                  <Loader2 className="w-5 h-5 text-[var(--color-accent)] animate-spin shrink-0" />
                ) : (
                  <Loader2 className="w-5 h-5 text-[var(--color-text-muted)] shrink-0 opacity-30" />
                )}
                <span className={`text-sm ${
                  isDone ? "text-[var(--color-success)]"
                    : isActive ? "text-[var(--color-accent)] font-medium"
                    : !enabled ? "text-[var(--color-text-muted)] line-through"
                    : "text-[var(--color-text-muted)]"
                }`}>
                  {item.label}{!enabled ? " (skipped)" : ""}
                </span>
              </div>
            );
          })}
        </div>
      </Card>

      {isFailed && job.error && (
        <div className="flex items-start gap-2 rounded-[var(--radius-sm)] border border-[var(--color-error)]/30 bg-[var(--color-error)]/10 p-3 text-sm text-[var(--color-error)]">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{job.error}</span>
        </div>
      )}

      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--color-border-light)] bg-[var(--color-bg-sidebar)]">
          <span className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wide">Log Output</span>
          <Button variant="ghost" size="sm" onClick={copyLog} disabled={job.logLines.length === 0} className="h-7 gap-1.5 text-xs">
            {copied ? <><Check className="w-3.5 h-3.5 text-[var(--color-success)]" /> Copied</> : <><Copy className="w-3.5 h-3.5" /> Copy</>}
          </Button>
        </div>
        <div className="h-[260px] overflow-y-auto p-3 font-mono text-xs space-y-1 bg-[var(--color-bg-primary)]">
          {job.logLines.map((line, index) => (
            <div key={`${line.ts}-${index}`} className="flex gap-2">
              <span className="text-[var(--color-text-muted)] shrink-0">[{formatLogTime(line.ts)}]</span>
              <span className={line.level === "error" ? "text-[var(--color-error)]" : line.level === "success" ? "text-[var(--color-success)]" : line.level === "warn" ? "text-[var(--color-warning)]" : "text-[var(--color-text-secondary)]"}>{line.message}</span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      </Card>

      {!isRunning && (
        <div className="flex gap-3">
          <Button onClick={() => navigate("/")} variant="outline" className="flex-1">Back to Create</Button>
          <Button onClick={() => navigate("/library")} className="flex-1">{isComplete ? "Go to Library" : "Open Library"}</Button>
        </div>
      )}
    </div>
  );
}
