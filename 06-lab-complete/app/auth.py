"""
API Key authentication.

  • Client gửi header  X-API-Key: <key>
  • Key phải trùng biến môi trường AGENT_API_KEY
  • Thiếu hoặc sai key → HTTP 401 (không phải 403 hay 422)

auto_error=False để tự trả 401; nếu để FastAPI tự xử lý header bắt buộc thì thiếu header sẽ ra 422.
"""
import hmac

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Dependency cho FastAPI — dùng trong /ask: Depends(verify_api_key)."""
    expected = settings.agent_api_key
    # Chưa cấu hình key trên server → từ chối tất cả (fail closed), không bao giờ cho qua.
    if not api_key or not expected or not hmac.compare_digest(api_key.encode(), expected.encode()):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
