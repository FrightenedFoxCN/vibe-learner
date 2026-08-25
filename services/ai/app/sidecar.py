from __future__ import annotations

import argparse

from app.core.tls import configure_outbound_tls_environment


def main() -> None:
    configure_outbound_tls_environment()

    import uvicorn
    from app.main import app as fastapi_app

    parser = argparse.ArgumentParser(description="Run the Vibe Learner AI desktop sidecar.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    uvicorn.run(
        fastapi_app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        reload=False,
    )


if __name__ == "__main__":
    main()
