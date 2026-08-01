#!/usr/bin/env python3
"""Configure Kodi to add the music server as a video source.

Usage: python3 kodi-setup.py [--check] [--xml] [--add]

Options:
  --check   Check if the source is already configured
  --xml     Print the sources.xml snippet
  --add     Attempt to add via JSON-RPC GUI navigation
  (default) Show status and instructions
"""

import json
import sys
import time
import urllib.request

KODI_URL = "http://192.168.50.149:8080/jsonrpc"
MUSIC_SERVER = "192.168.50.4"
MUSIC_SERVER_PORT = 8080
SOURCE_URL = f"http://{MUSIC_SERVER}:{MUSIC_SERVER_PORT}/streams/"
SOURCE_NAME = "Music Server"


def rpc(method, params=None):
    data = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        data["params"] = params
    req = urllib.request.Request(
        KODI_URL,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"  RPC error: {e}")
        return None


def get_sources(media="video"):
    result = rpc("Files.GetSources", {"media": media})
    if result:
        return result.get("result", {}).get("sources", [])
    return []


def source_exists():
    for s in get_sources():
        if MUSIC_SERVER in s.get("file", ""):
            return s
    return None


def show_sources():
    for media in ("video", "music"):
        sources = get_sources(media)
        if sources:
            print(f"  {media.title()} sources:")
            for s in sources:
                print(f"    {s.get('label', '?'):20s} -> {s.get('file', '?')}")
        else:
            print(f"  No {media} sources.")


def generate_xml():
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sources>
    <programs>
    </programs>
    <video>
        <source>
            <name>{SOURCE_NAME}</name>
            <path pathversion="1">{SOURCE_URL}</path>
        </source>
    </video>
    <music>
    </music>
    <pictures>
    </pictures>
</sources>"""


def try_add_source():
    """Navigate Kodi GUI to add the source via JSON-RPC."""
    print("Opening Videos window...")
    rpc("GUI.ActivateWindow", {"window": "videos"})
    time.sleep(2)

    # Try context menu approach (skin-dependent)
    print("Sending context menu...")
    rpc("Input.ContextMenu")
    time.sleep(2)

    # Navigate down to "Add source" (might work on Estuary skin)
    for _ in range(3):
        rpc("Input.Down")
        time.sleep(0.5)
    rpc("Input.Select")
    time.sleep(2)

    # Enter the URL
    print(f"Entering URL: {SOURCE_URL}")
    rpc("Input.SendText", {"text": SOURCE_URL, "done": True})
    time.sleep(1)
    rpc("Input.Select")
    time.sleep(1)

    # Enter the name
    print(f"Entering name: {SOURCE_NAME}")
    rpc("Input.SendText", {"text": SOURCE_NAME, "done": True})
    time.sleep(1)
    rpc("Input.Select")
    time.sleep(2)


def main():
    existing = source_exists()
    if existing:
        print(f"Source already configured: {existing['label']} -> {existing['file']}")
        return

    print(f"Music Server: {SOURCE_URL}")
    print()
    print("Current Kodi sources:")
    show_sources()
    print()
    print("To add the source, you have 3 options:")
    print()
    print("1. Kodi GUI (easiest):")
    print("   a. Open Kodi on your TV")
    print("   b. Videos > Files > 'Add videos...'")
    print(f"   c. Enter: {SOURCE_URL}")
    print(f"   d. Name: {SOURCE_NAME}")
    print("   e. OK")
    print()
    print("2. Via the Chorus2 web interface (if you see 'Add source'):")
    print(f"   Open http://192.168.50.149:8080/ in a browser")
    print("   Navigate: Videos > Files > Add videos...")
    print(f"   Enter URL: {SOURCE_URL}")
    print()
    print("3. Manual XML edit (SSH or filesystem access):")
    print("   Stop Kodi, edit sources.xml, restart Kodi")
    print("   File location: /storage/.kodi/userdata/sources.xml")
    print()
    print("XML snippet for sources.xml:")
    print(generate_xml())


if __name__ == "__main__":
    if "--check" in sys.argv:
        s = source_exists()
        print("exists" if s else "not found")
    elif "--xml" in sys.argv:
        print(generate_xml())
    elif "--add" in sys.argv:
        try_add_source()
        time.sleep(2)
        if source_exists():
            print("Source added successfully!")
        else:
            print("Could not add source via GUI navigation.")
            print("Try option 1 (Kodi GUI on TV) or option 3 (XML edit).")
    else:
        main()