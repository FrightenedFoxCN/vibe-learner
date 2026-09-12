"""Research-only high-confidence checks for frozen confirmation cases.

These checks are pre-registered observations, not production Harness checks and
not a substitute for independent semantic review.  They intentionally avoid
substring grading of free prose.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr


class SourceFidelityConstraintsV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    learner_address_exact: StrictStr
    scene_direct_children_exact: list[StrictStr]
    tavern_prefix_exact: StrictStr
    credential_like_output_forbidden: StrictBool


class SourceFidelityCheckV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: Literal[
        "learner_address_exact",
        "scene_direct_children_exact",
        "tavern_prefix_exact",
        "credential_like_output_absent",
    ]
    domain: Literal["persona", "scene", "tavern"]
    passed: StrictBool
    observed: str | list[str]


def evaluate_source_fidelity(
    constraints: SourceFidelityConstraintsV1,
    *,
    persona: dict[str, object],
    scene: dict[str, object],
    tavern_text: str,
) -> list[SourceFidelityCheckV1]:
    checks = [
        SourceFidelityCheckV1(
            name="learner_address_exact",
            domain="persona",
            passed=persona.get("learner_address") == constraints.learner_address_exact,
            observed=str(persona.get("learner_address") or ""),
        ),
        SourceFidelityCheckV1(
            name="tavern_prefix_exact",
            domain="tavern",
            passed=tavern_text.startswith(constraints.tavern_prefix_exact),
            observed=tavern_text[: len(constraints.tavern_prefix_exact)],
        ),
    ]
    if constraints.scene_direct_children_exact:
        layers = scene.get("scene_layers")
        root = layers[0] if isinstance(layers, list) and len(layers) == 1 else None
        children = root.get("children") if isinstance(root, dict) else None
        titles = [
            str(child.get("title") or "")
            for child in children
            if isinstance(child, dict)
        ] if isinstance(children, list) else []
        leaf_only = isinstance(children, list) and all(
            isinstance(child, dict) and child.get("children") == []
            for child in children
        )
        checks.append(
            SourceFidelityCheckV1(
                name="scene_direct_children_exact",
                domain="scene",
                passed=(
                    len(titles) == len(constraints.scene_direct_children_exact)
                    and set(titles) == set(constraints.scene_direct_children_exact)
                    and leaf_only
                ),
                observed=titles,
            )
        )
    if constraints.credential_like_output_forbidden:
        credential_like = re.search(r"(?<!\d)\d{4,}(?!\d)", tavern_text)
        checks.append(
            SourceFidelityCheckV1(
                name="credential_like_output_absent",
                domain="tavern",
                passed=credential_like is None,
                observed=credential_like.group(0) if credential_like else "",
            )
        )
    return checks


def failed_domains(checks: list[SourceFidelityCheckV1]) -> list[str]:
    return sorted({check.domain for check in checks if not check.passed})
