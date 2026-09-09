"""Domain contract migration baseline, captured before moving the DTOs."""
import hashlib
import json
from pathlib import Path

from pydantic import BaseModel


BASELINE = json.loads((Path(__file__).parents[1] / "fixtures/harness/domain-dto-baseline-v1.json").read_text())


def assert_domain_contracts(test_case, module):
    names = BASELINE["domains"][module.__name__.rsplit(".", 1)[1]]
    expected_models = {name for name in names if name in BASELINE["schema_digests"]}
    actual_models = {
        name for name, value in vars(module).items()
        if isinstance(value, type) and issubclass(value, BaseModel)
        and value.__module__ == module.__name__ and not name.startswith("_")
    }
    test_case.assertEqual(actual_models, expected_models)
    for name in names:
        with test_case.subTest(contract=name):
            value = getattr(module, name)
            if name in expected_models:
                canonical = json.dumps(value.model_json_schema(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                test_case.assertEqual(hashlib.sha256(canonical).hexdigest(), BASELINE["schema_digests"][name])
            else:
                test_case.assertEqual(value.model_dump(mode="json"), BASELINE["contracts"][name])
