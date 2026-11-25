# ============================================================
# Production Dockerfile — multi-stage, slim, non-root, HEALTHCHECK
# Build context: thư mục 06-lab-complete/
# ============================================================

# ── Stage 1: builder — cài dependencies vào /install ──────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
# Copy requirements trước source để tận dụng layer cache: đổi code không phải cài lại thư viện.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime — chỉ chứa kết quả build + code ──────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app

WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=app:app app/ ./app/
COPY --chown=app:app utils/ ./utils/

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=2)" || exit 1

# `exec` để uvicorn là PID 1 → nhận SIGTERM từ `docker stop` và tắt gọn (exit code 0).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
