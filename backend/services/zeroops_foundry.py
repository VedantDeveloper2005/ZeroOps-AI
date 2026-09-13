"""Centralized Azure AI Foundry client service for ZeroOps AI.

Integrates the configured Microsoft Foundry Prompt Agent (`zeroops-architecture-advisor`)
as the primary AI engine for the ZeroOps college demonstration. Supports:
- REPOSITORY_ANALYSIS
- ARCHITECTURE_RECOMMENDATION
- ARCHITECTURE_CHAT
- FAILURE_ANALYSIS
- FIX_RECOMMENDATION
- SECURITY_ANALYSIS
- TERRAFORM_GENERATION
- PIPELINE_EXPLANATION
- COST_OPTIMIZATION
- DEPLOYMENT_GUIDANCE

Enforces strict boundaries: factual scanner detection stays authoritative;
AI recommendations cannot directly apply infrastructure or claim success
without recorded execution results.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Type, TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel

from backend import config

logger = logging.getLogger("zeroops.foundry")
ai_logger = logging.getLogger("zeroops.ai.observability")

T = TypeVar("T", bound=BaseModel)

# Supported Task Types per specification
TASK_REPOSITORY_ANALYSIS = "REPOSITORY_ANALYSIS"
TASK_ARCHITECTURE_RECOMMENDATION = "ARCHITECTURE_RECOMMENDATION"
TASK_ARCHITECTURE_CHAT = "ARCHITECTURE_CHAT"
TASK_FAILURE_ANALYSIS = "FAILURE_ANALYSIS"
TASK_FIX_RECOMMENDATION = "FIX_RECOMMENDATION"
TASK_SECURITY_ANALYSIS = "SECURITY_ANALYSIS"
TASK_TERRAFORM_GENERATION = "TERRAFORM_GENERATION"
TASK_PIPELINE_EXPLANATION = "PIPELINE_EXPLANATION"
TASK_COST_OPTIMIZATION = "COST_OPTIMIZATION"
TASK_DEPLOYMENT_GUIDANCE = "DEPLOYMENT_GUIDANCE"


class FoundryAgentError(RuntimeError):
    """Raised when an Azure AI Foundry agent invocation fails."""

    def __init__(
        self,
        message: str,
        *,
        task_type: str = "UNKNOWN",
        status_code: int | None = None,
        error_code: str = "unknown_error",
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.task_type = task_type
        self.status_code = status_code
        self.error_code = error_code
        self.original_error = original_error


class FoundryAuthenticationError(FoundryAgentError):
    """Raised when Azure authentication fails (e.g. invalid az login or Managed Identity)."""


class FoundryAuthorizationError(FoundryAgentError):
    """Raised when the identity lacks Azure AI Developer permissions on the Foundry project."""


@dataclass(frozen=True)
class FoundryProvenance:
    provider: str = "azure-ai-foundry"
    agent: str = "zeroops-architecture-advisor"
    agent_version: str = "3"
    task_type: str = ""
    execution_mode: str = "live"
    ai_used: bool = True
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "agent": self.agent,
            "agent_version": self.agent_version,
            "task_type": self.task_type,
            "execution_mode": self.execution_mode,
            "ai_used": self.ai_used,
            "latency_ms": self.latency_ms,
            "fallback_reason": self.fallback_reason,
        }


def extract_json_from_text(text: str) -> dict[str, Any]:
    """Extract and parse the first JSON object found within arbitrary model text."""
    trimmed = text.strip()
    # 1. Direct JSON
    if trimmed.startswith("{") and trimmed.endswith("}"):
        try:
            val = json.loads(trimmed)
            if isinstance(val, dict):
                return val
        except Exception:
            pass

    # 2. Markdown fenced code block
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if json_match:
        try:
            val = json.loads(json_match.group(1))
            if isinstance(val, dict):
                return val
        except Exception:
            pass

    # 3. Broad search for any outer braces
    broad_match = re.search(r"(\{.*\})", text, re.DOTALL)
    if broad_match:
        try:
            val = json.loads(broad_match.group(1))
            if isinstance(val, dict):
                return val
        except Exception:
            pass

    raise ValueError("No valid JSON object could be extracted from the model response.")


class ZeroOpsFoundryClient:
    """Unified client communicating with the retained ZeroOps Foundry agent."""

    def __init__(
        self,
        endpoint: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        *,
        project_client: Any | None = None,
        openai_client: Any | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.endpoint = (endpoint or config.FOUNDRY_PROJECT_ENDPOINT).strip().rstrip("/")
        self.agent_name = (agent_name or config.FOUNDRY_AGENT_NAME or "zeroops-architecture-advisor").strip()
        self.agent_version = (agent_version or config.FOUNDRY_AGENT_VERSION or "3").strip()
        self.timeout_seconds = timeout_seconds or getattr(config, "FOUNDRY_REQUEST_TIMEOUT_SECONDS", 120)

        self._project_client = project_client
        self._openai_client = openai_client

        parsed = urlparse(self.endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise FoundryAgentError(
                "Foundry project endpoint must use HTTPS.",
                error_code="invalid_endpoint",
            )
        if not self.agent_name:
            raise FoundryAgentError(
                "Foundry agent name must be configured.",
                error_code="missing_agent_name",
            )

    def _get_openai_client(self) -> Any:
        """Obtain or reuse the project's OpenAI-compatible client."""
        if self._openai_client is not None:
            return self._openai_client

        try:
            from azure.ai.projects import AIProjectClient
            from backend.services.foundry_identity import foundry_credential
        except ImportError as err:
            raise FoundryAgentError(
                "azure-ai-projects or azure-identity package is missing.",
                error_code="sdk_missing",
                original_error=err,
            ) from err

        try:
            credential = foundry_credential()
            if self._project_client is None:
                self._project_client = AIProjectClient(
                    endpoint=self.endpoint,
                    credential=credential,
                    allow_preview=True,
                )
            # Agent invocation is scoped to the existing agent; project responses
            # require agents/write even when an agent_reference is supplied.
            self._openai_client = self._project_client.get_openai_client(
                agent_name=self.agent_name,
                timeout=self.timeout_seconds,
                max_retries=0,
            )
            return self._openai_client
        except Exception as err:
            err_str = str(err).lower()
            if "authentication" in err_str or "credential" in err_str:
                raise FoundryAuthenticationError(
                    "Azure authentication to Microsoft Foundry failed. Please ensure 'az login' or Managed Identity is active.",
                    error_code="auth_failed",
                    original_error=err,
                ) from err
            if "forbidden" in err_str or "permission" in err_str or "403" in err_str:
                raise FoundryAuthorizationError(
                    "Access denied to Microsoft Foundry project. Ensure the identity has 'Azure AI Developer' role.",
                    status_code=403,
                    error_code="forbidden",
                    original_error=err,
                ) from err
            raise FoundryAgentError(
                f"Failed to initialize Azure AI Foundry client: {err}",
                error_code="init_failed",
                original_error=err,
            ) from err

    def call_agent(
        self,
        task_type: str,
        user_input: str,
        context: str = "",
        *,
        demo_mode: bool = True,
        max_output_tokens: int = 2000,
        temperature: float = 0.1,
    ) -> tuple[str, FoundryProvenance]:
        """Invoke the unified Foundry demo v1 agent using the official extra_body pattern."""
        prompt = f"""TASK_TYPE: {task_type}
DEMO_MODE: {str(demo_mode).lower()}

CONTEXT:
{context}

USER_REQUEST:
{user_input}

Follow the ZeroOps instructions configured in the Foundry agent.
Only perform the requested TASK_TYPE.
Base conclusions on the supplied repository, logs, architecture,
scan results, infrastructure plan or deployment data.
Never claim an operation succeeded unless execution results confirm it.
"""
        client = self._get_openai_client()

        # Step 22: Safe logging
        logger.info(
            "[ZeroOps AI] Provider: Azure AI Foundry | Agent: %s | Agent version: %s | Task: %s | Execution mode: live",
            self.agent_name,
            self.agent_version,
            task_type,
        )
        started = time.perf_counter()
        try:
            create_kwargs: dict[str, Any] = {
                "input": [{"role": "user", "content": prompt}],
                "extra_body": {
                    "agent_reference": {
                        "name": self.agent_name,
                        "version": self.agent_version,
                        "type": "agent_reference",
                    }
                },
            }
            if max_output_tokens is not None:
                create_kwargs["max_output_tokens"] = max_output_tokens

            response = client.responses.create(**create_kwargs)
        except Exception as err:
            latency_ms = max(0, round((time.perf_counter() - started) * 1_000))
            err_str = str(err).lower()
            status_code = getattr(err, "status_code", None)

            logger.warning(
                "[ZeroOps AI] Execution mode: fallback | Task: %s | Reason: foundry_invocation_error (%s)",
                task_type,
                type(err).__name__,
            )

            if status_code == 401 or "authentication" in err_str or "unauthorized" in err_str:
                raise FoundryAuthenticationError(
                    "Microsoft Foundry authentication failed (401). Check Azure login or Managed Identity.",
                    task_type=task_type,
                    status_code=401,
                    error_code="auth_failure",
                    original_error=err,
                ) from err
            if status_code == 403 or "forbidden" in err_str or "permission" in err_str:
                raise FoundryAuthorizationError(
                    "Microsoft Foundry access denied (403). Ensure 'Azure AI Developer' RBAC role is assigned.",
                    task_type=task_type,
                    status_code=403,
                    error_code="permission_denied",
                    original_error=err,
                ) from err
            raise FoundryAgentError(
                f"Microsoft Foundry agent call failed: {err}",
                task_type=task_type,
                status_code=status_code,
                error_code="call_failed",
                original_error=err,
            ) from err

        latency_ms = max(0, round((time.perf_counter() - started) * 1_000))
        if getattr(response, "status", "completed") != "completed":
            raise FoundryAgentError(
                "Microsoft Foundry response did not complete.",
                task_type=task_type,
                error_code="incomplete_response",
            )
        output_text = str(getattr(response, "output_text", "") or "").strip()

        if not output_text:
            logger.warning(
                "[ZeroOps AI] Execution mode: fallback | Task: %s | Reason: empty_response",
                task_type,
            )
            raise FoundryAgentError(
                "Microsoft Foundry agent returned an empty response.",
                task_type=task_type,
                error_code="empty_response",
            )

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

        provenance = FoundryProvenance(
            provider="azure-ai-foundry",
            agent=self.agent_name,
            agent_version=self.agent_version,
            task_type=task_type,
            execution_mode="live",
            ai_used=True,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        return output_text, provenance

    def call_agent_structured(
        self,
        task_type: str,
        user_input: str,
        context: str = "",
        *,
        output_contract: Type[T] | None = None,
        demo_mode: bool = True,
        max_output_tokens: int = 2500,
    ) -> tuple[dict[str, Any] | T, FoundryProvenance]:
        """Invoke agent and parse/validate response against a structured JSON contract."""
        system_hint = (
            "\n\nIMPORTANT: Respond with ONLY a valid JSON object matching the requested schema. "
            "Do not include markdown codeblocks or extra conversation text."
        )
        raw_text, provenance = self.call_agent(
            task_type=task_type,
            user_input=user_input + system_hint,
            context=context,
            demo_mode=demo_mode,
            max_output_tokens=max_output_tokens,
        )

        data = extract_json_from_text(raw_text)
        if output_contract is not None:
            validated = output_contract.model_validate(data)
            return validated, provenance
        return data, provenance

    # ─────────────────────────────────────────────────────────────
    # Workload Task Implementations
    # ─────────────────────────────────────────────────────────────

    def analyze_repository(
        self,
        source_facts: dict[str, Any],
        safe_files: list[dict[str, Any]] | None = None,
        repo_tree: str = "",
    ) -> tuple[dict[str, Any], FoundryProvenance]:
        """TASK_TYPE=REPOSITORY_ANALYSIS: Enrich real scanned repository facts."""
        context = json.dumps(
            {
                "scanned_facts": source_facts,
                "safe_files": safe_files or [],
                "repository_tree": repo_tree[:4000],
            },
            indent=2,
        )
        user_input = (
            "Analyze the detected repository facts. Return a JSON object with: "
            "'explanation' (string summarizing app structure), "
            "'deployment_risk' (string detailing key unknowns or prerequisites), "
            "'recommendations' (list of up to 5 non-destructive checks), "
            "'unresolved_questions' (list of up to 5 questions to confirm before launch)."
        )
        return self.call_agent_structured(
            task_type=TASK_REPOSITORY_ANALYSIS,
            user_input=user_input,
            context=context,
        )

    def recommend_architecture(
        self,
        facts: dict[str, Any],
        project_name: str = "application",
        user_query: str | None = None,
    ) -> tuple[dict[str, Any], FoundryProvenance]:
        """TASK_TYPE=ARCHITECTURE_RECOMMENDATION: Suggest Azure infrastructure."""
        context = json.dumps(
            {
                "project_name": project_name,
                "scanned_facts": facts,
                "user_intent": user_query or "Deploy a production-ready Azure architecture",
            },
            indent=2,
        )
        user_input = (
            "Recommend an Azure architecture for this application. Return a JSON object with: "
            "'recommendation' (string explaining choice), "
            "'confidence' ('high', 'medium', or 'low'), "
            "'assumptions' (list of strings), "
            "'missing_information' (list of strings), "
            "'proposed_components' (list of objects with 'id', 'role', 'service', 'proposed_sku', 'instance_count', 'reason', 'security_requirements'), "
            "'cost_considerations' (list of strings)."
        )
        return self.call_agent_structured(
            task_type=TASK_ARCHITECTURE_RECOMMENDATION,
            user_input=user_input,
            context=context,
        )

    def architecture_chat(
        self,
        message: str,
        current_plan: dict[str, Any],
        context_extra: str = "",
    ) -> tuple[str, FoundryProvenance]:
        """TASK_TYPE=ARCHITECTURE_CHAT: Interactive advice on approved plan."""
        context = json.dumps(
            {
                "current_plan": current_plan,
                "additional_context": context_extra,
            },
            indent=2,
        )
        user_input = f"Answer the following user query about the architecture plan: {message}"
        return self.call_agent(
            task_type=TASK_ARCHITECTURE_CHAT,
            user_input=user_input,
            context=context,
            max_output_tokens=config.AI_CHAT_MAX_OUTPUT_TOKENS,
        )

    def analyze_failure(
        self,
        logs: list[str] | str,
        build_logs: list[str] | str = "",
        events: list[str] | None = None,
        stage: str = "",
    ) -> tuple[dict[str, Any], FoundryProvenance]:
        """TASK_TYPE=FAILURE_ANALYSIS: Evidence-bound failure diagnosis."""
        def format_logs(val: Any) -> str:
            if isinstance(val, list):
                return "\n".join(str(l) for l in val[-50:])
            return str(val)[-4000:]

        context = f"""FAILED STAGE: {stage}
=== EXECUTION LOGS ===
{format_logs(logs)}

=== BUILD LOGS ===
{format_logs(build_logs)}

=== EVENTS ===
{format_logs(events or [])}
"""
        user_input = (
            "Analyze the failure logs. Return a JSON object with: "
            "'failure_summary' (one-sentence diagnosis), "
            "'root_cause' (detailed explanation citing specific lines or errors), "
            "'severity' ('critical', 'error', or 'warning'), "
            "'recommended_fix' (high-level remediation), "
            "'step_by_step_resolution' (list of up to 6 actionable numbered steps), "
            "'safe_to_auto_fix' (boolean, false if destructive or requires human credentials)."
        )
        return self.call_agent_structured(
            task_type=TASK_FAILURE_ANALYSIS,
            user_input=user_input,
            context=context,
        )

    def recommend_fix(
        self,
        failure_details: dict[str, Any],
        logs: str = "",
    ) -> tuple[dict[str, Any], FoundryProvenance]:
        """TASK_TYPE=FIX_RECOMMENDATION: Targeted code / config fix checklist."""
        context = json.dumps(
            {
                "failure_details": failure_details,
                "recent_logs": logs[-2000:],
            },
            indent=2,
        )
        user_input = (
            "Suggest concrete non-destructive remediation for this issue. Return a JSON object with: "
            "'recommended_fix' (string), "
            "'suggested_changes' (list of objects with 'file', 'description', 'action'), "
            "'step_by_step_resolution' (list of strings)."
        )
        return self.call_agent_structured(
            task_type=TASK_FIX_RECOMMENDATION,
            user_input=user_input,
            context=context,
        )

    def analyze_security(
        self,
        scanner_findings: dict[str, Any],
        context: str = "",
    ) -> tuple[dict[str, Any], FoundryProvenance]:
        """TASK_TYPE=SECURITY_ANALYSIS: Synthesize real scanner findings."""
        ctx = json.dumps(
            {
                "real_scanner_findings": scanner_findings,
                "context": context,
            },
            indent=2,
        )
        user_input = (
            "Explain these verified security scanner findings without fabricating new ones. "
            "Return a JSON object with: "
            "'summary' (string overview), "
            "'critical_issues' (list of strings), "
            "'remediations' (list of actionable steps), "
            "'should_block_deployment' (boolean indicating if critical vulnerability or secret is present)."
        )
        return self.call_agent_structured(
            task_type=TASK_SECURITY_ANALYSIS,
            user_input=user_input,
            context=ctx,
        )

    def generate_terraform(
        self,
        approved_plan: dict[str, Any],
        constraints: list[str] | None = None,
    ) -> tuple[dict[str, Any], FoundryProvenance]:
        """TASK_TYPE=TERRAFORM_GENERATION: Propose Terraform HCL for approved plan."""
        context = json.dumps(
            {
                "approved_plan": approved_plan,
                "allowed_constraints": constraints or [
                    "Only azurerm_resource_group, azurerm_service_plan, azurerm_linux_web_app, azurerm_role_assignment",
                    "Do not embed secret values or passwords in HCL",
                    "Use variables.tf for configurable parameters",
                ],
            },
            indent=2,
        )
        user_input = (
            "Generate production-ready Terraform HCL for this approved plan. Return a JSON object with: "
            "'files' (list of objects with 'path' and 'content', e.g. versions.tf, providers.tf, variables.tf, main.tf, outputs.tf), "
            "'summary' (short summary of resources generated)."
        )
        return self.call_agent_structured(
            task_type=TASK_TERRAFORM_GENERATION,
            user_input=user_input,
            context=context,
        )

    def explain_pipeline(
        self,
        stages: list[dict[str, Any]],
        current_stage: str = "",
        status: str = "",
        logs: str = "",
    ) -> tuple[str, FoundryProvenance]:
        """TASK_TYPE=PIPELINE_EXPLANATION: Explain execution state clearly."""
        context = json.dumps(
            {
                "stages": stages,
                "current_stage": current_stage,
                "pipeline_status": status,
                "recent_logs": logs[-1500:],
            },
            indent=2,
        )
        user_input = "Provide a concise narrative explanation of the pipeline's progress, current stage, and any blocker."
        return self.call_agent(
            task_type=TASK_PIPELINE_EXPLANATION,
            user_input=user_input,
            context=context,
        )

    def optimize_cost(
        self,
        current_plan: dict[str, Any],
        constraints: list[str] | None = None,
    ) -> tuple[dict[str, Any], FoundryProvenance]:
        """TASK_TYPE=COST_OPTIMIZATION: Suggest realistic lower-cost options."""
        context = json.dumps(
            {
                "current_plan": current_plan,
                "constraints": constraints or ["Maintain high availability for production"],
            },
            indent=2,
        )
        user_input = (
            "Analyze this Azure plan for cost reduction opportunities. Return a JSON object with: "
            "'cost_summary' (string), "
            "'optimizations' (list of objects with 'title', 'service', 'proposed_change', 'tradeoffs'), "
            "'estimated_savings_percentage' (approximate percentage string)."
        )
        return self.call_agent_structured(
            task_type=TASK_COST_OPTIMIZATION,
            user_input=user_input,
            context=context,
        )

    def guide_deployment(
        self,
        current_status: str,
        target: str = "azure-app-service",
        project_info: dict[str, Any] | None = None,
    ) -> tuple[str, FoundryProvenance]:
        """TASK_TYPE=DEPLOYMENT_GUIDANCE: Describe next operational step."""
        context = json.dumps(
            {
                "status": current_status,
                "target": target,
                "project": project_info or {},
            },
            indent=2,
        )
        user_input = "Explain what the next deployment step is and what verification the user should perform."
        return self.call_agent(
            task_type=TASK_DEPLOYMENT_GUIDANCE,
            user_input=user_input,
            context=context,
        )


# Global singleton instance cache
_client_instance: ZeroOpsFoundryClient | None = None


def get_foundry_client() -> ZeroOpsFoundryClient:
    """Retrieve or construct the global ZeroOpsFoundryClient."""
    global _client_instance
    if _client_instance is None:
        _client_instance = ZeroOpsFoundryClient()
    return _client_instance


def set_foundry_client(client: ZeroOpsFoundryClient | None) -> None:
    """Explicitly inject a client (used for mocking in unit tests)."""
    global _client_instance
    _client_instance = client
