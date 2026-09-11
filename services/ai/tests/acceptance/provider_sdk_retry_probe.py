"""Local HTTP fault injection through the installed SDK; no live model or key."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import subprocess
from threading import Thread
import time

from app.services.provider_sdk import ProviderSDK, ProviderRequestAdapter
from app.services.provider_transport import ProviderTransport


def run(output: Path) -> None:
    sdk = ProviderSDK.load()
    state = {"requests": 0, "failure_limit": None}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("content-length", "0")))
            state["requests"] += 1
            failed = state["failure_limit"] is None or state["requests"] <= state["failure_limit"]
            payload = {"error": {"message": "synthetic service unavailable", "type": "server_error", "code": "fixture"}} if failed else {
                "id": "fixture", "object": "chat.completion", "created": 1, "model": "MiniMax-M3",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "recovered"}}],
            }
            raw = json.dumps(payload).encode()
            self.send_response(503 if failed else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Retry-After", "0.01")
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/v1"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    rows = []
    try:
        for failure_limit in (None, 1):
            for sdk_defaults in (True, False):
                state.update(requests=0, failure_limit=failure_limit)
                attempts = []

                def completion(**kwargs):
                    attempts.append(True)
                    if sdk_defaults:
                        kwargs.pop("num_retries", None)
                        kwargs.pop("max_retries", None)
                    return sdk.completion(**kwargs)

                adapter = ProviderRequestAdapter(api_key="synthetic-local", base_url=endpoint,
                    plan_api_key="synthetic-local", plan_base_url=endpoint,
                    setting_api_key="synthetic-local", setting_base_url=endpoint,
                    chat_api_key="synthetic-local", chat_base_url=endpoint, timeout_seconds=2,
                    completion=completion, responses=None, embedding=None, providers=frozenset({"openai"}),
                    transport=ProviderTransport(timeout_seconds=2, sdk=sdk.error_types, sleep=lambda _: None))
                row = {"scope": "local_sdk_retry_fault_injection", "git_revision": revision,
                    "case": "always_503" if failure_limit is None else "recover_after_one_503",
                    "retry_policy": "sdk_defaults" if sdk_defaults else "production_transport_owned"}
                started = time.perf_counter()
                try:
                    raw, _ = adapter.request_chat_completion({"model": "MiniMax-M3", "messages": [{"role": "user", "content": "synthetic fixture"}]},
                        request_kind="plan", model="MiniMax-M3")
                    row["reply"] = raw["choices"][0]["message"]["content"]
                except Exception as exc:
                    row.update(error_class=type(exc).__name__, error_code=str(exc))
                row.update(actual_http_requests=state["requests"], transport_attempts=len(attempts),
                    elapsed_ms=round((time.perf_counter() - started) * 1000))
                rows.append(row)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    output.write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
