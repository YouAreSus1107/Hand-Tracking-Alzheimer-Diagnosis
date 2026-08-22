"""
Native-log suppression for MediaPipe / TFLite (stdlib-only).

MediaPipe's C++ core prints a wall of startup noise the first time a task graph
is built — glog `W0000 ... face_landmarker_graph.cc` lines, the
`inference_feedback_manager` warnings, and TFLite's own
`INFO: Created TensorFlow Lite XNNPACK delegate for CPU.` None of it is
actionable, and it buries the camera prompt in every tool's console.

Two layers, because the messages come from two different loggers:

1. `import core.quiet` (before `import mediapipe`) sets the glog/absl
   environment so only real errors are logged. Importing it later has no
   effect — glog reads these at load time — so keep the import above
   mediapipe's in every module that pulls it in.
2. `with muted_native_stderr():` around task-graph construction swallows what
   is left at the file-descriptor level (TFLite writes straight to stderr and
   ignores glog). The captured text is re-printed if the block raises, so a
   genuine model-load failure is never hidden.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile

# glog: 2 = ERROR and above only (leave logtostderr alone — turning it off just
# moves the noise into log files). TF_CPP_MIN_LOG_LEVEL covers the TF-derived
# ops. setdefault so an operator debugging MediaPipe can override from outside.
for _var, _val in (("GLOG_minloglevel", "2"),
                   ("GLOG_stderrthreshold", "2"),
                   ("TF_CPP_MIN_LOG_LEVEL", "3")):
    os.environ.setdefault(_var, _val)

try:                                    # absl is pulled in by mediapipe
    from absl import logging as _absl_logging
    _absl_logging.set_verbosity(_absl_logging.ERROR)
except Exception:                       # noqa: BLE001 - never break on logging
    pass


@contextlib.contextmanager
def muted_native_stderr():
    """Silence C-level stderr for the block; replay it if the block raises."""
    try:
        saved_fd = os.dup(2)
    except OSError:                     # no real stderr (pythonw / frozen)
        yield
        return
    tmp = tempfile.TemporaryFile(mode="w+b")
    try:
        sys.stderr.flush()
        os.dup2(tmp.fileno(), 2)
        try:
            yield
        finally:
            sys.stderr.flush()
            os.dup2(saved_fd, 2)
    except BaseException:
        tmp.seek(0)
        captured = tmp.read().decode("utf-8", "replace").strip()
        if captured:
            print(captured, file=sys.stderr)
        raise
    finally:
        os.close(saved_fd)
        tmp.close()
