from __future__ import annotations

import logging
import os
from contextlib import nullcontext

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace as _TRACE_API
    from opentelemetry import metrics as _METRICS_API
    from opentelemetry.propagate import extract as _PROPAGATE_EXTRACT, inject as _PROPAGATE_INJECT
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency path
    _TRACE_API = None
    _METRICS_API = None
    _PROPAGATE_EXTRACT = None
    _PROPAGATE_INJECT = None
    OTLPSpanExporter = None
    OTLPMetricExporter = None
    FastAPIInstrumentor = None
    Resource = None
    MeterProvider = None
    PeriodicExportingMetricReader = None
    ConsoleMetricExporter = None
    TracerProvider = None
    BatchSpanProcessor = None
    ConsoleSpanExporter = None
    _OTEL_AVAILABLE = False

_TELEMETRY_STATUS = {
    "enabled": False,
    "configured": False,
    "exporter": None,
    "reason": "disabled",
    "metrics": {"enabled": False, "configured": False, "exporter": None},
    "logs": {"correlation_enabled": False, "format": "text"},
    "collection": {
        "mode": "local_only",
        "centralized_signals": 0,
        "required_signals": 3,
        "traces": {"centralized": False, "exporter": None, "endpoint": None},
        "metrics": {"centralized": False, "exporter": None, "endpoint": None},
        "logs": {"centralized": False, "sink": "none", "target": None},
    },
}
_INSTRUMENTED_APP_IDS: set[int] = set()
_REQUEST_COUNTER = None
_JOB_COUNTER = None


