"""Send a message and check what the bot responds with."""
import json
import time
import urllib.parse
import urllib.request

token = "8964284841:AAEcCVZFURMcHVKDLl7O0EO9EeEfIpslTYI"
chat_id = 5499527319
base_url = f"https://api.telegram.org/bot{token}"


def send_message(text):
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(f"{base_url}/sendMessage", data=data)
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read().decode())
    print(f"SENT: {text}")
    print(f"  Response: {result.get('ok')}")


def get_updates(limit=10):
    resp = urllib.request.urlopen(f"{base_url}/getUpdates?limit={limit}")
    data = json.loads(resp.read().decode())
    updates = data.get("result", [])
    for u in updates:
        msg = u.get("message", {})
        text = msg.get("text", "")
        from_name = msg.get("from", {}).get("first_name", "")
        print(f"  Update {u['update_id']}: "
              f"from={from_name} text={repr(text[:80])}")
    if not updates:
        print("  (no updates)")
    return updates


print("=== Sending REFLECT message ===")
send_message("how have i made progress so far")
time.sleep(8)
print()
print("=== Checking updates ===")
get_updates(limit=10)
