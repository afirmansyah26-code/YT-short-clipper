import sys
from types import ModuleType
from unittest.mock import MagicMock

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
