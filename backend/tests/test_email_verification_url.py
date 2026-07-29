import asyncio
from urllib.parse import parse_qs, urlparse

try:
    from backend import main, models
except ImportError:
    import main
    import models


def test_verification_email_link_includes_encoded_email_and_opaque_token(monkeypatch):
    delivered = {}
    raw_token = "opaque_token-123"
    user = models.User(email="owner+production@example.com")

    monkeypatch.setattr(main.config, "FRONTEND_URL", "https://app.zeroops.example")
    monkeypatch.setattr(main.auth, "create_verification_token", lambda: raw_token)

    def capture_email(to_email, verification_url):
        delivered["to_email"] = to_email
        delivered["verification_url"] = verification_url
        return True

    monkeypatch.setattr(main.email_service, "send_verification_email", capture_email)

    asyncio.run(main.prepare_and_send_verification_email(user))

    assert delivered["to_email"] == user.email
    assert (
        delivered["verification_url"]
        == "https://app.zeroops.example/verify-email"
        "?token=opaque_token-123&email=owner%2Bproduction%40example.com"
    )
    parsed_query = parse_qs(urlparse(delivered["verification_url"]).query)
    assert parsed_query == {
        "token": [raw_token],
        "email": [user.email],
    }
    assert user.email_verification_token == main.auth.hash_verification_token(raw_token)
    assert raw_token not in user.email_verification_token
    assert user.email_verification_expires_at is not None
