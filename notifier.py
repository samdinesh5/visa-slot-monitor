
"""US H-1B visa alerts via ntfy phone notifications."""

import asyncio
import logging
import os

import aiohttp

log = logging.getLogger(__name__)

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_BASE_URL = os.environ.get(
    "NTFY_BASE_URL", "https://ntfy.sh"
).rstrip("/")


async def send_notification(message: str) -> bool:
    """Send a phone push notification through ntfy."""

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

                log.error(
                    "ntfy failed: HTTP %s; %s",
                    response.status,
                    await response.text(),
                )
                return False

    except Exception:
        log.exception("ntfy notification failed.")
        return False


if __name__ == "__main__":
    asyncio.run(
        send_notification(
            "Test notification from your GitHub visa monitor. "
            "This is not a real appointment alert."
        )
    )
