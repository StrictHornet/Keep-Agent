"""
📱 Telegram Notification Module
=================================
Simple HTTPS POST to Telegram Bot API.

Setup:
  1. Message @BotFather on Telegram → /newbot → get token
  2. Message your bot, then visit:
     https://api.telegram.org/bot<TOKEN>/getUpdates
     to find your chat_id
  3. Set env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import logging
import urllib.request
import urllib.parse
import json

log = logging.getLogger("keep_agent.telegram")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Telegram message length limit
MAX_MESSAGE_LENGTH = 4096


def send_telegram_message(text: str, bot_token: str, chat_id: str) -> bool:
    """
    Send a message via Telegram Bot API.
    Uses Markdown parsing for formatting.
    Falls back to plain text if Markdown fails.
    
    Returns True on success.
    """
    if not bot_token or not chat_id:
        log.error("Missing Telegram credentials")
        return False

    # Truncate if too long
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH - 50] + "\n\n_...truncated_"
        log.warning("Message truncated to fit Telegram limit")

    url = TELEGRAM_API.format(token=bot_token)

    # Try Markdown first, fall back to plain text
    for parse_mode in ["Markdown", None]:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                if result.get("ok"):
                    log.info(f"Message sent (parse_mode={parse_mode})")
                    return True
                else:
                    log.warning(f"Telegram API returned ok=false: {result}")

        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            log.warning(f"Telegram HTTP {e.code} (parse_mode={parse_mode}): {body}")
            if parse_mode == "Markdown":
                log.info("Retrying without Markdown formatting...")
                continue
            return False
        except Exception as e:
            log.error(f"Telegram request failed: {e}")
            return False

    return False
