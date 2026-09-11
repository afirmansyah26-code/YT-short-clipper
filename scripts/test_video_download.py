"""Offline downloader regression tests: python -m unittest discover -s scripts -p test_video_download.py."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yt_dlp
from yt_short_clipper_core import video_processor as vp


class DownloadTests(unittest.TestCase):
    def select(self, formats):
        with yt_dlp.YoutubeDL({
            "format": vp.VIDEO_FORMAT_SELECTOR,
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
                vp._download_section_module("https://example.com/test", "00:00:01", "00:00:02", output, lambda msg: None)
                vp._download_section_module("https://example.com/test", "00:00:02", "00:00:03", output, lambda msg: None)
                self.assertEqual(cut.call_count, 2)
        self.assertEqual(len(options), 2)
        self.assertEqual(options[0]["format"], options[1]["format"])
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

    def test_progress_not_duplicated(self):
        messages = []
        logger = vp._YTDlpLogger(messages.append)
        logger.debug("[download]  27.1% of 288.59MiB")
        logger.debug("[download] Destination: section.mp4")
        self.assertEqual(messages, ["[download] Destination: section.mp4"])


if __name__ == "__main__":
    unittest.main()
