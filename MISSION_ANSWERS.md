# Day 14 Lab — Mission Answers

> Mọi output dưới đây là kết quả chạy thật trên máy của tôi (Windows 11 + Docker Desktop + WSL2 Ubuntu, Python 3.11), ngày 2026-11-25. Mục nào chưa chạy được thì ghi rõ "Chưa chạy".

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (`01-localhost-vs-production/develop/app.py`)

1. **API key và DB password hardcode** (dòng 17–18): `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"`, `DATABASE_URL = "postgresql://admin:password123@..."` — push lên GitHub là lộ secret ngay.
2. **In secret ra log** (dòng 34): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` — log thường được gom về hệ thống tập trung, ai đọc log cũng thấy key.
3. **Config cố định, không đọc từ biến môi trường** (dòng 21–22, 52): `DEBUG = True`, `MAX_TOKENS = 500`, `port=8000` — không đổi được giữa dev/staging/production.
4. **`print()` thay vì logging có cấu trúc** (dòng 33, 38, 48): không có level, timestamp, không parse/tìm kiếm được.
5. **Không có health check** (dòng 42–43): đã thử `GET /health` → `404 Not Found` (xem 1.2), platform không biết khi nào cần restart.
6. **Bind `host="localhost"`** (dòng 51): trong container/cloud thì không nhận được kết nối từ ngoài (cần `0.0.0.0`).
7. **Port cứng 8000, bỏ qua biến `PORT`** (dòng 52): Railway/Render cấp port qua env nên app không lên được.
8. **`reload=True`** (dòng 53): chế độ debug/hot-reload không dành cho production.
9. **Không xử lý shutdown, không có readiness**, và `question` nhận qua query string — thiếu validation schema.

### Exercise 1.2: Chạy bản develop

```bash
cd 01-localhost-vs-production/develop
curl -i -X POST "http://localhost:8000/ask?question=Hello"
```

```
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:19:36 GMT
server: uvicorn
content-length: 95
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Nó chạy, nhưng chưa production-ready: `GET /health` trả
```
HTTP/1.1 404 Not Found
{"detail":"Not Found"}
```

### Exercise 1.3: Comparison table

| Feature | Develop (basic) | Production (advanced) | Tại sao quan trọng? |
|---|---|---|---|
| Config | Hardcode trong code (dòng 17–22, 52) | Biến môi trường qua `config.py` / `Settings` (`settings.port`, `settings.environment`…) | Đổi cấu hình theo môi trường không cần sửa code; không commit secret; cùng một image chạy ở dev/staging/prod (12-Factor) |
| Secrets | `sk-...` và password trong code, còn `print` ra log | `AGENT_API_KEY`, `OPENAI_API_KEY` đọc từ env; không log | Tránh lộ key khi push repo hoặc đọc log |
| Health check | Không có (`/health` → 404) | `GET /health` (liveness: status, uptime, version) | Platform biết khi nào restart container, monitoring biết service còn sống |
| Readiness | Không có | `GET /ready` trả 503 khi chưa sẵn sàng (cờ `is_ready` đặt trong `lifespan`) | Load balancer chỉ route traffic vào instance đã khởi động xong |
| Logging | `print()` | JSON có `event`, `question_length`… (không log secret) | Log có cấu trúc dễ parse/tìm kiếm trong Datadog/Loki |
| Shutdown | Đột ngột (Ctrl+C là chết) | Graceful: `lifespan` đặt `is_ready=False`, chờ request đang chạy, handler SIGTERM | Không cắt ngang request đang xử lý khi deploy/scale |
| Host/Port | `localhost`, 8000 cố định, `reload=True` | `0.0.0.0`, port từ `PORT`, reload chỉ khi `DEBUG=true` | Chạy được trong container và trên Railway/Render |

Kiểm chứng bản production (`python app.py` ở `01-.../production`):
```
GET /health  -> HTTP/1.1 200 OK  {"status":"ok","uptime_seconds":0.5,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T09:1
GET /ready   -> HTTP/1.1 200 OK  {"ready":true}
POST /ask    -> HTTP/1.1 200 OK
```

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (bản đầy đủ: OS Debian + Python + nhiều công cụ build).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Vì sao `COPY requirements.txt` trước:** Docker cache theo từng layer. Dependencies ít đổi, code đổi liên tục; copy requirements và `pip install` trước thì khi chỉ sửa code, layer cài thư viện được dùng lại, build nhanh hơn rất nhiều.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh mặc định, dễ bị ghi đè khi `docker run <image> <lệnh khác>`; `ENTRYPOINT` là chương trình cố định, tham số truyền vào `docker run` được nối thêm vào sau. Hai cái hay dùng chung: ENTRYPOINT là chương trình, CMD là tham số mặc định.

