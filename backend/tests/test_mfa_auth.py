from datetime import datetime, timedelta

from jose import jwt

try:
    from backend import auth, config, models
except ImportError:
    import auth
    import config
    import models


def test_totp_accepts_current_code_and_rejects_invalid_code(monkeypatch):
    secret = auth.generate_totp_secret()
    counter = 2_000_000
    monkeypatch.setattr(auth.time, "time", lambda: counter * 30 + 1)

    code = auth._hotp(secret, counter)

    assert auth.verify_totp_code(secret, code) == counter
    assert auth.verify_totp_code(secret, "000000") is None


def test_recovery_codes_are_hashed_and_single_use():
    codes, hashes = auth.generate_recovery_codes()
    user = models.User(email="mfa-test@example.com", mfa_recovery_code_hashes=hashes)

    assert len(codes) == 10
    assert codes[0] not in hashes[0]
    assert auth.consume_recovery_code(user, codes[0]) is True
    assert len(user.mfa_recovery_code_hashes) == 9
    assert auth.consume_recovery_code(user, codes[0]) is False


def test_mfa_challenge_token_is_short_lived_and_scoped_to_pre_authentication():
    token = auth.create_mfa_challenge_token("2b7365a1-b190-4cc3-9ecd-dfe7b3d8f5c6", "single-use-challenge")
    payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])

    assert payload["type"] == "mfa_challenge"
    assert payload["challenge_id"] == "single-use-challenge"
    assert payload["exp"] - payload["iat"] == config.MFA_CHALLENGE_EXPIRE_MINUTES * 60


def test_refresh_tokens_are_persisted_as_hashes_only():
    _, refresh_token = auth.get_session_tokens("2b7365a1-b190-4cc3-9ecd-dfe7b3d8f5c6")
    refresh_hash = auth.hash_refresh_token(refresh_token)

    assert refresh_hash != refresh_token
    assert len(refresh_hash) == 64


def test_mfa_setup_requires_a_recent_primary_sign_in():
    user = models.User(email="mfa-test@example.com", last_primary_auth_at=datetime.utcnow() - timedelta(minutes=11))
    assert auth.is_recent_primary_authentication(user) is False

    user.last_primary_auth_at = datetime.utcnow() - timedelta(minutes=9)
    assert auth.is_recent_primary_authentication(user) is True


def test_email_verification_token_generation_and_validation():
    token = auth.create_verification_token()
    token_hash = auth.hash_verification_token(token)

    assert token != token_hash
    assert len(token_hash) == 64
    assert auth.verify_verification_token(token, token_hash) is True
    assert auth.verify_verification_token("invalid_token", token_hash) is False


def test_email_otp_generation_and_validation():
    otp = auth.generate_email_otp()
    assert len(otp) == 6
    assert otp.isdigit()

    otp_hash = auth.hash_otp(otp)
    assert auth.verify_otp(otp, otp_hash) is True
    assert auth.verify_otp("123456" if otp != "123456" else "654321", otp_hash) is False
