#!/usr/bin/env python3
"""Local smoke-test for NvidiaProvider — reads credentials from the environment only.

Usage
-----
    $env:NVIDIA_API_KEY = "<your-api-key>"  # PowerShell
    python scripts/test_nvidia_provider.py

Exit codes
----------
0  Structured response received and parsed successfully.
1  Authentication error, JSON parse failure, or provider error.

Security notes
--------------
- The API key is read from the environment variable NVIDIA_API_KEY only.
- The key is NEVER printed, logged, or included in error messages.
- Raw model responses are printed only after successful JSON parsing.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Allow running from the repository root without installing the package.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

os.environ.setdefault("APP_ENV", "test")


def _die(message: str, exit_code: int = 1) -> None:
    """Print a safe error and exit. Never include credentials."""
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(exit_code)


def main() -> None:
    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not api_key:
        _die(
            "NVIDIA_API_KEY environment variable is not set.\n"
            "Set it before running this script:\n"
            "  $env:NVIDIA_API_KEY = '<your-api-key>'  # PowerShell\n"
            "  export NVIDIA_API_KEY='<your-api-key>'  # bash"
        )

    endpoint = os.environ.get(
        "NVIDIA_ENDPOINT", "https://integrate.api.nvidia.com/v1"
    ).strip()
    model = os.environ.get("NVIDIA_MODEL", "z-ai/glm-5.2").strip()

    print(f"Endpoint : {endpoint}")
    print(f"Model    : {model}")
    print("API key  : [set, not printed]")
    print()

    # Import provider after path setup.
    try:
        from backend.services.providers import NvidiaProvider
        from backend.services.providers.base import (
            ProviderConfiguration,
            ProviderConfigurationError,
            ProviderError,
            ProviderRequest,
        )
    except ImportError as exc:
        _die(f"Could not import backend providers: {exc}")

    # Minimal test output schema for repository analysis.
    output_schema = {
        "type": "object",
        "properties": {
            "explanation": {"type": "string"},
            "deployment_risk": {"type": "string"},
            "recommendations": {
                "type": "array",
                "items": {"type": "string"},
            },
            "unresolved_questions": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "explanation",
            "deployment_risk",
            "recommendations",
            "unresolved_questions",
        ],
    }

    system_prompt = (
        "You are a concise deployment readiness assistant. "
        "Respond only with the requested JSON object. "
        "Do not add commentary or markdown."
    )
    user_prompt = json.dumps(
        {
            "repository": "smoke-test/hello-world",
            "branch": "main",
            "facts": [
                {
                    "id": "fact-readme",
                    "category": "documentation",
                    "value": "README.md present.",
                }
            ],
        },
        separators=(",", ":"),
    )

    try:
        configuration = ProviderConfiguration(
            provider="nvidia",
            endpoint=endpoint,
            model=model,
            api_key=api_key,
            max_input_chars=40_000,
            max_output_tokens=1_600,
            timeout_seconds=60,
        )
    except ProviderConfigurationError as exc:
        _die(f"Configuration error: {exc}")

    try:
        provider = NvidiaProvider(configuration)  # type: ignore[arg-type]
    except ProviderConfigurationError as exc:
        _die(f"Provider configuration error: {exc}")

    request = ProviderRequest(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_name="SmokeTestRepositoryReview",
        output_schema=output_schema,
        max_output_tokens=1_600,
        temperature=0.0,
    )

    print("Sending request to NVIDIA Build API …")
    started = time.perf_counter()
    try:
        response = provider.generate(request)  # type: ignore[arg-type]
    except ProviderError as exc:
        _die(f"Provider error: {exc}")
    except Exception as exc:
        # Never print exc details — they may contain request metadata.
        _die("An unexpected error occurred. Check your API key and network connectivity.")

    elapsed_ms = round((time.perf_counter() - started) * 1_000)
    print(f"Response received in {elapsed_ms} ms")
    print(f"Model    : {response.model}")  # type: ignore[union-attr]
    print(f"Tokens   : {response.input_tokens} in / {response.output_tokens} out")  # type: ignore[union-attr]
    print()

    # Parse and display the structured result.
    try:
        parsed: dict = json.loads(response.content)  # type: ignore[union-attr]
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Raw content preview (first 500 chars): {response.content[:500]}")  # type: ignore[union-attr]
        _die(f"JSON parse error: {exc}")

    required_keys = {"explanation", "deployment_risk", "recommendations", "unresolved_questions"}
    missing = required_keys - set(parsed)
    if missing:
        print(f"Parsed JSON: {json.dumps(parsed, indent=2)}")
        _die(f"Response is missing required fields: {missing}")

    print("=== Repository Analysis Smoke Test Result ===")
    print(f"Explanation       : {parsed['explanation']}")
    print(f"Deployment risk   : {parsed['deployment_risk']}")
    print(f"Recommendations   : {parsed['recommendations']}")
    print(f"Unresolved        : {parsed['unresolved_questions']}")
    print()
    print("PASS — NVIDIA provider is reachable and returns a valid structured response.")
    sys.exit(0)


if __name__ == "__main__":
    main()
