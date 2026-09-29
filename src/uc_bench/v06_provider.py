"""Provider-aware, replayable OpenRouter adapter for v0.6 scientific episodes."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from verifiers.legacy.clients.openai_chat_completions_client import (
    OpenAIChatCompletionsClient,
)

from uc_bench.errors import ConfigurationError
from uc_bench.openrouter_catalog import (
    CatalogModel,
    fetch_model_endpoints,
    fetch_user_catalog,
)

PANEL_PATH = Path("configs/hard_suite_v06_model_panel.json")
COMPATIBILITY_PATH = Path("artifacts/diagnostics/hard_suite_v06_compatibility.json")
REASONING_STATE_FIELDS = ("reasoning_details", "reasoning")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
    return value


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json", exclude_none=False)
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    return {}


@dataclass(frozen=True, slots=True)
class ProviderAdapter:
    model_id: str
    expected_canonical_slug: str
    provider_order: tuple[str, ...]
    allow_fallbacks: bool
    requested_reasoning_effort: str
    tool_choice: str
    preserve_reasoning_state: bool
    maximum_prompt_price_usd_per_million: float
    maximum_completion_price_usd_per_million: float

    def __post_init__(self) -> None:
        if not self.model_id or not self.expected_canonical_slug:
            raise ConfigurationError("Provider adapter model identities must be non-empty")
        if not self.provider_order:
            raise ConfigurationError("Provider adapter requires a pinned provider")
        if self.allow_fallbacks:
            raise ConfigurationError("v0.6 provider fallbacks must remain disabled")
        if self.tool_choice not in {"auto", "provider_default_auto"}:
            raise ConfigurationError(f"Unsupported scientific tool choice: {self.tool_choice}")
        if not self.preserve_reasoning_state:
            raise ConfigurationError("Provider reasoning state must be preserved across tool turns")
        if min(
            self.maximum_prompt_price_usd_per_million,
            self.maximum_completion_price_usd_per_million,
        ) <= 0:
            raise ConfigurationError("Provider price ceilings must be positive")

    @property
    def accepted_response_models(self) -> set[str]:
        return {self.model_id, self.expected_canonical_slug}

    def sampling_args(self, *, maximum_completion_tokens: int) -> dict[str, Any]:
        if maximum_completion_tokens <= 1024 and self.provider_order == ("Anthropic",):
            raise ConfigurationError(
                "Anthropic scientific requests require room above the reasoning minimum"
            )
        extra_body: dict[str, Any] = {
            "provider": {
                "order": list(self.provider_order),
                "only": list(self.provider_order),
                "allow_fallbacks": False,
                "require_parameters": True,
                "max_price": {
                    "prompt": self.maximum_prompt_price_usd_per_million,
                    "completion": self.maximum_completion_price_usd_per_million,
                },
            },
            "reasoning": {"effort": self.requested_reasoning_effort},
            "parallel_tool_calls": False,
        }
        if self.tool_choice == "auto":
            extra_body["tool_choice"] = "auto"
        return {
            "max_tokens": maximum_completion_tokens,
            "extra_body": extra_body,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "expected_canonical_slug": self.expected_canonical_slug,
            "provider_order": list(self.provider_order),
            "allow_fallbacks": self.allow_fallbacks,
            "requested_reasoning_effort": self.requested_reasoning_effort,
            "tool_choice": self.tool_choice,
            "preserve_reasoning_state": self.preserve_reasoning_state,
            "maximum_route_price_usd_per_million": {
                "prompt": self.maximum_prompt_price_usd_per_million,
                "completion": self.maximum_completion_price_usd_per_million,
            },
        }


def load_provider_adapters(project_root: Path) -> dict[str, ProviderAdapter]:
    root = project_root.resolve()
    panel = _read_object(root / PANEL_PATH)
    compatibility = _read_object(root / COMPATIBILITY_PATH)
    if compatibility.get("status") != "passed" or compatibility.get("astra_requests") != 0:
        raise ConfigurationError("The v0.6 compatibility gate is not cleanly passed")
    passing = {
        str(row.get("model_id"))
        for row in compatibility.get("results") or []
        if row.get("classification") == "compatible"
    }
    adapters: dict[str, ProviderAdapter] = {}
    for row in panel.get("models") or []:
        model_id = str(row["model_id"])
        if model_id not in passing:
            raise ConfigurationError(f"No passing compatibility result for {model_id}")
        adapter = ProviderAdapter(
            model_id=model_id,
            expected_canonical_slug=str(row["expected_canonical_slug"]),
            provider_order=tuple(str(item) for item in row["provider_order"]),
            allow_fallbacks=bool(row.get("allow_fallbacks")),
            requested_reasoning_effort=str(row["requested_reasoning_effort"]),
            tool_choice=str(row["scientific_tool_choice"]),
            preserve_reasoning_state=bool(
                row.get("preserve_reasoning_details_across_tool_turns")
            ),
            maximum_prompt_price_usd_per_million=float(
                row["maximum_route_price_usd_per_million"]["prompt"]
            ),
            maximum_completion_price_usd_per_million=float(
                row["maximum_route_price_usd_per_million"]["completion"]
            ),
        )
        adapters[model_id] = adapter
    if passing != set(adapters):
        raise ConfigurationError("Compatibility results and proposed panel differ")
    return adapters


def validate_live_adapter_identity(
    adapters: dict[str, ProviderAdapter],
    catalog: dict[str, CatalogModel],
    endpoints_by_model: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Validate exact catalog pins and native tool routes without inference."""

    models: list[dict[str, Any]] = []
    required_parameters = {"reasoning", "structured_outputs", "tools"}
    for model_id, adapter in adapters.items():
        model = catalog.get(model_id)
        if model is None:
            raise ConfigurationError(f"Pinned model disappeared before execution: {model_id}")
        if model.canonical_slug != adapter.expected_canonical_slug:
            raise ConfigurationError(f"Pinned canonical model changed before execution: {model_id}")
        matching = [
            row
            for row in endpoints_by_model.get(model_id, [])
            if str(row.get("provider_name")) in set(adapter.provider_order)
            and required_parameters.issubset(set(row.get("supported_parameters") or []))
        ]
        if not matching:
            raise ConfigurationError(f"Pinned native tool route disappeared: {model_id}")
        models.append(
            {
                "model_id": model_id,
                "expected_canonical_slug": adapter.expected_canonical_slug,
                "observed_canonical_slug": model.canonical_slug,
                "provider_order": list(adapter.provider_order),
                "matching_native_tool_route_count": len(matching),
            }
        )
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "inference_requests_made": 0,
        "status": "passed",
        "models": models,
    }


