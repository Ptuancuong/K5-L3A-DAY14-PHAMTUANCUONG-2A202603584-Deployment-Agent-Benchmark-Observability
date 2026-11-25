# plan.md — Kế hoạch làm Lab Day 14 (Deployment, Benchmark & Observability)

> Tổng hợp từ: README (mục "Lưu ý K5"), CODE_LAB, CHECKPOINTS, SUBMISSION, RUBRIC, RULES, DAY14_DELIVERY_CHECKLIST, INSTRUCTOR_GUIDE, `06-lab-complete/README.md`, `benchmark-observability/README.md`.
> Tổng điểm thô 120 → quy về 100 (đạt ≥ 70/100 = 84/120).

## 0. Hiện trạng môi trường (đã kiểm tra)

| Hạng mục                      | Trạng thái                                                                                             | Hệ quả                                                                                                  |
| ----------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Python                        | 3.14.3 (Windows)                                                                                       | OK cho code; `check_production_ready.py` bản Windows **không** đạt Graceful shutdown (không có SIGTERM) |
| Docker CLI                    | 29.2.0, **daemon đang tắt** (Docker Desktop Stopped)                                                   | Cần bật Docker Desktop mới build/chạy được                                                              |
| WSL2                          | chỉ có distro `docker-desktop`, **chưa có Ubuntu**                                                     | Cần `wsl --install -d Ubuntu` để chạy Python `posix` và đạt PASS 12/12                                  |
| Node                          | v24.15                                                                                                 | Cài được Railway CLI (`npm i -g @railway/cli`)                                                          |
| Railway CLI / tài khoản cloud | chưa có                                                                                                | **Bạn phải tự đăng nhập** Railway/Render (tôi không thể đăng nhập hộ)                                   |
| Git remote                    | `origin` = `Ptuancuong/K5-L3A-DAY14-PHAMTUANCUONG-2A202603584-...`                                     | Tên repo đã đúng mẫu; cần đảm bảo repo **Public**                                                       |
| Repo                          | sạch, nhánh `main`, chưa có `plan.md` / `MISSION_ANSWERS.md` / `DEPLOYMENT.md` / `BENCHMARK_REPORT.md` | Phải tạo mới                                                                                            |

## 1. Ai làm gì

- **Tôi (Claude) làm được tự động:** viết toàn bộ code Part 6 (`app/*`, Dockerfile, compose, .dockerignore, .env.example, railway.toml/render.yaml), chạy `check_production_ready.py --static-only`/`--skip-docker`, chạy Part 1/4/7 Bước 1 local bằng Python (khi cần Redis thì dùng Docker), viết khung các file nộp bài, điền số liệu **thật** từ file output.
- **Chỉ bạn làm được:** bật Docker Desktop; cài Ubuntu WSL2; đăng nhập Railway/Render và deploy; chụp **screenshot** (Grafana, Jaeger, Prometheus alerts, dashboard cloud); đặt repo Public; nộp link trên LMS; dán AI log trung thực.
- **Nguyên tắc (RULES.md):** không bịa số đo — mọi số trong báo cáo lấy từ lệnh đã chạy; không sửa `check_production_ready.py` và `golden_dataset.jsonl`; không commit `.env`/key; ghi **AI log** cuối `MISSION_ANSWERS.md`.

## 2. Thứ tự thực hiện (ưu tiên theo điểm)

Điểm nhiều nhất là Part 6 (60/120) → làm trước, rồi mới tới Part 1–5 (40) và Part 7 (20).

### Giai đoạn A — Setup (CP0)

- [ ] A1. Bật Docker Desktop, kiểm tra `docker run --rm hello-world`.
- [ ] A2. Cài Ubuntu cho WSL2 (`wsl --install -d Ubuntu`), bật tích hợp WSL trong Docker Desktop; trong Ubuntu cài `python3.11+`, `pip`, `venv`; mở repo qua `/mnt/c/...`. Kiểm tra `python -c "import os; print(os.name)"` → `posix`.
- [ ] A3. Xác nhận repo `origin` Public, tên đúng mẫu.

