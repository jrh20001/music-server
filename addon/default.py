#!/usr/bin/env python3
"""Kodi addon: Music Server Streams - YouTube genre streams.

Genre list is fetched live from the music server every time the addon is
opened, so genres.json edits on the server show up in Kodi immediately.
"""

import json
import sys
import urllib.request

import xbmcgui
import xbmcplugin

ADDON_ID = "audio.music-server"
MUSIC_SERVER = "http://192.168.50.147:8778"

# Only used if the music server is unreachable
FALLBACK_GENRES = [
    ("smooth-jazz", "Smooth Jazz", "Smooth jazz & soulful R&B instrumentals"),
    ("cocktail-piano", "Cocktail Piano", "Cozy jazz lounge with fireplace & rain"),
    ("top-40", "Top 40 Hits", "Billboard Hot 100 pop hits"),
]


def fetch_genres():
    """Fetch the live genre list from the music server."""
    try:
        req = urllib.request.Request(f"{MUSIC_SERVER}/genres")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return [(k, g.get("name", k), g.get("description", ""))
                for k, g in data.items()]
    except Exception:
        return None


def get_stream_url(genre_key):
    """Fetch the resolved audio URL from the .strm file."""
    try:
        req = urllib.request.Request(f"{MUSIC_SERVER}/streams/{genre_key}.strm")
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.read().decode().strip()
    except Exception:
        return None


def show_genres():
    """Show the genre listing as playable items (fetched live from server)."""
    genres = fetch_genres() or FALLBACK_GENRES
    items = []
    for key, name, desc in genres:
        # Use a plugin URL so Kodi calls our addon to resolve the stream
        url = f"plugin://{ADDON_ID}/?action=play&genre={key}"

        li = xbmcgui.ListItem(label=name, path=url)
        li.setInfo("music", {"title": name, "genre": name, "comment": desc})
        li.setProperty("IsPlayable", "true")
        li.setContentLookup(False)

        items.append((url, li, False))

    xbmcplugin.addDirectoryItems(int(sys.argv[1]), items, len(items))
    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


def play_genre(genre):
    """Play a genre by resolving the .strm URL to the actual audio stream."""
    handle = int(sys.argv[1])
    genres = fetch_genres() or FALLBACK_GENRES
    name = next((n for k, n, _ in genres if k == genre), genre)

    # Fetch the resolved stream URL from the .strm file
    stream_url = get_stream_url(genre)
    if not stream_url:
        li = xbmcgui.ListItem(label=name, path="")
        xbmcplugin.setResolvedUrl(handle, False, li)
        return

    li = xbmcgui.ListItem(label=name, path=stream_url)
    li.setInfo("music", {"title": name, "genre": genre})
    li.setProperty("IsPlayable", "true")
    li.setMimeType("audio/mp4")
    li.setContentLookup(False)
    xbmcplugin.setResolvedUrl(handle, True, li)


def main():
    handle = int(sys.argv[1])

    if len(sys.argv) > 2 and sys.argv[2]:
        params = dict(arg.split("=") for arg in sys.argv[2].lstrip("?").split("&") if "=" in arg)
        action = params.get("action")
        genre = params.get("genre")

        if action == "play" and genre:
            play_genre(genre)
            return

    show_genres()


if __name__ == "__main__":
    main()