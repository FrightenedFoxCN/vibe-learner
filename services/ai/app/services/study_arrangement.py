from __future__ import annotations

import math
import re

from app.models.domain import (
    DocumentDebugRecord,
    DocumentPageRecord,
    DocumentRecord,
    DocumentSection,
    LearningGoalInput,
    LearningPlanRecord,
    PersonaProfile,
    StudyScheduleRecord,
    StudyUnitRecord,
)


class StudyArrangementService:
    def build_study_units(
        self, *, document: DocumentRecord, debug_report: DocumentDebugRecord
    ) -> list[StudyUnitRecord]:
        raw_sections = sorted(
            [section for section in debug_report.sections if section.level == 1],
            key=lambda section: (section.page_start, section.page_end, section.id),
        )
        pages_by_number = {page.page_number: page for page in debug_report.pages}
        anchors: list[tuple[DocumentSection, str, str, float]] = []

        for section in raw_sections:
            title, confidence = self._derive_anchor_title(
                section=section,
                pages_by_number=pages_by_number,
            )
            if not title:
                continue
            unit_kind = self._classify_unit_kind(title)
            anchors.append((section, title, unit_kind, confidence))

        if not anchors:
            fallback_title = self._normalize_title(document.title) or "教材内容"
            anchors = [
                (
                    DocumentSection(
                        id=f"{document.id}:study-anchor:1",
                        document_id=document.id,
                        title=fallback_title,
                        page_start=1,
                        page_end=max(1, debug_report.page_count),
                        level=1,
                    ),
                    fallback_title,
                    "chapter",
                    0.45,
                )
            ]

        if anchors[0][0].page_start > 1:
            anchors.insert(
                0,
                (
                    DocumentSection(
                        id=f"{document.id}:study-anchor:front",
                        document_id=document.id,
                        title="Front Matter",
                        page_start=1,
                        page_end=anchors[0][0].page_start - 1,
                        level=1,
                    ),
                    "Front Matter",
                    "front_matter",
                    0.72,
                ),
            )

        deduped_anchors: list[tuple[DocumentSection, str, str, float]] = []
        seen: set[tuple[int, str]] = set()
        for section, title, unit_kind, confidence in anchors:
            key = (section.page_start, title.casefold())
            if key in seen:
                continue
            seen.add(key)
            deduped_anchors.append((section, title, unit_kind, confidence))

        study_units: list[StudyUnitRecord] = []
        for index, (section, title, unit_kind, confidence) in enumerate(deduped_anchors, start=1):
            next_start = (
                deduped_anchors[index][0].page_start - 1
                if index < len(deduped_anchors)
                else debug_report.page_count
            )
            page_start = section.page_start
            page_end = max(page_start, next_start)
            if (
                page_start == 1
                and page_end <= 10
                and title.casefold() in {self._normalize_title(document.title).casefold(), "front matter"}
            ):
                unit_kind = "front_matter"
            if (
                page_start <= 10
                and unit_kind == "chapter"
                and not re.match(r"^(?:\d+(?:\.\d+)*\.?\s+|Chapter\s+|Part\s+|Appendix\s+)", title, re.IGNORECASE)
                and title not in {"Preliminaries"}
            ):
                unit_kind = "front_matter"
            if (
                page_start >= max(1, debug_report.page_count - 5)
                and unit_kind == "chapter"
                and not re.match(r"^\d+(?:\.\d+)*\.?\s+", title)
            ):
                unit_kind = "back_matter"
            include_in_plan = unit_kind == "chapter"
            summary = self._build_unit_summary(
                title=title,
                unit_kind=unit_kind,
                page_start=page_start,
                page_end=page_end,
            )
            study_units.append(
                StudyUnitRecord(
                    id=f"{document.id}:study-unit:{index}",
                    document_id=document.id,
                    title=title,
                    page_start=page_start,
                    page_end=page_end,
                    unit_kind=unit_kind,
                    include_in_plan=include_in_plan,
                    source_section_ids=[section.id],
                    summary=summary,
                    confidence=round(confidence, 2),
                )
            )

        merged_units = self._merge_adjacent_units(document=document, units=study_units)
        if any(unit.include_in_plan for unit in merged_units):
            return merged_units
        if merged_units:
            merged_units[0].unit_kind = "chapter"
            merged_units[0].include_in_plan = True
            merged_units[0].summary = self._build_unit_summary(
                title=merged_units[0].title,
                unit_kind="chapter",
                page_start=merged_units[0].page_start,
                page_end=merged_units[0].page_end,
            )
            return merged_units
        return merged_units

    def build_plan(
        self,
        *,
        goal: LearningGoalInput,
        document: DocumentRecord,
        persona_name: str,
        persona: PersonaProfile | None = None,
    ) -> LearningPlanRecord:
        units = document.study_units or self._fallback_units_from_sections(document)
        plannable_units = [unit for unit in units if unit.include_in_plan] or units
        schedule = self._build_schedule(
            units=plannable_units,
        )
        study_chapters = [unit.title for unit in plannable_units[:4]] or [document.title]
        today_tasks = [
            f"{item.title} · {item.focus}"
            for item in schedule[:3]
        ] or [
            f"阅读 {document.title} 的第一页内容，确认学习目标与术语。",
        ]
        if persona is not None:
            from app.models.domain import persona_slot_content
            enc_style = persona_slot_content(persona, "encouragement_style")
            if enc_style:
                today_tasks = [
                    f"[{enc_style}] {task}"
                    for task in today_tasks
                ]
        # objective stays as learner-authored goal text; overview/course_title are generated display fields.
        persona_hint = ""
        if persona is not None:
            from app.models.domain import persona_narrative_mode_label, persona_slot_content
            narrative_mode = persona_narrative_mode_label(
                persona_slot_content(persona, "narrative_mode", "稳态导学")
            )
            correction_style = persona_slot_content(persona, "correction_style")
            persona_hint = f" \u91c7\u7528{narrative_mode}\u53d9\u4e8b\uff0c\u5e76\u4fdd\u6301{correction_style}\u7684\u53cd\u9988\u8282\u594f\u3002" if correction_style else f" \u91c7\u7528{narrative_mode}\u53d9\u4e8b\u3002"
        overview = (
            f"{persona_name} 将带你完成 {document.title} 的"
            f" {len(plannable_units)} 个学习单元，先从 {plannable_units[0].title if plannable_units else document.title} 开始。"
            f"{persona_hint}"
        )
        course_title = " / ".join(
            [unit.title for unit in plannable_units[:2] if unit.title]
        ) or document.title
        return LearningPlanRecord(
            id="",
            document_id=document.id,
            persona_id=goal.persona_id,
            course_title=course_title,
            objective=goal.objective,
            scene_profile_summary=goal.scene_profile_summary,
            overview=overview,
            study_chapters=study_chapters,
            today_tasks=today_tasks,
            study_units=units,
            schedule=schedule,
            created_at="",
        )

    def _derive_anchor_title(
        self,
        *,
        section: DocumentSection,
        pages_by_number: dict[int, DocumentPageRecord],
    ) -> tuple[str, float]:
        raw_title = self._normalize_title(section.title)
        if self._is_valid_anchor_title(raw_title):
            return raw_title, 0.88

        for page_offset in range(0, 2):
            page = pages_by_number.get(section.page_start + page_offset)
            if page is None:
                continue
            preview_title = self._extract_title_from_preview(page.text_preview)
            if self._is_valid_anchor_title(preview_title):
                return preview_title, 0.74 - (page_offset * 0.08)

            for candidate in page.heading_candidates:
                normalized = self._normalize_title(candidate.text)
                if self._is_valid_anchor_title(normalized):
                    return normalized, min(0.9, max(0.55, candidate.confidence))

        if self._is_backmatter_title(raw_title):
            return raw_title, 0.68
        return "", 0.0

    def _extract_title_from_preview(self, preview: str) -> str:
        lines = self._prepare_preview_lines(preview)
        if not lines:
            return ""

        candidates: list[str] = []
        for index, line in enumerate(lines[:6]):
            candidates.append(line)
            if index + 1 < len(lines):
                candidates.append(f"{line} {lines[index + 1]}")
            if index + 2 < len(lines):
                candidates.append(f"{line} {lines[index + 1]} {lines[index + 2]}")

        for candidate in candidates:
            normalized = self._normalize_title(candidate)
            if self._is_valid_anchor_title(normalized):
                return normalized
        return ""

    def _prepare_preview_lines(self, preview: str) -> list[str]:
        prepared: list[str] = []
        for raw_line in preview.splitlines()[:8]:
            line = self._normalize_title(raw_line)
            if not line:
                continue
            if re.fullmatch(r"[0-9ivxlcdmIVXLCDM]+", line):
                continue
            if re.fullmatch(r"[°•·eE]+", line):
                continue
            if line.casefold().startswith("figure "):
                continue
            prepared.append(line)
        return prepared

    def _normalize_title(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text).strip(" |-_:.")
        normalized = re.sub(r"^\d{1,4}\s+[—-]\s+", "", normalized)
        normalized = re.sub(r"\s+\d{1,4}$", "", normalized)
        normalized = re.sub(r"\s+[ivxlcdmIVXLCDM]+$", "", normalized)
        normalized = re.sub(
            r"^\d+\s+(Preface|Preliminaries|References|Index)\b",
            r"\1",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(r"\bExercises?\b", "Exercises", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bChapter\]\b", "Chapter 1", normalized)
        return normalized.strip()

    def _is_valid_anchor_title(self, title: str) -> bool:
        if not title:
            return False
        lowered = title.casefold()
        if lowered in {"body text", "intro body text"} or lowered.startswith("body text "):
            return False
        if self._looks_like_exercise_prompt(title):
            return False
        if self._looks_like_sentence_title(title):
            return False
        if self._looks_like_gibberish(title):
            return False
        if len(title.split()) > 14:
            return False
        if self._is_backmatter_title(title):
            return True
        if title in {"Front Matter", "Preface", "Preliminaries"}:
            return True
        if re.match(r"^\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z]", title):
            if re.match(r"^\d+\s+[A-Z]{2,}\b", title):
                return False
            return True
        if re.match(r"^(Chapter|Part|Appendix)\s+", title, re.IGNORECASE):
            return True
        if re.match(r"^[A-Z][A-Za-z0-9,'’()\-:?! ]{4,80}$", title):
            return True
        return False

    def _looks_like_exercise_prompt(self, title: str) -> bool:
        lowered = title.casefold()
        if lowered in {"exercise", "exercises", "additional exercise"}:
            return True
        if re.fullmatch(r"\(?\d+(?:\.\d+)*\)?\s*exercises?", title, re.IGNORECASE):
            return True
        if re.match(
            r"^[+\-*o•]?\s*\(?\d+(?:\.\d+)*\)?[.)-]?\s+"
            r"(design|prove|construct|show|explain|formulate|give|draw|let|suppose|referring|without|carry)\b",
            lowered,
        ):
            return True
        if re.match(
            r"^[+\-*o•]?\s*\(?\d+(?:\.\d+)*\)?[.)-]?\s+(for this exercise|in this exercise)\b",
            lowered,
        ):
            return True
        return False

    def _looks_like_gibberish(self, title: str) -> bool:
        if len(title) < 3:
            return True
        alpha_count = sum(char.isalpha() for char in title)
        digit_count = sum(char.isdigit() for char in title)
        symbol_count = sum(not char.isalnum() and not char.isspace() for char in title)
        uppercase_count = sum(char.isupper() for char in title)
        alpha_words = re.findall(r"[A-Za-z][A-Za-z'’\-]+", title)
        if alpha_count == 0 and digit_count == 0:
            return True
        if title.endswith((",", ";", ":")):
            return True
        if symbol_count > max(4, len(title) * 0.12):
            return True
        if digit_count > alpha_count and alpha_count < 4:
            return True
        if len(alpha_words) < 2 and not self._is_backmatter_title(title):
            return True
        if uppercase_count > max(4, alpha_count * 0.75) and alpha_count > 6 and digit_count > 0:
            return True
        if re.search(r"[{}\\<>~=]{2,}", title):
            return True
        if re.match(r"^[A-Za-z]\)\s", title):
            return True
        if re.match(r"^\d{2,4}\s+[A-Z][a-z]+(?:\.\s+[A-Z][a-z]+)?", title):
            return True
        if title.casefold() in {"0 lr", "0 1 b"}:
            return True
        return False

    def _looks_like_sentence_title(self, title: str) -> bool:
        words = re.findall(r"[A-Za-z][A-Za-z'’\-]*", title)
        if len(words) < 7:
            return False
        capitalized = sum(1 for word in words if word[:1].isupper())
        if capitalized >= math.ceil(len(words) * 0.65):
            return False
        lowered = title.casefold()
        if lowered.startswith(("to ", "if ", "suppose ", "note ", "we ", "then ")):
            return True
        return True

    def _is_backmatter_title(self, title: str) -> bool:
        lowered = title.casefold()
        return any(
            token in lowered
            for token in ("solutions", "references", "bibliography", "index")
        )

    def _classify_unit_kind(self, title: str) -> str:
        lowered = title.casefold()
        if lowered == "front matter" or lowered in {"contents", "preface"}:
            return "front_matter"
        if "solutions" in lowered:
            return "solutions"
        if any(token in lowered for token in ("references", "bibliography", "index")):
            return "back_matter"
        return "chapter"

    def _build_unit_summary(
        self, *, title: str, unit_kind: str, page_start: int, page_end: int
    ) -> str:
        if unit_kind == "chapter":
            return f"聚焦 {title}，覆盖教材第 {page_start}-{page_end} 页。"
        if unit_kind == "solutions":
            return f"{title} 位于教材第 {page_start}-{page_end} 页，默认不进入主学习排期。"
        if unit_kind == "back_matter":
            return f"{title} 属于附录/索引类内容，位于教材第 {page_start}-{page_end} 页。"
        return f"{title} 位于教材第 {page_start}-{page_end} 页。"

    def _build_schedule(
        self,
        *,
        units: list[StudyUnitRecord],
    ) -> list[StudyScheduleRecord]:
        schedule: list[StudyScheduleRecord] = []

        for index, unit in enumerate(units, start=1):
            schedule.append(
                StudyScheduleRecord(
                    id=f"schedule-{index * 2 - 1}",
                    unit_id=unit.id,
                    title=f"{unit.title} 精读",
                    focus=f"完成 {unit.title} 的首轮理解，标出定义、定理与例子。",
                    activity_type="learn",
                )
            )

            schedule.append(
                StudyScheduleRecord(
                    id=f"schedule-{index * 2}",
                    unit_id=unit.id,
                    title=f"{unit.title} 回顾",
                    focus=f"复述 {unit.title}，补一条错因或例题笔记。",
                    activity_type="review",
                )
            )

        return schedule

    def _fallback_units_from_sections(self, document: DocumentRecord) -> list[StudyUnitRecord]:
        if document.study_units:
            return document.study_units
        return [
            StudyUnitRecord(
                id=f"{document.id}:study-unit:fallback:{index}",
                document_id=document.id,
                title=section.title,
                page_start=section.page_start,
                page_end=section.page_end,
                source_section_ids=[section.id],
                summary=f"聚焦 {section.title}，覆盖教材第 {section.page_start}-{section.page_end} 页。",
                confidence=0.5,
            )
            for index, section in enumerate(document.sections, start=1)
        ]

    def _merge_adjacent_units(
        self, *, document: DocumentRecord, units: list[StudyUnitRecord]
    ) -> list[StudyUnitRecord]:
        if not units:
            return units

        merged: list[StudyUnitRecord] = []
        for unit in units:
            if not merged:
                merged.append(unit)
                continue

            previous = merged[-1]
            should_merge = (
                self._canonical_title(previous.title) == self._canonical_title(unit.title)
                or (previous.unit_kind == unit.unit_kind == "front_matter")
                or (previous.unit_kind == unit.unit_kind == "back_matter")
            )
            if not should_merge:
                merged.append(unit)
                continue

            previous.page_end = max(previous.page_end, unit.page_end)
            previous.source_section_ids.extend(unit.source_section_ids)
            previous.source_section_ids = list(dict.fromkeys(previous.source_section_ids))
            previous.confidence = round(max(previous.confidence, unit.confidence), 2)
            if previous.unit_kind in {"front_matter", "back_matter"}:
                previous.title = "Front Matter" if previous.unit_kind == "front_matter" else previous.title
                previous.include_in_plan = False
                previous.summary = self._build_unit_summary(
                    title=previous.title,
                    unit_kind=previous.unit_kind,
                    page_start=previous.page_start,
                    page_end=previous.page_end,
                )

        for index, unit in enumerate(merged, start=1):
            unit.id = f"{document.id}:study-unit:{index}"
        return merged

    def _canonical_title(self, title: str) -> str:
        normalized = self._normalize_title(title)
        normalized = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", normalized)
        return normalized.casefold()
