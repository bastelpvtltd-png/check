"""
app.py — Flask web dashboard + Socket.IO real-time updates
"""
import os, time, threading
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import trade_manager as tm
import scanner
import notifier
import config

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cryptobot2026')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')


# ── Signal callback → push to all web clients ────────────────────
def on_new_signal(trade):
    socketio.emit('new_signal', trade)
    socketio.emit('state_update', _get_dashboard_state())

scanner.set_signal_callback(on_new_signal)


def _get_dashboard_state():
    state = tm.get_state()
    total   = state["wins"] + state["losses"] + state["breakevens"]
    wr      = round(state["wins"] / total * 100, 1) if total > 0 else 0
    roi     = round((state["balance"] - state["starting"]) / state["starting"] * 100, 2)
    total_pnl = round(state["balance"] - state["starting"], 4)
    scan_st = scanner.get_status()
    return {
        "balance":       round(state["balance"], 2),
        "starting":      state["starting"],
        "roi":           roi,
        "total_pnl":     total_pnl,
        "wins":          state["wins"],
        "losses":        state["losses"],
        "breakevens":    state["breakevens"],
        "total_trades":  total,
        "win_rate":      wr,
        "open_trades":   state["open_trades"],
        "closed_trades": state["closed_trades"][:50],
        "scanner":       scan_st,
    }


# ── Routes ───────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('dashboard.html')


@app.route('/api/state')
def api_state():
    return jsonify(_get_dashboard_state())


@app.route('/api/scan', methods=['POST'])
def api_scan():
    scanner.scan_now()
    return jsonify({"ok": True, "msg": "Scan started"})


@app.route('/api/scanner/start', methods=['POST'])
def api_start():
    interval = int(request.json.get('interval', 60))
    scanner.start(interval)
    return jsonify({"ok": True, "msg": f"Scanner started (every {interval} min)"})


@app.route('/api/scanner/stop', methods=['POST'])
def api_stop():
    scanner.stop()
    return jsonify({"ok": True, "msg": "Scanner stopped"})


@app.route('/api/reset', methods=['POST'])
def api_reset():
    scanner.stop()
    tm.reset()
    return jsonify({"ok": True, "msg": "Reset complete"})


@app.route('/api/coins')
def api_coins():
    return jsonify({"coins": scanner.get_status().get("coins", [])})


# ── Socket.IO ────────────────────────────────────────────────────
@socketio.on('connect')
def on_connect():
    emit('state_update', _get_dashboard_state())


# ── Live price updater ───────────────────────────────────────────
def _price_updater():
    """Every 30s update live P&L on open trades and push to clients."""
    while True:
        time.sleep(30)
        try:
            state = tm.get_state()
            if state["open_trades"]:
                for t in state["open_trades"]:
                    from engine import get_live_price
                    price = get_live_price(t["coin"])
                    if price:
                        tm.update_open_trade_price(t["trade_id"], price)
                socketio.emit('state_update', _get_dashboard_state())
        except Exception as e:
            print(f"Price updater error: {e}")


# ── Startup ──────────────────────────────────────────────────────
def create_app():
    tm.load()
    # Start price updater thread
    t = threading.Thread(target=_price_updater, daemon=True)
    t.start()
    return app


if __name__ == '__main__':
    create_app()
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
