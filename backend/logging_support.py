from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import requests
import telemetry


def install_trace_log_record_factory(*, trace_id_supplier, span_id_supplier):
    previous_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = previous_factory(*args, **kwargs)
        record.trace_id = trace_id_supplier()
        record.span_id = span_id_supplier()
        return record

    logging.setLogRecordFactory(record_factory)


class JsonLogFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None),
            "span_id": getattr(record, "span_id", None),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class HttpJsonLogHandler(logging.Handler):
    def __init__(self, endpoint: str, *, session=None, timeout_seconds: float = 5.0):
        super().__init__()
        self.endpoint = endpoint
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def emit(self, record):
        try:
            payload = json.loads(self.format(record))
            headers = {"Content-Type": "application/json"}
            headers.update(
                telemetry.build_trace_headers(
                    trace_id=getattr(record, "trace_id", None),
                    span_id=getattr(record, "span_id", None),
                )
            )
            response = self.session.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except Exception:
            self.handleError(record)


def install_json_log_formatter_if_enabled():
    if os.environ.get("AUS_ELE_JSON_LOGS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    formatter = JsonLogFormatter()
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
    return True


def install_structured_log_sink_if_configured():
    if os.environ.get("AUS_ELE_LOG_AGGREGATION_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    sink = os.environ.get("AUS_ELE_LOG_AGGREGATION_SINK", "none").strip().lower() or "none"
    root_logger = logging.getLogger()
    if sink == "file":
        path_value = os.environ.get("AUS_ELE_LOG_AGGREGATION_FILE_PATH", "").strip()
        if not path_value:
            return False
        resolved_path = str(Path(path_value).resolve())
        for handler in root_logger.handlers:
            if getattr(handler, "_aus_ele_structured_sink_path", None) == resolved_path:
                return True
        path = Path(resolved_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(JsonLogFormatter())
        handler._aus_ele_structured_sink_path = resolved_path
        root_logger.addHandler(handler)
        return True
    if sink == "http":
        endpoint_value = os.environ.get("AUS_ELE_LOG_AGGREGATION_ENDPOINT", "").strip()
        if not endpoint_value:
            return False
        for handler in root_logger.handlers:
            if getattr(handler, "_aus_ele_structured_sink_endpoint", None) == endpoint_value:
                return True
        handler = HttpJsonLogHandler(endpoint_value)
        handler.setFormatter(JsonLogFormatter())
        handler._aus_ele_structured_sink_endpoint = endpoint_value
        root_logger.addHandler(handler)
        return True
    return False
