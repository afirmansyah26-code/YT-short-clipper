"""Clip processing regression tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yt_short_clipper_core import clip_processor as cp


class ClipProcessorTests(unittest.TestCase):
    def test_loads_and_resolves_channel_template_without_mutating_config(self):
        messages = []
        config = {"text": "Source: {channel}", "font_size": 24}
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "session_data.json").write_text(
                json.dumps({"video_info": {"channel": "Raditya Dika"}}), encoding="utf-8"
            )
            channel = cp._load_video_channel(Path(tmp), messages.append)
        resolved = cp._resolve_credit_watermark(config, channel, messages.append)
        self.assertEqual(resolved["text"], "Source: Raditya Dika")
        self.assertEqual(config["text"], "Source: {channel}")
        self.assertIn("Credit watermark channel: Raditya Dika", messages)

    def test_missing_channel_never_leaves_literal_placeholder(self):
        resolved = cp._resolve_credit_watermark(
            {"text": "Source: {channel}"}, "", lambda message: None
        )
        self.assertEqual(resolved["text"], "Source: Unknown channel")

    def test_single_clip_uses_cached_source_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "session_data.json").write_text(
                json.dumps({"video_info": {"channel": "Channel"}}), encoding="utf-8"
            )
            source = root / "source.mp4"
            source.write_bytes(b"video")
            highlights = [{
                "start_time": "00:00:01,000", "end_time": "00:00:02,000",
                "title": "Test", "description": "", "duration_seconds": 1,
                "_highlight_index": 0,
            }]
            with patch.object(cp, "download_video_section", return_value=str(source)) as download, patch.object(cp, "_run_portrait", return_value=str(source)):
                cp.process_selected_highlights(
                    "https://example.com", highlights, str(root),
                    {"sourceQuality": "720", "addCaptions": False, "addHook": False,
                     "addWatermark": False, "addCreditWatermark": False},
                    {}, lambda message: None,
                )
            self.assertTrue(download.call_args.kwargs["prefer_cached_source"])
            self.assertEqual(download.call_args.kwargs["source_quality"], "720")


if __name__ == "__main__":
    unittest.main()
