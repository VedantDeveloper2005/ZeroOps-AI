from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

from worker import azure_adapters
from worker.execution_gate import ExecutionGateError


class _Response(io.BytesIO):
    def __init__(self, payload: bytes = b"", *, url: str, status: int = 200):
        super().__init__(payload)
        self._url = url
        self.status = status
        self.was_closed = False

    def geturl(self) -> str:
        return self._url

    def close(self) -> None:
        self.was_closed = True
        super().close()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://management.azure.com/subscriptions/id",
        "https://management.azure.com.evil.example/subscriptions/id",
        "https://management.azure.com@evil.example/subscriptions/id",
        "https://127.0.0.1/subscriptions/id",
    ],
)
def test_arm_url_validator_rejects_file_and_untrusted_origins(url: str) -> None:
    with pytest.raises(ExecutionGateError):
        azure_adapters._validated_arm_resource_url(url)


def test_imds_validator_accepts_only_the_compute_metadata_endpoint() -> None:
    assert (
        azure_adapters._validated_imds_compute_url(azure_adapters._IMDS_COMPUTE_URL)
        == azure_adapters._IMDS_COMPUTE_URL
    )
    for url in (
        "file:///etc/passwd",
        "http://127.0.0.1/metadata/instance/compute?api-version=2021-02-01",
        "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01",
    ):
        with pytest.raises(ExecutionGateError):
            azure_adapters._validated_imds_compute_url(url)


def test_approved_azure_request_rejects_a_moved_response(monkeypatch) -> None:
    response = _Response(b"", url="file:///etc/passwd")

    class FakeOpener:
        def open(self, request, *, timeout):
            assert request.full_url == azure_adapters._IMDS_COMPUTE_URL
            assert timeout == 5
            return response

    monkeypatch.setattr(
        azure_adapters.urllib.request,
        "build_opener",
        lambda *_: FakeOpener(),
    )
    request = azure_adapters.urllib.request.Request(azure_adapters._IMDS_COMPUTE_URL)

    with pytest.raises(ExecutionGateError, match="redirects"):
        azure_adapters._open_approved_azure_request(
            request,
            timeout=5,
            validator=azure_adapters._validated_imds_compute_url,
        )

    assert response.was_closed


def test_vmss_metadata_and_arm_update_use_validated_endpoints(monkeypatch) -> None:
    metadata = {
        "subscriptionId": "11111111-1111-4111-8111-111111111111",
        "resourceGroupName": "production/group",
        "name": "worker?blue",
    }
    opened: list[tuple[str, int]] = []

    def fake_open(request, *, timeout, validator):
        validator(request.full_url)
        opened.append((request.full_url, timeout))
        if request.full_url == azure_adapters._IMDS_COMPUTE_URL:
            payload = json.dumps(metadata).encode("utf-8")
            return _Response(payload, url=request.full_url)
        return _Response(url=request.full_url, status=202)

    monkeypatch.setattr(azure_adapters, "_open_approved_azure_request", fake_open)
    credential = SimpleNamespace(
        get_token=lambda *_: SimpleNamespace(token="managed-identity-token")
    )
    protection = azure_adapters.VmssScaleInProtection(credential)

    assert protection._compute_metadata() == metadata
    protection.protect()

    assert opened == [
        (azure_adapters._IMDS_COMPUTE_URL, 5),
        (
            "https://management.azure.com/subscriptions/"
            "11111111-1111-4111-8111-111111111111/resourceGroups/"
            "production%2Fgroup/providers/Microsoft.Compute/virtualMachines/"
            "worker%3Fblue?api-version=2024-11-01",
            30,
        ),
    ]
