"""Custom PyInstaller hook for mediapipe to ensure required runtime modules and data files are collected."""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Force import of the MediaPipe Tasks API before collecting submodules so the
# modules used by portrait conversion are discovered. MediaPipe 1.x no longer
# ships the legacy mediapipe.python.solutions namespace.
try:
    import mediapipe
    import mediapipe.tasks.python
    import mediapipe.tasks.python.vision
except ImportError:
    pass


def _is_runtime_submodule(name):
    parts = name.split('.')
    return not any(
        part in {'test', 'tests', 'conftest'}
        or part.startswith('test_')
        or part.endswith('_test')
        for part in parts
    )


hiddenimports = collect_submodules('mediapipe', filter=_is_runtime_submodule)
datas = collect_data_files('mediapipe', include_py_files=False)

# Also collect the protobuf model files
datas += collect_data_files('mediapipe_model_maker')
