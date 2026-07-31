from __future__ import annotations

import importlib.util
import io
import json
import hashlib
import sys
import tempfile
import unittest
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict


ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "functions" / "common"
REPOSITORY_HANDLER = ROOT / "functions" / "repository_analysis" / "handler.py"
TERRAFORM_HANDLER = ROOT / "functions" / "terraform_generation" / "handler.py"
HISTORY_HANDLER = ROOT / "functions" / "history_projector" / "handler.py"
sys.path.insert(0, str(COMMON))

from zeroops_functions import history_store
from zeroops_functions.ai_contracts import TerraformBundle
from zeroops_functions.contracts import (
    ArtifactReferenceV1,
    EventArtifactV1,
    RepositoryAnalysisJobV1,
    TerraformGenerationJobV1,
    WorkflowEventV1,
)
from zeroops_functions.model_client import StructuredModelClient
from zeroops_functions.model_client import ModelProvenance, ModelUnavailableError
from zeroops_functions.security import (
    UnsafeArtifactError,
    safe_relative_path,
    validate_terraform_source,
)
from worker.contracts import ExecutionEnvelope
from worker.execution_gate import require_provider_lockfile, safe_extract_zip


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


repository_handler = load_module("repository_handler_for_tests", REPOSITORY_HANDLER)
terraform_handler = load_module("terraform_handler_for_tests", TERRAFORM_HANDLER)
history_handler = load_module("history_handler_for_tests", HISTORY_HANDLER)


def artifact(
    *,
    artifact_id: str = "artifact-1",
    sha256: str = "a" * 64,
    size_bytes: int = 2,
) -> ArtifactReferenceV1:
    return ArtifactReferenceV1(
        artifact_id=artifact_id,
        account_url="https://stzopsartp2f871a.blob.core.windows.net",
        container="t-opaque-tenant",
        blob_name=f"projects/project-1/{artifact_id}.json",
        sha256=sha256,
        size_bytes=size_bytes,
        media_type="application/json",
        classification="tenant-source",
    )


class ContractTests(unittest.TestCase):
    def test_artifact_rejects_non_blob_origin(self):
        with self.assertRaises(ValueError):
            ArtifactReferenceV1(
                artifact_id="artifact-1",
                account_url="https://attacker.example",
                container="t-opaque-tenant",
                blob_name="source.json",
                sha256="a" * 64,
                size_bytes=2,
                media_type="application/json",
                classification="tenant-source",
            )

    def test_job_rejects_unknown_queue_fields(self):
        value = {
            "schema_version": "repository-analysis-job.v1",
            "job_id": "job-1",
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "correlation_id": "correlation-1",
            "source_artifact": artifact().model_dump(mode="json"),
            "scanner_facts_artifact": artifact(
                artifact_id="scanner-1"
            ).model_dump(mode="json"),
            "output_artifact_id": "20000000-0000-0000-0000-000000000001",
            "output_container": "t-0123456789abcdef0123456789abcdef01234567",
            "source_commit": "abcdef0123456789",
            "scanner_version": "scanner.v1",
            "raw_repository_source": "must not be placed on Service Bus",
        }
        with self.assertRaises(ValueError):
            RepositoryAnalysisJobV1.model_validate(value)

    def test_terraform_path_and_provisioner_are_rejected(self):
        for value in ("../main.tf", "/tmp/main.tf", "module\\..\\main.tf"):
            with self.assertRaises(UnsafeArtifactError):
                safe_relative_path(value)
        with self.assertRaises(UnsafeArtifactError):
            validate_terraform_source(
                'resource "azurerm_resource_group" "x" {\n'
                '  provisioner "local-exec" { command = "whoami" }\n'
                "}"
            )


