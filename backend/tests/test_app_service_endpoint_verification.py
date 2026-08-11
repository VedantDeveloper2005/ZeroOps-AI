import socket
from types import SimpleNamespace

import pytest

try:
    from backend.services import app_service
except ImportError:
    from services import app_service


PUBLIC_IPV4 = "93.184.216.34"


def _address_record(address: str):
    if ":" in address:
        return (
            socket.AF_INET6,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            (address, 443, 0, 0),
        )
    return (
        socket.AF_INET,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        "",
        (address, 443),
    )


def test_endpoint_verification_normalizes_expected_app_name_and_requires_2xx(monkeypatch):
    requests = []
    monkeypatch.setattr(
        app_service,
        "_resolve_public_addresses",
        lambda host: (PUBLIC_IPV4,),
    )
    monkeypatch.setattr(
        app_service,
        "_request_pinned_https",
        lambda host, target, address, *, timeout: requests.append(
            (host, target, address, timeout)
        ) or 204,
    )

    app_service.verify_public_endpoint(
        "https://example-app.azurewebsites.net/health?ready=1",
        expected_app_name="Example App",
        attempts=1,
        delay_seconds=0,
    )

    assert requests == [
        (
            "example-app.azurewebsites.net",
            "/health?ready=1",
            PUBLIC_IPV4,
            15,
        )
    ]


@pytest.mark.parametrize(
    "live_url",
    [
        "http://example-app.azurewebsites.net",
        "https://different-app.azurewebsites.net",
        "https://example-app.azurewebsites.net:443",
        "https://user:password@example-app.azurewebsites.net",
        "https://example-app.azurewebsites.net.",
        "https://example-app.azurewebsites.net#fragment",
        " https://example-app.azurewebsites.net",
    ],
)
def test_endpoint_verification_rejects_unexpected_authority_before_dns(live_url, monkeypatch):
    def unexpected_resolution(_host):
        raise AssertionError("An invalid endpoint must not reach DNS.")

    monkeypatch.setattr(app_service, "_resolve_public_addresses", unexpected_resolution)

    with pytest.raises(app_service.AzureDeploymentError, match="safely verified"):
        app_service.verify_public_endpoint(
            live_url,
            expected_app_name="example-app",
            attempts=1,
            delay_seconds=0,
        )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.20.30.40",
        "169.254.169.254",
        "192.0.2.10",
        "224.0.0.1",
        "0.0.0.0",
        "100.64.0.1",
        "::1",
        "fe80::1",
    ],
)
def test_dns_validation_rejects_every_non_global_address(address, monkeypatch):
    monkeypatch.setattr(
        app_service.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [_address_record(address)],
    )

    with pytest.raises(app_service.AzureDeploymentError) as failure:
        app_service._resolve_public_addresses("example-app.azurewebsites.net")

    assert address not in str(failure.value)
    assert str(failure.value) == "The application endpoint could not be safely verified."


def test_dns_validation_rejects_mixed_public_and_private_answers(monkeypatch):
    monkeypatch.setattr(
        app_service.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            _address_record(PUBLIC_IPV4),
            _address_record("127.0.0.1"),
        ],
    )
    request_called = False

    def unexpected_request(*args, **kwargs):
        nonlocal request_called
        request_called = True

    monkeypatch.setattr(app_service, "_request_pinned_https", unexpected_request)

    with pytest.raises(app_service.AzureDeploymentError, match="did not become healthy"):
        app_service.verify_public_endpoint(
            "https://example-app.azurewebsites.net",
            expected_app_name="example-app",
            attempts=1,
            delay_seconds=0,
        )

    assert request_called is False


def test_dns_is_resolved_again_for_each_retry(monkeypatch):
    resolutions = []
    statuses = iter((503, 200))
    sleeps = []

    def resolve(host):
        resolutions.append(host)
        return (PUBLIC_IPV4,)

    monkeypatch.setattr(app_service, "_resolve_public_addresses", resolve)
    monkeypatch.setattr(
        app_service,
        "_request_pinned_https",
        lambda *args, **kwargs: next(statuses),
    )
    monkeypatch.setattr(app_service.time, "sleep", lambda delay: sleeps.append(delay))

    app_service.verify_public_endpoint(
        "https://example-app.azurewebsites.net",
        expected_app_name="example-app",
        attempts=2,
        delay_seconds=0.25,
    )

    assert resolutions == [
        "example-app.azurewebsites.net",
        "example-app.azurewebsites.net",
    ]
    assert sleeps == [0.25]


@pytest.mark.parametrize("status", [300, 301, 302, 307, 308, 400, 404, 500])
def test_redirects_and_all_other_non_2xx_statuses_fail_closed(status, monkeypatch):
    monkeypatch.setattr(
        app_service,
        "_resolve_public_addresses",
        lambda host: (PUBLIC_IPV4,),
    )
    calls = []
    monkeypatch.setattr(
        app_service,
        "_request_pinned_https",
        lambda *args, **kwargs: calls.append((args, kwargs)) or status,
    )

    with pytest.raises(app_service.AzureDeploymentError, match="did not become healthy"):
        app_service.verify_public_endpoint(
            "https://example-app.azurewebsites.net",
            expected_app_name="example-app",
            attempts=1,
            delay_seconds=0,
        )

    assert len(calls) == 1


def test_pinned_request_returns_redirect_without_following_it(monkeypatch):
    events = []

    class FakeConnection:
        def __init__(self, host, address, *, timeout):
            events.append(("connect", host, address, timeout))

        def request(self, method, target, *, headers):
            events.append(("request", method, target, headers["Host"]))

        def getresponse(self):
            events.append(("response",))
            return SimpleNamespace(status=302)

        def close(self):
            events.append(("close",))

    monkeypatch.setattr(app_service, "_PinnedHTTPSConnection", FakeConnection)

    status = app_service._request_pinned_https(
        "example-app.azurewebsites.net",
        "/",
        PUBLIC_IPV4,
        timeout=15,
    )

    assert status == 302
    assert [event[0] for event in events] == ["connect", "request", "response", "close"]
    assert events[1][1] == "GET"
