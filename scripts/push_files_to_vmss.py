import base64
import gzip
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]

def run_remote_sh(name: str, sh_content: str):
    script_path = Path(f"D:/{name}.sh")
    script_path.write_text(sh_content, encoding="utf-8")
    print(f"\n========================================================")
    print(f"[{name}] size={script_path.stat().st_size} bytes, executing on VMSS...")
    cmd = [
        "az.cmd", "vmss", "run-command", "invoke",
        "--subscription", "7abbc9d1-585e-452a-9f6d-a137a0015959",
        "--resource-group", "zeroops-exec-demo-rg",
        "--name", "vmss-zops-tfexec",
        "--instance-id", "8",
        "--command-id", "RunShellScript",
        "--scripts", f"@{script_path.as_posix()}"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(f"[{name}] returncode={res.returncode}")
    print(f"[{name}] STDOUT:\n", res.stdout)
    if res.stderr:
        print(f"[{name}] STDERR:\n", res.stderr)
    return res.returncode == 0

# Step 1: Push pipeline_evidence.py (12 KB, uncompressed is fine)
pipe_evid_bytes = (root / "backend" / "services" / "pipeline_evidence.py").read_bytes()
pipe_evid_b64 = base64.b64encode(pipe_evid_bytes).decode("ascii")
sh1 = f"""#!/bin/bash
set -euo pipefail
mkdir -p /opt/zeroops-pipeline
echo "{pipe_evid_b64}" | base64 -d > /opt/zeroops-pipeline/pipeline_evidence.py
chmod 0644 /opt/zeroops-pipeline/pipeline_evidence.py
ls -l /opt/zeroops-pipeline/pipeline_evidence.py
"""
run_remote_sh("push_evidence", sh1)

# Step 2: Push ai.py (gzipped ~18 KB)
ai_bytes = (root / "backend" / "services" / "ai.py").read_bytes()
ai_gz_b64 = base64.b64encode(gzip.compress(ai_bytes)).decode("ascii")
sh2 = f"""#!/bin/bash
set -euo pipefail
echo "{ai_gz_b64}" | base64 -d | gunzip > /opt/zeroops-pipeline/ai.py
chmod 0644 /opt/zeroops-pipeline/ai.py
ls -l /opt/zeroops-pipeline/ai.py
"""
run_remote_sh("push_ai", sh2)

# Step 3: Push pipeline.py (gzipped ~28 KB)
pipeline_bytes = (root / "backend" / "services" / "pipeline.py").read_bytes()
pipeline_gz_b64 = base64.b64encode(gzip.compress(pipeline_bytes)).decode("ascii")
sh3 = f"""#!/bin/bash
set -euo pipefail
echo "{pipeline_gz_b64}" | base64 -d | gunzip > /opt/zeroops-pipeline/pipeline.py
chmod 0644 /opt/zeroops-pipeline/pipeline.py
ls -l /opt/zeroops-pipeline/pipeline.py
"""
run_remote_sh("push_pipeline", sh3)

# Step 4: Stop service, kill old container, update unit with ALL mounts, start service, inspect mounts
sh4 = """#!/bin/bash
set -euo pipefail

echo "Stopping worker service..."
systemctl stop zeroops-pipeline-worker.service || true
/usr/local/bin/docker kill zeroops-pipeline-worker 2>/dev/null || true
/usr/local/bin/docker rm -f zeroops-pipeline-worker 2>/dev/null || true

cat <<'EOF' > /etc/systemd/system/zeroops-pipeline-worker.service
[Unit]
Description=ZeroOps application release pipeline worker
Wants=network-online.target docker.service
After=network-online.target docker.service

[Service]
Type=simple
Restart=on-failure
RestartSec=15
EnvironmentFile=/etc/zeroops-pipeline-worker.env
Environment=DOCKER_CONFIG=/run/zeroops-docker
ExecStartPre=/usr/local/sbin/zeroops-acr-login
ExecStart=/usr/local/bin/docker run --rm --name zeroops-pipeline-worker --network host -v /var/run/docker.sock:/var/run/docker.sock -v /run/zeroops-docker:/root/.docker:ro -v /opt/zeroops-pipeline/azure_connector.py:/app/backend/services/azure_connector.py:ro -v /opt/zeroops-pipeline/config.py:/app/backend/config.py:ro -v /opt/zeroops-pipeline/terraform_runner.py:/app/worker/terraform_runner.py:ro -v /opt/zeroops-pipeline/repository_executor.py:/app/worker/repository_executor.py:ro -v /opt/zeroops-pipeline/demo_executor.py:/app/backend/services/demo_executor.py:ro -v /opt/zeroops-pipeline/pipeline.py:/app/backend/services/pipeline.py:ro -v /opt/zeroops-pipeline/repository_checks.py:/app/backend/services/repository_checks.py:ro -v /opt/zeroops-pipeline/security_scanner.py:/app/backend/services/security_scanner.py:ro -v /opt/zeroops-pipeline/pipeline_evidence.py:/app/backend/services/pipeline_evidence.py:ro -v /opt/zeroops-pipeline/app_service.py:/app/backend/services/app_service.py:ro -v /opt/zeroops-pipeline/ai.py:/app/backend/services/ai.py:ro --user 0:0 --env-file /etc/zeroops-pipeline-worker.env zeroopsexec7abb.azurecr.io/zeroops/pipeline-worker:repair-20260914
ExecStop=/usr/local/bin/docker stop --time 300 zeroops-pipeline-worker
TimeoutStopSec=330

[Install]
WantedBy=multi-user.target
EOF

echo "Starting updated worker service..."
systemctl daemon-reload
systemctl enable zeroops-pipeline-worker.service
systemctl start zeroops-pipeline-worker.service
sleep 6
systemctl status zeroops-pipeline-worker.service --no-pager || true
docker ps --filter "name=zeroops-pipeline-worker"
docker inspect zeroops-pipeline-worker --format '{{range .Mounts}}{{.Destination}} <- {{.Source}}{{"\\n"}}{{end}}'
"""
run_remote_sh("restart_worker", sh4)