class ModelClientTests(unittest.TestCase):
    def test_provenance_hash_binds_prompt_schema_and_input(self):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": json.dumps(
                                    {
                                        "schema_version": "test-output.v1",
                                        "summary": "Evidence-bound result",
                                    }
                                )
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 3},
                },
            )

        class OutputA(BaseModel):
            model_config = ConfigDict(extra="forbid")
            schema_version: str
            summary: str

        class OutputB(BaseModel):
            model_config = ConfigDict(extra="forbid")
            schema_version: str
            summary: str
            note: str | None = None

        client = StructuredModelClient(
            provider="github-models",
            endpoint="https://models.github.ai/inference",
            model="openai/gpt-4o",
            api_key="test-only-token",
            workload="repository-analysis",
            prompt_version="repository-analysis.v1",
            maximum_input_chars=10_000,
            maximum_output_tokens=100,
            transport=httpx.MockTransport(handler),
        )
        common = {
            "input_value": {"evidence": ["fact-1"]},
            "schema_version": "test-output.v1",
            "correlation_id": "correlation-1",
        }
        _, first = client.generate(
            system_instructions="Prompt one.",
            output_model=OutputA,
            **common,
        )
        _, changed_prompt = client.generate(
            system_instructions="Prompt two.",
            output_model=OutputA,
            **common,
        )
        _, changed_schema = client.generate(
            system_instructions="Prompt one.",
            output_model=OutputB,
            **common,
        )

        self.assertEqual(
            len(
                {
                    first.request_hash,
                    changed_prompt.request_hash,
                    changed_schema.request_hash,
                }
            ),
            3,
        )
        self.assertEqual(first.correlation_id, "correlation-1")
        request_body = json.loads(requests[0].content)
        system_message = request_body["messages"][0]["content"]
        self.assertIn("Return exactly one JSON object", system_message)
        self.assertIn('"summary"', system_message)

    def test_client_repairs_once_and_records_aggregate_usage(self):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 1:
                content = '{"schema_version":"test-output.v1"}'
            else:
                content = json.dumps(
                    {
                        "schema_version": "test-output.v1",
                        "summary": "Evidence-bound result",
                    }
                )
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                },
            )

        class Output(BaseModel):
            model_config = ConfigDict(extra="forbid")
            schema_version: str
            summary: str

        client = StructuredModelClient(
            provider="github-models",
            endpoint="https://models.github.ai/inference",
            model="openai/gpt-4o",
            api_key="test-only-token",
            workload="repository-analysis",
            prompt_version="repository-analysis.v1",
            maximum_input_chars=10_000,
            maximum_output_tokens=100,
            transport=httpx.MockTransport(handler),
        )
        result, provenance = client.generate(
            system_instructions="Return strict JSON.",
            input_value={"evidence": []},
            output_model=Output,
            schema_version="test-output.v1",
        )
        self.assertEqual(result.summary, "Evidence-bound result")
        self.assertEqual(len(requests), 2)
        self.assertTrue(provenance.repair_attempted)
        self.assertEqual(provenance.input_tokens, 20)
        self.assertEqual(provenance.output_tokens, 8)

    def test_client_rejects_legacy_or_cross_route_endpoint(self):
        with self.assertRaises(ValueError):
            StructuredModelClient(
                provider="github-models",
                endpoint="https://models.inference.ai.azure.com",
                model="openai/gpt-4o",
                api_key="test-only-token",
                workload="repository-analysis",
                prompt_version="v1",
                maximum_input_chars=1000,
                maximum_output_tokens=100,
            )


@dataclass
class Uploaded:
    version_id: str = "version-1"
    etag: str = "etag-1"
    sha256: str = "b" * 64
    size_bytes: int = 120


class FakeStore:
    account_url = "https://stzopsartp2f871a.blob.core.windows.net"

    def __init__(self):
        self.uploads = []

    def download_verified_json(self, *_args, **_kwargs):
        return {
            "schema_version": "repository-analysis-request.v1",
            "tenant_id": "10000000-0000-0000-0000-000000000001",
            "project_id": "10000000-0000-0000-0000-000000000002",
            "repository": "owner/repository",
            "branch": "main",
            "commit_sha": "a" * 40,
            "source_facts": [
                {
                    "id": "file:requirements.txt",
                    "category": "dependency",
                    "value": "fastapi",
                    "source_path": "requirements.txt",
                    "source_line": 1,
                }
            ],
            "safe_files": [],
            "repository_tree": "requirements.txt",
            "constraints": [],
        }

    def upload_immutable_json(self, **_kwargs):
        return Uploaded()

    def upload_immutable_bytes(
        self,
        *,
        container,
        blob_name,
        body,
        media_type,
        metadata,
    ):
        uploaded = Uploaded(
            etag='"test-etag"',
            sha256=hashlib.sha256(body).hexdigest(),
            size_bytes=len(body),
        )
        self.uploads.append(
            {
                "container": container,
                "blob_name": blob_name,
                "body": body,
                "media_type": media_type,
                "metadata": metadata,
                "uploaded": uploaded,
            }
        )
        return uploaded


