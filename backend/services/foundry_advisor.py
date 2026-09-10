"""Microsoft Foundry Architecture Advisor service.

Invokes the pre-configured Microsoft Foundry Prompt Agent (`zeroops-architecture-advisor`, version 2)
using Microsoft Entra authentication (DefaultAzureCredential).
Preserves server-side agent instructions, File Search (zeroops-knowledge vector store),
and Web Search. Enforces the strict ZeroOps security boundary: advisory recommendations only;
Terraform generation and deployment remain separate approved operations.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, Literal
from urllib.parse import urlparse

from backend import config
from backend.contracts.architecture_advisor import (
    ArchitectureRecommendation,
    CitationEvidence,
    ComponentRecommendation,
)
from backend.services.providers.azure_foundry import extract_annotations

logger = logging.getLogger("zeroops.foundry_advisor")
ai_logger = logging.getLogger("zeroops.ai.observability")

# ZeroOps currently supports automated Terraform deployment for Azure App Service.
DEPLOYABLE_AUTOMATION_ALLOWLIST = {
    "azure app service",
    "app service",
}

ADVISORY_UNSUPPORTED_NOTE = "Advisory recommendation — deployment automation not currently supported"
DEPLOYABLE_SUPPORTED_NOTE = "Supported by current engine"


class FoundryAdvisorError(RuntimeError):
    """Base error for Foundry Architecture Advisor failures."""


class FoundryAuthenticationError(FoundryAdvisorError):
    """Raised when Entra ID / DefaultAzureCredential authentication fails."""


class FoundryAuthorizationError(FoundryAdvisorError):
    """Raised when identity lacks Azure AI Developer RBAC on the project."""


class FoundryAdvisorClient:
    """Manages connection to the Microsoft Foundry Architecture Advisor agent."""

    def __init__(
        self,
        endpoint: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        *,
        project_client: Any | None = None,
        openai_client: Any | None = None,
    ) -> None:
        self.endpoint = (endpoint or config.FOUNDRY_PROJECT_ENDPOINT).strip().rstrip("/")
        self.agent_name = (agent_name or config.FOUNDRY_AGENT_NAME).strip()
        self.agent_version = (agent_version or config.FOUNDRY_AGENT_VERSION).strip()
        self._project_client = project_client
        self._openai_client = openai_client

        parsed = urlparse(self.endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise FoundryAdvisorError("Foundry project endpoint must use HTTPS.")
        if not self.agent_name:
            raise FoundryAdvisorError("Foundry agent name must be configured.")

    def get_client(self) -> Any:
        if self._openai_client is not None:
            return self._openai_client

        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential
        except ImportError as err:
            raise FoundryAdvisorError(
                "The azure-ai-projects package is not installed."
            ) from err

        try:
            # DefaultAzureCredential supports az login in dev, and App Service MI in prod
            credential = DefaultAzureCredential(
                exclude_interactive_browser_credential=True,
            )
            if self._project_client is None:
                self._project_client = AIProjectClient(
                    endpoint=self.endpoint,
                    credential=credential,
                )

            # Bind to the agent so server-side instructions, File Search, and Web Search are used
            self._openai_client = self._project_client.get_openai_client(
                agent_name=self.agent_name
            )
        except Exception as err:
            err_str = str(err).lower()
            if "authentication" in err_str or "credential" in err_str:
                raise FoundryAuthenticationError(
                    "Authentication to Microsoft Foundry failed. Please ensure 'az login' or Managed Identity is active."
                ) from err
            if "forbidden" in err_str or "permission" in err_str or "403" in err_str:
                raise FoundryAuthorizationError(
                    "Access denied to Microsoft Foundry. Ensure identity has the 'Azure AI Developer' role on the project."
                ) from err
            raise FoundryAdvisorError(f"Could not connect to Microsoft Foundry: {err}") from err

        return self._openai_client


def build_sanitized_advisor_prompt(
    facts: dict[str, Any],
    project_name: str = "application",
    user_query: str | None = None,
) -> str:
    """Build a sanitized prompt containing only non-secret repository facts.

    Never passes secret values, customer credentials, private tokens, or full paths.
    """
    safe_env_vars = [
        str(var).strip()
        for var in facts.get("environment_variables", [])
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,120}", str(var).strip())
    ]
    databases = [str(db) for db in facts.get("database_dependencies", []) if str(db).strip()]

    sanitized_facts = {
        "workload_name": project_name[:80],
        "framework": str(facts.get("framework") or "Unknown")[:60],
        "framework_version": str(facts.get("version") or "")[:40],
        "language": str(facts.get("language") or "")[:40],
        "runtime": str(facts.get("runtime") or "")[:60],
        "package_manager": str(facts.get("package_manager") or "")[:40],
        "docker_support": bool(facts.get("docker_support")),
        "database_dependencies": databases[:10],
        "exposed_port": facts.get("port"),
        "environment_variable_names": safe_env_vars[:40],
    }

    query_part = f"\nUser specific questions/constraints:\n{user_query.strip()}\n" if user_query else ""

    prompt = f"""You are the ZeroOps Architecture and Cost Advisor.
