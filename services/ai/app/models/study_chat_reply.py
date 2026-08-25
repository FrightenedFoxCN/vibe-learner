from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.study_question import StudyQuestionProposalV1


class StudyChatRichBlockProposalV1(BaseModel):
    """Model-owned rich-text block before application projection."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=40_000)

    @field_validator("kind", "content", mode="before")
    @classmethod
    def require_bounded_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("study_chat_reply_string_required")
        return value.strip()


class StudyChatReplyProposalV1(BaseModel):
    """Strict model-owned Study Chat response; it owns no committed state."""

    model_config = ConfigDict(extra="forbid", strict=True)

    text: str = Field(min_length=1, max_length=40_000)
    mood: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=2_000)
    speech_style: str = Field(default="", max_length=500)
    delivery_cue: str = Field(default="", max_length=2_000)
    state_commentary: str = Field(default="", max_length=4_000)
    rich_blocks: list[StudyChatRichBlockProposalV1] = Field(
        default_factory=list,
        max_length=32,
    )
    interactive_question: StudyQuestionProposalV1 | None = None

    @field_validator(
        "text",
        "mood",
        "action",
        "speech_style",
        "delivery_cue",
        "state_commentary",
        mode="before",
    )
    @classmethod
    def require_bounded_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("study_chat_reply_string_required")
        return value.strip()

    @field_validator("interactive_question", mode="before")
    @classmethod
    def require_strict_question_payload(cls, value: object) -> object:
        """Keep the nested model proposal strict at this provider boundary.

        ``StudyQuestionProposalV1`` is also fed application-built question-tool
        results and has intentionally tolerant text normalizers.  A fresh model
        reply must not inherit those coercions (for example, integer option text
        or a string ``call_back`` flag).
        """

        if value is None or isinstance(value, StudyQuestionProposalV1):
            return value
        if not isinstance(value, dict):
            raise ValueError("study_chat_question_object_required")

        string_fields = (
            "schema_version",
            "question_type",
            "prompt",
            "difficulty",
            "topic",
            "explanation",
        )
        for field_name in string_fields:
            if field_name in value and not isinstance(value[field_name], str):
                raise ValueError(f"study_chat_question_{field_name}_string_required")

        if "call_back" in value and not isinstance(value["call_back"], bool):
            raise ValueError("study_chat_question_call_back_boolean_required")
        if "answer_key" in value and value["answer_key"] is not None and not isinstance(
            value["answer_key"], str
        ):
            raise ValueError("study_chat_question_answer_key_string_required")

        if "accepted_answers" in value:
            accepted_answers = value["accepted_answers"]
            if not isinstance(accepted_answers, list) or any(
                not isinstance(item, str) for item in accepted_answers
            ):
                raise ValueError("study_chat_question_accepted_answers_strings_required")

        if "options" in value:
            options = value["options"]
            if not isinstance(options, list):
                raise ValueError("study_chat_question_options_list_required")
            for option in options:
                if not isinstance(option, dict):
                    raise ValueError("study_chat_question_option_object_required")
                for field_name in ("key", "text"):
                    if field_name in option and not isinstance(option[field_name], str):
                        raise ValueError(
                            f"study_chat_question_option_{field_name}_string_required"
                        )
        return value