class FakePublisher:
    def __init__(self):
        self.events = []

    def send_event(self, queue_name, event):
        self.events.append((queue_name, event))

    def send_json(self, queue_name, value, **properties):
        if not hasattr(self, "messages"):
            self.messages = []
        self.messages.append((queue_name, value, properties))


class RepositoryFallbackTests(unittest.TestCase):
    def test_missing_repository_model_degrades_without_cross_fallback(self):
        publisher = FakePublisher()
        store = FakeStore()
        dependencies = repository_handler.RepositoryHandlerDependencies(
            store=store,
            publisher=publisher,
            model_client=None,
            workflow_events_queue="workflow-events",
            instructions="unused",
        )
        job = RepositoryAnalysisJobV1(
            job_id="job-1",
            tenant_id="10000000-0000-0000-0000-000000000001",
            project_id="10000000-0000-0000-0000-000000000002",
            run_id="10000000-0000-0000-0000-000000000003",
            correlation_id="correlation-1",
            source_artifact=artifact(),
            scanner_facts_artifact=artifact(artifact_id="scanner-1"),
            output_artifact_id="20000000-0000-0000-0000-000000000001",
            output_container="t-0123456789abcdef0123456789abcdef01234567",
            source_commit="a" * 40,
            scanner_version="scanner.v1",
        )
        result = repository_handler.handle_repository_analysis(
            job.model_dump_json().encode(),
            dependencies,
        )
        self.assertEqual(result["analysis_status"], "deterministic_only")
        self.assertIsNone(result["provenance"]["provider"])
        self.assertEqual([event.status for _, event in publisher.events], ["started", "degraded"])
        upload = store.uploads[0]
        self.assertEqual(
            upload["blob_name"],
            (
                "objects/20000000-0000-0000-0000-000000000001/v1/"
                f"{upload['uploaded'].sha256}"
            ),
        )
        self.assertNotIn(
            "output_blob_name",
            publisher.events[-1][1].safe_metadata,
        )


class FakeTerraformStore(FakeStore):
    def __init__(self):
        self.uploads = []

    def download_verified_json(self, *_args, **_kwargs):
        return {
            "schema_version": "terraform-generation-request.v1",
            "tenant_id": "10000000-0000-0000-0000-000000000001",
            "project_id": "10000000-0000-0000-0000-000000000002",
            "plan_id": "40000000-0000-0000-0000-000000000001",
            "plan_revision": 1,
            "plan_sha256": "d" * 64,
            "plan_status": "approved",
            "target_cloud": "azure",
            "region": "centralindia",
            "components": [
                {
                    "id": "component-rg",
                    "service": "Azure Resource Group",
                    "tier": None,
                    "properties": {"public_network_access": False},
                }
            ],
            "allowed_resource_types": ["azurerm_resource_group"],
            "module_catalog_version": "zeroops-modules.v1",
            "policy_version": "zeroops-policy.v1",
            "constraints": [],
            "pricing": None,
        }

    def upload_immutable_bytes(
        self,
        *,
        container,
        blob_name,
        body,
        media_type,
        metadata,
    ):
        digest = hashlib.sha256(body).hexdigest()
        self.assert_canonical_upload(container, blob_name, digest)
        uploaded = Uploaded(
            version_id="version-1",
            etag='"test-etag"',
            sha256=digest,
            size_bytes=len(body),
        )
        self.uploads.append(
            {
                "container": container,
                "blob_name": blob_name,
                "body": body,
                "media_type": media_type,
                "metadata": metadata,
                "uploaded": uploaded,
            }
        )
        return uploaded

    @staticmethod
    def assert_canonical_upload(container, blob_name, digest):
        if container != "t-0123456789abcdef0123456789abcdef01234567":
            raise AssertionError("Terraform artifacts must use the opaque tenant container")
        parts = blob_name.split("/")
        if (
            len(parts) != 4
            or parts[0] != "objects"
            or parts[2] != "v1"
            or parts[3] != digest
        ):
            raise AssertionError("Terraform artifact path is not canonical")
        uuid.UUID(parts[1])


