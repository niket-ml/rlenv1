#!/usr/bin/env python3
"""Check account-filtered Astra catalog metadata without making an inference request."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.model_runner import load_openrouter_key

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "openai/gpt-6-astra"
CATALOG_URL = "https://openrouter.ai/api/v1/models/user"


def _get_user_models(key: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        CATALOG_URL,
        method="GET",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "UC-Bench/0.1 read-only availability audit",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(response.status)
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        value = json.loads(exc.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise TypeError("OpenRouter user-model response is not an object")
    return status, value


def main() -> int:
    key = load_openrouter_key(PROJECT_ROOT)
    status, response = _get_user_models(key)
    data = response.get("data")
    rows = data if isinstance(data, list) else []
    matches = [row for row in rows if isinstance(row, dict) and row.get("id") == MODEL_ID]
    model = matches[0] if len(matches) == 1 else {}
    supported = set(str(value) for value in model.get("supported_parameters") or [])
    output = {
        "schema_version": "0.1",
        "checked_at": datetime.now(UTC).isoformat(),
        "request_method": "GET",
        "catalog_endpoint": CATALOG_URL,
        "chat_or_response_completion_requested": False,
        "http_status": status,
        "authenticated_account_filtered_catalog": status == 200,
        "model_id": MODEL_ID,
        "listed_for_account": len(matches) == 1,
        "tool_calling_supported": "tools" in supported,
        "tool_choice_supported": "tool_choice" in supported,
        "available_for_account_tool_canary": (
            status == 200 and len(matches) == 1 and "tools" in supported
        ),
        "supported_parameters": sorted(supported),
        "context_length": model.get("context_length"),
        "pricing": model.get("pricing"),
        "per_request_limits": model.get("per_request_limits"),
        "error": response.get("error") if status != 200 else None,
    }
    output_path = PROJECT_ROOT / "artifacts" / "runtime" / "astra_availability.json"
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["available_for_account_tool_canary"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
