# Benchmark & Observability Report — Day 14

**Họ tên:** Pham Tuan Cuong
**Ngày chạy:** 2026-11-25 (phần 2–3); phần 4–6 xem trạng thái ở từng mục
**Môi trường:** Windows 11, Intel Core i5-12500H (16 luồng), 15.7 GB RAM; Python 3.11 (venv); agent, load generator và các agent khác chạy **cùng một máy** nên số đo có nhiễu. Agent chạy `python app.py` (uvicorn 1 process, 1 worker).

> Mọi số trong phần 2–3 được sinh trực tiếp từ `reports/*.json` (`load_v2_c*.json`, `load_v2_slow_*.json`, `eval_*.json`).

---

## 1. SLO của agent

| SLI                          | SLO      | Lý do chọn ngưỡng này                                                                                                                                                                                                                      |
| ---------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| p95 latency `/ask`           | < 500 ms | Request thành công bình thường mất ~190–250 ms (p50 ≈ 200 ms) nên 500 ms còn dư ~2× biên; người dùng chat chấp nhận được dưới nửa giây. Đặt theo p95 vì average che giấu nhóm request chậm. Đây cũng là ngưỡng mặc định của `load_test.py` |
| Error rate `/ask`            | < 2 %    | Mock LLM có lỗi upstream nền ~1 % (`MOCK_ERROR_RATE=0.01`); 2 % cho phép dao động ngẫu nhiên nhưng vẫn bắt được sự cố thật. Mặc định của `load_test.py`                                                                                    |
| Accuracy trên golden dataset | ≥ 85 %   | Ngưỡng quality gate trong CI (`.github/workflows/eval.yml`); v2 sau khi sửa KB đạt 100 % nên còn biên để bắt regression                                                                                                                    |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

300 request mỗi lần chạy, agent v2 (`MOCK_ERROR_RATE=0.01`, `MOCK_SLOW_RATE=0.03` mặc định).

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS   | p50 (ms) | p95 (ms) | p99 (ms) | Error rate    | SLO  |
| ----------- | ----- | -------- | -------- | -------- | ------------- | ---- |
| 1           | 3.85  | 203.1    | 236.4    | 1700.6   | 0.33% (1/300) | PASS |
| 10          | 40.7  | 190.3    | 248.8    | 1702.9   | 2.00% (6/300) | PASS |
| 50          | 96.11 | 202.1    | 500.1    | 1734.7   | 0.33% (1/300) | FAIL |
| 100         | 47.84 | 718.0    | 3820.2   | 4187.4   | 1.33% (4/300) | FAIL |

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency. Từ c=1 lên c=10 RPS tăng 10.6× (3.85 → 40.7), gần tuyến tính vì mỗi request chủ yếu _chờ_ (mock LLM `sleep`) nên nhiều request chồng lên nhau được. Từ c=10 lên c=50 (5× số worker) RPS chỉ tăng 2.4× (40.7 → 96.11) và p95 chạm 500.1 ms — đúng ngưỡng SLO, `load_test.py` báo FAIL: agent bắt đầu bão hoà. Ở c=100 RPS **giảm** còn 47.84 và p95/p99 vọt lên 3820.2/4187.4 ms: quá tải, request xếp hàng chờ. Lưu ý đây là lần chạy ngắn (6.27 s) trên cùng máy với load generator, nên nút thắt có thể nằm ở cả agent (1 process, 1 event loop) lẫn bên phát tải; tôi không tách riêng được hai yếu tố này trong bài. Điểm cần nhớ: tới c≈10 agent còn trong SLO, từ c≈50 thì vi phạm. p99 ≈ 1.7 s ở c=1 và c=10 là các request "slow" (+1500 ms) do `MOCK_SLOW_RATE`, không phải do tải. Error rate dao động 0.33–2 % vì lỗi mock ngẫu nhiên 1 %, c=10 có 6/300 lỗi (2.00 %) chạm đúng ngưỡng 2 % mà `load_test.py` vẫn tính PASS (nó chỉ báo FAIL khi vượt ngưỡng), chỉ là nhiễu ngẫu nhiên chứ không phải dấu hiệu quá tải.

### 2.2 Tail latency (300 request, concurrency 20)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
| ---------------- | -------- | -------- | -------- |
| 0                | 208.1    | 482.8    | 491.6    |
| 0.03 (mặc định)  | 238.2    | 453.6    | 1692.4   |
| 0.1              | 393.6    | 1711.5   | 1747.8   |

