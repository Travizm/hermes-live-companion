# Architecture

```
 "hey chaddy"
      │
      ▼
 companion daemon  (launchd, KeepAlive, ~/.hermes/scripts/wake-live-voice.py)
   • arms Hermes' own sherpa wake engine ONLY while Hermes.app is running
   • releases the microphone the moment the app exits
      │  on_wake()
      ▼
 local bridge  http://127.0.0.1:8799   (/wake, /heartbeat, /ping)
      │                                    ▲
      │ counter++                          │ heartbeat 5 s
      ▼                                    │
 Live Voice page (patched plugin bundle) ──┘
   • polls /wake every 1 s; on a counter bump presses Connect
   • owns the realtime session UI, transcript, task inbox
      │  WebSocket
      ▼
 hermes-live gateway :8788  ──►  OpenAI Realtime (or Gemini / local)
      │
      └──►  Hermes API server :8642  →  agent runs in the selected chat
```

## Why a companion instead of the app's own wake word

Hermes' desktop app already has a wake word, and it works — but on `wake.detected` it runs its
**own** voice loop (free the mic → chime → VAD + STT + agent + TTS). A desktop plugin receives the
same event (plugins hear the gateway stream first) yet **cannot veto app flow**, and no config gates
only that path. So enabling it and adding Live Voice on top produces two assistants listening and
answering at once.

The companion sidesteps the contention entirely: the app's listener stays off, the daemon owns the
microphone while the app runs, and the wake is delivered to the Live Voice page over the bridge.
`wake_word.enabled` therefore stays `false` in `config.yaml` — this is load-bearing, not an oversight.

## Why the bridge exists

The page cannot be driven from outside a browser: no process can click its buttons, and the wake
happens in Python. The bridge is the seam — one counter the page polls, one heartbeat so the daemon
knows whether a page is already open (and only opens a window when none is).

## Cost model

Realtime sessions bill by the minute while *open*. The lifecycle controls exist to make that
bounded: a voice instruction disconnects immediately, and 60 s of silence with no task in flight
disconnects automatically. A wake-driven session that is used and then abandoned costs about a
minute, not an afternoon.

## What each patch does

| Patch | Failure it fixes |
|---|---|
| `openai-realtime.adapter.patch` | Hardcoded 10 s handshake cap; measured handshakes of 0.8–20 s meant intermittent "session.ready" failures with no retry. Raised to 45 s / 60 s. |
| `plugin_api.patch` | 2.5 s status timeout reused for the conversation list, which takes 3.1–3.8 s cold → an *empty* chat picker. Also filters machine-generated sessions (`cron`, `subagent`) out of the picker by default — they were 88% of the newest 100 — with a toggle to show them. |
| `dashboard-index.patch` | Adds the bridge polling, the wake bridge status line, and the session-lifecycle controls (stop phrases + idle auto-sleep). |

## Upstream defects worked around (report, do not silently accept)

1. `OPENAI_HANDSHAKE_TIMEOUT_MS = 10_000`, not configurable, no retry.
2. `STATUS_TIMEOUT_SECONDS = 2.5` used for a multi-second session query.
3. `wake.sherpa` dependency set omits `pypinyin`, so `text2token` raises and the sherpa engine can
   never arm as shipped.
4. The conversation list proxy scans recency-ordered pages, which cannot reach older chats on a
   machine with many scheduled jobs.