def verify_live_adapter_identity(
    key: str, adapters: dict[str, ProviderAdapter]
) -> dict[str, Any]:
    catalog = fetch_user_catalog(key)
    endpoints = {
        model_id: fetch_model_endpoints(key, model_id) for model_id in adapters
    }
    return validate_live_adapter_identity(adapters, catalog, endpoints)


def preserve_reasoning_fields(
    source_messages: list[Any], native_messages: list[Any]
) -> list[Any]:
    """Copy provider reasoning payloads into the next request without alteration."""

    if len(source_messages) != len(native_messages):
        raise ConfigurationError("Native prompt conversion changed the message count")
    for source, native in zip(source_messages, native_messages, strict=True):
        source_dict = _as_dict(source)
        if source_dict.get("role") != "assistant" or not isinstance(native, dict):
            continue
        for field in REASONING_STATE_FIELDS:
            if field in source_dict and source_dict[field] is not None:
                native[field] = source_dict[field]
    return native_messages


def _response_record(
    response: Any,
    adapter: ProviderAdapter,
    *,
    latency_seconds: float,
    request_index: int,
) -> dict[str, Any]:
    raw = _as_dict(response)
    choices = raw.get("choices") or []
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    prompt_details = (
        usage.get("prompt_tokens_details")
        if isinstance(usage.get("prompt_tokens_details"), dict)
        else {}
    )
    completion_details = (
        usage.get("completion_tokens_details")
        if isinstance(usage.get("completion_tokens_details"), dict)
        else {}
    )
    returned_model = raw.get("model")
    actual_provider = raw.get("provider")
    violations: list[str] = []
    if returned_model not in adapter.accepted_response_models:
        violations.append("returned_model_mismatch")
    if actual_provider not in set(adapter.provider_order):
        violations.append("serving_provider_mismatch")
    refusal = message.get("refusal")
    return {
        "request_index": request_index,
        "recorded_at": datetime.now(UTC).isoformat(),
        "requested_model": adapter.model_id,
        "returned_model": returned_model,
        "requested_provider_order": list(adapter.provider_order),
        "actual_provider": actual_provider,
        "allow_fallbacks": False,
        "requested_reasoning_effort": adapter.requested_reasoning_effort,
        "resolved_reasoning_effort": raw.get("reasoning_effort", "not_reported"),
        "reasoning_state_present": any(message.get(field) for field in REASONING_STATE_FIELDS)
        or bool(message.get("reasoning_content")),
        "finish_reason": choice.get("finish_reason"),
        "response_refusal_observed": bool(refusal)
        or choice.get("finish_reason") == "content_filter",
        "refusal": str(refusal)[:1000] if refusal else None,
        "latency_seconds": round(latency_seconds, 6),
        "usage": usage,
        "cache": {
            "cached_prompt_tokens": int(prompt_details.get("cached_tokens") or 0),
            "cache_write_tokens": int(prompt_details.get("cache_write_tokens") or 0),
            "reasoning_tokens": int(completion_details.get("reasoning_tokens") or 0),
            "fields_reported": bool(prompt_details),
        },
        "reported_cost_usd": float(usage.get("cost") or 0.0),
        "retry_count": 0,
        "identity_violations": violations,
        "error": None,
    }


