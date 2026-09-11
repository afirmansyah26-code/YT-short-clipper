"""Watermark overlay: logo image and/or credit text burned into video."""

import os
import shutil
import tempfile
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .helpers import get_ffmpeg_path, _get_app_dir

LogFn = Callable[[str], None]

_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _credit_font_path() -> Path:
    """Use a concrete font file; bundled Windows FFmpeg has no Fontconfig setup."""
    app_dir = _get_app_dir()
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf",
        app_dir / "fonts/Barlow Condensed SemiBold.ttf",
        app_dir.parent / "fonts/Barlow Condensed SemiBold.ttf",
        Path(__file__).resolve().parent.parent / "src-tauri/fonts/Barlow Condensed SemiBold.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Credit watermark font not found. Please restore the bundled fonts.")


def apply_watermark(
    input_video_path: str,
    output_path: str,
    watermark: dict[str, Any] | None = None,
    credit_watermark: dict[str, Any] | None = None,
    log: LogFn | None = None,
) -> str:
    """Apply logo watermark and/or credit text overlay to video.

    watermark keys: image_path, position_x, position_y, opacity, scale
    credit_watermark keys: text, color, font_size, opacity, position_x, position_y

    Returns the output path.
    """
    log = log or (lambda m: None)
    ffmpeg_path = str(Path(get_ffmpeg_path()).resolve())
    input_video_path = str(Path(input_video_path).resolve())
    output_path = str(Path(output_path).resolve())

    has_logo = watermark and watermark.get("image_path") and Path(watermark["image_path"]).exists()
    has_credit = credit_watermark and credit_watermark.get("text")

    if not has_logo and not has_credit:
        log("No watermark configured, skipping")
        shutil.copy2(input_video_path, output_path)
        return output_path

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="watermark-", dir=Path(output_path).parent) as work_dir:
        # Build ffmpeg filter chain
        inputs = ["-i", input_video_path]
        filter_parts = []

        if has_logo:
            logo_path = str(Path(watermark["image_path"]).resolve())
            pos_x = watermark.get("position_x", 0.85)
            pos_y = watermark.get("position_y", 0.05)
            opacity = watermark.get("opacity", 0.8)
            scale = watermark.get("scale", 0.15)

            inputs.extend(["-i", logo_path])

            # Scale logo relative to video width, position as fraction of video dimensions
            logo_filter = (
                f"[1:v]format=rgba,colorchannelmixer=aa={opacity},"
                f"scale=iw*{scale}:-1[logo];"
                f"[0:v][logo]overlay="
                f"W*{pos_x}-overlay_w/2:H*{pos_y}-overlay_h/2"
            )

            if has_credit:
                logo_filter += "[watermarked]"
                filter_parts.append(logo_filter)
            else:
                filter_parts.append(logo_filter)

        if has_credit:
            text = credit_watermark["text"]
            color = credit_watermark.get("color", "#FFFFFF")
            font_size = credit_watermark.get("font_size", 24)
            opacity = credit_watermark.get("opacity", 0.7)
            pos_x = credit_watermark.get("position_x", 0.03)
            pos_y = credit_watermark.get("position_y", 0.92)

            # Convert hex color to ffmpeg format (remove #)
            ff_color = color.lstrip("#")

            # Calculate alpha as hex
            alpha_hex = format(int(opacity * 255), "02x")

            # Files with fixed relative names avoid Windows drive-letter escaping.
            # expansion=none keeps percent signs and %{...} in credits literal.
            shutil.copyfile(_credit_font_path(), Path(work_dir) / "credit-font.ttf")
            (Path(work_dir) / "credit.txt").write_text(text, encoding="utf-8")

            if has_logo:
                # Chain after logo overlay
                credit_filter = (
                    f"[watermarked]drawtext="
                    "fontfile=credit-font.ttf:textfile=credit.txt:expansion=none:"
                    f"fontsize={font_size}:"
                    f"fontcolor=0x{ff_color}{alpha_hex}:"
                    f"x=w*{pos_x}:y=h*{pos_y}:"
                    f"shadowcolor=black@0.5:shadowx=1:shadowy=1"
                )
            else:
                # Apply directly to input
                credit_filter = (
                    f"[0:v]drawtext="
                    "fontfile=credit-font.ttf:textfile=credit.txt:expansion=none:"
                    f"fontsize={font_size}:"
                    f"fontcolor=0x{ff_color}{alpha_hex}:"
                    f"x=w*{pos_x}:y=h*{pos_y}:"
                    f"shadowcolor=black@0.5:shadowx=1:shadowy=1"
                )
            filter_parts.append(credit_filter)

        filter_complex = ";".join(filter_parts)

        log("Applying watermark overlay...")
        cmd = [
            ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_SUBPROCESS_FLAGS, cwd=work_dir, encoding="utf-8", errors="replace")

        if result.returncode != 0:
            raise RuntimeError(f"Watermark overlay failed (exit {result.returncode}): {result.stderr[-2000:]}")

        log("Watermark overlay complete")
        return output_path
