"""Disposable real Tavern API with controlled mock actor holds/failures."""

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock

import uvicorn

from app.app_factory import create_app
from app.core.bootstrap import Container
from app.core.settings import Settings
from app.services.model_provider import MockModelProvider


def order_app(root: Path):
    lock = Lock()
    fail_once: set[str] = set()
    hold: set[str] = set()
    gates: list[Event] = []
    calls: list[dict] = []

    class ControlledProvider(MockModelProvider):
        def generate_tavern_actor_reply(self, **kwargs):
            persona = kwargs["persona"]
            with lock:
                calls.append(
                    {
                        "persona_id": persona.id,
                        "name": persona.name,
                        "message": kwargs["user_message"],
                    }
                )
                fail = persona.name in fail_once
                fail_once.discard(persona.name)
                gate = Event() if persona.name in hold else None
                if gate is not None:
                    gates.append(gate)
            if gate is not None and not gate.wait(60):
                raise RuntimeError("acceptance_actor_hold_expired")
            if fail:
                raise RuntimeError("acceptance_actor_failure")
            return super().generate_tavern_actor_reply(**kwargs)

    def container_factory(settings):
        container = Container(settings)
        container.tavern_service.model_provider = ControlledProvider()
        return container

    app = create_app(
        settings=Settings(
            database_url=f"sqlite:///{root / 'runtime.db'}",
            storage_root=str(root / "data"),
            allowed_origins=("http://127.0.0.1:3437",),
            auto_migrate_local_data=False,
            plan_provider="mock",
            ocr_engine="disabled",
        ),
        container_factory=container_factory,
    )

    # Test-only controls; these never enter the production route table.
    @app.post("/__acceptance__/configure")
    def configure(payload: dict):
        with lock:
            fail_once.clear()
            fail_once.update(payload.get("fail_once", []))
            hold.clear()
            hold.update(payload.get("hold", []))
        return {"configured": True}

    @app.post("/__acceptance__/release")
    def release():
        with lock:
            for gate in gates:
                gate.set()
            hold.clear()
        return {"released": True}

    @app.get("/__acceptance__/calls")
    def observed_calls():
        with lock:
            return {"calls": list(calls)}

    return app


if __name__ == "__main__":
    with TemporaryDirectory(prefix="vibe-tavern-order-") as folder:
        uvicorn.run(order_app(Path(folder)), host="127.0.0.1", port=18447)
