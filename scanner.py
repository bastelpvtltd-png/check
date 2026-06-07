"""
scanner.py — Live signal scanner (runs in background thread)
"""
import time, threading
from datetime import datetime
import config
import engine
import trade_manager as tm
import notifier

_running   = False
_thread    = None
_on_signal = None
_coin_list = []
_last_scan_info = {"time": None, "coins": [], "status": "idle"}


def set_signal_callback(fn):
    global _on_signal
    _on_signal = fn


def get_status():
    return {
        "running":   _running,
        "last_scan": _last_scan_info,
        "coins":     _coin_list,
    }


def _lk_now():
    return datetime.utcfromtimestamp(
        time.time() + config.LK_OFFSET_SEC
    ).strftime('%d %b %Y %I:%M %p')


def _ms_to_lk(ms):
    if ms is None: return "Still Open"
    return datetime.utcfromtimestamp(ms/1000 + config.LK_OFFSET_SEC).strftime('%d %b %Y %I:%M %p')


def _calc_pnl_usd(outcome, result_pct, alloc_usd, entry, tp1, tp2, sl, direction):
    if outcome == "TP2_HIT":
        tp1_pct = abs(tp1 - entry) / entry * 100
        tp2_pct = abs(tp2 - entry) / entry * 100
        return round(alloc_usd * ((tp1_pct/100)*0.5 + (tp2_pct/100)*0.5), 4)
    elif outcome == "SL_HIT":
        sl_pct = abs(sl - entry) / entry * 100
        return round(-alloc_usd * (sl_pct / 100), 4)
    elif outcome == "BREAKEVEN":
        tp1_pct = abs(tp1 - entry) / entry * 100
        return round(alloc_usd * (tp1_pct/100) * 0.5, 4)
    else:
        return round(alloc_usd * (result_pct / 100), 4)


def _check_outcome(df_full, signal_idx, direction, entry, tp1, tp2, sl):
    future = df_full.iloc[signal_idx+1:signal_idx+73]
    tp1_hit = False
    for i, (_, row) in enumerate(future.iterrows()):
        h = float(row['high']); l = float(row['low']); ms = int(row['Open_time'])
        if direction == "LONG":
            if l <= sl:
                if tp1_hit: return "BREAKEVEN", (tp1-entry)/entry*100*0.5+(sl-entry)/entry*100*0.5, i+1, ms
                return "SL_HIT", (sl-entry)/entry*100, i+1, ms
            if not tp1_hit and h >= tp1: tp1_hit = True
            if tp1_hit and h >= tp2:
                return "TP2_HIT", ((tp1-entry)/entry*100)*0.5+((tp2-entry)/entry*100)*0.5, i+1, ms
        else:
            if h >= sl:
                if tp1_hit: return "BREAKEVEN", (entry-tp1)/entry*100*0.5+(entry-sl)/entry*100*0.5, i+1, ms
                return "SL_HIT", (entry-sl)/entry*100, i+1, ms
            if not tp1_hit and l <= tp1: tp1_hit = True
            if tp1_hit and l <= tp2:
                return "TP2_HIT", ((entry-tp1)/entry*100)*0.5+((entry-tp2)/entry*100)*0.5, i+1, ms
    if len(future) == 0: return "NO_DATA", 0.0, 0, None
    last = float(future.iloc[-1]['close']); lms = int(future.iloc[-1]['Open_time'])
    pct = (last-entry)/entry*100 if direction=="LONG" else (entry-last)/entry*100
    return "STILL_OPEN", pct, len(future), lms


