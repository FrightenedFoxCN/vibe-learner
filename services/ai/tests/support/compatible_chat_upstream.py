"""Local HTTP peer that observes socket closure during a held completion."""

from __future__ import annotations

import json
import select
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Condition, Event, Thread


def reply_body():
    return {
        "id": "fixture-completion",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "text": "I can help examine this choice.",
                            "mood": "calm",
                            "action": "nod",
                            "speech_style": "clear",
                            "delivery_cue": "steady",
                            "state_commentary": "listening",
                            "addressed_participant_ids": [],
                        }
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


class CompatibleChatUpstream:
    def __init__(self, *plans):
        self.plans = deque(plans)
        self.requests = []
        self.condition = Condition()
        self.stop = Event()
        peer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                request = {
                    "path": self.path,
                    "payload": body,
                    "closed": Event(),
                    "holding": Event(),
                }
                with peer.condition:
                    plan = peer.plans.popleft() if peer.plans else "reply"
                    peer.requests.append(request)
                    peer.condition.notify_all()
                try:
                    if plan in {"hold_headers", "hold_body"}:
                        if plan == "hold_body":
                            self.send_response(200)
                            self.send_header("content-type", "application/json")
                            self.send_header("content-length", "4096")
                            self.end_headers()
                            self.wfile.write(b'{"choices":[')
                            self.wfile.flush()
                        request["holding"].set()
                        while not peer.stop.wait(0.01):
                            readable, _, _ = select.select(
                                [self.connection], [], [], 0.05
                            )
                            if readable and self.connection.recv(1) == b"":
                                request["closed"].set()
                                return
                    elif plan == "disconnect":
                        return
                    else:
                        status = (
                            400
                            if plan == "schema_reject"
                            else 401
                            if plan == "unauthorized"
                            else 200
                        )
                        payload = (
                            {
                                "error": {
                                    "code": "unsupported_response_format",
                                    "message": "response format not supported",
                                }
                            }
                            if status == 400
                            else {
                                "error": {
                                    "code": "invalid_key",
                                    "message": "fixture refusal",
                                }
                            }
                            if status == 401
                            else reply_body()
                        )
                        if plan == "invalid_actor":
                            payload["choices"][0]["message"]["content"] = "{}"
                        response = json.dumps(payload).encode()
                        self.send_response(status)
                        self.send_header("content-type", "application/json")
                        self.send_header("content-length", str(len(response)))
                        self.end_headers()
                        self.wfile.write(response)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    request["closed"].set()
                finally:
                    self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        self.thread = Thread(
            target=self.server.serve_forever,
            name="compatible-chat-fixture",
            daemon=True,
        )

    def __enter__(self):
        self.thread.start()
        return self

    def wait_request(self, index=0, timeout=5):
        with self.condition:
            if not self.condition.wait_for(
                lambda: len(self.requests) > index, timeout=timeout
            ):
                raise AssertionError("upstream did not receive a completion")
            return self.requests[index]

    def __exit__(self, *_args):
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
