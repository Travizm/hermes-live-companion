# Changelog

## 0.1.0 — 2026-09-11

First packaged release. Built and verified against Hermes Agent v0.21.1 and hermes-live-voice 1.1.3
on macOS 15.6.1 (Apple Silicon).

**Added**
- Wake-phrase companion daemon (`scripts/wake-live-voice.py`) with app-scoped microphone ownership:
  armed only while `Hermes.app` runs, released the moment it exits.
- Local bridge (`127.0.0.1:8799`) so the Live Voice page reacts to a wake it did not initiate.
- Open-vocabulary wake phrase via Hermes' sherpa engine (`wake_word.provider: sherpa`) — any typed
  phrase, no training, local model.
- Session lifecycle in the page: voice-instruction disconnect (*"that's all"*, *"stop listening"*,
  *"goodbye"*, …) and 60 s idle auto-sleep that is held while background work runs.
- Conversation picker filtering: machine-generated sessions (`cron`, `subagent`) hidden by default
  with a toggle to show them; per-source fetch so older real chats are reachable.
- Installer with `--check-only` / `--phrase` / `--revert`, idempotent patch application with
  `.pre-companion` backups.

**Fixed (vendor patches)**
- Provider handshake cap of 10 s (measured handshakes 0.8–20 s) causing intermittent
  `session.ready` failures → 45 s handshake / 60 s connect.
- 2.5 s proxy timeout reused for the multi-second conversation list, which made the chat picker
  empty and forced every voice session into a new chat → dedicated 15 s budget.

**Known issues**
- macOS only.
- Pinned to hermes-live-voice 1.1.3; the installer refuses other versions rather than half-apply.
- First audio playback may require one click on the page (browser gesture rule).
- Four upstream defects are worked around rather than fixed here — see ARCHITECTURE.md.
