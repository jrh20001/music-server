# Session Transcript — August 14-15, 2026

## Music Server: troubleshooting stream updates, audio output, and intermittent 403 failures

This transcript covers the full troubleshooting session across three distinct
problems: (1) streams not updating in Kodi, (2) no audio output, and (3) some
genres silently failing to play. All user prompts and agent responses are
summarized below in the order they occurred.

---

### Prompt 1

**User:** Check the operation of music-server on hcontrol.local (set up as a
sudo crontab running as root). Also check the streaming software on xbian.local.
Currently the streams are not being updated in Kodi — identify the issue.

**Agent (investigation):** Established SSH access to both hosts (hcontrol via
key, xbian via password). Found:
- Music server running on hcontrol.local (pid 156414, `screen` session), port
  8778, all 8 genres resolved, `.strm` files regenerated fresh.
- Root crontab had the correct `@reboot` line.
- Kodi on xbian running; the addon and a "Music Server" video source existed.
- Two real problems:
  1. **Kodi library stale** — `MyVideos121.db` had three `path` entries, two
     of which were dead: the old server `http://192.168.50.4:8080/streams/`
     and a deleted local copy `/home/xbian/music/music-server/`. It also
     cached `.strm` entries for deleted genres (brazilian-jazz-fusion,
     paris-cafe) and was missing new ones (acoustic-alchemy, etc.).
  2. **URLs expire faster than the refresh** — these are YouTube *live*
     restreams whose `cps`/`met`-signed URLs die in ~40 min, but the server
     refreshed every 60 min. Kodi's log showed repeated HTTP 403 on playback.

**Agent (recommendations):** Three fixes — (1) rescan Kodi library + remove
stale sources, (2) reduce refresh to 30 min and re-resolve stale URLs on
demand, (3) move `@reboot` from root crontab to ubuntu to avoid a
root-vs-ubuntu file-ownership clash.

---

### Prompt 2

**User:** I think you have enough information — what are the suggested fixes?

**Agent:** Presented the three fixes concretely (Kodi DB cleanup + `rm` of the
stale copy, 30-min refresh + on-demand re-resolve, crontab ownership), and
asked whether to apply them.

---

### Prompt 3

**User:** Yes, apply the fixes.

**Agent:** Applied:
- **Fix 2** — `server.py`: `REFRESH_INTERVAL` 3600→1800s, added `STREAM_TTL`,
  on-demand re-resolve in `_serve_strm`. Restarted server; fresh `.strm`
  returned 200/206.
- **Fix 3** — moved the `@reboot` line from root to ubuntu crontab. (Caught
  and restored the comics/crosswords/jumbles cron lines that were briefly
  clobbered.)

**Fix 1** was split: the Kodi DB surgery was skipped initially (Kodi was live-
playing, `journal_mode=delete`), and the `rm` of the stale local copy was
deferred pending explicit consent (destructive-action guard). The stale rows
were noted as inert (not referenced by the current `sources.xml`).

---

### Prompt 4

**User:** Go ahead and implement Fix 1, don't worry about interrupting Kodi.

**Agent:** Attempted `pkill -9 kodi.bin` (blocked as destructive), then quit
Kodi gracefully via JSON-RPC `Application.Quit`. Executed:
- `MyVideos121.db`: deleted stale `path`/`files` rows for `.4:8080` and the
  deleted local copy; kept only `http://192.168.50.147:8778/streams/`.
- `MyMusic82.db`: removed the orphaned local-copy path.
- Removed `/home/xbian/music/music-server/`.
- Restarted Kodi; JSON-RPC responded (v13.0.0).

---

### Prompt 5

**User:** In the Kodi GUI, Addons → Music Server Streams, all 8 stream titles
show up, but clicking any stream produces no sound. Troubleshoot and get
streaming audio from the addon working.

**Agent (investigation):** Found Kodi was *actually playing* — AAC decoder
opened, 2ch/44.1kHz, playhead advancing, unmuted, volume 65 — but no sound.
This pointed to audio *output routing*, not the stream. Evidence: the stream
delivered 31KB/s of valid DASH audio; the ALSA `default` device resolved to
card 0 (HDMI), which was RUNNING, while the headphone jack (card 1) was closed.

**User (mid-turn):** Audio needs to go to the headphone jack; HDMI is not used.

**Agent:** Set `audiooutput.audiodevice` → `ALSA:sysdefault:CARD=Headphones`
via JSON-RPC (live), then persisted it in `guisettings.xml`.

**User (mid-turn):** OK, I hear sound now.

**Agent:** Verified card1 (Headphones) RUNNING, card0 (HDMI) closed; setting
persisted.

---

### Prompt 6

**User:** Under Addons / Music Server Streams, Cocktail Piano, Top 40 Hits,
Bossa Nova Jazz, and 70s 80s 90s do not play (stream seems missing); the other
streams work. Troubleshoot and fix.

**Agent (investigation):** Reproduced exactly: those 4 `.strm` endpoints
returned 403, the other 4 returned 206. Isolated the cause:
- Fresh yt-dlp resolves of the *same* video intermittently returned 206 vs 403
  (~50/50), even at t=0 — so it was not URL age.
- These are long "24/7" live-restream videos; YouTube intermittently issues a
  *dead* `cps`-signed URL that immediately 403s despite a 6h `expire` field.
- The server cached whatever yt-dlp returned, so ~half the genres got a
  poisoned URL each refresh — hence a fixed subset of genres silently failing.

**Fix:** Added `_url_playable()` (Range probe, accept 200/206) and wrapped the
yt-dlp fallback in `resolve_stream_url()` in a 4-attempt verify-and-retry loop
so a dead URL is never cached. Restarted server.

**Verification:** all 8 genres now return 206.

---

### Prompt 7

**User:** Update PROCESSING-DESCRIPTION.md, README.md, SW-Development.md,
build-transcript, create a session-transcript.md for this entire session
(include all prompts and responses/recommendations, no code edits, human-
readable). Also update `uv sync` and git.

**Agent:** Created/updated the four docs (PROCESSING-DESCRIPTION.md,
README.md, SW-Development.md, build-transcript.md, session-transcript.md),
ran `uv sync`, and committed to git.

---

## Outcome Summary

| Problem | Root Cause | Resolution |
|---------|-----------|------------|
| Streams not updating in Kodi | stale library DB entries (old IP + deleted local copy) | cleaned Kodi DBs, removed stale copy |
| No sound | audio routed to HDMI instead of headphone jack | pinned `ALSA:sysdefault:CARD=Headphones` |
| 4 genres silent (403) | YouTube serves dead URLs ~50% of the time for live restreams | verify + retry on resolve; 30-min TTL |
| root/ubuntu file ownership | root `@reboot` would start a 2nd instance | moved `@reboot` to ubuntu crontab |
