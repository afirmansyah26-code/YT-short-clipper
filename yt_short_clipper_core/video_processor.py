"""Download video sections from YouTube via yt-dlp."""

import hashlib
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .cookies import validate_cookies
from .helpers import debug_log, get_deno_path, get_ffmpeg_path, is_ytdlp_module_available
from .helpers import _get_app_dir

LogFn = Callable[[str], None]

FFMPEG_NO_DATA_TIMEOUT_SECONDS = 30
DOWNLOAD_HEARTBEAT_POLL_SECONDS = 5
DOWNLOAD_HEARTBEAT_LOG_SECONDS = 15

# Rank resolution before codec and transport so lower-resolution AVC cannot
# hide an available 1080p stream in another codec.
VIDEO_FORMAT_SELECTOR = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
VIDEO_FORMAT_SORT = ["res", "vcodec:h264", "proto", "br"]


def _quality_selector(quality: str) -> str:
    if quality == "auto":
        return VIDEO_FORMAT_SELECTOR
    if not isinstance(quality, str) or not quality.isdecimal() or not 1 <= int(quality) <= 1080:
        raise ValueError("Invalid source video quality")
    # An explicit selection must never silently switch resolution.
    height = int(quality)
    return f"bestvideo[height={height}]+bestaudio/best[height={height}]"


def _available_heights(info: dict) -> list[int]:
    formats = info.get("formats") or []
    has_audio = any(f.get("acodec") not in (None, "none") and f.get("vcodec") == "none"
                    and f.get("url") and not f.get("has_drm") for f in formats)
    return sorted({int(f["height"]) for f in formats
                   if isinstance(f.get("height"), (int, float)) and 0 < f["height"] <= 1080
                   and f.get("vcodec") not in (None, "none") and f.get("url")
                   and not f.get("has_drm")
                   and (f.get("acodec") not in (None, "none") or has_audio)}, reverse=True)


def get_video_qualities(url: str) -> dict:
    """Inspect available source resolutions without downloading media."""
    import yt_dlp
    _setup_ytdlp_env()
    opts = {"cookiefile": _get_cookies_path(), "quiet": True, "noplaylist": True,
            "skip_download": True, "socket_timeout": 20, "retries": 2,
            "logger": _YTDlpLogger(debug_log)}
    deno = get_deno_path()
    if deno and Path(deno).exists():
        opts.update(js_runtimes={"deno": {"path": deno}}, remote_components=["ejs:github"])
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    heights = _available_heights(info or {})
    if not heights:
        raise RuntimeError("No downloadable video quality up to 1080p was found. Refresh the available qualities.")
    return {"heights": heights}


def _parse_timestamp(ts: str) -> float:
    """Convert timestamp HH:MM:SS,mmm or HH:MM:SS.mmm to seconds."""
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def _find_downloaded_file(output_path: str) -> str:
    """yt-dlp may change the extension; find the actual file."""
    if Path(output_path).exists():
        return output_path
    output_dir = Path(output_path).parent
    output_stem = Path(output_path).stem
    mp4 = output_dir / f"{output_stem}.mp4"
    if mp4.exists():
        return str(mp4)
    candidates = [
        c for c in output_dir.glob(f"{output_stem}.*")
        if c.suffix in (".mp4", ".mkv", ".webm")
    ]
    if candidates:
        return str(candidates[0])
    raise RuntimeError(f"Downloaded section file not found: {output_path}")


def _source_cache_path(url: str, output_path: str, quality: str = "auto") -> Path:
    """Return a stable per-video cache path inside the session temp folder."""
    _quality_selector(quality)
    cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return Path(output_path).parent / f"_source_quality_{quality}_{cache_key}.mp4"


def _find_cached_source(cache_path: Path) -> str | None:
    # yt-dlp may use another final container, but temporary per-format files
    # such as ``.f136.mp4`` must never be mistaken for a complete cache.
    for suffix in (".mp4", ".mkv", ".webm"):
        candidate = cache_path.with_suffix(suffix)
        try:
            if candidate.is_file() and candidate.stat().st_size > 0:
                return str(candidate)
        except OSError:
            continue
    return None


