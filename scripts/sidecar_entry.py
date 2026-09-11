"""PyInstaller entry point for the YT Short Clipper Python sidecar.

This thin wrapper exists so PyInstaller has a single top-level script to
freeze. All real logic lives in yt_short_clipper_core.sidecar.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock

# MediaPipe drawing_utils imports matplotlib unconditionally at module load,
# even though plot_landmarks is never called by our app.
if "matplotlib" not in sys.modules or not hasattr(sys.modules["matplotlib"], "__path__"):
    try:
        import matplotlib
        import matplotlib.pyplot
    except ImportError:
        m = ModuleType("matplotlib")
        m.__path__ = []
        plt = MagicMock()
        m.pyplot = plt
        sys.modules["matplotlib"] = m
        sys.modules["matplotlib.pyplot"] = plt

from yt_short_clipper_core.sidecar import main

if __name__ == "__main__":
    main()

