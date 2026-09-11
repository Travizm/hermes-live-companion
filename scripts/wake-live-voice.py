#!/usr/bin/env python3
"""hermes-live-companion · wake-word launcher for Live Voice, scoped to the Hermes desktop app.

Part of hermes-live-companion v0.1 — https://github.com/Travizm/hermes-live-companion

Why this exists instead of the app's own wake word: the desktop app handles
``wake.detected`` by running its *own* voice loop (VAD + STT + Hermes + TTS), and a
plugin cannot veto that. So the app's listener stays disabled and this process owns
the microphone instead — but only while the app is running, so the mic is never hot
in the background.

On the phrase it:
  1. chimes (confirmation, like the app's own wake sound),
  2. bumps a counter that any open Live Voice page polls over the local bridge,
  3. opens the page if no page has heartbeated recently.

The page (a patched hermes-live dashboard bundle) polls ``/wake`` and clicks the
Connect control itself, so the realtime session comes up without touching the app.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
REPO = HERMES_HOME / "hermes-agent"
APP_MATCH = "Hermes.app/Contents/MacOS/Hermes"
LIVE_URL = os.environ.get("WAKE_LV_URL", "http://127.0.0.1:9119/live-voice?autoconnect=1")
PORT = int(os.environ.get("WAKE_LV_PORT", "8799"))
OWNER = "wake-live-voice"
POLL_SECONDS = 3.0
HEARTBEAT_TTL = 20.0
CHIME = os.environ.get("WAKE_LV_CHIME", "/System/Library/Sounds/Glass.aiff")

# Test/headless hooks (never set in production).
FAKE_APP = os.environ.get("WAKE_LV_FAKE_APP") == "1"
DRY_OPEN = os.environ.get("WAKE_LV_DRY_OPEN") == "1"
TEST_TRIGGER = os.environ.get("WAKE_LV_TEST_TRIGGER") == "1"
EXTERNAL_AUDIO = os.environ.get("WAKE_LV_EXTERNAL_AUDIO") == "1"

sys.path.insert(0, str(REPO))

STATE: dict = {"armed": False, "phrase": "", "provider": "", "counter": 0,
               "last_wake": 0.0, "wakes": 0, "page_beat": 0.0, "last_error": "",
               "opened": 0, "started_at": time.time()}
_LOCK = threading.Lock()


def log(message: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


def app_running() -> bool:
    if FAKE_APP:
        return True
    try:
        return subprocess.run(["pgrep", "-f", APP_MATCH], capture_output=True).returncode == 0
    except Exception:
        return False


def chime() -> None:
    if not os.path.exists(CHIME):
        return
    try:
        subprocess.Popen(["afplay", CHIME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def open_page() -> None:
    if DRY_OPEN:
        log(f"[dry-run] would open {LIVE_URL}")
    else:
        subprocess.Popen(["open", LIVE_URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with _LOCK:
        STATE["opened"] += 1


def page_is_alive() -> bool:
    with _LOCK:
        return (time.time() - STATE["page_beat"]) < HEARTBEAT_TTL


def on_wake() -> None:
    """Detector callback — runs on the detector's thread."""
    with _LOCK:
        STATE["counter"] += 1
        STATE["wakes"] += 1
        STATE["last_wake"] = time.time()
        counter = STATE["counter"]
        phrase = STATE["phrase"]
    log(f"WAKE #{counter} ({phrase!r}) -> Live Voice")
    chime()
    # An open page picks the counter up over the bridge; only spawn a window if none is live.
    if not page_is_alive():
        open_page()


