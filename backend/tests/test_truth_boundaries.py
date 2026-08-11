import asyncio
import logging
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

try:
    from backend import main, schemas
    from backend.services import email_service, sms_service
except ImportError:
    import main
    import schemas
    from services import email_service, sms_service


class ScalarResult:
    def __init__(self, first=None):
        self._first = first

    def scalars(self):
        return self

    def first(self):
        return self._first


class RecordingSession:
    def __init__(self, first=None, commit_error=None):
        self.first = first
        self.commit_error = commit_error
        self.execute_count = 0
        self.commits = 0
        self.rollbacks = 0
        self.added = []

    async def execute(self, _):
        self.execute_count += 1
        return ScalarResult(self.first)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1
        if self.commit_error:
            raise self.commit_error

    async def rollback(self):
        self.rollbacks += 1


def assert_http_error(coroutine, expected_status):
    with pytest.raises(HTTPException) as error:
        asyncio.run(coroutine)
    assert error.value.status_code == expected_status
    return error.value


def test_production_startup_refuses_unavailable_key_vault_for_legacy_secret_migration(
    monkeypatch,
):
    class NoSession:
        def __call__(self):
            raise AssertionError("The database must not be opened without the production secret store.")

    monkeypatch.setattr(main.config, "IS_PRODUCTION", True)
    monkeypatch.setattr(main.vault, "HAS_AZURE_KV", False)
    monkeypatch.setattr(main, "AsyncSessionLocal", NoSession())

    with pytest.raises(RuntimeError, match="Key Vault is unavailable"):
        asyncio.run(main.migrate_legacy_environment_secrets())


def test_stale_ai_investigation_is_finalized_as_unavailable(monkeypatch):
    record = SimpleNamespace(
        status="running",
        model_provider="pending",
        model_name="pending",
        error_code=None,
        redacted_error=None,
        completed_at=None,
    )

    class Result:
        def scalars(self):
            return self

        def all(self):
            return [record]

    class Session:
        commits = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def execute(self, _query):
            return Result()

        async def commit(self):
            self.commits += 1

    session = Session()
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: session)

    count = asyncio.run(main.reconcile_stale_ai_investigations())

    assert count == 1
    assert session.commits == 1
    assert record.status == "unavailable"
    assert record.error_code == "AI_INVESTIGATION_INTERRUPTED"
    assert record.completed_at is not None


def test_unsupported_paid_operation_is_rejected_before_database_or_checkout():
    class NoTouchSession:
        async def execute(self, _):
            raise AssertionError("The database must not be queried for an unavailable operation.")

        def add(self, _):
            raise AssertionError("An unavailable billing operation must not be persisted.")

        async def commit(self):
            raise AssertionError("An unavailable billing operation must not be committed.")

    error = assert_http_error(
        main.create_billing_operation(
            schemas.BillingOperationCreate(operation_type="ai_code_fix"),
            SimpleNamespace(id=uuid.uuid4()),
            NoTouchSession(),
        ),
        501,
    )

    assert "No checkout was created" in error.detail


def test_stripe_checkout_helper_is_fail_closed_for_unimplemented_operations():
    operation = SimpleNamespace(operation_type="ai_redeploy_fix")

    error = assert_http_error(
        _async_call(
            main.create_stripe_checkout_session,
            operation,
            SimpleNamespace(id=uuid.uuid4()),
        ),
        501,
    )

    assert "not available" in error.detail


async def _async_call(function, *args):
    return function(*args)


def test_existing_unsupported_operation_cannot_resume_checkout():
    operation = SimpleNamespace(operation_type="ai_action_apply")
    session = RecordingSession(operation)

    assert_http_error(
        main.create_billing_checkout(
            uuid.uuid4(),
            SimpleNamespace(id=uuid.uuid4()),
            session,
        ),
        501,
    )

    assert session.execute_count == 1
    assert session.commits == 0


