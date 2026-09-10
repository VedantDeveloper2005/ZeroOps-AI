"""Live integration test for Microsoft Foundry Architecture Advisor.

Authenticates using Microsoft Entra (DefaultAzureCredential from az login or Managed Identity).
Calls agent `zeroops-architecture-advisor` (version 2) with a harmless architecture query.
Inspects response text, model provenance, file search citations, and web citations.
"""

from __future__ import annotations

import json
import os
import sys
import time
from urllib.parse import urlparse

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from backend import config
from backend.services.foundry_advisor import (
    FoundryAdvisorClient,
    invoke_architecture_advisor,
)
from backend.services.providers.azure_foundry import extract_annotations


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run_live_test():
    print("=" * 70)
    print("Microsoft Foundry Prompt Agent Live Integration Test")
    print("=" * 70)

    endpoint = config.FOUNDRY_PROJECT_ENDPOINT
    agent_name = config.FOUNDRY_AGENT_NAME
    agent_version = config.FOUNDRY_AGENT_VERSION

    print(f"Project Endpoint: {endpoint}")
    print(f"Agent Name:       {agent_name}")
    print(f"Agent Version:    {agent_version}")
    print("-" * 70)

    print("Step 1: Authenticating with DefaultAzureCredential (Entra ID)...")
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)

    print("Step 2: Initializing AIProjectClient...")
    try:
        project_client = AIProjectClient(
            endpoint=endpoint,
            credential=credential,
        )
        print("  [OK] AIProjectClient initialized.")
    except Exception as err:
        print(f"  [ERROR] Failed to initialize AIProjectClient: {err}")
        return False

    print(f"Step 3: Getting agent-bound OpenAI client for '{agent_name}'...")
    try:
        openai_client = project_client.get_openai_client(agent_name=agent_name)
        print("  [OK] Agent-bound OpenAI client acquired.")
    except Exception as err:
        print(f"  [FAIL] Failed to bind OpenAI client to agent '{agent_name}': {err}")
        return False

    test_prompt = (
        "Recommend an Azure architecture for a small React + FastAPI + PostgreSQL application. "
        "Use ZeroOps knowledge and current Microsoft documentation where appropriate. "
        "Do not provision anything."
    )

    payload = {
        "input": test_prompt,
        "max_output_tokens": 3000,
    }
    if agent_version:
        payload["extra_body"] = {
            "agent_reference": {
                "type": "agent_reference",
                "name": agent_name,
                "version": agent_version,
            }
        }

    print("Step 4: Invoking Responses API on the agent...")
    print(f"  Prompt: {test_prompt}")
    started = time.perf_counter()

    try:
        response = openai_client.responses.create(**payload)
        latency_s = time.perf_counter() - started
        print(f"  [OK] Response received in {latency_s:.2f}s.")
    except Exception as err:
        latency_s = time.perf_counter() - started
        print(f"  [FAIL] Agent invocation failed after {latency_s:.2f}s: {err}")
        status_code = getattr(err, "status_code", None)
        if status_code == 401 or "authentication" in str(err).lower():
            print("    -> 401 Unauthorized: Run 'az login' locally, or ensure App Service Managed Identity is enabled.")
        elif status_code == 403 or "forbidden" in str(err).lower():
            print("    -> 403 Forbidden: Ensure your Azure identity is assigned the 'Azure AI Developer' role on the Foundry project.")
        return False

    # Extract model and usage
    model = getattr(response, "model", "Unknown")
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None) if usage else None
    output_tokens = getattr(usage, "output_tokens", None) if usage else None
    output_text = getattr(response, "output_text", "")

    print("-" * 70)
    print("Response Metadata:")
    print(f"  Model:         {model}")
    print(f"  Input Tokens:  {input_tokens}")
    print(f"  Output Tokens: {output_tokens}")
    print(f"  Latency:       {latency_s:.2f}s")
    print("-" * 70)

    # Check annotations (File Search and Web Search)
    annotations = extract_annotations(response)
    print(f"Annotations / Citations ({len(annotations)}):")
    file_search_citations = [a for a in annotations if a.get("file_id") or "file" in a.get("type", "")]
    web_search_citations = [a for a in annotations if a.get("url")]

    print(f"  File Search Citations: {len(file_search_citations)}")
    for fc in file_search_citations[:3]:
        print(f"    - File ID: {fc.get('file_id')}, Title: {fc.get('title')}, Text: {str(fc.get('text', ''))[:80]}...")

    print(f"  Web Search Citations:  {len(web_search_citations)}")
    for wc in web_search_citations[:3]:
        print(f"    - URL: {wc.get('url')}, Title: {wc.get('title')}")

    print("-" * 70)
    print("Advisor Output Preview (first 500 chars):")
    print(output_text[:500] + ("..." if len(output_text) > 500 else ""))
    print("=" * 70)

    # Step 5: Test through ZeroOps foundry_advisor service layer
    print("\nStep 5: Testing full ZeroOps service layer parsing & allowlist...")
    advisor_client = FoundryAdvisorClient(
        endpoint=endpoint,
        agent_name=agent_name,
        agent_version=agent_version,
        openai_client=openai_client,
    )

    repo_facts = {
        "framework": "FastAPI",
        "runtime": "python:3.11",
        "database_dependencies": ["postgresql"],
        "name": "live-verification-app",
        "environment_variables": ["DATABASE_URL", "PORT"],
    }

    rec = invoke_architecture_advisor(
        facts=repo_facts,
        project_name="live-verification-app",
        user_query=test_prompt,
        client=advisor_client,
    )

    print(f"  Confidence:            {rec.confidence}")
    print(f"  Components Count:      {len(rec.proposed_components)}")
    for comp in rec.proposed_components:
        deployable_label = "DEPLOYABLE" if comp.deployable else "ADVISORY ONLY"
        print(f"    - [{deployable_label}] {comp.service} ({comp.proposed_sku or 'No SKU'}) -> {comp.role}")
    print(f"  Unsupported Services:  {rec.unsupported_services}")
    print(f"  Evidence Citations:    {len(rec.evidence_sources)}")

    print("\n[OK] Live Foundry Integration Test COMPLETED SUCCESSFULLY!")
    return True


if __name__ == "__main__":
    success = run_live_test()
    sys.exit(0 if success else 1)
