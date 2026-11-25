"""
Production AI Agent — Part 6 Final Project.

Luồng /ask: verify_api_key → check_rate_limit → check_budget → LLM → record_cost
"""
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


# ── Structured logging: mỗi dòng log là 1 JSON object ─────────────────────
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + f".{int(record.msecs):03d}Z",
            "lvl": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _setup_logging() -> logging.Logger:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("agent")
    log.handlers = [handler]
    log.setLevel(settings.log_level)
    log.propagate = False
    return log


logger = _setup_logging()


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": fields})


# ── Graceful shutdown ─────────────────────────────────────────────────────
# Khi `docker stop` gửi SIGTERM, uvicorn ngừng nhận kết nối mới, chờ request đang chạy xong,
# rồi gọi phần sau `yield` của lifespan này và thoát với exit code 0.
# Không tự đăng ký signal.signal(SIGTERM) để khỏi đè handler của uvicorn.
@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event("startup", environment=settings.environment, port=settings.port)
    yield
    log_event("shutdown", detail="SIGTERM received; in-flight requests finished")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = Field(default=None, max_length=100)


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        log_event(
            "request",
            path=request.url.path,
            method=request.method,
            status=status,
            ms=round((time.perf_counter() - start) * 1000, 1),
        )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    # Ghi chi tiết vào log, nhưng trả cho client một thông báo chung — không lộ stack trace.
    logger.error("unhandled_exception", extra={"fields": {"path": request.url.path}}, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health():
    """Liveness: luôn 200 khi process còn chạy (không phụ thuộc Redis)."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: 200 khi Redis kết nối được, ngược lại 503."""
    if not redis_healthy():
        return JSONResponse(status_code=503, content={"status": "not ready", "reason": "redis unavailable"})
    return {"status": "ready"}


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()
    answer = llm_ask(body.question)
    cost = record_cost(_approx_tokens(body.question), _approx_tokens(answer))
    return {
        "question": body.question,
        "answer": answer,
        "user_id": body.user_id,
        "cost_usd": round(cost, 8),
    }
