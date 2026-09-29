from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from uc_bench.openrouter import fetch_credit_balance, fetch_key_status


class FakeResponse:
    status = 200

    def __init__(self, body: str) -> None:
        self.body = io.BytesIO(body.encode())

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body.read()


class OpenRouterAccountTests(unittest.TestCase):
    @patch("uc_bench.openrouter.urllib.request.urlopen")
    def test_key_status_keeps_only_non_secret_fields(self, urlopen) -> None:
        urlopen.return_value = FakeResponse(
            '{"data":{"usage":1.25,"limit":10,"limit_remaining":8.75,'
            '"is_free_tier":false,"label":"secret label"}}'
        )
        status = fetch_key_status("secret-key")
        self.assertEqual(status.usage_usd, 1.25)
        self.assertEqual(status.limit_remaining_usd, 8.75)
        self.assertNotIn("secret", status.to_dict())

    @patch("uc_bench.openrouter.urllib.request.urlopen")
    def test_credit_balance_is_computed(self, urlopen) -> None:
        urlopen.return_value = FakeResponse(
            '{"data":{"total_credits":10,"total_usage":2.5}}'
        )
        self.assertEqual(fetch_credit_balance("secret-key")["remaining_usd"], 7.5)


if __name__ == "__main__":
    unittest.main()
