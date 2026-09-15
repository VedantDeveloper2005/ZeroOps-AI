#!/bin/sh
set -eu
systemctl list-units --type=service --all --no-pager | grep -E 'zeroops|pipeline' || true
/usr/local/bin/docker ps --format '{{.Names}} {{.Image}} {{.Status}}'
curl -s --max-time 5 http://127.0.0.1:8085/ready || true
