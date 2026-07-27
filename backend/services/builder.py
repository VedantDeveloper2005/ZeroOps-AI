import os
import subprocess
from typing import Generator

try:
    from backend.config import DOCKER_AVAILABLE
except ImportError:
    from config import DOCKER_AVAILABLE


def build_and_tag_image(repo_path: str, image_name: str, tag: str) -> Generator[str, None, None]:
    """
    Build a Docker image and tag it.
    Yields real Docker output so it can be streamed to the deployment log feed.
    """
    dockerfile_path = os.path.join(repo_path, "Dockerfile")
    if not os.path.exists(dockerfile_path):
        try:
            from backend.services.ai import analyze_repo_local
        except ImportError:
            from services.ai import analyze_repo_local
        metadata = analyze_repo_local(repo_path)
        if not metadata.get("dockerfile"):
            raise RuntimeError("No Dockerfile found and framework-specific Dockerfile generation is unavailable.")
        with open(dockerfile_path, "w", encoding="utf-8") as f:
            f.write(metadata["dockerfile"])

    full_image_tag = f"{image_name}:{tag}"

    if not DOCKER_AVAILABLE:
        message = "Docker daemon is not available. Configure Docker before starting deployments."
        yield f"{message}\n"
        raise RuntimeError(message)

    yield f"Initializing Docker image build: {full_image_tag}\n"
    process = subprocess.Popen(
        ["docker", "build", "-t", full_image_tag, "."],
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    while True:
        line = process.stdout.readline() if process.stdout else ""
        if not line and process.poll() is not None:
            break
        if line:
            yield f"  {line.strip()}\n"

    if process.returncode != 0:
        yield f"Docker build failed with return code {process.returncode}\n"
        raise RuntimeError(f"Docker build failed for {full_image_tag}")

    yield f"Container image built successfully: {full_image_tag}\n"


def push_image(image_ref: str) -> Generator[str, None, None]:
    """Push a previously built image to the configured registry."""
    if not DOCKER_AVAILABLE:
        message = "Docker daemon is not available. Cannot push container image."
        yield f"{message}\n"
        raise RuntimeError(message)

    yield f"Pushing container image: {image_ref}\n"
    process = subprocess.Popen(
        ["docker", "push", image_ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    while True:
        line = process.stdout.readline() if process.stdout else ""
        if not line and process.poll() is not None:
            break
        if line:
            yield f"  {line.strip()}\n"

    if process.returncode != 0:
        yield f"Docker push failed with return code {process.returncode}\n"
        raise RuntimeError("Docker push failed. Ensure the deployment worker is logged into the selected container registry.")

    yield "Container image pushed successfully.\n"
