# hermes-live-companion

**v0.1** · Make [`hermes-live-voice`](https://github.com/bielcarpi/hermes-live-voice) usable as a
daily driver on a Hermes box: wake it with a phrase, keep the chat picker free of machine noise,
and stop it burning realtime minutes when you have walked away.

Built and verified on macOS 15.6.1 (Apple Silicon) against **Hermes Agent v0.21.1** and
**hermes-live-voice 1.1.3**.

---

## What it adds

| Capability | Without it | With it |
|---|---|---|
| **Wake phrase** | Click *Connect Live Voice* every session | Say *"hey Chaddy"* — the page connects itself |
| **Mic discipline** | — | The listener is armed **only while the Hermes desktop app is running** |
| **Picker hygiene** | Newest-50 chats are ~88% cron watchdogs | Machine sessions hidden, real chats instantly reachable, one toggle to show them |
| **Session lifecycle** | Session runs until you remember to close it | Say *"that's all"* to disconnect, or let 60 s of idle sleep it (never sleeps on running work) |

Four things happen on install:

1. **`wake_word`** is configured for an open-vocabulary custom phrase using Hermes' own sherpa
   engine — no training, no cloud, ~13 MB local model. The *app's* own wake word is deliberately
   left **off** (see [Why the app's own wake is disabled](docs/ARCHITECTURE.md#why-the-apps-own-wake-is-disabled)).
2. A **companion daemon** (`scripts/wake-live-voice.py`, launchd `KeepAlive`) owns the microphone
   while the desktop app runs and fires the wake.
3. Three **vendor patches** (pinned to hermes-live-voice 1.1.3) fix two hard failures and add the
   picker filter + lifecycle controls. See [`patches/`](patches).
4. A small **local bridge** (`127.0.0.1:8799`) connects the daemon to the Live Voice page, so the
   page can react to a wake it did not initiate.

## Requirements

- macOS (Apple Silicon or Intel), with the **Hermes desktop app** installed
- Hermes Agent **v0.21.1** (or newer) with the API server enabled
- `hermes-live-voice` **1.1.3** installed globally via npm, gateway service running
- A realtime voice provider configured (OpenAI, Gemini, or local)
- `node`, `npm`, `ffmpeg`, and `python3` on `PATH`

## Install

```bash
git clone https://github.com/Travizm/hermes-live-companion.git
cd hermes-live-companion
./install.sh --phrase "hey chaddy"      # default phrase is "hey chaddy"
```

The installer is idempotent and refuses to apply patches to an unexpected version. Useful flags:

```bash
./install.sh --check-only     # verify prerequisites, change nothing
./install.sh --phrase "hey jarvis"
./install.sh --revert         # undo every change (patches, plist, config keys)
```

## Verify

```bash
curl -s http://127.0.0.1:8799/wake | python3 -m json.tool
# {"armed": true, "phrase": "hey chaddy", "app_running": true, ...}

./tests/run-tests.sh          # stop-phrase matcher + wake-detection engine self-test
```

Then open the dashboard, choose **PLUGINS → LIVE VOICE**, and you should see:

```
Wake word: listening for 'hey chaddy'
```

Say the phrase. You should hear a chime, the page should connect, and you can just talk.

## What it changes on your machine

Transparency matters more than a tidy install story — every change is reversible:

| Path | Change |
|---|---|
| `~/.hermes/config.yaml` | `wake_word.{enabled:false, provider:sherpa, phrase:…}` |
| `~/.hermes/hermes-live/config.env` | `OPENAI_REALTIME_TURN_DETECTION`, `HERMES_LIVE_PROVIDER_READY_TIMEOUT_MS` |
| `~/.hermes/plugins/hermes-live/dashboard/plugin_api.py` | patched (backup: `.pre-companion`) |
| `~/.hermes/plugins/hermes-live/dashboard/dist/index.js` | patched (backup: `.pre-companion`) |
| `~/…/hermes-live-voice/dist/…/openai-realtime.adapter.js` | patched (backup: `.pre-companion`) |
| `~/.hermes/scripts/wake-live-voice.py` | the companion daemon |
| `~/Library/LaunchAgents/dev.hermes.wake-live-voice.plist` | launchd agent (`KeepAlive`) |
| Hermes venv | `sherpa-onnx`, `sentencepiece`, `pypinyin` Python packages |

**Vendor patches are overwritten by `npm i -g hermes-live-voice`.** Re-run `./install.sh` after any
hermes-live upgrade. The installer detects its own patches and re-applies cleanly.

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md) — step-by-step, including the parts only a human can do
- [docs/AGENT.md](docs/AGENT.md) — machine-readable install/verify/uninstall procedure for an AI agent
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the pieces fit, and the cost model
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — every failure we actually hit, with causes

## Known limits (v0.1)

- **macOS only.** The companion uses `afplay`, `open`, and launchd.
- **Pinned to hermes-live-voice 1.1.3.** The installer refuses other versions rather than
  half-apply; `patches/` are small enough to rebase by hand.
- **The voice UI lives in the dashboard page** (browser or the desktop preview pane), not as a
  native desktop pane — the vendor plugin ships only a dashboard tab.
- **Audio priming:** browsers gate audio *playback* behind a user gesture. If the first reply is
  silent, click the page once; playback is then unblocked for the session.
- Upstream has three real bugs worth reporting (all worked around here): a hardcoded 10 s provider
  handshake cap with no retry, a 2.5 s proxy budget for a multi-second session query, and a
  `wake.sherpa` dependency set that omits `pypinyin`.

## License

MIT for this repo's code. The patches modify [hermes-live-voice](https://github.com/bielcarpi/hermes-live-voice) (MIT),
and the companion drives Hermes Agent's own wake-word engine — both are credited, neither is vendored.
