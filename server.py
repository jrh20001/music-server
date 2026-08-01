#!/usr/bin/env python3
"""Music Server - Stream YouTube genre audio to Kodi via STRM/NFO files."""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "genres.json"
STREAMS_DIR = ROOT / "streams"
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8778"))
REFRESH_INTERVAL = int(os.environ.get("REFRESH_INTERVAL", "3600"))

# Resolve yt-dlp and deno paths
_YTDLP = os.getenv("YTDLP", str(ROOT / ".venv/bin/yt-dlp"))
_DENO = os.getenv("DENO", str(Path.home() / ".deno/bin/deno"))

genres = {}
stream_cache = {}  # genre_key -> {"url": str, "resolved_at": float}


def load_genres():
    global genres
    with open(CONFIG_PATH) as f:
        genres = json.load(f)


YTDLP_FMT = "bestaudio[ext=m4a]/bestaudio/best"


def resolve_stream_url(youtube_url):
    """Get the best audio stream URL from a YouTube video.
    Tries Inception API first (if INCEPTION_API_KEY is set), then falls back to yt-dlp.
    Prefers audio-only m4a, falls back to any audio, then best combined."""
    # Try Inception provider if API key is available
    inception_key = os.getenv("INCEPTION_API_KEY")
    if inception_key:
        try:
            # Placeholder endpoint – replace with actual Inception API URL
            endpoint = f"https://api.inception.ai/v1/resolve?url={urllib.parse.quote(youtube_url)}&api_key={inception_key}"
            with urllib.request.urlopen(endpoint, timeout=30) as resp:
                data = json.load(resp)
                # Expecting JSON response with a 'stream_url' field
                url = data.get("stream_url")
                if url:
                    return url
                else:
                    print(f"  Inception API did not return stream_url for {youtube_url}")
        except Exception as e:
            print(f"  Inception API error: {e}")
    # Fallback to yt-dlp (with deno runtime)
    try:
        cmd = [_YTDLP, "--js-runtimes", f"deno:{_DENO}", "-g", "-f", YTDLP_FMT, youtube_url]
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
        )
        url = result.stdout.strip()
        if url:
            return url
        if result.stderr:
            print(f"  yt-dlp stderr: {result.stderr.strip()}")
    except FileNotFoundError:
        print("  ERROR: yt-dlp not found.")
    except subprocess.TimeoutExpired:
        print(f"  Timeout resolving {youtube_url}")
    except Exception as e:
        print(f"  Error: {e}")
    return None


def resolve_or_search(url, genre_name):
    """Resolve a direct URL, or search YouTube by name if url is empty/missing."""
    if url:
        return resolve_stream_url(url)
    # Auto-search: find a live stream matching the genre name
    search_query = f"ytsearch:{genre_name} live stream music"
    print(f"  No URL given, searching '{genre_name}'...")
    return resolve_stream_url(search_query)


def refresh_all_streams():
    """Resolve stream URLs for all genres."""
    now = time.time()
    for key, genre in genres.items():
        url = genre.get("youtube_url", "")
        print(f"Resolving {genre['name']}...")
        stream_url = resolve_or_search(url, genre["name"])
        if stream_url:
            stream_cache[key] = {"url": stream_url, "resolved_at": now}
            print(f"  OK: {genre['name']}")
        else:
            print(f"  FAILED: {genre['name']}")
            if key in stream_cache:
                print(f"  Keeping previous URL for {genre['name']}")


def background_refresher():
    """Periodically refresh stream URLs in the background."""
    while True:
        time.sleep(REFRESH_INTERVAL)
        print(f"\n[{datetime.now().isoformat()}] Refreshing stream URLs...")
        refresh_all_streams()


def get_stream_url(key):
    """Get cached stream URL, resolving if needed."""
    if key in stream_cache:
        return stream_cache[key]["url"]
    return None


def get_nfo_content(key, genre):
    """Generate NFO XML metadata for a genre stream."""
    return f"""<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<musicvideo>
  <title>{genre['name']}</title>
  <artist>Music Server</artist>
  <album>Genre Streams</album>
  <genre>{genre['name']}</genre>
  <year>{datetime.now().year}</year>
  <description>{genre.get('description', '')}</description>
</musicvideo>"""


