# Troubleshooting

Every entry here is a failure actually hit while building this, with the real cause.

## Wake word

**`Timed out while opening the wake-word microphone` in the daemon log.**
A launchd-spawned process starts with no microphone access and gets no TCC prompt. Run the daemon
once from a Terminal to trigger the prompt, approve it, then
`launchctl kickstart -k gui/$(id -u)/dev.hermes.wake-live-voice`. Verify with
`curl -s http://127.0.0.1:8799/wake` → `"armed": true`.

**`ModuleNotFoundError: No module named 'pypinyin'`.**
`sherpa_onnx.text2token` imports it; the upstream `wake.sherpa` feature set omits it, so the engine
raises at build time and the listener never arms. `pip install pypinyin` into the Hermes venv.

**`arm failed: ... requirements not met` (but the engine clearly works).**
Hermes' `check_wake_word_requirements()` reports `available`, **not** `ok`. Reading the wrong key
makes arming fail forever; the daemon reads `available`.

**The phrase never fires.**
Run `tests/test_wake_detection.py` — it synthesises the phrase locally and feeds it through the
engine with no microphone involved, so it separates "engine can't hear this phrase" from "mic
isn't delivering audio". If the positive clip doesn't fire, raise `wake_word.sensitivity`
(default 0.6) or choose a phrase with more distinctive phonemes.

**It fires too easily / on the TV.**
Raise `wake_word.sensitivity`, or raise `confirmation_frames` (default 3) so a stray phoneme can't
trip it. Changes take effect on the next arm (`launchctl kickstart -k …`).

## Session

**The session connects but the first reply is silent.**
Browser audio *playback* needs a user gesture. Click the page once; it stays unblocked for that
page session. (Microphone capture is unaffected.)

**`Gateway did not complete the WebSocket/session.ready handshake within 10000ms`.**
The provider handshake exceeded the vendor's hardcoded 10 s cap. Check
`patches/openai-realtime-adapter.patch` applied and that the gateway was restarted afterwards.
Measured handshakes ranged 0.8–20 s on the same machine, so this is intermittent by nature.

**It disconnects mid-conversation.**
The idle clock resets on any new utterance (yours or the assistant's), a task state change, or
playback change, and is *held* while a task is `accepted`/`queued`/`running`/`stopping`. If it still
sleeps early, check the transcript is still arriving (a stalled transcript looks idle) and lengthen
`IDLE_SLEEP_MS` in the bundle patch.

**It never disconnects when asked.**
The matcher works per clause after stripping wake prefixes and punctuation. Say the phrase as its
own clause: *"that's all"*, *"stop listening"*, *"hey chaddy, that's all"*. Sentences that merely
*contain* a stop word (*"we should disconnect the battery"*) deliberately do not trigger — run
`tests/test_stop_matcher.mjs` to see the exact table.

## Dashboard

**Page shows *"Desktop boot failed: Desktop IPC bridge is unavailable"*.**
The dashboard inherited `HERMES_WEB_DIST` from the desktop app's terminal and is serving the
desktop's renderer bundle instead of the web SPA. Launch with
`env -u HERMES_WEB_DIST -u HERMES_DESKTOP hermes dashboard --no-open --port 9119`, and build the
SPA first (`cd ~/.hermes/hermes-agent/web && npm run build`).

**The page is blank / the plugin tab renders nothing after a patch.**
Check for a temporal-dead-zone error: a `useEffect(..., [deps])` evaluates its dependency array
*during render*, so patch code referencing a later `const` (like `connected`) throws and blanks the
page. `node --check` won't catch it — load the page. Patch blocks must come after their
dependencies are declared.

**Picker is empty.**
The proxy had a 2.5 s budget for a 3.1–3.8 s cold session query. Confirm
`patches/plugin_api.patch` applied and restart the dashboard.

## Gateway

**Crash loop, `config.env:N: KEY must be a string`.**
Managed-config values must be quoted: `KEY="60000"`, not `KEY=60000`. Only
`~/.hermes/hermes-live/logs/gateway.error.log` reveals it; `hermes-live service status` just shows
`last exit code = 1`.

**Voice worked this morning and not now.**
Check `curl -s http://127.0.0.1:8788/ready` and the gateway log for provider handshake failures —
this is usually the handshake cap, not your setup.
