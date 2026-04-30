import json
import logging
import os
import tempfile
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

import logging_support


class LoggingSupportTests(unittest.TestCase):
    def test_record_factory_injects_trace_and_span_ids(self):
        original_factory = logging.getLogRecordFactory()
        try:
            logging_support.install_trace_log_record_factory(
                trace_id_supplier=lambda: "0123456789abcdef0123456789abcdef",
                span_id_supplier=lambda: "0123456789abcdef",
            )
            record = logging.getLogRecordFactory()(
                "test",
                logging.INFO,
                __file__,
                12,
                "hello",
                (),
                None,
            )
            self.assertEqual(record.trace_id, "0123456789abcdef0123456789abcdef")
            self.assertEqual(record.span_id, "0123456789abcdef")
        finally:
            logging.setLogRecordFactory(original_factory)

    def test_json_formatter_emits_trace_and_span_fields(self):
        formatter = logging_support.JsonLogFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.trace_id = "0123456789abcdef0123456789abcdef"
        record.span_id = "0123456789abcdef"

        payload = json.loads(formatter.format(record))

        self.assertEqual(payload["message"], "hello")
        self.assertEqual(payload["trace_id"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(payload["span_id"], "0123456789abcdef")

    def test_install_json_log_formatter_replaces_root_handler_formatters(self):
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.handlers = [handler]
        original_env = os.environ.get("AUS_ELE_JSON_LOGS")
        os.environ["AUS_ELE_JSON_LOGS"] = "1"
        try:
            logging_support.install_json_log_formatter_if_enabled()
            self.assertIsInstance(root_logger.handlers[0].formatter, logging_support.JsonLogFormatter)
        finally:
            root_logger.handlers = original_handlers
            if original_env is None:
                os.environ.pop("AUS_ELE_JSON_LOGS", None)
            else:
                os.environ["AUS_ELE_JSON_LOGS"] = original_env

    def test_install_structured_log_sink_can_add_json_file_handler(self):
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        original_env = {
            key: os.environ.get(key)
            for key in (
                "AUS_ELE_LOG_AGGREGATION_ENABLED",
                "AUS_ELE_LOG_AGGREGATION_SINK",
                "AUS_ELE_LOG_AGGREGATION_FILE_PATH",
            )
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "observability.jsonl")
            try:
                root_logger.handlers = []
                os.environ["AUS_ELE_LOG_AGGREGATION_ENABLED"] = "1"
                os.environ["AUS_ELE_LOG_AGGREGATION_SINK"] = "file"
                os.environ["AUS_ELE_LOG_AGGREGATION_FILE_PATH"] = log_path

                installed = logging_support.install_structured_log_sink_if_configured()

                self.assertTrue(installed)
                self.assertEqual(len(root_logger.handlers), 1)
                self.assertIsInstance(root_logger.handlers[0].formatter, logging_support.JsonLogFormatter)
            finally:
                for handler in root_logger.handlers:
                    handler.close()
                root_logger.handlers = original_handlers
                for key, value in original_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_install_structured_log_sink_can_add_http_handler(self):
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        original_env = {
            key: os.environ.get(key)
            for key in (
                "AUS_ELE_LOG_AGGREGATION_ENABLED",
                "AUS_ELE_LOG_AGGREGATION_SINK",
                "AUS_ELE_LOG_AGGREGATION_ENDPOINT",
            )
        }
        try:
            root_logger.handlers = []
            os.environ["AUS_ELE_LOG_AGGREGATION_ENABLED"] = "1"
            os.environ["AUS_ELE_LOG_AGGREGATION_SINK"] = "http"
            os.environ["AUS_ELE_LOG_AGGREGATION_ENDPOINT"] = "https://logs.example/ingest"

            installed = logging_support.install_structured_log_sink_if_configured()

            self.assertTrue(installed)
            self.assertEqual(len(root_logger.handlers), 1)
            self.assertIsInstance(root_logger.handlers[0], logging_support.HttpJsonLogHandler)
        finally:
            for handler in root_logger.handlers:
                handler.close()
            root_logger.handlers = original_handlers
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_http_json_log_handler_posts_formatted_payload(self):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        session = mock.Mock()
        session.post.return_value = response
        handler = logging_support.HttpJsonLogHandler(
            endpoint="https://logs.example/ingest",
            session=session,
        )
        handler.setFormatter(logging_support.JsonLogFormatter())
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.trace_id = "0123456789abcdef0123456789abcdef"
        record.span_id = "0123456789abcdef"

        handler.emit(record)

        session.post.assert_called_once()
        payload = session.post.call_args.kwargs["json"]
        self.assertEqual(payload["message"], "hello")
        self.assertEqual(payload["trace_id"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(
            session.post.call_args.kwargs["headers"]["traceparent"],
            "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        )
