import unittest
from contextlib import contextmanager
import os

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

import telemetry


class TelemetryTests(unittest.TestCase):
    def test_get_current_trace_id_returns_none_without_span(self):
        original_trace_api = telemetry._TRACE_API
        try:
            telemetry._TRACE_API = None
            self.assertIsNone(telemetry.get_current_trace_id())
        finally:
            telemetry._TRACE_API = original_trace_api

    def test_start_span_degrades_to_noop_when_dependencies_missing(self):
        original_enabled = telemetry._telemetry_enabled
        original_available = telemetry._OTEL_AVAILABLE
        telemetry._telemetry_enabled = lambda: True
        telemetry._OTEL_AVAILABLE = False
        try:
            with telemetry.start_span("test-span"):
                value = "ok"
            self.assertEqual(value, "ok")
        finally:
            telemetry._telemetry_enabled = original_enabled
            telemetry._OTEL_AVAILABLE = original_available

    def test_get_current_trace_id_reads_hex_trace_id_from_span_context(self):
        class _SpanContext:
            trace_id = int("0123456789abcdef0123456789abcdef", 16)
            span_id = int("0123456789abcdef", 16)

            def is_valid(self):
                return True

        class _Span:
            def get_span_context(self):
                return _SpanContext()

        class _TraceApi:
            @staticmethod
            def get_current_span():
                return _Span()

        original_trace_api = telemetry._TRACE_API
        try:
            telemetry._TRACE_API = _TraceApi()
            self.assertEqual(
                telemetry.get_current_trace_id(),
                "0123456789abcdef0123456789abcdef",
            )
        finally:
            telemetry._TRACE_API = original_trace_api

    def test_get_current_span_id_reads_hex_span_id_from_span_context(self):
        class _SpanContext:
            trace_id = int("0123456789abcdef0123456789abcdef", 16)
            span_id = int("0123456789abcdef", 16)

            def is_valid(self):
                return True

        class _Span:
            def get_span_context(self):
                return _SpanContext()

        class _TraceApi:
            @staticmethod
            def get_current_span():
                return _Span()

        original_trace_api = telemetry._TRACE_API
        try:
            telemetry._TRACE_API = _TraceApi()
            self.assertEqual(telemetry.get_current_span_id(), "0123456789abcdef")
        finally:
            telemetry._TRACE_API = original_trace_api

    def test_telemetry_status_can_report_metrics_and_logs_health(self):
        original_status = dict(telemetry._TELEMETRY_STATUS)
        try:
            telemetry._TELEMETRY_STATUS = {
                "enabled": True,
                "configured": True,
                "exporter": "otlp",
                "reason": "configured",
                "metrics": {"enabled": True, "configured": True, "exporter": "otlp"},
                "logs": {"correlation_enabled": True, "format": "json"},
                "collection": {"mode": "partial", "centralized_signals": 2, "required_signals": 3},
            }
            status = telemetry.get_telemetry_status()
            self.assertTrue(status["metrics"]["enabled"])
            self.assertTrue(status["logs"]["correlation_enabled"])
            self.assertEqual(status["collection"]["mode"], "partial")
        finally:
            telemetry._TELEMETRY_STATUS = original_status

    def test_configure_telemetry_reports_centralized_collection_readiness(self):
        original_env = {
            key: os.environ.get(key)
            for key in (
                "AUS_ELE_OTEL_ENABLED",
                "AUS_ELE_OTEL_METRICS_ENABLED",
                "AUS_ELE_OTEL_EXPORTER",
                "AUS_ELE_OTEL_EXPORTER_OTLP_ENDPOINT",
                "AUS_ELE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
                "AUS_ELE_OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
                "AUS_ELE_JSON_LOGS",
                "AUS_ELE_LOG_AGGREGATION_ENABLED",
                "AUS_ELE_LOG_AGGREGATION_SINK",
                "AUS_ELE_LOG_AGGREGATION_ENDPOINT",
            )
        }
        original_available = telemetry._OTEL_AVAILABLE
        try:
            os.environ["AUS_ELE_OTEL_ENABLED"] = "1"
            os.environ["AUS_ELE_OTEL_METRICS_ENABLED"] = "1"
            os.environ["AUS_ELE_OTEL_EXPORTER"] = "otlp"
            os.environ["AUS_ELE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = "https://otel.example/v1/traces"
            os.environ["AUS_ELE_OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"] = "https://otel.example/v1/metrics"
            os.environ["AUS_ELE_JSON_LOGS"] = "1"
            os.environ["AUS_ELE_LOG_AGGREGATION_ENABLED"] = "1"
            os.environ["AUS_ELE_LOG_AGGREGATION_SINK"] = "http"
            os.environ["AUS_ELE_LOG_AGGREGATION_ENDPOINT"] = "https://logs.example/ingest"
            telemetry._OTEL_AVAILABLE = False

            status = telemetry.configure_telemetry()

            self.assertEqual(status["collection"]["mode"], "centralized_ready")
            self.assertEqual(status["collection"]["centralized_signals"], 3)
            self.assertTrue(status["collection"]["traces"]["centralized"])
            self.assertTrue(status["collection"]["metrics"]["centralized"])
            self.assertTrue(status["collection"]["logs"]["centralized"])
            self.assertEqual(status["collection"]["traces"]["endpoint"], "https://otel.example/v1/traces")
            self.assertEqual(status["collection"]["metrics"]["endpoint"], "https://otel.example/v1/metrics")
        finally:
            telemetry._OTEL_AVAILABLE = original_available
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_extract_trace_id_from_traceparent_reads_parent_trace(self):
        trace_id = telemetry.extract_trace_id_from_traceparent(
            "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
        )
        self.assertEqual(trace_id, "0123456789abcdef0123456789abcdef")

    def test_build_traceparent_uses_trace_and_span_ids(self):
        traceparent = telemetry.build_traceparent(
            trace_id="0123456789abcdef0123456789abcdef",
            span_id="0123456789abcdef",
        )
        self.assertEqual(
            traceparent,
            "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        )

    def test_otlp_signal_endpoints_fall_back_to_generic_endpoint(self):
        original_env = {
            key: os.environ.get(key)
            for key in (
                "AUS_ELE_OTEL_EXPORTER_OTLP_ENDPOINT",
                "AUS_ELE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
                "AUS_ELE_OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
            )
        }
        try:
            os.environ["AUS_ELE_OTEL_EXPORTER_OTLP_ENDPOINT"] = "https://otel.example/v1/otlp"
            os.environ.pop("AUS_ELE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)
            os.environ.pop("AUS_ELE_OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", None)
            self.assertEqual(telemetry._otlp_traces_endpoint(), "https://otel.example/v1/otlp")
            self.assertEqual(telemetry._otlp_metrics_endpoint(), "https://otel.example/v1/otlp")
        finally:
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
