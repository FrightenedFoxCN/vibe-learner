from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.tls import (
    certifi_ca_bundle_path,
    configure_outbound_tls_environment,
    create_outbound_ssl_context,
)


class OutboundTlsConfigTests(unittest.TestCase):
    def test_missing_certifi_bundle_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_path = Path(directory) / "missing-cacert.pem"
            with patch("app.core.tls.certifi.where", return_value=str(missing_path)):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "certifi_ca_bundle_missing",
                ):
                    certifi_ca_bundle_path()

    def test_configure_environment_uses_certifi_for_all_supported_clients(self) -> None:
        environment: dict[str, str] = {}
        with patch(
            "app.core.tls.certifi_ca_bundle_path",
            return_value="/bundled/cacert.pem",
        ):
            selected = configure_outbound_tls_environment(environment)

        self.assertEqual(selected, "/bundled/cacert.pem")
        self.assertEqual(environment["SSL_CERT_FILE"], selected)
        self.assertEqual(environment["REQUESTS_CA_BUNDLE"], selected)
        self.assertEqual(environment["CURL_CA_BUNDLE"], selected)

    def test_configure_environment_preserves_custom_ca_bundle(self) -> None:
        environment = {"SSL_CERT_FILE": "/custom/company-ca.pem"}

        selected = configure_outbound_tls_environment(environment)

        self.assertEqual(selected, "/custom/company-ca.pem")
        self.assertEqual(environment["SSL_CERT_FILE"], selected)
        self.assertEqual(environment["REQUESTS_CA_BUNDLE"], selected)
        self.assertEqual(environment["CURL_CA_BUNDLE"], selected)

    def test_ssl_context_adds_certifi_without_disabling_default_trust(self) -> None:
        context = MagicMock()
        with (
            patch("app.core.tls.ssl.create_default_context", return_value=context) as create,
            patch(
                "app.core.tls.certifi_ca_bundle_path",
                return_value="/bundled/cacert.pem",
            ),
        ):
            result = create_outbound_ssl_context()

        self.assertIs(result, context)
        create.assert_called_once_with()
        context.load_verify_locations.assert_called_once_with(
            cafile="/bundled/cacert.pem"
        )


if __name__ == "__main__":
    unittest.main()