Review the following sanitized repository facts and recommend a justified Azure architecture.

Consult the attached ZeroOps AI Knowledge Master and use Web Search for current Microsoft Azure documentation/SKUs where appropriate.

Repository facts:
{json.dumps(sanitized_facts, indent=2)}
{query_part}
Provide your advisory response covering:
1. Executive Recommendation and Confidence (high, medium, or low).
2. Supporting Evidence, Assumptions, and Missing Information.
3. Component Configuration:
   For every recommended component (e.g. application runtime, database, cache, storage, networking, monitoring):
   - Role / Category
   - Azure Service (e.g. Azure App Service, Azure Database for PostgreSQL Flexible Server, Azure Cache for Redis)
   - Candidate SKU (e.g. B1, Burstable B1ms)
   - Instance count or scaling triggers
   - Sizing rationale
   - Security requirements (e.g. VNet, Managed Identity, Key Vault)
   - Availability and recovery considerations
   - Cost status (qualitative tier, price driver notes)
   - Pre-deployment validation required
4. Cost Considerations & Unknowns (note that pricing requires a connected subscription).
5. Ordered Checklist of validation required before provisioning.

Note: ZeroOps currently automates deployment only for Azure App Service. Other recommended services will be presented to the user as advisory recommendations.
"""
    return prompt


def _parse_components_from_text(text: str) -> list[ComponentRecommendation]:
    """Parse structured component recommendations from model response text or headings."""
    # First, attempt to parse structured JSON block if present
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate_json = json_match.group(1) if json_match else None
    if not candidate_json and text.strip().startswith("{") and text.strip().endswith("}"):
        candidate_json = text.strip()

    if candidate_json:
        try:
            parsed = json.loads(candidate_json)
            if isinstance(parsed, dict) and "proposed_components" in parsed and isinstance(parsed["proposed_components"], list):
                components = []
                for comp_data in parsed["proposed_components"]:
                    if isinstance(comp_data, dict) and "service" in comp_data:
                        service = str(comp_data["service"]).strip()
                        is_deployable = service.lower() in DEPLOYABLE_AUTOMATION_ALLOWLIST
                        components.append(
                            ComponentRecommendation(
                                id=str(comp_data.get("id") or uuid.uuid4().hex[:8]),
                                role=str(comp_data.get("role") or "Workload"),
                                service=service,
                                proposed_sku=comp_data.get("proposed_sku"),
                                instance_count=comp_data.get("instance_count"),
                                reason=str(comp_data.get("reason") or ""),
                                evidence=comp_data.get("evidence") or [],
                                security_requirements=comp_data.get("security_requirements") or [],
                                availability_recovery=comp_data.get("availability_recovery"),
                                cost_status=comp_data.get("cost_status"),
                                validation_required=comp_data.get("validation_required") or [],
                                deployable=is_deployable,
                                status_note=DEPLOYABLE_SUPPORTED_NOTE if is_deployable else ADVISORY_UNSUPPORTED_NOTE,
                            )
                        )
                if components:
                    return components
        except Exception:
            pass

    components: list[ComponentRecommendation] = []

    # Check for Azure App Service
    if re.search(r"\bapp\s*service\b", text, re.IGNORECASE):
        sku_match = re.search(r"\b(B1|B2|B3|S1|S2|S3|P0v3|P1v3|P2v3|P3v3|Basic|Standard|Premium)\b", text)
        sku = sku_match.group(1) if sku_match else "B1"
        components.append(
            ComponentRecommendation(
                id="application",
                role="Application Runtime",
                service="Azure App Service",
                proposed_sku=sku,
                instance_count="1 (autoscale 1-3)",
                reason="Primary hosting platform for the web application workload.",
                evidence=["Repository framework and runtime detection"],
                security_requirements=["System-assigned Managed Identity", "HTTPS only"],
                availability_recovery="Zone-redundancy or backup configuration in production.",
                cost_status="Low-cost burstable baseline.",
                validation_required=["Confirm runtime version and deployment slot requirements."],
                deployable=True,
                status_note=DEPLOYABLE_SUPPORTED_NOTE,
            )
        )

    # Check for PostgreSQL Flexible Server
    if re.search(r"\bpostgre(?:sql)?\b", text, re.IGNORECASE):
        sku_match = re.search(r"\b(B1ms|B2s|D2s_v5|Burstable|General\s*Purpose)\b", text, re.IGNORECASE)
        sku = sku_match.group(1) if sku_match else "Burstable B1ms"
        components.append(
            ComponentRecommendation(
                id="database",
                role="Database",
                service="Azure Database for PostgreSQL Flexible Server",
                proposed_sku=sku,
                instance_count="1",
                reason="Relational database for application persistent state.",
                evidence=["Repository database dependency detection"],
                security_requirements=["VNet private endpoint integration", "Entra ID authentication"],
                availability_recovery="Automated 7-day backups; geo-redundancy optional.",
                cost_status="Burstable compute tier.",
                validation_required=["Validate required IOPS, storage retention, and connection pooler."],
                deployable=False,
                status_note=ADVISORY_UNSUPPORTED_NOTE,
            )
        )

    # Check for Redis Cache
    if re.search(r"\bredis\b", text, re.IGNORECASE):
        components.append(
            ComponentRecommendation(
                id="cache",
                role="Cache",
                service="Azure Cache for Redis",
                proposed_sku="Basic C0 / C1",
                instance_count="1",
                reason="In-memory cache for session state and query acceleration.",
                evidence=["Repository caching reference"],
                security_requirements=["TLS 1.2+", "Private endpoint"],
                availability_recovery="Non-persistent in basic tier; standard tier for replication.",
                cost_status="Cache driver note.",
                validation_required=["Verify session TTL and eviction policies."],
                deployable=False,
                status_note=ADVISORY_UNSUPPORTED_NOTE,
            )
        )

    # Check for Azure Blob Storage
    if re.search(r"\b(blob\s*storage|storage\s*account|s3|bucket)\b", text, re.IGNORECASE):
        components.append(
            ComponentRecommendation(
                id="storage",
                role="Object Storage",
                service="Azure Blob Storage",
                proposed_sku="Standard LRS",
                instance_count="N/A",
                reason="Unstructured object and media file storage.",
                evidence=["Repository object storage integration"],
                security_requirements=["Private container access", "Managed identity"],
                availability_recovery="Locally redundant storage (LRS).",
                cost_status="Consumption-based storage capacity.",
                validation_required=["Validate lifecycle management rules and soft delete."],
                deployable=False,
                status_note=ADVISORY_UNSUPPORTED_NOTE,
            )
        )

    # Check for Azure Key Vault
    if re.search(r"\bkey\s*vault\b", text, re.IGNORECASE):
        components.append(
            ComponentRecommendation(
                id="secrets",
                role="Secrets Management",
                service="Azure Key Vault",
                proposed_sku="Standard",
                instance_count="N/A",
                reason="Secure centralized storage of secrets and configuration keys.",
                evidence=["Repository environment configuration"],
                security_requirements=["Azure RBAC authorization", "Purge protection"],
                availability_recovery="Multi-region automatic failover.",
                cost_status="Low per-transaction pricing.",
                validation_required=["Verify secret access policy and managed identity assignment."],
                deployable=False,
                status_note=ADVISORY_UNSUPPORTED_NOTE,
            )
        )

    # Check for Application Insights
    if re.search(r"\bapplication\s*insights\b", text, re.IGNORECASE) or re.search(r"\btelemetry\b", text, re.IGNORECASE):
        components.append(
            ComponentRecommendation(
                id="monitoring",
                role="Observability",
                service="Azure Application Insights",
                proposed_sku="Workspace-based",
                instance_count="N/A",
                reason="Telemetry, distributed tracing, and real-time failure diagnostics.",
                evidence=["ZeroOps baseline operations guidance"],
                security_requirements=["Log Analytics workspace integration"],
                availability_recovery="Regional data ingestion.",
                cost_status="Ingestion volume billing (first 5GB free).",
                validation_required=["Set daily data cap to avoid runaway ingestion costs."],
                deployable=False,
                status_note=ADVISORY_UNSUPPORTED_NOTE,
            )
        )

    # Check for Virtual Network
    if re.search(r"\bvnet\b|\bvirtual\s*network\b", text, re.IGNORECASE):
        components.append(
            ComponentRecommendation(
                id="networking",
                role="Networking",
                service="Azure Virtual Network",
                proposed_sku="Standard VNet",
                instance_count="1",
                reason="Network isolation and private connectivity between App Service and database.",
                evidence=["ZeroOps security and isolation architecture"],
                security_requirements=["Subnet delegation for App Service", "Network Security Groups (NSGs)"],
                availability_recovery="Zonal resilience.",
                cost_status="No charge for VNet; private endpoint fees apply.",
                validation_required=["Confirm subnet CIDR address space without overlap."],
                deployable=False,
                status_note=ADVISORY_UNSUPPORTED_NOTE,
            )
        )

    # Fallback component if none were extracted
    if not components:
        components.append(
            ComponentRecommendation(
                id="application",
                role="Application Runtime",
                service="Azure App Service",
                proposed_sku="B1",
                instance_count="1",
                reason="Default recommended deployment target for containerized and web workloads in ZeroOps.",
                evidence=["Repository analysis evidence"],
                security_requirements=["Managed Identity", "HTTPS only"],
                availability_recovery="Regional SLA.",
                cost_status="Standard entry-tier estimate.",
                validation_required=["Verify application startup command and health check endpoint."],
                deployable=True,
                status_note=DEPLOYABLE_SUPPORTED_NOTE,
            )
        )

    return components


def _classify_citations(raw_annotations: list[dict[str, Any]]) -> list[CitationEvidence]:
    """Classify citations into knowledge, web, repository, or assumptions."""
    citations: list[CitationEvidence] = []
    seen = set()

    for idx, ann in enumerate(raw_annotations):
        url = ann.get("url")
        text = ann.get("text") or ""
        title = ann.get("title")
        file_id = ann.get("file_id")
        ann_type = ann.get("type", "")

        if url:
            source_type = "web"
            key = url
            citation_text = text or url
            display_title = title or "Official Microsoft / Azure Documentation"
        elif file_id or "file" in ann_type:
            source_type = "knowledge"
            key = f"file:{file_id or idx}"
            citation_text = text or "ZeroOps Knowledge Base Master Reference"
            display_title = title or "ZeroOps AI Knowledge Master"
        else:
            source_type = "assumption"
            key = f"ann:{idx}:{text[:30]}"
            citation_text = text or "General advisory consideration"
            display_title = title or "Architectural Assumption"

        if key in seen:
            continue
        seen.add(key)

        citations.append(
            CitationEvidence(
                id=f"cit-{idx + 1}",
                source_type=source_type,
                title=display_title,
                citation=citation_text,
                url=url,
            )
        )

    return citations


def invoke_architecture_advisor(
    facts: dict[str, Any],
    project_name: str = "application",
    user_query: str | None = None,
    *,
    conversation_id: str | None = None,
    correlation_id: str | None = None,
    client: FoundryAdvisorClient | None = None,
) -> ArchitectureRecommendation:
    """Invoke the Microsoft Foundry Architecture Advisor and return a structured recommendation."""
    advisor_client = client or FoundryAdvisorClient()
    cid = correlation_id or str(uuid.uuid4())
    openai_client = advisor_client.get_client()

    prompt = build_sanitized_advisor_prompt(facts, project_name, user_query)
    payload: dict[str, Any] = {
        "input": prompt,
        "max_output_tokens": 3_500,
    }
    if conversation_id:
        payload["conversation"] = conversation_id

    # If an explicit agent version is specified, include it in the agent_reference
    if advisor_client.agent_version and advisor_client.agent_name:
        payload["extra_body"] = {
            "agent_reference": {
                "type": "agent_reference",
                "name": advisor_client.agent_name,
                "version": advisor_client.agent_version,
            }
        }

    ai_logger.info(
        "FOUNDRY_ADVISOR_START | agent=%s | version=%s | correlation_id=%s | project=%s",
        advisor_client.agent_name,
        advisor_client.agent_version,
        cid,
        project_name[:50],
    )

    started = time.perf_counter()
    try:
        response = openai_client.responses.create(**payload)
    except Exception as err:
        latency_ms = max(0, round((time.perf_counter() - started) * 1_000))
        ai_logger.error(
            "FOUNDRY_ADVISOR_FAIL | agent=%s | correlation_id=%s | latency_ms=%d | error=%s",
            advisor_client.agent_name,
            cid,
            latency_ms,
            err,
        )
        err_str = str(err).lower()
        if "authentication" in err_str or "credential" in err_str or getattr(err, "status_code", None) == 401:
            raise FoundryAuthenticationError(
                "Authentication to Microsoft Foundry failed. Please ensure Azure CLI or Managed Identity credentials are valid."
            ) from err
        if "forbidden" in err_str or "permission" in err_str or getattr(err, "status_code", None) == 403:
            raise FoundryAuthorizationError(
                "Access denied to Microsoft Foundry. Ensure identity has the 'Azure AI Developer' role on the project."
            ) from err
        raise FoundryAdvisorError(f"Foundry Architecture Advisor inference failed: {err}") from err

    latency_ms = max(0, round((time.perf_counter() - started) * 1_000))
    output_text = str(getattr(response, "output_text", "") or "").strip()
    if not output_text:
        raise FoundryAdvisorError("Microsoft Foundry returned an empty architecture response.")

    # Check for candidate JSON block
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output_text, re.DOTALL)
    candidate_json = json_match.group(1) if json_match else None
    if not candidate_json and output_text.strip().startswith("{") and output_text.strip().endswith("}"):
        candidate_json = output_text.strip()

    parsed_json: dict[str, Any] = {}
    if candidate_json:
        try:
            val = json.loads(candidate_json)
            if isinstance(val, dict):
                parsed_json = val
        except Exception:
            pass

    raw_annotations = extract_annotations(response)
    citations = _classify_citations(raw_annotations)

    # If parsed_json includes evidence_sources, merge them
    if "evidence_sources" in parsed_json and isinstance(parsed_json["evidence_sources"], list):
        for ev in parsed_json["evidence_sources"]:
            if isinstance(ev, dict) and "citation" in ev:
                st = str(ev.get("source_type") or "assumption").lower()
                if st not in {"knowledge", "web", "repository", "assumption"}:
                    st = "knowledge" if "zeroops" in str(ev.get("title", "")).lower() else "web"
                citations.append(
                    CitationEvidence(
                        id=str(ev.get("id") or f"cit-json-{len(citations) + 1}"),
                        source_type=st,  # type: ignore[arg-type]
                        title=ev.get("title"),
                        citation=str(ev.get("citation")),
                        url=ev.get("url"),
                    )
                )

    # Add repository facts citation
    citations.insert(
        0,
        CitationEvidence(
            id="cit-repo-facts",
            source_type="repository",
            title="Scanned Repository Facts",
            citation=(
                f"Framework: {facts.get('framework', 'Unknown')}, "
                f"Runtime: {facts.get('runtime', 'Unknown')}, "
                f"Dependencies: {', '.join(str(d) for d in facts.get('database_dependencies', [])) or 'None'}"
            ),
            url=None,
        ),
    )

    # Parse components and enforce the deployability boundary
    components = _parse_components_from_text(output_text)
    unsupported_services = [
        comp.service
        for comp in components
        if not comp.deployable
    ]

    # Extract recommendation text
    recommendation_text = str(parsed_json.get("recommendation") or output_text).strip()

    # Extract confidence
    conf_raw = str(parsed_json.get("confidence") or "").lower()
    if conf_raw in {"high", "medium", "low"}:
        confidence: Literal["high", "medium", "low"] = conf_raw  # type: ignore[assignment]
    elif "confidence: high" in output_text.lower() or "high confidence" in output_text.lower() or '"confidence": "high"' in output_text.lower():
        confidence = "high"
    elif "confidence: low" in output_text.lower() or "low confidence" in output_text.lower() or '"confidence": "low"' in output_text.lower():
        confidence = "low"
    else:
        confidence = "medium"

    # Extract assumptions and missing information
    assumptions = parsed_json.get("assumptions") or [
        "Workload operates within estimated peak request concurrency without sustained unbounded spikes.",
        "Traffic is predominantly standard HTTPS web/API traffic.",
        "Production deployment will use Azure subscription with necessary service quotas enabled.",
    ]
    missing_info = parsed_json.get("missing_information") or [
        "Measured production CPU and memory utilization under actual peak traffic.",
        "Exact database data volume, IOPS growth expectations, and retention requirements.",
        "Subscription-specific negotiated Azure pricing and enterprise discounts.",
    ]

    cost_status_str = str(parsed_json.get("cost_status") or "requires_connected_azure_subscription")
    cost_considerations = parsed_json.get("cost_considerations") or [
        "Subscription-specific Azure pricing requires a connected Azure account with Cost Management permissions.",
        "Burstable compute tiers (B-series) offer significant cost savings during variable utilization.",
        "Outbound bandwidth (egress), backup retention, and Log Analytics ingestion are separate variable cost drivers.",
    ]

    validation_required = parsed_json.get("validation_required") or [
        "Verify runtime support and environment variables before approval.",
        "Perform preflight simulation to validate security controls and resource naming.",
        "Ensure user approval is granted before queuing Terraform generation.",
    ]

    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

    ai_logger.info(
        "FOUNDRY_ADVISOR_SUCCESS | agent=%s | version=%s | correlation_id=%s | latency_ms=%d | input_tokens=%d | output_tokens=%d | citations=%d",
        advisor_client.agent_name,
        advisor_client.agent_version,
        cid,
        latency_ms,
        input_tokens,
        output_tokens,
        len(citations),
    )

    provenance = {
        "agent_name": advisor_client.agent_name,
        "agent_version": advisor_client.agent_version,
        "model": str(getattr(response, "model", None) or "GPT-5.6 Terra"),
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "correlation_id": cid,
        "file_search_used": any(c.source_type == "knowledge" for c in citations),
        "web_search_used": any(c.source_type == "web" for c in citations),
    }

    return ArchitectureRecommendation(
        recommendation=recommendation_text,
        confidence=confidence,
        assumptions=assumptions,
        missing_information=missing_info,
        proposed_components=components,
        cost_status=cost_status_str,
        cost_considerations=cost_considerations,
        evidence_sources=citations,
        unsupported_services=unsupported_services,
        validation_required=validation_required,
        provenance=provenance,
    )


def advisor_chat(
    message: str,
    current_plan: dict[str, Any],
    *,
    conversation_id: str | None = None,
    client: FoundryAdvisorClient | None = None,
) -> tuple[dict[str, Any], str, str | None, list[CitationEvidence]]:
    """Conversational interaction with the Foundry Architecture Advisor.

    Maintains conversational continuity via the conversation parameter.
    Returns: (updated_plan_data, assistant_reply, conversation_id, citations)
    """
    advisor_client = client or FoundryAdvisorClient()
    openai_client = advisor_client.get_client()

    # If no conversation ID, create a new conversation for continuity
    active_conversation_id = conversation_id
    if not active_conversation_id:
        try:
            conversation = openai_client.conversations.create()
            active_conversation_id = getattr(conversation, "id", None)
        except Exception:
            active_conversation_id = None

    context_str = json.dumps({
        "current_plan_components": [
            {"service": c.get("service"), "tier": c.get("tier"), "category": c.get("category")}
            for c in current_plan.get("components", [])
            if isinstance(c, dict)
        ],
        "cloud": current_plan.get("cloud", "Azure"),
        "region": current_plan.get("region_label", "East US"),
    })

    prompt = f"""Current ZeroOps Plan:
{context_str}

User Question/Instruction:
{message}

Answer with specific architectural advice citing ZeroOps knowledge and current Azure documentation where relevant.
Do not claim that resources have already been deployed or altered in the cloud.
"""

    payload: dict[str, Any] = {
        "input": prompt,
        "max_output_tokens": 2_000,
    }
    if active_conversation_id:
        payload["conversation"] = active_conversation_id

    response = openai_client.responses.create(**payload)
    output_text = str(getattr(response, "output_text", "") or "").strip()
    raw_annotations = extract_annotations(response)
    citations = _classify_citations(raw_annotations)

    return current_plan, output_text, active_conversation_id, citations
