"""Resolve application language policy without translating source evidence."""

from __future__ import annotations


def plan_output_language(plan) -> str:
    if plan is None:
        return "auto"
    explicit = plan.planning_intent.output_language
    if explicit.status == "user_explicit":
        return explicit.value or "auto"
    return (
        plan.output_language if plan.output_language.casefold() != "unknown" else "auto"
    )


def output_language_instruction(preference: str, *, plan=None) -> str:
    language = plan_output_language(plan) if preference == "auto" else preference
    policy = (
        "Use the same language as the learner's current goal/message; if unclear, use the textbook's main language, then the Persona's language."
        if language == "auto"
        else f"Use {language} for learner-facing explanations, guidance, tasks, questions and feedback. This application preference overrides the product interface language and Persona style."
    )
    return (
        f"Application output language (output-language-v1): {language}\n"
        f"{policy} Preserve source quotations, textbook excerpts, proper names, formulas and symbols verbatim; do not translate or rewrite evidence."
    )
