from __future__ import annotations

import json
import logging
import secrets
import sys
from datetime import UTC, datetime
from time import perf_counter

from fastapi import FastAPI, Request


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if fields:
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    if getattr(root, "_fcc_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level.upper())
    root._fcc_configured = True  # type: ignore[attr-defined]


def install_request_logging(app: FastAPI) -> None:
    logger = logging.getLogger("fcc.request")

    @app.middleware("http")
    async def log_request(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = perf_counter()
        request_id = request.headers.get("X-Request-ID") or secrets.token_hex(8)
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            logger.info(
                "request_complete",
                extra={
                    "fields": {
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": status_code,
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                    }
                },
            )