def _telemetry_enabled() -> bool:
    return os.environ.get("AUS_ELE_OTEL_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _service_name() -> str:
    return os.environ.get("AUS_ELE_OTEL_SERVICE_NAME", "aus-ele-backend").strip() or "aus-ele-backend"


def _exporter_kind() -> str:
    return os.environ.get("AUS_ELE_OTEL_EXPORTER", "otlp").strip().lower() or "otlp"


def _metrics_enabled() -> bool:
    return os.environ.get("AUS_ELE_OTEL_METRICS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _logs_json_enabled() -> bool:
    return os.environ.get("AUS_ELE_JSON_LOGS", "").strip().lower() in {"1", "true", "yes", "on"}


def _otlp_endpoint() -> str | None:
    value = os.environ.get("AUS_ELE_OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    return value or None


def _otlp_traces_endpoint() -> str | None:
    value = os.environ.get("AUS_ELE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
    return value or _otlp_endpoint()


def _otlp_metrics_endpoint() -> str | None:
    value = os.environ.get("AUS_ELE_OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "").strip()
    return value or _otlp_endpoint()


def _log_aggregation_enabled() -> bool:
    return os.environ.get("AUS_ELE_LOG_AGGREGATION_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _log_aggregation_sink() -> str:
    return os.environ.get("AUS_ELE_LOG_AGGREGATION_SINK", "none").strip().lower() or "none"


def _log_aggregation_target() -> str | None:
    sink = _log_aggregation_sink()
    if sink == "http":
        value = os.environ.get("AUS_ELE_LOG_AGGREGATION_ENDPOINT", "").strip()
        return value or None
    if sink == "file":
        value = os.environ.get("AUS_ELE_LOG_AGGREGATION_FILE_PATH", "").strip()
        return value or None
    return None


def _build_collection_status(*, telemetry_enabled: bool, trace_exporter: str | None, metrics_exporter: str | None, metrics_configured: bool) -> dict:
    traces_endpoint = _otlp_traces_endpoint()
    metrics_endpoint = _otlp_metrics_endpoint()
    trace_centralized = bool(telemetry_enabled and trace_exporter == "otlp" and traces_endpoint)
    metrics_centralized = bool(telemetry_enabled and metrics_configured and metrics_exporter == "otlp" and metrics_endpoint)
    log_sink = _log_aggregation_sink()
    log_target = _log_aggregation_target()
    logs_centralized = bool(_log_aggregation_enabled() and log_sink in {"http", "file"} and log_target)
    centralized_signals = sum([trace_centralized, metrics_centralized, logs_centralized])
    mode = "local_only"
    if centralized_signals == 3:
        mode = "centralized_ready"
    elif centralized_signals > 0:
        mode = "partial"
    return {
        "mode": mode,
        "centralized_signals": centralized_signals,
        "required_signals": 3,
        "traces": {
            "centralized": trace_centralized,
            "exporter": trace_exporter,
            "endpoint": traces_endpoint if trace_exporter == "otlp" else None,
        },
        "metrics": {
            "centralized": metrics_centralized,
            "exporter": metrics_exporter,
            "endpoint": metrics_endpoint if metrics_exporter == "otlp" else None,
        },
        "logs": {
            "centralized": logs_centralized,
            "sink": log_sink,
            "target": log_target,
        },
    }


def configure_telemetry(app=None) -> dict:
    global _TELEMETRY_STATUS, _REQUEST_COUNTER, _JOB_COUNTER
    if not _telemetry_enabled():
        _TELEMETRY_STATUS = {
            "enabled": False,
            "configured": False,
            "exporter": None,
            "reason": "disabled",
            "metrics": {"enabled": False, "configured": False, "exporter": None},
            "logs": {"correlation_enabled": True, "format": "json" if _logs_json_enabled() else "text"},
            "collection": _build_collection_status(
                telemetry_enabled=False,
                trace_exporter=None,
                metrics_exporter=None,
                metrics_configured=False,
            ),
        }
        return dict(_TELEMETRY_STATUS)
    if not _OTEL_AVAILABLE:
        _TELEMETRY_STATUS = {
            "enabled": True,
            "configured": False,
            "exporter": None,
            "reason": "missing_dependencies",
            "metrics": {"enabled": _metrics_enabled(), "configured": False, "exporter": None},
            "logs": {"correlation_enabled": True, "format": "json" if _logs_json_enabled() else "text"},
            "collection": _build_collection_status(
                telemetry_enabled=True,
                trace_exporter=_exporter_kind(),
                metrics_exporter=_exporter_kind() if _metrics_enabled() else None,
                metrics_configured=_metrics_enabled(),
            ),
        }
        logger.warning("OpenTelemetry enabled by env but dependencies are missing.")
        return dict(_TELEMETRY_STATUS)

    provider = _TRACE_API.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider(resource=Resource.create({"service.name": _service_name()}))
        exporter_kind = _exporter_kind()
        if exporter_kind == "console":
            span_exporter = ConsoleSpanExporter()
        else:
            endpoint = _otlp_traces_endpoint()
            headers = os.environ.get("AUS_ELE_OTEL_EXPORTER_OTLP_HEADERS")
            insecure = os.environ.get("AUS_ELE_OTEL_EXPORTER_OTLP_INSECURE", "").strip().lower() in {"1", "true", "yes", "on"}
            exporter_kwargs = {}
            if endpoint:
                exporter_kwargs["endpoint"] = endpoint
            if headers:
                exporter_kwargs["headers"] = headers
            if insecure:
                exporter_kwargs["insecure"] = True
            span_exporter = OTLPSpanExporter(**exporter_kwargs)
        provider.add_span_processor(BatchSpanProcessor(span_exporter))
        _TRACE_API.set_tracer_provider(provider)

    metrics_status = {"enabled": _metrics_enabled(), "configured": False, "exporter": None}
    if _metrics_enabled() and _METRICS_API is not None and MeterProvider is not None:
        exporter_kind = _exporter_kind()
        if exporter_kind == "console":
            metric_exporter = ConsoleMetricExporter()
        else:
            endpoint = _otlp_metrics_endpoint()
            headers = os.environ.get("AUS_ELE_OTEL_EXPORTER_OTLP_HEADERS")
            insecure = os.environ.get("AUS_ELE_OTEL_EXPORTER_OTLP_INSECURE", "").strip().lower() in {"1", "true", "yes", "on"}
            exporter_kwargs = {}
            if endpoint:
                exporter_kwargs["endpoint"] = endpoint
            if headers:
                exporter_kwargs["headers"] = headers
            if insecure:
                exporter_kwargs["insecure"] = True
            metric_exporter = OTLPMetricExporter(**exporter_kwargs)
        reader = PeriodicExportingMetricReader(metric_exporter)
        meter_provider = MeterProvider(resource=Resource.create({"service.name": _service_name()}), metric_readers=[reader])
        _METRICS_API.set_meter_provider(meter_provider)
        meter = _METRICS_API.get_meter(__name__)
        _REQUEST_COUNTER = meter.create_counter("aus_ele_http_requests_total")
        _JOB_COUNTER = meter.create_counter("aus_ele_job_runs_total")
        metrics_status = {"enabled": True, "configured": True, "exporter": exporter_kind}

    if app is not None and FastAPIInstrumentor is not None and id(app) not in _INSTRUMENTED_APP_IDS:
        FastAPIInstrumentor.instrument_app(app)
        _INSTRUMENTED_APP_IDS.add(id(app))

    _TELEMETRY_STATUS = {
        "enabled": True,
        "configured": True,
        "exporter": _exporter_kind(),
        "reason": "configured",
        "metrics": metrics_status,
        "logs": {"correlation_enabled": True, "format": "json" if _logs_json_enabled() else "text"},
        "collection": _build_collection_status(
            telemetry_enabled=True,
            trace_exporter=_exporter_kind(),
            metrics_exporter=metrics_status.get("exporter"),
            metrics_configured=bool(metrics_status.get("configured")),
        ),
    }
    return dict(_TELEMETRY_STATUS)


def get_telemetry_status() -> dict:
    return dict(_TELEMETRY_STATUS)


def get_current_trace_id() -> str | None:
    if _TRACE_API is None:
        return None
    try:
        span = _TRACE_API.get_current_span()
        if span is None:
            return None
        span_context = span.get_span_context()
        if not span_context or not getattr(span_context, "is_valid", lambda: False)():
            return None
        trace_id = getattr(span_context, "trace_id", 0)
        if not trace_id:
            return None
        return f"{trace_id:032x}"
    except Exception:
        return None


def get_current_span_id() -> str | None:
    if _TRACE_API is None:
        return None
    try:
        span = _TRACE_API.get_current_span()
        if span is None:
            return None
        span_context = span.get_span_context()
        if not span_context or not getattr(span_context, "is_valid", lambda: False)():
            return None
        span_id = getattr(span_context, "span_id", 0)
        if not span_id:
            return None
        return f"{span_id:016x}"
    except Exception:
        return None


def start_span(name: str, *, attributes: dict | None = None, parent_context=None):
    if not _telemetry_enabled() or not _OTEL_AVAILABLE or _TRACE_API is None:
        return nullcontext()
    tracer = _TRACE_API.get_tracer(__name__)
    return tracer.start_as_current_span(name, context=parent_context, attributes=attributes or {})


def serialize_current_trace_context() -> dict | None:
    if not _telemetry_enabled() or not _OTEL_AVAILABLE or _TRACE_API is None or _PROPAGATE_INJECT is None:
        return None
    trace_id = get_current_trace_id()
    if not trace_id:
        return None
    carrier: dict[str, str] = {}
    try:
        _PROPAGATE_INJECT(carrier)
    except Exception:
        return None
    return carrier or None


def extract_trace_context(carrier: dict | None):
    if not carrier or not _telemetry_enabled() or not _OTEL_AVAILABLE or _PROPAGATE_EXTRACT is None:
        return None
    try:
        return _PROPAGATE_EXTRACT(carrier)
    except Exception:
        return None


def extract_trace_id_from_traceparent(traceparent: str | None) -> str | None:
    if not traceparent:
        return None
    parts = [part.strip() for part in traceparent.split("-")]
    if len(parts) != 4:
        return None
    trace_id = parts[1].lower()
    if len(trace_id) != 32:
        return None
    try:
        int(trace_id, 16)
    except ValueError:
        return None
    return trace_id


def build_traceparent(*, trace_id: str | None = None, span_id: str | None = None, trace_flags: str = "01") -> str | None:
    trace_id = trace_id or get_current_trace_id()
    span_id = span_id or get_current_span_id()
    if not trace_id or not span_id:
        return None
    if len(trace_id) != 32 or len(span_id) != 16:
        return None
    return f"00-{trace_id}-{span_id}-{trace_flags}"


def build_trace_headers(*, trace_id: str | None = None, span_id: str | None = None) -> dict[str, str]:
    traceparent = build_traceparent(trace_id=trace_id, span_id=span_id)
    if not traceparent:
        return {}
    return {"traceparent": traceparent}


def build_collector_governance_status(telemetry_status: dict, openlineage_status: dict) -> dict:
    collection = telemetry_status.get("collection") or {}
    traces = collection.get("traces") or {}
    metrics = collection.get("metrics") or {}
    logs = collection.get("logs") or {}
    lineage_target = openlineage_status.get("endpoint") or openlineage_status.get("path")
    lineage_signal = {
        "enabled": bool(openlineage_status.get("enabled")),
        "sink": openlineage_status.get("sink"),
        "target": lineage_target,
        "centralized": bool(openlineage_status.get("enabled") and lineage_target),
    }
    signals = {
        "traces": {
            "enabled": bool(telemetry_status.get("enabled")),
            "transport": traces.get("exporter"),
            "target": traces.get("endpoint"),
            "centralized": bool(traces.get("centralized")),
        },
        "metrics": {
            "enabled": bool((telemetry_status.get("metrics") or {}).get("enabled")),
            "transport": metrics.get("exporter"),
            "target": metrics.get("endpoint"),
            "centralized": bool(metrics.get("centralized")),
        },
        "logs": {
            "enabled": bool((telemetry_status.get("logs") or {}).get("correlation_enabled")),
            "transport": logs.get("sink"),
            "target": logs.get("target"),
            "centralized": bool(logs.get("centralized")),
        },
        "lineage": lineage_signal,
    }
    missing = [
        name
        for name, signal in signals.items()
        if signal.get("enabled") and not signal.get("target") and name != "logs"
    ]
    if signals["logs"].get("enabled") and not signals["logs"].get("target") and signals["logs"].get("transport") not in {"file", "http"}:
        missing.append("logs")
    return {
        "propagation_standardized": True,
        "signals": signals,
        "missing_targets": missing,
        "governance_complete": len(missing) == 0,
    }


def record_request_metric(*, endpoint: str, method: str):
    if _REQUEST_COUNTER is None:
        return
    _REQUEST_COUNTER.add(1, {"endpoint": endpoint, "method": method})


def record_job_metric(*, job_type: str, status: str):
    if _JOB_COUNTER is None:
        return
    _JOB_COUNTER.add(1, {"job_type": job_type, "status": status})
