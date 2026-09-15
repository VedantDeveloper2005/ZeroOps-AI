"""Create a minimal runtime-only context for the application worker image."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
target = root / 'dist' / 'pipeline-worker-context'
excluded = {'tests', 'workspace', '__pycache__', '.pytest_cache', '.venv', 'node_modules'}
for tree in ('backend', 'worker', 'ai-specs'):
    for source in (root / tree).rglob('*'):
        relative = source.relative_to(root)
        if not source.is_file() or any(part in excluded or part.startswith('.env') for part in relative.parts):
            continue
        if source.suffix in {'.pyc', '.pyo'}:
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
print(target)
