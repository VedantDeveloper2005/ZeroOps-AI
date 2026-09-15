import base64
import gzip
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]

pipeline_bytes = (root / "backend" / "services" / "pipeline.py").read_bytes()
pipeline_gz_b64 = base64.b64encode(gzip.compress(pipeline_bytes)).decode("ascii")

app_service_bytes = (root / "backend" / "services" / "app_service.py").read_bytes()
app_service_gz_b64 = base64.b64encode(gzip.compress(app_service_bytes)).decode("ascii")

sh = f"""#!/bin/bash
set -euo pipefail
echo "{pipeline_gz_b64}" | base64 -d | gunzip > /opt/zeroops-pipeline/pipeline.py
chmod 0644 /opt/zeroops-pipeline/pipeline.py
ls -l /opt/zeroops-pipeline/pipeline.py

echo "{app_service_gz_b64}" | base64 -d | gunzip > /opt/zeroops-pipeline/app_service.py
chmod 0644 /opt/zeroops-pipeline/app_service.py
ls -l /opt/zeroops-pipeline/app_service.py

systemctl restart zeroops-pipeline-worker
systemctl status zeroops-pipeline-worker --no-pager -n 5
"""

script_path = Path("D:/quick_pipeline.sh")
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
print("Executing quick push to VMSS instance 8...")
res = subprocess.run(cmd, capture_output=True, text=True)
print("Return code:", res.returncode)
print("Output:\n", res.stdout)
if res.stderr:
    print("Stderr:\n", res.stderr)