class FakeTerraformModel:
    def generate(self, **_kwargs):
        output = TerraformBundle(
            schema_version="terraform-bundle.v1",
            status="generated",
            plan_revision=1,
            plan_sha256="d" * 64,
            files=[
                {
                    "path": "versions.tf",
                    "content": (
                        'terraform {\n'
                        '  required_version = ">= 1.7, < 2.0"\n'
                        "  required_providers {\n"
                        "    azurerm = {\n"
                        '      source = "hashicorp/azurerm"\n'
                        '      version = "~> 4.0"\n'
                        "    }\n"
                        "  }\n"
                        '  backend "azurerm" {}\n'
                        "}\n"
                    ),
                },
                {
                    "path": "providers.tf",
                    "content": 'provider "azurerm" {\n  features {}\n}\n',
                },
                {
                    "path": "variables.tf",
                    "content": (
                        'variable "resource_group_name" {\n'
                        "  type = string\n"
                        '  description = "Approved resource group name."\n'
                        "}\n"
                        'variable "location" {\n'
                        "  type = string\n"
                        '  description = "Approved Azure region."\n'
                        "}\n"
                    ),
                },
                {
                    "path": "main.tf",
                    "content": (
                        'resource "azurerm_resource_group" "approved" {\n'
                        '  name = var.resource_group_name\n'
                        '  location = var.location\n'
                        "}\n"
                    ),
                },
                {
                    "path": "outputs.tf",
                    "content": (
                        'output "resource_group_name" {\n'
                        '  description = "Created resource group name."\n'
                        "  value = azurerm_resource_group.approved.name\n"
                        "}\n"
                    ),
                },
            ],
            variables=[
                {
                    "name": "resource_group_name",
                    "type": "string",
                    "description": "Approved resource group name.",
                    "sensitive": False,
                    "default": None,
                },
                {
                    "name": "location",
                    "type": "string",
                    "description": "Approved Azure region.",
                    "sensitive": False,
                    "default": None,
                },
            ],
            resources=[
                {
                    "address": "azurerm_resource_group.approved",
                    "resource_type": "azurerm_resource_group",
                    "component_id": "component-rg",
                    "rationale": "Creates the approved resource boundary.",
                    "cost_driver": False,
                }
            ],
            outputs=[
                {
                    "name": "resource_group_name",
                    "description": "Created resource group name.",
                    "sensitive": False,
                }
            ],
            assumptions=[],
            warnings=[],
            cost_optimizations=[
                {
                    "id": "keep-approved-scope",
                    "component_id": "component-rg",
                    "mechanism": "Generate only the approved resource.",
                    "expected_impact": "low",
                    "tradeoff": "New services need another approved revision.",
                    "requires_verified_pricing": True,
                }
            ],
            validation_requirements=[
                "Run terraform fmt -check.",
                "Run terraform init -backend=false.",
                "Run terraform validate.",
                "Run TFLint.",
                "Run Checkov.",
                "Run terraform plan and compare it with the approved allowlist.",
                "Verify pricing and budget policy.",
                "Require human approval before apply.",
            ],
            blocked_reasons=[],
        )
        semantic_validator = _kwargs.get("semantic_validator")
        if semantic_validator is not None:
            semantic_validator(output)
        return output, ModelProvenance(
            provider="github-models",
            model="openai/gpt-4.1",
            workload="terraform-generation",
            prompt_version="terraform-generation.v1",
            schema_version="terraform-bundle.v1",
            execution_mode="model",
            correlation_id="correlation-terraform-1",
            input_tokens=100,
            output_tokens=200,
            latency_ms=50,
            request_hash="c" * 64,
            repair_attempted=False,
            cached=False,
        )


class FailingTerraformModel:
    def generate(self, **_kwargs):
        raise ModelUnavailableError("unavailable")