def generate_static_files():
    """Generate static STRM + NFO files to the streams/ directory."""
    STREAMS_DIR.mkdir(exist_ok=True)
    index = []
    for key, genre in genres.items():
        url = get_stream_url(key)
        if not url:
            print(f"  Skipping {genre['name']} (no URL resolved)")
            continue

        safe_name = key
        strm_path = STREAMS_DIR / f"{safe_name}.strm"
        nfo_path = STREAMS_DIR / f"{safe_name}.nfo"

        strm_path.write_text(url)
        nfo_path.write_text(get_nfo_content(key, genre))
        print(f"  Generated: {strm_path.name} + {nfo_path.name}")
        index.append((safe_name, genre))

    # Generate a combined M3U playlist
    m3u_path = STREAMS_DIR / "playlist.m3u"
    with open(m3u_path, "w") as f:
        f.write("#EXTM3U\n")
        for key, genre in index:
            url = get_stream_url(key)
            f.write(f'#EXTINF:-1,{genre["name"]}\n')
            f.write(f"{url}\n")
    print(f"  Generated: {m3u_path.name}")

    # Generate album.nfo for the directory
    album_nfo = STREAMS_DIR / "album.nfo"
    album_nfo.write_text(f"""<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<album>
  <title>Music Server Streams</title>
  <artist>Music Server</artist>
  <genre>Various</genre>
  <description>YouTube genre streams served by Music Server</description>
</album>""")

    print(f"\nGenerated {len(index)} stream(s) in {STREAMS_DIR}")
    return index


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        """Handle HEAD requests same as GET but without body."""
        self._head_only = True
        self.do_GET()
        self._head_only = False

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/" or path == "":
            self._serve_ui()
        elif path == "/health":
            self._serve_health()
        elif path == "/genres":
            self._serve_genres()
        elif path == "/playlist.m3u":
            self._serve_m3u()
        elif path.startswith("/streams/") and path.endswith(".strm"):
            key = path[len("/streams/"):-len(".strm")]
            self._serve_strm(key)
        elif path.startswith("/streams/") and path.endswith(".nfo"):
            key = path[len("/streams/"):-len(".nfo")]
            self._serve_nfo(key)
        elif path == "/streams" or path == "/streams/":
            self._serve_streams_dir()
        elif path == "/kodi":
            self._serve_kodi()
        elif path == "/refresh":
            self._serve_refresh()
        else:
            self._serve_404()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path == "/kodi":
            self._serve_kodi_post()
        else:
            self._serve_404()

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(body)

    def _send_text(self, text, content_type="text/plain", status=200):
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not getattr(self, '_head_only', False):
            self.wfile.write(body)

    def _serve_ui(self):
        items = []
        for key, genre in genres.items():
            url = get_stream_url(key)
            status = "resolved" if url else "pending"
            items.append(f"""
        <div class="genre-card">
            <h2>{genre['name']}</h2>
            <p>{genre.get('description', '')}</p>
            <div class="status status-{status}">{"ready" if url else "pending"}</div>
            <button class="play-btn" data-key="{key}">Play on Kodi</button>
            <div class="links">
                <a href="/streams/{key}.strm">.strm</a>
                <a href="/streams/{key}.nfo">.nfo</a>
            </div>
        </div>""")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Music Server</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, system-ui, sans-serif; background: #111; color: #eee; padding: 20px; }}
