"""
Cost guard.

  • Cộng dồn chi phí LLM (tính theo token) vào Redis, theo ngày (UTC).
  • Tổng chi phí >= DAILY_BUDGET_USD → HTTP 402.
"""
import datetime

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _key() -> str:
    return "cost:" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    try:
        spent = float(r.get(_key()) or 0)
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Cost guard unavailable (Redis).")
    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Daily budget exceeded: ${spent:.4f} / ${settings.daily_budget_usd:.4f}.",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
    try:
        key = _key()
        pipe = r.pipeline(transaction=True)
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, 2 * 24 * 3600)  # tự dọn sau 2 ngày
        pipe.execute()
    except redis.RedisError:
        pass  # request đã phục vụ xong; mất một lần ghi chi phí không đáng làm hỏng response
    return cost
