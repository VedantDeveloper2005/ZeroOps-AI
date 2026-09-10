"""Package a locally built Next standalone server with Linux sharp binaries.

Run npm pack @img/sharp-linux-x64@0.35.3
@img/sharp-libvips-linux-x64@1.3.2 --pack-destination dist first.
"""
from pathlib import Path, PurePosixPath
import hashlib
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist/zeroops-frontend-appservice.zip"


def main():
    standalone = ROOT / ".next/standalone"
    if not (standalone / "server.js").is_file():
        raise SystemExit("Build the standalone frontend first")
    entries = {}
    for source, prefix in [(standalone, ""), (ROOT / "public", "public/"),
                           (ROOT / ".next/static", ".next/static/")]:
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            if any(p.startswith(".env") for p in relative.parts):
                continue
            if any("sharp-win32" in p for p in relative.parts):
                continue
            entries[prefix + relative.as_posix()] = path.read_bytes()
    for name, version in [("sharp-linux-x64", "0.35.3"),
                          ("sharp-libvips-linux-x64", "1.3.2")]:
        with tarfile.open(ROOT / f"dist/img-{name}-{version}.tgz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                relative = PurePosixPath(member.name)
                if relative.parts[0] != "package" or ".." in relative.parts:
                    raise ValueError("Unsafe npm archive path")
                content = archive.extractfile(member)
                entries[f"node_modules/@img/{name}/" + str(relative.relative_to("package"))] = content.read()
    manifest = entries[".next/routes-manifest.json"].decode()
    if "https://zeroops-backend-v2.azurewebsites.net" not in manifest:
        raise SystemExit("Rebuild with the Vedant backend URL")
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    print(f"{OUTPUT}\nfiles={len(entries)}\nsha256={hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
