import base64
import gzip
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]

rep_checks_bytes = (root / "backend" / "services" / "repository_checks.py").read_bytes()
rep_checks_gz_b64 = base64.b64encode(gzip.compress(rep_checks_bytes)).decode("ascii")

sh = f"""#!/bin/bash
set -euo pipefail

echo "Replacing repository_checks.py directory with real file..."
rm -rf /opt/zeroops-pipeline/repository_checks.py
echo "{rep_checks_gz_b64}" | base64 -d | gunzip > /opt/zeroops-pipeline/repository_checks.py
chmod 0644 /opt/zeroops-pipeline/repository_checks.py
ls -l /opt/zeroops-pipeline/repository_checks.py

echo "Stopping and restarting worker..."
systemctl stop zeroops-pipeline-worker.service || true
/usr/local/bin/docker kill zeroops-pipeline-worker 2>/dev/null || true
/usr/local/bin/docker rm -f zeroops-pipeline-worker 2>/dev/null || true

systemctl daemon-reload
systemctl start zeroops-pipeline-worker.service
sleep 6

systemctl status zeroops-pipeline-worker.service --no-pager || true
docker ps --filter "name=zeroops-pipeline-worker"
docker inspect zeroops-pipeline-worker --format '{{range .Mounts}}{{.Destination}} <- {{.Source}}{{"\\n"}}{{end}}'
"""

script_path = Path("D:/fix_checks.sh")
script_path.write_text(sh, encoding="utf-8")

cmd = [
    "az.cmd", "vmss", "run-command", "invoke",
    "--subscription", "7abbc9d1-585e-452a-9f6d-a137a0015959",
    "--resource-group", "zeroops-exec-demo-rg",
    "--name", "vmss-zops-tfexec",
    "--instance-id", "8",
    "--command-id", "RunShellScript",
    "--scripts", f"@{script_path.as_posix()}"
]

print("Executing fix on VMSS instance 8...")
res = subprocess.run(cmd, capture_output=True, text=True)
print("Returncode:", res.returncode)
print(res.stdout)
if res.stderr:
    print("STDERR:\n", res.stderr)
