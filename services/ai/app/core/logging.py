from __future__ import annotations

import logging
import json
import re
from datetime import datetime, timezone

from app.core.diagnostics import correlation
from logging.config import dictConfig


class DiagnosticJsonFormatter(logging.Formatter):
    """Do not serialize interpolated messages, exception text or arbitrary extras."""

    def format(self, record: logging.LogRecord) -> str:
        template = record.msg if isinstance(record.msg, str) else "log"
        match = re.match(r"[a-zA-Z][a-zA-Z0-9_.-]{0,95}(?=\s|$)", template)
        payload = {
            "schema_version": "diagnostic-log-v1",
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "severity": record.levelname,
            "event": match.group(0) if match and match.group(0) in {"bootstrap.model_provider", "request.start", "request.end", "request.error"} else "log",
            **correlation.get(),
        }
        if record.exc_info and record.exc_info[0]:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=True)


def configure_logging() -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "()": DiagnosticJsonFormatter
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "level": "INFO",
                }
            },
            "root": {
                "handlers": ["default"],
                "level": "INFO",
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
