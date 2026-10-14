"""
Visa Slot Monitor — Playwright-based change detector
Supports: Telegram, WhatsApp (Twilio), SMS (Twilio)
Modes:
  - Continuous (local):   CHECK_INTERVAL > 0  → loops forever
  - Single-shot (CI):     CHECK_INTERVAL = 0  → checks once and exits (GitHub Actions)
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from config import URLS, CHECK_INTERVAL_SECONDS, STATE_FILE, LOG_FILE
from notifier import send_notification

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ── State persistence ──────────────────────────────────────────────────────────
def load_state() -> dict:
    if Path(STATE_FILE).exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Page scraping ──────────────────────────────────────────────────────────────
CLOUDFLARE_KEYWORDS = ["security service", "verifying you are not a bot", "Ray ID", "Cloudflare"]

async def get_page_content(browser, url: str) -> tuple[str, str]:
    """
    Returns (visible_text, sha256_hash).
    Uses a real Chromium browser so JS-rendered pages and #hash fragments work.
    """
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/New_York",
        viewport={"width": 1280, "height": 800},
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page = await context.new_page()
    try:
        response = await page.goto(
    url,
    wait_until="domcontentloaded",
    timeout=60_000
)

if response is None or not response.ok:
    status = response.status if response else "no response"
    raise RuntimeError(f"Page unavailable: HTTP {status}")

await page.wait_for_timeout(5_000)

        if "#" in url:
            fragment = url.split("#")[-1]
            try:
                await page.evaluate(
                    f"document.getElementById('{fragment}')?.scrollIntoView()"
                )
                await page.wait_for_timeout(1_500)
            except Exception:
                pass

        text = await page.evaluate("""() => {
            ['nav','footer','header','script','style','noscript',
             '.cookie-banner','#cookie-notice','.ads','.advertisement']
              .forEach(sel => document.querySelectorAll(sel)
                .forEach(el => el.remove()));
            return document.body?.innerText?.trim() ?? '';
        }""")

        if any(kw in text for kw in CLOUDFLARE_KEYWORDS):
            raise RuntimeError("Cloudflare challenge page detected — bot blocked")

        return text, hashlib.sha256(text.encode()).hexdigest()
    finally:
        await page.close()
        await context.close()


# ── Diff summary ───────────────────────────────────────────────────────────────
def summarize_change(old_text: str, new_text: str) -> str:
    old_lines = set(old_text.splitlines())
    new_lines = set(new_text.splitlines())
    added   = [l for l in (new_lines - old_lines) if l.strip()]
    removed = [l for l in (old_lines - new_lines) if l.strip()]
    parts = []
    if added:
        parts.append("➕ *New content:*\n```\n" + "\n".join(added[:6]) + "\n```")
    if removed:
        parts.append("➖ *Removed:*\n```\n" + "\n".join(removed[:6]) + "\n```")
    return "\n\n".join(parts) if parts else "Page content changed."


# ── Core check logic ───────────────────────────────────────────────────────────
async def check_all_urls(browser, state: dict, texts: dict) -> bool:
    changed = False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for entry in URLS:
        url   = entry["url"]
        label = entry["label"]
        try:
            new_text, new_hash = await get_page_content(browser, url)
            old_hash = state.get(url, {}).get("hash", "")

            if url not in state:
                state[url] = {}
            state[url]["label"]        = label
            state[url]["last_checked"] = now

            if old_hash == "":
                log.info(f"   📸 Baseline recorded: {label}")
                state[url]["hash"] = new_hash
                texts[url] = new_text
            elif new_hash != old_hash:
                log.info(f"   🔔 CHANGE DETECTED: {label}")
                diff = summarize_change(texts.get(url, ""), new_text)
                message = (
                   message = (
    f"⚠️ PAGE CONTENT CHANGED — NOT A CONFIRMED SLOT\n\n"
    f"Site: {label}\n"
    f"URL: {url}\n\n"
    f"{diff}\n\n"
    f"Checked: {now}\n\n"
    f"Please verify availability on the official scheduling portal."
)
                )
                await send_notification(message)
                state[url]["hash"] = new_hash
                texts[url] = new_text
                changed = True
            else:
                log.info(f"   — No change: {label}")

        except Exception as e:
            log.error(f"   ❌ Error checking {label}: {e}")

    save_state(state)
    return changed


# ── Entry point ────────────────────────────────────────────────────────────────
async def run_monitor():
    state = load_state()
    texts: dict[str, str] = {}

    log.info("🚀 Visa slot monitor starting")
    log.info(f"   URLs     : {len(URLS)}")
    log.info(f"   Mode     : {'single-shot (CI)' if CHECK_INTERVAL_SECONDS == 0 else 'continuous (' + str(CHECK_INTERVAL_SECONDS) + 's)'}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        if CHECK_INTERVAL_SECONDS == 0:
            # GitHub Actions mode — check once and exit
            log.info("⚡ Running single check...")
            await check_all_urls(browser, state, texts)
            log.info("✅ Done. Exiting.")
        else:
            # Local continuous mode
            log.info("👁️  Continuous mode started\n")
            while True:
                await check_all_urls(browser, state, texts)
                log.info(f"   💤 Sleeping {CHECK_INTERVAL_SECONDS}s...\n")
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run_monitor())
