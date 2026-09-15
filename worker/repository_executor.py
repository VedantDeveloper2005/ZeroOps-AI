"""Run repository checks in disposable, network-disabled Docker containers.

The trusted preparation step supplies a digest-pinned image containing an exact
source snapshot, dependencies and offline package caches. No repository command
runs on the credentialed worker. Each stage starts from the original image.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import PurePosixPath
import re
import subprocess
import threading
from typing import Sequence
import uuid

from backend.services.repository_checks import (
    CommandExecution, RepositoryIsolationAttestation, RepositoryIsolationRequest,
)
from backend.services.redaction import redact_sensitive_text


_IMAGE = re.compile(r"^[a-z0-9][a-z0-9./:_-]+@sha256:[0-9a-f]{64}$")
_TOOLS = frozenset({"python", "python3", "pytest", "node", "npm", "npx", "yarn", "pnpm",
                    "ruff", "flake8", "black", "eslint", "tsc"})


def configured_executor(source_revision: str, image_mapping: str):
    """Resolve a trusted prepared image; its source digest is checked at attest."""
    images = json.loads(image_mapping)
    if not isinstance(images, dict):
        raise ValueError("Repository check image configuration must be an object")
    image = images.get(source_revision)
    if image is None:
        return None
    if not isinstance(image, str):
        raise ValueError("Repository check image reference must be a string")
    return DockerRepositoryCheckExecutor(image)


class DockerRepositoryCheckExecutor:
    def __init__(self, image: str):
        if not _IMAGE.fullmatch(image):
            raise ValueError("Repository check images must be pinned by SHA-256 digest")
        self.image = image
        self._containers: dict[str, tuple[str, RepositoryIsolationAttestation]] = {}

    @staticmethod
    def _docker(args: Sequence[str], *, timeout: int = 60) -> str:
        result = subprocess.run(["docker", *args], capture_output=True, text=True,
                                timeout=timeout, check=False)
        if result.returncode:
            raise RuntimeError("Docker sandbox control operation failed")
        return result.stdout.strip()

    def attest(self, request: RepositoryIsolationRequest) -> RepositoryIsolationAttestation:
        # These labels are produced by trusted source preparation, and the
        # supplied digest fixes the image and labels for the whole release.
        info = json.loads(self._docker(["image", "inspect", self.image]))[0]
        labels = info.get("Config", {}).get("Labels") or {}
        if (labels.get("io.zeroops.source.revision") != request.source_revision
                or labels.get("io.zeroops.source.digest") != request.source_digest):
            raise ValueError("Prepared check image does not match the approved source")
        name = "zeroops-check-" + uuid.uuid4().hex
        created = False
        try:
            self._docker([
                "create", "--name", name, "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "--pids-limit", "256", "--memory", "1536m", "--cpus", "2",
                "--user", "10001:10001", "--workdir", "/work",
                "--tmpfs", "/work:rw,exec,nosuid,nodev,uid=10001,gid=10001,size=2147483648",
                "--tmpfs", "/tmp:rw,nosuid,nodev,uid=10001,gid=10001,size=268435456",
                "--entrypoint", "/bin/sh", self.image, "-c",
                "cp -R /source/. /work/ && touch /tmp/zeroops-source-ready && exec sleep 2100",
            ])
            created = True
            self._docker(["start", name])
            self._docker(["exec", name, "/bin/sh", "-c",
                          "for i in $(seq 1 55); do test -f /tmp/zeroops-source-ready && exit 0; sleep 1; done; exit 1"])
            state = json.loads(self._docker(["inspect", name]))[0]
            host = state["HostConfig"]
            if (host.get("NetworkMode") != "none" or host.get("ReadonlyRootfs") is not True
                    or host.get("Privileged") or host.get("Binds")
                    or state["Config"].get("User") != "10001:10001"
                    or not state["State"].get("Running")
                    or "ALL" not in host.get("CapDrop", [])
                    or not any("no-new-privileges" in item for item in host.get("SecurityOpt", []))
                    or any(mount.get("Type") != "tmpfs" for mount in state.get("Mounts", []))):
                raise RuntimeError("Docker did not enforce the required isolation settings")
            now = datetime.now(timezone.utc)
            attestation = RepositoryIsolationAttestation(
                isolation_id=name, stage=request.stage, source_revision=request.source_revision,
                source_digest=request.source_digest, issued_at=now, expires_at=now + timedelta(seconds=2100),
                disposable=True, fresh_source=True, worker_filesystem_access=False,
                database_access=False, key_vault_access=False, imds_access=False,
                network_policy="none", allowed_network_destinations=(),
            )
            self._containers[name] = (name, attestation)
            return attestation
        except Exception:
            if created:
                self._docker(["rm", "--force", name])
            raise

    def _container(self, attestation: RepositoryIsolationAttestation) -> str:
        record = self._containers.get(attestation.isolation_id)
        if record is None or record[1] is not attestation:
            raise ValueError("Unknown sandbox capability")
        if datetime.now(timezone.utc) >= attestation.expires_at:
            raise ValueError("Sandbox capability expired")
        return record[0]

    def resolve_tool(self, tool: str, *, attestation: RepositoryIsolationAttestation) -> str | None:
        if tool not in _TOOLS:
            return None
        container = self._container(attestation)
        try:
            # The tool is drawn from a fixed allowlist; repository text is not
            # interpolated into a host shell command.
            result = self._docker(["exec", container, "/bin/sh", "-c", "command -v " + tool])
        except RuntimeError:
            return None
        return result if result.startswith("/") and "\n" not in result else None

    def execute(self, command: Sequence[str], *, relative_cwd: str,
                timeout_seconds: int, attestation: RepositoryIsolationAttestation) -> CommandExecution:
        container = self._container(attestation)
        cwd = PurePosixPath(relative_cwd)
        if cwd.is_absolute() or ".." in cwd.parts or "\\" in relative_cwd:
            raise ValueError("Repository working directory must stay inside the sandbox")
        if not command or PurePosixPath(command[0]).name not in _TOOLS:
            raise ValueError("Unsupported repository check executable")
        if not 1 <= timeout_seconds <= 1800:
            raise ValueError("Repository check timeout is outside the supported bounds")
        # Offline caches belong to the prepared image. Environment values from
        # the worker (Azure credentials, DB credentials, tokens) are never passed.
        args = ["docker", "exec", "--workdir", str(PurePosixPath("/work") / cwd), container,
                "/usr/bin/env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin:/work/node_modules/.bin",
                "HOME=/tmp", "CI=true", "npm_config_offline=true", "npm_config_cache=/work/.npm-cache",
                "PIP_NO_INDEX=1", "PIP_FIND_LINKS=/wheelhouse", "PYTHONPATH=/work", *command]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        tails = [bytearray(), bytearray()]

        def drain(stream, tail):
            try:
                while chunk := stream.read(8192):
                    tail.extend(chunk)
                    del tail[:-32000]
            finally:
                stream.close()

        threads = [threading.Thread(target=drain, args=(stream, tails[index]), daemon=True)
                   for index, stream in enumerate((process.stdout, process.stderr))]
        for thread in threads:
            thread.start()
        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            self._docker(["kill", container])
            process.kill()
            process.wait(timeout=10)
            returncode = 124
        finally:
            for thread in threads:
                thread.join(timeout=10)
        captured = [redact_sensitive_text(bytes(tail).decode("utf-8", errors="replace")) for tail in tails]
        return CommandExecution(returncode=returncode, stdout=captured[0], stderr=captured[1])

    def close(self) -> None:
        for name in list(self._containers):
            self._docker(["rm", "--force", name])
            del self._containers[name]
