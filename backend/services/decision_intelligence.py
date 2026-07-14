"""Deterministic decision controls for ZeroOps Cloud Architect.

The module deliberately has no model or cloud-provider calls.  It transforms
recorded repository analysis, an approved architecture decision, and verified
target readiness into explainable graph, preflight, and outcome metrics.  This
keeps recommendations grounded in evidence and prevents an LLM response from
becoming an infrastructure command.
"""

from __future__ import annotations

from typing import Any, Iterable


RISK_MODEL_VERSION = "deterministic-policy-v1"


def _items(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_items(value: Any) -> list[str]:
    return [str(item).strip() for item in _items(value) if str(item).strip()]


def _component(plan: dict[str, Any], component_id: str) -> dict[str, Any] | None:
    return next(
        (item for item in _items(plan.get("components")) if item.get("id") == component_id),
        None,
    )


def _risk_level(score: int) -> str:
    if score >= 70:
        return "critical"
    if score >= 45:
        return "high"
    if score >= 20:
        return "moderate"
    return "low"


def _node(node_id: str, kind: str, label: str, **properties: Any) -> dict[str, Any]:
    return {"id": node_id, "type": kind, "label": label, "properties": properties}


def build_knowledge_graph(
    *,
    project: Any,
    analysis: dict[str, Any] | None,
    plan: dict[str, Any] | None,
    plan_revision: int | None,
) -> dict[str, Any]:
    """Build a redacted graph from persisted application evidence.

    Environment-variable *names* may establish a secret relationship; their
    values and any source-file contents are never accepted by this function.
    """
    analysis = analysis or {}
    plan = plan or {}
    project_id = str(getattr(project, "id", "project"))
    project_node = f"project:{project_id}"
    analysis_node = f"analysis:{project_id}"
    plan_node = f"plan:{project_id}:v{plan_revision or 0}"
    nodes = [
        _node(
            project_node,
            "project",
            str(getattr(project, "name", "Application")),
            framework=getattr(project, "framework", None),
            language=getattr(project, "language", None),
            region=getattr(project, "region", None),
        ),
        _node(
            analysis_node,
            "source_analysis",
            "Recorded source analysis",
            framework=analysis.get("framework"),
            runtime=analysis.get("runtime"),
            database_dependency_count=len(_string_items(analysis.get("database_dependencies"))),
            finding_count=len(_string_items(analysis.get("vulnerabilities"))),
        ),
    ]
    edges = [{"source": project_node, "target": analysis_node, "relation": "has_evidence"}]

    if plan:
        nodes.append(
            _node(
                plan_node,
                "architecture_plan",
                f"Architecture plan v{plan_revision or 1}",
                cloud=plan.get("cloud"),
                region=plan.get("region_label"),
            )
        )
        edges.append({"source": analysis_node, "target": plan_node, "relation": "informs"})
        edges.append({"source": project_node, "target": plan_node, "relation": "uses"})

        for item in _items(plan.get("components")):
            component_id = str(item.get("id") or "component")
            node_id = f"component:{project_id}:{component_id}"
            nodes.append(
                _node(
                    node_id,
                    "cloud_component",
                    str(item.get("service") or component_id),
                    category=item.get("category"),
                    tier=item.get("tier"),
                    deployable=bool(item.get("deployable")),
                )
            )
            edges.append({"source": plan_node, "target": node_id, "relation": "recommends"})

        for name in _string_items(analysis.get("environment_variables")):
            reference_id = f"config_reference:{project_id}:{name.lower()}"
            nodes.append(_node(reference_id, "configuration_reference", name, value_present=False))
            edges.append({"source": analysis_node, "target": reference_id, "relation": "references"})
            secret = _component(plan, "secrets")
            if secret:
                edges.append({"source": reference_id, "target": f"component:{project_id}:secrets", "relation": "secured_by"})

        for index, finding in enumerate(_string_items(analysis.get("vulnerabilities"))):
            finding_id = f"finding:{project_id}:{index}"
            nodes.append(_node(finding_id, "source_finding", f"Source finding {index + 1}", summary=finding))
            edges.append({"source": analysis_node, "target": finding_id, "relation": "contains"})

    return {
        "version": 1,
        "model": RISK_MODEL_VERSION,
        "plan_revision": plan_revision,
        "nodes": nodes,
        "edges": edges,
    }


def simulate_digital_twin(
    *,
    project: Any,
    plan: dict[str, Any] | None,
    plan_revision: int | None,
    analysis: dict[str, Any] | None,
    target_status: dict[str, Any] | None,
    plan_approved: bool = False,
) -> dict[str, Any]:
    """Evaluate a proposed configuration without provisioning Azure resources.

    The score is an additive, bounded policy score.  Every applied weight is
    returned with the check, making the result reviewable and testable.
    """
    plan = plan or {}
    analysis = analysis or {}
    target_status = target_status or {}
    checks: list[dict[str, Any]] = []
    score = 5  # baseline review risk; no plan is automatically risk-free.

    def add_check(check_id: str, label: str, status: str, detail: str, risk_weight: int = 0) -> None:
        nonlocal score
        score += risk_weight
        checks.append({
            "id": check_id,
            "label": label,
            "status": status,
            "detail": detail,
            "risk_weight": risk_weight,
        })

    application = _component(plan, "application")
    if not plan or not application:
        add_check("architecture", "Architecture plan", "blocked", "Generate an architecture plan from source analysis before deployment.", 35)
    elif application.get("service") != "Azure App Service" or not application.get("deployable"):
        add_check("deployment-engine", "Deployment engine compatibility", "blocked", "The selected application service is not enabled by this workspace's deployment engine.", 35)
    else:
        add_check("deployment-engine", "Deployment engine compatibility", "passed", "The selected Azure App Service architecture is supported by the configured deployment engine.")

    if plan_approved:
        add_check("human-approval", "Human approval gate", "passed", "The current architecture revision has an explicit user approval.")
    else:
        add_check("human-approval", "Human approval gate", "warning", "This preflight is informative only until the current architecture revision receives explicit user approval.")

    if analysis:
        add_check("source-evidence", "Source evidence", "passed", "The simulation is based on the latest recorded repository analysis.")
    else:
        add_check("source-evidence", "Source evidence", "blocked", "Analyze the application before relying on an infrastructure recommendation.", 35)

    if bool(target_status.get("any_ready")):
        add_check("azure-target", "Azure target readiness", "passed", "A connected Azure application environment is available for the deployment workflow.")
    else:
        add_check("azure-target", "Azure target readiness", "blocked", "Connect and validate an Azure application environment before executing changes.", 35)

    vulnerabilities = _string_items(analysis.get("vulnerabilities"))
    if vulnerabilities:
        weight = min(24, len(vulnerabilities) * 8)
        add_check("source-findings", "Source security findings", "warning", f"{len(vulnerabilities)} recorded source finding(s) require review before production release.", weight)
    else:
        add_check("source-findings", "Source security findings", "passed", "No recorded dependency or source findings are currently attached to this analysis.")

    unresolved = _string_items(analysis.get("unresolved_questions"))
    if unresolved:
        weight = min(12, len(unresolved) * 4)
        add_check("open-questions", "Open architecture questions", "warning", f"{len(unresolved)} unresolved architecture question(s) remain in the recorded analysis.", weight)
    else:
        add_check("open-questions", "Open architecture questions", "passed", "No unresolved questions were recorded by the source analysis.")

    data_components = [item for item in _items(plan.get("components")) if item.get("id") in {"database", "cache", "storage", "networking"}]
    needing_configuration = [item for item in data_components if not item.get("deployable")]
    if needing_configuration:
        add_check("data-configuration", "Data-service configuration", "warning", "Data or network components need an explicit configuration and access review before use.", 10)
    else:
        add_check("data-configuration", "Data-service configuration", "passed", "No additional data-service configuration was inferred from the selected architecture.")

    cost = plan.get("cost") if isinstance(plan.get("cost"), dict) else {}
    if cost.get("monthly_estimate") is None:
        add_check("cost-evidence", "Cost evidence", "warning", "Subscription-specific pricing has not been validated; no cost estimate is assumed.", 6)
    else:
        add_check("cost-evidence", "Cost evidence", "passed", "The plan includes a recorded subscription-specific cost estimate.")

    score = min(100, max(0, score))
    blocked = any(check["status"] == "blocked" for check in checks)
    warned = any(check["status"] == "warning" for check in checks)
    status = "blocked" if blocked else "requires_review" if warned else "ready"
    proposed_changes = [check["detail"] for check in checks if check["status"] in {"blocked", "warning"}]
    snapshot = {
        "project": str(getattr(project, "name", "Application")),
        "plan_revision": plan_revision,
        "region": plan.get("region_label"),
        "application_service": application.get("service") if application else None,
        "component_count": len(_items(plan.get("components"))),
        "target_ready": bool(target_status.get("any_ready")),
        "target_labels": [str(target.get("label")) for target in _items(target_status.get("targets")) if target.get("label")],
    }
    summary = {
        "blocked": "Preflight blocked execution. Resolve the blocking checks; no infrastructure change was started.",
        "requires_review": "Preflight found review items. A user-approved plan is still required before any infrastructure change.",
        "ready": "Preflight passed its recorded checks. Deployment still requires an approved plan and runtime health validation.",
    }[status]
    return {
        "model": RISK_MODEL_VERSION,
        "status": status,
        "risk_score": score,
        "risk_level": _risk_level(score),
        "summary": summary,
        "snapshot": snapshot,
        "checks": checks,
        "proposed_changes": proposed_changes,
    }


def decision_accuracy_summary(evaluations: Iterable[Any]) -> dict[str, Any]:
    """Calculate accuracy only from terminal, observed deployment outcomes."""
    rows = list(evaluations)
    terminal = [row for row in rows if getattr(row, "status", None) in {"successful", "failed"}]
    successful = sum(1 for row in terminal if getattr(row, "status", None) == "successful")
    failed = sum(1 for row in terminal if getattr(row, "status", None) == "failed")
    pending = sum(1 for row in rows if getattr(row, "status", None) == "pending")
    evaluated = len(terminal)
    return {
        "available": evaluated > 0,
        "outcome_accuracy_percent": round((successful / evaluated) * 100, 1) if evaluated else None,
        "evaluated_deployments": evaluated,
        "successful_deployments": successful,
        "failed_deployments": failed,
        "pending_deployments": pending,
        "methodology": "Accuracy is the share of recorded architecture decisions whose deployment completed and passed runtime health validation. Pending, blocked, and unobserved decisions are excluded.",
    }
