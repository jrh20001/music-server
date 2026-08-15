# Processing Description — Music Server

This document explains the audio-stream resolution pipeline. The Music Server
serves YouTube genre streams to Kodi as `.strm`/`.nfo` files over HTTP, and the
Kodi addon (`audio.music-server`) resolves them into playable audio.

```
genres.json → yt-dlp resolve → verify playable → stream_cache
              ↓
      .strm/.nfo files (streams/)   ← served over HTTP (port 8778)
              ↓
      Kodi addon / video source → plays googlevideo audio URL
```

---

## 1. Genre Configuration

`genres.json` maps a genre key to a display name, description, and a YouTube
URL:

```json
{
  "smooth-jazz": {
    "name": "Smooth Jazz",
    "description": "…",
    "youtube_url": "https://www.youtube.com/watch?v=rAPcQyJrqck",
    "thumbnail": ""
  }
}
```

If `youtube_url` is empty, the server auto-searches YouTube for
`"{genre name} live stream music"`.

Most genre URLs point at long "24/7" live-restream videos (e.g. "LIVE 24/7:
Cozy Jazz Lounge"). These behave like live streams on YouTube's delivery
backend even though `yt-dlp` reports them as `was_live` / `not_live`.

---

## 2. URL Resolution

`resolve_stream_url()` is the core function. It first tries an Inception API
(if `INCEPTION_API_KEY` is set), then falls back to `yt-dlp`.

### 2.1 Radio-mix parameter stripping

`plain_video_url()` strips `list=RD*`, `start_radio`, and `t` query params
from auto-generated radio-mix URLs. YouTube throttles `yt-dlp` on these mixes;
the plain video resolves the same stream.

### 2.2 Format selection

```python
YTDLP_FMT = "bestaudio[ext=m4a]/bestaudio/best"
```

Prefers audio-only m4a (itag 140, ~129k AAC), falls back to any audio, then
best combined.

### 2.3 Verification + retry (critical fix)

The resolved googlevideo URL carries a `cps` (content protection signature)
and a `met` (media timestamp). For long live-restream videos, YouTube
**intermittently (~50%) returns a URL that immediately 403s**, even though the
`expire` field claims 6 hours.

```python
def _url_playable(url):
    # Range request; accept only 200/206
```

`resolve_stream_url()` loops up to 4 attempts: resolve → `_url_playable()`
probe → discard dead URLs → retry (2s backoff). Only a verified-playable URL
is ever returned and cached.

Without this check, roughly half the genres cached a poisoned URL and stayed
silent until the next refresh — the root cause of "4 streams play, 4 don't."

---

## 3. Caching & Refresh

| Mechanism | Value | Purpose |
|-----------|-------|---------|
| `stream_cache` | in-memory dict | `genre_key → {url, resolved_at}` |
| `REFRESH_INTERVAL` | 1800s (30 min) | background re-resolve of all genres |
| `STREAM_TTL` | 1800s (30 min) | on-demand re-resolve when served URL is stale |

`background_refresher()` re-resolves everything every 30 min and regenerates
static files. `_serve_strm()` also re-resolves on demand if the cached URL is
older than `STREAM_TTL`, so Kodi never gets a URL that has aged out.

---

## 4. Static File Generation

`generate_static_files()` writes, for each resolved genre:

- `streams/{key}.strm` — the playable audio URL (one line)
- `streams/{key}.nfo` — XML `<musicvideo>` metadata
- `streams/playlist.m3u` — combined M3U playlist

Genres that fail to resolve are skipped (no stale URL is served), and `.strm`/
`.nfo` files for removed genres are deleted.

---

## 5. HTTP Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Web UI |
| `GET /health` | status, resolved genre list, uptime |
| `GET /genres` | JSON genre list with stream URLs |
| `GET /streams/{key}.strm` | audio stream URL (verified, re-resolves stale) |
| `GET /streams/{key}.nfo` | NFO metadata |
| `GET /playlist.m3u` | M3U playlist |
| `GET /refresh` | force re-resolve |
| `POST /kodi` | JSON-RPC proxy to Kodi |

---

## 6. Kodi Side

The addon (`addon/default.py`) fetches the genre list live from `/genres` and
resolves each stream via `/streams/{key}.strm` at play time. It sets
`setResolvedUrl()` with the googlevideo URL and mime `audio/mp4`.

Audio output is routed to the Raspberry Pi headphone jack
(`ALSA:sysdefault:CARD=Headphones`), not HDMI.

---

## Known Limitations

| Issue | Cause | Mitigation |
|-------|-------|-----------|
| Intermittent 403 on resolve | YouTube serves dead `cps` URLs ~50% of the time for live restreams | verify + 4× retry in `resolve_stream_url` |
| URL expiry before refresh | live-restream signatures die faster than 30 min | `STREAM_TTL` on-demand re-resolve |
| Kodi caches file-source listing | Kodi doesn't auto-refresh HTTP directory listings | browse via addon, or re-open the source |
