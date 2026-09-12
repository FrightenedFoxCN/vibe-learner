import json
import tempfile
import unittest
from pathlib import Path
from model_quality.export import export


class PrivateExportTests(unittest.TestCase):
    def test_one_private_case_blocks_entire_export_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);campaign=root/'campaign';campaign.mkdir()
            (campaign/'manifest.json').write_text(json.dumps({'config':{'cases':[
                {'provenance':'public-licensed'}, {'provenance':'user-provided'}]}}))
            output=root/'evidence.zip'
            with self.assertRaisesRegex(ValueError,'private or unreviewed'):
                export([campaign],root/'ledger.sqlite3',output)
            self.assertFalse(output.exists())
