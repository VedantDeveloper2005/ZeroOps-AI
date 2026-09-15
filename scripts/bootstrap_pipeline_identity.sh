#!/bin/bash
set -euo pipefail
install -d -m 0700 /run/zeroops-pipeline-identity
cat > /usr/local/sbin/zeroops-refresh-pipeline-identity <<'PY'
#!/usr/bin/python3
import json, os, pathlib, urllib.request
url = 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=api%3A%2F%2FAzureADTokenExchange&client_id=aa6c0b8c-2587-4abc-a33f-ed76a1581a03'
request = urllib.request.Request(url, headers={'Metadata': 'true'})
with urllib.request.urlopen(request, timeout=10) as response:
    token = json.load(response)['access_token']
directory = pathlib.Path('/run/zeroops-pipeline-identity')
directory.mkdir(mode=0o700, exist_ok=True)
temporary = directory / 'token.jwt.tmp'
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as output:
    output.write(token)
os.replace(temporary, directory / 'token.jwt')
PY
chmod 0700 /usr/local/sbin/zeroops-refresh-pipeline-identity
cat > /etc/systemd/system/zeroops-pipeline-identity.service <<'UNIT'
[Unit]
Description=Refresh the application worker's managed identity assertion
After=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/zeroops-refresh-pipeline-identity
UNIT
cat > /etc/systemd/system/zeroops-pipeline-identity.timer <<'UNIT'
[Unit]
Description=Keep application worker identity assertions fresh
[Timer]
OnBootSec=15
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl start zeroops-pipeline-identity.service
systemctl enable --now zeroops-pipeline-identity.timer
/usr/local/bin/docker run --rm --user 0:0 --network host \
  --env AZURE_TENANT_ID=65444c60-8471-413d-9d50-a0472e4c80f5 \
  --env AZURE_CLIENT_ID=364fa923-8db7-4823-83d7-0c9b3b94ce17 \
  --env AZURE_AUTHORITY_HOST=https://login.microsoftonline.com \
  --env AZURE_FEDERATED_TOKEN_FILE=/identity/token.jwt \
  --volume /run/zeroops-pipeline-identity:/identity:ro \
  zeroopsexec7abb.azurecr.io/zeroops/pipeline-worker@sha256:388c9a3efd9b7beaf5aed23af37378d6fd17c63ffafe2596edfc5280f708479e \
  python -c 'from azure.identity import WorkloadIdentityCredential; from azure.keyvault.secrets import SecretClient; c=SecretClient("https://zeroops-kv-v2.vault.azure.net", WorkloadIdentityCredential()); print("Key Vault configuration read:", bool(c.get_secret("zeroops-database-url").value))'