### Giai đoạn B — Part 6 Final Project (CP5, 60 điểm) — làm trước

Làm ngay trong `06-lab-complete/`. Thứ tự gợi ý của đề:

| #   | File                                          | Việc cần làm                                                                                                                                                                                                                                       | Tiêu chí       |
| --- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| B1  | `app/config.py`                               | `Settings` đọc env: `PORT`, `ENVIRONMENT`, `AGENT_API_KEY`, `REDIS_URL`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`; không hardcode secret                                                                                                        | 9              |
| B2  | `app/main.py`                                 | `JsonFormatter` (mọi log app là JSON), `GET /health` luôn 200, `GET /ready` 503 khi Redis chết, middleware log request, lifespan + SIGTERM handler gọi lại handler cũ                                                                              | 4,5,10,11      |
| B3  | `app/auth.py`                                 | `APIKeyHeader(name="X-API-Key", auto_error=False)`, thiếu/sai → **401** (so sánh `hmac.compare_digest`)                                                                                                                                            | 6              |
| B4  | `app/redis_client.py`                         | `redis.from_url(...)` lazy (không ping lúc import), `redis_healthy()`                                                                                                                                                                              | 5              |
| B5  | `app/rate_limiter.py`                         | Sliding window 60s bằng sorted set (`ZREMRANGEBYSCORE→ZCARD→ZADD→EXPIRE`), vượt → **429** + `Retry-After: 60`, key theo API key                                                                                                                    | 7              |
| B6  | `app/cost_guard.py`                           | `check_budget()` → **402** khi tổng ≥ `DAILY_BUDGET_USD`; `record_cost()` dùng `INCRBYFLOAT` theo token, key theo ngày + TTL                                                                                                                       | 8              |
| B7  | `app/main.py` `/ask`                          | Nối: `Depends(verify_api_key)` → `check_rate_limit` → `check_budget` → `llm_ask` → `record_cost`; lỗi input trả 422 gọn, không lộ stack trace (exception handler chung → 500 JSON sạch)                                                            | Functional 15đ |
| B8  | `Dockerfile` + `.dockerignore`                | Multi-stage `python:3.11-slim`, `PYTHONUSERBASE`, user non-root, `HEALTHCHECK`, `CMD sh -c "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"`; ignore `.env*`, `__pycache__`, `venv`, `.git`, `benchmark-observability/` | 1,3            |
| B9  | `docker-compose.yml`                          | `agent` (build, ports, `env_file` `required:false`, `REDIS_URL=redis://redis:6379/0`, `depends_on` healthy) + `redis:7-alpine` có healthcheck                                                                                                      | 2              |
| B10 | `.env.example`, `railway.toml`, `render.yaml` | Đủ biến, không secret; Railway `builder="DOCKERFILE"`, `healthcheckPath="/health"`; Render `type: web`, `runtime: docker`, `healthCheckPath: /health`, secret `generateValue`/`sync:false`                                                         | 9,12           |
| B11 | Kiểm tra                                      | `python check_production_ready.py --static-only` → `--skip-docker` → bản đầy đủ **trong WSL2** → mục tiêu `PASS 12/12`                                                                                                                             | tất cả         |

Mở rộng (không tính điểm, chỉ làm nếu dư giờ): history trong Redis, streaming, Nginx + 3 instance.

### Giai đoạn C — Part 1–5 (CP1–CP4, 32 điểm) → `MISSION_ANSWERS.md`

Rút gọn: chạy ví dụ có sẵn, ghi kết quả thật. Lưu ý K5: app develop nhận `question` qua **query**, build Docker từ **gốc repo**, `touch .env.local`, token `student/demo123` ở `/auth/token`, stack Part 5 dùng cổng 8080 + `POST /chat` + `-p k5-day14-scaling`.

