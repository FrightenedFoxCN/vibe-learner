from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROMPTS_ROOT = Path(__file__).resolve().parents[1] / "prompts"


@dataclass(frozen=True)
class PromptTemplate:
    sections: dict[str, str]

    def require(self, name: str) -> str:
        value = self.sections.get(name, "").strip()
        if not value:
            raise RuntimeError(f"prompt_missing_section:{name}")
        return value

    def optional(self, name: str, default: str = "") -> str:
        return self.sections.get(name, "").strip() or default

    def render(self, name: str, replacements: dict[str, str]) -> str:
        content = self.require(name)
        for key, value in replacements.items():
            content = content.replace(f"{{{{{key}}}}}", value)
        return content


@lru_cache(maxsize=32)
def load_prompt_template(filename: str) -> PromptTemplate:
    path = PROMPTS_ROOT / filename
    raw_text = path.read_text(encoding="utf-8")
    return PromptTemplate(sections=_parse_prompt_sections(raw_text))


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
