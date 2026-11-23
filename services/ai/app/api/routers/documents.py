from app.models.document_input_limits import DocumentInputLimitsV1
from app.models.document_checkpoint import DocumentCheckpointResponseV1
from app.models.pdf_page_scope import DocumentPageNumberingResponseV1
from app.services.document_page_numbering import read_document_page_numbering
import json
from pathlib import Path
import queue
import threading
from contextvars import copy_context

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import Response, StreamingResponse

from app.core.diagnostics import reference_resource
from app.core.bootstrap import Container
from app.api.dependencies import get_container
from fastapi import Depends
from app.models.api import (
    DocumentDebugResponse,
    DocumentListResponse,
    DocumentPlanningContextResponse,
    DocumentPlanningTraceResponse,
    DocumentResponse,
    DocumentProcessResponse,
    DocumentStudyUnitUpdateResponse,
    StreamReportResponse,
    DocumentStatusResponse,
    LearningPlanResponse,
    StudyUnitTitleUpdateRequest,
    ProcessDocumentRequest,
)
from app.models.domain import PlanGenerationTraceRecord
from app.models.harness import HarnessStage
from app.models.harness_operation import HarnessDomainOperationKind
from app.services.study_chat_attachments import render_pdf_page_png_bytes
from app.services.stream_interrupts import StreamInterruptedError
from app.services.stream_reports import (
    DOCUMENT_PROCESS_STREAM_CATEGORY,
    LEARNING_PLAN_STREAM_CATEGORY,
    StreamReportRecorder,
)
from app.services.plan_prompt import build_learning_plan_context
from app.services.plan_tool_runtime import get_learning_plan_tool_specs


from app.api._shared import (
    logger,
    _into_response,
    _require_domain_harness_trace,
    _document_stream_subject,
    _document_stream_committed_evidence,
    _stream_failure_evidence,
    _stringify_error,
)

router = APIRouter()


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(
    *, container: Container = Depends(get_container)
) -> DocumentListResponse:
    return DocumentListResponse(
        items=[
            _into_response(DocumentResponse, document)
            for document in container.document_service.list_documents()
        ]
    )


@router.get("/documents/input-limits", response_model=DocumentInputLimitsV1)
def get_document_input_limits() -> DocumentInputLimitsV1:
    return DocumentInputLimitsV1()


@router.post("/documents", response_model=DocumentResponse)
def create_document(
    file: UploadFile = File(...), *, container: Container = Depends(get_container)
) -> DocumentResponse:
    logger.info(
        "documents.create filename=%s content_type=%s",
        file.filename,
        file.content_type,
    )
    document = container.document_service.create_document(file)
    reference_resource("document", document.id)
    return _into_response(DocumentResponse, document)


@router.post("/documents/{document_id}/process", response_model=DocumentProcessResponse)
def process_document(
    document_id: str,
    payload: ProcessDocumentRequest | None = None,
    *,
    container: Container = Depends(get_container),
) -> DocumentProcessResponse:
    domain_operation_id = ""

    def remember_operation(operation_id: str) -> None:
        nonlocal domain_operation_id
        domain_operation_id = operation_id

    recorder = StreamReportRecorder(
        store=container.store,
        category=DOCUMENT_PROCESS_STREAM_CATEGORY,
        document_id=document_id,
        stream_kind="document_process",
        subject=_document_stream_subject(document_id),
    )
    logger.info(
        "documents.process document_id=%s force_ocr=%s",
        document_id,
        payload.force_ocr if payload else False,
    )
    try:
        document = container.document_service.process_document(
            document_id,
            force_ocr=(payload.force_ocr if payload else False),
            resume_from_operation_id=payload.resume_from_operation_id
            if payload
            else None,
            progress_callback=recorder.callback,
            operation_admitted_callback=remember_operation,
        )
    except Exception as exc:
        recorder.emit(
            "stream_error",
            {
                "document_id": document_id,
                "error": _stringify_error(exc),
            },
            terminal_evidence=_stream_failure_evidence(
                operation_id=domain_operation_id,
                domain="document_process",
                container=container,
            ),
        )
        raise
    harness_trace = _require_domain_harness_trace(
        domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
        domain_operation_id=domain_operation_id,
        stage=HarnessStage.DOCUMENT_PARSE,
        container=container,
    )
    reference_resource("document", document.id)
    document_commit_projection = document.model_dump(mode="json")
    document_projection = {
        **document_commit_projection,
        "harness_trace": harness_trace.model_dump(mode="json", exclude_none=False),
    }
    recorder.emit(
        "stream_completed",
        {
            "document_id": document.id,
            "status": document.status,
        },
        terminal_evidence=_document_stream_committed_evidence(
            operation_id=domain_operation_id,
            document_payload=document_projection,
            container=container,
        ),
        committed_projection=document_projection,
    )
    return DocumentProcessResponse.model_validate(document_projection)


