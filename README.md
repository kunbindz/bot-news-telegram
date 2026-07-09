# AI Deal Bot

Bot Telegram thu thập tin AI/dev/deal từ Reddit + RSS feeds, lọc bằng OpenAI, gửi notification tiếng Việt.

## Yêu cầu

- Python 3.11+
- Windows (script setup là PowerShell, có thể chạy được trên Linux/Mac với chỉnh sửa nhỏ)

## Cài đặt

```powershell
cd D:\Projects\ai-deal-bot
.\setup.ps1
```

Script sẽ tạo venv, cài deps, và tạo file `.env` từ template.

## Lấy API keys

Mở file `.env` và điền 3 keys sau:

> Reddit dùng RSS public, không cần API key.

### 1. Telegram Bot Token

1. Mở Telegram, search **@BotFather**
2. Gõ `/newbot` → đặt tên bot (vd: "My AI Deal Bot")
3. Đặt username kết thúc bằng `bot` (vd: `myaideal_bot`)
4. Copy token dạng `123456789:ABC-DEF...` vào `TELEGRAM_BOT_TOKEN`

### 2. Telegram Chat ID

1. Search **@userinfobot** trong Telegram
2. Gõ `/start`
3. Bot trả về `Id: 123456789` → copy số đó vào `TELEGRAM_CHAT_ID`
4. **Quan trọng:** Nhắn `/start` cho chính bot bạn vừa tạo ở bước 1 (nếu không bot không gửi được tin nhắn cho bạn)

### 3. AI Provider (OpenAI-compatible)

1. Lấy API key từ nhà cung cấp → copy vào `API_KEY`
2. (Tùy chọn) `BASE_URL` và `MODEL` để đổi endpoint/model chủ động qua `.env`.
   Bỏ trống sẽ dùng giá trị mặc định trong `config.yaml` (`ai_filter.base_url` / `ai_filter.model`).
   Ví dụ trong `.env`:
   ```
   BASE_URL=https://api.pateway.ai
   MODEL=deepseek-v4-flash
   ```

## Chạy

```powershell
# Test Telegram trước
python main.py --test-telegram

# Chạy thử 1 cycle (xem có collect được tin không)
python main.py --once

# Chạy production (forever)
python main.py
```

Mỗi 60 phút bot poll Reddit + RSS feeds, lọc và gửi tin score ≥ 6 vào Telegram của bạn.

## Chạy nền 24/7 trên Windows

### Cách 1: NSSM (khuyên dùng)

1. Download NSSM tại https://nssm.cc/download
2. Giải nén, copy `nssm.exe` vào `C:\Windows\System32`
3. Chạy PowerShell as Administrator:
   ```powershell
   nssm install AIDealBot
   ```
4. Trong UI:
   - **Path**: `D:\Projects\ai-deal-bot\.venv\Scripts\python.exe`
   - **Startup directory**: `D:\Projects\ai-deal-bot`
   - **Arguments**: `main.py`
5. Click **Install service**
6. Start:
   ```powershell
   nssm start AIDealBot
   ```

Quản lý service:
```powershell
nssm status AIDealBot    # check status
nssm restart AIDealBot   # restart
nssm stop AIDealBot      # stop
nssm remove AIDealBot    # xóa service
```

### Cách 2: Task Scheduler (đơn giản hơn)

1. Mở **Task Scheduler** → Create Basic Task
2. Trigger: When the computer starts
3. Action: Start a program
   - Program: `D:\Projects\ai-deal-bot\.venv\Scripts\python.exe`
   - Arguments: `main.py`
   - Start in: `D:\Projects\ai-deal-bot`
4. Properties → Settings → uncheck "Stop the task if it runs longer than..."

## Deploy miễn phí trên GitHub Actions

Chạy bot theo lịch (mỗi giờ 1 lần) bằng GitHub Actions — miễn phí, không cần thẻ.
Workflow đã có sẵn ở `.github/workflows/bot.yml`, gọi `python main.py --once`.

> ⚠️ **Đánh đổi:** không còn tiến trình chạy liên tục nên **các lệnh Telegram tương tác
> mất tác dụng** (`/pause`, `/status`, `/top`, `/draft_top`, `/score`, `/stats`).
> Bot chỉ tự đẩy tin mỗi giờ. Cần lệnh tương tác thì phải host 24/7 (VD Fly.io / Oracle Cloud).

