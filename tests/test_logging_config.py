from __future__ import annotations

import json
import logging

from src.logging_config import JsonFormatter, PrettyFormatter, configure_logging


def _log_record(**context: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="src.agents.wing.nodes",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="wing_llm_completed",
        args=(),
        exc_info=None,
    )
    record.created = 0
    for field, value in context.items():
        setattr(record, field, value)
    return record


def test_pretty_formatter_renders_readable_structured_context() -> None:
    output = PrettyFormatter(use_colors=False).format(
        _log_record(
            node="llm",
            tool_names=["get_spending_by_category"],
            decision="call_tools",
            request_id="request-1",
        )
    )

    assert output == (
        "00:00:00 INFO     src.agents.wing.nodes | wing_llm_completed | "
        'request_id=request-1 node=llm '
        'tool_names=["get_spending_by_category"] decision=call_tools'
    )
    assert "\033[" not in output


def test_json_formatter_preserves_tool_decision_fields() -> None:
    payload = json.loads(
        JsonFormatter().format(
            _log_record(
                tool_names=["get_spending_by_category"],
                decision="call_tools",
            )
        )
    )

    assert payload["tool_names"] == ["get_spending_by_category"]
    assert payload["decision"] == "call_tools"


def test_configure_logging_selects_pretty_formatter() -> None:
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level

    try:
        configure_logging("INFO", log_format="pretty")

        assert len(root_logger.handlers) == 1
        assert isinstance(root_logger.handlers[0].formatter, PrettyFormatter)
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)
        root_logger.setLevel(original_level)
