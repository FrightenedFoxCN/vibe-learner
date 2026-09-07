import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.core.settings import Settings

with TemporaryDirectory(prefix='vibe-goal-api-audit-') as directory:
    audit_settings = Settings(database_url=f'sqlite:///{directory}/audit.db', storage_root=directory, plan_provider='mock')
    with patch.object(Settings, 'from_env', return_value=audit_settings):
        from app.app_factory import create_app
        app = create_app()
        logging.disable(logging.CRITICAL)
        with TestClient(app, raise_server_exceptions=False) as client:
            for endpoint in ['/learning-plans', '/learning-plans/stream']:
                response = client.post(endpoint, json={'client_request_id': 'audit-goal-request', 'document_id': '', 'persona_id': 'mentor-aurora', 'objective': 'Learn introductory algebra'})
                print(json.dumps({'endpoint': endpoint, 'status': response.status_code, 'body': response.text}))
        with TestClient(app, raise_server_exceptions=True) as client:
            try:
                client.post('/learning-plans/stream', json={'client_request_id': 'audit-goal-request-detail', 'document_id': '', 'persona_id': 'mentor-aurora', 'objective': 'Learn algebra'})
            except Exception as error:
                print(json.dumps({'exception_type': type(error).__name__, 'exception': str(error)}))
        from app.core.bootstrap import container
        container.store.close()