**Nhận xét:** Chỉ số nhạy nhất với request chậm là **p99** rồi tới p95. Từ slow rate 0 → 0.03, avg chỉ tăng 30 ms (+14%) nhưng p99 nhảy từ 491.6 lên 1692.4 ms (×3.4) trong khi p95 gần như đứng yên (482.8 → 453.6 ms) vì mới ~3 % request chậm, chưa vượt 5 %. Khi slow rate lên 0.1 (> 5 % request chậm), p95 cũng nhảy lên 1711.5 ms (vi phạm SLO) còn avg mới 393.6 ms — dưới 400 ms, nhìn "ổn". Average trộn nhóm nhỏ rất chậm vào số đông nhanh nên che đi việc cứ ~10 người dùng thì có 1 người chờ gần 2 giây. Vì vậy SLO phải đặt theo percentile (p95/p99), không đặt theo average. (RPS khác nhau giữa 3 lần chạy chủ yếu do nhiễu máy và request chậm chiếm worker, không dùng so sánh.)

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số                | Agent v1       | Agent v2       | Agent v2 (sau khi sửa KB)         |
| --------------------- | -------------- | -------------- | --------------------------------- |
| Accuracy              | 4.3% (1/23)    | 91.3% (21/23)  | 100.0% (23/23)                    |
| Avg tokens / câu      | 57.2           | 108.7          | 113.7                             |
| Tổng cost (USD)       | 0.000406       | 0.000756       | 0.00079                           |
| Cost / câu đúng (USD) | 0.00040575     | 3.599e-05      | 3.436e-05                         |
| Quality gate          | FAIL (min 80%) | PASS (min 80%) | PASS (min 100%, không regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID          | Keyword bị thiếu            | Bạn đã sửa gì                                                                                                |
| ----------- | --------------------------- | ------------------------------------------------------------------------------------------------------------ |
| security-02 | token, hết hạn, chữ ký      | Thêm entry `(["jwt"], ...)` mô tả khác biệt API key (cố định, không hết hạn) và JWT (token, chữ ký, hết hạn) |
| scaling-03  | cpu, memory, custom metrics | Thêm entry `(["hpa", "kubernetes", "autoscal"], ...)` mô tả HPA scale theo CPU, memory, custom metrics       |

Chỉ sửa `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (đã chép sang `production/utils/mock_llm.py` để stack Docker cũng đạt 100 %); không đụng tới `golden_dataset.jsonl`. Chạy lại với `--baseline reports/eval_v2.json`: 2 câu được cải thiện, **0 regression**.

**Quality gate trong CI:** `run_eval.py` thoát với exit code 1 nếu accuracy < `--min-accuracy` hoặc có câu regression so với baseline, nên step đó fail và PR bị chặn khi bật "Require status checks to pass". Job nằm ở `.github/workflows/eval.yml` (`--min-accuracy 0.85`). Kiểm chứng tại chỗ: eval v1 (accuracy 4.3%) thoát exit code 1.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- Chất lượng: v1 chỉ đúng 1/23 câu (4.3%), v2 đúng 21/23 (91.3%) nhờ bước retrieval.
- Chi phí: v2 tốn gấp 1.9× token mỗi câu (57.2 → 108.7) vì prompt chứa thêm tài liệu, tổng cost cao hơn ~1.9×. Nhưng **cost / câu đúng** của v2 rẻ hơn khoảng 11× (0.00040575 → 3.599e-05 USD), vì v1 trả tiền cho gần như toàn câu sai. Đây là lý do dùng "cost / câu đúng" thay vì "cost / câu" để so hai phiên bản.
- Latency: retrieval thêm ~20 ms mỗi request (p50 eval v1 184.3 ms vs v2 200.5 ms). p95 eval của v2 (1701.4 ms) cao hơn v1 (203.3 ms) chủ yếu vì lần chạy v2 gặp request "slow" ngẫu nhiên (+1500 ms) trong 23 câu, không phải do retrieval — mẫu 23 câu quá nhỏ để kết luận về tail.

---

## 4. Observability stack (production)

Stack chạy bằng `docker compose -p k5-day14-observability up -d --build --scale agent=…` trong `06-lab-complete/benchmark-observability/production/` (agent + Nginx + Prometheus + Grafana + Jaeger + Locust). Tải: Locust, 30 người dùng (ramp 5/s) trong các thí nghiệm. Số liệu bên dưới lấy từ API của Prometheus/Jaeger và từ log chạy thật (`scripts` điều phối nằm ngoài repo; số thời gian được đo từ lúc chạy `docker compose up -d` — **đã gồm** ~10–15 s tạo lại container — tới lần đầu Prometheus API báo `firing`, poll mỗi 5 s).

> Sửa 1 lỗi trong file đề cho: `production/Dockerfile` thiếu `ENV PYTHONUSERBASE=/home/agent/.local` nên container crash-loop `No module named 'uvicorn'` (user `agent` có home `/app`, còn package được copy vào `/home/agent/.local`). Đã thêm đúng dòng đó.

### 4.1 Screenshot

Các ảnh nằm ở `screenshots/`, chụp từ stack đang chạy với tải 30 user ở cấu hình `mock-llm-large` (cuối chuỗi thí nghiệm, ngày 25/11/2026 khoảng 21:35–21:53 giờ máy):

- [x] `grafana-dashboard.png` — Dashboard "Day 14 — AI Agent Overview", khoảng "Last 15 minutes": traffic 16.4 req/s, error rate 18.25 %, latency p95 653.68 ms, 2 instance up, LLM cost (1h) $28.49, chỉ có model `mock-llm-large`.
- [x] `jaeger-slow-trace.png` — trace chậm `cc959e4…` (Jaeger chỉ hiện 7 ký tự đầu), `POST /ask` 200, **2.0 s**, bắt đầu 21:51:18.106, 4 span; span `chat mock-llm-large` chiếm gần hết thời gian, `agent.retrieve_context` chỉ 13.6 ms.
- [x] `jaeger-error-trace.png` — trace lỗi `5d15189705037e07c3a10ebecb127c2f`, `POST /ask` **503**, 295 ms, bắt đầu 21:34:51.414; span `agent.run` có event `exception` (`utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)`), span `chat mock-llm-large` đánh dấu lỗi.
- [x] `prometheus-alert-firing.png` — trang Alerts: `LLMCostBurnRateHigh` và `AgentHighErrorRate` cùng **FIRING**; `AgentHighLatencyP95` và `AgentInstanceDown` inactive.

Lưu ý: Jaeger lưu trace trong bộ nhớ nên các trace ở mục 4.3 (đã ghi lại cùng log JSON ngay khi đo) không còn để chụp; hai ảnh Jaeger ở trên là hai trace khác cùng loại, lấy sau đó từ cùng stack. Phân tích ở 4.3 dựa trên cặp trace/log đã ghi; ảnh minh họa cùng mẫu hình (span LLM chiếm gần hết thời gian ở trace chậm, event `exception` ở trace lỗi).

### 4.2 Thí nghiệm "phá hệ thống"

| #   | Thay đổi                   | Alert nào firing                         | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất                                                                                                     |
| --- | -------------------------- | ---------------------------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| A   | `MOCK_ERROR_RATE=0.2`      | `AgentHighErrorRate` (pending sau 33 s)  | **93 s**                      | Error rate: đo được 19.7 % (SLO alert 5 %); trace lỗi có event `exception`                                                     |
| B   | `MOCK_SLOW_RATE=0.3`       | `AgentHighLatencyP95` (pending sau 27 s) | **147 s**                     | p95 `/ask` lên 1.92 s trong khi error rate chỉ 0.74 %; avg tăng ít hơn p95                                                     |
| C   | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (pending sau 27 s) | **148 s**                     | Cost USD/giờ: 18.5 $/h so với khoảng 1.4–1.8 $/h trước đó (~10×); p95 0.64 s                                                   |
| D   | `docker pause` 1 instance  | `AgentInstanceDown` (pending sau 15 s)   | **45 s**                      | Instances up giảm 2 → 1; error rate của agent vẫn xanh (0.55 %)                                                                |
| E   | `AGENT_VERSION=v1`         | **không có** (quan sát 200 s)            | —                             | Metric hạ tầng không đổi: error 1.6 %, p95 0.20 s, đều xanh (tôi không đo riêng tokens/s hay retrieval ratio ở thí nghiệm này) |

Ghi chú trung thực: (1) `LLMCostBurnRateHigh` đã đang firing ngay từ đầu phiên đo vì cửa sổ 5 phút còn chứa tải 100 user của lần chạy Locust scaling trước đó (alert tự hết trước thí nghiệm B); số 148 s ở dòng C đo từ trạng thái đã inactive. (2) Alert dùng `rate(...[1m])`/`for` nên thời gian phát hiện phụ thuộc cửa sổ: A nhanh hơn B vì B cần `for: 2m`. (3) Với D tôi **không** đo số lỗi 504 phía Locust/Nginx; chỉ xác nhận metric của agent vẫn xanh (0.55 %) trong khi một instance không phản hồi.

Chạy thêm tổ hợp A + C để có 2 alert cùng firing cho ảnh `prometheus-alert-firing.png`: `LLMCostBurnRateHigh` firing sau 3 s (cửa sổ 5 phút vẫn còn dữ liệu model lớn), `AgentHighErrorRate` firing sau **98 s**.

Alert rules đã unit test: `promtool test rules alert_rules_test.yml` → `SUCCESS`.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Metric hạ tầng (latency, error rate, up) chỉ nói "service có chạy và nhanh không", không nói "câu trả lời có đúng không". v1 trả lời nhanh, ít lỗi, rẻ hơn → mọi panel xanh nhưng chất lượng tụt xuống ~4 % (mục 3). Cách phát hiện: (1) chạy **eval trên golden dataset** làm quality gate trong CI trước khi deploy (`run_eval.py --baseline`, exit code 1 khi regression) và định kỳ chạy lại trên bản đang chạy (canary/synthetic eval); (2) thêm **metric chất lượng** vào Prometheus, ví dụ tỉ lệ request có retrieval (`retrieved=true`) hoặc điểm eval gần nhất rồi alert khi tụt; (3) tín hiệu từ người dùng (👍/👎, tỉ lệ hỏi lại) và LLM-as-judge lấy mẫu từ traffic thật; (4) alert khi `agent_info{version=...}` đổi ngoài kế hoạch.

**Trả lời Exercise 7.4** (đo ở cấu hình mặc định, 30 user, 2 instance, cửa sổ 2 phút):

1. avg = **232 ms**, p50 = 176 ms, p95 = **293 ms**, p99 = **1831 ms**. avg và p95 gần nhau vì chỉ ~3 % request chậm (< 5 %) nên chưa kéo p95 lên; khoảng cách lớn nằm ở p99 (≈ 8× avg) — đó là nhóm request "slow" +1.5 s mà average che đi.
2. Có chia đều: 9.56 req/s và 9.59 req/s cho hai instance (Nginx round-robin).
3. input tokens/s = 1466, output tokens/s = 766 (≈ 1.9×) vì prompt của v2 gồm system prompt + tài liệu retrieval + câu hỏi, trong khi output chỉ là câu trả lời ngắn.
4. `curl http://localhost:8080/metrics` trả **404**: Nginx chủ động không proxy `/metrics` ra ngoài để không lộ số liệu nội bộ (traffic, cost, version); Prometheus scrape trực tiếp từng instance trong mạng Docker nội bộ.

