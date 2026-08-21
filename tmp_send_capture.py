"""Send a single CAPTURE message and verify event is created."""
import json
import time
import urllib.parse
import urllib.request

token = "8964284841:AAEcCVZFURMcHVKDLl7O0EO9EeEfIpslTYI"
chat_id = 5499527319
base = f"https://api.telegram.org/bot{token}"

text = "I love machine learning and data science."
data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
req = urllib.request.Request(f"{base}/sendMessage", data=data)
resp = urllib.request.urlopen(req)
result = json.loads(resp.read().decode())
print(f"Sent: {text}")
print(f"Response: {result['ok']}")
print("Waiting for bot to process...")
time.sleep(8)
print("Done. Check database.")