@router.patch(
    "/documents/{document_id}/study-units/{study_unit_id}",
    response_model=DocumentStudyUnitUpdateResponse,
)
def update_study_unit_title(
    document_id: str,
    study_unit_id: str,
    payload: StudyUnitTitleUpdateRequest,
    *,
    container: Container = Depends(get_container),
) -> DocumentStudyUnitUpdateResponse:
    document = container.document_service.update_study_unit_title(
        document_id=document_id,
        study_unit_id=study_unit_id,
        title=payload.title,
        expected_revision=payload.expected_revision,
    )
    plans = container.plan_service.update_study_unit_title(
        document_id=document_id,
        study_unit_id=study_unit_id,
        title=payload.title,
    )
    return DocumentStudyUnitUpdateResponse(
        document=_into_response(DocumentResponse, document),
        plans=[_into_response(LearningPlanResponse, plan) for plan in plans],
    )


@router.post("/documents/{document_id}/process/stream")
def process_document_stream(
    document_id: str,
    payload: ProcessDocumentRequest | None = None,
    *,
    container: Container = Depends(get_container),
) -> StreamingResponse:
    force_ocr = payload.force_ocr if payload else False
    event_queue: queue.Queue[dict[str, object] | None] = queue.Queue()
    interrupt_handle = container.stream_interrupt_registry.create(
        stream_kind="document_process",
        target_id=document_id,
    )
    recorder = StreamReportRecorder(
        store=container.store,
        category=DOCUMENT_PROCESS_STREAM_CATEGORY,
        document_id=document_id,
        stream_kind="document_process",
        subject=_document_stream_subject(document_id),
        operation_id=interrupt_handle.stream_id,
    )
    domain_operation_id = ""

    def remember_operation(operation_id: str) -> None:
        nonlocal domain_operation_id
        domain_operation_id = operation_id

    def report(stage: str, event_payload: dict[str, object]) -> None:
        interrupt_handle.raise_if_cancelled()
        event = recorder.emit(stage, event_payload)
        event_queue.put(event.model_dump(mode="json"))

    def emit_cancelled() -> None:
        event = recorder.emit(
            "stream_cancelled",
            {
                "document_id": document_id,
                "detail": "stream_interrupted",
            },
            terminal_evidence=_stream_failure_evidence(
                operation_id=domain_operation_id,
                domain="document_process",
                container=container,
            ),
        )
        event_queue.put(event.model_dump(mode="json"))

    def run() -> None:
        try:
            document = container.document_service.process_document(
                document_id,
                force_ocr=force_ocr,
                resume_from_operation_id=payload.resume_from_operation_id
                if payload
                else None,
                progress_callback=report,
                interrupt_check=interrupt_handle.raise_if_cancelled,
                operation_admitted_callback=remember_operation,
            )
            if interrupt_handle.claim_terminal():
                emit_cancelled()
            else:
                harness_trace = _require_domain_harness_trace(
                    domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
                    domain_operation_id=domain_operation_id,
                    stage=HarnessStage.DOCUMENT_PARSE,
                    container=container,
                )
                reference_resource("document", document.id)
                document_commit_projection = document.model_dump(mode="json")
                document_projection = {
                    **document_commit_projection,
                    "harness_trace": harness_trace.model_dump(
                        mode="json", exclude_none=False
                    ),
                }
                event = recorder.emit(
                    "stream_completed",
                    {
                        "document_id": document.id,
                        "status": document.status,
                    },
                    terminal_evidence=_document_stream_committed_evidence(
                        operation_id=domain_operation_id,
                        document_payload=document_projection,
                        container=container,
                    ),
                    committed_projection=document_projection,
                )
                event_queue.put(event.model_dump(mode="json"))
        except StreamInterruptedError:
            interrupt_handle.claim_terminal()
            emit_cancelled()
        except Exception as exc:
            if interrupt_handle.claim_terminal():
                emit_cancelled()
            else:
                event = recorder.emit(
                    "stream_error",
                    {
                        "document_id": document_id,
                        "error": _stringify_error(exc),
                    },
                    terminal_evidence=_stream_failure_evidence(
                        operation_id=domain_operation_id,
                        domain="document_process",
                        container=container,
                    ),
                )
                event_queue.put(event.model_dump(mode="json"))
        finally:
            interrupt_handle.mark_completed()
            event_queue.put(None)

    threading.Thread(target=copy_context().run, args=(run,), daemon=True).start()

    def generate():
        while True:
            item = event_queue.get()
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(
    document_id: str, *, container: Container = Depends(get_container)
) -> DocumentStatusResponse:
    document = container.document_service.require_document(document_id)
    return _into_response(DocumentStatusResponse, document)


