"""Application-owned language preferences; source quotations stay unchanged."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, Field


def _validate_language(value: str) -> str:
    if value.casefold() == "unknown":
        raise ValueError("output_language_unknown_is_not_a_preference")
    return "auto" if value.casefold() == "auto" else value


OutputLanguagePreference = Annotated[
    str,
    Field(
        strict=True,
        min_length=2,
        max_length=35,
        pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$",
    ),
    AfterValidator(_validate_language),
]
