#!/bin/sh
# Run kodi-ssh-setup with the correct venv
cd "$(dirname "$0")"
source .venv/bin/activate
python3 kodi-ssh-setup.py "$@"