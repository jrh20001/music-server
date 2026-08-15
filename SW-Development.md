# Music Server — Development Plan

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture Decision](#2-architecture-decision)
3. [Phase 0: Prerequisites & Setup](#3-phase-0-prerequisites--setup)
4. [Phase 1: Core Server (v1.0)](#4-phase-1-core-server-v10)
5. [Phase 2: Kodi Integration](#5-phase-2-kodi-integration)
6. [Phase 3: Reliability Fixes (this session)](#6-phase-3-reliability-fixes-this-session)
7. [Key Decisions & Risks](#7-key-decisions--risks)

---

## 1. Overview

A small HTTP server that turns YouTube "genre" streams (smooth jazz, cocktail
piano, bossa nova, etc. — mostly long 24/7 live-restream videos) into Kodi-
playable audio. No transcoding; the server just resolves YouTube URLs to
direct googlevideo audio URLs and hands them to Kodi.

---

## 2. Architecture Decision

**Why a resolve-and-serve proxy rather than native YouTube in Kodi?**

- YouTube keeps breaking native Kodi addons (bot detection, JS challenges).
- `yt-dlp` + `deno` solves YouTube's current challenge reliably.
- Kodi's built-in player handles a plain googlevideo `audio/mp4` URL with no
  extra codec work.

**Trade-off accepted:** googlevideo URLs expire and YouTube intermittently
serves dead signatures, so the server must verify + re-resolve. This is the
core complexity of the whole project (see Phase 3).

---

## 3. Phase 0: Prerequisites & Setup

- [x] `uv` project with `yt-dlp>=2026.7.4` as the only dependency
- [x] `deno` installed at `~/.deno/bin/deno` (yt-dlp JS runtime)
- [x] `.venv` created via `uv sync`

---

## 4. Phase 1: Core Server (v1.0)

- [x] `server.py` — `HTTPServer` + `ThreadingMixIn`, port 8778
- [x] `genres.json` — genre definitions with YouTube URLs
- [x] `resolve_stream_url()` — yt-dlp `-g` with `deno` runtime
- [x] `stream_cache` — in-memory URL cache keyed by genre
- [x] Static `.strm` / `.nfo` generation into `streams/`
- [x] `background_refresher()` — hourly re-resolve
- [x] Web UI with "Play on Kodi" button + JSON-RPC proxy

**Result:** server runs, resolves genres, serves `.strm` files.

---

## 5. Phase 2: Kodi Integration

- [x] `addon/default.py` — fetches genre list live from `/genres`
- [x] `addon/addon.xml` — `audio.music-server` plugin manifest
- [x] `deploy.py` — pexpect-based scp/ssh deploy to hcontrol.local
- [x] `kodi-setup.py` / `kodi-ssh-setup.py` — video source via JSON-RPC / SSH
- [x] Auto-start via crontab `@reboot` + `screen`

**Result:** genres browseable in Kodi, streams play.

---

## 6. Phase 3: Reliability Fixes (this session)

Three distinct problems were found and fixed.

### 6.1 Streams not updating in Kodi

**Symptom:** genre list in Kodi stale; `.strm` files on server were fresh.

**Root cause:** Kodi's video library DB (`MyVideos121.db`) had stale `path`
rows pointing at the *old* server address (`192.168.50.4:8080`) and a deleted
local copy (`/home/xbian/music/music-server/`), plus cached `.strm` entries for
deleted genres.

**Fix:**
- Removed the stale `path`/`files` rows and the orphaned local-copy dir.
- Kept only the current source (`http://192.168.50.147:8778/streams/`).

### 6.2 No sound from any stream

**Symptom:** Kodi decoded AAC and advanced the playhead but no audio.

**Root cause:** audio output routed to HDMI (ALSA `default` = card 0) instead
of the headphone jack (card 1).

**Fix:** set `audiooutput.audiodevice = ALSA:sysdefault:CARD=Headphones`
(live via JSON-RPC, then persisted to `guisettings.xml`).

### 6.3 Some genres play, others silent (403)

**Symptom:** 4 of 8 genres consistently silent (Cocktail Piano, Top 40,
Bossa Nova, 70s 80s 90s); the other 4 worked.

**Root cause:** YouTube intermittently (~50%) returns a *dead* `cps`-signed URL
that immediately 403s, even though `expire` says 6h. The server cached whatever
yt-dlp returned, so ~half the genres got a poisoned URL each refresh.

**Fix:**
- `_url_playable()` — probe each resolved URL with a Range request.
- `resolve_stream_url()` retries up to 4×, discarding 403 URLs.
- `REFRESH_INTERVAL` 3600→1800s; `STREAM_TTL` on-demand re-resolve.

**Result:** all 8 genres return 206 (playable).

---

## 7. Key Decisions & Risks

| Decision | Rationale | Risk |
|----------|-----------|------|
| Verify-then-cache URLs | YouTube serves dead URLs ~50% of the time for live restreams | adds ~1 Range request per resolve |
| 30-min refresh + 30-min TTL | live-restream signatures die faster than the old 1h refresh | still a window where a URL could die; mitigated by on-demand re-resolve |
| Headphone-jack audio | user does not use HDMI | needs re-pin if HDMI audio is ever used |
| Root → ubuntu crontab | keeps generated files ubuntu-owned | none |

---

## Timeline

| Phase | Status |
|-------|--------|
| 0 — Prerequisites | ✅ Done |
| 1 — Core server (v1.0) | ✅ Done |
| 2 — Kodi integration | ✅ Done |
| 3 — Reliability fixes | ✅ Done |
