"""Full-stack request normalization for the infrastructure-only v0.6.2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _temporary_environment
from uc_bench.v06_provider import _as_dict
from uc_bench.v061_provider import (
    V061AuditedOpenRouterClient,
    V061ProviderAdapter,
    V061RequestLedger,
    load_v061_provider_adapters,
    v061_client_config,
)

INTEGRATION_COMPATIBILITY_PATH = Path(
    "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility.json"
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


class V062AuditedOpenRouterClient(V061AuditedOpenRouterClient):
    """Normalize Verifiers' one-sample default before route filtering."""

    async def get_native_response(
        self,
        prompt: Any,
        model: str,
        sampling_args: Any,
        tools: Any = None,
        **kwargs: Any,
    ) -> Any:
        normalized = dict(sampling_args)
        injected_n = normalized.pop("n", None)
        state_present = "state" in kwargs
        kwargs.pop("state", None)
        if injected_n is not None and (
            not isinstance(injected_n, int)
            or isinstance(injected_n, bool)
            or injected_n != 1
        ):
            raise ConfigurationError(
                "v0.6.2 may normalize only Verifiers' redundant n=1 default"
            )
        annotation = {
            "input_n": injected_n,
            "removed_redundant_n_equals_one": injected_n == 1,
            "removed_nontransport_state_object": state_present,
            "semantic_rollout_count_unchanged": True,
        }
        prompt_rows = [_as_dict(message) for message in prompt]
        prompt_contract = {
            "message_count": len(prompt_rows),
            "roles": [row.get("role") for row in prompt_rows],
            "tool_result_message_count": sum(
                row.get("role") == "tool" for row in prompt_rows
            ),
            "assistant_reasoning_state_message_count": sum(
                row.get("role") == "assistant"
                and any(
                    row.get(field)
                    for field in ("reasoning", "reasoning_content", "reasoning_details")
                )
                for row in prompt_rows
            ),
        }
        before = len(self.ledger.records)
        try:
            response = await super().get_native_response(
                prompt,
                model,
                normalized,
                tools,
                **kwargs,
            )
        except Exception:
            if len(self.ledger.records) > before:
                row = self.ledger.records[-1]
                row["runner_normalization"] = annotation
                row["prompt_state_contract"] = prompt_contract
                self.ledger._checkpoint()  # noqa: SLF001 - audited request boundary
            raise
        row = self.ledger.records[-1]
        row["runner_normalization"] = annotation
        row["prompt_state_contract"] = prompt_contract
        self.ledger._checkpoint()  # noqa: SLF001 - audited request boundary
        return response


def load_v062_provider_adapters(
    project_root: Path,
) -> dict[str, V061ProviderAdapter]:
    """Load exact adapters only after the full Verifiers-stack gate passes."""

    root = project_root.resolve()
    adapters = load_v061_provider_adapters(root)
    result = _read_object(root / INTEGRATION_COMPATIBILITY_PATH)
    if (
        result.get("status") != "passed"
        or result.get("scientific_requests") != 0
        or result.get("heldout_requests") != 0
        or result.get("astra_requests") != 0
        or result.get("model_adapter_pass_count") != len(adapters)
    ):
        raise ConfigurationError("v0.6.2 full-stack compatibility is not clean")
    rows = {str(row["model_id"]): row for row in result.get("results") or []}
    if set(rows) != set(adapters):
        raise ConfigurationError("v0.6.2 compatibility and panel differ")
    for model_id, row in rows.items():
        if row.get("classification") != "compatible_full_stack":
            raise ConfigurationError(f"No full-stack pass for {model_id}")
    return adapters


def build_v062_client(
    *,
    key: str,
    adapter: V061ProviderAdapter,
    ledger: V061RequestLedger,
) -> V062AuditedOpenRouterClient:
    """Construct the v0.6.2 client with credentials already available."""

    config = v061_client_config()
    config.extra_headers = {"X-OpenRouter-Title": "UC-Bench v0.6.2"}
    with _temporary_environment("OPENROUTER_API_KEY", key):
        return V062AuditedOpenRouterClient(config, adapter, ledger)