@pytest.mark.parametrize("endpoint", [main.get_api_key, main.regenerate_api_key])
def test_api_key_endpoints_do_not_generate_or_persist_credentials(endpoint):
    class NoTouchSession:
        def add(self, _):
            raise AssertionError("An unusable API key must not be persisted.")

        async def commit(self):
            raise AssertionError("An unusable API key must not be committed.")

    error = assert_http_error(
        endpoint(NoTouchSession(), SimpleNamespace(id=uuid.uuid4(), api_key=None)),
        501,
    )

    assert "No credential was generated" in error.detail


@pytest.mark.parametrize(
    "invoke",
    [
        lambda project_id, user, db: main.add_secret(
            schemas.SecretCreateRequest(
                projectId=str(project_id),
                key="DATABASE_URL",
                value="must-not-be-written",
            ),
            db,
            user,
        ),
        lambda project_id, user, db: main.list_secrets(str(project_id), db, user),
        lambda project_id, user, db: main.delete_secret(
            str(project_id),
            "DATABASE_URL",
            db,
            user,
        ),
    ],
)
def test_legacy_secret_endpoints_authorize_then_fail_without_vault_access(
    monkeypatch,
    invoke,
):
    def unexpected_vault_access(*_):
        raise AssertionError("The disabled legacy API must not access Key Vault.")

    monkeypatch.setattr(main.vault, "set_project_secret", unexpected_vault_access)
    monkeypatch.setattr(main.vault, "get_project_secrets", unexpected_vault_access)
    monkeypatch.setattr(main.vault, "delete_project_secret", unexpected_vault_access)
    project_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    session = RecordingSession(SimpleNamespace(id=project_id))

    assert_http_error(invoke(project_id, user, session), 501)

    assert session.execute_count == 1
    assert session.commits == 0
    assert session.added == []


def _stripe_request():
    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/billing/stripe/webhook",
            "headers": [(b"stripe-signature", b"test-signature")],
        },
        receive,
    )


def test_stripe_webhook_rejects_mismatched_completion(monkeypatch):
    operation_id = uuid.uuid4()
    user_id = uuid.uuid4()
    operation = SimpleNamespace(
        id=operation_id,
        user_id=user_id,
        operation_type="future_paid_operation",
        status="pending_payment",
        provider_reference="cs_expected",
        amount_cents=2500,
        currency="usd",
        paid_at=None,
    )
    session = RecordingSession(operation)
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_expected",
                "mode": "payment",
                "payment_status": "paid",
                "amount_total": 1,
                "currency": "usd",
                "metadata": {
                    "operation_id": str(operation_id),
                    "user_id": str(user_id),
                    "operation_type": "future_paid_operation",
                },
            }
        },
    }

    webhook = SimpleNamespace(construct_event=lambda *_: event)
    monkeypatch.setattr(main, "stripe", SimpleNamespace(Webhook=webhook))
    monkeypatch.setattr(main.config, "PAYMENT_PROVIDER", "stripe")
    monkeypatch.setattr(main.config, "STRIPE_WEBHOOK_SECRET", "configured")
    monkeypatch.setattr(
        main,
        "SUPPORTED_PAID_OPERATION_TYPES",
        frozenset({"future_paid_operation"}),
    )

    response = asyncio.run(main.stripe_webhook(_stripe_request(), session))

    assert response == {"received": True}
    assert operation.status == "pending_payment"
    assert operation.paid_at is None
    assert session.commits == 0


def test_azure_put_rejects_vault_failure_before_database_mutation(monkeypatch):
    try:
        from backend.services import azure_connector
    except ImportError:
        from services import azure_connector

    async def no_existing_connection(*_):
        return None

    monkeypatch.setattr(main, "get_active_azure_connection", no_existing_connection)
    monkeypatch.setattr(
        azure_connector,
        "validate_credential",
        lambda **_: {"success": True},
    )
    monkeypatch.setattr(
        azure_connector,
        "store_credential_in_vault",
        lambda *_: False,
    )
    session = RecordingSession()
    request = schemas.AzureConnectionUpsert(
        tenant_id="tenant",
        subscription_id="subscription",
        client_id="client",
        client_secret="secret",
        resource_group="apps",
    )

    error = assert_http_error(
        main.upsert_azure_connection(
            request,
            SimpleNamespace(id=uuid.uuid4()),
            session,
        ),
        503,
    )

    assert "not saved" in error.detail
    assert session.added == []
    assert session.commits == 0