h1 {{ font-size: 1.5rem; margin-bottom: 4px; }}
.subtitle {{ color: #888; margin-bottom: 24px; font-size: 0.9rem; }}
.genre-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }}
.genre-card {{ background: #1a1a2e; border: 1px solid #333; border-radius: 8px; padding: 20px; }}
.genre-card h2 {{ font-size: 1.1rem; margin-bottom: 8px; color: #fff; }}
.genre-card p {{ font-size: 0.85rem; color: #aaa; margin-bottom: 12px; }}
.status {{ display: inline-block; font-size: 0.75rem; padding: 2px 8px; border-radius: 4px; margin-bottom: 12px; }}
.status-resolved {{ background: #1a3a1a; color: #4caf50; }}
.status-pending {{ background: #3a3a1a; color: #ff9800; }}
.play-btn {{ display: block; width: 100%%; padding: 10px; background: #4caf50; color: #fff; border: none; border-radius: 6px; font-size: 0.95rem; cursor: pointer; margin-bottom: 12px; }}
.play-btn:active {{ background: #388e3c; }}
.play-btn.playing {{ background: #f44336; }}
.play-btn:disabled {{ opacity: 0.6; cursor: wait; }}
.links {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.links a {{ color: #64b5f6; text-decoration: none; font-size: 0.85rem; padding: 4px 8px; border: 1px solid #333; border-radius: 4px; }}
.links a:hover {{ background: #333; }}
.footer {{ margin-top: 24px; font-size: 0.8rem; color: #666; }}
.footer a {{ color: #666; }}
#status {{ margin: 12px 0; padding: 10px; border-radius: 6px; display: none; }}
#status.info {{ background: #1a3a1a; color: #4caf50; display: block; }}
#status.error {{ background: #3a1a1a; color: #f44336; display: block; }}
</style>
</head>
<body>
<h1>Music Server</h1>
<p class="subtitle">Click a genre to play it on Kodi at <strong>xbian.local</strong> &middot; <a href="/refresh">Refresh streams</a></p>
<div id="status"></div>
<div class="genre-grid" id="grid">{"".join(items)}</div>
<div class="footer">
    <a href="/playlist.m3u">M3U Playlist</a> &middot; <a href="/health">Health</a>
</div>
<script>
async function kodi(method, params) {{
    const r = await fetch('/kodi', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{jsonrpc:'2.0', id:1, method, params}})
    }});
    return r.json();
}}

async function playGenre(key) {{
    const btn = document.querySelector('.play-btn[data-key="' + key + '"]');
    if (!btn) return;
    btn.textContent = 'Loading...';
    btn.disabled = true;

    try {{
        const resp = await fetch('/streams/' + key + '.strm');
        const url = await resp.text();
        const result = await kodi('Player.Open', {{
            item: {{ file: url.trim() }}
        }});

        if (result.result === 'OK') {{
            showStatus('Now playing: ' + key, 'info');
            btn.textContent = '\u25A0 Playing';
            btn.classList.add('playing');
        }} else {{
            showStatus('Failed: ' + JSON.stringify(result.error), 'error');
            btn.textContent = 'Play on Kodi';
        }}
    }} catch(e) {{
        showStatus('Error: ' + e.message, 'error');
        btn.textContent = 'Play on Kodi';
    }}
    btn.disabled = false;
}}

function showStatus(msg, type) {{
    const el = document.getElementById('status');
    el.textContent = msg;
    el.className = type;
}}

// Handle clicks on play buttons
document.addEventListener('click', function(e) {{
    const btn = e.target.closest('.play-btn');
    if (btn) playGenre(btn.dataset.key);
}});
</script>
</body>
</html>"""
        self._send_text(html, "text/html")

    def _serve_health(self):
        data = {
            "status": "ok",
            "genres": list(genres.keys()),
            "resolved": list(stream_cache.keys()),
            "uptime": time.time() - self.server.start_time,
        }
        self._send_json(data)

    def _serve_genres(self):
        """Return full genre list with names, descriptions, and stream status."""
        data = {}
        for key, genre in genres.items():
            url = get_stream_url(key) or (STREAMS_DIR / f"{key}.strm").read_text().strip() if (STREAMS_DIR / f"{key}.strm").exists() else None
            data[key] = {
                "name": genre["name"],
                "description": genre.get("description", ""),
                "youtube_url": genre.get("youtube_url", ""),
                "stream_url": url,
                "resolved": key in stream_cache,
            }
        self._send_json(data)

    def _serve_m3u(self):
        lines = ["#EXTM3U"]
        for key, genre in genres.items():
            url = get_stream_url(key)
            if url:
                lines.append(f'#EXTINF:-1,{genre["name"]}')
                lines.append(url)
        self._send_text("\n".join(lines), "audio/x-mpegurl")

    def _serve_strm(self, key):
        if key not in genres:
            return self._serve_404()
        # Check cache first (fresh URLs from refresh)
        url = get_stream_url(key)
        if url:
            self._send_text(url, "text/plain")
            return
        # Fallback to static .strm file
        strm_path = STREAMS_DIR / f"{key}.strm"
        if strm_path.exists():
            url = strm_path.read_text().strip()
            if url:
                stream_cache[key] = {"url": url, "resolved_at": time.time()}
                self._send_text(url, "text/plain")
                return
        # Try resolving on demand
        print(f"On-demand resolve for {key}")
        url = resolve_or_search(genres[key].get("youtube_url", ""), genres[key]["name"])
        if url:
            stream_cache[key] = {"url": url, "resolved_at": time.time()}
        if not url:
            return self._send_text("Stream URL not available", "text/plain", 503)
        self._send_text(url, "text/plain")

    def _serve_nfo(self, key):
        if key not in genres:
            return self._serve_404()
        nfo = get_nfo_content(key, genres[key])
        self._send_text(nfo, "application/xml")

    def _serve_streams_dir(self):
        """Serve an HTML directory listing of STRM files."""
        items = []
        for key, genre in genres.items():
            strm_path = STREAMS_DIR / f"{key}.strm"
            url = get_stream_url(key) or (strm_path.read_text().strip() if strm_path.exists() else None)
            if url:
                items.append(f"<li><a href='/streams/{key}.strm'>{key}.strm</a> &mdash; {genre['name']}</li>")
                items.append(f"<li><a href='/streams/{key}.nfo'>{key}.nfo</a> &mdash; metadata</li>")
        html = f"""<!DOCTYPE html>
<html><head><title>Music Server - Streams</title></head>
<body><h1>Streams</h1><ul>{"".join(items)}</ul></body></html>"""
        self._send_text(html, "text/html")

    def _serve_refresh(self):
        self._send_text("Refreshing... check /health for status", "text/plain")
        threading.Thread(target=lambda: [refresh_all_streams(), generate_static_files()], daemon=True).start()

    def _serve_kodi(self):
        """Proxy GET to Kodi JSON-RPC (for health check)."""
        try:
            req = urllib.request.Request(
                "http://xbian.local:8080/jsonrpc",
                data=b'{"jsonrpc":"2.0","id":1,"method":"JSONRPC.Version"}',
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=5)
            self._send_text(resp.read().decode(), "application/json")
        except Exception as e:
            self._send_json({"error": str(e)}, 502)

    def _serve_kodi_post(self):
        """Proxy POST to Kodi JSON-RPC."""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            req = urllib.request.Request(
                "http://xbian.local:8080/jsonrpc",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=30)
            self._send_text(resp.read().decode(), "application/json")
        except urllib.error.URLError as e:
            self._send_json({"error": "kodi_unreachable"}, 502)
        except Exception as e:
            self._send_json({"error": str(e)}, 502)

    def _serve_404(self):
        self._send_text("Not Found", "text/plain", 404)

    def log_message(self, format, *args):
        if len(args) >= 3:
            print(f"[{datetime.now().isoformat()}] {args[0]} {args[1]} {args[2]}")
        elif len(args) >= 1:
            print(f"[{datetime.now().isoformat()}] {" ".join(str(a) for a in args)}")


class MusicServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_time = time.time()


def main():
    load_genres()
    print(f"Loaded {len(genres)} genre(s): {', '.join(genres.keys())}")

    STREAMS_DIR.mkdir(exist_ok=True)

    print("Resolving stream URLs...")
    refresh_all_streams()

    # Start background refresher
    refresher = threading.Thread(target=background_refresher, daemon=True)
    refresher.start()

    # Generate static files
    print("\nGenerating static STRM/NFO files...")
    generate_static_files()

    print(f"\nStarting server on http://{HOST}:{PORT}")
    print(f"  Web UI:    http://{HOST}:{PORT}/")
    print(f"  Playlist:  http://{HOST}:{PORT}/playlist.m3u")
    print(f"  Streams:   http://{HOST}:{PORT}/streams/")
    print(f"  Health:    http://{HOST}:{PORT}/health")
    print(f"\nKodi setup:")
    print(f"  1. Add 'http://{HOST}:{PORT}/streams/' as a file source (Videos > Files > Add source)")
    print(f"  2. Browse to the directory and play .strm files")
    print(f"  OR: Use /playlist.m3u with IPTV Simple Client addon")
    print(f"\nStatic files also available in: {STREAMS_DIR}")
    print("  Copy these to a SMB/NFS share for Kodi library integration.")

    server = MusicServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
