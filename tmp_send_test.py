"""Check if the bot has the intent router configured."""
import asyncio
import urllib.request
import json

# We can't directly access bot_data from outside, but we can verify
# the bot is running and check the database for new events.

# First, send a message that SHOULD NOT be captured
token = "8964284841:AAEcCVZFURMcHVKDLl7O0EO9EeEfIpslTYI"
chat_id = 5499527319
base_url = f"https://api.telegram.org/bot{token}"

text = "how have i made progress so far"
data = urllib.parse.urlencode(
    {"chat_id": chat_id, "text": text}
).encode()
req = urllib.request.Request(f"{base_url}/sendMessage", data=data)
resp = urllib.request.urlopen(req)
result = json.loads(resp.read().decode())
print(f"Sent: {text}")
print(f"Response ok: {result['ok']}")
