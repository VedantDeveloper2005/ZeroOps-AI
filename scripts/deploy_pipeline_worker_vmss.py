import base64
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
connector_bytes = (root / "backend" / "services" / "azure_connector.py").read_bytes()
connector_b64 = base64.b64encode(connector_bytes).decode("ascii")

config_bytes = (root / "backend" / "config.py").read_bytes()
config_b64 = base64.b64encode(config_bytes).decode("ascii")

tf_runner_bytes = (root / "worker" / "terraform_runner.py").read_bytes()
tf_runner_b64 = base64.b64encode(tf_runner_bytes).decode("ascii")

rep_exec_bytes = (root / "worker" / "repository_executor.py").read_bytes()
rep_exec_b64 = base64.b64encode(rep_exec_bytes).decode("ascii")

demo_exec_bytes = (root / "backend" / "services" / "demo_executor.py").read_bytes()
demo_exec_b64 = base64.b64encode(demo_exec_bytes).decode("ascii")

pipeline_bytes = (root / "backend" / "services" / "pipeline.py").read_bytes()
pipeline_b64 = base64.b64encode(pipeline_bytes).decode("ascii")

rep_checks_bytes = (root / "backend" / "services" / "repository_checks.py").read_bytes()
rep_checks_b64 = base64.b64encode(rep_checks_bytes).decode("ascii")

sec_scanner_bytes = (root / "backend" / "services" / "security_scanner.py").read_bytes()
sec_scanner_b64 = base64.b64encode(sec_scanner_bytes).decode("ascii")

pipe_evid_bytes = (root / "backend" / "services" / "pipeline_evidence.py").read_bytes()
pipe_evid_b64 = base64.b64encode(pipe_evid_bytes).decode("ascii")

app_svc_bytes = (root / "backend" / "services" / "app_service.py").read_bytes()
app_svc_b64 = base64.b64encode(app_svc_bytes).decode("ascii")

ai_bytes = (root / "backend" / "services" / "ai.py").read_bytes()
ai_b64 = base64.b64encode(ai_bytes).decode("ascii")

shell_script = f"""#!/bin/bash
set -euo pipefail

echo "[1/4] Preparing directories and files..."
mkdir -p /opt/zeroops-pipeline
echo "{connector_b64}" | base64 -d > /opt/zeroops-pipeline/azure_connector.py
chmod 0644 /opt/zeroops-pipeline/azure_connector.py

echo "{config_b64}" | base64 -d > /opt/zeroops-pipeline/config.py
chmod 0644 /opt/zeroops-pipeline/config.py

echo "{tf_runner_b64}" | base64 -d > /opt/zeroops-pipeline/terraform_runner.py
chmod 0644 /opt/zeroops-pipeline/terraform_runner.py

echo "{rep_exec_b64}" | base64 -d > /opt/zeroops-pipeline/repository_executor.py
chmod 0644 /opt/zeroops-pipeline/repository_executor.py

echo "{demo_exec_b64}" | base64 -d > /opt/zeroops-pipeline/demo_executor.py
chmod 0644 /opt/zeroops-pipeline/demo_executor.py

echo "{pipeline_b64}" | base64 -d > /opt/zeroops-pipeline/pipeline.py
chmod 0644 /opt/zeroops-pipeline/pipeline.py

echo "{rep_checks_b64}" | base64 -d > /opt/zeroops-pipeline/repository_checks.py
chmod 0644 /opt/zeroops-pipeline/repository_checks.py

echo "{sec_scanner_b64}" | base64 -d > /opt/zeroops-pipeline/security_scanner.py
chmod 0644 /opt/zeroops-pipeline/security_scanner.py

echo "{pipe_evid_b64}" | base64 -d > /opt/zeroops-pipeline/pipeline_evidence.py
chmod 0644 /opt/zeroops-pipeline/pipeline_evidence.py

echo "{app_svc_b64}" | base64 -d > /opt/zeroops-pipeline/app_service.py
chmod 0644 /opt/zeroops-pipeline/app_service.py

echo "{ai_b64}" | base64 -d > /opt/zeroops-pipeline/ai.py
chmod 0644 /opt/zeroops-pipeline/ai.py

echo "[2/4] Writing /etc/zeroops-pipeline-worker.env..."
cat <<'EOF' > /etc/zeroops-pipeline-worker.env
APP_ENV=development
ZEROOPS_DEMO_EXECUTOR=true
DATABASE_URL="${DATABASE_URL}"
DB_SSL_ENABLED=true
DB_SSL_VERIFY=true
AZURE_CLIENT_SECRET="${AZURE_CLIENT_SECRET}"
JWT_SECRET="${JWT_SECRET}"
REPOSITORY_CHECK_IMAGES={{}}
WORKER_POLL_INTERVAL_SECONDS=5
WORKER_LEASE_SECONDS=300
WORKER_HEARTBEAT_SECONDS=30
WORKER_MAX_ATTEMPTS=3
WORKER_HEALTH_PORT=8086
ARM_CLIENT_ID=a9ae8065-a0cf-4595-981b-7c5358bbbabb
ARM_SUBSCRIPTION_ID=7abbc9d1-585e-452a-9f6d-a137a0015959
ARM_TENANT_ID=4df935fe-ee7e-4b05-9701-bf58fd1fd854
AZURE_CLIENT_ID=aa6c0b8c-2587-4abc-a33f-ed76a1581a03
EOF
chmod 0600 /etc/zeroops-pipeline-worker.env

echo "[3/4] Stopping existing service and cleaning up containers..."
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

echo "[4/4] Reloading systemd and starting service..."
systemctl daemon-reload
systemctl enable zeroops-pipeline-worker.service
systemctl start zeroops-pipeline-worker.service
sleep 6
systemctl status zeroops-pipeline-worker.service --no-pager || true
docker ps --filter "name=zeroops-pipeline-worker"
docker inspect zeroops-pipeline-worker --format '{{range .Mounts}}{{.Destination}} <- {{.Source}}{{"\\n"}}{{end}}'
"""

script_path = Path("D:/setup_pipeline_worker.sh")
script_path.write_text(shell_script, encoding="utf-8")

cmd = [
    "az.cmd", "vmss", "run-command", "invoke",
    "--subscription", "7abbc9d1-585e-452a-9f6d-a137a0015959",
    "--resource-group", "zeroops-exec-demo-rg",
    "--name", "vmss-zops-tfexec",
    "--instance-id", "8",
    "--command-id", "RunShellScript",
    "--scripts", f"@{script_path.as_posix()}"
]

print("Executing on VMSS instance 8...")
result = subprocess.run(cmd, capture_output=True, text=True)
print("Return code:", result.returncode)
print("STDOUT:\n", result.stdout)
if result.stderr:
    print("STDERR:\n", result.stderr)
