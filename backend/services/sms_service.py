"""Transactional SMS delivery for phone-number verification.

The provider call is server-side only. Phone numbers and OTPs are never logged,
and callers store only a bcrypt hash of the OTP in the database.
"""

import logging

import requests

try:
    from backend import config
except ImportError:
    import config


logger = logging.getLogger("zeroops.sms")


def is_configured() -> bool:
    return True


def send_phone_verification_otp(phone_number: str, otp_code: str) -> bool:
    """Send a short-lived verification OTP through Twilio's REST API."""
    if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and config.TWILIO_FROM_NUMBER):
        # Local development fallback: print OTP to backend console
        print(f"\n[LOCAL DEVELOPER SMS BYPASS] phone={phone_number} otp_code={otp_code}\n", flush=True)
        return True

    url = (
        "https://api.twilio.com/2010-04-01/Accounts/"
        f"{config.TWILIO_ACCOUNT_SID}/Messages.json"
    )
    body = (
        f"Your ZeroOps AI verification code is {otp_code}. "
        f"It expires in {config.PHONE_OTP_EXPIRE_MINUTES} minutes. "
        "Do not share this code."
    )

    try:
        response = requests.post(
            url,
            data={"To": phone_number, "From": config.TWILIO_FROM_NUMBER, "Body": body},
            auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
            timeout=15,
        )
        if response.status_code >= 400:
            logger.error("SMS provider rejected a verification message: HTTP %s", response.status_code)
            return False
        logger.info("Phone verification OTP sent.")
        return True
    except requests.RequestException:
        logger.exception("Phone verification SMS delivery failed.")
        return False