- [ ] C1 (Part 1, 8đ): ≥5 anti-pattern trong `01-.../develop/app.py` (kèm dòng code); chạy develop bằng `curl -X POST "http://localhost:8000/ask?question=Hello"`; bảng so sánh develop/production có cột "Tại sao quan trọng".
- [ ] C2 (Part 2, 8đ): 4 câu Exercise 2.1; build `my-agent:develop` & `my-agent:advanced` từ gốc repo; **đo MB bằng `docker images`** + % chênh; sơ đồ stack 2.4 + test qua Nginx.
- [ ] C3 (Part 4, 8đ): output `curl -i` các ca 401 / 200 / 429 (che token); trả lời câu hỏi 4.1/4.3 (thuật toán, limit, bypass admin); giải thích cách làm cost guard (có thể dẫn lại implement ở B6).
- [ ] C4 (Part 5, 8đ): `/health` vs `/ready`, graceful shutdown, stateless; `docker compose -p k5-day14-scaling up -d --build --scale agent=3` → `python test_stateless.py` → giải thích → `down`.
- [ ] C5 (Part 3, 8đ — nhánh còn lại ngoài deploy): so sánh `railway.toml` vs `render.yaml` (3đ) + 3–5 dòng pipeline `cloudbuild.yaml`/`service.yaml` (1đ).

### Giai đoạn D — Part 3 Cloud Deployment (CP6, 8đ + 10đ deploy Part 6) → `DEPLOYMENT.md`

- [ ] D1. **(Bạn)** Chọn Railway (hoặc Render). Railway: `cd 06-lab-complete && railway login && railway init`, tạo thêm service **Redis**, đặt biến `AGENT_API_KEY` (key mạnh, không commit), `REDIS_URL` trỏ Redis, `PORT`, `LOG_LEVEL`; `railway up`, `railway domain`.
- [ ] D2. Kiểm `/ready` = 200 rồi chạy 4 lệnh CP6 (health 200, ready 200, ask không key 401, có key 200); chụp `dashboard.png`, `running.png`, `test.png` vào `screenshots/`.
- [ ] D3. Tôi viết `DEPLOYMENT.md` theo mẫu; điền URL sau khi bạn cung cấp. Chạy thêm `check_production_ready.py --public-url <URL>`.
- [ ] D4. Để lấy trọn 3đ "nền tảng còn lại": hoặc deploy thêm Render, hoặc dùng bản so sánh config ở C5.

### Giai đoạn E — Part 7 Bước 1: benchmark local (CP7, 9đ)

Trong `06-lab-complete/benchmark-observability/develop/` (Python, không cần Docker):

