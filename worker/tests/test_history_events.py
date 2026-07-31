from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from worker.contracts import ExecutionEnvelope, payload_with_digest
from worker.history_events import build_workflow_event
from worker.tests.test_execution_contract import (
    ARTIFACT_ID,
    BUNDLE_DIGEST,
    JOB_ID,
    OPAQUE_CONTAINER,
    PLAN_DIGEST,
    PROJECT_ID,
    TENANT_ID,
    USER_ID,
    WORKFLOW_ID,
    base_plan_payload,
)


# Contract compatibility is checked only in tests. The VMSS worker runtime has
# no dependency on, or import path to, the Azure Functions application.
FUNCTIONS_COMMON = Path(__file__).resolve().parents[2] / "functions" / "common"
sys.path.insert(0, str(FUNCTIONS_COMMON))
from zeroops_functions.contracts import WorkflowEventV1  # noqa: E402


HISTORY_ARTIFACT_ID = "99999999-9999-4999-8999-999999999999"
HISTORY_DIGEST = "d" * 64


def plan_envelope() -> ExecutionEnvelope:
    return ExecutionEnvelope.from_mapping(payload_with_digest(base_plan_payload()))


def apply_envelope() -> ExecutionEnvelope:
    payload = base_plan_payload()
    payload["operation"] = "apply"
    payload["saved_plan"] = {
        "blob_name": (
            f"tenants/{TENANT_ID}/workflows/{WORKFLOW_ID}/"
            f"plans/{JOB_ID}/{PLAN_DIGEST}.tfplan"
        ),
        "etag": '"executor-plan-etag"',
        "sha256": PLAN_DIGEST,
        "plan_job_digest": "c" * 64,
        "bundle_sha256": BUNDLE_DIGEST,
    }
    payload["approval"] = {
        "approval_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "decision": "approved",
        "approved_by": USER_ID,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "plan_job_digest": "c" * 64,
        "plan_sha256": PLAN_DIGEST,
        "plan_etag": '"executor-plan-etag"',
        "bundle_sha256": BUNDLE_DIGEST,
    }
    return ExecutionEnvelope.from_mapping(payload_with_digest(payload))


def sanitized_plan_result() -> dict:
    return {
        "status": "planned",
        "completed_at": "2026-07-29T10:00:00+00:00",
        "plan_sha256": PLAN_DIGEST,
        "summary": {
            "format_version": "1.2",
            "terraform_version": "1.15.8",
            "actions": {
                "create": 2,
                "update": 1,
                "delete": 0,
                "replace": 0,
                "read": 0,
                "no_op": 0,
            },
            "resource_kinds": [
                "azurerm_linux_virtual_machine_scale_set",
                "azurerm_storage_account",
            ],
        },
        "history_artifact": {
            "artifact_id": HISTORY_ARTIFACT_ID,
            "kind": "terraform-plan-summary",
            "sha256": HISTORY_DIGEST,
            "storage_container": OPAQUE_CONTAINER,
            "storage_path": (
                f"objects/{HISTORY_ARTIFACT_ID}/v1/{HISTORY_DIGEST}"
            ),
            "blob_version_id": None,
            "size_bytes": 512,
            "content_type": "application/json",
            "access_scope": "user",
            "sanitization_status": "sanitized",
        },
        # Executor/control-plane values below must never cross into history.
        "plan_handle": {
            "blob_name": (
                f"tenants/{TENANT_ID}/workflows/{WORKFLOW_ID}/"
                f"plans/{JOB_ID}/{PLAN_DIGEST}.tfplan"
            ),
            "etag": '"executor-plan-etag"',
            "sha256": PLAN_DIGEST,
        },
        "state_key": (
            f"tenants/{TENANT_ID}/workspaces/{WORKFLOW_ID}/terraform.tfstate"
        ),
        "result_uri": (
            f"https://artifact.blob.core.windows.net/{OPAQUE_CONTAINER}/"
            f"objects/{ARTIFACT_ID}/v1/{BUNDLE_DIGEST}?sig=private"
        ),
    }


class WorkflowEventCompatibilityTests(unittest.TestCase):
    def test_plan_event_matches_function_golden_contract(self) -> None:
        envelope = plan_envelope()
        event = build_workflow_event(envelope, sanitized_plan_result())

        validated = WorkflowEventV1.model_validate(event)
        self.assertEqual(validated.schema_version, "workflow-event.v1")
        self.assertEqual(validated.event_type, "terraform.plan.completed")
        self.assertEqual(validated.status, "completed")
        self.assertEqual(validated.actor_type, "vmss")
        self.assertEqual(validated.tenant_id, TENANT_ID)
        self.assertEqual(validated.project_id, PROJECT_ID)
        self.assertEqual(validated.run_id, WORKFLOW_ID)
        self.assertEqual(len(validated.artifacts), 1)

    def test_event_id_is_stable_and_scoped_to_job(self) -> None:
        envelope = plan_envelope()
        first = build_workflow_event(envelope, sanitized_plan_result())
        second = build_workflow_event(envelope, sanitized_plan_result())
        self.assertEqual(first["event_id"], second["event_id"])

        changed_payload = base_plan_payload()
        changed_payload["job_id"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        changed = ExecutionEnvelope.from_mapping(
            payload_with_digest(changed_payload)
        )
        changed_event = build_workflow_event(changed, sanitized_plan_result())
        self.assertNotEqual(first["event_id"], changed_event["event_id"])

    def test_executor_locators_and_etags_are_not_emitted(self) -> None:
        event_json = json.dumps(
            build_workflow_event(plan_envelope(), sanitized_plan_result()),
            sort_keys=True,
        )
        for forbidden in (
            "plan_handle",
            "executor-plan-etag",
            "terraform.tfstate",
            "plans/",
            "result_uri",
            "?sig=",
            '"etag"',
        ):
            self.assertNotIn(forbidden, event_json)

    def test_apply_and_failure_outcomes_use_history_taxonomy(self) -> None:
        apply = apply_envelope()
        applied_event = build_workflow_event(
            apply,
            {
                "status": "applied",
                "completed_at": "2026-07-29T10:00:00+00:00",
                "applied_plan_sha256": PLAN_DIGEST,
                "approval_id": apply.approval.approval_id,
            },
        )
        WorkflowEventV1.model_validate(applied_event)
        self.assertEqual(applied_event["event_type"], "terraform.apply.completed")
        self.assertEqual(applied_event["stage"], "terraform-apply")

        failed_event = build_workflow_event(
            plan_envelope(),
            {
                "status": "failed",
                "failure_category": "tool:Terraform validation",
            },
        )
        WorkflowEventV1.model_validate(failed_event)
        self.assertEqual(failed_event["event_type"], "terraform.plan.failed")
        self.assertEqual(failed_event["status"], "failed")
        self.assertEqual(failed_event["actor_type"], "vmss")
        self.assertEqual(
            failed_event["safe_message"],
            "Terraform plan failed.",
        )


if __name__ == "__main__":
    unittest.main()
