# AI Deal Bot

Bot Telegram thu thập tin AI/dev/deal từ Reddit + Twitter, lọc bằng OpenAI, gửi notification tiếng Việt.

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

### 3. OpenAI API Key

1. Vào https://platform.openai.com/api-keys
2. Đăng nhập tài khoản
3. Tạo key mới (**Create new secret key**)
4. Copy vào `OPENAI_API_KEY`

## Chạy

```powershell
# Test Telegram trước
python main.py --test-telegram

# Chạy thử 1 cycle (xem có collect được tin không)
python main.py --once

# Chạy production (forever)
python main.py
```

Mỗi 15 phút bot poll Reddit, mỗi 20 phút poll Twitter, lọc và gửi tin score ≥ 6 vào Telegram của bạn.

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

## Tùy chỉnh

Mở `config.yaml`:

- **Thêm/bớt subreddit**: edit `reddit.subreddits`
- **Thêm/bớt Twitter account**: edit `twitter.accounts`
- **Đổi tần suất**: `schedule.reddit_interval_minutes`
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
    │   └── twitter_nitter.py
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

**Twitter/Nitter không trả về gì**: Nitter instances hay sập. Thử update danh sách trong `config.yaml` từ https://github.com/zedeus/nitter/wiki/Instances.

**OpenAI báo lỗi auth**: kiểm tra API key tại platform.openai.com/api-keys, check còn credits/billing không.

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
