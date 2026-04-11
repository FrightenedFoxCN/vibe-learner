from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "prompts" / "study_session_prompt.txt"


@dataclass(frozen=True)
class StudySessionPromptTemplate:
    system_prompt: str


def build_study_session_system_prompt(
    *,
    persona_name: str,
    persona_system_prompt: str,
    document_title: str,
    section_id: str,
    section_title: str,
    theme_hint: str,
    scene_profile_summary: str = "",
) -> str:
    template = load_study_session_prompt_template().system_prompt
    return (
        template.replace("{{PERSONA_SYSTEM_PROMPT}}", persona_system_prompt.strip())
        .replace("{{PERSONA_NAME}}", persona_name.strip())
        .replace("{{DOCUMENT_TITLE}}", document_title.strip())
        .replace("{{SECTION_ID}}", section_id.strip())
        .replace("{{SECTION_TITLE}}", section_title.strip())
        .replace("{{THEME_HINT}}", theme_hint.strip() or "N/A")
        .replace("{{SCENE_PROFILE_SUMMARY}}", scene_profile_summary.strip() or "N/A")
    )


@lru_cache(maxsize=1)
def load_study_session_prompt_template() -> StudySessionPromptTemplate:
    raw_text = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    sections = _parse_prompt_sections(raw_text)
    system_prompt = sections.get("system", "").strip()
    if not system_prompt:
        raise RuntimeError("study_session_prompt_missing_system_section")
    return StudySessionPromptTemplate(system_prompt=system_prompt)


def _parse_prompt_sections(raw_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_section: str | None = None
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].strip().lower()
            sections.setdefault(current_section, [])
            continue
        if current_section is None:
            continue
        sections[current_section].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}