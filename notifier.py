
"""US visa slot notifications via ntfy and Telegram."""

import asyncio
import logging
import os

import aiohttp

log = logging.getLogger(__name__)

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_BASE_URL = os.environ.get(
    "NTFY_BASE_URL", "https://ntfy.sh"
).rstrip("/")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


async def send_ntfy(session, message):
    if not NTFY_TOPIC:
        log.error("NTFY_TOPIC is not configured.")
        return False

    if "/" in NTFY_TOPIC or " " in NTFY_TOPIC:
        log.error("Invalid NTFY_TOPIC format.")
        return False

    try:
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

            log.error("ntfy failed with HTTP %s.", response.status)
            return False

    except Exception:
        log.exception("ntfy notification failed.")
        return False


async def send_telegram(session, message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Telegram credentials are not configured.")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    try:
        async with session.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message[:4000],
                "disable_web_page_preview": True,
            },
        ) as response:
            result = await response.json()

            if response.status == 200 and result.get("ok"):
                log.info("Telegram notification sent.")
                return True

            # Avoid logging the request URL, which contains the bot token.
            log.error(
                "Telegram notification failed: HTTP %s; %s",
                response.status,
                result.get("description", "Unknown error"),
            )
            return False

    except Exception:
        log.exception("Telegram notification failed.")
        return False


async def send_notification(message: str):
    """Attempt both notification channels independently."""
    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        results = await asyncio.gather(
            send_ntfy(session, message),
            send_telegram(session, message),
            return_exceptions=True,
        )

    for channel, result in zip(("ntfy", "Telegram"), results):
        if isinstance(result, Exception):
            log.error("%s notification raised an error.", channel)
        elif not result:
            log.warning("%s notification was not delivered.", channel)


if __name__ == "__main__":
    asyncio.run(
        send_notification(
            "TEST ONLY: Your visa alert notifications are connected. "
            "This is not a real appointment opening."
        )
    )
