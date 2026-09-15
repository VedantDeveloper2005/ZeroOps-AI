"""Prepare a source-bound, credential-free check image for the existing demo."""
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from backend.services.repository_snapshot import collect_repository_snapshot
from backend.services.change_detection import fingerprint_repository

source = root / 'dist/demo-check-source'
revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
snapshot = collect_repository_snapshot(str(source))
digest = fingerprint_repository(snapshot.files, commit_sha=revision).repository_fingerprint
target = root / 'dist' / f'demo-check-image-{revision[:12]}'
for path in source.rglob('*'):
    relative = path.relative_to(source)
    if not path.is_file() or '.git' in relative.parts:
        continue
    destination = target / 'source' / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, destination)
(target / 'Dockerfile').write_text(f'''FROM node:20-bookworm-slim
LABEL io.zeroops.source.revision="{revision}" io.zeroops.source.digest="{digest}"
WORKDIR /source
COPY source/package*.json ./
RUN npm ci --ignore-scripts --cache /source/.npm-cache --no-audit --no-fund
COPY source/ /source/
RUN chmod -R a+rX /source
USER 10001:10001
CMD ["node", "--version"]
''', encoding='utf-8')
print(f'Prepared {revision} source digest {digest}: {target}')
