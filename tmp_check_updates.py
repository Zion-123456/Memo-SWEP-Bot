"""Check Telegram updates."""
import os
import json
import urllib.request

token = os.environ["TELEGRAM_BOT_TOKEN"]
url = f"https://api.telegram.org/bot{token}/getUpdates?offset=-5&limit=10"
resp = urllib.request.urlopen(url)
data = json.loads(resp.read().decode())
for u in data.get("result", []):
    msg = u.get("message", {})
    text = msg.get("text", "")
    print(f"Update {u['update_id']}: {repr(text[:80])}")