### 4.3 Debug bằng trace

Trace chậm nhất tìm được (Jaeger, sắp xếp Longest First; xảy ra lúc đang chạy thí nghiệm C nên model là `mock-llm-large`):

- `trace_id`: `a22b4b87d5c8d187f93832f18a8e86bb`
- Tổng thời gian: 1999.1 ms (`POST /ask`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-large` (1973.3 ms, 98.7 %); `agent.retrieve_context` chỉ 23.2 ms. Attribute: `gen_ai.usage.input_tokens=74`, `output_tokens=37`. Nghĩa là chậm do LLM upstream (một request "slow" +1.5 s và model lớn chậm hơn 2.5×), không phải code của agent.
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-25T09:35:48.968958+00:00", "level": "INFO", "service": "observable-agent", "instance": "f8258430c285", "event": "llm_call", "trace_id": "a22b4b87d5c8d187f93832f18a8e86bb", "span_id": "79f43f502a73bd19", "request_id": "37c1e94b7b0c", "model": "mock-llm-large", "agent_version": "v2", "input_tokens": 74, "output_tokens": 37, "cost_usd": 0.000555, "llm_ms": 1973.3}
{"ts": "2026-11-25T09:35:48.969654+00:00", "level": "INFO", "service": "observable-agent", "instance": "f8258430c285", "event": "http_request", "trace_id": "a22b4b87d5c8d187f93832f18a8e86bb", "span_id": "79f43f502a73bd19", "request_id": "37c1e94b7b0c", "method": "POST", "route": "/ask", "status": 200, "ms": 1998.2}
```

Trace lỗi (tag `error=true`): `5cc5e6c2fcd78477868006b1fafe3a2f` — 186.3 ms, `POST /ask` trả 503, span `chat mock-llm-large` có event `exception` (`LLMError: Upstream LLM error: 503 Service Unavailable (mock)`). Log JSON khớp:

```json
{"ts": "2026-11-25T09:35:46.038922+00:00", "level": "INFO", "service": "observable-agent", "instance": "47470adde997", "event": "llm_error", "trace_id": "5cc5e6c2fcd78477868006b1fafe3a2f", "span_id": "cf46c0ff74eccabe", "request_id": "a3267ae74ac2", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-25T09:35:46.039263+00:00", "level": "INFO", "service": "observable-agent", "instance": "47470adde997", "event": "http_request", "trace_id": "5cc5e6c2fcd78477868006b1fafe3a2f", "span_id": "cf46c0ff74eccabe", "request_id": "a3267ae74ac2", "method": "POST", "route": "/ask", "status": 503, "ms": 185.8}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Dòng `POST /ask` trong `benchmark-results/scale_{1,3}_stats.csv` (Locust, `-u 100 -r 10 -t 2m`, wait 0.5–2 s giữa các lần gọi):

| Số instance | RPS   | p50 (ms) | p95 (ms) | p99 (ms) | Failures        |
| ----------- | ----- | -------- | -------- | -------- | --------------- |
| 1           | 59.63 | 190      | 290      | 1700     | 67/7088 (0.95%) |
| 3           | 59.87 | 190      | 230      | 1700     | 73/7112 (1.03%) |

**Giải thích kết quả:** Scale từ 1 lên 3 instance **không làm RPS tăng** (59.63 → 59.87) và p50/p99 y nguyên (190 / 1700 ms); chỉ p95 giảm từ 290 xuống 230 ms. Lý do: tải là _vòng kín_ — 100 user mỗi người chờ 0.5–2 s (TB ≈ 1.25 s) rồi mới gọi tiếp, nên RPS tối đa ≈ 100 / (1.25 + ~0.24) ≈ 67 req/s kể cả `/health` — Locust (số user và thời gian nghỉ) mới là nút thắt, không phải agent: 1 instance chưa bão hoà (mỗi request chủ yếu _chờ_ mock LLM, async nên 1 container xử lý được nhiều request chồng nhau), nên thêm instance chỉ bớt xếp hàng ở phần đuôi (p95). Ngoài ra latency của một request bị quyết định bởi 1 lần gọi LLM (~190 ms, và request "slow" +1.5 s) — thêm instance không làm lần gọi đó nhanh hơn, đúng như gợi ý "xem panel LLM latency". Failures ~1 % ở cả hai lần là lỗi `503` ngẫu nhiên của mock LLM (`MOCK_ERROR_RATE=0.01`), không liên quan scale. Muốn thấy lợi ích của scale cần tải cao hơn, ví dụ nhiều user hơn hoặc giảm wait time, để 1 instance (giới hạn 0.5 CPU) thật sự bão hoà; tôi chưa chạy thêm cấu hình đó.

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. **Đừng tin average, hãy đặt SLO theo percentile.** Slow rate 3 % chỉ làm avg tăng ~14 % nhưng p99 tăng ~3.4×; ở 10 % request chậm thì p95 vi phạm SLO còn avg vẫn dưới 400 ms.
  2. **Dashboard xanh ≠ agent đúng.** v1 nhanh, rẻ, không lỗi nhưng chỉ đúng 1/23 câu; chỉ eval trên golden dataset (và quality gate bằng exit code) mới bắt được. Dùng "cost / câu đúng" mới so sánh được hai phiên bản (v2 rẻ hơn ~11×).
  3. **Alert phải được đo và hiểu cửa sổ của nó.** Thời gian phát hiện từ 45 s (instance down) tới ~150 s (latency, cost) vì `rate[1m]`/`for`; metric của agent không thấy lỗi xảy ra ở Nginx (D), nên cần thêm giám sát ở tầng LB hoặc synthetic check. Scale ngang cũng không cứu được nút thắt nằm ở LLM upstream hay ở bên phát tải.
- Nếu đưa agent này lên production thật, sẽ thêm: (a) alert theo error rate của Nginx/LB và synthetic probe từ bên ngoài; (b) metric chất lượng (điểm eval định kỳ, tỉ lệ có retrieval, 👍/👎) và alert khi tụt; (c) alert ngân sách theo ngày (cộng với cost guard của Part 6) thay vì chỉ burn-rate; (d) SLO + error budget burn alert nhiều cửa sổ (1h/6h) thay cho ngưỡng cố định; (e) sampling trace khi traffic lớn.
