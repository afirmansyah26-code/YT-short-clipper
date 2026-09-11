import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Cpu, Loader2, RefreshCw, Zap, ChevronRight, Folder, FolderOpen, RotateCcw, Sun, Moon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { SettingRow, SettingSection } from "@/components/settings/SettingRow";
import {
  detectGpu,
  getDefaultOutputDir,
  pickOutputFolder,
  openOutputFolder,
  type GpuDetection,
} from "@/hooks/appConfig";
import { useConfigStore } from "@/stores/configStore";
import { useAppStore } from "@/stores/appStore";

export function SettingsPage() {
  const navigate = useNavigate();
  const { theme, toggleTheme } = useAppStore();
  const { config, loaded, load, setGpuAcceleration, setOutputDirectory } = useConfigStore();
  const [detection, setDetection] = useState<GpuDetection | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [defaultDir, setDefaultDir] = useState<string>("");

  useEffect(() => {
    load();
  }, [load]);

  const runDetect = async () => {
    setDetecting(true);
    try {
      const result = await detectGpu();
      setDetection(result);
    } catch (err) {
      console.error("GPU detection failed", err);
      toast.error("GPU detection failed");
    } finally {
      setDetecting(false);
    }
  };

  useEffect(() => {
    runDetect();
    getDefaultOutputDir().then(setDefaultDir).catch(console.error);
  }, []);

  const gpuEnabled = config.gpuAcceleration.enabled;
  const encoderAvailable = detection?.encoder.available ?? false;
  const canToggle = encoderAvailable && !detecting;

  const handleToggle = async (next: boolean) => {
    setSaving(true);
    try {
      await setGpuAcceleration(next);
      toast.success(next ? "GPU acceleration enabled" : "GPU acceleration disabled");
    } catch {
      toast.error("Failed to save setting");
    } finally {
      setSaving(false);
    }
  };

  const customDir = config.outputDirectory || "";

  const handlePickFolder = async () => {
    try {
      const selected = await pickOutputFolder();
      if (selected) {
        await setOutputDirectory(selected);
        toast.success("Output folder updated");
      }
    } catch (err) {
      console.error("Failed to pick folder", err);
      toast.error("Failed to select folder");
    }
  };

  const handleResetFolder = async () => {
    try {
      await setOutputDirectory("");
      toast.success("Output folder reset to default");
    } catch {
      toast.error("Failed to reset folder");
    }
  };

  const handleOpenFolder = async () => {
    try {
      await openOutputFolder();
    } catch (err) {
      console.error("Failed to open folder", err);
      toast.error("Failed to open folder");
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-bold text-[var(--color-text-primary)]">Settings</h1>
        <p className="text-sm text-[var(--color-text-muted)] mt-1">
          Configure performance and output options.
        </p>
      </div>

      <SettingSection
        title="Appearance"
        description="Customize the look and feel of the application."
      >
        <SettingRow
          title="Dark Mode"
          description={
            theme === "dark"
              ? "Dark theme active (comfortable for low-light environments)"
              : "Light theme active"
          }
        >
          <div className="flex items-center gap-2">
            {theme === "dark" ? (
              <Moon className="w-4 h-4 text-blue-400" />
            ) : (
              <Sun className="w-4 h-4 text-amber-500" />
            )}
            <Switch
              checked={theme === "dark"}
              onCheckedChange={toggleTheme}
            />
          </div>
        </SettingRow>
      </SettingSection>

      <SettingSection
        title="GPU Acceleration"
        description="Hardware encoding is 3-5x faster than CPU. Requires a compatible GPU."
      >
        <SettingRow
          title="Detected GPU"
          description={
            detecting
              ? "Detecting..."
              : detection
                ? detection.gpu.available
                  ? `${gpuTypeLabel(detection.gpu.type)} · ${detection.gpu.name}`
                  : "No GPU detected — CPU encoding will be used"
                : "Not checked yet"
          }
        >
          <Button
            variant="outline"
            size="sm"
            onClick={runDetect}
            disabled={detecting}
            className="gap-2"
          >
            {detecting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            Detect
          </Button>
        </SettingRow>

        <SettingRow
          title="Enable GPU acceleration"
          description={
            encoderAvailable
              ? `Encoder: ${detection?.encoder.name}${
                  detection?.encoder.preset ? ` · preset ${detection.encoder.preset}` : ""
                }`
              : detection?.encoder.reason ?? "Run detection to check encoder support"
          }
        >
          <div className="flex items-center gap-2">
            {saving && <Loader2 className="w-4 h-4 animate-spin text-[var(--color-text-muted)]" />}
            <Switch
              checked={gpuEnabled && encoderAvailable}
              onCheckedChange={handleToggle}
              disabled={!canToggle || saving || !loaded}
            />
          </div>
        </SettingRow>

        <SettingRow
          title="Active encoder"
          description="What will be used when processing video."
        >
          <span className="inline-flex items-center gap-2 text-sm font-medium">
            {gpuEnabled && encoderAvailable ? (
              <>
                <Zap className="w-4 h-4 text-[var(--color-success)]" />
                <span className="text-[var(--color-success)]">
                  {detection?.encoder.name}
                </span>
              </>
            ) : (
              <>
                <Cpu className="w-4 h-4 text-[var(--color-text-muted)]" />
                <span className="text-[var(--color-text-secondary)]">libx264 (CPU)</span>
              </>
            )}
          </span>
        </SettingRow>
      </SettingSection>

      <SettingSection
        title="Storage & Output"
        description="Where generated video clips and session data are stored."
      >
        <SettingRow
          title="Output Folder"
          description={
            customDir
              ? customDir
              : defaultDir
                ? `${defaultDir} (Default)`
                : "Default AppData folder"
          }
        >
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handlePickFolder}
              className="gap-2"
            >
              <Folder className="w-4 h-4" />
              {customDir ? "Change..." : "Browse..."}
            </Button>
            {customDir && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleResetFolder}
                className="gap-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                title="Reset to default AppData folder"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={handleOpenFolder}
              className="gap-2"
              title="Open folder in Explorer"
            >
              <FolderOpen className="w-4 h-4" />
              Open
            </Button>
          </div>
        </SettingRow>
      </SettingSection>

      <SettingSection
        title="Output"
        description="Branding and overlays applied to every clip."
      >
        <SettingRow
          title="Watermark"
          description={
            config.watermark.enabled
              ? "Enabled — overlay a logo on each clip"
              : "Add a logo overlay to each clip"
          }
        >
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/settings/watermark")}
            className="gap-2"
          >
            Configure
            <ChevronRight className="w-4 h-4" />
          </Button>
        </SettingRow>

        <SettingRow
          title="Credit Text"
          description={
            config.creditWatermark.enabled
              ? "Enabled — credit overlay on each clip"
              : "Add source channel credit overlay"
          }
        >
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/settings/credit")}
            className="gap-2"
          >
            Configure
            <ChevronRight className="w-4 h-4" />
          </Button>
        </SettingRow>

        <SettingRow
          title="Hook Style"
          description={
            "Font, colors, and shape of the opening hook scene"
          }
        >
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/settings/hook-style")}
            className="gap-2"
          >
            Configure
            <ChevronRight className="w-4 h-4" />
          </Button>
        </SettingRow>
      </SettingSection>

      <SettingSection
        title="Integrations"
        description="Connect external services for publishing your clips."
      >
        <SettingRow
          title="Repliz"
          description={
            config.repliz.accessKey && config.repliz.secretKey
              ? "Connected — upload clips to multiple platforms"
              : "Upload clips to YouTube, TikTok, Instagram, and more"
          }
        >
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/settings/repliz")}
            className="gap-2"
          >
            Configure
            <ChevronRight className="w-4 h-4" />
          </Button>
        </SettingRow>
      </SettingSection>

      <SettingSection
        title="About"
        description="Application information and credits."
      >
        <SettingRow
          title="Open Source Credits"
          description="Libraries and tools used in this application"
        >
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/settings/credits")}
            className="gap-2"
          >
            View
            <ChevronRight className="w-4 h-4" />
          </Button>
        </SettingRow>
      </SettingSection>
    </div>
  );
}

function gpuTypeLabel(type: string | null): string {
  switch (type) {
    case "nvidia":
      return "NVIDIA";
    case "amd":
      return "AMD";
    case "intel":
      return "Intel";
    case "apple":
      return "Apple";
    default:
      return "GPU";
  }
}
