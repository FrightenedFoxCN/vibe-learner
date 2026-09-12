"""Deterministic, research-only closed-world checks for Scene proposals.

The policy is manually pre-registered by an experiment author.  It is not
derived from source prose, does not call a provider, and is not a production
Harness validator.  Invalid policies and malformed proposal inputs raise
instead of producing an empty (apparently passing) issue list.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    ValidationError,
    model_validator,
)

from app.models.scene import SceneTreeProposalV1


class SceneClosedWorldPolicyV1(BaseModel):
    """Human-authored expectations for one frozen Scene case."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal["scene-closed-world-policy-v1"] = (
        "scene-closed-world-policy-v1"
    )
    root_title: StrictStr | None = None
    direct_children_exact: list[StrictStr]
    # V1 has no recursive policy language. Allowing deeper layers would leave
    # their objects and entrances unconstrained, so this closed-world contract
    # only supports the no-deeper-layer case.
    forbid_deeper_layers: Literal[True]
    required_root_objects: list[StrictStr]
    allowed_root_objects: list[StrictStr]
    required_child_objects_by_title: dict[StrictStr, list[StrictStr]]
    allowed_child_objects_by_title: dict[StrictStr, list[StrictStr]]
    allowed_entrances: list[StrictStr]

    @model_validator(mode="after")
    def validate_unambiguous_policy(self) -> "SceneClosedWorldPolicyV1":
        if self.root_title is not None and not self.root_title:
            raise ValueError("empty_root_title")
        _require_unique_nonempty(self.direct_children_exact, "direct_children_exact")
        if self.root_title in self.direct_children_exact:
            raise ValueError("root_title_conflicts_with_child_title")
        _require_unique_nonempty(
            self.required_root_objects,
            "required_root_objects",
        )
        _require_unique_nonempty(self.allowed_root_objects, "allowed_root_objects")
        if not set(self.required_root_objects).issubset(self.allowed_root_objects):
            raise ValueError("required_root_object_not_allowed")
        for field_name, mapping in (
            ("required_child_objects_by_title", self.required_child_objects_by_title),
            ("allowed_child_objects_by_title", self.allowed_child_objects_by_title),
        ):
            for title, names in mapping.items():
                if not title:
                    raise ValueError(f"{field_name}:empty_layer_title")
                _require_unique_nonempty(names, f"{field_name}:{title}")
        child_titles = set(self.direct_children_exact)
        if set(self.required_child_objects_by_title) != child_titles:
            raise ValueError("required_child_object_titles_mismatch")
        if set(self.allowed_child_objects_by_title) != child_titles:
            raise ValueError("allowed_child_object_titles_mismatch")
        for title, required in self.required_child_objects_by_title.items():
            allowed = self.allowed_child_objects_by_title[title]
            if not set(required).issubset(allowed):
                raise ValueError(f"required_object_not_allowed:{title}")
        _require_nonempty_unique_choices(
            self.allowed_entrances,
            "allowed_entrances",
        )
        return self


SceneClosedWorldIssueCode = Literal[
    "root_title_mismatch",
    "extra_child",
    "missing_child",
    "extra_depth",
    "missing_object",
    "unsupported_object",
    "duplicate_object",
    "unsupported_entrance",
]


class SceneClosedWorldIssueV1(BaseModel):
    """One deterministic finding; an empty list is the only passing result."""

    model_config = ConfigDict(extra="forbid", strict=True)

    code: SceneClosedWorldIssueCode
    path: StrictStr
    expected: StrictStr | None = None
    observed: StrictStr | None = None


class SceneClosedWorldInputError(ValueError):
    """The candidate was not a structurally usable Scene proposal."""


def validate_scene_closed_world(
    policy: SceneClosedWorldPolicyV1,
    proposal: Mapping[str, object] | BaseModel,
) -> list[SceneClosedWorldIssueV1]:
    """Evaluate a decoded SceneTreeProposalV1 or its JSON-shaped dictionary.

    Matching is deliberately literal and case-sensitive. Entrance checks cover
    only the structured ``entrance`` field on the root and registered direct
    children; they do not classify claims in free text. Policy entries are never
    inferred from candidate or source text. A malformed candidate raises
    :class:`SceneClosedWorldInputError`, so callers cannot count it as passing.
    """

    payload = _proposal_mapping(proposal)
    if payload.get("schema_name") != "scene-tree-proposal":
        raise SceneClosedWorldInputError("invalid_scene_schema_name")
    if payload.get("schema_version") != "scene-tree-proposal-v1":
        raise SceneClosedWorldInputError("invalid_scene_schema_version")
    roots = _layer_list(payload.get("scene_layers"), "scene_layers", nonempty=True)
    if len(roots) != 1:
        raise SceneClosedWorldInputError("scene_requires_one_policy_root")
    root = roots[0]
    root_path = "scene_layers[0]"
    root_title = _nonempty_string(root.get("title"), f"{root_path}.title")

    issues: list[SceneClosedWorldIssueV1] = []
    if policy.root_title is not None and root_title != policy.root_title:
        issues.append(
            _issue(
                "root_title_mismatch",
                f"{root_path}.title",
                expected=policy.root_title,
                observed=root_title,
            )
        )

    children = _layer_list(root.get("children"), f"{root_path}.children")
    child_titles = [
        _nonempty_string(child.get("title"), f"{root_path}.children[{index}].title")
        for index, child in enumerate(children)
    ]
    expected_counts = Counter(policy.direct_children_exact)
    observed_counts = Counter(child_titles)
    for title in policy.direct_children_exact:
        if observed_counts[title] < expected_counts[title]:
            issues.append(
                _issue(
                    "missing_child",
                    f"{root_path}.children",
                    expected=title,
                )
            )
    for index, title in enumerate(child_titles):
        if observed_counts[title] > expected_counts[title]:
            issues.append(
                _issue(
                    "extra_child",
                    f"{root_path}.children[{index}].title",
                    observed=title,
                )
            )
            observed_counts[title] -= 1

    _walk_layers(roots, "scene_layers", issues, policy)
    _validate_objects(
        root,
        root_path,
        required=policy.required_root_objects,
        allowed=policy.allowed_root_objects,
        issues=issues,
    )
    _validate_entrance(
        root,
        root_path,
        allowed=policy.allowed_entrances,
        issues=issues,
    )
    children_by_title: dict[str, list[tuple[int, Mapping[str, object]]]] = {}
    for index, child in enumerate(children):
        children_by_title.setdefault(child_titles[index], []).append((index, child))
    for title in policy.direct_children_exact:
        matches = children_by_title.get(title, [])
        if len(matches) != 1:
            continue
        index, child = matches[0]
        child_path = f"{root_path}.children[{index}]"
        _validate_objects(
            child,
            child_path,
            required=policy.required_child_objects_by_title[title],
            allowed=policy.allowed_child_objects_by_title[title],
            issues=issues,
        )
        _validate_entrance(
            child,
            child_path,
            allowed=policy.allowed_entrances,
            issues=issues,
        )
    return issues


