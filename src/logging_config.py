from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


LOG_CONTEXT_FIELDS = (
    "request_id",
    "agent_run_id",
    "turn_id",
    "agent_profile",
    "node",
    "tool_name",
    "tool_names",
    "decision",
    "tool_call_id",
    "tool_error_message",
    "message_count",
    "tool_call_count",
    "tool_result_count",
    "tool_error_count",
    "duration_ms",
    "method",
    "path",
    "status_code",
    "client_ip",
)

LEVEL_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[1;31m",
}
COLOR_RESET = "\033[0m"


def _context_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        field: value
        for field in LOG_CONTEXT_FIELDS
        if (value := getattr(record, field, None)) is not None
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_context_fields(record))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class PrettyFormatter(logging.Formatter):
    def __init__(self, *, use_colors: bool = True) -> None:
        super().__init__()
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(
            record.created,
            tz=timezone.utc,
        ).strftime("%H:%M:%S")
        level = f"{record.levelname:<8}"
        if self.use_colors:
            color = LEVEL_COLORS.get(record.levelname, "")
            if color:
                level = f"{color}{level}{COLOR_RESET}"

        output = f"{timestamp} {level} {record.name} | {record.getMessage()}"
        context = _context_fields(record)
        if context:
            details = " ".join(
                f"{field}={_pretty_value(value)}"
                for field, value in context.items()
            )
            output = f"{output} | {details}"

        if record.exc_info:
            output = f"{output}\n{self.formatException(record.exc_info)}"

        return output


def _pretty_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str, separators=(",", ":"))
    return str(value)


def configure_logging(log_level: str, log_format: str = "json") -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level.upper())

    normalized_format = log_format.strip().lower()
    if normalized_format == "json":
        handler.setFormatter(JsonFormatter())
    elif normalized_format == "pretty":
        handler.setFormatter(PrettyFormatter(use_colors=sys.stdout.isatty()))
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            )
        )

    root_logger.addHandler(handler)
