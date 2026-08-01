import hashlib
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import auth, config, models
from backend.database import get_db
from backend.main import app
from backend.services import email_service, github_oauth, google_oauth


@pytest_asyncio.fixture
async def auth_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(models.Base.metadata.create_all)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session

    async with engine.begin() as connection:
        await connection.run_sync(models.Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_local_signup_login_and_profile_use_persisted_user_data(auth_db, monkeypatch):
    sent_verification_urls: list[str] = []
    monkeypatch.setattr(config, "PHONE_VERIFICATION_REQUIRED", False)
    monkeypatch.setattr(email_service, "is_configured", lambda: True)
    monkeypatch.setattr(
        email_service,
        "send_verification_email",
        lambda _email, url: sent_verification_urls.append(url) is None,
    )

    async def override_db():
        yield auth_db

    app.dependency_overrides[get_db] = override_db
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            signup_response = await client.post(
                "/api/auth/signup",
                json={
                    "email": "Owner.Account@Example.COM",
                    "password": "LongPassword1!",
                    "firstName": "Owner",
                    "lastName": "Account",
                },
            )
            assert signup_response.status_code == 200
            assert signup_response.json() == {
                "email_verification_required": True,
                "email": "owner.account@example.com",
            }

            result = await auth_db.execute(
                select(models.User).where(models.User.email == "owner.account@example.com")
            )
            user = result.scalar_one()
            assert user.password_hash != "LongPassword1!"
            assert auth.verify_password("LongPassword1!", user.password_hash) is True
            assert user.email_verified is False
            assert user.refresh_token is None

            tenant = await auth_db.get(models.Tenant, user.id)
            assert tenant is not None
            membership_result = await auth_db.execute(
                select(models.TenantMembership).where(
                    models.TenantMembership.tenant_id == user.id,
                    models.TenantMembership.user_id == user.id,
                )
            )
            membership = membership_result.scalar_one()
            assert membership.role == "owner"
            settings_result = await auth_db.execute(
                select(models.UserSettings).where(models.UserSettings.user_id == user.id)
            )
            assert settings_result.scalar_one() is not None

            assert len(sent_verification_urls) == 1
            raw_verification_token = parse_qs(
                urlparse(sent_verification_urls[0]).query
            )["token"][0]
            assert user.email_verification_token == hashlib.sha256(
                raw_verification_token.encode("utf-8")
            ).hexdigest()
            assert user.email_verification_token != raw_verification_token

            # A repeated signup is deliberately indistinguishable to the
            # caller and must not let an attacker replace existing credentials.
            original_password_hash = user.password_hash
            duplicate_response = await client.post(
                "/api/auth/signup",
                json={
                    "email": "OWNER.ACCOUNT@example.com",
                    "password": "DifferentPassword2!",
                    "firstName": "Attacker",
                },
            )
            assert duplicate_response.status_code == 200
            await auth_db.refresh(user)
            assert user.password_hash == original_password_hash
            assert user.first_name == "Owner"
            user_count = (
                await auth_db.execute(select(func.count(models.User.id)))
            ).scalar_one()
            assert user_count == 1

            user.email_verified = True
            user.email_verification_token = None
            user.email_verification_expires_at = None
            auth_db.add(user)
            await auth_db.commit()

            own_project = models.Project(
                user_id=user.id,
                name="owned",
                full_name="owner/owned",
            )
            other_user = models.User(
                id=uuid.uuid4(),
                email="other@example.com",
                password_hash=auth.get_password_hash("OtherPassword3!"),
                email_verified=True,
                provider="local",
                plan="starter",
            )
            other_project = models.Project(
                user_id=other_user.id,
                name="other",
                full_name="other/private",
            )
            auth_db.add_all([own_project, other_user, other_project])
            await auth_db.commit()

            login_response = await client.post(
                "/api/auth/login",
                json={
                    "email": "Owner.Account@EXAMPLE.com",
                    "password": "LongPassword1!",
                },
            )
            assert login_response.status_code == 200
            login_body = login_response.json()
            assert login_body["id"] == str(user.id)
            assert login_body["email"] == "owner.account@example.com"
            assert {
                "password_hash",
                "refresh_token",
                "github_access_token_encrypted",
                "email_verification_token",
                "phone_otp_hash",
                "mfa_secret_encrypted",
            }.isdisjoint(login_body)

            set_cookie_headers = login_response.headers.get_list("set-cookie")
            assert any("session_token=" in value and "HttpOnly" in value for value in set_cookie_headers)
            assert any("refresh_token=" in value and "HttpOnly" in value for value in set_cookie_headers)
            raw_refresh_token = client.cookies.get(auth.REFRESH_COOKIE)
            await auth_db.refresh(user)
            assert raw_refresh_token
            assert user.refresh_token == auth.hash_refresh_token(raw_refresh_token)
            assert user.refresh_token != raw_refresh_token

            me_response = await client.get("/api/auth/me")
            assert me_response.status_code == 200
            assert me_response.json()["id"] == str(user.id)

            profile_response = await client.get("/api/user/profile")
            assert profile_response.status_code == 200
            assert profile_response.json()["id"] == str(user.id)
            assert profile_response.json()["total_projects"] == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_github_callback_rejects_profile_without_immutable_provider_id(auth_db, monkeypatch):
    async def token_exchange(_code):
        return "provider-token"

    async def incomplete_profile(_token):
        return {"login": "missing-subject", "name": "Missing Subject"}

    async def override_db():
        yield auth_db

    monkeypatch.setattr(github_oauth, "exchange_code_for_token", token_exchange)
    monkeypatch.setattr(github_oauth, "get_github_user", incomplete_profile)
    app.dependency_overrides[get_db] = override_db
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            client.cookies.set("oauth_state", "expected-state")
            response = await client.get(
                "/api/auth/github/callback",
                params={"code": "provider-code", "state": "expected-state"},
            )
            assert response.status_code == 302
            assert "oauth_error=github_user_fetch_failed" in response.headers["location"]
            count = (await auth_db.execute(select(func.count(models.User.id)))).scalar_one()
            assert count == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_github_oauth_mfa_redirect_includes_email_method(auth_db, monkeypatch):
    user = models.User(
        id=uuid.uuid4(),
        email="github-mfa@example.com",
        provider="local",
        plan="starter",
        email_verified=True,
        mfa_enabled=True,
        mfa_method="email",
    )
    auth_db.add(user)
    await auth_db.commit()

    async def token_exchange(_code):
        return "provider-token"

    async def provider_profile(_token):
        return {"id": 4312, "login": "github-mfa", "name": "GitHub MFA"}

    async def verified_email(_token):
        return user.email

    async def override_db():
        yield auth_db

    monkeypatch.setattr(github_oauth, "exchange_code_for_token", token_exchange)
    monkeypatch.setattr(github_oauth, "get_github_user", provider_profile)
    monkeypatch.setattr(github_oauth, "get_github_user_email", verified_email)
    monkeypatch.setattr(email_service, "send_otp_email", lambda _email, _code: True)
    app.dependency_overrides[get_db] = override_db
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            client.cookies.set("oauth_state", "github-state")
            response = await client.get(
                "/api/auth/github/callback",
                params={"code": "provider-code", "state": "github-state"},
            )

            assert response.status_code == 302
            query = parse_qs(urlparse(response.headers["location"]).query)
            assert query["mfa"] == ["required"]
            assert query["provider"] == ["github"]
            assert query["mfa_method"] == ["email"]
            assert auth.MFA_CHALLENGE_COOKIE in response.cookies
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_google_oauth_mfa_redirect_allowlists_legacy_method_to_totp(auth_db, monkeypatch):
    user = models.User(
        id=uuid.uuid4(),
        email="google-mfa@example.com",
        provider="local",
        plan="starter",
        email_verified=True,
        mfa_enabled=True,
        mfa_method="legacy-invalid-method",
        mfa_secret_encrypted="encrypted-totp-secret",
    )
    auth_db.add(user)
    await auth_db.commit()

    async def token_exchange(_code, _redirect_uri, _code_verifier):
        return "provider-token"

    async def provider_profile(_token):
        return {
            "sub": "google-account-4312",
            "email": user.email,
            "email_verified": True,
            "given_name": "Google",
            "family_name": "MFA",
        }

    async def override_db():
        yield auth_db

    monkeypatch.setattr(google_oauth, "exchange_code_for_token", token_exchange)
    monkeypatch.setattr(google_oauth, "get_google_user", provider_profile)
    app.dependency_overrides[get_db] = override_db
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            client.cookies.set("google_oauth_state", "google-state")
            client.cookies.set("google_oauth_verifier", "google-verifier")
            response = await client.get(
                "/api/auth/google/callback",
                params={"code": "provider-code", "state": "google-state"},
            )

            assert response.status_code == 302
            query = parse_qs(urlparse(response.headers["location"]).query)
            assert query["mfa"] == ["required"]
            assert query["provider"] == ["google"]
            assert query["mfa_method"] == ["totp"]
            assert auth.MFA_CHALLENGE_COOKIE in response.cookies
    finally:
        app.dependency_overrides.clear()


def test_auth_identity_migration_is_append_only_and_enforces_upgraded_schema():
    from backend.migrations.v004_auth_identity_integrity import STATEMENTS, VERSION

    migration_sql = "\n".join(STATEMENTS).lower()
    google_column_statement = next(
        index
        for index, statement in enumerate(STATEMENTS)
        if "add column if not exists google_id" in statement.lower()
    )
    google_index_statement = next(
        index
        for index, statement in enumerate(STATEMENTS)
        if "ix_users_google_id_unique" in statement.lower()
    )
    assert VERSION == "004_auth_identity_integrity"
    assert google_column_statement < google_index_statement
    assert "duplicate normalized email identities" in migration_sql
    assert "lower(btrim(email))" in migration_sql
    assert "ix_users_google_id_unique" in migration_sql
