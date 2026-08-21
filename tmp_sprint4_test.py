"""Comprehensive Telegram test for Sprint 4 intent routing."""
import json
import time
import urllib.parse
import urllib.request

TOKEN = "8964284841:AAEcCVZFURMcHVKDLl7O0EO9EeEfIpslTYI"
CHAT_ID = 5499527319
BASE = f"https://api.telegram.org/bot{TOKEN}"


def send(text):
    """Send a message to the bot."""
    data = urllib.parse.urlencode(
        {"chat_id": CHAT_ID, "text": text}
    ).encode()
    req = urllib.request.Request(f"{BASE}/sendMessage", data=data)
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read().decode())
    return result.get("ok", False)


# Sequence of test messages
messages = [
    ("capture", "Today I studied drilling operations and reservoir engineering."),
    ("reflect", "How have i made progress so far"),
    ("retrieve", "What did I learn today?"),
    ("conversation", "Hello Memo"),
    ("capture", "Remember that I spent today studying reservoir engineering."),
]

print("=== Sprint 4 Telegram Test Sequence ===")
print()

for i, (intent, text) in enumerate(messages, 1):
    print(f"Step {i}: [{intent}] Sending: {text}")
    ok = send(text)
    print(f"  Sent: {ok}")
    print("  Waiting for bot to process...")
    time.sleep(8)
    print()

print("=== Test sequence complete ===")
print("Check database to verify only CAPTURE messages created events.")
