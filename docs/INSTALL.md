# Install

Two paths: the automated one (what you want) and the manual one (what to do when something
disagrees). `install.sh --check-only` runs every precondition without touching anything.

## Automated

```bash
git clone https://github.com/Travizm/hermes-live-companion.git
cd hermes-live-companion
./install.sh --check-only          # read the report first
./install.sh --phrase "hey chaddy"
```

## The parts only a human can do

1. **Microphone permission.** A launchd-spawned process gets no TCC prompt and no microphone
   access. On first run the daemon logs
   `TimeoutError: Timed out while opening the wake-word microphone`. Fix by running the daemon
   once from a Terminal:

   ```bash
   ~/.hermes/hermes-agent/venv/bin/python ~/.hermes/scripts/wake-live-voice.py
   ```

   Approve the microphone prompt, Ctrl-C, then `launchctl kickstart -k gui/$(id -u)/dev.hermes.wake-live-voice`.
   Confirm with `curl -s http://127.0.0.1:8799/wake` → `"armed": true`.

2. **Start the dashboard correctly.** If you launch it from a terminal *inside the Hermes
   desktop app*, it inherits `HERMES_WEB_DIST` (the desktop's own renderer bundle) and serves the
   wrong SPA — the page dies with *"Desktop boot failed: Desktop IPC bridge is unavailable"*.
   Always:

   ```bash
   env -u HERMES_WEB_DIST -u HERMES_DESKTOP hermes dashboard --no-open --port 9119
   ```

   and build the SPA once: `cd ~/.hermes/hermes-agent/web && npm run build`.

3. **First audio gesture.** Browsers gate audio *playback* behind a user gesture. The first
   spoken reply may be silent; click the page once and it is unblocked for that page session.

## Manual install (equivalent to the script)

```bash
# 1. wake engine + the upstream-omitted dependency
~/.hermes/hermes-agent/venv/bin/pip install sherpa-onnx sentencepiece pypinyin

# 2. custom phrase via the open-vocabulary engine (the bundled openWakeWord model is "hey hermes" only)
hermes config set wake_word.enabled false      # the app's own listener stays OFF — the daemon owns the mic
hermes config set wake_word.provider sherpa
hermes config set wake_word.phrase "hey chaddy"

# 3. vendor patches (back up first!)
cd ~/.hermes/plugins/hermes-live
cp dashboard/plugin_api.py dashboard/plugin_api.py.pre-companion
cp dashboard/dist/index.js  dashboard/dist/index.js.pre-companion
patch -p1 < <repo>/patches/plugin_api.patch
patch -p1 < <repo>/patches/dashboard-index.patch

cd "$(npm root -g)/hermes-live-voice"
cp dist/adapters/outbound/realtime/openai-realtime.adapter.js{,.pre-companion}
patch -p1 < <repo>/patches/openai-realtime-adapter.patch

# 4. gateway config
cat >> ~/.hermes/hermes-live/config.env <<'EOF'
OPENAI_REALTIME_TURN_DETECTION="semantic_vad"
HERMES_LIVE_PROVIDER_READY_TIMEOUT_MS="60000"
EOF
hermes-live service restart

# 5. daemon + launchd
install -m 0755 scripts/wake-live-voice.py ~/.hermes/scripts/wake-live-voice.py
sed -e "s|__PYTHON__|$HOME/.hermes/hermes-agent/venv/bin/python|g" \
    -e "s|__DAEMON__|$HOME/.hermes/scripts/wake-live-voice.py|g" \
    -e "s|__HERMES_HOME__|$HOME/.hermes|g" -e "s|__PORT__|8799|g" \
    launchd/dev.hermes.wake-live-voice.plist.template > ~/Library/LaunchAgents/dev.hermes.wake-live-voice.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.hermes.wake-live-voice.plist
```

Config values in `config.env` **must be quoted** — an unquoted number makes the gateway exit 1 in a
crash loop with `KEY must be a string`.

## Post-install checklist

- [ ] `curl -s http://127.0.0.1:8799/wake` → `"armed": true`
- [ ] `./tests/run-tests.sh` → all pass
- [ ] Dashboard → PLUGINS → LIVE VOICE shows `Wake word: listening for '<phrase>'`
- [ ] Say the phrase: chime → page connects → you can talk
- [ ] Say *"that's all"*: disconnects
- [ ] Stay silent 60 s: auto-sleeps (unless a background task is running)
- [ ] Quit the desktop app: `curl -s http://127.0.0.1:8799/wake` → `"armed": false` (mic released)
