"""Integration tests using the project's real FFmpeg binary."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from yt_short_clipper_core import watermark as wm


class WatermarkTests(unittest.TestCase):
    def test_real_ffmpeg_overlays_without_fontconfig(self):
        ffmpeg = str(Path(wm.get_ffmpeg_path()).resolve())
        with tempfile.TemporaryDirectory(prefix="watermark test's ") as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            logo = root / "logo.png"
            Image.new("RGBA", (80, 80), (255, 0, 0, 255)).save(logo)
            subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=320x240:r=10:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:v", "libx264", "-c:a", "aac", str(source)], check=True, capture_output=True, timeout=30)
            credit = {"text": "Pandu's: 100% [OK]; %{literal}\nKredit", "font_size": 16, "position_y": 0.5}
            logo_config = {"image_path": str(logo), "scale": 0.5, "position_y": 0.2}
            with patch.dict(os.environ, {"FONTCONFIG_FILE": str(root / "missing.conf")}):
                for mode, logo_opts, credit_opts in (("credit", None, credit), ("logo", logo_config, None), ("both", logo_config, credit), ("none", None, None)):
                    with self.subTest(mode=mode):
                        output = root / f"{mode}.mp4"
                        wm.apply_watermark(str(source), str(output), logo_opts, credit_opts)
                        # Decode to prove both video and audio survive, not just file creation.
                        subprocess.run([ffmpeg, "-v", "error", "-i", str(output), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"], check=True, capture_output=True, timeout=30)
                        frame = subprocess.run([ffmpeg, "-v", "error", "-i", str(output), "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], check=True, capture_output=True, timeout=30).stdout
                        self.assertEqual(len(frame), 320 * 240 * 3)
                        if mode != "none":
                            self.assertGreater(sum(frame), 10000)
                self.assertEqual(list(root.glob("watermark-*")), [])


if __name__ == "__main__":
    unittest.main()
