import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from model_quality.export import export
from model_quality.runner import run
from tests.test_infrastructure import config


class ExportTests(unittest.TestCase):
    def test_portable_evidence_hashes_and_secret_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            run(config(),root/'run',root/'ledger.sqlite3')
            note=root/'handoff.md';note.write_text('Review scope and results.')
            result=export([root/'run'],root/'ledger.sqlite3',root/'evidence.zip',{'docs/handoff.md':note})
            self.assertGreater(result['files'],5)
            with zipfile.ZipFile(root/'evidence.zip') as archive:
                self.assertEqual(archive.read('docs/handoff.md'),b'Review scope and results.')
                index=json.loads(archive.read('index.json'))
                for name,record in index['files'].items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),record['sha256'])
                self.assertFalse(any(name.endswith('.sqlite3') for name in archive.namelist()))
            report=root/'run/report.json'
            payload=json.loads(report.read_text());payload['secret_canary']='never-export-this-credential'
            report.write_text(json.dumps(payload))
            with patch.dict('os.environ',{'K3_API_KEY':'never-export-this-credential'}):
                with self.assertRaises(ValueError):
                    export([root/'run'],root/'ledger.sqlite3',root/'blocked.zip')
            self.assertFalse((root/'blocked.zip').exists())

    def test_tool_shape_telemetry_omits_content_and_unknown_keys(self):
        from model_quality.transport import tool_call_shape
        value=tool_call_shape({'id':'private-id','type':'function','index':0,
            'function':{'name':'private-name','arguments':'private-content'},'private-field':'private-value'})
        self.assertEqual(value['unknown_field_count'],1)
        self.assertNotIn('private',json.dumps(value))

    def test_nested_execution_snapshot_validates_hash_and_credential_bytes(self):
        from model_quality.export import validate_source_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.zip';data=b'private-source-canary'
            index={'campaign':'c','git_revision':'r','files':{'code.py':hashlib.sha256(data).hexdigest()}}
            with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('code.py',data);archive.writestr('source-index.json',json.dumps(index))
            manifest={'config':{'id':'c'},'source':{'git_revision':'r'}}
            validate_source_snapshot(path,manifest)
            with patch.dict('os.environ',{'K3_API_KEY':'private-source-canary'}):
                with self.assertRaises(ValueError):validate_source_snapshot(path,manifest)
            manifest['config']['id']='wrong'
            with self.assertRaises(ValueError):validate_source_snapshot(path,manifest)