def test_azure_put_restores_previous_secret_after_database_failure(monkeypatch):
    try:
        from backend.services import azure_connector
    except ImportError:
        from services import azure_connector

    existing = SimpleNamespace(
        tenant_id="old-tenant",
        subscription_id="old-subscription",
        client_id="old-client",
        region="eastus",
        resource_group="old-rg",
        acr_login_server=None,
        app_service_plan=None,
        namespace_prefix=None,
        connection_status="connected",
        is_active=True,
        updated_at=None,
    )

    async def existing_connection(*_):
        return existing

    stored_secrets = []
    monkeypatch.setattr(main, "get_active_azure_connection", existing_connection)
    monkeypatch.setattr(
        azure_connector,
        "get_credential_secret",
        lambda *_: "previous-secret",
    )
    monkeypatch.setattr(
        azure_connector,
        "validate_credential",
        lambda **_: {"success": True},
    )
    monkeypatch.setattr(
        azure_connector,
        "store_credential_in_vault",
        lambda _user_id, secret: stored_secrets.append(secret) is None,
    )
    session = RecordingSession(commit_error=RuntimeError("database unavailable"))
    request = schemas.AzureConnectionUpsert(
        tenant_id="new-tenant",
        subscription_id="new-subscription",
        client_id="new-client",
        client_secret="new-secret",
        resource_group="new-rg",
    )

    assert_http_error(
        main.upsert_azure_connection(
            request,
            SimpleNamespace(id=uuid.uuid4()),
            session,
        ),
        503,
    )

    assert stored_secrets == ["new-secret", "previous-secret"]
    assert session.commits == 1
    assert session.rollbacks == 1


@pytest.mark.parametrize(
    "invoke",
    [
        lambda project_id, user, db: main.get_project_health_score(project_id, user, db),
        lambda project_id, user, db: main.get_project_domains(project_id, user, db),
        lambda project_id, user, db: main.create_project_domain(
            project_id,
            schemas.ProjectDomainCreate(name="app.example.com"),
            user,
            db,
        ),
        lambda project_id, user, db: main.verify_project_domain(
            project_id,
            "app.example.com",
            user,
            db,
        ),
        lambda project_id, user, db: main.renew_domain_ssl(
            project_id,
            "app.example.com",
            user,
            db,
        ),
        lambda project_id, user, db: main.delete_project_domain(
            project_id,
            "app.example.com",
            user,
            db,
        ),
        lambda project_id, user, db: main.get_project_members(project_id, user, db),
        lambda project_id, user, db: main.add_project_member(
            project_id,
            schemas.ProjectMemberCreate(email="member@example.com", role="Viewer"),
            user,
            db,
        ),
        lambda project_id, user, db: main.delete_project_member(
            project_id,
            "member@example.com",
            user,
            db,
        ),
    ],
)
def test_unsupported_legacy_capabilities_authorize_then_fail_without_mutation(invoke):
    project_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    session = RecordingSession(SimpleNamespace(id=project_id))

    assert_http_error(invoke(project_id, user, session), 501)

    assert session.execute_count == 1
    assert session.commits == 0
    assert session.added == []


def test_legacy_capability_does_not_disclose_an_unowned_project():
    session = RecordingSession(first=None)

    assert_http_error(
        main.get_project_domains(
            uuid.uuid4(),
            SimpleNamespace(id=uuid.uuid4()),
            session,
        ),
        404,
    )


