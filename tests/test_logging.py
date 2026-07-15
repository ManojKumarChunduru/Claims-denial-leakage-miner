from __future__ import annotations

import json
import logging

from claims_miner.logging_conf import JsonFormatter


def test_log_lines_are_valid_json_with_extras():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="claims_miner.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="model built",
        args=(),
        exc_info=None,
    )
    record.model = "fct_denials"
    record.seconds = 0.02
    line = formatter.format(record)
    payload = json.loads(line)
    assert payload["message"] == "model built"
    assert payload["model"] == "fct_denials"
    assert payload["seconds"] == 0.02
    assert payload["level"] == "INFO"
    assert "ts" in payload
