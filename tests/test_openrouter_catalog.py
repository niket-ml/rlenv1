from __future__ import annotations

import io
from unittest.mock import patch

from uc_bench.openrouter_catalog import fetch_model_endpoints, fetch_user_catalog


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


@patch("uc_bench.openrouter_catalog.urllib.request.urlopen")
def test_user_catalog_parses_non_secret_interface_and_pricing(urlopen) -> None:
    urlopen.return_value = FakeResponse(
        '{"data":[{"id":"vendor/model","canonical_slug":"vendor/model-20260101",'
        '"context_length":1000,"top_provider":{"max_completion_tokens":100},'
        '"supported_parameters":["tools","response_format"],'
        '"pricing":{"prompt":"0.000001","completion":"0.000002"}}]}'
    )
    model = fetch_user_catalog("secret")["vendor/model"]
    assert model.canonical_slug == "vendor/model-20260101"
    assert model.pricing["prompt"] == 0.000001
    request = urlopen.call_args.args[0]
    assert request.full_url.endswith("/models/user")
    assert "secret" not in repr(model.to_dict())


@patch("uc_bench.openrouter_catalog.urllib.request.urlopen")
def test_endpoint_route_preserves_model_organisation_separator(urlopen) -> None:
    urlopen.return_value = FakeResponse(
        '{"data":{"endpoints":[{"provider_name":"Provider",'
        '"model_name":"Model","supported_parameters":["max_tokens","tools"],'
        '"context_length":1000,"max_completion_tokens":100,'
        '"pricing":{"prompt":"0.000001"}}]}}'
    )
    endpoints = fetch_model_endpoints("secret", "vendor/model")
    assert endpoints[0]["provider_name"] == "Provider"
    assert endpoints[0]["supported_parameters"] == ["max_tokens", "tools"]
    request = urlopen.call_args.args[0]
    assert request.full_url.endswith("/models/vendor/model/endpoints")
