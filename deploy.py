#!/usr/bin/env python3
"""Copy music-server to hcontrol.local and start it there."""

import pexpect
import shutil
import sys
import os
import json
import urllib.request

HCONTROL = "ubuntu@hcontrol.local"
PASSWORD = "pi120741"
KODI_IP = "192.168.50.149"
KODI_USER = "xbian"
KODI_PASS = "pi120741"
LOCAL_DIR = "/home/jerry/projects/music-server"
REMOTE_DIR = "/home/ubuntu/music-server"

def run(cmd, password, timeout=60):
    child = pexpect.spawn(cmd, timeout=timeout, encoding='utf-8')
    child.logfile = sys.stdout
    i = child.expect_exact(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
    if i == 0:
        child.sendline(password)
        child.expect(pexpect.EOF, timeout=timeout)
    child.close()
    return child.exitstatus

def ssh_cmd(cmd, password, timeout=60):
    """Run a command via ssh and return exit status."""
    return run(f"ssh -o StrictHostKeyChecking=no {HCONTROL} '{cmd}'", password, timeout)

# Step 1: Remove old remote dir if exists
print("=== Cleaning remote directory ===")
run(f"ssh -o StrictHostKeyChecking=no {HCONTROL} 'rm -rf {REMOTE_DIR} && mkdir -p {REMOTE_DIR}'", PASSWORD, timeout=30)

# Step 2: Copy the music-server directory via tar-to-ssh
print("\n=== Copying music-server to hcontrol.local ===")
import subprocess, tempfile
# Create a tarball to a temp file, then scp it
tar_path = os.path.join(tempfile.gettempdir(), "music-server.tar.gz")
subprocess.run([
    "tar", "czf", tar_path,
    "-C", LOCAL_DIR,
    "--exclude=.venv", "--exclude=__pycache__", "--exclude=nohup.out",
    "."
], check=True)
print(f"  Created tarball: {tar_path}")

# scp the tarball
child = pexpect.spawn(
    f"scp -o StrictHostKeyChecking=no {tar_path} {HCONTROL}:{REMOTE_DIR}/music-server.tar.gz",
    timeout=120, encoding='utf-8'
)
child.logfile = sys.stdout
i = child.expect_exact(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=120)
if i == 0:
    child.sendline(PASSWORD)
    child.expect(pexpect.EOF, timeout=120)
child.close()
if child.exitstatus != 0:
    print(f"ERROR: scp failed with exit code {child.exitstatus}")
    sys.exit(1)

# Extract tarball on remote
child = pexpect.spawn(
    f"ssh -o StrictHostKeyChecking=no {HCONTROL} 'cd {REMOTE_DIR} && tar xzf music-server.tar.gz && rm music-server.tar.gz'",
    timeout=60, encoding='utf-8'
)
child.logfile = sys.stdout
i = child.expect_exact(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=60)
if i == 0:
    child.sendline(PASSWORD)
    child.expect(pexpect.EOF, timeout=60)
child.close()
if child.exitstatus != 0:
    print(f"ERROR: extraction failed with exit code {child.exitstatus}")
    sys.exit(1)

print("  Copy complete!")

# Cleanup local tarball
os.remove(tar_path)

# Step 3: Install yt-dlp and dependencies on remote
print("\n=== Installing dependencies on hcontrol.local ===")
child = pexpect.spawn(
    f"ssh -o StrictHostKeyChecking=no {HCONTROL} 'cd {REMOTE_DIR} && sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip yt-dlp 2>&1 | tail -5'",
    timeout=120, encoding='utf-8'
)
child.logfile = sys.stdout
i = child.expect_exact(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=120)
if i == 0:
    child.sendline(PASSWORD)
    child.expect(pexpect.EOF, timeout=120)
child.close()

# Step 4: Start the server on hcontrol.local in a screen session
print("\n=== Starting server on hcontrol.local ===")
child = pexpect.spawn(
    f"ssh -o StrictHostKeyChecking=no {HCONTROL} 'cd {REMOTE_DIR} && screen -dmS music-server python3 server.py'",
    timeout=30, encoding='utf-8'
)
child.logfile = sys.stdout
i = child.expect_exact(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=30)
if i == 0:
    child.sendline(PASSWORD)
    child.expect(pexpect.EOF, timeout=30)
child.close()

# Step 5: Verify the server is running
print("\n=== Verifying server on hcontrol.local ===")
child = pexpect.spawn(
    f"ssh -o StrictHostKeyChecking=no {HCONTROL} 'screen -ls | grep music-server'",
    timeout=30, encoding='utf-8'
)
child.logfile = sys.stdout
i = child.expect_exact(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=30)
if i == 0:
    child.sendline(PASSWORD)
    child.expect(pexpect.EOF, timeout=30)
child.close()

# Step 6: Check if it's listening
print("\n=== Checking server port ===")
child = pexpect.spawn(
    f"ssh -o StrictHostKeyChecking=no {HCONTROL} 'sleep 5 && curl -s http://localhost:8080/health | head -20'",
    timeout=30, encoding='utf-8'
)
child.logfile = sys.stdout
i = child.expect_exact(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=30)
if i == 0:
    child.sendline(PASSWORD)
    child.expect(pexpect.EOF, timeout=30)
child.close()

print("\n=== Done! ===")
print(f"Music server should be running at http://hcontrol.local:8080")