def _require_unique_nonempty(values: list[str], field_name: str) -> None:
    if any(not value for value in values):
        raise ValueError(f"{field_name}:empty_value")
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name}:duplicate_value")


def _require_nonempty_unique_choices(values: list[str], field_name: str) -> None:
    if not values:
        raise ValueError(f"{field_name}:missing_choices")
    _require_unique_nonempty(values, field_name)


def _proposal_mapping(proposal: Mapping[str, object] | BaseModel) -> Mapping[str, object]:
    if isinstance(proposal, BaseModel):
        payload: Any = proposal.model_dump(mode="python")
    else:
        payload = proposal
    if not isinstance(payload, Mapping):
        raise SceneClosedWorldInputError("scene_proposal_must_be_mapping_or_model")
    try:
        decoded = SceneTreeProposalV1.model_validate(payload, strict=True)
    except ValidationError as exc:
        raise SceneClosedWorldInputError("scene_proposal_strict_decode_failed") from exc
    return decoded.model_dump(mode="python")


def _layer_list(value: object, path: str, *, nonempty: bool = False) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or (nonempty and not value):
        raise SceneClosedWorldInputError(f"invalid_layer_list:{path}")
    if not all(isinstance(item, Mapping) for item in value):
        raise SceneClosedWorldInputError(f"invalid_layer:{path}")
    return value


def _object_list(value: object, path: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise SceneClosedWorldInputError(f"invalid_object_list:{path}")
    return value


def _nonempty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise SceneClosedWorldInputError(f"invalid_nonempty_string:{path}")
    return value


def _walk_layers(
    layers: list[Mapping[str, object]],
    base_path: str,
    issues: list[SceneClosedWorldIssueV1],
    policy: SceneClosedWorldPolicyV1,
    *,
    depth: int = 0,
) -> None:
    for index, layer in enumerate(layers):
        path = f"{base_path}[{index}]"
        _object_list(layer.get("objects"), f"{path}.objects")
        children = _layer_list(layer.get("children"), f"{path}.children")
        if policy.forbid_deeper_layers and depth >= 1:
            for child_index, child in enumerate(children):
                child_title = _nonempty_string(
                    child.get("title"),
                    f"{path}.children[{child_index}].title",
                )
                issues.append(
                    _issue(
                        "extra_depth",
                        f"{path}.children[{child_index}]",
                        observed=child_title,
                    )
                )
        _walk_layers(
            children,
            f"{path}.children",
            issues,
            policy,
            depth=depth + 1,
        )


def _validate_objects(
    layer: Mapping[str, object],
    path: str,
    *,
    required: list[str],
    allowed: list[str],
    issues: list[SceneClosedWorldIssueV1],
) -> None:
    objects = _object_list(layer.get("objects"), f"{path}.objects")
    names = [
        _nonempty_string(obj.get("name"), f"{path}.objects[{index}].name")
        for index, obj in enumerate(objects)
    ]
    counts = Counter(names)
    for required_name in required:
        if counts[required_name] == 0:
            issues.append(
                _issue("missing_object", f"{path}.objects", expected=required_name)
            )
    allowed_names = set(allowed)
    for index, name in enumerate(names):
        if name not in allowed_names:
            issues.append(
                _issue(
                    "unsupported_object",
                    f"{path}.objects[{index}].name",
                    observed=name,
                )
            )
        elif counts[name] > 1:
            issues.append(
                _issue(
                    "duplicate_object",
                    f"{path}.objects[{index}].name",
                    observed=name,
                )
            )
            counts[name] -= 1


def _validate_entrance(
    layer: Mapping[str, object],
    path: str,
    *,
    allowed: list[str],
    issues: list[SceneClosedWorldIssueV1],
) -> None:
    entrance = _nonempty_string(layer.get("entrance"), f"{path}.entrance")
    if entrance not in set(allowed):
        issues.append(
            _issue(
                "unsupported_entrance",
                f"{path}.entrance",
                expected=" | ".join(allowed),
                observed=entrance,
            )
        )


def _issue(
    code: SceneClosedWorldIssueCode,
    path: str,
    *,
    expected: str | None = None,
    observed: str | None = None,
) -> SceneClosedWorldIssueV1:
    return SceneClosedWorldIssueV1(
        code=code,
        path=path,
        expected=expected,
        observed=observed,
    )
