"""Independent catalog/manifest comparison; no provider calls or credentials."""
import json
from app.services.model_provider import TOOL_CATALOG, CHAT_STAGE
from app.models.harness import HarnessWorkflow, HarnessStage
from app.models.tool_manifest import resolve_tool_manifest_entry

mismatches = []
for name, info in TOOL_CATALOG[CHAT_STAGE].items():
    entry = resolve_tool_manifest_entry(
        workflow=HarnessWorkflow.STUDY_CHAT,
        offered_in_stage=HarnessStage.STUDY_CHAT_REPLY,
        transport_name=name,
    )
    if info["description"] != entry.display.provider_description:
        mismatches.append({"tool": name, "catalog": info["description"],
                           "manifest": entry.display.provider_description})
print(json.dumps({"passed": not mismatches, "mismatches": mismatches},
                 ensure_ascii=False, indent=2))
raise SystemExit(1 if mismatches else 0)