- [ ] E1. `pip install -r requirements.txt`; chạy v1 (cổng 8001) và v2 (cổng 8002); Exercise 7.1: phân loại Counter/Gauge/Histogram, trả lời câu hỏi cardinality, thêm metric `agent_question_length_chars` (Histogram).
- [ ] E2. Copy template: `cp -n .../BENCHMARK_REPORT_TEMPLATE.md BENCHMARK_REPORT.md` (ở gốc repo).
- [ ] E3. Load test v2 ở concurrency 1/10/50/100 → `reports/load_v2_c{1,10,50,100}.json`.
- [ ] E4. So sánh `MOCK_SLOW_RATE` 0 / 0.03 / 0.1 (300 req, c=20) → `reports/load_v2_slow_{0,0.03,0.1}.json`.
- [ ] E5. Eval v1 → `eval_v1.json`; v2 với `--baseline` → `eval_v2.json` (kỳ vọng v1≈4%, v2≈91%).
- [ ] E6. Sửa `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (HPA/Kubernetes autoscale; JWT vs API key — cho `scaling-03`, `security-02`), restart v2, chạy `--min-accuracy 1.0 --baseline reports/eval_v2.json --out reports/eval_v2_fixed.json` → 23/23, không regression. **Không** sửa `golden_dataset.jsonl`.
- [ ] E7. Job CI quality gate: tạo `.github/workflows/eval.yml` (chạy eval, fail nếu accuracy < 85%) + giải thích dùng exit code.
- [ ] E8. Điền §1–§3 của `BENCHMARK_REPORT.md` bằng số thật từ JSON.

### Giai đoạn F — Part 7 Bước 2: observability stack (CP8, 11đ — sau giờ lab)

Trong `.../benchmark-observability/production/`, luôn dùng `-p k5-day14-observability`:

- [ ] F1. `docker compose -p k5-day14-observability up -d --build --scale agent=1`; mở Grafana/Prometheus/Jaeger/Locust; copy `.env.example` → `.env` nếu cần chaos.
- [ ] F2. Locust headless `scale_1` (100 users, 2 phút) → `benchmark-results/scale_1_stats.csv`; `--scale agent=3` → `scale_3_stats.csv`.
- [ ] F3. **(Bạn chụp)** `grafana-dashboard.png` khi đang có tải; trả lời 4 câu Exercise 7.4 (avg↔p95, chia tải 2 instance, input > output tokens, `/metrics` bị Nginx chặn → 404).
- [ ] F4. **(Bạn chụp)** `jaeger-slow-trace.png` (span chậm nhất + ms), `jaeger-error-trace.png` (event `exception`); lấy `trace_id` từ `docker compose -p ... logs agent | grep llm_error` và chép dòng log JSON tương ứng vào báo cáo.
- [ ] F5. `promtool test rules` cho `alert_rules_test.yml`; chạy ≥ 2 thí nghiệm chaos (đề xuất A `MOCK_ERROR_RATE=0.2` và C `LLM_MODEL=mock-llm-large`, hoặc D `docker pause`), ghi **thời gian từ lúc đổi → firing**, chụp **một** ảnh `prometheus-alert-firing.png` thấy ≥ 2 alert cùng firing; trả lời thí nghiệm E (đổi v1 không alert → cần eval/giám sát chất lượng).
- [ ] F6. Hoàn thiện §4–§6 `BENCHMARK_REPORT.md`; `docker compose -p k5-day14-observability down -v`.

### Giai đoạn G — Đóng gói & nộp

- [ ] G1. Từ gốc repo: `mkdir -p reports benchmark-results`; `cp -r 06-lab-complete/benchmark-observability/develop/reports/. reports/`; `cp -r 06-lab-complete/benchmark-observability/production/benchmark-results/. benchmark-results/`.
- [ ] G2. Cấu trúc nộp cuối (SUBMISSION.md): `MISSION_ANSWERS.md`, `DEPLOYMENT.md`, `BENCHMARK_REPORT.md`, `reports/`, `benchmark-results/`, `screenshots/` (7 ảnh: dashboard, running, test, grafana-dashboard, jaeger-slow-trace, jaeger-error-trace, prometheus-alert-firing), `06-lab-complete/`.
- [ ] G3. `MISSION_ANSWERS.md` có: Part 1–5, **output "📋 Checklist Deliverable"** (PASS 12/12), mục **AI log**.
- [ ] G4. Rà soát: không `.env`/secret trong repo _và lịch sử_ (`git log --all --oneline -- '*.env' '.env'` rỗng); không email/SĐT trong bài; số trong `BENCHMARK_REPORT.md` khớp JSON/CSV; mở link repo ở cửa sổ ẩn danh không 404.
- [ ] G5. Commit nhỏ, thông điệp rõ (yêu cầu của checklist); push; nộp **link repo** trên LMS trước 23h59 (GMT+7).

## 3. Rủi ro & cách xử lý

| Rủi ro                                                  | Xử lý                                                                                             |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Docker daemon tắt / thiếu WSL Ubuntu                    | Làm A1–A2 trước. Không có → code vẫn viết được, nhưng 12/12 và Part 2/5/7B bị chặn; báo Lab Coach |
| Python Windows không gửi SIGTERM → Graceful shutdown ⚠️ | Chạy script trong WSL2 (`os.name == "posix"`)                                                     |
| Phụ thuộc `pyjwt`/`redis` trên Python 3.14              | Dùng venv Python 3.11–3.12 trong WSL nếu có lỗi cài                                               |
| Cổng 8000/8080 trùng giữa các bài                       | Tắt server/stack cũ trước khi bật bài mới; luôn dùng `-p` cho compose                             |
| Lộ secret (−10đ)                                        | `.env` ở `.gitignore`; key chỉ đặt trên dashboard Railway; che token khi dán output               |
| Số liệu báo cáo không khớp JSON (Part 7 = 0đ)           | Sinh bảng trực tiếp từ file JSON/CSV, không gõ tay                                                |
| Railway cần thẻ / hết credit                            | Chuyển Render (free 750h) hoặc báo Lab Coach                                                      |

## 4. Bản đồ điểm → bằng chứng

| Hạng mục     |    Điểm | Bằng chứng nộp                                                    |
| ------------ | ------: | ----------------------------------------------------------------- |
| Part 1       |       8 | `MISSION_ANSWERS.md` Part 1                                       |
| Part 2       |       8 | `MISSION_ANSWERS.md` Part 2 (MB đo thật)                          |
| Part 3       |       8 | URL + so sánh config + Cloud Run                                  |
| Part 4       |       8 | output 401/200/429                                                |
| Part 5       |       8 | Part 5 + kết quả `test_stateless.py`                              |
| **Part 6**   |  **60** | `PASS 12/12`, `DEPLOYMENT.md`, `screenshots/`                     |
| Part 7       |      20 | `BENCHMARK_REPORT.md` + `reports/` + `benchmark-results/` + 4 ảnh |
| **Tổng thô** | **120** | → ×100/120                                                        |

## 5. Bước tiếp theo ngay sau khi lập plan

1. Thực hiện **Giai đoạn B** (code Part 6) — không cần Docker để viết và chạy `--static-only`/`--skip-docker`.
2. Song song yêu cầu bạn bật Docker Desktop + cài Ubuntu WSL2 để chạy bản đầy đủ.
3. Tiếp tục E (benchmark local) vì chạy được bằng Python thuần.

## 6. Tiến độ (cập nhật lần 2)

| Giai đoạn | Trạng thái | Ghi chú |
|---|---|---|
| A. Setup | **Xong** | Docker Desktop bật; Ubuntu WSL2 đã cài (Python 3.11 qua `uv`, Redis, wrapper `docker` gọi `docker.exe`) |
| B. Part 6 code + `PASS 12/12` | **Xong** | Chạy đầy đủ trong WSL2: `12/12 tiêu chí đạt · 43/43 checks passed`; image 56 MB |
| C. Part 1, 4 | **Xong** | Output thật trong `MISSION_ANSWERS.md` |
| C. Part 2, 5 (phần Docker) | **Bị chặn tạm thời** | Docker Hub trả 429 (anonymous 100 pull/giờ, IP dùng chung, còn 0). Job nền tự thử lại. Part 5.4/5.5 còn cần cổng 8080 đang bị stack observability chiếm |
| C. Part 5.1–5.2 | **Xong** | Health/ready + SIGTERM: request đang chạy vẫn 200, exit code 0 |
| D. Cloud deploy | **Chưa** | Cần bạn đăng nhập Railway/Render; `DEPLOYMENT.md` đã có khung |
| E. Part 7 bước 1 | **Xong** | `reports/*.json`; v2 23/23 sau khi sửa KB; `.github/workflows/eval.yml` |
| F. Part 7 bước 2 (số liệu) | **Xong** | scale_1/scale_3 CSV, chaos A–E có thời gian firing, trace chậm/lỗi + log, promtool SUCCESS. Sửa bug `PYTHONUSERBASE` trong `production/Dockerfile` |
| F. Screenshot (7 ảnh) | **Cần bạn** | Stack đang chạy ở trạng thái 2 alert firing để chụp |
| G. Đóng gói | Một phần | `reports/`, `benchmark-results/`, `BENCHMARK_REPORT.md`, `MISSION_ANSWERS.md`, `DEPLOYMENT.md` đã tạo; chưa commit/push |
