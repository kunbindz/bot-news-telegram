# Setup script cho Windows PowerShell
# Chạy: .\setup.ps1

Write-Host "=== AI Deal Bot Setup ===" -ForegroundColor Cyan

# Check Python
$pyVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python chưa được cài. Cài Python 3.11+ tại python.org" -ForegroundColor Red
    exit 1
}
Write-Host "Python: $pyVersion" -ForegroundColor Green

# Create venv
if (-not (Test-Path ".venv")) {
    Write-Host "Tạo virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# Activate venv
Write-Host "Activate venv..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# Install deps
Write-Host "Cài đặt dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip
pip install -r requirements.txt

# Copy .env template
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ""
    Write-Host "⚠️  Đã tạo .env từ template." -ForegroundColor Yellow
    Write-Host "    Hãy mở file .env và điền các API keys trước khi chạy bot." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "=== Setup xong! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Bước tiếp theo:" -ForegroundColor Cyan
Write-Host "  1. Mở file .env và điền 4 keys (xem README.md để biết cách lấy)"
Write-Host "  2. Test Telegram:    python main.py --test-telegram"
Write-Host "  3. Test một cycle:   python main.py --once"
Write-Host "  4. Chạy production:  python main.py"
