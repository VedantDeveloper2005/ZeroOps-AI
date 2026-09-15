#!/bin/bash
set -euo pipefail
/usr/local/bin/docker logs --tail 150 zeroops-pipeline-worker 2>&1 | /usr/local/bin/docker exec -i zeroops-pipeline-worker python -c 'import sys; from backend.services.redaction import redact_sensitive_text; print(redact_sensitive_text(sys.stdin.read(), maximum_length=18000))'
