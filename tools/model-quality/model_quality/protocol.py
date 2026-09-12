"""Frozen controlled research fixtures. No credentials or private user artifacts."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[int, Field(strict=True, gt=0)]
Identifier = Annotated[str, Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$')]


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Case(Strict):
    id: Identifier
    family: Identifier
    lane: Identifier
    split: Literal['development', 'confirmation', 'reserved'] = 'development'
    provenance: Literal['synthetic-authored', 'public-licensed', 'user-provided']
    source: Annotated[str, Field(min_length=1, max_length=20000)]
    request: Annotated[str, Field(min_length=1, max_length=4000)]
    gold: Annotated[str, Field(min_length=1, max_length=20000)]
    rubric: Identifier


class Variant(Strict):
    id: Identifier
    instruction: Annotated[str, Field(min_length=1, max_length=4000)]


class Budget(Strict):
    # One persistent ledger per resource window, shared by every campaign.
    token_limit: Positive
    wire_limit: Positive
    rpm: Positive
    tpm: Positive
    max_inflight: Positive
    expires_at: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    stop_buffer_seconds: Annotated[int, Field(strict=True, ge=0)] = 900


class Autoscale(Strict):
    min_concurrency: Positive = 1
    max_concurrency: Annotated[int, Field(strict=True, gt=0, le=64)] = 8
    window_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 60.0
    min_completed: Positive = 30
    healthy_windows: Annotated[int, Field(strict=True, ge=2)] = 2
    p95_multiplier: Annotated[float, Field(ge=1, le=2, allow_inf_nan=False)] = 1.25
    max_error_rate: Annotated[float, Field(ge=0, le=.05, allow_inf_nan=False)] = .05


class EvidenceReference(Strict):
    path: Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]+\.json$')]
    contract: Identifier
    # Adapter-owned evidence reference, never a fabricated Harness identity.


class AdapterResult(Strict):
    status: Literal['completed', 'candidate_failed', 'data_failed', 'grader_failed', 'metric_failed', 'infrastructure_failed', 'uncertain']
    failure_owner: Literal['candidate', 'data', 'grader', 'metric', 'infrastructure'] | None = None
    error_code: Identifier | None = None
    metrics: dict[Identifier, bool | int | float | None] = Field(default_factory=dict)
    scope: Literal['provider-proposal-only; no domain admission, commit or read-back', 'domain-primary-output-readback'] = 'provider-proposal-only; no domain admission, commit or read-back'
    evidence: list[EvidenceReference] = Field(default_factory=list)

    @model_validator(mode='after')
    def owner_matches(self):
        owner = None if self.status == 'completed' else 'infrastructure' if self.status == 'uncertain' else self.status.removesuffix('_failed')
        if self.scope == 'domain-primary-output-readback' and not self.evidence:
            raise ValueError('domain evidence reference required')
        if self.failure_owner != owner:
            raise ValueError('failure ownership mismatch')
        return self


class Campaign(Strict):
    version: Literal['quality-campaign-v1']
    id: Identifier
    purpose: Annotated[str, Field(min_length=1, max_length=1000)]
    transport: Literal['fake', 'minimax'] = 'fake'
    model: Literal['MiniMax-M3'] = 'MiniMax-M3'
    adapter: Annotated[str, Field(pattern=r'^[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*:[a-zA-Z_]\w*$')] = 'model_quality.adapters:text_probe'
    autoscale: Autoscale | None = None
    repetitions: Annotated[int, Field(strict=True, gt=0, le=30)] = 1
    seed: int = 0
    concurrency: Annotated[int, Field(strict=True, gt=0, le=64)] = 4
    timeout_seconds: Annotated[int, Field(strict=True, gt=0, le=300)] = 90
    sample_deadline_seconds: Annotated[int, Field(strict=True, gt=0, le=3600)] = 180
    sample_wire_limit: Positive = 1
    max_output_tokens: Positive = 256
    max_inline_images: Annotated[int, Field(strict=True, ge=0, le=4)] = 0
    max_inline_image_bytes: Annotated[int, Field(strict=True, ge=1, le=524288)] = 32768
    max_inline_image_dimension: Annotated[int, Field(strict=True, ge=1, le=2048)] = 1024
    # Operational reservation, NOT an unverified provider billing guarantee.
    input_reservation_tokens: Positive = 4096
    temperature: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 0.1
    thinking: Literal['disabled', 'adaptive'] = 'disabled'
    budget: Budget
    cases: Annotated[list[Case], Field(min_length=1, max_length=10000)]
    variants: Annotated[list[Variant], Field(min_length=1, max_length=10)]

    @model_validator(mode='after')
    def validate_matrix(self):
        if self.autoscale:
            a = self.autoscale
            if not a.min_concurrency <= self.concurrency <= a.max_concurrency <= self.budget.max_inflight:
                raise ValueError('invalid autoscale concurrency bounds')
            if self.transport == 'minimax' and (a.window_seconds < 60 or a.min_completed < 30):
                raise ValueError('live autoscale needs at least 60 seconds and 30 completions per window')
        for values in (self.cases, self.variants):
            if len({item.id for item in values}) != len(values):
                raise ValueError('duplicate identity')
        if any(case.split == 'reserved' for case in self.cases):
            raise ValueError('reserved cases cannot be dispatched')
        if self.input_reservation_tokens + self.max_output_tokens > self.budget.tpm:
            raise ValueError('one reservation exceeds TPM')
        if self.sample_deadline_seconds <= self.timeout_seconds:
            raise ValueError('sample deadline must exceed wire timeout')
        return self

    def samples(self):
        # Randomized AB/BA inside each paired block; repeats remain one family.
        import random
        blocks = [(c, r) for c in self.cases for r in range(self.repetitions)]
        rng = random.Random(self.seed)
        rng.shuffle(blocks)
        for case, repetition in blocks:
            variants = list(self.variants)
            rng.shuffle(variants)
            for variant in variants:
                identity = {'campaign': self.id, 'case': case.id,
                            'variant': variant.id, 'repetition': repetition}
                yield digest(identity), identity, case, variant