### Exercise 2.2: Build và run (build từ gốc repo)

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -p 8000:8000 my-agent:develop
curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker"
```
```
HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Multi-stage build

- **Stage 1 (builder):** `python:3.11-slim` + `gcc`, `libpq-dev`; `pip install --user -r requirements.txt` — chứa công cụ biên dịch để cài dependencies.
- **Stage 2 (runtime):** `python:3.11-slim` sạch, chỉ `COPY --from=builder` thư mục `.local` (package đã cài) + mã nguồn; tạo user non-root `appuser`, có `HEALTHCHECK`, chạy 2 worker uvicorn.
- **Vì sao nhỏ hơn:** image cuối không chứa gcc, apt cache, header build, pip cache; và base là `slim` thay vì bản đầy đủ. Ít thứ hơn cũng nghĩa là ít lỗ hổng bảo mật hơn.

```bash
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker images my-agent
```
```
my-agent:develop   1.67GB
my-agent:advanced  240MB
```

Image size (cột SIZE của `docker images`, đo trên máy tôi):

- Develop: **1.67 GB** (~1710 MB)
- Production (advanced): **240 MB**
- Difference: giảm khoảng **86 %** (1.67 GB → 240 MB, nhỏ hơn ~7×). Tính theo dung lượng nén `docker image inspect` (`.Size`): 426 MB → 57 MB, giảm ~87 %.

Container advanced chạy bằng user `appuser` (non-root), trả `200` cho `POST /ask`.

### Exercise 2.4: Docker Compose stack

```bash
cd 02-docker/production && touch .env.local
docker compose -p k5-day14-docker up -d --build
```

Kiến trúc (4 service trong network `internal`; chỉ Nginx mở cổng ra ngoài):

```
Client ──► Nginx :80/:443 ──► Agent :8000 ──► Redis :6379   (session / cache)
                                        └───► Qdrant :6333  (vector DB cho RAG)
```

- Agent `depends_on` Redis và Qdrant (đợi `service_healthy`), Nginx `depends_on` agent.
- Các service nói chuyện với nhau qua tên service trong network bridge `internal` (Docker DNS), ví dụ `redis://redis:6379/0`, `http://qdrant:6333`.

Test qua Nginx (cổng 80), tất cả service `healthy`:
```
curl -i http://localhost/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":8.3,"version":"2.0.0","timestamp":"2026-11-25T10:05:11.865782"}

curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
HTTP/1.1 200 OK
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```
Đã `docker compose -p k5-day14-docker down -v` sau khi test.


## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy agent Part 6 lên Railway

- **Public URL:** https://day14-agent-production-8924a34b.up.railway.app
- **Nền tảng:** Railway (project `comfortable-wonder`, environment `production`), service `day14-agent` + service `Redis` trong cùng project. Deploy bằng Railway CLI từ thư mục `06-lab-complete/` (`railway link` → `railway up`, build bằng Dockerfile). Uvicorn chạy theo cổng `PORT` do Railway cấp (log: `Uvicorn running on http://0.0.0.0:8080`).
- **Biến môi trường đặt trên dashboard Railway (không có trong repo):** `AGENT_API_KEY` (chuỗi ngẫu nhiên tạo bằng `secrets.token_urlsafe(32)`), `REDIS_URL` = `${{Redis.REDIS_URL}}` (biến tham chiếu tới service Redis của Railway), `ENVIRONMENT=production`.

Kết quả 4 lệnh kiểm tra trên URL thật:

| Lệnh | Mong đợi | Kết quả |
|---|---|---|
| `GET /health` | 200 | 200 (`{"status":"ok"}`) |
| `GET /ready` | 200 | 200 (`{"status":"ready"}`, nghĩa là nối được Redis) |
| `POST /ask` không có key | 401 | 401 |
| `POST /ask` có `X-API-Key` | 200 | 200 |

Ba lệnh đầu tôi chạy lại để đối chiếu và ra đúng như trên; lệnh thứ tư cần key nên chỉ chủ tài khoản chạy được. `check_production_ready.py --public-url <URL>` (chạy trong WSL2 vì Windows không gửi được SIGTERM) → **PASS 12/12, 44/44 checks**, mục 12 có dòng `Public URL: GET .../health → 200`. Lần chạy đầu tiên trên Git Bash của Windows chỉ đạt 4/12 vì máy đó chưa cài `fastapi`/`uvicorn` (script báo `thiếu fastapi, uvicorn`), không phải lỗi của ứng dụng.

