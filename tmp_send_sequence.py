"""Send test sequence to the Memo bot and verify behavior."""
import json
import time
import urllib.parse
import urllib.request

TOKEN = "8964284841:AAEcCVZFURMcHVKDLl7O0EO9EeEfIpslTYI"
CHAT_ID = 5499527319
BASE = f"https://api.telegram.org/bot{TOKEN}"


def send(text):
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(f"{BASE}/sendMessage", data=data)
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read().decode())
    print(f"SENT: {text}")


# Step 1: CAPTURE message
print("=== Step 1: CAPTURE message ===")
send("Today I studied drilling operations and reservoir engineering.")
print("Waiting for bot to process...")
time.sleep(5)
print()

# Step 2: REFLECT message
print("=== Step 2: REFLECT message ===")
send("how have i made progress so far")
print("Waiting for bot to process...")
time.sleep(8)
print()

# Step 3: RETRIEVE message
print("=== Step 3: RETRIEVE message ===")
send("What did I learn today?")
print("Waiting for bot to process...")
time.sleep(5)
print()

# Step 4: CONVERSATION message
print("=== Step 4: CONVERSATION message ===")
send("Hello Memo")
print("Waiting for bot to process...")
time.sleep(5)
print()

print("Done. Check bot logs for responses.")
