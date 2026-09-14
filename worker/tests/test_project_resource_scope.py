import json

import pytest

from worker.contracts import ExecutionEnvelope, canonical_digest, payload_with_digest
from worker.execution_gate import ExecutionGateError, validate_plan_guardrails
from worker.tests.test_execution_contract import base_plan_payload


def fixture():
    payload = base_plan_payload()
    registry = (f"/subscriptions/{payload['target_subscription_id']}/resourceGroups/hosting"
                "/providers/Microsoft.ContainerRegistry/registries/sharedregistry")
    values = {"container_registry_id": registry}
    payload["input_variables"]["sha256"] = canonical_digest(values)
    payload["input_variables"]["definitions"] = [{"name": "container_registry_id", "type": "string"}]
    payload["guardrails"]["allowed_resource_types"] = ["azurerm_linux_web_app", "azurerm_role_assignment"]
    envelope = ExecutionEnvelope.from_mapping(payload_with_digest(payload))
    grant = "azurerm_role_assignment.application_acr_pull"
    document = {
        "resource_changes": [
            {"address": "azurerm_linux_web_app.application", "type": "azurerm_linux_web_app",
             "change": {"actions": ["create"], "after": {"resource_group_name": "rg-zeroops-target"}}},
            {"address": grant, "type": "azurerm_role_assignment",
             "change": {"actions": ["create"], "after": {"scope": registry, "role_definition_name": "AcrPull"}}},
        ],
        "configuration": {"root_module": {"resources": [{"address": grant, "expressions": {
            "principal_id": {"references": ["azurerm_linux_web_app.application.identity[0].principal_id",
                                            "azurerm_linux_web_app.application"]}
        }}]}},
    }
    return envelope, values, document


def test_shared_registry_pull_bound_to_verified_inputs_and_project_identity():
    envelope, values, document = fixture()
    validate_plan_guardrails(json.dumps(document).encode(), envelope, approved_input_values=values)


@pytest.mark.parametrize("mutation", ["owner", "other_registry", "other_identity", "other_group", "unbound_values"])
def test_shared_registry_exception_cannot_expand_access(mutation):
    envelope, values, document = fixture()
    grant = document["resource_changes"][1]["change"]["after"]
    if mutation == "owner":
        grant["role_definition_name"] = "Owner"
    elif mutation == "other_registry":
        grant["scope"] += "other"
    elif mutation == "other_identity":
        document["configuration"]["root_module"]["resources"][0]["expressions"]["principal_id"] = {
            "constant_value": "11111111-1111-4111-8111-111111111111"
        }
    elif mutation == "other_group":
        document["resource_changes"][0]["change"]["after"]["resource_group_name"] = "another-project"
    else:
        values["container_registry_id"] += "other"
    with pytest.raises(ExecutionGateError):
        validate_plan_guardrails(json.dumps(document).encode(), envelope, approved_input_values=values)
