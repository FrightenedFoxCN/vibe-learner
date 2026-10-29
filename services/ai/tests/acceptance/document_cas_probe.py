"""Provider-free HTTP probe with a real PDF parser and fresh application instances.

Run from services/ai with PYTHONPATH=. uv run python tests/acceptance/document_cas_probe.py.
All database/filesystem effects are confined to an automatically removed directory.
"""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.settings import Settings


def accepted(response, expected=200):
    assert response.status_code == expected, (response.status_code, response.text[:1000])
    return response.json()


pdf = fitz.open()
for index in range(3):
    page = pdf.new_page()
    page.insert_text((50, 50), f"Chapter {index + 1}: Vector spaces")
    page.insert_textbox(
        fitz.Rect(50, 90, 550, 720),
        "\n".join(
            f"Example {index * 20 + line}: A vector has magnitude and direction. "
            "Linear transformations preserve vector addition and scalar multiplication."
            for line in range(20)
        ),
        fontsize=10,
    )
pdf_bytes = pdf.tobytes()
pdf.close()
with TemporaryDirectory(prefix="vibe-document-cas-http-") as folder:
    root = Path(folder)
    settings = Settings(
        database_url=f"sqlite:///{root / 'app.db'}",
        storage_root=str(root / "data"),
        auto_migrate_local_data=False,
        plan_provider="mock",
    )
    with TestClient(create_app(settings=settings)) as client:
        with ThreadPoolExecutor(max_workers=3) as pool:
            documents = list(pool.map(
                lambda index: accepted(client.post(
                    "/documents", files={"file": (f"book-{index}.pdf", pdf_bytes, "application/pdf")}
                )),
                range(3),
            ))
        assert len(accepted(client.get("/documents"))["items"]) == 3
        document_id = documents[0]["id"]
        processed = accepted(client.post(f"/documents/{document_id}/process"))
        assert processed["revision"] == 2
        unit_id = processed["study_units"][0]["id"]
        url = f"/documents/{document_id}/study-units/{unit_id}"
        renamed = accepted(client.patch(url, json={"title": "HTTP persisted title", "expected_revision": 2}))
        assert renamed["document"]["revision"] == 3
        rejected = accepted(client.patch(url, json={"title": "Stale overwrite", "expected_revision": 2}), 409)
        assert rejected["detail"] == "document_revision_conflict"
        accepted(client.patch(url, json={"title": "Missing revision"}), 422)
    with TestClient(create_app(settings=settings)) as client:
        restored = accepted(client.get(f"/documents/{document_id}/status"))
        debug = accepted(client.get(f"/documents/{document_id}/debug"))
        assert restored["revision"] == 3
        assert restored["study_units"][0]["title"] == "HTTP persisted title"
        assert debug["study_units"][0]["title"] == "HTTP persisted title"
        assert len(accepted(client.get("/documents"))["items"]) == 3
    print(json.dumps({"concurrent_uploads": 3, "actual_pdf_parse": "passed", "revision": 3,
                      "stale_patch": 409, "missing_revision": 422, "http_restart_readback": "passed"}))