def _scan_once():
    global _coin_list, _last_scan_info
    import pandas as pd

    print(f"\n🔍 Scanning... {_lk_now()}")
    _last_scan_info["status"] = "scanning"
    _last_scan_info["time"]   = _lk_now()

    # ── Get coins ──────────────────────────────────────────────
    coins = engine.get_top_coins(config.TOP_COINS_COUNT, config.MIN_VOLUME_USDT)
    if not coins:
        # fallback hardcoded list
        coins = [
            "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
            "ADAUSDT","AVAXUSDT","DOTUSDT","LINKUSDT","MATICUSDT",
            "LTCUSDT","UNIUSDT","NEARUSDT","APTUSDT","INJUSDT",
            "OPUSDT","ARBUSDT","SUIUSDT","TIAUSDT","FETUSDT",
            "STXUSDT","WLDUSDT","SEIUSDT","ATOMUSDT","FILUSDT",
            "LDOUSDT","RUNEUSDT","GALAUSDT","SANDUSDT","MANAUSDT",
        ]
        print(f"⚠️  Fallback coin list ({len(coins)} coins)")

    _coin_list = coins
    _last_scan_info["coins"] = coins

    state = tm.get_state()
    notifier.send(
        f"🔍 *Scanner running* — {_lk_now()}\n"
        f"Scanning *{len(coins)} coins*\n"
        f"Balance: `${state['balance']:.2f}`"
    )

    signals_found = 0
    skip_reasons  = {}   # coin → reason (for debug)

    for coin in coins:
        if not _running: break
        if not tm.can_open():
            print("⛔ Balance too low"); break

        try:
            # ── HTF — relaxed: accept NEUTRAL with weak trend ──
            htf_trend, htf_strength = engine.get_htf_trend(coin)

            # If NEUTRAL, try to detect weak trend from 4h alone
            if htf_trend == "NEUTRAL":
                df4h = engine.download_data(coin, interval="4h", limit=60)
                if df4h is not None and len(df4h) >= 30:
                    c4 = df4h['close']
                    e20 = c4.ewm(span=20, adjust=False).mean()
                    lc  = c4.iloc[-1]
                    if lc > e20.iloc[-1]:
                        htf_trend = "BULL"; htf_strength = 1
                    elif lc < e20.iloc[-1]:
                        htf_trend = "BEAR"; htf_strength = 1

            if htf_trend == "NEUTRAL":
                skip_reasons[coin] = "HTF NEUTRAL"
                continue

            # ── 1H data ────────────────────────────────────────
            df_full = engine.download_data(coin, interval="1h", limit=config.DATA_LIMIT)
            if df_full is None or len(df_full) < 100:
                skip_reasons[coin] = "No data"
                continue

            df_ind   = engine.compute_indicators(df_full)
            key_lvls = engine.find_key_levels(df_ind)

            # ── Scan last 6 candles (more chances) ─────────────
            start_i  = max(100, len(df_ind) - 7)
            targets  = list(range(start_i, len(df_ind) - 1))
            last_sig = {"LONG": -99, "SHORT": -99}

            # Both directions if HTF allows
            if htf_trend == "BULL":
                directions = ["LONG"]
            elif htf_trend == "BEAR":
                directions = ["SHORT"]
            else:
                directions = ["LONG", "SHORT"]

            coin_signals = 0

            for i in targets:
                if not tm.can_open(): break
                c = df_ind.iloc[i]
                req_cols = ['ATR','EMA200','STOCHRSI','ADX']
                if any(pd.isna(c.get(k, float('nan'))) for k in req_cols):
                    continue

                for direction in directions:
                    if i - last_sig[direction] < config.COOLDOWN_BARS:
                        continue

                    score, reasons = engine.score_signal(
                        df_ind, i, direction, htf_trend, htf_strength, key_lvls)

                    if score < config.MIN_SCORE:
                        continue

                    entry = float(c['close'])
                    sl, tp1, tp2, sl_pct, tp1_pct, rr = engine.calculate_levels(
                        df_ind, i, direction, entry)
                    if rr < config.MIN_RR:
                        continue

                    alloc_usd, alloc_pct = tm.get_allocation(score)
                    if alloc_usd < config.MIN_TRADE_USD:
                        continue

                    outcome, result_pct, candles, result_ms = _check_outcome(
                        df_full, i, direction, entry, tp1, tp2, sl)

                    pnl_usd = _calc_pnl_usd(outcome, result_pct, alloc_usd,
                                             entry, tp1, tp2, sl, direction)

                    trade_id  = f"{coin}_{direction}_{i}_{int(time.time())}"
                    sig_lk    = _ms_to_lk(int(df_full.iloc[i]['Open_time']))
                    result_lk = _ms_to_lk(result_ms)
                    is_win    = outcome == "TP2_HIT" or (outcome == "STILL_OPEN" and pnl_usd > 0)
                    is_be     = outcome == "BREAKEVEN"

                    trade = {
                        "trade_id":      trade_id,
                        "coin":          coin,
                        "direction":     direction,
                        "htf":           htf_trend,
                        "score":         score,
                        "entry":         entry,
                        "sl":            sl,
                        "tp1":           tp1,
                        "tp2":           tp2,
                        "rr":            round(rr, 2),
                        "allocated_usd": alloc_usd,
                        "alloc_pct":     alloc_pct,
                        "outcome":       outcome,
                        "result_pct":    round(result_pct, 4),
                        "pnl_usd":       round(pnl_usd, 4),
                        "candles":       candles,
                        "sig_time":      sig_lk,
                        "result_time":   result_lk,
                        "reasons":       reasons,
                        "is_win":        is_win,
                        "is_be":         is_be,
                        "opened_at":     _lk_now(),
                        "current_price": entry,
                        "live_pct":      0.0,
                        "live_pnl":      0.0,
                    }

                    tm.open_trade(trade)
                    bal_before, new_bal = tm.close_trade(trade_id, pnl_usd, outcome)
                    trade["bal_before"] = bal_before
                    trade["bal_after"]  = new_bal

                    last_sig[direction] = i
                    signals_found += 1
                    coin_signals  += 1
                    em = "✅" if is_win else "🟡" if is_be else "❌"
                    print(f"  {em} {coin} {direction} score={score} → {outcome} ${pnl_usd:+.2f}")

                    notifier.signal_alert(
                        coin, direction, score, htf_trend,
                        entry, sl, tp1, tp2, rr,
                        alloc_usd, alloc_pct, sig_lk, reasons,
                        outcome, result_pct, pnl_usd, candles, result_lk,
                        bal_before, new_bal,
                        df_ind=df_ind, signal_idx=i,
                    )

                    if _on_signal:
                        _on_signal(trade)

                    time.sleep(0.5)

            if coin_signals == 0 and coin not in skip_reasons:
                skip_reasons[coin] = "Score/ADX/RR filter"

        except Exception as e:
            print(f"  ❌ {coin} error: {e}")
            skip_reasons[coin] = str(e)

        time.sleep(0.3)

    # ── Debug summary to Telegram ──────────────────────────────
    _last_scan_info["status"] = "done"
    state = tm.get_state()
    total = state["wins"] + state["losses"] + state["breakevens"]
    wr    = state["wins"] / total * 100 if total > 0 else 0
    roi   = (state["balance"] - state["starting"]) / state["starting"] * 100

    # Show skip reasons for first 10 coins
    skip_lines = "\n".join(
        f"`{c}` → {r}" for c, r in list(skip_reasons.items())[:10]
    )

    print(f"\n✅ Scan done | Signals: {signals_found} | Balance: ${state['balance']:.2f}")
    notifier.send(
        f"✅ *Scan complete* — {_lk_now()}\n"
        f"Coins scanned: `{len(coins)}`\n"
        f"New signals: `{signals_found}`\n\n"
        f"💵 Balance : `${state['balance']:.2f}`\n"
        f"📈 ROI     : `{roi:+.2f}%`\n"
        f"✅ Wins: `{state['wins']}` | ❌ Losses: `{state['losses']}`\n"
        f"🏆 Win Rate: `{wr:.1f}%`\n\n"
        f"━━ Skip reasons (sample) ━━\n"
        f"{skip_lines if skip_lines else '_None_'}"
    )


def _loop(interval_minutes=60):
    while _running:
        try:
            _scan_once()
        except Exception as e:
            print(f"Scanner loop error: {e}")
        for _ in range(interval_minutes * 60):
            if not _running: break
            time.sleep(1)


def start(interval_minutes=60):
    global _running, _thread
    if _running:
        return
    _running = True
    _thread  = threading.Thread(target=_loop, args=(interval_minutes,), daemon=True)
    _thread.start()
    print(f"✅ Scanner started (every {interval_minutes} min)")


def stop():
    global _running
    _running = False


def scan_now():
    t = threading.Thread(target=_scan_once, daemon=True)
    t.start()
