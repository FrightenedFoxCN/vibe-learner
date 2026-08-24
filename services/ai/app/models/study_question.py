from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


STUDY_QUESTION_PROPOSAL_SCHEMA_VERSION = "study-question-proposal-v1"
STUDY_QUESTION_GRADING_SCHEMA_VERSION = "study-question-grading-v1"
STUDY_QUESTION_RECORD_SCHEMA_VERSION = "study-interactive-question-v2"
STUDY_QUESTION_RESULT_SCHEMA_VERSION = "study-question-result-v1"
STUDY_QUESTION_ATTEMPT_REQUEST_SCHEMA_VERSION = "study-question-attempt-request-v1"
STUDY_QUESTION_ATTEMPT_FINGERPRINT_VERSION = "study-question-attempt-fingerprint-v1"
STUDY_QUESTION_ATTEMPT_RESPONSE_SCHEMA_VERSION = "study-question-attempt-response-v1"
STUDY_QUESTION_NORMALIZATION_POLICY_VERSION = "unicode-nfkc-casefold-whitespace-v1"

StudyQuestionType = Literal["multiple_choice", "fill_blank"]
StudyQuestionDifficulty = Literal["easy", "medium", "hard"]


class StudyQuestionOptionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=16)
    text: str = Field(min_length=1, max_length=2_000)

    @field_validator("key", "text", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> str:
        return str(value or "").strip()


class StudyQuestionProposalV1(BaseModel):
    """Strict model-owned question content. It never owns Turn/attempt state."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["study-question-proposal-v1"] = (
        STUDY_QUESTION_PROPOSAL_SCHEMA_VERSION
    )
    question_type: StudyQuestionType
    prompt: str = Field(min_length=1, max_length=8_000)
    difficulty: StudyQuestionDifficulty = "medium"
    topic: str = Field(default="", max_length=500)
    options: list[StudyQuestionOptionV1] = Field(default_factory=list, max_length=8)
    call_back: bool = False
    answer_key: str | None = Field(default=None, max_length=64)
    accepted_answers: list[str] = Field(default_factory=list, max_length=16)
    explanation: str = Field(default="", max_length=8_000)

    @field_validator("prompt", "topic", "explanation", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("answer_key", mode="before")
    @classmethod
    def normalize_optional_answer_key(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("accepted_answers", mode="before")
    @classmethod
    def normalize_answer_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("study_question_accepted_answers_list_required")
        answers = [str(item or "").strip() for item in value]
        return [answer for answer in answers if answer]

    @model_validator(mode="after")
    def validate_question_contract(self) -> "StudyQuestionProposalV1":
        if self.question_type == "multiple_choice":
            if len(self.options) < 2:
                raise ValueError("study_question_multiple_choice_options_required")
            normalized_keys = [normalize_study_answer(option.key) for option in self.options]
            if len(normalized_keys) != len(set(normalized_keys)):
                raise ValueError("study_question_option_key_duplicate")
            if self.answer_key is None:
                raise ValueError("study_question_answer_key_required")
            if normalize_study_answer(self.answer_key) not in normalized_keys:
                raise ValueError("study_question_answer_key_unknown")
        else:
            answers = [*self.accepted_answers]
            if self.answer_key:
                answers.append(self.answer_key)
            if not answers:
                raise ValueError("study_question_fill_blank_answers_required")
            if self.options:
                raise ValueError("study_question_fill_blank_options_forbidden")
        return self


class StudyQuestionGradingSpecV1(BaseModel):
    """Server-only grading material persisted with the committed Turn."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["study-question-grading-v1"] = (
        STUDY_QUESTION_GRADING_SCHEMA_VERSION
    )
    question_type: StudyQuestionType
    correct_option_key: str | None = Field(default=None, max_length=64)
    accepted_answers: list[str] = Field(default_factory=list, max_length=16)
    explanation: str = Field(default="", max_length=8_000)
    normalization_policy: Literal["unicode-nfkc-casefold-whitespace-v1"] = (
        STUDY_QUESTION_NORMALIZATION_POLICY_VERSION
    )

    @model_validator(mode="after")
    def validate_grading_contract(self) -> "StudyQuestionGradingSpecV1":
        if self.question_type == "multiple_choice":
            if not self.correct_option_key or self.accepted_answers:
                raise ValueError("study_question_multiple_choice_grading_invalid")
        elif self.correct_option_key is not None or not self.accepted_answers:
            raise ValueError("study_question_fill_blank_grading_invalid")
        return self


class StudyQuestionResultRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["study-question-result-v1"] = (
        STUDY_QUESTION_RESULT_SCHEMA_VERSION
    )
    attempt_id: str = Field(default="", max_length=64)
    client_attempt_id: str = Field(default="", max_length=80)
    submitted_answer: str = Field(min_length=1, max_length=8_000)
    normalized_answer: str = Field(min_length=1, max_length=8_000)
    is_correct: bool
    feedback_text: str = Field(min_length=1, max_length=10_000)
    explanation: str = Field(default="", max_length=8_000)
    before_revision: int | None = Field(default=None, ge=0)
    committed_revision: int | None = Field(default=None, ge=1)
    committed_at: str = ""


class StudyInteractiveQuestionRecordV2(BaseModel):
    """Committed private question record stored inside a Study Session Turn."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["study-interactive-question-v2"] = (
        STUDY_QUESTION_RECORD_SCHEMA_VERSION
    )
    question_type: StudyQuestionType
    prompt: str = Field(min_length=1, max_length=8_000)
    difficulty: StudyQuestionDifficulty = "medium"
    topic: str = Field(default="", max_length=500)
    options: list[StudyQuestionOptionV1] = Field(default_factory=list, max_length=8)
    call_back: bool = False
    grading_spec: StudyQuestionGradingSpecV1 | None = None
    result: StudyQuestionResultRecordV1 | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_question(cls, value: Any) -> Any:
        if (
            not isinstance(value, dict)
            or value.get("schema_version") is not None
            or "grading_spec" in value
            or "result" in value
        ):
            return value
        payload = dict(value)
        question_type = str(payload.get("question_type") or "")
        answer_key = str(payload.pop("answer_key", "") or "").strip()
        accepted_answers = [
            str(item or "").strip()
            for item in payload.pop("accepted_answers", []) or []
            if str(item or "").strip()
        ]
        explanation = str(payload.pop("explanation", "") or "").strip()
        submitted_answer = str(payload.pop("submitted_answer", "") or "").strip()
        is_correct = payload.pop("is_correct", None)
        feedback_text = str(payload.pop("feedback_text", "") or "").strip()

        grading_spec: dict[str, Any] | None = None
        if question_type == "multiple_choice" and answer_key:
            grading_spec = {
                "question_type": question_type,
                "correct_option_key": answer_key,
                "accepted_answers": [],
                "explanation": explanation,
            }
        elif question_type == "fill_blank" and (accepted_answers or answer_key):
            grading_spec = {
                "question_type": question_type,
                "correct_option_key": None,
                "accepted_answers": _deduplicate_answers(
                    [*accepted_answers, *([answer_key] if answer_key else [])]
                ),
                "explanation": explanation,
            }

        result: dict[str, Any] | None = None
        if submitted_answer and isinstance(is_correct, bool) and feedback_text:
            result = {
                "submitted_answer": submitted_answer,
                "normalized_answer": normalize_study_answer(submitted_answer),
                "is_correct": is_correct,
                "feedback_text": feedback_text,
                "explanation": explanation,
            }

        payload.update(
            {
                "schema_version": STUDY_QUESTION_RECORD_SCHEMA_VERSION,
                "grading_spec": grading_spec,
                "result": result,
            }
        )
        return payload

    @model_validator(mode="after")
    def validate_record_contract(self) -> "StudyInteractiveQuestionRecordV2":
        if self.grading_spec is not None and self.grading_spec.question_type != self.question_type:
            raise ValueError("study_question_grading_type_mismatch")
        if self.question_type == "multiple_choice" and len(self.options) < 2:
            # Legacy persisted questions without options remain readable only if
            # they also lack grading material and therefore cannot be submitted.
            if self.grading_spec is not None:
                raise ValueError("study_question_multiple_choice_options_required")
        if self.question_type == "fill_blank" and self.options:
            raise ValueError("study_question_fill_blank_options_forbidden")
        return self


class StudyQuestionResultResponseV1(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: Literal["study-question-result-v1"] = (
        STUDY_QUESTION_RESULT_SCHEMA_VERSION
    )
    attempt_id: str | None = None
    client_attempt_id: str | None = None
    submitted_answer: str
    is_correct: bool
    feedback_text: str
    explanation: str = ""
    before_revision: int | None = None
    committed_revision: int | None = None
    committed_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def project_internal_result(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        payload.pop("normalized_answer", None)
        payload["attempt_id"] = str(payload.get("attempt_id") or "") or None
        payload["client_attempt_id"] = str(payload.get("client_attempt_id") or "") or None
        payload["committed_at"] = str(payload.get("committed_at") or "") or None
        return payload


class StudyQuestionPromptResponseV1(BaseModel):
    """Public prompt/result projection. Grading material never appears here."""

    model_config = ConfigDict(extra="ignore")

    schema_version: Literal["study-interactive-question-v2"] = (
        STUDY_QUESTION_RECORD_SCHEMA_VERSION
    )
    question_type: StudyQuestionType
    prompt: str
    difficulty: StudyQuestionDifficulty
    topic: str
    options: list[StudyQuestionOptionV1]
    call_back: bool
    result: StudyQuestionResultResponseV1 | None


class StudyQuestionAttemptRequestPayloadV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["study-question-attempt-request-v1"] = (
        STUDY_QUESTION_ATTEMPT_REQUEST_SCHEMA_VERSION
    )
    turn_id: str = Field(min_length=1, max_length=64)
    expected_session_revision: int = Field(ge=0)
    normalized_answer: str = Field(min_length=1, max_length=8_000)


class StudyQuestionAttemptResponseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["study-question-attempt-response-v1"] = (
        STUDY_QUESTION_ATTEMPT_RESPONSE_SCHEMA_VERSION
    )
    attempt_id: str = Field(min_length=1, max_length=64)
    client_attempt_id: str = Field(min_length=8, max_length=80)
    session_id: str = Field(min_length=1, max_length=64)
    turn_id: str = Field(min_length=1, max_length=64)
    submitted_answer: str = Field(min_length=1, max_length=8_000)
    is_correct: bool
    feedback_text: str = Field(min_length=1, max_length=10_000)
    explanation: str = Field(default="", max_length=8_000)
    before_revision: int = Field(ge=0)
    committed_revision: int = Field(ge=1)
    committed_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_revision(self) -> "StudyQuestionAttemptResponseV1":
        if self.committed_revision != self.before_revision + 1:
            raise ValueError("study_question_attempt_revision_invalid")
        return self


def project_study_question_proposal(
    proposal: StudyQuestionProposalV1,
) -> StudyInteractiveQuestionRecordV2:
    if proposal.question_type == "multiple_choice":
        assert proposal.answer_key is not None
        normalized_answer_key = normalize_study_answer(proposal.answer_key)
        correct_key = next(
            option.key
            for option in proposal.options
            if normalize_study_answer(option.key) == normalized_answer_key
        )
        grading = StudyQuestionGradingSpecV1(
            question_type=proposal.question_type,
            correct_option_key=correct_key,
            accepted_answers=[],
            explanation=proposal.explanation,
        )
    else:
        grading = StudyQuestionGradingSpecV1(
            question_type=proposal.question_type,
            correct_option_key=None,
            accepted_answers=_deduplicate_answers(
                [
                    *proposal.accepted_answers,
                    *([proposal.answer_key] if proposal.answer_key else []),
                ]
            ),
            explanation=proposal.explanation,
        )
    return StudyInteractiveQuestionRecordV2(
        question_type=proposal.question_type,
        prompt=proposal.prompt,
        difficulty=proposal.difficulty,
        topic=proposal.topic,
        options=proposal.options,
        call_back=proposal.call_back,
        grading_spec=grading,
        result=None,
    )


def grade_study_question(
    question: StudyInteractiveQuestionRecordV2,
    submitted_answer: str,
) -> tuple[str, bool, str, str]:
    grading = question.grading_spec
    if grading is None:
        raise ValueError("study_question_grading_unavailable")
    answer = submitted_answer.strip()
    normalized = normalize_study_answer(answer)
    if not normalized:
        raise ValueError("study_question_answer_empty")
    if question.question_type == "multiple_choice":
        assert grading.correct_option_key is not None
        is_correct = normalized == normalize_study_answer(grading.correct_option_key)
        reference = grading.correct_option_key
        feedback = "回答正确" if is_correct else f"回答不正确，正确答案是 {reference}"
    else:
        accepted = {
            normalize_study_answer(candidate) for candidate in grading.accepted_answers
        }
        is_correct = normalized in accepted
        reference = " / ".join(grading.accepted_answers)
        feedback = "回答正确" if is_correct else f"回答不正确，参考答案：{reference}"
    return normalized, is_correct, feedback, grading.explanation


def study_question_attempt_fingerprint(
    payload: StudyQuestionAttemptRequestPayloadV1,
) -> str:
    canonical = {
        "contract": STUDY_QUESTION_ATTEMPT_FINGERPRINT_VERSION,
        "request": payload.model_dump(mode="json"),
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def study_question_attempt_response_digest(
    response: StudyQuestionAttemptResponseV1,
) -> str:
    encoded = json.dumps(
        response.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_study_answer(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return re.sub(r"\s+", " ", normalized)


def _deduplicate_answers(values: list[str]) -> list[str]:
    answers: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = str(value or "").strip()
        normalized = normalize_study_answer(stripped)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        answers.append(stripped)
    return answers
