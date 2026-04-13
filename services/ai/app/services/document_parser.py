from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import fitz

from app.core.logging import get_logger
from app.models.domain import (
    DocumentChunkRecord,
    DocumentDebugRecord,
    DocumentPageRecord,
    DocumentSection,
    HeadingCandidate,
    ParseWarning,
)
from app.services.ocr_engine import OcrPageResult, OnnxtrOcrEngine

HEADING_PATTERNS = [
    re.compile(r"^(chapter|section|part|appendix)\s+\d+", re.IGNORECASE),
    re.compile(r"^第[一二三四五六七八九十百0-9]+[章节讲部分]"),
    re.compile(r"^[0-9]+(\.[0-9]+)*\s+\S+"),
]

OCR_HEADER_PATTERNS = [
    re.compile(
        r"^(Chapter\s+\d+[A-Za-z]?(?:[:.\-]\s*|\s+)[A-Z][A-Za-z0-9,'’()\- ]{3,90}?)(?=\s+\d{1,4}\b|$)"
    ),
    re.compile(
        r"^(\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z0-9,'’()\- ]{3,90}?)(?=\s+\d{1,4}\b|$)"
    ),
    re.compile(
        r"^(Solutions\s+for\s+Chapter\s+\d+)(?=\s+\d{1,4}\b|$)",
        re.IGNORECASE,
    ),
]

TEXT_DENSITY_THRESHOLD = 40
OCR_LANGUAGE_HINT = "multilingual"
TOC_MAX_LEVEL = 2
MIN_GOOD_TOC_ENTRIES = 6
CHUNK_TARGET_CHARS = 1100
CHUNK_MAX_CHARS = 1400
CHUNK_MIN_CHARS = 500
MARGIN_SCAN_LINES = 3
MARGIN_MIN_REPEAT = 4
logger = get_logger("vibe_learner.parser")


@dataclass(slots=True)
class ParsedPage:
    page_number: int
    line_entries: list[tuple[str, float]]
    dominant_font_size: float
    extraction_source: str
    warnings: list[ParseWarning]
    used_ocr: bool
    ocr_result: OcrPageResult | None = None


