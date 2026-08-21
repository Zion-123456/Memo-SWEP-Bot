"""Check all Telegram updates."""
import json
import urllib.request

token = "8964284841:AAEcCVZFURMcHVKDLl7O0EO9EeEfIpslTYI"
url = f"https://api.telegram.org/bot{token}/getUpdates?limit=20"
resp = urllib.request.urlopen(url)
data = json.loads(resp.read().decode())
for u in data.get("result", []):
    msg = u.get("message", {})
    text = msg.get("text", "")
    from_name = msg.get("from", {}).get("first_name", "")
    print(f"Update {u['update_id']}: from={from_name} text={repr(text[:80])}")
if not data.get("result"):
    print("(no updates)")
