import json
import os
import urllib.request
from pathlib import Path

config = json.loads(Path(__file__).with_name("config.json").read_text(encoding="utf-8"))
headers = {"Content-Type": "application/json"}
if key := os.environ.get("ARG_POC_OV_API_KEY"):
    headers["X-API-Key"] = key
for variable, header in (
    ("ARG_POC_OV_ACCOUNT", "X-OpenViking-Account"),
    ("ARG_POC_OV_USER", "X-OpenViking-User"),
):
    if value := os.environ.get(variable):
        headers[header] = value
body = {field: config[field] for field in ("query", "target_uri", "limit")}
body["telemetry"] = True
request = urllib.request.Request(
    config["url"].rstrip("/") + "/api/v1/search/find",
    data=json.dumps(body).encode(),
    headers=headers,
)
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
except urllib.error.URLError as error:
    raise SystemExit(f"OpenViking request failed: {error.reason}") from error
if payload.get("status") != "ok":
    raise SystemExit(f"OpenViking returned an error: {payload.get('error')}")
print(json.dumps(payload, ensure_ascii=False, indent=2))
