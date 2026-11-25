# Deployment Information

> **Trạng thái: ĐÃ DEPLOY** lên Railway, `check_production_ready.py --public-url` → **PASS 12/12 (44/44 checks)**.

## Public URL

https://day14-agent-production-8924a34b.up.railway.app

## Platform

Railway: project `comfortable-wonder`, environment `production`, gồm service `day14-agent` (agent Part 6 trong `06-lab-complete/`) và service `Redis` trong cùng project.

## Cách deploy (Railway)

Tạo project trống và thêm Redis, thêm service rỗng `day14-agent`, đặt biến trên dashboard (xem dưới), rồi:

```bash
npm i -g @railway/cli
railway login
cd 06-lab-complete
railway link        # chọn project comfortable-wonder → production → day14-agent
railway up          # upload thư mục, build bằng Dockerfile
```

Sau đó vào Settings → Networking của service `day14-agent` → Generate Domain để lấy URL public.

## Test Commands (4 lệnh tự kiểm ở CP6)

```bash
BASE=https://<URL>
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kiểm tra bằng script chấm: `cd 06-lab-complete && python check_production_ready.py --public-url $BASE`

## Environment Variables Set (đặt trên dashboard nền tảng, không ghi trong code)

- `PORT` (Railway tự cấp, tôi không đặt)
- `REDIS_URL` = `${{Redis.REDIS_URL}}` (biến tham chiếu tới service Redis của Railway)
- `AGENT_API_KEY` (chuỗi ngẫu nhiên, giá trị không ghi trong repo)
- `ENVIRONMENT` = `production`
- `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`, `LOG_LEVEL`: không đặt, dùng mặc định trong code (10 request/phút, 1.0 USD/ngày, INFO)

## Screenshots

- `screenshots/dashboard.png` — dashboard nền tảng
- `screenshots/running.png` — service đang chạy
- `screenshots/test.png` — kết quả 4 lệnh test
