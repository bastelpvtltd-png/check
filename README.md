# 🚀 CryptoBot — Paper Trading Dashboard

## Features
- ✅ Auto top-30 coins by $30k+ volume (no blocked list)
- ✅ Paper trading — fake money, real signals
- ✅ Telegram alerts with charts
- ✅ Web dashboard — live pending trades, wins, losses
- ✅ Real-time Socket.IO updates
- ✅ Runs on Render / Railway / any server

---

## Quick Setup

### 1. Edit `config.py`
```python
TELEGRAM_BOT_TOKEN = "your_bot_token"
TELEGRAM_CHAT_ID   = "your_chat_id"
STARTING_BALANCE   = 100.0   # fake USD
TOP_COINS_COUNT    = 30      # scan top 30 coins
```

### 2. Run locally
```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```

---

## Deploy to Render (Free)

1. Push this folder to GitHub
2. Go to [render.com](https://render.com) → New Web Service
3. Connect your repo → it detects `render.yaml` automatically
4. Click Deploy ✅

---

## Deploy to Railway

1. Push to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Railway detects `Procfile` automatically ✅

---

## Web Dashboard

| Button | Action |
|--------|--------|
| ▶ Start Scanner | Auto-scan every 60 min |
| 🔍 Scan Now | Immediate one-time scan |
| ⏹ Stop | Pause scanner |
| 🔄 Reset | Clear all trades |

**Dashboard shows:**
- Balance, ROI, Win Rate
- Open trades with live P&L
- Trade history with outcomes

---

## File Structure
```
cryptobot/
├── app.py           # Flask web server + Socket.IO
├── scanner.py       # Live coin scanner
├── engine.py        # Indicators + scoring
├── trade_manager.py # Paper trading state
├── notifier.py      # Telegram alerts + charts
├── config.py        # All settings
├── templates/
│   └── dashboard.html  # Web UI
├── trades.json      # Auto-saved trade history
├── requirements.txt
├── render.yaml      # Render deploy config
└── Procfile         # Railway/Heroku config
```