**1. Push repo lên GitHub** (nếu chưa có remote):
```bash
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin master
```

**2. Nạp secrets** — vào repo trên GitHub → **Settings → Secrets and variables → Actions
→ New repository secret**, thêm 5 secret:

| Name | Ví dụ |
|------|-------|
| `TELEGRAM_BOT_TOKEN` | `123:ABC...` |
| `TELEGRAM_CHAT_ID` | `123456789` |
| `API_KEY` | `sk-...` |
| `BASE_URL` | `https://api.pateway.ai` |
| `MODEL` | `deepseek-v4-flash` |

**3. Chạy thử** — tab **Actions → news-bot → Run workflow** (nút `workflow_dispatch`).
Sau đó nó tự chạy mỗi giờ theo cron.

**Ghi chú:**
- DB dedupe được giữ giữa các lần chạy qua `actions/cache` (không gửi trùng tin).
- Cron GitHub dùng UTC và có thể trễ 5–15 phút; tần suất thực tế ~mỗi giờ.
- Quiet hours / diversity cap trong `config.yaml` vẫn áp dụng bình thường.
- GitHub **tạm dừng** scheduled workflow nếu repo không có hoạt động trong 60 ngày —
  chỉ cần vào bấm "Enable workflow" lại là chạy tiếp.

## Tùy chỉnh

Mở `config.yaml`:

- **Thêm/bớt subreddit**: edit `reddit.subreddits`
- **Thêm/bớt nguồn RSS**: edit `feeds.sources`
- **Đổi tần suất**: `schedule.reddit_interval_minutes` / `schedule.feeds_interval_minutes`
- **Đổi ngưỡng score**: `ai_filter.min_score_to_notify` (5 = nhiều tin, 8 = chỉ tin xuất sắc)
- **Tắt AI filter**: `ai_filter.enabled: false` (sẽ gửi tất cả tin pass keyword + dedupe)
- **Đổi model**: `ai_filter.model: "gpt-4o"` nếu muốn quality cao hơn (mặc định `gpt-4o-mini` rẻ hơn)

## Cấu trúc dự án

```
ai-deal-bot/
├── main.py                     # Entry point + scheduler
├── config.yaml                 # Cấu hình sources, keywords
├── .env                        # API keys (không commit)
├── db.sqlite                   # Dedupe + history
├── logs/bot.log
└── src/
    ├── models.py               # Item dataclass
    ├── db.py                   # SQLite helpers
    ├── pipeline.py             # Orchestrator
    ├── collectors/
    │   ├── reddit_rss.py       # Reddit via public RSS (no auth)
    │   └── feeds_rss.py        # HN / Dev.to / GitHub / FE blogs via RSS
    ├── filters/
    │   ├── keyword.py          # Pre-filter (tiết kiệm AI credit)
    │   ├── dedupe.py           # Dedupe vs SQLite
    │   └── ai_classifier.py    # OpenAI classifier
    └── notifier/
        └── telegram_sender.py
```

## Troubleshooting

**Telegram báo "chat not found"**: bạn chưa nhắn `/start` cho bot. Vào Telegram, mở bot vừa tạo, nhấn Start.

**Reddit báo 429**: bot bị rate limit. Tăng `request_delay_seconds` trong config.yaml lên 2-3 giây, hoặc giảm số subreddit.

**HH Tech API báo lỗi auth**: kiểm tra `API_KEY` trong `.env`, check còn credits/billing không.

**Bot gửi quá nhiều tin**: tăng `min_score_to_notify` lên 7 hoặc 8.

**Bot không gửi tin nào**: 
- Check logs trong `logs/bot.log`
- Thử tắt AI filter: `ai_filter.enabled: false`
- Giảm `min_score_to_notify` xuống 4

## Phase 3 (chưa làm)

- [ ] Bot commands: `/pause`, `/resume`, `/stats`, `/addsub`
- [ ] Inline buttons: "🔖 Lưu", "🚫 Mute nguồn"
- [ ] Udemy free course tracker
- [ ] Telegram channels VN forwarder (Telethon)
- [ ] Web dashboard FastAPI
