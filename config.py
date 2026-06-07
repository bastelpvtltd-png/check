# ══════════════════════════════════════════════
# CONFIG — Meka wenas karanna
# ══════════════════════════════════════════════

TELEGRAM_BOT_TOKEN = "8905811864:AAEaEzjyirk1dJivfvtQWtumL3mXXCh5-SQ"
TELEGRAM_CHAT_ID   = "1450144996"

# Paper trading starting balance
STARTING_BALANCE = 100.0

# Top N coins by volume (auto-selected from Binance)
TOP_COINS_COUNT = 30
MIN_VOLUME_USDT = 30_000  # minimum 30k USDT 24h volume

# Scoring thresholds
MIN_SCORE    = 6
MIN_RR       = 1.8
COOLDOWN_BARS = 4
DATA_LIMIT   = 700

# Skip low-activity UTC hours (midnight to 6am UTC)
SKIP_UTC_START = 0
SKIP_UTC_END   = 6

# Risk management
MAX_ALLOC_PCT = 0.20   # max 20% of balance per trade
MIN_TRADE_USD = 2.0

SCORE_ALLOC_PCT = {
    6:  5.0,
    7:  8.0,
    8: 12.0,
    9: 18.0,
    10: 22.0,
}

# Binance endpoints (geo-block bypass)
BINANCE_ENDPOINTS = [
    "https://api.binance.us",
    "https://api1.binance.us",
    "https://api2.binance.us",
    "https://api3.binance.us",
    "https://api4.binance.us",
]

LK_OFFSET_SEC = 5 * 3600 + 30 * 60  # Sri Lanka UTC+5:30
