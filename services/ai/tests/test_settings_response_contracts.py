"""Public settings contracts and actual HTTP responses across the browser decoder."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.app_factory import create_app
from app.core.settings import Settings
from app.models.api import (
    ModelToolConfigResponse,
    RuntimeCapabilitySignalResponse,
    RuntimeFeatureReadinessResponse,
    RuntimeSettingsProbeResponse,
    RuntimeSettingsResponse,
    TokenUsageStatsResponse,
)
from app.models.domain import TokenUsageRecord
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "packages/shared/fixtures/settings/responses-v1.json"
MODELS = {
    "runtime_settings": RuntimeSettingsResponse,
    "model_tools": ModelToolConfigResponse,
    "model_probe": RuntimeSettingsProbeResponse,
    "model_usage": TokenUsageStatsResponse,
}


class SettingsResponseContractTests(unittest.TestCase):
    def test_shared_fixture_matches_public_models_and_enum_vocabularies(self):
        data = json.loads(FIXTURE.read_text())
        for name, model in MODELS.items():
            with self.subTest(name=name):
                self.assertEqual(
                    model.model_validate(data[name]).model_dump(mode="json"), data[name]
                )
        self.assertEqual(
            RuntimeSettingsProbeResponse.model_json_schema()["properties"][
                "feature_readiness"
            ]["propertyNames"]["enum"],
            data["vocabularies"]["probe_features"],
        )
        for name, model, field in (
            ("capability_statuses", RuntimeCapabilitySignalResponse, "status"),
            ("capability_sources", RuntimeCapabilitySignalResponse, "source"),
            ("readiness_statuses", RuntimeFeatureReadinessResponse, "status"),
        ):
            self.assertEqual(
                model.model_json_schema()["properties"][field]["enum"],
                data["vocabularies"][name],
            )

    def test_actual_http_reads_and_mutations_pass_current_browser_decoders(self):
        fixture = json.loads(FIXTURE.read_text())
        with TemporaryDirectory(prefix="model-response-http-") as folder:
            root = Path(folder)
            app = create_app(
                settings=Settings(
                    database_url=f"sqlite:///{root / 'app.db'}",
                    storage_root=str(root / "data"),
                    plan_provider="mock",
                    auto_migrate_local_data=False,
                    ocr_engine="disabled",
                )
            )
            with TestClient(app) as client:

                def response(value):
                    self.assertEqual(value.status_code, 200, value.text)
                    return value.json()

                settings = response(client.get("/runtime-settings"))
                saved = response(
                    client.patch("/runtime-settings", json={"show_debug_info": False})
                )
                secrets = response(
                    client.put(
                        "/runtime-settings/session-secrets",
                        json={"openai_api_key": "fixture-only"},
                    )
                )
                cleared = response(client.delete("/runtime-settings/session-secrets"))
                tools = response(client.get("/model-tools/config"))
                tool = tools["stages"][0]["tools"][0]
                updated_tools = response(
                    client.patch(
                        "/model-tools/config",
                        json={
                            "toggles": [
                                {
                                    "stage_name": tools["stages"][0]["name"],
                                    "tool_name": tool["name"],
                                    "enabled": False,
                                }
                            ]
                        },
                    )
                )
                for record in fixture["model_usage"]["records"]:
                    app.state.container.token_usage_service.record_entry(
                        TokenUsageRecord.model_validate(record)
                    )
                usage = response(client.get("/model-usage/stats"))
                with (
                    patch(
                        "app.api.routes.probe_openai_models",
                        return_value=fixture["model_probe"],
                    ),
                    patch("app.api.routes.OpenAIModelProvider") as provider,
                ):
                    provider.return_value.probe_feature_readiness.return_value = (
                        fixture["model_probe"]["feature_readiness"]
                    )
                    probe = response(
                        client.post(
                            "/runtime-settings/check-openai-models",
                            json={
                                "api_key": "fixture-only",
                                "base_url": "https://example.invalid",
                                "model": "fixture-model",
                                "features": ["plan"],
                            },
                        )
                    )
            # No provider is contacted: only JSON from the real HTTP DTOs crosses into Node.
            modules = {
                name: (ROOT / "apps/web/lib" / filename).as_uri()
                for name, filename in (
                    ("settings", "runtime-settings-decode.ts"),
                    ("tools", "model-tools-decode.ts"),
                    ("usage", "model-usage-decode.ts"),
                )
            }
            script = f"""
                import {{ readFileSync }} from 'node:fs';
                import {{ decodeRuntimeSettings, decodeRuntimeModelProbe }} from {json.dumps(modules["settings"])};
                import {{ decodeModelToolConfig }} from {json.dumps(modules["tools"])};
                import {{ decodeModelUsageStats }} from {json.dumps(modules["usage"])};
                const raw = JSON.parse(readFileSync(0, 'utf8'));
                raw.settings.forEach(decodeRuntimeSettings);
                raw.tools.forEach(decodeModelToolConfig);
                const usage = decodeModelUsageStats(raw.usage);
                decodeRuntimeModelProbe(raw.probe, {{ model: "fixture-model", features: ["plan"] }});
                if (usage.totalTokens !== 207) throw new Error('wrong usage read-back');
                console.log('actual HTTP contracts passed');
            """
            result = subprocess.run(
                [
                    "node",
                    "--experimental-strip-types",
                    "--input-type=module",
                    "-e",
                    script,
                ],
                input=json.dumps(
                    {
                        "settings": [settings, saved, secrets, cleared],
                        "tools": [tools, updated_tools],
                        "usage": usage,
                        "probe": probe,
                    }
                ),
                text=True,
                capture_output=True,
                cwd=ROOT,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
