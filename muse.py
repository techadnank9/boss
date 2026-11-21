"""Muse connector: Boss sends an order to the shopper's own Muse (muse.ai) and reads the reply.

Boss drives the shopper's installed Google Chrome with a dedicated profile (.muse-profile, git-ignored).
Sign in once with:  python muse.py login
Test an order with: python muse.py ask "wireless earbuds under $50"

Boss only reads messages that arrive after the order it sent. It never buys anything: the order text
tells Muse not to, and Muse itself asks before any purchase.
"""
import asyncio
import os
import sys
import time
from pathlib import Path

PROFILE = Path(__file__).parent / ".muse-profile"
URL = "https://muse.ai/"
HEADLESS = os.getenv("MUSE_HEADLESS", "1") != "0"
_lock = asyncio.Lock()  # one conversation with Muse at a time

# JavaScript run in the Muse page: all chat message texts in order, oldest first.
_MESSAGES_JS = """() => {
  const log = document.querySelector('[aria-label="Chat messages"]') || document.body;
  const nodes = [...log.querySelectorAll('[aria-label^="Assistant message"], [aria-label^="User message"]')];
  if (nodes.length) return nodes.map(n => ({role: n.getAttribute('aria-label').startsWith('User') ? 'user' : 'muse',
                                            text: n.innerText.trim()}));
  return [{role: 'all', text: log.innerText}];
}"""
# All link targets on the page, in document order. Boss keeps only those added after its order.
_LINKS_JS = """() => [...document.querySelectorAll('a[href^="http"]')].map(a => a.href)"""


def _unwrap(url: str) -> str:
    """Meta wraps outbound links as l.meta.ai/?u=<real url>; return the real one."""
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(url).query)
    return q["u"][0] if "l.meta.ai" in url and q.get("u") else url
_STATUS_JS = """() => (document.body.innerText.match(/(Searching|Checking|Working|Opening|Thinking|Looking|Comparing|Reading)[^\\n]{0,60}/) || [''])[0]"""


async def _open(playwright, headless: bool):
    return await playwright.chromium.launch_persistent_context(
        str(PROFILE), channel="chrome", headless=headless, viewport={"width": 1100, "height": 1000},
        args=["--disable-blink-features=AutomationControlled"])


async def _signed_in(page) -> bool:
    return await page.get_by_role("textbox", name="Message").count() > 0


async def login() -> None:
    """Open Muse in Boss's Chrome so the shopper can sign in once."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        ctx = await _open(p, headless=False)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(URL)
        print("Sign in to Muse in the Chrome window. This window closes by itself once you are in.")
        for _ in range(600):
            await asyncio.sleep(1)
            try:
                if await _signed_in(page):
                    print("Signed in. Boss can now talk to Muse.")
                    await asyncio.sleep(2)
                    break
            except Exception:
                pass
        await ctx.close()


async def ask(order: str, on_event=None, timeout: int = 420) -> dict:
    """Send one order to Muse and wait for its answer.

    on_event(kind, data) is called for every message and status change so Boss can log them live.
    Returns {"reply": str, "links": [str], "seconds": float}.
    """
    from playwright.async_api import async_playwright
    emit = on_event or (lambda kind, data: None)
    async with _lock, async_playwright() as p:
        ctx = await _open(p, headless=HEADLESS)
        try:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(URL, wait_until="domcontentloaded")
            box = page.get_by_role("textbox", name="Message")
            try:
                await box.wait_for(timeout=30000)
            except Exception:
                raise RuntimeError("Boss is not signed in to Muse. Run: python muse.py login")
            await page.wait_for_timeout(2500)
            before = await page.evaluate(_MESSAGES_JS)
            links_before = len(await page.evaluate(_LINKS_JS))
            await box.click()
            await box.fill(order)
            await box.press("Enter")
            started = time.monotonic()
            emit("sent", {"text": order})

            seen_status, last_reply, stable_since = "", "", None
            while time.monotonic() - started < timeout:
                await page.wait_for_timeout(3000)
                status = (await page.evaluate(_STATUS_JS)).strip()
                if status and status != seen_status:
                    seen_status = status
                    emit("status", {"text": status})
                msgs = await page.evaluate(_MESSAGES_JS)
                new = [m for m in msgs[len(before):] if m["role"] == "muse"] if msgs and msgs[0]["role"] != "all" else []
                reply = "\n\n".join(m["text"] for m in new)
                if msgs and msgs[0]["role"] == "all":  # fallback: page text after our order
                    full = msgs[0]["text"]
                    at = full.rfind(order[:60])
                    reply = full[at + len(order):].strip() if at >= 0 else ""
                if reply and reply != last_reply:
                    last_reply, stable_since = reply, time.monotonic()
                    continue
                # done when the reply has a price and has not changed for 12s with no work status showing
                if last_reply and "$" in last_reply and not status and time.monotonic() - stable_since > 12:
                    break
            if not last_reply:
                raise RuntimeError(f"Muse did not answer within {timeout}s")
            new_links = (await page.evaluate(_LINKS_JS))[links_before:]
            links = [u for u in dict.fromkeys(_unwrap(h) for h in new_links)
                     if not any(d in u for d in ("muse.ai", "meta.com", "facebook.com", "meta.ai"))]
            seconds = round(time.monotonic() - started, 1)
            emit("received", {"text": last_reply[:4000], "seconds": seconds})
            return {"reply": last_reply, "links": links[:10], "seconds": seconds}
        finally:
            await ctx.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        asyncio.run(login())
    elif len(sys.argv) > 2 and sys.argv[1] == "ask":
        out = asyncio.run(ask(sys.argv[2] + "\n\nShopping research only, please don't buy anything or contact anyone. "
                              "Reply with: product name, price, seller, link, and delivery estimate.",
                              on_event=lambda k, d: print(f"[{k}] {str(d)[:200]}")))
        print(out)
    else:
        print(__doc__)
