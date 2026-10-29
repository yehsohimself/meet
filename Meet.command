#!/bin/bash
# Double-click to open Meet. The site normally runs at login (kurulum.sh); if it is not running, it is started here.
cd "$(dirname "$0")"
if ! curl -s -o /dev/null http://127.0.0.1:8766/; then
  nohup .venv/bin/python site.py > site.log 2>&1 &
  for i in $(seq 1 40); do sleep 0.5; curl -s -o /dev/null http://127.0.0.1:8766/ && break; done
fi
open http://127.0.0.1:8766/
