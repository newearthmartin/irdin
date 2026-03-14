#!/bin/bash
set -e

ssh phoenix.elmartus.mooo.com 'cd ~/workspace/irdin && uv run python manage.py export_transcriptions'
scp -P 2200 phoenix.elmartus.mooo.com:~/workspace/irdin/transcriptions_export.json .
uv run python manage.py import_transcriptions transcriptions_export.json
