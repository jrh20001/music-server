#!/usr/bin/env python3
"""SSH into Kodi and add the music server as a video source.

Usage: source .venv/bin/activate && python3 kodi-ssh-setup.py
"""

import sys
import os

# Try to import paramiko, give clear error if in wrong venv
try:
    import paramiko
except ImportError:
    print("Error: paramiko not found. Activate the virtual environment first:")
    print("  source .venv/bin/activate")
    print("  python3 kodi-ssh-setup.py")
    sys.exit(1)

KODI_HOST = "xbian.local"
KODI_USER = "xbian"
KODI_PASS = "pi120741"
SOURCE_URL = "http://192.168.50.4:8080/streams/"
SOURCE_NAME = "Music Server"


def ssh_run(cmd):
    """Run a command on the Kodi box via SSH and return stdout."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(KODI_HOST, username=KODI_USER, password=KODI_PASS,
                   allow_agent=False, look_for_keys=False, timeout=10)
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode().strip()
    client.close()
    return out


def find_sources_xml():
    """Find the sources.xml file on the Kodi box."""
    paths = [
        "~/.kodi/userdata/sources.xml",
        "/storage/.kodi/userdata/sources.xml",
        "/home/xbian/.kodi/userdata/sources.xml",
    ]
    for path in paths:
        result = ssh_run(f"test -f {path} && echo 'EXISTS:{path}'")
        if "EXISTS:" in result:
            found = [l for l in result.split("\n") if "EXISTS:" in l]
            if found:
                return found[0].split(":", 1)[1]
    return None


def add_source_via_ssh():
    """Add the music server source via SSH."""
    print(f"Connecting to {KODI_USER}@{KODI_HOST}...")

    # Find the sources.xml
    xml_path = find_sources_xml()
    if not xml_path:
        print("sources.xml not found. Creating default...")
        xml_path = "~/.kodi/userdata/sources.xml"
        ssh_run(f"""cat > {xml_path} << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<sources>
    <programs>
    </programs>
    <video>
    </video>
    <music>
    </music>
    <pictures>
    </pictures>
</sources>
EOF""")
        print("  Created default sources.xml")

    # Check if source already exists
    check = ssh_run(f"grep -q '{SOURCE_URL}' {xml_path} && echo 'ALREADY_EXISTS' || echo 'NOT_FOUND'")
    if "ALREADY_EXISTS" in check:
        print("Source already configured. No changes needed.")
        return True

    print(f"Adding source to {xml_path}...")

    # Use the Kodi box's Python to edit the XML (reliable)
    script = f"""
import xml.etree.ElementTree as ET
import os

path = os.path.expanduser('{xml_path}')
try:
    tree = ET.parse(path)
    root = tree.getroot()
except (ET.ParseError, FileNotFoundError):
    root = ET.Element('sources')
    ET.SubElement(root, 'programs')
    ET.SubElement(root, 'video')
    ET.SubElement(root, 'music')
    ET.SubElement(root, 'pictures')
    tree = ET.ElementTree(root)

video = root.find('video')
if video is None:
    video = ET.SubElement(root, 'video')

# Check if already exists
for source in video.findall('source'):
    for p in source.findall('path'):
        if '{SOURCE_URL}' in (p.text or ''):
            print('ALREADY_EXISTS')
            exit(0)

source = ET.SubElement(video, 'source')
name = ET.SubElement(source, 'name')
name.text = '{SOURCE_NAME}'
path_elem = ET.SubElement(source, 'path')
path_elem.text = '{SOURCE_URL}'
path_elem.set('pathversion', '1')

xml_str = ET.tostring(root, encoding='unicode', xml_declaration=True)
with open(path, 'w') as f:
    f.write(xml_str)

print('ADDED')
"""

    result = ssh_run(f"python3 << 'PYEOF'\n{script}\nPYEOF")

    if "ALREADY_EXISTS" in result:
        print("Source already configured.")
        return True
    elif "ADDED" in result:
        print("Source added successfully to sources.xml!")
        print()
        print("Restart Kodi for changes to take effect:")
        print("  ssh xbian@xbian.local 'sudo systemctl restart kodi'")
        return True
    else:
        print(f"Result: {result}")
        return False


def upload_addon():
    """Upload the Kodi addon via SSH."""
    print("Uploading addon via SSH...")
    home = ssh_run("echo $HOME").split("\n")[-1].strip()
    addon_dir = f"{home}/.kodi/addons/script.music-server-source"
    ssh_run(f"mkdir -p {addon_dir}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    addon_path = os.path.join(script_dir, "addon")

    for fname in ["addon.xml", "default.py"]:
        with open(os.path.join(addon_path, fname)) as f:
            content = f.read()
        # Write via SSH
        ssh_run(f"cat > {addon_dir}/{fname} << 'FILEEOF'\n{content}\nFILEEOF")
        print(f"  Uploaded {fname}")

    print(f"\nAddon installed at {addon_dir}")
    print("Run it from Kodi: Addons > My addons > Scripts > Music Server Source")
    return True


if __name__ == "__main__":
    print("=== Music Server - Kodi Setup ===")
    print()

    if len(sys.argv) > 1 and sys.argv[1] == "--addon":
        upload_addon()
    else:
        if add_source_via_ssh():
            print("\nDone! Open Kodi and check Videos > Files for 'Music Server'.")
        else:
            print("\nSSH approach failed. Trying addon upload...")
            upload_addon()