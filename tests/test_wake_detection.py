#!/usr/bin/env python3
"""Feed synthesised speech through the configured wake engine.

Positive clip contains the configured phrase and MUST fire; the negative clip is unrelated
speech and MUST NOT. Runs entirely locally: macOS `say` + ffmpeg -> 16 kHz PCM -> engine.
No microphone is used, so this works over ssh and in CI-ish contexts.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

HERMES_HOME = pathlib.Path.home() / ".hermes"
sys.path.insert(0, str(HERMES_HOME / "hermes-agent"))

import numpy as np  # noqa: E402
from tools import wake_word as ww  # noqa: E402
from tools.wake_word_engines import _SherpaKwsEngine  # noqa: E402

cfg = ww.load_wake_word_config()
phrase = ww.wake_phrase(cfg)
print(f"engine={cfg.get('provider')} phrase={phrase!r} sensitivity={cfg.get('sensitivity')} "
      f"confirmation_frames={cfg.get('confirmation_frames')}")


def synth(text: str, tmp: pathlib.Path, attempt: int = 1) -> bytes:
    """macOS say -> 16 kHz mono int16 PCM bytes.

    `say` intermittently writes a truncated file on its first invocation in a fresh process
    (observed: a 0 s clip), which looks exactly like a detector failure. Retry once before
    letting that ambiguity reach the assertion.
    """
    aiff, pcm = tmp / "clip.aiff", tmp / "clip.pcm"
    subprocess.run(["say", "-o", str(aiff), text], check=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1",
                    "-f", "s16le", str(pcm)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    data = pcm.read_bytes()
    if attempt == 1 and len(data) < 16000:            # < 0.5 s of audio => truncated
        print("    (say produced a truncated clip — retrying once)")
        return synth(text, tmp, attempt=2)
    return data


def detect(pcm: bytes) -> tuple[int, float | None]:
    audio = np.frombuffer(pcm, dtype=np.int16)
    peak = int(np.abs(audio).max()) if audio.size else 0
    print(f"    clip: {len(pcm)}B  {len(audio)/16000:.2f}s  peak={peak}")
    if peak == 0 or len(audio) < 16000 * 0.4:
        print("    ! clip looks empty/too short — `say` produced no audio (this is a TEST problem, not the engine)")
    engine = _SherpaKwsEngine(cfg)
    fires, first = 0, None
    for offset in range(0, len(audio) - engine.frame_length, engine.frame_length):
        if engine.process(audio[offset:offset + engine.frame_length]):
            fires += 1
            first = first if first is not None else offset / 16000.0
    engine.close()
    return fires, first


with tempfile.TemporaryDirectory() as raw:
    tmp = pathlib.Path(raw)
    pos = detect(synth(f"{phrase}, are you there?", tmp))
    neg = detect(synth("The weather in Brisbane is warm today and the trains are running on time.", tmp))

print(f"  positive clip: fires={pos[0]} first@{pos[1] if pos[1] is None else round(pos[1], 2)}s")
print(f"  negative clip: fires={neg[0]}")
ok = pos[0] > 0 and neg[0] == 0
print("\n" + ("PASS — phrase detected, unrelated speech ignored" if ok
               else "FAIL — expected the phrase to fire and the negative clip to stay silent"))
if pos[0] == 0:
    print("  hint: raise wake_word.sensitivity (currently %s) or re-check the phrase" % cfg.get("sensitivity"))
sys.exit(0 if ok else 1)