class BlockedTerraformModel:
    def generate(self, **_kwargs):
        output = TerraformBundle(
            schema_version="terraform-bundle.v1",
            status="blocked",
            plan_revision=1,
            plan_sha256="d" * 64,
            files=[],
            variables=[],
            resources=[],
            outputs=[],
            assumptions=[],
            warnings=[],
            cost_optimizations=[],
            validation_requirements=[],
            blocked_reasons=["The approved plan lacks a safe deterministic mapping."],
        )
        semantic_validator = _kwargs.get("semantic_validator")
        if semantic_validator is not None:
            semantic_validator(output)
        return output, ModelProvenance(
            provider="github-models",
            model="openai/gpt-4.1",
            workload="terraform-generation",
            prompt_version="terraform-generation.v1",
            schema_version="terraform-bundle.v1",
            execution_mode="model",
            correlation_id="correlation-terraform-1",
            input_tokens=20,
            output_tokens=20,
            latency_ms=10,
            request_hash="e" * 64,
            repair_attempted=False,
            cached=False,
        )


class TerraformGenerationTests(unittest.TestCase):
    def terraform_job(self):
        plan_artifact = artifact(
            artifact_id="30000000-0000-0000-0000-000000000001"
        ).model_copy(
            update={
                "classification": "tenant-analysis",
                "sha256": "e" * 64,
            }
        )
        return {
            "schema_version": "terraform-generation-job.v1",
            "job_id": "50000000-0000-4000-8000-000000000001",
            "tenant_id": "10000000-0000-0000-0000-000000000001",
            "project_id": "10000000-0000-0000-0000-000000000002",
            "run_id": "10000000-0000-0000-0000-000000000003",
            "correlation_id": "correlation-terraform-1",
            "enqueued_at": "2026-07-29T00:00:00Z",
            "user_id": "20000000-0000-4000-8000-000000000001",
            "approved_plan_artifact": plan_artifact.model_dump(mode="json"),
            "output_artifact_id": "30000000-0000-0000-0000-000000000002",
            "output_container": "t-0123456789abcdef0123456789abcdef01234567",
            "approved_plan_id": "40000000-0000-0000-0000-000000000001",
            "approved_plan_revision": 1,
            "approved_plan_digest": "d" * 64,
            "target_environment": "test",
            "target_subscription_id": "60000000-0000-4000-8000-000000000001",
            "target_tenant_id": "70000000-0000-4000-8000-000000000001",
            "terraform_version": "1.15.8",
        }

    def test_valid_bundle_enqueues_exact_vmss_envelope_and_deterministic_zip(self):
        publisher = FakePublisher()
        store = FakeTerraformStore()
        dependencies = terraform_handler.TerraformHandlerDependencies(
            store=store,
            publisher=publisher,
            model_client=FakeTerraformModel(),
            workflow_events_queue="workflow-events",
            terraform_plan_queue="terraform-plan",
            instructions="strict output",
        )
        result = terraform_handler.handle_terraform_generation(
            json.dumps(self.terraform_job()).encode(),
            dependencies,
        )
        self.assertEqual(result["validation_status"], "not_run")
        self.assertEqual(result["plan_status"], "not_run")
        self.assertEqual(result["apply_status"], "not_run")
        self.assertEqual(len(publisher.messages), 1)
        self.assertEqual(publisher.messages[0][0], "terraform-plan")
        envelope_value = publisher.messages[0][1]
        envelope = ExecutionEnvelope.from_mapping(envelope_value)
        self.assertEqual(envelope.operation, "plan")
        self.assertEqual(envelope.workflow_id, self.terraform_job()["run_id"])
        self.assertEqual(envelope.user_id, self.terraform_job()["user_id"])
        self.assertEqual(envelope.terraform_version, "1.15.8")
        self.assertEqual(
            publisher.messages[0][2]["session_id"],
            self.terraform_job()["run_id"],
        )
        self.assertEqual(
            publisher.messages[0][2]["message_id"],
            envelope.job_digest,
        )
        self.assertNotIn("content", json.dumps(envelope_value))

        zip_upload = next(
            item for item in store.uploads if item["media_type"] == "application/zip"
        )
        self.assertEqual(
            zip_upload["blob_name"],
            (
                "objects/30000000-0000-0000-0000-000000000002/v1/"
                f"{zip_upload['uploaded'].sha256}"
            ),
        )
        with zipfile.ZipFile(io.BytesIO(zip_upload["body"])) as archive:
            names = archive.namelist()
            self.assertEqual(
                names,
                [
                    ".terraform.lock.hcl",
                    "main.tf",
                    "outputs.tf",
                    "providers.tf",
                    "variables.tf",
                    "versions.tf",
                ],
            )
            lock = archive.read(".terraform.lock.hcl").decode()
            self.assertIn("registry.terraform.io/hashicorp/azurerm", lock)
            self.assertIn('version     = "4.81.0"', lock)
            self.assertTrue(
                all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())
            )
        with tempfile.TemporaryDirectory(prefix="zeroops-golden-bundle-") as directory:
            archive_path = Path(directory) / "bundle.zip"
            extracted = Path(directory) / "source"
            archive_path.write_bytes(zip_upload["body"])
            safe_extract_zip(archive_path, extracted)
            require_provider_lockfile(extracted)
            self.assertTrue((extracted / "main.tf").is_file())

        generated, _ = FakeTerraformModel().generate()
        first = terraform_handler.build_deterministic_terraform_zip(generated)
        second = terraform_handler.build_deterministic_terraform_zip(generated)
        self.assertEqual(first, second)
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())

        audit_upload = next(
            item for item in store.uploads if item["media_type"] == "application/json"
        )
        audit = json.loads(audit_upload["body"])
        self.assertEqual(audit["executor_bundle"]["sha256"], envelope.bundle.sha256)
        self.assertEqual(audit["validation_status"], "not_run")

    def test_terraform_job_rejects_noncanonical_executor_identity_and_storage(self):
        invalid = self.terraform_job()
        invalid["job_id"] = "job-terraform-1"
        with self.assertRaises(ValueError):
            TerraformGenerationJobV1.model_validate(invalid)

        invalid = self.terraform_job()
        invalid["output_container"] = "tenant-readable-name"
        with self.assertRaises(ValueError):
            TerraformGenerationJobV1.model_validate(invalid)

    def test_blocked_bundle_is_persisted_but_never_enqueues_plan(self):
        publisher = FakePublisher()
        store = FakeTerraformStore()
        dependencies = terraform_handler.TerraformHandlerDependencies(
            store=store,
            publisher=publisher,
            model_client=BlockedTerraformModel(),
            workflow_events_queue="workflow-events",
            terraform_plan_queue="terraform-plan",
            instructions="strict output",
        )
        result = terraform_handler.handle_terraform_generation(
            json.dumps(self.terraform_job()).encode(),
            dependencies,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(hasattr(publisher, "messages"))
        self.assertEqual(
            [item["media_type"] for item in store.uploads],
            ["application/json"],
        )
        self.assertEqual(
            [event.event_type for _, event in publisher.events],
            ["terraform.generation.started", "terraform.generation.blocked"],
        )

    def test_provider_failure_is_fail_closed_and_enqueues_no_plan(self):
        publisher = FakePublisher()
        dependencies = terraform_handler.TerraformHandlerDependencies(
            store=FakeTerraformStore(),
            publisher=publisher,
            model_client=FailingTerraformModel(),
            workflow_events_queue="workflow-events",
            terraform_plan_queue="terraform-plan",
            instructions="strict output",
        )
        with self.assertRaises(ModelUnavailableError):
            terraform_handler.handle_terraform_generation(
                json.dumps(self.terraform_job()).encode(),
                dependencies,
            )
        self.assertFalse(hasattr(publisher, "messages"))
        self.assertEqual([event.status for _, event in publisher.events], ["started", "failed"])


class FakeProjector:
    def __init__(self):
        self.events = []

    async def project(self, event):
        self.events.append(event)
        return len(self.events) == 1


class HistoryProjectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_handler_validates_and_passes_external_event_id(self):
        projector = FakeProjector()
        event = {
            "schema_version": "workflow-event.v1",
            "event_id": "event-1",
            "event_type": "repository.analysis.completed",
            "tenant_id": "10000000-0000-0000-0000-000000000001",
            "project_id": "10000000-0000-0000-0000-000000000002",
            "run_id": "10000000-0000-0000-0000-000000000003",
            "correlation_id": "correlation-1",
            "stage": "repository-analysis",
            "attempt": 1,
            "status": "completed",
            "actor_type": "function",
            "actor_id": "repository-analysis",
            "artifacts": [],
            "safe_metadata": {"model": "openai/gpt-4o"},
        }
        result = await history_handler.handle_history_event(
            json.dumps(event).encode(),
            history_handler.HistoryHandlerDependencies(projector=projector),
        )
        self.assertTrue(result)
        self.assertEqual(projector.events[0].event_id, "event-1")


class HistoryStoreContractTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def event(
        *,
        status="completed",
        event_type="repository.analysis.completed",
        artifacts=None,
        safe_metadata=None,
    ):
        return WorkflowEventV1(
            event_id="event-1",
            event_type=event_type,
            tenant_id="10000000-0000-0000-0000-000000000001",
            project_id="10000000-0000-0000-0000-000000000002",
            run_id="10000000-0000-0000-0000-000000000003",
            correlation_id="correlation-1",
            stage="repository-analysis",
            attempt=1,
            status=status,
            actor_type="function",
            actor_id="repository-analysis",
            artifacts=artifacts or [],
            safe_metadata=safe_metadata or {},
        )

    def test_user_event_data_never_contains_blob_locator(self):
        projected_artifact = EventArtifactV1(
            artifact_id="20000000-0000-0000-0000-000000000001",
            kind="repository-analysis",
            sha256="a" * 64,
            storage_container="t-opaque-tenant",
            storage_path="projects/p/runs/r/analysis.json",
            blob_version_id="private-version-id",
            size_bytes=128,
            content_type="application/json",
            access_scope="executor",
            sanitization_status="restricted",
        )
        event = self.event(
            artifacts=[projected_artifact],
            safe_metadata={
                "api_key": "must-not-persist",
                "finding_count": 2,
                "output_blob_name": "projects/p/runs/r/private.json",
                "output_version_id": "private-version-id",
            },
        )

        safe = history_store._safe_event_data(event)
        serialized = json.dumps(safe)
        self.assertNotIn("storage_container", serialized)
        self.assertNotIn("storage_path", serialized)
        self.assertNotIn("output_blob_name", serialized)
        self.assertNotIn("private-version-id", serialized)
        self.assertNotIn("must-not-persist", serialized)
        self.assertEqual(safe["metadata"]["api_key"], "[REDACTED]")

    def test_artifact_projection_metadata_is_all_or_none(self):
        logical_only = EventArtifactV1(
            artifact_id="20000000-0000-0000-0000-000000000001",
            kind="logical-result",
        )
        self.assertFalse(history_store._artifact_projection_complete(logical_only))

        partial = logical_only.model_copy(update={"sha256": "a" * 64})
        with self.assertRaisesRegex(ValueError, "all-or-none"):
            history_store._artifact_projection_complete(partial)

    def test_operation_terminal_mapping_is_run_type_aware(self):
        completed = self.event()
        self.assertEqual(
            history_store._operation_status("repository_analysis", completed),
            ("completed", True),
        )
        degraded = self.event(status="degraded")
        self.assertEqual(
            history_store._operation_status("repository_analysis", degraded),
            ("degraded", True),
        )
        self.assertEqual(
            history_store._operation_status("deployment", completed),
            ("repository_analysis_completed", False),
        )

    def test_terminal_attempt_cannot_be_regressed_by_late_stage_event(self):
        self.assertTrue(
            history_store._attempt_is_already_terminal(
                "completed",
                prior_attempt=2,
                incoming_attempt=2,
            )
        )
        self.assertFalse(
            history_store._attempt_is_already_terminal(
                "completed",
                prior_attempt=2,
                incoming_attempt=3,
            )
        )
        naive = datetime(2026, 7, 29, 12, 0, 0)
        normalized = history_store._utc_timestamp(naive)
        self.assertEqual(normalized.tzinfo, timezone.utc)

    def test_duplicate_event_id_must_match_run_and_fingerprint(self):
        event = self.event()
        run_id = uuid.UUID(event.run_id)
        project_id = uuid.UUID(event.project_id)
        fingerprint = history_store._event_fingerprint(event)
        retry = event.model_copy(
            update={"occurred_at": event.occurred_at + timedelta(seconds=5)}
        )
        self.assertEqual(history_store._event_fingerprint(retry), fingerprint)
        duplicate = {
            "operation_run_id": run_id,
            "project_id": project_id,
            "action": event.event_type,
            "actor_type": event.actor_type,
            "actor_id": event.actor_id,
            "details": None,
            "event_data": history_store._safe_event_data(event),
            "event_fingerprint": fingerprint,
        }
        history_store.PostgresHistoryProjector._assert_duplicate_matches(
            duplicate,
            event=event,
            run_id=run_id,
            project_id=project_id,
            safe_message=None,
            event_data=history_store._safe_event_data(event),
            fingerprint=fingerprint,
        )

        duplicate["operation_run_id"] = uuid.uuid4()
        with self.assertRaisesRegex(ValueError, "different event"):
            history_store.PostgresHistoryProjector._assert_duplicate_matches(
                duplicate,
                event=event,
                run_id=run_id,
                project_id=project_id,
                safe_message=None,
                event_data=history_store._safe_event_data(event),
                fingerprint=fingerprint,
            )

    async def test_artifact_replay_compares_access_and_sanitization_metadata(self):
        event = self.event()
        projected_artifact = EventArtifactV1(
            artifact_id="20000000-0000-0000-0000-000000000001",
            kind="repository-analysis",
            sha256="a" * 64,
            storage_container="t-opaque-tenant",
            storage_path="projects/p/runs/r/analysis.json",
            size_bytes=128,
            content_type="application/json",
            access_scope="user",
            sanitization_status="sanitized",
        )
        artifact_id = uuid.UUID(projected_artifact.artifact_id)
        tenant_id = uuid.UUID(event.tenant_id)
        run_id = uuid.UUID(event.run_id)
        project_id = uuid.UUID(event.project_id)
        user_id = uuid.uuid4()

        class ReplayConnection:
            async def execute(self, *_args):
                return None

            async def fetchrow(self, *_args):
                return {
                    "artifact_key": artifact_id,
                    "tenant_id": tenant_id,
                    "operation_run_id": run_id,
                    "project_id": project_id,
                    "created_by_user_id": user_id,
                    "kind": projected_artifact.kind,
                    "display_name": "analysis.json",
                    "content_type": projected_artifact.content_type,
                    "storage_container": projected_artifact.storage_container,
                    "storage_path": projected_artifact.storage_path,
                    "sha256_digest": projected_artifact.sha256,
                    "size_bytes": projected_artifact.size_bytes,
                    "version": 1,
                    "access_scope": "executor",
                    "sanitization_status": "restricted",
                }

        with self.assertRaisesRegex(ValueError, "immutable metadata"):
            await history_store.PostgresHistoryProjector._project_artifact(
                ReplayConnection(),
                event=event,
                artifact=projected_artifact,
                tenant_id=tenant_id,
                run_id=run_id,
                project_id=project_id,
                user_id=user_id,
            )

    async def test_operation_projection_includes_cost_and_stale_event_guard(self):
        event = self.event(
            safe_metadata={
                "provider": "github-models",
                "model": "openai/gpt-4o",
                "input_tokens": 12,
                "output_tokens": 7,
                "model_cost_microusd": 345,
            }
        )

        class CaptureConnection:
            def __init__(self):
                self.call = None

            async def execute(self, statement, *arguments):
                self.call = (statement, arguments)

        connection = CaptureConnection()
        await history_store.PostgresHistoryProjector._update_operation(
            connection,
            event,
            uuid.UUID(event.tenant_id),
            uuid.UUID(event.run_id),
            operation_type="repository_analysis",
            activity_event_id=uuid.uuid4(),
            sequence=2,
            reopen_terminal=False,
        )
        statement, arguments = connection.call
        self.assertIn("model_cost_microusd", statement)
        self.assertIn("NOT EXISTS", statement)
        self.assertEqual(arguments[2], "completed")
        self.assertEqual(arguments[10], 345)


if __name__ == "__main__":
    unittest.main()
