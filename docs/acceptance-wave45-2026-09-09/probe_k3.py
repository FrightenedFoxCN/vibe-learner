"""Read-only model discovery at the documented Kimi official endpoint."""
import argparse
import json
import os
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--platform", choices=("kimi", "minimax"), default="kimi")
args = parser.parse_args()
endpoint = {"kimi": "https://api.moonshot.cn/v1/models",
            "minimax": "https://api.minimax.cn/v1/models"}[args.platform]
response = httpx.get(endpoint,
                     headers={"Authorization": "Bearer " + os.environ["K3_API_KEY"]},
                     timeout=30, follow_redirects=False)
print(json.dumps({"status": response.status_code,
                  "endpoint": endpoint,
                  "model_ids": [m["id"] for m in response.json().get("data", [])]
                  if response.status_code == 200 else []}))