Screenshot: `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`.


### So sánh `railway.toml` với `render.yaml`

| Khía cạnh | `railway.toml` | `render.yaml` |
|---|---|---|
| Phạm vi | Cấu hình **một service** (build + deploy) | **Blueprint cả hạ tầng**: nhiều service (web + Redis/key-value) trong một file |
| Build | `[build] builder = "DOCKERFILE"` (hoặc `NIXPACKS`) | `runtime: docker` + `dockerfilePath`/`dockerContext` (hoặc `runtime: python` + `buildCommand`) |
| Health check | `[deploy] healthcheckPath = "/health"`, `healthcheckTimeout` | `healthCheckPath: /health` |
| Restart | `restartPolicyType`, `restartPolicyMaxRetries` | Render tự restart; không khai báo ở đây |
| Biến môi trường / secret | Đặt qua dashboard hoặc `railway variables set`, **không** nằm trong file | Có thể khai báo trong file: giá trị thường (`value`), secret tự sinh (`generateValue: true`) hoặc nhập tay (`sync: false`) |
| Redis | Tạo service Redis riêng trên dashboard rồi trỏ `REDIS_URL` | Khai báo ngay trong blueprint (`type: keyvalue`) và nối bằng `fromService` |
| Định dạng / cách deploy | TOML, `railway up` từ CLI | YAML, kết nối repo GitHub → Blueprint |

Khác nhau chính: Railway tách "code + cấu hình build" khỏi "biến/hạ tầng" (làm trên dashboard/CLI), còn Render mô tả toàn bộ hạ tầng bằng code trong repo (Infrastructure as Code). Vì vậy với Render, Redis và secret được dựng cùng lúc từ một file; với Railway phải tạo Redis và đặt `AGENT_API_KEY`, `REDIS_URL` thủ công.

### Exercise 3.3: Cloud Run (đọc `cloudbuild.yaml` và `service.yaml`, không deploy)

Pipeline CI/CD trong `cloudbuild.yaml` chạy 4 bước tuần tự: (1) `test` — cài `requirements.txt` và chạy `pytest tests/`, fail thì dừng; (2) `build` — `docker build` gắn tag `$COMMIT_SHA` và `latest`, dùng `--cache-from` để tận dụng layer cache; (3) `push` — đẩy image lên Container Registry; (4) `deploy` — `gcloud run deploy` ra region `asia-southeast1` với `min-instances=1` (tránh cold start), `max-instances=10`, 512Mi/1 CPU, secret `OPENAI_API_KEY` lấy từ Secret Manager. `service.yaml` (Knative) mô tả trạng thái mong muốn của dịch vụ: autoscaling 1–10 instance, `containerConcurrency: 80`, biến môi trường/secret, và `livenessProbe`/`startupProbe` trên `/health`. Nhờ tag theo commit SHA, mỗi lần push là một revision mới có thể rollback.

## Part 4: API Security

### Exercise 4.1: API key (`04-api-gateway/develop`, chạy với `AGENT_API_KEY=secret-key-123`)

- API key được check ở dependency `verify_api_key` (`develop/app.py`, dòng 39–54) qua header `X-API-Key`.
- Thiếu key → `401`; sai key → `403`; đúng → `200` (output bên dưới).
- Rotate key: đổi biến môi trường `AGENT_API_KEY` rồi restart (không sửa code); nên hỗ trợ hai key song song trong giai đoạn chuyển đổi.

```
# không có key
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# có key đúng
HTTP/1.1 200 OK
{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}

# key sai
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}
```

### Exercise 4.2: JWT (`04-api-gateway/production`)

Lấy token tại `POST /auth/token` với `student` / `demo123` (token đã che):

