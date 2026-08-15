# Build Transcript — Music Server (Reliability Fixes)

**Date:** 2026-08-15
**Source Repo:** /home/ubuntu/music-server (hcontrol.local, 192.168.50.147)
**Remote access:** `ssh ubuntu@hcontrol.local` (key auth), `ssh xbian@xbian.local` (password)
**Kodi host:** xbian.local (192.168.50.149), Kodi 20.2 Nexus / XBian 11.0 Bookworm
**Toolchain:** Python 3.14 (server), yt-dlp 2026.7.4 + deno, uv

---

## Environment

| Host | Role | Port | User |
|------|------|------|------|
| hcontrol.local | music server | 8778 | ubuntu |
| xbian.local | Kodi + audio output | 8080 (JSON-RPC) | xbian |

Note: the server was previously reached at `192.168.50.4:8080`; it moved to
`192.168.50.147:8778`. Stale references to the old address caused symptom #1.

---

## Issues Fixed

| # | Symptom | Root Cause | Fix |
|---|---------|-----------|-----|
| 1 | Genre list stale in Kodi | Kodi library DB had stale `path` rows (old `.4:8080`, deleted local copy) + cached deleted genres | Removed stale `path`/`files` rows in `MyVideos121.db`, removed local copy, kept current source |
| 2 | No sound from any stream | Audio routed to HDMI (ALSA `default` = card 0) | Set `audiooutput.audiodevice = ALSA:sysdefault:CARD=Headphones`, persisted in `guisettings.xml` |
| 3 | 4 of 8 genres silent (403) | YouTube intermittently returns dead `cps`-signed URLs (~50%); server cached them | `_url_playable()` verify + 4× retry in `resolve_stream_url()`; refresh 3600→1800s; `STREAM_TTL` on-demand re-resolve |
| 4 | root crontab vs ubuntu-owned files | root `@reboot` would start a second instance, root-owning generated files | moved `@reboot` to ubuntu crontab |

---

## Changes to `server.py`

1. `REFRESH_INTERVAL` default 3600 → 1800s.
2. Added `STREAM_TTL = 1800`.
3. Added `_url_playable(url)` — Range probe, accepts 200/206.
4. `resolve_stream_url()` — wrapped yt-dlp fallback in a 4-attempt loop that
   verifies each URL and discards dead (403) ones.
5. `_serve_strm()` — re-resolves on demand when the cached URL is older than
   `STREAM_TTL`.

---

## Deployment Steps (executed)

```bash
# hcontrol.local — edit server.py, then restart the screen session
ssh ubuntu@hcontrol.local
cd /home/ubuntu/music-server
.venv/bin/python -m py_compile server.py      # verify syntax
screen -S ms -X quit                          # stop old server
screen -dmS ms .venv/bin/python server.py     # start new server

# xbian.local — fix Kodi audio device (JSON-RPC, live)
curl -X POST http://xbian.local:8080/jsonrpc \
  -d '{"jsonrpc":"2.0","id":1,"method":"Settings.SetSettingValue",
       "params":{"setting":"audiooutput.audiodevice","value":"ALSA:sysdefault:CARD=Headphones"}}'

# persist the setting
#   edit /home/xbian/.kodi/userdata/guisettings.xml
#   <setting id="audiooutput.audiodevice">ALSA:sysdefault:CARD=Headphones</setting>
```

Crontab migration:

```bash
# remove @reboot music-server line from root crontab
sudo crontab -l | grep -v music-server | sudo crontab -

# add to ubuntu crontab
crontab -l | grep -v music-server
echo '@reboot sleep 20 && cd /home/ubuntu/music-server && screen -dmS ms .venv/bin/python server.py' | crontab -
```

---

## Verification

- [x] `server.py` compiles (`.venv/bin/python -m py_compile`)
- [x] Server listening on 8778 after restart
- [x] `/health` shows 8/8 genres resolved
- [x] All 8 `.strm` endpoints return HTTP 206 (playable)
- [x] Kodi audio sink RUNNING on card1 (Headphones), card0 (HDMI) closed
- [x] `guisettings.xml` audio device persisted to Headphones

---

## Known Issues

| Issue | Details |
|-------|---------|
| YouTube ~50% dead-URL rate | handled by verify + retry; if it worsens, add rotating client/UA |
| Kodi file-source listing cached | browse via addon (live) to see genre changes immediately |
| `PI:Analogue` device string maps to HDMI "default" on XBian | pinned explicit `ALSA:sysdefault:CARD=Headphones` instead |
