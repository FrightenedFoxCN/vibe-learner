from __future__ import annotations

import os
import ssl
from collections.abc import MutableMapping
from pathlib import Path

import certifi


_CA_BUNDLE_ENV_VARS = (
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
)


def certifi_ca_bundle_path() -> str:
    path = Path(certifi.where()).resolve()
    if not path.is_file():
        raise RuntimeError("certifi_ca_bundle_missing")
    return str(path)


def configure_outbound_tls_environment(
    environment: MutableMapping[str, str] | None = None,
) -> str:
    target = os.environ if environment is None else environment
    configured_path = next(
        (
            str(target.get(name) or "").strip()
            for name in _CA_BUNDLE_ENV_VARS
            if str(target.get(name) or "").strip()
        ),
        "",
    )
    ca_bundle_path = configured_path or certifi_ca_bundle_path()
    for name in _CA_BUNDLE_ENV_VARS:
        if not str(target.get(name) or "").strip():
            target[name] = ca_bundle_path
    return ca_bundle_path


def create_outbound_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi_ca_bundle_path())
    return context