```
HTTP/1.1 200 OK
{"access_token":"<TOKEN-MASKED>","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."}

# gọi /ask không có token
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

### Exercise 4.3: Rate limiting (`production/rate_limiter.py`)

- Thuật toán: **sliding window** (deque timestamp trong 60 giây; loại timestamp cũ rồi so `len(window)` với limit).
- Limit: user 10 req/phút (`rate_limiter_user`), admin 100 req/phút (`rate_limiter_admin`).
- "Bypass" cho admin: không bỏ giới hạn mà dùng limiter cao hơn theo `role` trong JWT (`app.py` dòng 140–141).
- Lưu ý: limiter này giữ state **trong memory** của process → không dùng chung khi scale nhiều instance; bản Part 6 của tôi dùng Redis.

Vòng lặp 15 request với token `student` (`curl -i`, in dòng trạng thái):

```
#1: HTTP/1.1 200 OK
#2: HTTP/1.1 200 OK
#3: HTTP/1.1 200 OK
#4: HTTP/1.1 200 OK
#5: HTTP/1.1 200 OK
#6: HTTP/1.1 200 OK
#7: HTTP/1.1 200 OK
#8: HTTP/1.1 200 OK
#9: HTTP/1.1 200 OK
#10: HTTP/1.1 200 OK
#11: HTTP/1.1 429 Too Many Requests
#12: HTTP/1.1 429 Too Many Requests
#13: HTTP/1.1 429 Too Many Requests
#14: HTTP/1.1 429 Too Many Requests
#15: HTTP/1.1 429 Too Many Requests
```

Response khi chạm limit:
```
HTTP/1.1 429 Too Many Requests | x-ratelimit-limit: 10 | x-ratelimit-remaining: 0 | x-ratelimit-reset: 1795598467 | retry-after: 59 | {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59
```

### Exercise 4.4: Cost guard

Cách làm (đã cài trong `06-lab-complete/app/cost_guard.py` và nối vào `/ask`): trước khi gọi LLM, `check_budget()` đọc tổng chi phí trong ngày từ Redis (`cost:YYYY-MM-DD`, UTC) và trả **402** nếu `>= DAILY_BUDGET_USD`; sau khi gọi LLM, `record_cost(input_tokens, output_tokens)` tính tiền theo bảng giá (`$0.00015`/1K input, `$0.0006`/1K output) rồi cộng bằng `INCRBYFLOAT`, đặt TTL 2 ngày để key tự dọn. Dùng Redis để mọi worker/instance dùng chung tổng chi phí và còn nguyên sau restart. Khác bản mẫu trong đề (`$10/tháng` theo user): tôi theo "Hợp đồng" Part 6 — ngân sách theo ngày, toàn service — vì script chấm kiểm tra `DAILY_BUDGET_USD`. Script chấm xác nhận: ngân sách `0.000001` → request đầu tiên đã trả 402 ("402 ở request thứ 1").

Rate limit bảo vệ **tốc độ** (chống spam/DoS), cost guard bảo vệ **tiền** (một client gọi chậm nhưng prompt rất dài vẫn đốt budget) — cần cả hai.

## Part 5: Scaling & Reliability

### Exercise 5.1–5.2: Health check, readiness, graceful shutdown (`05-scaling-reliability/develop`, chạy trong WSL2 vì Windows không gửi được SIGTERM)

```
GET /health -> HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":2.2,"version":"1.0.0","environment":"development",...,"checks":{"memory":{"status":"ok","used_percent":22.2}}}
GET /ready  -> HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

- **Liveness (`/health`)** chỉ trả lời "process còn sống không" (platform restart nếu fail); **readiness (`/ready`)** trả lời "có nhận traffic được chưa" (503 khi đang khởi động/đang tắt → load balancer ngừng route nhưng không restart).
- **Graceful shutdown:** gửi `POST /ask` rồi gửi `SIGTERM` ngay sau 50 ms. Kết quả: request vẫn hoàn thành `HTTP 200` và server thoát với **exit code 0**. Log: `Shutting down` → request `200 OK` → `Waiting for application shutdown` → `Graceful shutdown initiated` → `Shutdown complete` → `Finished server process`. Cơ chế: `lifespan` đặt `_is_ready=False`, chờ `_in_flight_requests` về 0 (tối đa 30 s) rồi mới đóng; uvicorn tự dừng nhận kết nối mới khi có SIGTERM.

### Exercise 5.3: Stateless design

Bản `production/app.py` lưu session + history trong **Redis** (`session:{id}`, TTL; giữ tối đa 20 message), không giữ trong memory của process, nên bất kỳ instance nào cũng đọc/ghi được cùng một session. Anti-pattern là `conversation_history = {}` ở biến toàn cục: khi scale ra nhiều instance mỗi instance có memory riêng, request tiếp theo rơi vào instance khác sẽ "quên" cuộc hội thoại; rate limit đếm trong memory cũng tương tự bị chia nhỏ theo từng instance (đúng lý do Part 6 của tôi dùng Redis).

### Exercise 5.4–5.5: Load balancing + test stateless

Chạy trong `05-scaling-reliability/production`: `docker compose -p k5-day14-scaling up -d --build --scale agent=3` → 3 agent (đều `healthy`) + Redis + Nginx (cổng 8080). Đây là kết quả thật của lần chạy này.

**5.4 Load balancing.** Gửi 10 request `POST /chat` qua Nginx (`localhost:8080`), đếm theo `served_by`: `instance-04c0c5` 4, `instance-365251` 3, `instance-f09be9` 3, tức cả 3 instance đều nhận traffic, Nginx phân tán gần đều (round-robin).

**5.5 Test stateless.** `python test_stateless.py` gửi 5 request cùng một `session_id`: lần lượt rơi vào `04c0c5`, `f09be9`, `365251`, `04c0c5`, `f09be9` (3 instance khác nhau), rồi `GET /chat/{id}/history` trả đủ **10 message** (5 user + 5 assistant) → lịch sử được giữ vì nằm trong Redis chứ không nằm trong memory của từng instance.

Script không tự kill instance (đề bài mô tả bước đó), nên tôi làm thêm thủ công: tạo session mới, gửi 2 request, **`docker stop k5-day14-scaling-agent-1`**, rồi gửi tiếp 7 request cùng `session_id` qua Nginx. Kết quả: cả 7 request trả **HTTP 200** (6 request `After kill 1..6` + 1 request cuối do `instance-f09be9` xử lý), và history có **18 message** = 9 request × 2, gồm cả các message trước khi kill. Vậy khi một instance chết, traffic chuyển sang instance còn lại và hội thoại không mất. Lưu ý: tôi không biết instance bị dừng đã từng phục vụ session này hay chưa, nên đây là bằng chứng "không mất dữ liệu và không lỗi khi mất 1 instance", không phải bằng chứng "đúng request đó đã chuyển nhà". Sau khi xong tôi `docker compose down -v` stack này.


## Part 6: Final Project — output `check_production_ready.py`

Chạy đầy đủ trong WSL2 Ubuntu (`os.name == 'posix'`, Python 3.11) có Docker, từ `06-lab-complete/`:

```
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

## Part 7: Benchmark & Observability

Xem [`BENCHMARK_REPORT.md`](BENCHMARK_REPORT.md), `reports/`, `benchmark-results/`.

## AI log

Theo `RULES.md` mục 1: ghi lại việc dùng AI. Công cụ: Claude Code (model Claude Sonnet 5.5), chạy trong VS Code ở máy của tôi.

| # | Tôi yêu cầu | AI trả về | Kiểm tra / chỉnh sửa |
|---|---|---|---|
| 1 | Đọc các file hướng dẫn và yêu cầu rồi lên `plan.md`, làm theo | `plan.md` (kế hoạch theo giai đoạn, bảng điểm, rủi ro) | Đối chiếu với `RUBRIC.md`, `CHECKPOINTS.md`, `SUBMISSION.md` |
| 2 | Hoàn thành các `TODO` của Part 6 | Code `app/*`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml` | Chạy `check_production_ready.py`: lần đầu (Windows) 11/12 vì thiếu SIGTERM; cài Ubuntu WSL2, chạy lại → **12/12** (output ở Part 6). Không sửa script chấm |
| 3 | Cài WSL2 Ubuntu | Cài distro, Python 3.11 (`uv`), Redis, wrapper `docker` gọi `docker.exe` từ WSL (đổi đường dẫn `/mnt/c` → `C:/`) | Script chấm nhận Docker và báo đạt đủ mục |
| 4 | Chạy benchmark Part 7 bước 1 và 2, điền `BENCHMARK_REPORT.md` | Script chạy load test/eval/chaos, các bảng số liệu | Số trong báo cáo sinh trực tiếp từ `reports/*.json` và `benchmark-results/*.csv`; số alert/trace lấy từ API Prometheus/Jaeger. Ghi rõ các điểm không đo được |
| 5 | Sửa lỗi trong file đề | `production/Dockerfile` (benchmark) thiếu `PYTHONUSERBASE` nên container crash — AI thêm dòng `ENV PYTHONUSERBASE` | Sau sửa, các container `healthy` và Locust chạy được |
| 6 | Sửa `KNOWLEDGE_BASE` cho 2 câu v2 sai | Thêm 2 entry (HPA, JWT) | Eval v2 = 23/23, 0 regression so với baseline; không đụng `golden_dataset.jsonl` |

Tôi chịu trách nhiệm hiểu và giải thích được các đoạn code và con số ở trên khi Lab Coach hỏi.
