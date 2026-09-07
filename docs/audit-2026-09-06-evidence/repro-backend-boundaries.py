import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import fitz
from fastapi import UploadFile

from app.models.domain import DocumentChunkRecord, DocumentDebugRecord, DocumentPageRecord, StudyUnitRecord
from app.models.harness import canonical_harness_digest
from app.services.local_store import LocalJsonStore
from app.services.documents import DocumentService
from app.services.document_parser import DocumentParser
from app.services.study_arrangement import StudyArrangementService
from app.services.harness_broad_adoption import DocumentStageEvidenceV1, DocumentStageInputManifest, HarnessProposalRuntimeService, PersonaGenerationInputManifest, PersonaGenerationProposalV1, PersonaCardContentProposalV1
from app.services.model_provider import OpenAIModelProvider

def pdf_bytes():
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data

with TemporaryDirectory(prefix='vibe-backend-audit-') as directory:
    store = LocalJsonStore(Path(directory))
    harness = HarnessProposalRuntimeService.from_database(store.database)
    failed_evidence = DocumentStageEvidenceV1(stage='ocr_page', outcome='failed', item_count=1, warning_count=1, source_digest=canonical_harness_digest({'x': 1}))
    failed_trace = harness.emit_ocr_stage_evidence(document_id='audit-document', input_manifest=DocumentStageInputManifest(document_id='audit-document', stage='ocr_page', item_count=1), evidence=failed_evidence)
    print(json.dumps({'case': 'explicit_failed_ocr_stage', 'input_outcome': failed_evidence.outcome, 'trace_status': failed_trace.status.value, 'checks': [item.status.value for item in failed_trace.checks]}))

    documents = DocumentService(store, DocumentParser(ocr_engine_name='none'), StudyArrangementService())
    upload = documents.create_document(UploadFile(filename='blank.pdf', file=io.BytesIO(pdf_bytes())))
    with patch.object(documents.harness_service, 'emit_ocr_stage_evidence', wraps=documents.harness_service.emit_ocr_stage_evidence) as capture:
        processed = documents.process_document(upload.id, force_ocr=True)
        ocr_evidence = capture.call_args.kwargs['evidence']
    report = documents.require_debug_report(upload.id)
    print(json.dumps({'case': 'real_parser_unavailable_ocr', 'document_status': processed.status, 'debug_ocr_status': report.ocr_status, 'emitted_ocr_outcome': ocr_evidence.outcome, 'ocr_stage_item_count': ocr_evidence.item_count, 'page_characters': [p.char_count for p in report.pages], 'study_unit_count': processed.study_unit_count}))

    class InvalidParser:
        def parse(self, *, document_id, **kwargs):
            return DocumentDebugRecord(document_id=document_id, parser_name='audit-parser', processed_at='2026-09-05T00:00:00+00:00', page_count=1, total_characters=5, extraction_method='page_text_dict', pages=[DocumentPageRecord(page_number=1, char_count=5, word_count=1, text_preview='valid', dominant_font_size=10, heading_candidates=[])], sections=[], chunks=[DocumentChunkRecord(id='chunk-audit', document_id='another-document', section_id='nonexistent-section', page_start=999, page_end=-1, char_count=-50, text_preview='invalid', content='invalid')], warnings=[], dominant_language_hint='en')
    class EmptyArrangement:
        def build_study_units(self, **kwargs):
            return []
    invalid_service = DocumentService(store, InvalidParser(), EmptyArrangement())
    invalid_upload = invalid_service.create_document(UploadFile(filename='invalid-chunk.pdf', file=io.BytesIO(pdf_bytes())))
    invalid_processed = invalid_service.process_document(invalid_upload.id)
    invalid_report = invalid_service.require_debug_report(invalid_upload.id)
    print(json.dumps({'case': 'cross_document_out_of_bounds_chunk', 'document_status': invalid_processed.status, 'committed_chunk': invalid_report.chunks[0].model_dump()}))

    provider = OpenAIModelProvider(api_key='audit-test-key', base_url='https://example.invalid/v1', plan_model='audit-model', setting_model='audit-model', timeout_seconds=1)
    malformed = {'summary': {'unexpected': True}, 'relationship': ['bad'], 'learner_address': 77, 'cards': [{'id': 'forged-model-id', 'title': {'bad': 'title'}, 'content': 123, 'tags': [42]}]}
    with patch.object(provider, '_request_setting_json_chat', return_value=malformed):
        normalized = provider.generate_persona_cards_from_text(text='audit persona', count=1)
    proposal = PersonaGenerationProposalV1(request_kind='card_batch', used_model=normalized['used_model'], used_web_search=normalized['used_web_search'], summary=normalized['summary'], relationship=normalized['relationship'], learner_address=normalized['learner_address'], cards=[PersonaCardContentProposalV1.model_validate(item) for item in normalized['cards']])
    output, trace = harness.run_persona(manifest=PersonaGenerationInputManifest(request_kind='card_batch', mode='long_text', requested_count=1, input_char_count=13), protected_input={'input_text': 'audit persona'}, generate=lambda _: proposal)
    print(json.dumps({'case': 'malformed_model_persona_output', 'trace_status': trace.status.value, 'summary': output.summary, 'card': output.cards[0].model_dump()}))
    store.close()
