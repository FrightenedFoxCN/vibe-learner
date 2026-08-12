from __future__ import annotations

import unittest

from app.models.tavern_integrity import persona_prompt_hash, tavern_payload_digest


class TavernIntegrityTests(unittest.TestCase):
    def test_legacy_digest_bytes_remain_stable(self) -> None:
        payload = {"b": 2, "a": 1}

        self.assertEqual(tavern_payload_digest(payload), "d8497d9d82770a70")
        self.assertEqual(persona_prompt_hash(payload), "d8497d9d82770a70")


if __name__ == "__main__":
    unittest.main()
