#!/usr/bin/env python3
"""Kodi addon: Music Server Streams - YouTube genre streams."""

import sys
import urllib.request

import xbmc
import xbmcgui
import xbmcplugin

ADDON_ID = "audio.music-server"
MUSIC_SERVER = "http://192.168.50.147:8778"

GENRES = [
    ("smooth-jazz", "Smooth Jazz", "Smooth jazz & soulful R&B instrumentals"),
    ("cocktail-piano", "Cocktail Piano", "Cozy jazz lounge with fireplace & rain"),
    ("top-40", "Top 40 Hits", "Billboard Hot 100 pop hits"),
    ("romantic-accordion", "Romantic Paris Accordion", "Romantic French accordion & piano"),
    ("paris-cafe", "Paris Cafe", "Parisian cafe music with accordion & jazz guitar"),
    ("acoustic-jazz-guitar", "Acoustic Jazz Guitar", "Bossa nova acoustic jazz guitar"),
    ("bossa-nova-jazz", "Bossa Nova Jazz", "Smooth bossa nova jazz for relaxation"),
    ("santana-late-night", "Santana Late Night", "Latin blues rock guitar late night vibes"),
    ("brazilian-jazz-fusion", "Brazilian Jazz Fusion", "Latin nu jazz fusion with bossa nova"),
    ("60s-70s", "60s and 70s", "Golden oldies classic hits from the 60s and 70s"),
]


def get_stream_url(genre_key):
    """Fetch the resolved audio URL from the .strm file."""
    try:
        req = urllib.request.Request(f"{MUSIC_SERVER}/streams/{genre_key}.strm")
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.read().decode().strip()
    except Exception:
        return None


def show_genres():
    """Show the genre listing as playable items."""
    items = []
    for key, name, desc in GENRES:
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
    name = next((n for k, n, _ in GENRES if k == genre), genre)

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