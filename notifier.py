
"""US visa slot alerts via ntfy and WhatsApp (Twilio)."""

import asyncio
import logging
import os

import aiohttp

log = logging.getLogger(__name__)

# ntfy configuration
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_BASE_URL = os.environ.get(
    "NTFY_BASE_URL", "https://ntfy.sh"
).rstrip("/")

# Twilio WhatsApp configuration
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_WHATSAPP_FROM = os.environ.get(
    "TWILIO_WHATSAPP_FROM", ""
).strip()
TWILIO_WHATSAPP_TO = os.environ.get(
    "TWILIO_WHATSAPP_TO", ""
).strip()


async def send_ntfy(message: str) -> bool:
    if not NTFY_TOPIC:
        log.error("NTFY_TOPIC is not configured.")
        return False

    if "/" in NTFY_TOPIC or " " in NTFY_TOPIC:
        log.error("NTFY_TOPIC must be a single topic name.")
        return False

    try:
        timeout = aiohttp.ClientTimeout(total=20)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{NTFY_BASE_URL}/{NTFY_TOPIC}",
                data=message.encode("utf-8"),
                headers={
                    "Title": "US H-1B Visa Slot Alert",
                    "Priority": "high",
                },
            ) as response:
                if response.status in (200, 201):
                    log.info("ntfy notification sent.")
                    return True

                log.error("ntfy failed: HTTP %s", response.status)
                return False

    except Exception:
        log.exception("ntfy notification failed.")
        return False


async def send_whatsapp(message: str) -> bool:
    required = (
        TWILIO_ACCOUNT_SID,
        TWILIO_AUTH_TOKEN,
        TWILIO_WHATSAPP_FROM,
        TWILIO_WHATSAPP_TO,
    )

    if not all(required):
        log.error("Twilio WhatsApp settings are incomplete.")
        return False

    url = (
        "https://api.twilio.com/2010-04-01/Accounts/"
        f"{TWILIO_ACCOUNT_SID}/Messages.json"
    )

    # Twilio WhatsApp addresses normally use "whatsapp:+..."
    data = {
        "From": TWILIO_WHATSAPP_FROM,
        "To": TWILIO_WHATSAPP_TO,
        "Body": message[:1500],
    }

    try:
        timeout = aiohttp.ClientTimeout(total=20)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url,
                data=data,
                auth=aiohttp.BasicAuth(
                    TWILIO_ACCOUNT_SID,
                    TWILIO_AUTH_TOKEN,
                ),
            ) as response:
                if response.status in (200, 201):
                    log.info("WhatsApp message accepted by Twilio.")
                    return True

                log.error(
                    "WhatsApp failed: HTTP %s; %s",
                    response.status,
                    await response.text(),
                )
                return False

    except Exception:
        log.exception("WhatsApp notification failed.")
        return False


async def send_notification(message: str):
    """Send both notifications without one blocking the other."""
    results = await asyncio.gather(
        send_ntfy(message),
        send_whatsapp(message),
        return_exceptions=True,
    )

    for channel, result in zip(("ntfy", "WhatsApp"), results):
        if isinstance(result, Exception):
            log.error("%s raised an error: %s", channel, result)