def _error_record(
    error: BaseException,
    adapter: ProviderAdapter,
    *,
    latency_seconds: float,
    request_index: int,
) -> dict[str, Any]:
    status = getattr(error, "status_code", None)
    lowered = str(error).lower()
    if (
        status in {408, 409, 429}
        or isinstance(status, int)
        and status >= 500
        or any(term in lowered for term in ("timeout", "connection reset", "temporarily"))
    ):
        classification = "infrastructure_failure"
    elif status in {403, 451} or any(
        term in lowered for term in ("policy block", "policy violation")
    ):
        classification = "provider_policy_refusal"
    elif type(error).__name__ == "OverlongPromptError" or any(
        term in lowered for term in ("context length", "prompt_too_long")
    ):
        classification = "context_budget_exhaustion"
    elif any(
        term in lowered
        for term in ("tool_choice", "unsupported", "invalid request", "bad request")
    ):
        classification = "provider_adapter_failure"
    else:
        classification = "unknown_harness_failure"
    return {
        "request_index": request_index,
        "recorded_at": datetime.now(UTC).isoformat(),
        "requested_model": adapter.model_id,
        "returned_model": None,
        "requested_provider_order": list(adapter.provider_order),
        "actual_provider": None,
        "allow_fallbacks": False,
        "requested_reasoning_effort": adapter.requested_reasoning_effort,
        "resolved_reasoning_effort": "not_reported",
        "reasoning_state_present": False,
        "finish_reason": None,
        "response_refusal_observed": False,
        "refusal": None,
        "latency_seconds": round(latency_seconds, 6),
        "usage": {},
        "cache": {
            "cached_prompt_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
            "fields_reported": False,
        },
        "reported_cost_usd": 0.0,
        "retry_count": 0,
        "identity_violations": [],
        "error": {
            "classification": classification,
            "http_status": status,
            "type": type(error).__name__,
            "message": str(error)[:2000],
        },
    }


