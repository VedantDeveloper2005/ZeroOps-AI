import os
import shutil
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
standalone = root / ".next" / "standalone"
public = root / "public"
static = root / ".next" / "static"
dist = root / "dist"
dist.mkdir(exist_ok=True)

print("Preparing standalone bundle...")
# Ensure public is copied
target_public = standalone / "public"
if target_public.exists():
    shutil.rmtree(target_public)
if public.exists():
    shutil.copytree(public, target_public)
    print("Copied public/ to .next/standalone/public")

# Ensure .next/static is copied to .next/standalone/.next/static
target_static = standalone / ".next" / "static"
if target_static.exists():
    shutil.rmtree(target_static)
target_static.parent.mkdir(parents=True, exist_ok=True)
if static.exists():
    shutil.copytree(static, target_static)
    print("Copied .next/static to .next/standalone/.next/static")

zip_path = dist / "zeroopsai-frontend-appservice.zip"
print(f"Creating zip at {zip_path}...")
if zip_path.exists():
    zip_path.unlink()

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for file_path in standalone.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(standalone)
            zf.write(file_path, str(rel_path))

print(f"Zip created! Size: {zip_path.stat().st_size / (1024*1024):.2f} MB")
