"""
Email Service
=============
Sends transactional emails (verification links, OTP codes) via SMTP.
Uses Python's built-in smtplib — no extra dependencies required.
"""

import logging
import secrets
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

try:
    from backend import config
except ImportError:
    import config

logger = logging.getLogger("zeroops.email")

# Simple in-memory rate limiter: { email: last_sent_timestamp }
_send_timestamps: dict[str, float] = {}
_RATE_LIMIT_SECONDS = 60  # minimum seconds between emails to the same address


def _is_rate_limited(email: str) -> bool:
    last_sent = _send_timestamps.get(email, 0)
    return (time.time() - last_sent) < _RATE_LIMIT_SECONDS


def _record_send(email: str) -> None:
    _send_timestamps[email] = time.time()
    # Prevent memory leak: trim oldest entries when store grows large
    if len(_send_timestamps) > 5000:
        cutoff = time.time() - _RATE_LIMIT_SECONDS * 2
        for key in list(_send_timestamps):
            if _send_timestamps[key] < cutoff:
                del _send_timestamps[key]


def is_configured() -> bool:
    """Return whether transactional email can be delivered in this environment."""
    return bool(config.SMTP_HOST and config.SMTP_USERNAME and config.SMTP_PASSWORD)


# Compatibility alias for the earlier private helper. New auth code uses the
# public name so delivery requirements are explicit and testable.
def _smtp_configured() -> bool:
    return is_configured()


def _send_email(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send an email via SMTP. Returns True on success, False on failure."""
    if not is_configured():
        logger.warning("SMTP is not configured; transactional email was not sent.")
        return False

    if _is_rate_limited(to_email):
        logger.info("Rate-limited email to %s — skipping.", to_email)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.SMTP_FROM_EMAIL or config.SMTP_USERNAME
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if config.SMTP_USE_TLS:
            server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=15)

        server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        server.sendmail(msg["From"], [to_email], msg.as_string())
        server.quit()

        _record_send(to_email)
        logger.info("Transactional email sent: %s", subject)
        return True
    except Exception:
        logger.exception("Failed to send transactional email.")
        return False


def generate_otp(length: int = 6) -> str:
    """Generate a cryptographically random numeric OTP code."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


# ──────────────────────────────────────────────
# EMAIL TEMPLATES
# ──────────────────────────────────────────────

_BRAND_COLOR = "#6366f1"
_BACKGROUND = "#0f172a"
_CARD_BG = "#1e293b"
_TEXT_COLOR = "#e2e8f0"
_MUTED_COLOR = "#94a3b8"


def _email_wrapper(title: str, content: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background-color:{_BACKGROUND};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
<tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background:{_CARD_BG};border-radius:16px;overflow:hidden;">
<tr><td style="padding:32px 32px 0;">
  <div style="font-size:20px;font-weight:700;color:white;margin-bottom:4px;">ZeroOps AI</div>
  <div style="font-size:12px;color:{_MUTED_COLOR};margin-bottom:24px;">Autonomous Cloud Deployment</div>
  <div style="font-size:16px;font-weight:600;color:white;margin-bottom:16px;">{title}</div>
</td></tr>
<tr><td style="padding:0 32px 32px;">
  {content}
</td></tr>
<tr><td style="padding:16px 32px;border-top:1px solid #334155;">
  <div style="font-size:11px;color:{_MUTED_COLOR};text-align:center;">
    This email was sent by ZeroOps AI. If you didn't request this, you can safely ignore it.
  </div>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def send_verification_email(to_email: str, verification_url: str) -> bool:
    """Send an email verification link to a new user."""
    html_content = f"""
    <p style="color:{_TEXT_COLOR};font-size:14px;line-height:1.6;margin:0 0 20px;">
      Welcome to ZeroOps AI! Please verify your email address to get started.
    </p>
    <div style="text-align:center;margin:24px 0;">
      <a href="{verification_url}"
         style="display:inline-block;background:{_BRAND_COLOR};color:white;padding:12px 32px;
                border-radius:10px;text-decoration:none;font-weight:600;font-size:14px;">
        Verify Email Address
      </a>
    </div>
    <p style="color:{_MUTED_COLOR};font-size:12px;line-height:1.5;margin:16px 0 0;">
      Or copy this link into your browser:<br>
      <a href="{verification_url}" style="color:{_BRAND_COLOR};word-break:break-all;">{verification_url}</a>
    </p>
    <p style="color:{_MUTED_COLOR};font-size:11px;margin-top:16px;">
      This link expires in {config.EMAIL_VERIFICATION_EXPIRE_HOURS} hours.
    </p>
    """

    text_body = (
        f"Welcome to ZeroOps AI!\n\n"
        f"Verify your email by visiting: {verification_url}\n\n"
        f"This link expires in {config.EMAIL_VERIFICATION_EXPIRE_HOURS} hours."
    )

    return _send_email(
        to_email,
        "Verify your email — ZeroOps AI",
        _email_wrapper("Verify your email address", html_content),
        text_body,
    )


def send_otp_email(to_email: str, otp_code: str) -> bool:
    """Send a one-time login verification code."""
    # Format code with spaces for readability: "123 456"
    formatted = f"{otp_code[:3]} {otp_code[3:]}" if len(otp_code) == 6 else otp_code

    html_content = f"""
    <p style="color:{_TEXT_COLOR};font-size:14px;line-height:1.6;margin:0 0 20px;">
      Use this code to complete your sign-in. It expires in {config.EMAIL_OTP_EXPIRE_MINUTES} minutes.
    </p>
    <div style="text-align:center;margin:24px 0;">
      <div style="display:inline-block;background:{_BACKGROUND};border:2px solid {_BRAND_COLOR};
                  border-radius:12px;padding:16px 40px;letter-spacing:8px;
                  font-size:32px;font-weight:700;color:white;font-family:monospace;">
        {formatted}
      </div>
    </div>
    <p style="color:{_MUTED_COLOR};font-size:12px;line-height:1.5;margin:16px 0 0;">
      If you did not try to sign in, someone may be using your credentials.
      Change your password immediately.
    </p>
    """

    text_body = (
        f"Your ZeroOps AI verification code is: {otp_code}\n\n"
        f"This code expires in {config.EMAIL_OTP_EXPIRE_MINUTES} minutes.\n\n"
        f"If you did not request this, change your password immediately."
    )

    return _send_email(
        to_email,
        f"Your verification code: {otp_code} — ZeroOps AI",
        _email_wrapper("Your sign-in verification code", html_content),
        text_body,
    )
