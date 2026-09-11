"""Offline downloader regression tests: python -m unittest discover -s scripts -p test_video_download.py."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yt_dlp
from yt_short_clipper_core import video_processor as vp


class DownloadTests(unittest.TestCase):
    def select(self, formats, quality="auto"):
        with yt_dlp.YoutubeDL({
            "format": vp._quality_selector(quality),
            "format_sort": vp.VIDEO_FORMAT_SORT,
            "format_sort_force": True,
            "quiet": True,
        }) as ydl:
            return ydl.process_ie_result({
                "id": "test", "title": "Test", "extractor": "test",
                "formats": formats,
            }, download=False)

    def video(self, height, codec="avc1", audio="none"):
        return {"format_id": f"{height}-{codec}", "url": "https://example.com/video",
                "height": height, "width": height * 16 // 9, "vcodec": codec,
                "acodec": audio, "ext": "mp4"}

    def audio(self):
        return {"format_id": "audio", "url": "https://example.com/audio",
                "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a"}

    def test_resolution_beats_codec_preference(self):
        result = self.select([self.video(360), self.video(1080, "vp9"), self.audio()])
        self.assertEqual(result["height"], 1080)

    def test_cap_and_audio(self):
        result = self.select([self.video(720), self.video(1080), self.video(2160), self.audio()])
        self.assertEqual(result["height"], 1080)
        self.assertEqual(len(result["requested_formats"]), 2)

    def test_lower_quality_when_only_available(self):
        self.assertEqual(self.select([self.video(360, audio="mp4a")])["height"], 360)

    def test_fallback_retains_quality_and_reuses_source(self):
        options = []
        class FakeDL:
            def __init__(self, opts):
                self.opts = opts
                options.append(opts)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def download(self, urls):
                if "download_ranges" in self.opts:
                    raise RuntimeError("ffmpeg exited with code 1")
                Path(self.opts["outtmpl"]).write_bytes(b"mock source")
        with tempfile.TemporaryDirectory() as tmp:
            output = str(Path(tmp) / "section.mp4")
            with patch.object(vp, "_setup_ytdlp_env"), patch.object(vp, "get_ffmpeg_path", return_value=__file__), patch.object(vp, "get_deno_path", return_value=None), patch.object(vp, "_get_cookies_path", return_value="cookies.txt"), patch.object(vp, "_cut_local_section", return_value=output) as cut, patch.object(yt_dlp, "YoutubeDL", FakeDL):
                vp._download_section_module("https://example.com/test", "00:00:01", "00:00:02", output, lambda msg: None, source_quality="720")
                vp._download_section_module("https://example.com/test", "00:00:02", "00:00:03", output, lambda msg: None, source_quality="720")
                self.assertEqual(cut.call_count, 2)
        self.assertEqual(len(options), 2)
        self.assertEqual(options[0]["format"], options[1]["format"])
        self.assertEqual(options[1]["format"], vp._quality_selector("720"))
        self.assertNotIn("force_keyframes_at_cuts", options[1])
        self.assertNotIn("download_ranges", options[1])

    def test_batch_download_skips_remote_ranges_and_reuses_cache(self):
        options = []
        class FakeDL:
            def __init__(self, opts):
                self.opts = opts
                options.append(opts)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def download(self, urls):
                Path(self.opts["outtmpl"]).write_bytes(b"mock source")
        with tempfile.TemporaryDirectory() as tmp:
            output = str(Path(tmp) / "section.mp4")
            with patch.object(vp, "_setup_ytdlp_env"), patch.object(vp, "get_ffmpeg_path", return_value=__file__), patch.object(vp, "get_deno_path", return_value=None), patch.object(vp, "_get_cookies_path", return_value="cookies.txt"), patch.object(vp, "_cut_local_section", return_value=output) as cut, patch.object(yt_dlp, "YoutubeDL", FakeDL):
                for start in ("00:00:01", "00:00:02"):
                    vp._download_section_module("https://example.com/test", start, "00:00:03", output, lambda msg: None, prefer_cached_source=True)
                self.assertEqual(cut.call_count, 2)
        self.assertEqual(len(options), 1)
        self.assertNotIn("download_ranges", options[0])
        self.assertNotIn("force_keyframes_at_cuts", options[0])
        self.assertEqual(options[0]["format"], vp.VIDEO_FORMAT_SELECTOR)

    def test_explicit_quality_uses_exact_resolution(self):
        formats = [self.video(360), self.video(720), self.video(1080), self.audio()]
        for height in (360, 720, 1080):
            with self.subTest(height=height):
                self.assertEqual(self.select(formats, str(height))["height"], height)

    def test_missing_explicit_quality_does_not_downgrade(self):
        with self.assertRaises(yt_dlp.utils.ExtractorError):
            self.select([self.video(360), self.audio()], "720")

    def test_quality_cache_isolation(self):
        paths = {vp._source_cache_path("url", "clip.mp4", q) for q in ("auto", "360", "720", "1080")}
        self.assertEqual(len(paths), 4)
        # Legacy _source_1080 caches were capped, and might actually contain 720p.
        self.assertTrue(all(path.name.startswith("_source_quality_") for path in paths))

    def test_invalid_quality_rejected(self):
        for value in ("best", "720/1080", "2160", "0", "", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                vp._quality_selector(value)

    def test_metadata_filters_non_downloadable_resolutions(self):
        drm = dict(self.video(480), has_drm=True)
        self.assertEqual(vp._available_heights({"formats": [self.video(360), self.video(720), self.video(720, "vp9"), self.video(2160), self.audio(), drm]}), [720, 360])
        self.assertEqual(vp._available_heights({"formats": [self.video(720)]}), [])
        self.assertEqual(vp._available_heights({"formats": [self.video(360, audio="mp4a")]}), [360])

    def test_metadata_extraction_does_not_download(self):
        from unittest.mock import MagicMock
        fake = MagicMock()
        fake.__enter__.return_value = fake
        fake.extract_info.return_value = {"formats": [self.video(720), self.audio()]}
        with patch.object(vp, "_setup_ytdlp_env"), patch.object(vp, "get_deno_path", return_value=None), patch.object(vp, "_get_cookies_path", return_value="cookies.txt"), patch.object(yt_dlp, "YoutubeDL", return_value=fake):
            self.assertEqual(vp.get_video_qualities("test-url"), {"heights": [720]})
        fake.extract_info.assert_called_once_with("test-url", download=False)
        fake.download.assert_not_called()

    def test_progress_not_duplicated(self):
        messages = []
        logger = vp._YTDlpLogger(messages.append)
        logger.debug("[download]  27.1% of 288.59MiB")
        logger.debug("[download] Destination: section.mp4")
        self.assertEqual(messages, ["[download] Destination: section.mp4"])

    def test_local_cut_is_frame_accurate_across_long_gop(self):
        ffmpeg = Path(vp.get_ffmpeg_path())
        if not ffmpeg.is_file():
            self.skipTest("Bundled ffmpeg is not available")

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "long-gop-source.mp4"
            output = Path(tmp) / "section.mp4"

            # The only keyframe is at the beginning. Red covers 0-3 seconds;
            # blue covers 3-6 seconds. A stream-copy cut at 3.5 seconds starts
            # on red and lasts much longer than requested because it retains
            # the keyframe preroll.
            subprocess.run([
                str(ffmpeg), "-v", "error", "-y",
                "-f", "lavfi", "-i",
                "color=c=red:s=64x64:r=10:d=6,"
                "drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable='gte(t,3)'",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
                "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-g", "100", "-keyint_min", "100",
                "-sc_threshold", "0", "-pix_fmt", "yuv420p",
                "-c:a", "aac", str(source),
            ], check=True, capture_output=True, timeout=30)

            vp._cut_local_section(
                str(source), str(output), "00:00:03.500", "00:00:04.500", str(ffmpeg)
            )

            probe = subprocess.run([
                str(ffmpeg), "-hide_banner", "-i", str(output),
                "-vf", "signalstats,metadata=print", "-frames:v", "1",
                "-f", "null", "-",
            ], capture_output=True, text=True, timeout=30)
            diagnostic = probe.stderr

            duration_match = re.search(r"Duration: 00:00:(\d+(?:\.\d+)?)", diagnostic)
            self.assertIsNotNone(duration_match, diagnostic)
            self.assertAlmostEqual(float(duration_match.group(1)), 1.0, delta=0.08)

            vavg_match = re.search(r"lavfi\.signalstats\.VAVG=([\d.]+)", diagnostic)
            self.assertIsNotNone(vavg_match, diagnostic)
            # Blue has V around 110; the unwanted red preroll has V around 240.
            self.assertLess(float(vavg_match.group(1)), 150.0)

if __name__ == "__main__":
    unittest.main()