class DocumentParser:
    def __init__(
        self,
        runtime_temp_root: Path | None = None,
        *,
        ocr_engine_name: str = "onnxtr",
        onnxtr_model_dir: str = "",
    ) -> None:
        self.runtime_temp_root = runtime_temp_root
        self.ocr_engine_name = ocr_engine_name.strip().lower() or "onnxtr"
        self.ocr_engine = (
            OnnxtrOcrEngine(runtime_temp_root=runtime_temp_root, model_dir=onnxtr_model_dir)
            if self.ocr_engine_name == "onnxtr"
            else None
        )

    def parse(
        self,
        *,
        document_id: str,
        title: str,
        stored_path: str,
        force_ocr: bool = False,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
        interrupt_check: Callable[[], None] | None = None,
    ) -> DocumentDebugRecord:
        _call_interrupt(interrupt_check)
        pdf = fitz.open(stored_path)
        parsed_pages: list[ParsedPage] = []
        pages: list[DocumentPageRecord] = []
        page_texts: list[str] = []
        warnings: list[ParseWarning] = []
        heading_seed: list[tuple[int, str, float, float]] = []
        total_characters = 0
        ocr_applied_page_count = 0
        toc_sections = self._build_sections_from_toc(
            document_id=document_id,
            stored_path=stored_path,
            page_count=pdf.page_count,
            fallback_title=title,
        )
        _emit_progress(
            progress_callback,
            "parser_started",
            {
                "document_id": document_id,
                "page_count": pdf.page_count,
                "force_ocr": force_ocr,
                "toc_section_count": len(toc_sections),
            },
        )

        for index, page in enumerate(pdf, start=1):
            _call_interrupt(interrupt_check)
            parsed_page = self._parse_page(
                page_number=index,
                page=page,
                force_ocr=force_ocr,
            )
            parsed_pages.append(parsed_page)
            warnings.extend(parsed_page.warnings)
            if parsed_page.used_ocr:
                ocr_applied_page_count += 1
            if _should_emit_page_progress(page_number=index, page_count=pdf.page_count):
                _emit_progress(
                    progress_callback,
                    "page_parsed",
                    {
                        "page_number": index,
                        "page_count": pdf.page_count,
                        "processed_pages": index,
                        "extraction_source": parsed_page.extraction_source,
                        "used_ocr": parsed_page.used_ocr,
                        "warning_count": len(parsed_page.warnings),
                    },
                )

        top_margin_patterns, bottom_margin_patterns = self._detect_margin_patterns(parsed_pages)
        logger.info(
            "parser.margin_patterns top=%s bottom=%s",
            len(top_margin_patterns),
            len(bottom_margin_patterns),
        )
        _emit_progress(
            progress_callback,
            "margin_patterns_detected",
            {
                "top_pattern_count": len(top_margin_patterns),
                "bottom_pattern_count": len(bottom_margin_patterns),
            },
        )

        for parsed_page in parsed_pages:
            _call_interrupt(interrupt_check)
            stripped_lines, stripped_count = self._strip_margin_lines(
                parsed_page.line_entries,
                top_patterns=top_margin_patterns,
                bottom_patterns=bottom_margin_patterns,
            )
            page_text = "\n".join(text for text, _font_size in stripped_lines)
            total_characters += len(page_text)
            page_texts.append(page_text)

            heading_candidates = self._extract_heading_candidates(
                page_number=parsed_page.page_number,
                line_entries=stripped_lines,
                dominant_font_size=parsed_page.dominant_font_size,
            )
            if parsed_page.extraction_source in {"ocr", "ocr_attempted"}:
                heading_candidates = self._merge_heading_candidates(
                    heading_candidates,
                    self._extract_ocr_heading_candidates(
                        page_number=parsed_page.page_number,
                        page_text=page_text,
                    ),
                )

            if stripped_count:
                warnings.append(
                    ParseWarning(
                        code="header_footer_stripped",
                        message=f"Stripped {stripped_count} recurring header/footer lines from this page.",
                        page_number=parsed_page.page_number,
                    )
                )

            for candidate in heading_candidates:
                heading_seed.append(
                    (
                        candidate.page_number,
                        candidate.text,
                        candidate.font_size,
                        candidate.confidence,
                    )
                )

            pages.append(
                DocumentPageRecord(
                    page_number=parsed_page.page_number,
                    char_count=len(page_text),
                    word_count=len(page_text.split()),
                    text_preview=page_text[:400],
                    dominant_font_size=parsed_page.dominant_font_size,
                    extraction_source=parsed_page.extraction_source,
                    heading_candidates=heading_candidates,
                )
            )

        sections = toc_sections or self._build_sections(
            document_id=document_id,
            fallback_title=title,
            page_count=len(pages),
            heading_seed=heading_seed,
        )
        _call_interrupt(interrupt_check)
        _emit_progress(
            progress_callback,
            "sections_built",
            {
                "section_count": len(sections),
                "section_source": "toc" if toc_sections else "heuristic",
            },
        )
        chunks = self._build_chunks(
            document_id=document_id,
            sections=sections,
            page_texts=page_texts,
        )
        _emit_progress(
            progress_callback,
            "chunks_built",
            {
                "chunk_count": len(chunks),
            },
        )

        if not chunks:
            warnings.append(
                ParseWarning(
                    code="no_chunks_created",
                    message="No text chunks were created from this document.",
                )
            )

        ocr_applied = ocr_applied_page_count > 0
        ocr_results = [page.ocr_result for page in parsed_pages if page.ocr_result is not None]
        ocr_warnings = _unique_preserving_order(
            result.warning
            for result in ocr_results
            if result.warning
        )
        ocr_engine = next((result.engine_name for result in ocr_results if result.engine_name), None)
        ocr_model_id = next((result.model_id for result in ocr_results if result.model_id), None)
        low_density_detected = any(warning.code == "low_text_density" for warning in warnings)
        ocr_unavailable = any(result.status == "unavailable" for result in ocr_results)
        ocr_failed = any(result.status == "failed" for result in ocr_results)

        if force_ocr and ocr_applied:
            ocr_status = "forced"
        elif force_ocr and ocr_unavailable:
            ocr_status = "unavailable"
        elif force_ocr and ocr_failed:
            ocr_status = "failed"
        elif ocr_applied:
            ocr_status = "fallback_used"
        elif low_density_detected and ocr_unavailable:
            ocr_status = "unavailable"
        elif low_density_detected and ocr_failed:
            ocr_status = "failed"
        elif low_density_detected:
            ocr_status = "required"
        else:
            ocr_status = "completed"

        extraction_method = "ocr_forced" if force_ocr else "text_with_ocr_fallback" if ocr_applied else "page_text_dict"
        logger.info(
            "parser.result document_id=%s pages=%s sections=%s chunks=%s total_characters=%s extraction=%s ocr_status=%s ocr_applied_pages=%s warnings=%s section_source=%s",
            document_id,
            len(pages),
            len(sections),
            len(chunks),
            total_characters,
            extraction_method,
            ocr_status,
            ocr_applied_page_count,
            len(warnings),
            "toc" if toc_sections else "heuristic",
        )

        return DocumentDebugRecord(
            document_id=document_id,
            parser_name="pymupdf-text-pipeline",
            processed_at=_now(),
            page_count=len(pages),
            total_characters=total_characters,
            extraction_method=extraction_method,
            ocr_status=ocr_status,
            ocr_applied=ocr_applied,
            ocr_language=OCR_LANGUAGE_HINT if ocr_results else None,
            ocr_engine=ocr_engine,
            ocr_model_id=ocr_model_id,
            ocr_applied_page_count=ocr_applied_page_count,
            ocr_warnings=ocr_warnings,
            pages=pages,
            sections=sections,
            study_units=[],
            chunks=chunks,
            warnings=warnings,
            dominant_language_hint=self._guess_language(pages),
        )

    def _parse_page(
        self, *, page_number: int, page: fitz.Page, force_ocr: bool
    ) -> ParsedPage:
        line_entries, dominant_font_size = self._extract_text_lines(page)
        page_text = "\n".join(text for text, _font_size in line_entries)
        warnings: list[ParseWarning] = []
        used_ocr = False
        extraction_source = "text"
        ocr_result: OcrPageResult | None = None

        if force_ocr or len(page_text) < TEXT_DENSITY_THRESHOLD:
            original_text_length = len(page_text)
            ocr_result = self._run_ocr(page)
            cleaned_ocr = _clean_page_text(ocr_result.text)
            if cleaned_ocr and len(cleaned_ocr) > len(page_text):
                page_text = cleaned_ocr
                line_entries = [(line, 0.0) for line in cleaned_ocr.splitlines() if line]
                dominant_font_size = 0.0
                used_ocr = True
                extraction_source = "ocr"
                warnings.append(
                    ParseWarning(
                        code="ocr_applied",
                        message="OCR fallback was applied to this page.",
                        page_number=page_number,
                    )
                )
                logger.info(
                    "parser.page.ocr_applied page=%s force_ocr=%s text_chars_before=%s text_chars_after=%s",
                    page_number,
                    force_ocr,
                    original_text_length,
                    len(cleaned_ocr),
                )
            elif ocr_result.status == "unavailable":
                warnings.append(
                    ParseWarning(
                        code="ocr_unavailable",
                        message=ocr_result.warning or "OCR engine is unavailable for this page.",
                        page_number=page_number,
                    )
                )
                if force_ocr:
                    extraction_source = "ocr_unavailable"
                logger.warning(
                    "parser.page.ocr_unavailable page=%s reason=%s",
                    page_number,
                    ocr_result.warning or "unknown",
                )
            elif ocr_result.status == "failed":
                warnings.append(
                    ParseWarning(
                        code="ocr_failed",
                        message=ocr_result.warning or "OCR failed for this page.",
                        page_number=page_number,
                    )
                )
                if force_ocr:
                    extraction_source = "ocr_failed"
                logger.warning(
                    "parser.page.ocr_failed page=%s reason=%s",
                    page_number,
                    ocr_result.warning or "unknown",
                )
            elif force_ocr:
                extraction_source = "ocr_attempted"
                logger.warning(
                    "parser.page.ocr_attempted_no_gain page=%s",
                    page_number,
                )

        if len(page_text) < TEXT_DENSITY_THRESHOLD:
            warnings.append(
                ParseWarning(
                    code="low_text_density",
                    message="This page has very little extracted text and may require OCR.",
                    page_number=page_number,
                )
            )
        return ParsedPage(
            page_number=page_number,
            line_entries=line_entries,
            dominant_font_size=dominant_font_size,
            extraction_source=extraction_source,
            warnings=warnings,
            used_ocr=used_ocr,
            ocr_result=ocr_result,
        )

    def _detect_margin_patterns(
        self, pages: list[ParsedPage]
    ) -> tuple[set[str], set[str]]:
        top_counter: Counter[str] = Counter()
        bottom_counter: Counter[str] = Counter()
        non_empty_pages = 0

        for page in pages:
            line_texts = [text for text, _font_size in page.line_entries if text]
            if not line_texts:
                continue
            non_empty_pages += 1
            for line in line_texts[:MARGIN_SCAN_LINES]:
                if not self._looks_like_margin_candidate(line):
                    continue
                normalized = self._normalize_margin_text(line)
                if normalized:
                    top_counter[normalized] += 1
            for line in line_texts[-MARGIN_SCAN_LINES:]:
                if not self._looks_like_margin_candidate(line):
                    continue
                normalized = self._normalize_margin_text(line)
                if normalized:
                    bottom_counter[normalized] += 1

        threshold = max(MARGIN_MIN_REPEAT, non_empty_pages // 12) if non_empty_pages else MARGIN_MIN_REPEAT
        top_patterns = {
            pattern
            for pattern, count in top_counter.items()
            if self._is_recurrent_margin_pattern(pattern, count, threshold)
        }
        bottom_patterns = {
            pattern
            for pattern, count in bottom_counter.items()
            if self._is_recurrent_margin_pattern(pattern, count, threshold)
        }
        return top_patterns, bottom_patterns

    def _strip_margin_lines(
        self,
        line_entries: list[tuple[str, float]],
        *,
        top_patterns: set[str],
        bottom_patterns: set[str],
    ) -> tuple[list[tuple[str, float]], int]:
        start = 0
        end = len(line_entries)
        stripped_count = 0

        while start < end and stripped_count < MARGIN_SCAN_LINES:
            text = line_entries[start][0]
            if not self._is_margin_line(text, top_patterns):
                break
            start += 1
            stripped_count += 1

        bottom_removed = 0
        while end > start and bottom_removed < MARGIN_SCAN_LINES:
            text = line_entries[end - 1][0]
            if not self._is_margin_line(text, bottom_patterns):
                break
            end -= 1
            bottom_removed += 1

        return line_entries[start:end], stripped_count + bottom_removed

    def _extract_text_lines(self, page: fitz.Page) -> tuple[list[tuple[str, float]], float]:
        payload = page.get_text("dict")
        line_entries: list[tuple[str, float]] = []
        all_spans: list[tuple[str, float]] = []

        for block in payload.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_parts: list[str] = []
                sizes: list[float] = []
                for span in line.get("spans", []):
                    text = _clean_text(span.get("text", ""))
                    if not text:
                        continue
                    size = float(span.get("size", 0.0))
                    line_parts.append(text)
                    sizes.append(size)
                    all_spans.append((text, size))
                if line_parts:
                    merged = " ".join(line_parts).strip()
                    if merged:
                        average_size = sum(sizes) / len(sizes) if sizes else 0.0
                        line_entries.append((merged, average_size))

        return line_entries, _dominant_font_size(all_spans)

    def _extract_heading_candidates(
        self,
        *,
        page_number: int,
        line_entries: list[tuple[str, float]],
        dominant_font_size: float,
    ) -> list[HeadingCandidate]:
        candidates: list[HeadingCandidate] = []
        for text, font_size in line_entries[:12]:
            normalized = self._normalize_heading_text(text)
            if not normalized or self._looks_like_noisy_heading(normalized):
                continue

            pattern_bonus = (
                0.35 if any(pattern.match(normalized) for pattern in HEADING_PATTERNS) else 0.0
            )
            font_bonus = (
                0.2 if dominant_font_size and font_size >= dominant_font_size + 1.2 else 0.0
            )
            uppercase_bonus = 0.1 if normalized.isupper() and len(normalized) <= 32 else 0.0
            length_bonus = 0.12 if 3 <= len(normalized) <= 60 else 0.0
            confidence = min(0.95, 0.12 + pattern_bonus + font_bonus + uppercase_bonus + length_bonus)
            if confidence < 0.42:
                continue
            candidates.append(
                HeadingCandidate(
                    page_number=page_number,
                    text=normalized[:120],
                    font_size=round(font_size, 2),
                    confidence=round(confidence, 2),
                )
            )
        return candidates[:3]

    def _extract_ocr_heading_candidates(
        self,
        *,
        page_number: int,
        page_text: str,
    ) -> list[HeadingCandidate]:
        window = _clean_text(page_text[:220])
        candidates: list[HeadingCandidate] = []
        for pattern in OCR_HEADER_PATTERNS:
            match = pattern.search(window)
            if not match:
                continue
            normalized = self._normalize_heading_text(match.group(1))
            if not normalized or self._looks_like_noisy_heading(normalized):
                continue
            candidates.append(
                HeadingCandidate(
                    page_number=page_number,
                    text=normalized,
                    font_size=0.0,
                    confidence=0.76,
                )
            )
        return candidates[:2]

    def _merge_heading_candidates(
        self,
        existing: list[HeadingCandidate],
        extra: list[HeadingCandidate],
    ) -> list[HeadingCandidate]:
        merged: list[HeadingCandidate] = []
        seen: set[str] = set()
        for candidate in [*extra, *existing]:
            key = candidate.text.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(candidate)
        return merged[:3]

    def _build_sections(
        self,
        *,
        document_id: str,
        fallback_title: str,
        page_count: int,
        heading_seed: list[tuple[int, str, float, float]],
    ) -> list[DocumentSection]:
        accepted: list[tuple[int, str, int]] = []
        seen_pages: set[int] = set()
        recent_titles: set[str] = set()

        for page_number, text, _font_size, confidence in sorted(heading_seed, key=lambda item: item[0]):
            if confidence < 0.45 or page_number in seen_pages:
                continue
            cleaned = self._normalize_heading_text(text)
            if not cleaned or self._looks_like_noisy_heading(cleaned):
                continue
            title_key = cleaned.casefold()
            if title_key in recent_titles:
                continue
            seen_pages.add(page_number)
            recent_titles.add(title_key)
            accepted.append((page_number, cleaned, self._infer_heading_level(cleaned)))

        if not accepted:
            accepted = [
                (page_number, title, 1)
                for page_number, title in self._fallback_sections(
                    fallback_title=fallback_title,
                    page_count=page_count,
                )
            ]

        return self._materialize_sections(
            document_id=document_id,
            page_count=page_count,
            entries=accepted,
            fallback_title=fallback_title,
        )

    def _build_sections_from_toc(
        self, *, document_id: str, stored_path: str, page_count: int, fallback_title: str
    ) -> list[DocumentSection]:
        pdf = fitz.open(stored_path)
        try:
            toc = pdf.get_toc(simple=True)
            if not toc:
                return []

            filtered: list[tuple[int, str, int]] = []
            for level, title, page_number in toc:
                if level > TOC_MAX_LEVEL:
                    continue
                cleaned = self._normalize_heading_text(title)
                if not cleaned or self._looks_like_noisy_heading(cleaned):
                    continue
                if page_number < 1 or page_number > page_count:
                    continue
                filtered.append((page_number, cleaned, level))

            deduped: list[tuple[int, str, int]] = []
            seen: set[tuple[int, str, int]] = set()
            for page_number, cleaned, level in filtered:
                key = (page_number, cleaned.casefold(), level)
                if key in seen:
                    continue
                seen.add(key)
                deduped.append((page_number, cleaned, level))

            if len(deduped) < MIN_GOOD_TOC_ENTRIES:
                return []

            return self._materialize_sections(
                document_id=document_id,
                page_count=page_count,
                entries=deduped,
                fallback_title=fallback_title,
            )
        finally:
            pdf.close()

    def _fallback_sections(self, *, fallback_title: str, page_count: int) -> list[tuple[int, str]]:
        if page_count <= 1:
            return [(1, f"{fallback_title} 全文")]
        if page_count <= 6:
            return [
                (1, f"{fallback_title} 前半部分"),
                (max(2, (page_count // 2) + 1), f"{fallback_title} 后半部分"),
            ]
        stride = max(1, page_count // 3)
        fallback_pages = [1, min(page_count, 1 + stride), min(page_count, 1 + stride * 2)]
        return [
            (page_number, f"{fallback_title} 第 {index + 1} 部分")
            for index, page_number in enumerate(dict.fromkeys(fallback_pages))
        ]

    def _build_chunks(
        self,
        *,
        document_id: str,
        sections: list[DocumentSection],
        page_texts: list[str],
    ) -> list[DocumentChunkRecord]:
        chunks: list[DocumentChunkRecord] = []
        chunk_index = 1

        for section, segment_start, segment_end in self._iter_chunk_segments(sections):
            units: list[tuple[int, str]] = []
            for page_number in range(segment_start, segment_end + 1):
                page_text = page_texts[page_number - 1] if page_number - 1 < len(page_texts) else ""
                if not page_text:
                    continue
                units.extend((page_number, unit) for unit in self._split_text_units(page_text))

            buffer_parts: list[str] = []
            chunk_page_start: int | None = None
            chunk_page_end: int | None = None

            for page_number, unit in units:
                if chunk_page_start is None:
                    chunk_page_start = page_number
                candidate = "\n\n".join([*buffer_parts, unit]) if buffer_parts else unit
                if buffer_parts and len(candidate) > CHUNK_MAX_CHARS:
                    chunk_text = "\n\n".join(buffer_parts)
                    chunks.append(
                        DocumentChunkRecord(
                            id=f"{document_id}:chunk:{chunk_index}",
                            document_id=document_id,
                            section_id=section.id,
                            page_start=chunk_page_start,
                            page_end=chunk_page_end or chunk_page_start,
                            char_count=len(chunk_text),
                            text_preview=chunk_text[:260],
                            content=chunk_text,
                        )
                    )
                    chunk_index += 1
                    buffer_parts = [unit]
                    chunk_page_start = page_number
                    chunk_page_end = page_number
                    continue

                buffer_parts.append(unit)
                chunk_page_end = page_number

                current_text = "\n\n".join(buffer_parts)
                if len(current_text) >= CHUNK_TARGET_CHARS:
                    chunks.append(
                        DocumentChunkRecord(
                            id=f"{document_id}:chunk:{chunk_index}",
                            document_id=document_id,
                            section_id=section.id,
                            page_start=chunk_page_start,
                            page_end=chunk_page_end,
                            char_count=len(current_text),
                            text_preview=current_text[:260],
                            content=current_text,
                        )
                    )
                    chunk_index += 1
                    buffer_parts = []
                    chunk_page_start = None
                    chunk_page_end = None

            if buffer_parts:
                chunk_text = "\n\n".join(buffer_parts)
                chunks.append(
                    DocumentChunkRecord(
                        id=f"{document_id}:chunk:{chunk_index}",
                        document_id=document_id,
                        section_id=section.id,
                        page_start=chunk_page_start or segment_start,
                        page_end=chunk_page_end or segment_start,
                        char_count=len(chunk_text),
                        text_preview=chunk_text[:260],
                        content=chunk_text,
                    )
                )
                chunk_index += 1
        return chunks

    def _iter_chunk_segments(
        self, sections: list[DocumentSection]
    ) -> list[tuple[DocumentSection, int, int]]:
        coarse_sections = sorted(
            [section for section in sections if section.level == 1],
            key=lambda section: (section.page_start, section.page_end, section.id),
        )
        fine_sections = sorted(
            [section for section in sections if section.level == 2],
            key=lambda section: (section.page_start, section.page_end, section.id),
        )

        if not coarse_sections:
            return []

        segments: list[tuple[DocumentSection, int, int]] = []
        for coarse in coarse_sections:
            children = [
                section
                for section in fine_sections
                if coarse.page_start <= section.page_start <= section.page_end <= coarse.page_end
            ]
            if not children:
                segments.append((coarse, coarse.page_start, coarse.page_end))
                continue

            cursor = coarse.page_start
            for child in children:
                if cursor < child.page_start:
                    segments.append((coarse, cursor, child.page_start - 1))
                segments.append((child, child.page_start, child.page_end))
                cursor = child.page_end + 1

            if cursor <= coarse.page_end:
                segments.append((coarse, cursor, coarse.page_end))
        return segments

    def _split_text_units(self, text: str) -> list[str]:
        paragraphs = [segment.strip() for segment in re.split(r"\n\s*\n", text) if segment.strip()]
        units: list[str] = []
        for paragraph in paragraphs or [text]:
            if len(paragraph) <= 900:
                units.append(paragraph)
                continue
            sentences = re.split(r"(?<=[。！？.!?])\s+|(?<=:)\s+(?=[A-Z0-9])", paragraph)
            current = ""
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                candidate = f"{current} {sentence}".strip() if current else sentence
                if current and len(candidate) > 900:
                    units.append(current)
                    current = sentence
                else:
                    current = candidate
            if current:
                units.append(current)

        merged: list[str] = []
        for unit in units:
            if merged and len(unit) < 180 and len(merged[-1]) + len(unit) < 900:
                merged[-1] = f"{merged[-1]}\n{unit}"
            else:
                merged.append(unit)
        return merged

    def _run_ocr(self, page: fitz.Page) -> OcrPageResult:
        raw_result = self._ocr_page(page)
        if isinstance(raw_result, OcrPageResult):
            return raw_result
        text = str(raw_result or "")
        return OcrPageResult(
            text=text,
            status="completed" if text.strip() else "failed",
            engine_name=self.ocr_engine.engine_name if self.ocr_engine is not None else self.ocr_engine_name,
            model_id=self.ocr_engine.model_id if self.ocr_engine is not None else None,
            warning="" if text.strip() else "ocr_empty_result",
            language_hint=OCR_LANGUAGE_HINT,
        )

    def _ocr_page(self, page: fitz.Page) -> OcrPageResult | str:
        if self.ocr_engine is None:
            return OcrPageResult(
                status="unavailable",
                engine_name=self.ocr_engine_name,
                warning=f"unsupported_ocr_engine:{self.ocr_engine_name}",
                language_hint=OCR_LANGUAGE_HINT,
            )
        return self.ocr_engine.extract_page_text(page)

    def _normalize_heading_text(self, text: str) -> str:
        normalized = _clean_text(text)
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = re.sub(r"^\d{1,4}\s+[—-]\s+", "", normalized)
        normalized = re.sub(r"\s+\d{1,4}$", "", normalized)
        normalized = re.sub(r"\s+[ivxlcdmIVXLCDM]+$", "", normalized)
        return normalized.strip(" -_:|")

    def _normalize_margin_text(self, text: str) -> str:
        normalized = _clean_text(text).casefold()
        normalized = re.sub(r"\bpage\s+\d{1,4}\b", "#", normalized)
        normalized = re.sub(r"\b\d{1,4}\b", "#", normalized)
        normalized = re.sub(r"\b[ivxlcdm]{1,8}\b", "#", normalized)
        normalized = re.sub(r"[_~|]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip(" -_:|.,;[]()")

    def _is_recurrent_margin_pattern(self, pattern: str, count: int, threshold: int) -> bool:
        if count < threshold:
            return False
        if pattern in {"#", ""}:
            return True
        if len(pattern) < 4:
            return False
        if len(pattern.split()) > 14:
            return False
        return True

    def _looks_like_margin_candidate(self, text: str) -> bool:
        normalized = _clean_text(text)
        if not normalized:
            return False
        if self._is_page_marker(normalized):
            return True
        if len(normalized) > 90 or len(normalized.split()) > 12:
            return False
        alpha_words = re.findall(r"[A-Za-z]+", normalized)
        title_like_word_count = sum(1 for word in alpha_words if word[:1].isupper())
        is_title_like = bool(alpha_words) and title_like_word_count >= max(1, len(alpha_words) - 1)
        if (
            re.search(r"[.!?]$", normalized)
            and not re.search(r"\d{1,4}$", normalized)
            and not is_title_like
        ):
            return False
        if len(alpha_words) >= 5 and normalized == normalized.lower() and not re.search(r"\d", normalized):
            return False
        return True

    def _is_page_marker(self, text: str) -> bool:
        normalized = _clean_text(text)
        if not normalized:
            return False
        return bool(
            re.fullmatch(r"(?:page\s+)?\d{1,4}", normalized, re.IGNORECASE)
            or re.fullmatch(r"[ivxlcdmIVXLCDM]{1,8}", normalized)
        )

    def _looks_like_running_header(self, text: str) -> bool:
        normalized = _clean_text(text)
        if not normalized:
            return False
        return bool(
            re.match(r"^\d{1,4}\s+\d+(?:\.\d+)*\.?\s+\S+", normalized)
            or re.match(
                r"^(?:chapter\s+\d+[A-Za-z]?|solutions\s+(?:for\s+chapter\s+\d+|to\s+exercises)|\d+(?:\.\d+)*\.?\s+\S+|[A-Z][A-Za-z0-9,'’()\- ]{3,90})\s+\d{1,4}$",
                normalized,
                re.IGNORECASE,
            )
        )

    def _is_margin_line(self, text: str, patterns: set[str]) -> bool:
        normalized = self._normalize_margin_text(text)
        return (
            self._is_page_marker(text)
            or self._looks_like_running_header(text)
            or (normalized in patterns if normalized else False)
        )

    def _infer_heading_level(self, text: str) -> int:
        lowered = text.casefold()
        if re.match(r"^\d+\.\d+", text):
            return 2
        if lowered.startswith(("section ", "§")):
            return 2
        if re.match(r"^第[一二三四五六七八九十百0-9]+节", text):
            return 2
        if re.match(r"^\d+\s+[A-Z]", text):
            return 1
        if lowered.startswith(("chapter ", "part ", "appendix", "solutions for chapter", "solutions to exercises")):
            return 1
        if re.match(r"^第[一二三四五六七八九十百0-9]+[章节部分]", text):
            return 1
        return 1

    def _materialize_sections(
        self,
        *,
        document_id: str,
        page_count: int,
        entries: list[tuple[int, str, int]],
        fallback_title: str | None,
    ) -> list[DocumentSection]:
        coarse_entries = [
            (page_number, title)
            for page_number, title, level in entries
            if level <= 1
        ]
        fine_entries = [
            (page_number, title)
            for page_number, title, level in entries
            if level == 2
        ]

        if not coarse_entries:
            if not fallback_title:
                return []
            coarse_entries = self._fallback_sections(
                fallback_title=fallback_title,
                page_count=page_count,
            )

        if coarse_entries and coarse_entries[0][0] > 1 and fallback_title:
            coarse_entries = [(1, f"{fallback_title} Front Matter"), *coarse_entries]

        coarse_entries = self._dedupe_section_entries(coarse_entries)
        fine_entries = self._dedupe_section_entries(fine_entries)

        coarse_sections: list[DocumentSection] = []
        for index, (page_number, title) in enumerate(coarse_entries):
            next_page = coarse_entries[index + 1][0] - 1 if index + 1 < len(coarse_entries) else page_count
            coarse_sections.append(
                DocumentSection(
                    id=f"{document_id}:section:l1:{index + 1}",
                    document_id=document_id,
                    title=title,
                    page_start=page_number,
                    page_end=max(page_number, next_page),
                    level=1,
                )
            )

        sections: list[DocumentSection] = []
        fine_index = 1
        for coarse in coarse_sections:
            sections.append(coarse)
            children = [
                (page_number, title)
                for page_number, title in fine_entries
                if coarse.page_start <= page_number <= coarse.page_end
            ]
            for index, (page_number, title) in enumerate(children):
                if page_number == coarse.page_start and title.casefold() == coarse.title.casefold():
                    continue
                next_page = children[index + 1][0] - 1 if index + 1 < len(children) else coarse.page_end
                sections.append(
                    DocumentSection(
                        id=f"{document_id}:section:l2:{fine_index}",
                        document_id=document_id,
                        title=title,
                        page_start=page_number,
                        page_end=max(page_number, next_page),
                        level=2,
                    )
                )
                fine_index += 1
        return sections

    def _dedupe_section_entries(
        self, entries: list[tuple[int, str]]
    ) -> list[tuple[int, str]]:
        deduped: list[tuple[int, str]] = []
        seen: set[tuple[int, str]] = set()
        for page_number, title in sorted(entries, key=lambda item: (item[0], item[1].casefold())):
            key = (page_number, title.casefold())
            if key in seen:
                continue
            seen.add(key)
            deduped.append((page_number, title))
        return deduped

    def _looks_like_noisy_heading(self, text: str) -> bool:
        if len(text) < 3 or len(text) > 90:
            return True
        if len(text.split()) > 12:
            return True
        if self._looks_like_exercise_heading(text):
            return True
        if len(text) > 45 and text.endswith((".", ";", ":", ",")):
            return True
        if any(keyword in text for keyword in ["Theorem.", "Corollary.", "Definition.", "Proposition.", "Exercise.", "Remark.", "Example."]):
            return True
        alpha_count = sum(char.isalpha() for char in text)
        digit_count = sum(char.isdigit() for char in text)
        symbol_count = sum(not char.isalnum() and not char.isspace() for char in text)
        if alpha_count == 0 and digit_count == 0:
            return True
        if symbol_count > max(4, len(text) * 0.12):
            return True
        if digit_count > alpha_count * 2 and alpha_count < 4:
            return True
        lowered = text.casefold()
        banned_fragments = [
            "document generated by",
            "annas archive",
            "library of congress cataloging",
        ]
        if any(fragment in lowered for fragment in banned_fragments):
            return True
        if re.search(r"[{}\\<>~=]{2,}", text):
            return True
        if re.search(r"[A-Za-z]{1,2}\s*[=~<>]", text):
            return True
        return False

    def _looks_like_exercise_heading(self, text: str) -> bool:
        lowered = text.casefold()
        if lowered in {"exercise", "exercises"}:
            return True
        if re.fullmatch(r"\(?\d+(?:\.\d+)*\)?\s*exercises?", text, re.IGNORECASE):
            return True
        if lowered.startswith("additional exercise"):
            return True

        imperative_prompt = re.match(
            r"^[+\-*o•]?\s*\(?\d+(?:\.\d+)*\)?[.)-]?\s+"
            r"(design|prove|construct|show|explain|formulate|give|draw|let|suppose|referring|without|carry)\b",
            lowered,
        )
        if imperative_prompt:
            return True

        if re.match(
            r"^[+\-*o•]?\s*\(?\d+(?:\.\d+)*\)?[.)-]?\s+for this exercise\b",
            lowered,
        ):
            return True

        if "exercise" in lowered and any(
            lowered.startswith(prefix)
            for prefix in (
                "for this exercise",
                "in this exercise",
                "additional exercise",
            )
        ):
            return True

        return False

    def _guess_language(self, pages: list[DocumentPageRecord]) -> str:
        joined = "".join(page.text_preview for page in pages[:5])
        if re.search(r"[\u4e00-\u9fff]", joined):
            return "zh"
        if re.search(r"[A-Za-z]", joined):
            return "en"
        return "unknown"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clean_page_text(text: str) -> str:
    lines = [_clean_text(line) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _dominant_font_size(spans: list[tuple[str, float]]) -> float:
    if not spans:
        return 0.0
    rounded_sizes = [round(size, 1) for _text, size in spans if size > 0]
    if not rounded_sizes:
        return 0.0
    return Counter(rounded_sizes).most_common(1)[0][0]


def _should_emit_page_progress(*, page_number: int, page_count: int) -> bool:
    if page_count <= 12:
        return True
    if page_number in {1, page_count}:
        return True
    if page_number <= 3:
        return True
    return page_number % 10 == 0


def _unique_preserving_order(items: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_progress(
    callback: Callable[[str, dict[str, object]], None] | None,
    stage: str,
    payload: dict[str, object],
) -> None:
    if callback is None:
        return
    callback(stage, payload)


def _call_interrupt(callback: Callable[[], None] | None) -> None:
    if callback is None:
        return
    callback()
