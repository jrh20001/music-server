# Music Server

Serves YouTube genre audio streams to Kodi via STRM/NFO files. Web UI at port 8778 with one-click play on Kodi.

## Architecture

```
hcontrol.local (192.168.50.147)          xbian.local (192.168.50.149)
┌──────────────────────────────┐        ┌────────────────────────┐
│  Music Server (port 8778)   │        │  Kodi 20.2 (Nexus)     │
│                              │        │                        │
│  ┌──────────────────────┐   │        │  ┌──────────────────┐  │
│  │  yt-dlp resolves    │   │ .strm  │  │  Kodi Player     │  │
│  │  YouTube URLs to    │◄──┼────────┼──┤  plays audio     │  │
│  │  direct audio URLs  │   │        │  │  stream          │  │
│  └──────────────────────┘   │        │  └──────────────────┘  │
│         │                   │        │                        │
│  ┌──────▼────────────────┐  │        │  ┌──────────────────┐  │
│  │  stream_cache +       │  │ JSON   │  │  JSON-RPC API    │  │
│  │  static .strm files   │──┼──RPC───┼──┤  (port 8080)     │  │
│  └───────────────────────┘  │        │  └──────────────────┘  │
│         │                   │        │                        │
│  ┌──────▼────────────────┐  │        │  ┌──────────────────┐  │
│  │  Web UI (port 8778)  │  │ HTTP   │  │  Chorus 2 Web    │  │
│  │  One-click play      │──┼────────┼──┤  Interface       │  │
│  └───────────────────────┘  │        │  └──────────────────┘  │
└──────────────────────────────┘        └────────────────────────┘
```

## How it works

1. **Music Server** runs on `hcontrol.local` (port 8778). It uses `yt-dlp` to resolve YouTube video URLs into direct audio stream URLs (m4a format).

2. **Stream URLs** are cached in memory and written to static `.strm` files in the `streams/` directory. The background refresher re-resolves URLs every 30 minutes, and stale URLs are re-resolved on demand when served.

3. **URL verification**: each resolved URL is probed with a Range request before being cached. YouTube intermittently returns dead `cps`-signed URLs (~50% of the time) for long "24/7" live-restream videos; those are discarded and re-resolved (up to 4 attempts) so a poisoned URL is never served.

4. **Web UI** at `http://hcontrol.local:8778/` shows all genres. Clicking "Play on Kodi" fetches the fresh `.strm` URL and sends it to Kodi's JSON-RPC API.

5. **Kodi addon** (`audio.music-server`) lets you browse genres from within Kodi's UI. It fetches the `.strm` URL from the server and resolves it as a playable item. Audio output is routed to the Raspberry Pi headphone jack.

6. **Kodi web interface** (Chorus 2) at `http://xbian.local:8080/` can also browse and play streams.

## Setup

### Prerequisites

- Python 3.12+
- `yt-dlp` with `deno` for JavaScript runtime (YouTube URL extraction)
- A Kodi installation (tested on Kodi 20.2 Nexus / XBian 11.0 Bookworm)

### Quick start

```bash
# Clone and install
git clone https://github.com/jrh20001/music-server.git
cd music-server
uv sync              # or: pip install yt-dlp

# Start the server
python3 server.py
```

The server starts on port 8778. Open `http://localhost:8778/` in a browser.

### Adding to Kodi

**Option 1: Web UI (easiest)**
Open `http://hcontrol.local:8778/` and click any genre to play it on Kodi immediately.

**Option 2: Kodi addon**
Copy the `addon/` directory to Kodi's addons folder (`/home/xbian/.kodi/addons/audio.music-server/`). The addon appears in Kodi under Addons > My addons > Audio > Music Server Streams.

**Option 3: STRM files as a source**
1. In Kodi: Videos > Files > Add source
2. Enter: `http://hcontrol.local:8778/streams/`
3. Name: "Music Server"
4. Browse and play any `.strm` file

**Option 4: M3U playlist (IPTV Simple Client)**
Add `http://hcontrol.local:8778/playlist.m3u` as an IPTV Simple Client playlist source.

### Auto-start on reboot

The server is started via the `ubuntu` user's crontab (not root, so generated files stay `ubuntu`-owned):

```bash
(crontab -l 2>/dev/null; echo '@reboot sleep 20 && cd /home/ubuntu/music-server && screen -dmS ms .venv/bin/python server.py') | crontab -
```

## Genre configuration

Edit `genres.json` to add, remove, or change streams:

```json
{
  "genre-key": {
    "name": "Display Name",
    "description": "Short description shown in the UI",
    "youtube_url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "thumbnail": ""
  }
}
```

If `youtube_url` is empty, the server auto-searches YouTube for `"{genre name} live stream music"`.

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Web UI with genre cards |
| `GET /health` | Server status, resolved genres, uptime |
| `GET /genres` | JSON list of all genres with stream URLs |
| `GET /streams/{key}.strm` | Audio stream URL for a genre |
| `GET /streams/{key}.nfo` | NFO metadata for a genre |
| `GET /playlist.m3u` | M3U playlist of all genres |
| `GET /refresh` | Re-resolve all YouTube URLs |
| `POST /kodi` | Proxy JSON-RPC call to Kodi |

## Troubleshooting

**Some genres play, others are silent (403)**
YouTube intermittently serves dead `cps`-signed URLs for long live-restream videos. The server verifies every URL before caching and retries up to 4 times — so a silent genre should resolve on the next refresh. Force it with `http://hcontrol.local:8778/refresh`.

**No sound from any stream**
Kodi's audio device may be routed to HDMI instead of the headphone jack. Check Settings > System > Audio > Audio output device, and set it to the headphone device (`ALSA:sysdefault:CARD=Headphones` on XBian).

**Kodi shows stale genre names**
The Kodi video-source listing is cached. Re-open the "Music Server" source, or browse via the addon (Addons > Music Server Streams), which fetches live.

**Kodi crashes with "two concurrent busydialogs"**
The addon includes a global `_playing` lock to prevent concurrent play attempts.

**Stream returns HTTP 403**
Live-restream URLs expire quickly. The server re-resolves on a 30-min TTL and verifies before caching.

**Kodi web interface not reachable**
Kodi must be running with webserver enabled. Check `http://xbian.local:8080/`. If Kodi crashed, restart it:
```bash
ssh xbian@xbian.local 'pkill -9 kodi; nohup /usr/local/lib/kodi/kodi-rbpi --standalone -fs >/dev/null 2>&1 &'
```

## Files

| File | Purpose |
|------|---------|
| `server.py` | Main HTTP server with stream resolution, cache, static files, web UI |
| `genres.json` | Genre definitions with YouTube URLs |
| `addon/default.py` | Kodi addon for browsing genres in Kodi UI |
| `addon/addon.xml` | Kodi addon manifest |
| `deploy.py` | Deploy script to hcontrol.local |
| `kodi-setup.py` | Configure Kodi video source via JSON-RPC |
| `kodi-ssh-setup.py` | Configure Kodi video source via SSH |
| `streams/` | Generated .strm and .nfo files |
| `PROCESSING-DESCRIPTION.md` | Stream resolution pipeline detail |
| `SW-Development.md` | Development plan and decisions |
| `build-transcript.md` | Deployment and fix transcript |
| `session-transcript.md` | Full troubleshooting session log |