class RequestLedger:
    """Atomically persist cost and route evidence after every provider request."""

    def __init__(self, path: Path, adapter: ProviderAdapter) -> None:
        self.path = path.resolve()
        self.adapter = adapter
        self.records: list[dict[str, Any]] = []
        self.write_count = 0
        self._checkpoint()

    @property
    def cumulative_reported_cost_usd(self) -> float:
        return sum(float(row.get("reported_cost_usd") or 0.0) for row in self.records)

    def record_response(self, response: Any, *, latency_seconds: float) -> dict[str, Any]:
        row = _response_record(
            response,
            self.adapter,
            latency_seconds=latency_seconds,
            request_index=len(self.records),
        )
        self.records.append(row)
        self._checkpoint()
        return row

    def record_error(self, error: BaseException, *, latency_seconds: float) -> dict[str, Any]:
        row = _error_record(
            error,
            self.adapter,
            latency_seconds=latency_seconds,
            request_index=len(self.records),
        )
        self.records.append(row)
        self._checkpoint()
        return row

    def _checkpoint(self) -> None:
        value = {
            "schema_version": "0.6-request-ledger-1",
            "adapter": self.adapter.to_dict(),
            "request_count": len(self.records),
            "cumulative_reported_cost_usd": round(
                self.cumulative_reported_cost_usd, 8
            ),
            "requests": self.records,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        self.write_count += 1


class ProviderIdentityError(RuntimeError):
    """The response did not come from the frozen model/provider identity."""


class AuditedOpenRouterClient(OpenAIChatCompletionsClient):
    """Verifiers client that preserves reasoning state and request-level evidence."""

    def __init__(self, client_or_config: Any, adapter: ProviderAdapter, ledger: RequestLedger):
        self.adapter = adapter
        self.ledger = ledger
        super().__init__(client_or_config)

    async def to_native_prompt(self, messages: list[Any]) -> tuple[list[Any], dict[str, Any]]:
        native, kwargs = await super().to_native_prompt(messages)
        return preserve_reasoning_fields(messages, native), kwargs

    async def get_native_response(
        self,
        prompt: Any,
        model: str,
        sampling_args: Any,
        tools: Any = None,
        **kwargs: Any,
    ) -> Any:
        started = time.monotonic()
        try:
            response = await super().get_native_response(
                prompt, model, sampling_args, tools, **kwargs
            )
        except Exception as exc:
            self.ledger.record_error(exc, latency_seconds=time.monotonic() - started)
            raise
        row = self.ledger.record_response(
            response, latency_seconds=time.monotonic() - started
        )
        if row["identity_violations"]:
            raise ProviderIdentityError(
                "Provider identity validation failed: "
                + ", ".join(row["identity_violations"])
            )
        return response

    async def from_native_response(self, response: Any) -> Any:
        converted = await super().from_native_response(response)
        raw_message = _as_dict(response.choices[0].message)
        for field in REASONING_STATE_FIELDS:
            if field in raw_message and raw_message[field] is not None:
                setattr(converted.message, field, raw_message[field])
        converted.provider = _as_dict(response).get("provider")
        return converted


def classify_execution(
    *,
    rollout_error: Any,
    completion: list[Any],
    submitted: bool,
    request_records: list[dict[str, Any]],
) -> str:
    if any(row.get("identity_violations") for row in request_records):
        return "provider_adapter_failure"
    errors = [row.get("error") for row in request_records if row.get("error")]
    if errors:
        classes = {str(row.get("classification")) for row in errors}
        if classes == {"infrastructure_failure"}:
            return "infrastructure_failure"
        if classes == {"provider_policy_refusal"}:
            return "provider_policy_refusal"
        if classes == {"context_budget_exhaustion"}:
            return "context_budget_exhaustion"
        if "provider_adapter_failure" in classes:
            return "provider_adapter_failure"
        return "unknown_harness_failure"
    if any(row.get("response_refusal_observed") for row in request_records):
        return "agent_refusal"
    if submitted and not rollout_error:
        return "valid_episode"
    if completion:
        rendered = json.dumps(completion, default=str).lower()
        if any(marker in rendered for marker in ("i cannot assist", "i can't assist")):
            return "agent_refusal"
        return "agent_task_failure"
    if rollout_error:
        error = _as_dict(rollout_error)
        error_type = str(error.get("type") or "")
        if error_type == "DockerRuntimeError":
            return "infrastructure_failure"
        if error_type in {"TimeoutError", "EpisodeTimeoutError"}:
            return "agent_task_failure"
        return "unknown_harness_failure"
    if not submitted:
        return "agent_task_failure"
    return "unknown_harness_failure"


def reliability_score(classification: str, scientific_score: float) -> float | None:
    if classification == "valid_episode":
        return float(scientific_score)
    if classification in {
        "agent_task_failure",
        "agent_refusal",
        "context_budget_exhaustion",
    }:
        return 0.0
    if classification in {
        "infrastructure_failure",
        "provider_adapter_failure",
        "provider_policy_refusal",
        "unknown_harness_failure",
    }:
        return None
    raise ConfigurationError(f"Unknown v0.6 attempt classification: {classification}")