class Bridge(BaseHTTPRequestHandler):
    """Tiny local bridge the patched plugin page polls (1 s) and heartbeats (5 s)."""

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/wake":
            with _LOCK:
                self._json({
                    "counter": STATE["counter"],
                    "armed": STATE["armed"],
                    "phrase": STATE["phrase"],
                    "provider": STATE["provider"],
                    "wakes": STATE["wakes"],
                    "last_wake": STATE["last_wake"],
                    "app_running": app_running(),
                    "last_error": STATE["last_error"],
                })
            return
        if path == "/heartbeat":
            with _LOCK:
                STATE["page_beat"] = time.time()
            self._json({"ok": True})
            return
        if path == "/ping":
            self._json({"ok": True, "pid": os.getpid()})
            return
        if path == "/test-wake" and TEST_TRIGGER:
            on_wake()
            self._json({"ok": True, "counter": STATE["counter"]})
            return
        if path == "/test-feed" and TEST_TRIGGER:
            # Test-only: push a PCM clip through the REAL detector (same path the mic feeds),
            # so the confirmation-frame + cooldown logic decides whether it fires.
            clip = os.environ.get("WAKE_LV_TEST_PCM", "")
            if not clip or not os.path.exists(clip):
                self._json({"ok": False, "error": "WAKE_LV_TEST_PCM unset or missing"}, status=400)
                return
            from tools.wake_word import feed_audio
            import numpy as np
            audio = np.frombuffer(Path(clip).read_bytes(), dtype=np.int16)
            fed = 0
            frame = 1280  # 80 ms at 16 kHz, the engine's frame length
            for i in range(0, len(audio) - frame, frame):
                if feed_audio(owner=OWNER, pcm_int16=audio[i:i + frame].tobytes()):
                    fed += 1
            self._json({"ok": True, "frames_fed": fed, "counter": STATE["counter"],
                        "wakes": STATE["wakes"]})
            return
        self._json({"ok": False, "error": "not_found"}, status=404)

    def log_message(self, *args) -> None:  # keep the launchd log readable
        return


def load_wake_cfg() -> dict:
    """Wake config from config.yaml, with detection forced on for THIS process only."""
    from tools import wake_word as ww
    cfg = dict(ww.load_wake_word_config())
    cfg["enabled"] = True          # the file stays enabled:false so the app never arms
    if EXTERNAL_AUDIO:             # test-only: accept pushed PCM instead of the mic
        cfg["capture"] = "client"
    return cfg, ww


def arm() -> None:
    cfg, ww = load_wake_cfg()
    reqs = ww.check_wake_word_requirements(cfg)
    if not reqs.get("available", False):
        raise RuntimeError(reqs.get("hint") or "wake-word requirements not met")
    ww.start_listening(on_wake, owner=OWNER, config=cfg, external_audio=EXTERNAL_AUDIO)
    with _LOCK:
        STATE["armed"] = True
        STATE["phrase"] = ww.wake_phrase(cfg)
        STATE["provider"] = str(cfg.get("provider") or "")
        STATE["last_error"] = ""
    log(f"armed: listening for {STATE['phrase']!r} via {STATE['provider']} (app running)")


def disarm() -> None:
    from tools import wake_word as ww
    ww.stop_listening(owner=OWNER)
    with _LOCK:
        STATE["armed"] = False
    log("disarmed: app not running, microphone released")


def supervisor() -> None:
    """Arm only while the desktop app runs; release the mic the moment it exits."""
    failure_backoff = 0.0
    while True:
        try:
            if app_running():
                if not STATE["armed"] and time.time() >= failure_backoff:
                    try:
                        arm()
                    except Exception as exc:  # keep the daemon alive; retry later
                        with _LOCK:
                            STATE["last_error"] = f"{type(exc).__name__}: {exc}"
                        log(f"arm failed: {STATE['last_error']}")
                        failure_backoff = time.time() + 30
            elif STATE["armed"]:
                disarm()
        except Exception as exc:
            log(f"supervisor error: {type(exc).__name__}: {exc}")
        time.sleep(POLL_SECONDS)


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Bridge)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log(f"bridge on http://127.0.0.1:{PORT} · app-scoped listener · pid {os.getpid()}")
    try:
        supervisor()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if STATE["armed"]:
                disarm()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