@router.get("/documents/{document_id}/file")
def get_document_file(
    document_id: str, *, container: Container = Depends(get_container)
) -> FileResponse:
    document = container.document_service.require_document(document_id)
    path = Path(document.stored_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="document_file_not_found")
    return FileResponse(
        path=path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@router.get("/documents/{document_id}/pages/{page_number}/image")
def get_document_page_image(
    document_id: str, page_number: int, *, container: Container = Depends(get_container)
) -> Response:
    document = container.document_service.require_document(document_id)
    path = Path(document.stored_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="document_file_not_found")
    image_bytes = render_pdf_page_png_bytes(
        pdf_path=str(path),
        page_number=page_number,
    )
    return Response(content=image_bytes, media_type="image/png")


@router.get(
    "/documents/{document_id}/page-numbering",
    response_model=DocumentPageNumberingResponseV1,
)
def get_document_page_numbering(
    document_id: str,
    page_numbers: list[int] = Query(..., min_length=1, max_length=64),
    *,
    container: Container = Depends(get_container),
) -> DocumentPageNumberingResponseV1:
    document = container.document_service.require_document(document_id)
    return read_document_page_numbering(document, page_numbers)


@router.get(
    "/documents/{document_id}/checkpoints/{operation_id}",
    response_model=DocumentCheckpointResponseV1,
)
def get_document_checkpoint(
    document_id: str,
    operation_id: str,
    *,
    container: Container = Depends(get_container),
):
    result = container.document_service.checkpoints.public_view(operation_id)
    if result["document_id"] != document_id:
        raise HTTPException(404, "document_checkpoint_not_found")
    return result


@router.get(
    "/documents/{document_id}/checkpoint", response_model=DocumentCheckpointResponseV1
)
def get_latest_document_checkpoint(
    document_id: str, *, container: Container = Depends(get_container)
):
    operation = container.document_service.process_repository.latest(
        document_id=document_id, validate_read_back=False
    )
    if operation is None:
        raise HTTPException(404, "document_checkpoint_not_found")
    return container.document_service.checkpoints.public_view(operation.operation_id)


@router.get("/documents/{document_id}/debug", response_model=DocumentDebugResponse)
def get_document_debug(
    document_id: str, *, container: Container = Depends(get_container)
) -> DocumentDebugResponse:
    report = container.document_service.require_debug_report(document_id)
    return _into_response(DocumentDebugResponse, report)


@router.get(
    "/documents/{document_id}/process-events", response_model=StreamReportResponse
)
def get_document_process_events(
    document_id: str, *, container: Container = Depends(get_container)
) -> StreamReportResponse:
    report = StreamReportRecorder.load(
        store=container.store,
        category=DOCUMENT_PROCESS_STREAM_CATEGORY,
        document_id=document_id,
        stream_kind="document_process",
    )
    return _into_response(StreamReportResponse, report)


@router.get(
    "/documents/{document_id}/planning-context",
    response_model=DocumentPlanningContextResponse,
)
def get_document_planning_context(
    document_id: str, *, container: Container = Depends(get_container)
) -> DocumentPlanningContextResponse:
    snapshot = container.document_service.repository.get_with_debug(document_id)
    if snapshot is None:
        raise HTTPException(404, "document_not_found")
    document, report = snapshot
    if report is None:
        raise HTTPException(404, "document_debug_not_found")
    study_units = document.study_units or report.study_units
    planning_context = build_learning_plan_context(
        study_units=study_units,
        debug_report=report,
    )
    payload = {
        "document_id": document_id,
        "document_revision": document.revision,
        "course_outline": planning_context["course_outline"],
        "study_units": [
            {**unit, "unit_id": unit["detail_tool_target_id"]}
            for unit in planning_context["study_units"]
        ],
        "detail_map": planning_context["detail_map"],
        "available_tools": get_learning_plan_tool_specs(
            study_units=study_units,
            detail_map=planning_context["detail_map"],
            debug_report=report,
            document_path=document.stored_path,
            multimodal_enabled=container.model_provider.supports_page_image_tools(),
        ),
    }
    return _into_response(DocumentPlanningContextResponse, payload)


@router.get(
    "/documents/{document_id}/planning-trace",
    response_model=DocumentPlanningTraceResponse,
)
def get_document_planning_trace(
    document_id: str, *, container: Container = Depends(get_container)
) -> DocumentPlanningTraceResponse:
    trace = container.store.load_item(
        "planning_trace", document_id, PlanGenerationTraceRecord
    )
    if trace is not None:
        tool_call_count = sum(
            len(round_record.tool_calls) for round_record in trace.rounds
        )
        latest_finish_reason = trace.rounds[-1].finish_reason if trace.rounds else ""
        return DocumentPlanningTraceResponse(
            document_id=document_id,
            has_trace=True,
            summary={
                "round_count": len(trace.rounds),
                "tool_call_count": tool_call_count,
                "latest_finish_reason": latest_finish_reason,
            },
            trace=trace.model_dump(mode="json"),
        )
    return DocumentPlanningTraceResponse(
        document_id=document_id,
        has_trace=False,
        summary={
            "round_count": 0,
            "tool_call_count": 0,
            "latest_finish_reason": "",
        },
        trace=None,
    )


@router.get("/documents/{document_id}/plan-events", response_model=StreamReportResponse)
def get_document_plan_events(
    document_id: str, *, container: Container = Depends(get_container)
) -> StreamReportResponse:
    report = StreamReportRecorder.load(
        store=container.store,
        category=LEARNING_PLAN_STREAM_CATEGORY,
        document_id=document_id,
        stream_kind="learning_plan",
    )
    return _into_response(StreamReportResponse, report)
