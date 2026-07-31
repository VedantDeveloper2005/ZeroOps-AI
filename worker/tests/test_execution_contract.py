from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from worker.contracts import (
    ContractError,
    ExecutionEnvelope,
    payload_with_digest,
)
from worker.execution_gate import (
    ExecutionGateError,
    safe_extract_zip,
    summarize_plan_json,
    validate_saved_plan_gate,
)


TENANT_ID = "11111111-1111-4111-8111-111111111111"
USER_ID = "22222222-2222-4222-8222-222222222222"
WORKFLOW_ID = "33333333-3333-4333-8333-333333333333"
JOB_ID = "44444444-4444-4444-8444-444444444444"
PROJECT_ID = "77777777-7777-4777-8777-777777777777"
ARTIFACT_ID = "88888888-8888-4888-8888-888888888888"
OPAQUE_CONTAINER = "t-0123456789abcdef0123456789abcdef01234567"
PLAN_DIGEST = "a" * 64
BUNDLE_DIGEST = "b" * 64


def base_plan_payload() -> dict:
    return {
        "schema_version": "1.0",
        "operation": "plan",
        "job_id": JOB_ID,
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_ID,
        "user_id": USER_ID,
        "workflow_id": WORKFLOW_ID,
        "revision": 1,
        "bundle": {
            "uri": (
                f"https://artifact.blob.core.windows.net/{OPAQUE_CONTAINER}/"
                f"objects/{ARTIFACT_ID}/v1/{BUNDLE_DIGEST}"
            ),
            "etag": '"bundle-etag"',
            "sha256": BUNDLE_DIGEST,
            "size_bytes": 1024,
        },
        "state_key": (
            f"tenants/{TENANT_ID}/workspaces/{WORKFLOW_ID}/terraform.tfstate"
        ),
        "target_subscription_id": "55555555-5555-4555-8555-555555555555",
        "target_tenant_id": "66666666-6666-4666-8666-666666666666",
        "terraform_version": "1.15.8",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }


class ExecutionContractTests(unittest.TestCase):
    def test_valid_plan_is_accepted(self) -> None:
        envelope = ExecutionEnvelope.from_mapping(
            payload_with_digest(base_plan_payload())
        )
        self.assertEqual(envelope.operation, "plan")
        self.assertEqual(envelope.tenant_id, TENANT_ID)
        self.assertEqual(envelope.project_id, PROJECT_ID)

    def test_digest_detects_mutation(self) -> None:
        payload = payload_with_digest(base_plan_payload())
        payload["revision"] = 2
        with self.assertRaisesRegex(ContractError, "job_digest"):
            ExecutionEnvelope.from_mapping(payload)

    def test_raw_payload_field_is_rejected(self) -> None:
        payload = base_plan_payload()
        payload["raw_tfplan"] = "not permitted"
        with self.assertRaisesRegex(ContractError, "unsupported"):
            ExecutionEnvelope.from_mapping(payload_with_digest(payload))

    def test_nonopaque_bundle_container_is_rejected(self) -> None:
        payload = base_plan_payload()
        payload["bundle"]["uri"] = (
            "https://artifact.blob.core.windows.net/tenant-artifacts/"
            f"objects/{ARTIFACT_ID}/v1/{BUNDLE_DIGEST}"
        )
        with self.assertRaisesRegex(ContractError, "opaque tenant container"):
            ExecutionEnvelope.from_mapping(payload_with_digest(payload))

    def test_bundle_terminal_digest_must_match(self) -> None:
        payload = base_plan_payload()
        payload["bundle"]["uri"] = (
            f"https://artifact.blob.core.windows.net/{OPAQUE_CONTAINER}/"
            f"objects/{ARTIFACT_ID}/v1/{'c' * 64}"
        )
        with self.assertRaisesRegex(ContractError, "terminal digest"):
            ExecutionEnvelope.from_mapping(payload_with_digest(payload))

    def test_bundle_uri_rejects_sas_query(self) -> None:
        payload = base_plan_payload()
        payload["bundle"]["uri"] += "?sig=must-not-be-accepted"
        with self.assertRaisesRegex(ContractError, "query-free"):
            ExecutionEnvelope.from_mapping(payload_with_digest(payload))

    def test_bundle_version_must_be_positive(self) -> None:
        payload = base_plan_payload()
        payload["bundle"]["uri"] = payload["bundle"]["uri"].replace("/v1/", "/v0/")
        with self.assertRaisesRegex(ContractError, "canonical user-artifact path"):
            ExecutionEnvelope.from_mapping(payload_with_digest(payload))

    def test_project_id_must_be_a_canonical_uuid(self) -> None:
        payload = base_plan_payload()
        payload["project_id"] = "not-a-project-uuid"
        with self.assertRaisesRegex(ContractError, "project_id"):
            ExecutionEnvelope.from_mapping(payload_with_digest(payload))

    def test_apply_requires_exact_approval_and_plan(self) -> None:
        payload = base_plan_payload()
        payload["operation"] = "apply"
        payload["saved_plan"] = {
            "blob_name": (
                f"tenants/{TENANT_ID}/workflows/{WORKFLOW_ID}/"
                f"plans/{uuid.uuid4()}/{PLAN_DIGEST}.tfplan"
            ),
            "etag": '"plan-etag"',
            "sha256": PLAN_DIGEST,
            "plan_job_digest": "c" * 64,
            "bundle_sha256": BUNDLE_DIGEST,
        }
        payload["approval"] = {
            "approval_id": str(uuid.uuid4()),
            "decision": "approved",
            "approved_by": USER_ID,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "plan_job_digest": "c" * 64,
            "plan_sha256": PLAN_DIGEST,
            "plan_etag": '"plan-etag"',
            "bundle_sha256": BUNDLE_DIGEST,
        }
        envelope = ExecutionEnvelope.from_mapping(payload_with_digest(payload))
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "saved.tfplan"
            plan.write_bytes(b"different bytes")
            with self.assertRaisesRegex(ExecutionGateError, "digest mismatch"):
                validate_saved_plan_gate(envelope, plan)

    def test_zip_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "bundle.zip"
            destination = Path(directory) / "output"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../outside.tf", "terraform {}")
            with self.assertRaisesRegex(ExecutionGateError, "unsafe"):
                safe_extract_zip(archive, destination)

    def test_plan_json_is_reduced_to_safe_counts(self) -> None:
        document = {
            "format_version": "1.2",
            "terraform_version": "1.15.8",
            "resource_changes": [
                {
                    "type": "azurerm_storage_account",
                    "change": {
                        "actions": ["create"],
                        "after": {"secret_value": "must-not-escape"},
                    },
                }
            ],
        }
        summary = summarize_plan_json(json.dumps(document).encode())
        self.assertEqual(summary["actions"]["create"], 1)
        self.assertNotIn("secret_value", json.dumps(summary))
        self.assertNotIn("must-not-escape", json.dumps(summary))


if __name__ == "__main__":
    unittest.main()
