"""
notifier.py — Telegram alerts
"""
import time, os, tempfile
import mplfinance as mpf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import requests
import config

SESSION = requests.Session()


def _post(url, **kwargs):
    try:
        r = SESSION.post(url, timeout=15, **kwargs)
        return r
    except Exception as e:
        print(f"Telegram error: {e}")
        return None


def send(message: str):
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    for chunk in [message[i:i+4000] for i in range(0, len(message), 4000)]:
        _post(url, json={"chat_id": config.TELEGRAM_CHAT_ID,
                         "text": chunk, "parse_mode": "Markdown"})
        time.sleep(0.3)


def send_chart(photo_path: str, caption: str):
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
    caption = caption[:1020]
    try:
        with open(photo_path, 'rb') as photo:
            r = _post(url,
                data={"chat_id": config.TELEGRAM_CHAT_ID,
                      "caption": caption, "parse_mode": "Markdown"},
                files={"photo": photo})
            return r and r.status_code == 200
    except Exception as e:
        print(f"Chart send error: {e}"); return False


def build_chart(coin, df_raw, signal_idx, entry, tp1, tp2, sl,
                direction, score, outcome, pnl_pct, reasons,
                alloc_usd, bal_before, bal_after):
    try:
        end_idx   = signal_idx + 1
        start_idx = max(0, end_idx - 60)
        chart_df  = df_raw.iloc[start_idx:end_idx].copy()
        if len(chart_df) < 5: return None
        chart_df['datetime'] = pd.to_datetime(chart_df['Open_time'], unit='ms')
        chart_df = chart_df.set_index('datetime')[['open','high','low','close','volume']].astype(float)
        chart_df.index.name = 'Date'; n = len(chart_df)

        add_plots = [
            mpf.make_addplot([entry]*n, color='#2196F3', linestyle='--', width=2.0),
            mpf.make_addplot([tp1]*n,   color='#4CAF50', linestyle='-',  width=1.8),
            mpf.make_addplot([tp2]*n,   color='#1B5E20', linestyle='-',  width=1.5),
            mpf.make_addplot([sl]*n,    color='#F44336', linestyle='-',  width=1.8),
        ]

        if outcome == "TP2_HIT" or (outcome == "STILL_OPEN" and pnl_pct > 0):
            rc = '#4CAF50'; rl = f"WIN +{pnl_pct:.2f}%"
        elif outcome == "BREAKEVEN":
            rc = '#FF9800'; rl = f"BE {pnl_pct:+.2f}%"
        elif outcome == "STILL_OPEN":
            rc = '#2196F3'; rl = f"OPEN {pnl_pct:+.2f}%"
        else:
            rc = '#F44336'; rl = f"LOSS {pnl_pct:.2f}%"

        style = mpf.make_mpf_style(base_mpf_style='charles', rc={
            'axes.facecolor':'#0D1117','figure.facecolor':'#0D1117',
            'axes.edgecolor':'#30363D','text.color':'#E6EDF3',
            'axes.labelcolor':'#E6EDF3','xtick.color':'#8B949E',
            'ytick.color':'#8B949E','grid.color':'#21262D',
            'grid.linestyle':'--','grid.linewidth':0.4})

        fname = os.path.join(tempfile.gettempdir(), f"{coin}_{direction}_{signal_idx}.png")
        fig, axes = mpf.plot(chart_df, type='candle', style=style, addplot=add_plots,
                             volume=True, figsize=(14, 8), returnfig=True, tight_layout=True)
        ax = axes[0]
        dc = '#4CAF50' if direction == "LONG" else '#F44336'
        ax.set_title(f"  {coin} 1H {direction}  Score:{score}  Alloc:${alloc_usd:.2f}",
                     fontsize=13, fontweight='bold', color=dc, pad=10, loc='left')
        ax.text(0.99, 0.97, rl, transform=ax.transAxes, fontsize=12, fontweight='bold',
                color=rc, ha='right', va='top',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='#0D1117', edgecolor=rc, linewidth=2))
        bal_color = '#4CAF50' if bal_after >= bal_before else '#F44336'
        pnl_usd_d = bal_after - bal_before
        ax.text(0.99, 0.08, f"${bal_before:.2f} → ${bal_after:.2f}  ({pnl_usd_d:+.2f})",
                transform=ax.transAxes, fontsize=9, fontweight='bold',
                color=bal_color, ha='right', va='bottom',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='#0D1117', edgecolor=bal_color, linewidth=1.5))
        ax.text(0.01, 0.04,
                f"E:${entry:.4f}  TP1:${tp1:.4f}  TP2:${tp2:.4f}  SL:${sl:.4f}",
                transform=ax.transAxes, fontsize=8, family='monospace', color='#E6EDF3', va='bottom',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='#161B22', edgecolor='#30363D'))
        ax.text(0.01, 0.97, " | ".join(reasons[:5]), transform=ax.transAxes, fontsize=8,
                color='#8B949E', va='top',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#161B22', edgecolor='#30363D', alpha=0.85))
        for price, color, label in [(entry,'#2196F3','E'),(tp1,'#4CAF50','T1'),(tp2,'#1B5E20','T2'),(sl,'#F44336','SL')]:
            ax.axhline(y=price, color=color, linestyle='--' if price==entry else '-', linewidth=1.1, alpha=0.7)
            ax.annotate(f' {label}', xy=(1.0, price), xycoords=('axes fraction','data'),
                        fontsize=8, color=color, fontweight='bold', va='center')
        fig.savefig(fname, dpi=130, facecolor='#0D1117', bbox_inches='tight')
        plt.close(fig)
        return fname if os.path.exists(fname) and os.path.getsize(fname) > 1000 else None
    except Exception as e:
        print(f"Chart error: {e}"); return None


def signal_alert(coin, direction, score, htf, entry, sl, tp1, tp2,
                 rr, alloc_usd, alloc_pct, sig_lk, reasons,
                 outcome, result_pct, pnl_usd, candles, result_lk,
                 bal_before, new_bal,
                 df_ind=None, signal_idx=None):
    is_win = outcome == "TP2_HIT" or (outcome == "STILL_OPEN" and pnl_usd > 0)
    is_be  = outcome == "BREAKEVEN"
    em = "✅" if is_win else "🟡" if is_be else "🔵" if outcome == "STILL_OPEN" else "❌"
    rl = (f"✅ WIN  +{result_pct:.2f}% (+${pnl_usd:.2f})"  if is_win else
          f"🟡 BE   {result_pct:+.2f}% (+${pnl_usd:.2f})"  if is_be  else
          f"🔵 OPEN {result_pct:+.2f}% (${pnl_usd:+.2f})"  if outcome == "STILL_OPEN" else
          f"❌ LOSS {result_pct:.2f}% (-${abs(pnl_usd):.2f})")

    alloc_pct_of_bal = (alloc_usd / bal_before * 100) if bal_before > 0 else 0
    time_ln = ("⏳ Still open (72h)" if outcome == "STILL_OPEN"
               else f"⏰ {result_lk} ({candles}h)")

    msg = (
        f"{'📈' if direction=='LONG' else '📉'} *{direction} {coin}* {em}\n"
        f"📅 {sig_lk}\n"
        f"Score `{score}` | HTF `{htf}` | RR `1:{rr:.1f}`\n\n"
        f"💵 Entry `${entry:.4f}` | SL `${sl:.4f}`\n"
        f"🎯 TP1 `${tp1:.4f}` | TP2 `${tp2:.4f}`\n\n"
        f"━━ 💰 ALLOCATION ━━\n"
        f"Score {score} → {alloc_pct:.0f}% of available\n"
        f"Allocated : `${alloc_usd:.2f}` ({alloc_pct_of_bal:.1f}% of balance)\n\n"
        f"{rl}\n{time_ln}\n\n"
        f"━━ 📊 BALANCE UPDATE ━━\n"
        f"Before : `${bal_before:.2f}`\n"
        f"P&L    : `${pnl_usd:+.2f}`\n"
        f"*After  : `${new_bal:.2f}`* 💵\n\n"
        f"_{' | '.join(reasons[:5])}_"
    )

    chart_path = None
    if df_ind is not None and signal_idx is not None:
        chart_path = build_chart(coin, df_ind, signal_idx, entry, tp1, tp2, sl,
                                 direction, score, outcome, result_pct, reasons,
                                 alloc_usd, bal_before, new_bal)

    if chart_path:
        sent = send_chart(chart_path, msg)
        try: os.remove(chart_path)
        except: pass
        if not sent: send(msg)
    else:
        send(msg)