def _cut_local_section(
    source_path: str,
    output_path: str,
    start_time: str,
    end_time: str,
    ffmpeg_path: str,
) -> str:
    """Cut one section at the requested timestamps and reset its timeline.

    Stream-copying after an input seek can preserve media from the previous
    keyframe. Captions are timed from the exact highlight start, so that
    extra media makes the captions appear before the matching speech. Decode
    and encode the selected section so FFmpeg can discard the keyframe
    preroll, then reset video and audio timestamps to zero.
    """
    import subprocess
    import sys

    duration = _parse_timestamp(end_time) - _parse_timestamp(start_time)
    if duration <= 0:
        raise RuntimeError("Clip end time must be after its start time")

    cut_output = f"{output_path}.cut.mp4"
    cut_cmd = [
        str(ffmpeg_path), "-y",
        "-ss", start_time,
        "-i", source_path,
        "-t", f"{duration:.3f}",
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-vf", "setpts=PTS-STARTPTS",
        "-af", "asetpts=PTS-STARTPTS",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        cut_output,
    ]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        result = subprocess.run(
            cut_cmd,
            capture_output=True,
            text=True,
            creationflags=flags,
            timeout=max(120, int(duration * 3)),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Timed out while cutting the cached source video") from exc
    if result.returncode != 0:
        raise RuntimeError(f"Failed to cut video section with ffmpeg: {result.stderr[:500]}")
    os.replace(cut_output, output_path)
    return output_path


def _setup_ytdlp_env() -> None:
    """Ensure Deno is in PATH for yt-dlp remote components."""
    deno_path = get_deno_path()
    if deno_path and Path(deno_path).exists():
        deno_dir = str(Path(deno_path).parent)
        os.environ["PATH"] = f"{deno_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def _extract_progress(d: dict) -> tuple[str | None, str]:
    """Normalize a yt-dlp progress dict into ``(percent, detail)``.

    yt-dlp only fills ``_percent_str`` for some transports. For DASH/range
    downloads (e.g. ``271+140``) it's usually empty, so we compute the
    percentage ourselves from the raw byte counters, then fall back to
    fragment counts (HLS/DASH manifests). ``percent`` is a bare number string
    without the ``%`` sign, or ``None`` if nothing usable is available.
    """
    pct: str | None = None

    # 1) yt-dlp's own formatted percent, when present
    raw_pct = (d.get("_percent_str") or "").strip()
    match = re.search(r"(\d+\.?\d*)%", raw_pct)
    if match:
        pct = match.group(1)
    else:
        # 2) compute from raw byte counters (total may only be an estimate)
        downloaded = d.get("downloaded_bytes")
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total > 0:
            pct = f"{min(100.0, downloaded / total * 100):.1f}"
        else:
            # 3) fall back to fragment progress for segmented downloads
            frag_i = d.get("fragment_index")
            frag_n = d.get("fragment_count")
            if isinstance(frag_i, (int, float)) and isinstance(frag_n, (int, float)) and frag_n > 0:
                pct = f"{frag_i / frag_n * 100:.0f}"

    downloaded_str = d.get("_downloaded_bytes_str") or d.get("downloaded_bytes")
    speed = d.get("_speed_str") or d.get("speed")
    eta = d.get("_eta_str") or d.get("eta")
    parts = []
    if downloaded_str:
        parts.append(f"{downloaded_str}")
    if speed:
        parts.append(f"@ {speed}")
    if eta is not None:
        parts.append(f"eta {eta}")
    detail = " ".join(str(p) for p in parts)
    return pct, detail


def _yt_dlp_progress_hook(d: dict, log: LogFn) -> None:
    """Report yt-dlp download progress.

    yt-dlp's progress dict uses different keys depending on the transport
    (direct HTTP, HLS fragments, DASH). ``_percent_str`` can be empty during
    the first fragment or when the total size is unknown — in that case we
    compute the percentage from raw counters (see ``_extract_progress``) and,
    failing that, surface bytes downloaded and speed instead of staying silent
    (silent = looks like a hang to the user).
    """
    status = d.get("status")
    if status == "downloading":
        pct, detail = _extract_progress(d)
        if pct is not None:
            suffix = f" ({detail})" if detail else ""
            log(f"Download progress: {pct}%{suffix}")
        elif detail:
            log(f"Download progress: {detail}")
        else:
            log("Download progress: starting...")
    elif status == "finished":
        total = d.get("_total_bytes_str") or d.get("total_bytes") or ""
        elapsed = d.get("_elapsed_str") or d.get("elapsed") or ""
        tail = f" ({total}, {elapsed})" if (total or elapsed) else ""
        log(f"Download complete, merging...{tail}")


class _YTDlpLogger:
    """Forward yt-dlp's own log lines to our sidecar log fn.

    yt-dlp emits a lot of useful messages (extractor selection, format
    probing, fragment retries, 403s, merge steps) that are silenced by
    ``quiet: True``. Passing an instance of this class via ``ydl_opts[
    "logger"]`` surfaces info/warning/error lines so the user can see what
    yt-dlp is actually doing while a section download is in flight — instead
    of a silent hang at "FFmpeg path resolved: ...".
    """

    def __init__(self, log: LogFn) -> None:
        self._log = log

    def debug(self, msg: str) -> None:
        # Hooks report progress; preserve destination, retry and merge logs.
        if re.match(r"\[download\]\s+\d+(?:\.\d+)?%", msg):
            return
        # yt-dlp's debug channel is extremely noisy (per-fragment bytes),
        # so we only surface the lines that hint at *what* yt-dlp is doing
        # right now, not the byte counters.
        if any(k in msg for k in ("Downloading ", "Downloading item ", "[download]", "Extracting", "Downloading fragment", "Resuming", "Merging", "Deleting")):
            self._log(msg)

    def info(self, msg: str) -> None:
        self._log(msg)

    def warning(self, msg: str) -> None:
        self._log(f"⚠️ {msg}")

    def error(self, msg: str) -> None:
        self._log(f"❌ {msg}")


def _get_cookies_path() -> str:
    """Find cookies.txt in cwd, app dir, or Tauri app data dir."""
    app_dir = _get_app_dir()
    for loc in [Path("cookies.txt"), app_dir / "cookies.txt"]:
        if loc.exists():
            return str(loc)
    # Tauri app data dir
    try:
        import platform
        if platform.system() == "Windows":
            data_dir = Path(os.environ.get("APPDATA", ""))
        elif platform.system() == "Darwin":
            data_dir = Path.home() / "Library" / "Application Support"
        else:
            data_dir = Path.home() / ".config"
        app_data = data_dir / "com.jipraks.ytshortclipper-v2"
        ck = app_data / "cookies.txt"
        if ck.exists():
            return str(ck)
    except Exception:
        pass
    raise RuntimeError("cookies.txt not found. Please upload cookies first.")


def download_video_section(
    url: str,
    start_time: str,
    end_time: str,
    output_path: str,
    log: LogFn | None = None,
    prefer_cached_source: bool = False,
    source_quality: str = "auto",
) -> str:
    """Download a specific section of a YouTube video.

    Returns path to the downloaded file.
    """
    log = log or debug_log
    start_clean = start_time.replace(",", ".")
    end_clean = end_time.replace(",", ".")

    if is_ytdlp_module_available():
        return _download_section_module(url, start_clean, end_clean, output_path, log, prefer_cached_source, source_quality)
    else:
        raise RuntimeError(
            "yt-dlp Python module is required for downloading video sections. "
            "Install it with: pip install yt-dlp"
        )


def _download_section_module(
    url: str,
    start_time: str,
    end_time: str,
    output_path: str,
    log: LogFn,
    prefer_cached_source: bool = False,
    source_quality: str = "auto",
) -> str:
    import yt_dlp

    format_selector = _quality_selector(source_quality)
    quality_label = "best available quality up to 1080p" if source_quality == "auto" else f"{source_quality}p"
    log(f"Source video quality: {quality_label}")
    log(f"Downloading section {start_time} -> {end_time}...")

    _setup_ytdlp_env()
    ffmpeg_path = get_ffmpeg_path()
    cookies_path = _get_cookies_path()

    ydl_opts: dict[str, Any] = {
        "format": format_selector,
        "noplaylist": True,
        "format_sort": VIDEO_FORMAT_SORT,
        "format_sort_force": True,
        "merge_output_format": "mp4",
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": False,
        "hls_prefer_native": True,
        "concurrent_fragment_downloads": 1,
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
        # download_ranges delegates the transfer to FFmpeg. The Python API
        # only reads external_downloader_args; "downloader_args" is ignored.
        "external_downloader_args": {
            "ffmpeg_i": [
                # Never let a dead Googlevideo connection block a batch
                # forever. FFmpeg expects rw_timeout in microseconds.
                "-rw_timeout", "15000000",
                "-reconnect", "1",
                "-reconnect_on_network_error", "1",
                "-reconnect_on_http_error", "429,5xx",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
                "-reconnect_max_retries", "3",
                "-reconnect_delay_total_max", "15",
            ]
        },
        "download_ranges": yt_dlp.utils.download_range_func(
            None, [(_parse_timestamp(start_time), _parse_timestamp(end_time))]
        ),
        "force_keyframes_at_cuts": True,
        "cookiefile": cookies_path,
        "logger": _YTDlpLogger(log),
        "progress_hooks": [
            lambda d: _yt_dlp_progress_hook(d, log)
        ],
    }

    deno_path = get_deno_path()
    if deno_path and Path(deno_path).exists():
        ydl_opts["js_runtimes"] = {"deno": {"path": deno_path}}
        ydl_opts["remote_components"] = ["ejs:github"]

    if ffmpeg_path and Path(ffmpeg_path).exists():
        ffmpeg_dir = str(Path(ffmpeg_path).parent)
        ydl_opts["ffmpeg_location"] = ffmpeg_dir
        os.environ["PATH"] = f"{ffmpeg_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        log(f"FFmpeg path resolved: {ffmpeg_path}")
    else:
        raise RuntimeError(
            f"FFmpeg is required for downloading video sections but was not found. "
            f"Last path checked: {ffmpeg_path!r}. "
            "Please ensure ffmpeg is bundled with the app (ffmpeg/ffmpeg.exe next to "
            "the sidecar) or installed on the system PATH."
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    source_cache = _source_cache_path(url, output_path, source_quality)
    cached_source = _find_cached_source(source_cache)
    if cached_source:
        log("Using the session's cached source video for this clip...")
        return _cut_local_section(
            cached_source, output_path, start_time, end_time, str(ffmpeg_path)
        )

    def download_cached_source() -> str:
        source_opts = dict(ydl_opts)
        source_opts.pop("download_ranges", None)
        source_opts.pop("force_keyframes_at_cuts", None)
        source_opts["outtmpl"] = str(source_cache)
        last_progress = float("-inf")

        def source_progress(d: dict) -> None:
            nonlocal last_progress
            now = time.monotonic()
            if d.get("status") != "downloading" or now - last_progress >= 1:
                _yt_dlp_progress_hook(d, log)
                last_progress = now

        source_opts["progress_hooks"] = [source_progress]
        try:
            with yt_dlp.YoutubeDL(source_opts) as ydl:
                ydl.download([url])
        except Exception as exc:
            raise RuntimeError(f"Failed to download source video at {quality_label}. Refresh available qualities if the selected resolution is no longer available. {exc}") from exc
        full_path = _find_cached_source(source_cache)
        if not full_path:
            raise RuntimeError("Source download finished but its file was not found")
        log("Cutting downloaded video to requested section...")
        return _cut_local_section(full_path, output_path, start_time, end_time, str(ffmpeg_path))

    if prefer_cached_source:
        log(f"Batch download: downloading a reusable source at {quality_label}...")
        return download_cached_source()

    # A force-killed FFmpeg leaves this temporary file behind. It is never a
    # completed clip, so do not let a later retry inherit it.
    part_path = Path(f"{output_path}.part")
    try:
        part_path.unlink(missing_ok=True)
    except OSError as exc:
        log(f"Could not remove stale partial download: {exc}")

    download_state = {
        "last_log_ts": time.monotonic(),
        "last_progress_log_ts": float("-inf"),
        "last_pct": None,
        "last_detail": "",
        "ffmpeg_proc": None,
        "ffmpeg_started_ts": None,
        "last_part_size": 0,
        "last_part_growth_ts": None,
    }

    def _hook_with_heartbeat(d: dict) -> None:
        # Update heartbeat timestamp whenever yt-dlp reports activity
        download_state["last_log_ts"] = time.monotonic()
        if d.get("status") == "downloading":
            pct, detail = _extract_progress(d)
            if pct is not None:
                download_state["last_pct"] = pct
            if detail:
                download_state["last_detail"] = detail
        now = time.monotonic()
        if d.get("status") != "downloading" or now - download_state["last_progress_log_ts"] >= 1:
            _yt_dlp_progress_hook(d, log)
            download_state["last_progress_log_ts"] = now

    ydl_opts["progress_hooks"] = [_hook_with_heartbeat]

    stop_evt = threading.Event()

    def heartbeat() -> None:
        started = time.monotonic()
        next_log = started + DOWNLOAD_HEARTBEAT_LOG_SECONDS
        while not stop_evt.wait(DOWNLOAD_HEARTBEAT_POLL_SECONDS):
            now = time.monotonic()
            try:
                part_size = part_path.stat().st_size
            except OSError:
                part_size = 0

            if part_size > download_state["last_part_size"]:
                download_state["last_part_size"] = part_size
                download_state["last_part_growth_ts"] = now
                download_state["last_log_ts"] = now

            proc = download_state["ffmpeg_proc"]
            last_growth = download_state["last_part_growth_ts"]
            if (
                proc is not None
                and last_growth is not None
                and proc.poll() is None
                and now - last_growth >= FFMPEG_NO_DATA_TIMEOUT_SECONDS
            ):
                log(
                    "Download stalled: FFmpeg produced no output data for "
                    f"{FFMPEG_NO_DATA_TIMEOUT_SECONDS}s. Stopping this attempt..."
                )
                try:
                    proc.kill(timeout=5)
                except Exception as exc:
                    log(f"Could not stop stalled FFmpeg cleanly: {exc}")
                return

            if now < next_log:
                continue
            next_log = now + DOWNLOAD_HEARTBEAT_LOG_SECONDS
            elapsed = int(now - started)
            since_last_log = int(now - download_state["last_log_ts"])
            pct = download_state["last_pct"]
            detail = download_state["last_detail"]
            if pct is not None:
                log(f"⏳ Still downloading: {pct}% ({detail}), {elapsed}s elapsed")
            elif detail:
                log(f"⏳ Still downloading: {detail}, {elapsed}s elapsed (no progress % yet)")
            else:
                log(
                    f"⏳ Still waiting for download data... {elapsed}s elapsed, "
                    f"{since_last_log}s since last activity"
                )

    hb_thread = threading.Thread(target=heartbeat, daemon=True, name="yt-dlp-heartbeat")
    hb_thread.start()

    # yt-dlp does not expose a process callback for normal file outputs. Track
    # its FFmpeg Popen locally so the heartbeat can terminate a no-data stall.
    from yt_dlp.downloader import external as ytdlp_external
    original_external_popen = ytdlp_external.Popen

    def tracked_external_popen(*args: Any, **kwargs: Any) -> Any:
        proc = original_external_popen(*args, **kwargs)
        now = time.monotonic()
        download_state["ffmpeg_proc"] = proc
        download_state["ffmpeg_started_ts"] = now
        download_state["last_part_growth_ts"] = now
        try:
            download_state["last_part_size"] = part_path.stat().st_size
        except OSError:
            download_state["last_part_size"] = 0
        return proc

    ytdlp_external.Popen = tracked_external_popen

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        msg = str(e)
        log(f"Section download failed: {msg[:200]}")
        if "403" in msg or "Forbidden" in msg:
            raise RuntimeError(
                "YouTube rejected access (HTTP 403). Your cookies may have expired. "
                "Please export fresh cookies while logged into YouTube."
            )

        # FFmpeg cannot read some Googlevideo URLs even though yt-dlp's native
        # HTTP downloader can. Download one capped source file, cache it for
        # the session, then cut all requested clips from that local file.
        if "ffmpeg" in msg.lower():
            # The ranged-file watchdog must not monitor the full-source retry.
            stop_evt.set()
            hb_thread.join(timeout=2)
            ytdlp_external.Popen = original_external_popen
            log(f"Ranged download failed; downloading a reusable source at {quality_label}...")
            return download_cached_source()

        raise RuntimeError(f"Failed to download video section at {quality_label}. Refresh available qualities if the selected resolution is no longer available. {msg}")
    finally:
        ytdlp_external.Popen = original_external_popen
        stop_evt.set()
        hb_thread.join(timeout=2)

    return _find_downloaded_file(output_path)
