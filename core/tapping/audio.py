"""
Audio cues via a single persistent worker thread + queue — replaces the
thread-per-beep pattern that added start-jitter (audit A8). Cross-platform:
on Windows plays through winsound (zero-config, follows the system-default
playback device); elsewhere plays through sounddevice (PortAudio); if neither
is available it silently no-ops.
"""

from __future__ import annotations

import io
import math
import queue
import struct
import threading

try:
    import sounddevice as sd
    import numpy as np
except ImportError:            # sounddevice not installed
    sd = None

try:
    import winsound
except ImportError:            # non-Windows
    winsound = None


def build_tone(freq: float = 880, duration_ms: int = 100,
               sample_rate: int = 44100) -> bytes:
    """PCM WAV tone in memory with 5 ms fade in/out to avoid clicks.
    Routing through the normal audio mixer (sounddevice or
    PlaySound(SND_MEMORY)) is far more reliable than winsound.Beep()."""
    n = int(sample_rate * duration_ms / 1000)
    fade_n = max(1, int(sample_rate * 0.005))
    samples = []
    for i in range(n):
        t = i / sample_rate
        fade = min(i, n - i, fade_n) / fade_n
        samples.append(int(32767 * 0.9 * fade * math.sin(2 * math.pi * freq * t)))
    data = struct.pack(f"<{n}h", *samples)
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(data)))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(data)))
    buf.write(data)
    return buf.getvalue()


def _play_blocking(wav: bytes) -> None:
    """Play one of our own build_tone() WAV buffers (fixed 44-byte header,
    16-bit mono PCM) and return when it finishes, keeping the worker queue's
    one-at-a-time semantics on every backend. Prefer winsound on Windows: it
    routes to the system-default playback device, whereas PortAudio may pick a
    different 'default' (e.g. a Bluetooth or virtual-cable device)."""
    if winsound is not None:
        winsound.PlaySound(wav, winsound.SND_MEMORY)
    elif sd is not None:
        sample_rate = struct.unpack_from("<I", wav, 24)[0]
        pcm = np.frombuffer(wav, dtype=np.int16, offset=44)
        sd.play(pcm, samplerate=sample_rate)
        sd.wait()


class AudioWorker:
    """One daemon thread consuming a queue of prebuilt WAV buffers."""

    def __init__(self):
        self._q: queue.Queue[bytes | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def play(self, wav: bytes) -> None:
        self._q.put(wav)

    def _run(self) -> None:
        while True:
            wav = self._q.get()
            if wav is None:
                return
            try:
                _play_blocking(wav)
            except Exception:      # no output device etc. — cue is best-effort
                pass

    def close(self) -> None:
        self._q.put(None)
