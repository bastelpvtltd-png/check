"""
trade_manager.py — Paper trading state management
All trades stored in memory + trades.json for persistence
"""
import json, os, time, threading
from datetime import datetime
import config

TRADES_FILE = "trades.json"
_lock = threading.Lock()

# ── State ────────────────────────────────────────────────────────
_state = {
    "balance":      config.STARTING_BALANCE,
    "starting":     config.STARTING_BALANCE,
    "open_trades":  [],   # list of trade dicts
    "closed_trades":[],   # list of trade dicts
    "wins": 0, "losses": 0, "breakevens": 0,
}


def _save():
    try:
        with open(TRADES_FILE, "w") as f:
            json.dump(_state, f, indent=2)
    except Exception as e:
        print(f"Save error: {e}")


def load():
    global _state
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE) as f:
                _state = json.load(f)
            print(f"✅ Loaded trades.json — Balance: ${_state['balance']:.2f}")
        except Exception as e:
            print(f"Load error: {e}")


def get_state():
    with _lock:
        return {
            "balance":       round(_state["balance"], 4),
            "starting":      _state["starting"],
            "open_trades":   list(_state["open_trades"]),
            "closed_trades": list(_state["closed_trades"]),
            "wins":          _state["wins"],
            "losses":        _state["losses"],
            "breakevens":    _state["breakevens"],
        }


def available():
    locked = sum(t["allocated_usd"] for t in _state["open_trades"])
    return max(0.0, _state["balance"] - locked)


def can_open():
    return available() >= config.MIN_TRADE_USD


def get_allocation(score):
    pct     = config.SCORE_ALLOC_PCT.get(min(max(score, 6), 10), 5.0)
    avail   = available()
    max_usd = _state["balance"] * config.MAX_ALLOC_PCT
    alloc   = min(avail * (pct / 100.0), max_usd)
    return round(alloc, 4), pct


def open_trade(trade: dict):
    with _lock:
        _state["open_trades"].append(trade)
        _save()


def close_trade(trade_id: str, pnl_usd: float, outcome: str):
    with _lock:
        trade = None
        for i, t in enumerate(_state["open_trades"]):
            if t["trade_id"] == trade_id:
                trade = _state["open_trades"].pop(i)
                break
        if not trade:
            return None, None

        bal_before = round(_state["balance"], 4)
        _state["balance"] = round(_state["balance"] + pnl_usd, 4)
        trade["pnl_usd"]    = round(pnl_usd, 4)
        trade["outcome"]    = outcome
        trade["bal_after"]  = _state["balance"]
        trade["closed_at"]  = _lk_now()

        if outcome == "TP2_HIT" or (outcome == "STILL_OPEN" and pnl_usd > 0):
            _state["wins"] += 1
            trade["result_label"] = "WIN"
        elif outcome == "BREAKEVEN":
            _state["breakevens"] += 1
            trade["result_label"] = "BREAKEVEN"
        else:
            _state["losses"] += 1
            trade["result_label"] = "LOSS"

        _state["closed_trades"].insert(0, trade)
        # Keep last 500 closed trades
        _state["closed_trades"] = _state["closed_trades"][:500]
        _save()
        return bal_before, _state["balance"]


def update_open_trade_price(trade_id, current_price):
    """Update live P&L for an open trade."""
    with _lock:
        for t in _state["open_trades"]:
            if t["trade_id"] == trade_id:
                entry = t["entry"]
                direction = t["direction"]
                alloc = t["allocated_usd"]
                if direction == "LONG":
                    pct = (current_price - entry) / entry * 100
                else:
                    pct = (entry - current_price) / entry * 100
                t["current_price"] = current_price
                t["live_pct"]      = round(pct, 3)
                t["live_pnl"]      = round(alloc * pct / 100, 4)
                break


def reset():
    """Reset to starting state."""
    with _lock:
        _state["balance"]       = config.STARTING_BALANCE
        _state["starting"]      = config.STARTING_BALANCE
        _state["open_trades"]   = []
        _state["closed_trades"] = []
        _state["wins"]          = 0
        _state["losses"]        = 0
        _state["breakevens"]    = 0
        _save()


def _lk_now():
    return datetime.utcfromtimestamp(
        time.time() + config.LK_OFFSET_SEC
    ).strftime('%d %b %Y %I:%M %p')