@pytest.mark.parametrize("origin", [None, "https://attacker.example"])
def test_websocket_rejects_missing_or_unapproved_production_origin(
    monkeypatch,
    origin,
):
    class RejectBeforeAuthenticationWebSocket:
        def __init__(self):
            self.headers = {} if origin is None else {"origin": origin}
            self.closed_with = None

        @property
        def cookies(self):
            raise AssertionError("Origin must be checked before authentication.")

        async def close(self, code):
            self.closed_with = code

    monkeypatch.setattr(main.config, "IS_PRODUCTION", True)
    monkeypatch.setattr(
        main.config,
        "CORS_ORIGINS",
        ["https://app.zeroops.example"],
    )
    websocket = RejectBeforeAuthenticationWebSocket()

    asyncio.run(main.deploy_websocket(websocket, str(uuid.uuid4())))

    assert websocket.closed_with == 1008


def test_websocket_accepts_only_configured_origin(monkeypatch):
    monkeypatch.setattr(main.config, "IS_PRODUCTION", True)
    monkeypatch.setattr(
        main.config,
        "CORS_ORIGINS",
        ["https://app.zeroops.example/"],
    )

    assert main.websocket_origin_is_allowed(
        SimpleNamespace(headers={"origin": "https://app.zeroops.example"})
    )
    assert not main.websocket_origin_is_allowed(
        SimpleNamespace(headers={"origin": "https://attacker.example"})
    )


def test_otp_subjects_do_not_contain_codes(monkeypatch):
    messages = []

    def capture(to_email, subject, html_body, text_body):
        messages.append(
            {
                "to": to_email,
                "subject": subject,
                "html": html_body,
                "text": text_body,
            }
        )
        return True

    monkeypatch.setattr(email_service, "_send_email", capture)

    assert email_service.send_verification_otp_email("user@example.com", "123456")
    assert email_service.send_otp_email("user@example.com", "654321")

    assert "123456" not in messages[0]["subject"]
    assert "654321" not in messages[1]["subject"]
    assert "123456" in messages[0]["text"]
    assert "654321" in messages[1]["text"]


def test_missing_email_and_sms_providers_fail_without_logging_secrets(
    monkeypatch,
    caplog,
    capsys,
):
    for name in ("SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL"):
        monkeypatch.setattr(email_service.config, name, "")
    for name in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"):
        monkeypatch.setattr(sms_service.config, name, "")

    caplog.set_level(logging.WARNING)
    email_secret = "email-secret-123456"
    sms_secret = "sms-secret-654321"
    phone_number = "+15551234567"

    email_result = email_service._send_email(
        "private@example.com",
        f"subject {email_secret}",
        f"<p>{email_secret}</p>",
        email_secret,
    )
    sms_result = sms_service.send_phone_verification_otp(phone_number, sms_secret)

    captured = capsys.readouterr()
    recorded_output = caplog.text + captured.out + captured.err
    assert email_result is False
    assert sms_result is False
    assert email_secret not in recorded_output
    assert sms_secret not in recorded_output
    assert phone_number not in recorded_output


def test_successful_email_log_does_not_include_subject_or_body(monkeypatch, caplog):
    secret = "secret-otp-987654"

    class SMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, *_):
            pass

        def sendmail(self, *_):
            pass

        def quit(self):
            pass

    monkeypatch.setattr(email_service.config, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_service.config, "SMTP_USERNAME", "smtp-user")
    monkeypatch.setattr(email_service.config, "SMTP_PASSWORD", "smtp-password")
    monkeypatch.setattr(email_service.config, "SMTP_FROM_EMAIL", "sender@example.com")
    monkeypatch.setattr(email_service.config, "SMTP_USE_TLS", True)
    monkeypatch.setattr(email_service.smtplib, "SMTP", SMTP)
    monkeypatch.setattr(email_service, "_is_rate_limited", lambda _: False)
    monkeypatch.setattr(email_service, "_record_send", lambda _: None)
    caplog.set_level(logging.INFO)

    result = email_service._send_email(
        "recipient@example.com",
        f"subject {secret}",
        f"<p>{secret}</p>",
        secret,
    )

    assert result is True
    assert secret not in caplog.text
