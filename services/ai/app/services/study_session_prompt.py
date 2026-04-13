from __future__ import annotations

from dataclasses import dataclass

from app.models.domain import SceneProfileRecord
from app.services.prompt_loader import load_prompt_template


@dataclass(frozen=True)
class StudySessionPromptTemplate:
    system_prompt: str


def build_study_session_system_prompt(
    *,
    persona_name: str,
    persona_relationship: str,
    persona_learner_address: str,
    document_title: str,
    study_unit_id: str,
    study_unit_title: str,
    theme_hint: str,
    scene_profile: SceneProfileRecord | None = None,
) -> str:
    template = load_study_session_prompt_template().system_prompt
    scene_summary = scene_profile.summary.strip() if scene_profile else ""
    scene_title = scene_profile.title.strip() if scene_profile else ""
    scene_path = " > ".join(scene_profile.selected_path) if scene_profile else ""
    scene_focus_objects = ", ".join(scene_profile.focus_object_names) if scene_profile else ""
    scene_tags = ", ".join(scene_profile.tags) if scene_profile else ""
    scene_tree_roots = ", ".join(node.title for node in scene_profile.scene_tree[:4]) if scene_profile else ""
    return (
        template.replace("{{PERSONA_NAME}}", persona_name.strip())
        .replace("{{PERSONA_RELATIONSHIP}}", persona_relationship.strip() or "无")
        .replace("{{PERSONA_LEARNER_ADDRESS}}", persona_learner_address.strip() or "无")
        .replace("{{DOCUMENT_TITLE}}", document_title.strip())
        .replace("{{STUDY_UNIT_ID}}", study_unit_id.strip())
        .replace("{{STUDY_UNIT_TITLE}}", study_unit_title.strip())
        .replace("{{THEME_HINT}}", theme_hint.strip() or "无")
        .replace("{{SCENE_PROFILE_SUMMARY}}", scene_summary or "无")
        .replace("{{SCENE_PROFILE_TITLE}}", scene_title or "无")
        .replace("{{SCENE_PROFILE_PATH}}", scene_path or "无")
        .replace("{{SCENE_PROFILE_FOCUS_OBJECTS}}", scene_focus_objects or "无")
        .replace("{{SCENE_PROFILE_TAGS}}", scene_tags or "无")
        .replace("{{SCENE_PROFILE_TREE_ROOTS}}", scene_tree_roots or "无")
    )


def load_study_session_prompt_template() -> StudySessionPromptTemplate:
    prompt = load_prompt_template("study_session_prompt.txt")
    system_prompt = prompt.require("system")
    if not system_prompt:
        raise RuntimeError("study_session_prompt_missing_system_section")
    return StudySessionPromptTemplate(system_prompt=system_prompt)
