"""Loopback-only fault controls around the production Study lifecycle, no providers."""

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock

import uvicorn

from app.app_factory import create_app
from app.core.bootstrap import Container
from app.core.settings import Settings


def recovery_app(root: Path):
    gates: list[Event] = []
    calls: list[str] = []
    lock = Lock()

    def container_factory(settings):
        container = Container(settings)
        generate = container.pedagogy_orchestrator.generate_chat_reply

        def controlled(**kwargs):
            message = kwargs["message"]
            with lock:
                calls.append(message)
            if message.startswith("hold:"):
                gate = Event()
                with lock:
                    gates.append(gate)
                if not gate.wait(120):
                    raise RuntimeError("acceptance_hold_expired")
            if message.startswith("reject:"):
                raise RuntimeError("chat_model_invalid_payload")
            if message.startswith("uncertain:"):
                raise RuntimeError("acceptance_ambiguous_outcome")
            return generate(**kwargs)

        container.pedagogy_orchestrator.generate_chat_reply = controlled
        return container

    app = create_app(
        settings=Settings(
            database_url=f"sqlite:///{root / 'runtime.db'}",
            storage_root=str(root / "data"),
            allowed_origins=("http://127.0.0.1:3435",),
            auto_migrate_local_data=False,
            plan_provider="mock",
            ocr_engine="disabled",
        ),
        container_factory=container_factory,
    )

    # These controls exist only in this disposable acceptance server, never in
    # the production router, persistence model or provider schemas.
    @app.post("/__acceptance__/release")
    def release():
        with lock:
            for gate in gates:
                gate.set()
            return {"released": len(gates)}

    @app.get("/__acceptance__/calls")
    def observed_calls():
        with lock:
            return {"messages": list(calls), "held": len(gates)}

    return app


if __name__ == "__main__":
    with TemporaryDirectory(prefix="vibe-study-recovery-") as folder:
        uvicorn.run(recovery_app(Path(folder)), host="127.0.0.1", port=18445)
