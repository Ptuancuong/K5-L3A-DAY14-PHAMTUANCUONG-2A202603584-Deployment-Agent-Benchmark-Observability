"""
Rate limiting — sliding window 60 giây bằng Redis sorted set.

  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request / 60 giây.
  • Vượt giới hạn → HTTP 429 kèm header Retry-After.
  • State nằm trong Redis nên mọi worker/instance dùng chung và còn nguyên sau khi restart agent.
"""
import hashlib
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    # Không lưu API key thô trong Redis, chỉ lưu hash rút gọn.
    redis_key = "rl:" + hashlib.sha256(key.encode()).hexdigest()[:16]
    now = time.time()
    member = f"{now}:{uuid.uuid4().hex[:8]}"  # duy nhất, kể cả 2 request cùng timestamp
    try:
        pipe = r.pipeline(transaction=True)
        pipe.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)  # xoá request cũ
        pipe.zadd(redis_key, {member: now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        _, _, count, _ = pipe.execute()
        if count > settings.rate_limit_per_minute:
            r.zrem(redis_key, member)  # request bị từ chối không được tính vào cửa sổ
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} requests/minute.",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )
    except redis.RedisError:
        # Fail closed: không kiểm soát được tốc độ thì không phục vụ.
        raise HTTPException(status_code=503, detail="Rate limiter unavailable (Redis).")
