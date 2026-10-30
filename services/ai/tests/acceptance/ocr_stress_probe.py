"""Opt-in, offline neural OCR through the production Document API.

The parent runs one bounded child at a time and retains SQLite, raw observations,
API read-back and logs even on timeout. No production parser/engine is changed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import resource
import socket
import subprocess
import sys
import time
import traceback
import unicodedata


MODEL_HASHES = {
    "db_mobilenet_v3_large-4987e7bd.onnx": (
        "4987e7bdea372559808bd5add85fda10e179dc639696fb489e59a197a25b4c64"
    ),
    "parseq-00b40714.onnx": (
        "00b40714e00039c8c04891e5fd98ad5cb46c34fa7133ba09e2a55d4b28d42a68"
    ),
}
# Original, fixed prose; language labels describe fixtures, never detected language.
TEXTS = {
    "en": (
        "At sunrise we place three clean jars beside the window.",
        "Each jar receives the same amount of cool water.",
        "A small blue label records the initial temperature.",
        "We cover one jar and leave the other two open.",
        "After an hour we measure the water again.",
        "The notebook keeps every observation in order.",
        "A careful comparison may reveal a useful pattern.",
        "Tomorrow we repeat the procedure before drawing conclusions.",
    ),
    "fr": (
        "Au matin nous plaçons trois bocaux près de la fenêtre.",
        "Chaque bocal reçoit la même quantité d'eau fraîche.",
        "Une étiquette bleue indique la température initiale.",
        "Nous couvrons un bocal et laissons les autres ouverts.",
        "Après une heure nous mesurons encore l'eau.",
        "Le carnet conserve les observations dans leur ordre.",
        "Une comparaison précise révèle parfois une régularité.",
        "Demain nous répétons cette expérience avant de conclure.",
    ),
    "de": (
        "Am Morgen stellen wir drei Gläser neben das Fenster.",
        "Jedes Glas enthält die gleiche Menge kühles Wasser.",
        "Ein blaues Etikett zeigt die erste Temperatur.",
        "Wir schließen ein Glas und lassen die anderen offen.",
        "Nach einer Stunde messen wir das Wasser erneut.",
        "Das Heft bewahrt alle Beobachtungen in ihrer Reihenfolge.",
        "Ein genauer Vergleich erklärt mögliche Veränderungen.",
        "Morgen prüfen wir das Ergebnis mit einem neuen Versuch.",
    ),
    "zh": (
        "清晨我们把三个干净的玻璃杯放在窗边。",
        "每个杯子装入相同数量的凉水。",
        "蓝色标签记录最初测得的温度。",
        "我们盖住一个杯子其余两个保持敞开。",
        "一小时以后再次测量杯中的水。",
        "笔记本按照顺序保存每次观察。",
        "仔细比较数据可以发现变化的规律。",
        "明天重复实验以后再作出结论。",
    ),
}
SUPPORTED_CER_CEILING = 0.10  # A probe criterion, never an official support limit.


def write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def character_score(reference: str, hypothesis: str) -> dict:
    """Levenshtein CER and exact matches in a minimum-edit alignment.

    Among equal-cost alignments prefer more exact matches. Case, accents and
    punctuation remain significant. CER is not clamped when insertions exceed N.
    """
    reference, hypothesis = normalize(reference), normalize(hypothesis)
    if not reference:
        raise ValueError("ground_truth_must_not_be_empty")
    reference_length, hypothesis_length = len(reference), len(hypothesis)
    prefix = 0
    while (
        prefix < min(len(reference), len(hypothesis))
        and reference[prefix] == hypothesis[prefix]
    ):
        prefix += 1
    reference, hypothesis = reference[prefix:], hypothesis[prefix:]
    suffix = 0
    while (
        suffix < min(len(reference), len(hypothesis))
        and reference[-suffix - 1] == hypothesis[-suffix - 1]
    ):
        suffix += 1
    if suffix:
        reference, hypothesis = reference[:-suffix], hypothesis[:-suffix]
    previous = [(i, 0) for i in range(len(hypothesis) + 1)]
    for i, left in enumerate(reference, 1):
        current = [(i, 0)]
        for j, right in enumerate(hypothesis, 1):
            equal = left == right
            candidates = (
                (previous[j][0] + 1, previous[j][1]),
                (current[j - 1][0] + 1, current[j - 1][1]),
                (previous[j - 1][0] + (not equal), previous[j - 1][1] + equal),
            )
            current.append(min(candidates, key=lambda item: (item[0], -item[1])))
        previous = current
    errors, matches = previous[-1]
    matches += prefix + suffix
    return {
        "reference_characters": reference_length,
        "hypothesis_characters": hypothesis_length,
        "edit_distance": errors,
        "cer": errors / reference_length,
        "aligned_exact_matches": matches,
        "character_match_rate": matches / reference_length,
    }


def verify_models(cache: Path) -> list[dict]:
    """Allowlist exact files; verify prefix AND the supplied complete digest."""
    records = []
    for name, expected in MODEL_HASHES.items():
        path = cache / "models" / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"missing_or_symlink_model:{path}")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        prefix = name.rsplit("-", 1)[1].split(".")[0]
        if not actual.startswith(prefix) or actual != expected:
            raise ValueError(f"untrusted_model_digest:{name}:{actual}")
        records.append({"file": name, "bytes": path.stat().st_size, "sha256": actual})
    return records


def peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def block_network(attempts: list) -> None:
    # TestClient uses ASGI in-process, so no TCP, DNS or provider access is needed.
    def audit(event, args):
        if event == "socket.getaddrinfo" or (
            event == "socket.connect"
            and args[0].family in (socket.AF_INET, socket.AF_INET6)
        ):
            attempts.append({"event": event, "address": str(args[-1])})
            raise PermissionError("ocr_stress_network_forbidden")

    sys.addaudithook(audit)


def make_scan(
    root: Path, languages: list[str], layout: str = "sparse"
) -> tuple[bytes, list[dict]]:
    import fitz

    truth, images = [], {}
    with fitz.open() as scanned:
        for index, language in enumerate(languages, 1):
            lines = TEXTS[language] * (5 if layout == "dense" else 1)
            font_size = 11 if layout == "dense" else 14
            top, line_height = (55, 17) if layout == "dense" else (85, 35)
            if language not in images:
                with fitz.open() as source:
                    page = source.new_page(width=595, height=842)
                    for line_index, line in enumerate(lines):
                        if language != "zh":
                            if fitz.get_text_length(line, fontsize=font_size) > 505:
                                raise ValueError("fixture_line_exceeds_page_width")
                        page.insert_text(
                            (45, top + line_index * line_height),
                            line,
                            fontsize=font_size,
                            fontname="china-s" if language == "zh" else "helv",
                        )
                    images[language] = page.get_pixmap(
                        matrix=fitz.Matrix(2, 2), alpha=False
                    ).tobytes("png")
            page = scanned.new_page(width=595, height=842)
            page.insert_image(page.rect, stream=images[language])
            truth.append(
                {
                    "page_number": index,
                    "fixture_language": language,
                    "text": "\n".join(lines),
                    "raster_sha256": hashlib.sha256(images[language]).hexdigest(),
                }
            )
        content = scanned.tobytes(garbage=4, deflate=True, no_new_id=True)
    with fitz.open(stream=content, filetype="pdf") as check:
        if any(page.get_text().strip() or not page.get_images() for page in check):
            raise ValueError("fixture_not_image_only")
    (root / "scan.pdf").write_bytes(content)
    write_json(root / "ground-truth.json", truth)
    return content, truth


def score_pages(pages: list[dict], truth: list[dict], vocab: str) -> None:
    # Scoring runs outside the API request so it cannot consume its Harness budget.
    for observed in pages:
        if "cer" in observed:
            continue
        expected = truth[observed["page_number"] - 1]["text"]
        unsupported = sorted(set(normalize(expected)) - set(vocab) - {" "})
        score = character_score(expected, observed["text"])
        observed.update(score)
        observed["unsupported_characters"] = unsupported
        observed["quality"] = (
            "unsupported"
            if unsupported
            else "passed"
            if score["cer"] <= SUPPORTED_CER_CEILING
            else "failed"
        )
        observed["non_whitespace_score"] = character_score(
            "".join(normalize(expected).split()),
            "".join(normalize(observed["text"]).split()),
        )


def app_for(root: Path):
    from app.app_factory import create_app
    from app.core.settings import Settings

    return create_app(
        settings=Settings(
            database_url=f"sqlite:///{root / 'domain.db'}",
            storage_root=str(root / "data"),
            auto_migrate_local_data=False,
            plan_provider="mock",
            ocr_engine="onnxtr",
            onnxtr_model_dir=str(root / "model-binding"),
        )
    )


def configure_cpu(engine, cache: Path, threads: int) -> dict:
    """Real production predictor, explicit local paths and bounded CPU threads.

    Populate only the production engine's normal lazy-initialization fields.
    Missing paths reach real ORT initialization, whose exception is retained;
    extract_page_text and every parser/API/commit boundary remain production code.
    """
    from onnxruntime import ExecutionMode, SessionOptions
    from onnxtr.models import db_mobilenet_v3_large, ocr_predictor, parseq
    from onnxtr.models.engine import EngineConfig

    options = SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.execution_mode = ExecutionMode.ORT_SEQUENTIAL
    config = EngineConfig(providers=["CPUExecutionProvider"], session_options=options)
    started = time.perf_counter()
    engine._predictor = None
    engine._load_attempted = True
    engine._load_error = ""
    try:
        engine._predictor = ocr_predictor(
            det_arch=db_mobilenet_v3_large(
                str(cache / "models" / next(iter(MODEL_HASHES))), engine_cfg=config
            ),
            reco_arch=parseq(
                str(cache / "models" / "parseq-00b40714.onnx"), engine_cfg=config
            ),
            assume_straight_pages=True,
            straighten_pages=False,
            resolve_blocks=False,
        )
        engine._model_id = "db_mobilenet_v3_large+parseq"
    except Exception as exc:
        engine._load_error = f"onnxtr_predictor_init_failed:{exc}"
    return {
        "initialization_seconds": time.perf_counter() - started,
        "providers": config.providers,
        "intra_op_threads": threads,
        "inter_op_threads": 1,
        "error": engine._load_error,
        "detector_path": str(cache / "models" / next(iter(MODEL_HASHES))),
        "recognizer_path": str(cache / "models" / "parseq-00b40714.onnx"),
    }


def accepted(response) -> dict:
    if response.status_code != 200:
        raise RuntimeError(f"http_{response.status_code}:{response.text[:1000]}")
    return response.json()


def read_evidence(client, app, document_id: str) -> dict:
    from app.persistence.harness_runtime_repository import HarnessRuntimeRepository

    service = app.state.container.document_service
    operation = service.process_repository.latest(
        document_id=document_id, validate_read_back=False
    )
    result = {
        "status": accepted(client.get(f"/documents/{document_id}/status")),
        "operation": operation.model_dump(mode="json") if operation else None,
    }
    if operation:
        result["checkpoint"] = accepted(
            client.get(f"/documents/{document_id}/checkpoints/{operation.operation_id}")
        )
        snapshot = service.checkpoints.snapshot(operation.operation_id)
        result["durable_pages"] = [
            page.model_dump(mode="json") for page in snapshot.pages
        ]
        binding = service.process_repository.require_harness_operation(
            operation.operation_id
        )
        traces = HarnessRuntimeRepository(
            app.state.container.database
        ).list_operation_traces(binding.harness_operation_id)
        result["harness"] = [
            {
                "trace_id": trace.trace_id,
                "stage": trace.stage.value,
                "terminal": trace.terminal_trace.model_dump(mode="json")
                if trace.terminal_trace
                else None,
            }
            for trace in traces
        ]
    debug = client.get(f"/documents/{document_id}/debug")
    result["debug_http_status"] = debug.status_code
    if debug.status_code == 200:
        result["debug"] = debug.json()
    return result


def committed(evidence: dict) -> bool:
    return (
        evidence["status"]["status"] == "processed"
        and evidence["operation"]["status"] == "committed"
        and evidence["checkpoint"]["projection_state"] == "committed"
        and any(
            trace["stage"] == "document_parse"
            and trace["terminal"]
            and trace["terminal"]["commit_evidence"]["status"] == "committed"
            for trace in evidence["harness"]
        )
    )


def worker(args) -> None:
    root = args.root
    state_root = args.state_dir or root
    network = []
    block_network(network)
    started = time.perf_counter()
    result = {"case": args.worker, "network_attempts": network, "ocr_pages": []}
    try:
        from fastapi.testclient import TestClient

        if args.worker == "inspect":
            app = app_for(state_root)
            with TestClient(app, raise_server_exceptions=False) as client:
                result["read_back"] = read_evidence(
                    client, app, (state_root / "document-id").read_text()
                )
            return
        from onnxtr.utils import VOCABS

        result["models"] = verify_models(args.cache_dir)
        result["versions"] = {
            name: version(name) for name in ("onnxtr", "onnxruntime", "PyMuPDF")
        }
        result["platform"] = platform.platform()
        result["python"] = sys.version
        result["quality_cer_ceiling"] = SUPPORTED_CER_CEILING
        languages = (
            [list(TEXTS)[index % len(TEXTS)] for index in range(args.pages)]
            if args.worker == "stress"
            else [args.worker.removeprefix("baseline-")]
            if args.worker.startswith("baseline-")
            else ["en"]
        )
        if args.worker == "resume":
            prior = json.loads((state_root / "result.json").read_text())
            if prior.get("case") not in ("stress", "resume"):
                raise ValueError("resume_requires_an_existing_stress_probe")
            truth = json.loads((state_root / "ground-truth.json").read_text())
            content = (state_root / "scan.pdf").read_bytes()
            write_json(root / "ground-truth.json", truth)
        else:
            content, truth = make_scan(root, languages, args.layout)
        result["fixture"] = {
            "pages": len(truth),
            "image_only": True,
            "pdf_bytes": len(content),
            "pdf_sha256": hashlib.sha256(content).hexdigest(),
            "raster_scale": 2,
            "layout": args.layout,
            "lines_per_page": 40 if args.layout == "dense" else 8,
            "font_size": 11 if args.layout == "dense" else 14,
            "latin_font": "helv",
            "chinese_font": "china-s",
            "ground_truth": "ground-truth.json",
        }
        if args.worker == "resume":
            result["fixture"] = prior["fixture"]
        model_binding = state_root / "model-binding"
        model_binding.mkdir(exist_ok=args.worker == "resume")
        missing = args.worker == "missing-model"
        if not missing and args.worker != "resume":
            for name in MODEL_HASHES:
                os.link(args.cache_dir / "models" / name, model_binding / name)
        app = app_for(state_root)
        with TestClient(app, raise_server_exceptions=False) as client:
            engine = app.state.container.document_parser.ocr_engine
            result["cpu"] = configure_cpu(
                engine,
                root / "absent-model-cache" if missing else args.cache_dir,
                args.threads,
            )
            if not missing and result["cpu"]["error"]:
                raise RuntimeError(result["cpu"]["error"])
            original_extract = engine.extract_page_text

            def observe(page):
                before = time.perf_counter()
                observed = original_extract(page)
                expected = truth[page.number]
                result["ocr_pages"].append(
                    {
                        "page_number": page.number + 1,
                        "fixture_language": expected["fixture_language"],
                        "seconds": time.perf_counter() - before,
                        "peak_rss_bytes_so_far": peak_rss_bytes(),
                        "text": observed.text,
                        "ocr_status": observed.status,
                        "language_hint": observed.language_hint,
                        "warning": observed.warning,
                    }
                )
                write_json(root / "progress.json", result)
                return observed

            # Instrument the real call, returning its exact unmodified result.
            engine.extract_page_text = observe
            checkpoints = app.state.container.document_service.checkpoints
            original_save_page = checkpoints.save_page
            result["page_checkpoint_writes"] = []

            def observe_save(operation_id, parsed):
                original_save_page(operation_id, parsed)
                saved = checkpoints.snapshot(operation_id)
                result["page_checkpoint_writes"].append(
                    {
                        "operation_id": operation_id,
                        "page_number": parsed.page_number,
                        "durable_page_count": len(saved.pages),
                        "storage_limited": saved.storage_limited,
                        "elapsed_seconds": time.perf_counter() - started,
                    }
                )
                write_json(root / "progress.json", result)

            checkpoints.save_page = observe_save
            upload_content = (
                b"invalid synthetic PDF bytes"
                if args.worker == "invalid-pdf"
                else content
            )
            payload = {"force_ocr": True}
            if args.worker == "resume":
                document_id = (state_root / "document-id").read_text()
                result["resume_source"] = read_evidence(client, app, document_id)
                source = result["resume_source"]["operation"]
                if source["status"] not in ("failed", "interrupted"):
                    raise ValueError("resume_requires_failed_or_interrupted_operation")
                payload["resume_from_operation_id"] = source["operation_id"]
            else:
                document_id = accepted(
                    client.post(
                        "/documents",
                        files={
                            "file": (
                                "synthetic-scan.pdf",
                                upload_content,
                                "application/pdf",
                            )
                        },
                    )
                )["id"]
            (root / "document-id").write_text(document_id)
            before = time.perf_counter()
            response = client.post(f"/documents/{document_id}/process", json=payload)
            result["process_seconds"] = time.perf_counter() - before
            result["process_http_status"] = response.status_code
            result["process_response"] = (
                response.json() if response.status_code != 500 else response.text
            )
            result["read_back"] = read_evidence(client, app, document_id)
            score_pages(result["ocr_pages"], truth, VOCABS["french"])
            write_json(root / "progress.json", result)
            if args.worker in ("invalid-pdf", "missing-model"):
                failed = result["read_back"]
                if (
                    failed["operation"]["status"] != "failed"
                    or failed["checkpoint"]["projection_state"] != "checkpoint_only"
                    or failed["debug_http_status"] != 404
                ):
                    raise AssertionError("failure_must_not_claim_document_commit")
                if missing:
                    if not result["cpu"]["error"] or any(
                        p["ocr_status"] != "unavailable" for p in result["ocr_pages"]
                    ):
                        raise AssertionError(
                            "missing_model_not_observed_as_unavailable"
                        )
                    for name in MODEL_HASHES:
                        os.link(args.cache_dir / "models" / name, model_binding / name)
                    result["recovery_cpu"] = configure_cpu(
                        engine, args.cache_dir, args.threads
                    )
                    resume = client.post(
                        f"/documents/{document_id}/process",
                        json={
                            "force_ocr": True,
                            "resume_from_operation_id": failed["operation"][
                                "operation_id"
                            ],
                        },
                    )
                    result["changed_configuration_resume"] = {
                        "http_status": resume.status_code,
                        "body": resume.json(),
                    }
                    if (
                        resume.status_code != 409
                        or resume.json().get("detail")
                        != "document_checkpoint_input_changed"
                    ):
                        raise AssertionError(
                            "changed_model_configuration_was_not_fenced"
                        )
                else:
                    document_id = accepted(
                        client.post(
                            "/documents",
                            files={
                                "file": (
                                    "replacement-scan.pdf",
                                    content,
                                    "application/pdf",
                                )
                            },
                        )
                    )["id"]
                accepted(
                    client.post(
                        f"/documents/{document_id}/process", json={"force_ocr": True}
                    )
                )
                result["recovery"] = read_evidence(client, app, document_id)
                score_pages(result["ocr_pages"], truth, VOCABS["french"])
                if not committed(result["recovery"]):
                    raise AssertionError("recovery_not_committed")
                result["execution"] = "passed"
            else:
                result["execution"] = (
                    "passed" if committed(result["read_back"]) else "failed"
                )
                if args.worker == "resume" and result["execution"] == "passed":
                    calls = len(result["ocr_pages"])
                    duplicate = accepted(
                        client.post(f"/documents/{document_id}/process", json=payload)
                    )
                    result["duplicate_resume"] = {
                        "same_projection": duplicate == response.json(),
                        "new_ocr_calls": len(result["ocr_pages"]) - calls,
                    }
                    if (
                        duplicate != response.json()
                        or len(result["ocr_pages"]) != calls
                    ):
                        raise AssertionError(
                            "completed_resume_replayed_or_changed_projection"
                        )
        # Fresh application reads persisted state without predictor construction.
        app = app_for(state_root)
        with TestClient(app, raise_server_exceptions=False) as client:
            result["restart_read_back"] = read_evidence(client, app, document_id)
        result["restart_matches"] = result["restart_read_back"] == result.get(
            "recovery", result["read_back"]
        )
        if not result["restart_matches"] or network:
            result["execution"] = "failed"
    except Exception:
        result["execution"] = "failed"
        result["error"] = traceback.format_exc()
    finally:
        result["worker_seconds"] = time.perf_counter() - started
        result["peak_rss_bytes"] = peak_rss_bytes()
        write_json(
            root / ("inspection.json" if args.worker == "inspect" else "result.json"),
            result,
        )


def run_child(args, case: str, root: Path, *, pages=1, inspect=False) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        case,
        "--root",
        str(root),
        "--cache-dir",
        str(args.cache_dir),
        "--threads",
        str(args.threads),
        "--pages",
        str(pages),
        "--layout",
        args.layout,
    ]
    if args.resume_artifacts:
        command.extend(["--state-dir", str(args.resume_artifacts)])
    env = {
        **os.environ,
        "ONNXTR_CACHE_DIR": str(args.cache_dir),
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "OMP_NUM_THREADS": str(args.threads),
        "OPENBLAS_NUM_THREADS": str(args.threads),
        "VECLIB_MAXIMUM_THREADS": str(args.threads),
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
    }
    limit = (
        30
        if inspect
        else args.stress_timeout
        if case in ("stress", "resume")
        else args.baseline_timeout
    )
    before = time.perf_counter()
    log = root / ("inspection.log" if inspect else "worker.log")
    with log.open("w") as stream:
        try:
            child = subprocess.run(
                command, env=env, stdout=stream, stderr=stream, timeout=limit
            )
            outcome = {"exit_code": child.returncode, "timed_out": False}
        except subprocess.TimeoutExpired:
            outcome = {"exit_code": None, "timed_out": True}
    outcome.update(
        {"wall_seconds": time.perf_counter() - before, "timeout_seconds": limit}
    )
    if inspect:
        return outcome
    result_file = root / "result.json"
    if result_file.exists():
        outcome["result"] = json.loads(result_file.read_text())
    elif (root / "progress.json").exists():
        outcome["partial"] = json.loads((root / "progress.json").read_text())
    if (outcome["timed_out"] or outcome["exit_code"] != 0) and (
        root / "document-id"
    ).exists():
        outcome["inspection"] = run_child(args, "inspect", root, inspect=True)
    outcome["artifacts"] = str(root)
    return outcome


def checkpoints_cover_calls(attempt: dict) -> bool:
    writes = attempt["page_checkpoint_writes"]
    saved_count = attempt["read_back"]["checkpoint"]["completed_page_count"]
    numbers = [row["page_number"] for row in writes]
    # Resume copies the authorized prefix into the child checkpoint, without OCR.
    return (
        numbers == list(range(1, saved_count + 1))
        and all(
            row["durable_page_count"] == row["page_number"]
            and not row["storage_limited"]
            and row["operation_id"] == attempt["read_back"]["operation"]["operation_id"]
            for row in writes
        )
        and all(page["page_number"] in numbers for page in attempt["ocr_pages"])
    )


def summarize_chain(directories: list[Path]) -> dict:
    """Independently re-read the final database and retain historical failures."""
    attempts = [json.loads((path / "result.json").read_text()) for path in directories]
    if attempts[0]["case"] != "stress" or any(
        item["case"] != "resume" for item in attempts[1:]
    ):
        raise ValueError("chain_requires_stress_then_explicit_resumes")
    pages = [page for attempt in attempts for page in attempt["ocr_pages"]]
    count = attempts[0]["fixture"]["pages"]
    operations = [
        attempt["read_back"]["operation"]["operation_id"] for attempt in attempts
    ]
    network = []
    block_network(network)
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    from fastapi.testclient import TestClient

    app = app_for(directories[0])
    with TestClient(app, raise_server_exceptions=False) as client:
        service = app.state.container.document_service
        document_id = attempts[0]["read_back"]["status"]["id"]
        fresh = read_evidence(client, app, document_id)
        bindings = [
            service.process_repository.require_harness_operation(item)
            for item in operations
        ]
        relations = [service.checkpoints.resume_child(item) for item in operations[:-1]]
    budget_failures = [
        {
            "operation_id": operations[index],
            "error_codes": [
                trace["terminal"].get("error_code")
                for trace in item["read_back"]["harness"]
                if trace["terminal"]
            ],
            "saved_pages": item["read_back"]["checkpoint"]["completed_page_count"],
            "process_seconds": item["process_seconds"],
        }
        for index, item in enumerate(attempts[:-1])
    ]
    durable = fresh["durable_pages"]
    checks = {
        "all_pages_recognized_exactly_once": [page["page_number"] for page in pages]
        == list(range(1, count + 1)),
        "every_ocr_page_was_checkpointed": all(
            checkpoints_cover_calls(item) for item in attempts
        ),
        "all_durable_text_matches_real_observation": len(durable) == count
        and all(
            stored["page_number"] == observed["page_number"]
            and stored["ocr_result"]["text"] == observed["text"]
            and stored["ocr_result"]["status"] == "completed"
            for stored, observed in zip(durable, pages, strict=True)
        ),
        "distinct_operation_and_harness_identities": len(set(operations))
        == len(operations)
        and len({binding.harness_operation_id for binding in bindings})
        == len(operations),
        "exact_source_child_chain": relations == operations[1:],
        "historical_failures_are_expected_budget_failures": all(
            "harness_runtime_wall_time_budget_exceeded" in item["error_codes"]
            for item in budget_failures
        ),
        "final_document_commit_and_fresh_api_readback": committed(fresh)
        and fresh == attempts[-1]["read_back"],
        "duplicate_resume_does_not_replay": attempts[-1].get("duplicate_resume")
        == {"same_projection": True, "new_ocr_calls": 0},
        "no_network_or_fabricated_language_hint": not network
        and all(not item["network_attempts"] for item in attempts)
        and all(page["language_hint"] is None for page in pages),
    }
    measurements = {}
    for language in TEXTS:
        selected = [page for page in pages if page["fixture_language"] == language]
        if not selected:
            continue
        n = sum(page["reference_characters"] for page in selected)
        content_n = sum(
            page["non_whitespace_score"]["reference_characters"] for page in selected
        )
        measurements[language] = {
            "pages": len(selected),
            "cer": sum(page["edit_distance"] for page in selected) / n,
            "character_match_rate": sum(
                page["aligned_exact_matches"] for page in selected
            )
            / n,
            "non_whitespace_cer": sum(
                page["non_whitespace_score"]["edit_distance"] for page in selected
            )
            / content_n,
            "non_whitespace_character_match_rate": sum(
                page["non_whitespace_score"]["aligned_exact_matches"]
                for page in selected
            )
            / content_n,
            "unsupported_characters": sorted(
                {
                    character
                    for page in selected
                    for character in page["unsupported_characters"]
                }
            ),
        }
    return {
        "schema_version": "ocr-stress-recovery-chain-v1",
        "scope": "Recovered workflow outcome; historical failed attempts remain failed in their original reports.",
        "checks": checks,
        "execution_failures": [name for name, passed in checks.items() if not passed],
        "supported_vocabulary_quality_failures": [
            page["page_number"] for page in pages if page["quality"] == "failed"
        ],
        "historical_budget_failures": budget_failures,
        "operations": [binding.model_dump(mode="json") for binding in bindings],
        "measurements": measurements,
        "process_seconds_total": sum(item["process_seconds"] for item in attempts),
        "worker_seconds_total": sum(item["worker_seconds"] for item in attempts),
        "peak_rss_bytes": max(item["peak_rss_bytes"] for item in attempts),
        "source_artifacts": [str(path) for path in directories],
        "final_read_back": fresh,
    }


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/vibe-ocr-models"))
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--stress-pages", type=int, nargs="+", default=[16])
    parser.add_argument(
        "--summarize-chain",
        type=Path,
        nargs="+",
        help="Ordered original stress case and resume case directories; verify final state without OCR",
    )
    parser.add_argument("--layout", choices=("sparse", "dense"), default="sparse")
    parser.add_argument(
        "--resume-artifacts",
        type=Path,
        help="Resume the latest failed operation in an existing stress case directory",
    )
    parser.add_argument("--baseline-timeout", type=int, choices=(180,), default=180)
    parser.add_argument(
        "--stress-timeout", type=int, choices=(180, 300, 600), default=300
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=("baseline", "stress", "invalid-pdf", "missing-model"),
        default=["baseline", "stress", "invalid-pdf", "missing-model"],
    )
    parser.add_argument(
        "--worker",
        choices=tuple(f"baseline-{key}" for key in TEXTS)
        + ("stress", "invalid-pdf", "missing-model", "inspect", "resume"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--state-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--pages", type=int, default=1, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.threads <= 4 or any(
        not 1 <= count <= 512 for count in args.stress_pages
    ):
        parser.error("threads must be 1..4; stress pages must be 1..512")
    if args.worker:
        worker(args)
        return
    if not args.output_dir:
        parser.error("--output-dir is required; use a fresh directory under /tmp")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": "ocr-stress-probe-v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Local synthetic scans only; no language, platform or support-limit certification.",
        "arguments": {
            "threads": args.threads,
            "layout": args.layout,
            "stress_pages": args.stress_pages,
            "baseline_timeout": args.baseline_timeout,
            "stress_timeout": args.stress_timeout,
            "resume_artifacts": str(args.resume_artifacts)
            if args.resume_artifacts
            else None,
        },
        "cases": {},
    }
    try:
        report["models"] = verify_models(args.cache_dir)
    except ValueError as exc:
        report["preflight_error"] = str(exc)
        write_json(args.output_dir / "report.json", report)
        raise SystemExit(1) from exc
    if args.summarize_chain:
        try:
            summary = summarize_chain(args.summarize_chain)
        except Exception:
            write_json(
                args.output_dir / "report.json",
                {
                    "schema_version": "ocr-stress-recovery-chain-v1",
                    "execution_failures": ["summary_readback_failed"],
                    "error": traceback.format_exc(),
                },
            )
            raise SystemExit(1)
        write_json(args.output_dir / "report.json", summary)
        raise SystemExit(
            bool(
                summary["execution_failures"]
                or summary["supported_vocabulary_quality_failures"]
            )
        )
    jobs = []
    for case in args.cases:
        if case == "baseline":
            jobs.extend(
                (f"baseline-{language}", f"baseline-{language}", 1)
                for language in TEXTS
            )
        elif case == "stress":
            jobs.extend(
                (f"stress-{count}", "stress", count) for count in args.stress_pages
            )
        else:
            jobs.append((case, case, 1))
    if args.resume_artifacts:
        jobs = [("resume", "resume", 1)]
    for name, case, pages in jobs:
        report["cases"][name] = run_child(
            args, case, args.output_dir / name, pages=pages
        )
        write_json(args.output_dir / "report.json", report)
        outcome = report["cases"][name]
        print(
            json.dumps(
                {
                    "case": name,
                    "timed_out": outcome["timed_out"],
                    "wall_seconds": outcome["wall_seconds"],
                    "execution": outcome.get("result", {}).get("execution", "failed"),
                }
            ),
            flush=True,
        )
    failures = [
        name
        for name, item in report["cases"].items()
        if item["timed_out"]
        or item["exit_code"] != 0
        or item.get("result", {}).get("execution") != "passed"
    ]
    quality_failures = [
        name
        for name, item in report["cases"].items()
        if any(
            page.get("quality") == "failed"
            for page in item.get("result", {}).get("ocr_pages", [])
            if page["ocr_status"] == "completed"
        )
    ]
    report["execution_failures"] = failures
    report["supported_vocabulary_quality_failures"] = quality_failures
    report["unsupported_fixtures"] = sorted(
        {
            page["fixture_language"]
            for item in report["cases"].values()
            for page in item.get("result", {}).get("ocr_pages", [])
            if page.get("quality") == "unsupported"
        }
    )
    write_json(args.output_dir / "report.json", report)
    raise SystemExit(bool(failures or quality_failures))


if __name__ == "__main__":
    main()
