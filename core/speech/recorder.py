"""
Shared microphone capture for the speech tests (SPEECH_TEST_PLAN.md §4) — the
recording counterpart of core/tapping/audio.py, and the "shared mic recording
helper" ROADMAP §4 flagged as missing.

One continuous input stream per test run. Everything is timed on the
**sample clock** (sample index / rate), never on time.time(): the scored
window is a slice of the buffer, so a UI frame that runs late cannot shift a
syllable. The run loop reads `level_db` for the meter and `recent()` for the
live waveform, and asks for `mark()` at the window edges.

16 kHz mono float32: DDK energy sits well below 8 kHz, and it is the rate the
optional phoneme model expects, so nothing is resampled on the scoring path.
Sustained phonation (plan phase 3) wants 44.1 kHz and will open its own
Recorder with a different rate.
"""

from __future__ import annotations

import threading

import numpy as np

from .onsets import peak_dbfs, rms_dbfs

try:
    import sounddevice as sd
except ImportError:             # listed in requirements.txt; guarded anyway
    sd = None

DEFAULT_RATE = 16000
BLOCK_S = 0.03


class RecorderError(RuntimeError):
    """Raised with a sentence fit to show the user."""


class Recorder:
    def __init__(self, rate: int = DEFAULT_RATE, device=None):
        self.rate = rate
        self.device = device
        self._blocks: list[np.ndarray] = []
        self._n = 0
        self._lock = threading.Lock()
        self._stream = None
        self.level_db = -100.0
        self.peak_db = -100.0
        self.device_name = ""

    # ── lifecycle ─────────────────────────────────────────────────────────
    def open(self) -> None:
        if sd is None:
            raise RecorderError("The sounddevice package is not installed - "
                                "run python install.py.")
        try:
            info = sd.query_devices(self.device, "input")
        except Exception as exc:        # noqa: BLE001 - PortAudio raises many types
            raise RecorderError("No microphone was found - plug one in or "
                                "enable it in the system sound settings.") from exc
        self.device_name = str(info.get("name", ""))
        try:
            self._stream = sd.InputStream(
                samplerate=self.rate, channels=1, dtype="float32",
                blocksize=int(self.rate * BLOCK_S), device=self.device,
                callback=self._callback)
            self._stream.start()
        except Exception as exc:        # noqa: BLE001
            raise RecorderError("The microphone could not be opened - another "
                                "app may be using it.") from exc

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:           # noqa: BLE001 - closing is best-effort
                pass
            self._stream = None

    def _callback(self, indata, frames, time_info, status) -> None:
        block = indata[:, 0].copy()
        with self._lock:
            self._blocks.append(block)
            self._n += block.size
        self.level_db = rms_dbfs(block)
        self.peak_db = peak_dbfs(block)

    # ── buffer ────────────────────────────────────────────────────────────
    def reset(self) -> None:
        """Drop everything recorded so far; the clock restarts at zero."""
        with self._lock:
            self._blocks.clear()
            self._n = 0

    def mark(self) -> int:
        """Current position on the sample clock."""
        with self._lock:
            return self._n

    def seconds(self, mark: int) -> float:
        return mark / self.rate

    def _joined(self) -> np.ndarray:
        with self._lock:
            if len(self._blocks) > 1:
                self._blocks = [np.concatenate(self._blocks)]
            return self._blocks[0] if self._blocks else np.zeros(0, np.float32)

    def slice(self, start: int, end: int | None = None) -> np.ndarray:
        buf = self._joined()
        return buf[start:end].copy()

    def recent(self, seconds: float) -> np.ndarray:
        """The last `seconds` of audio, for the live waveform."""
        n = int(seconds * self.rate)
        with self._lock:
            tail, got = [], 0
            for block in reversed(self._blocks):
                tail.append(block)
                got += block.size
                if got >= n:
                    break
        if not tail:
            return np.zeros(0, np.float32)
        return np.concatenate(tail[::-1])[-n:]
