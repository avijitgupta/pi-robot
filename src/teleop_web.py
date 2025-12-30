"""Wi-Fi teleop over HTTP with a phone-friendly web UI.

- Hosts a simple joystick page at '/'
- Receives drive commands at POST /api/drive {"throttle": -1..1, "steering": -1..1}
- Deadman safety: if commands stop arriving, motors stop

Works well from iOS Safari on the same Wi-Fi.

Security note: this is intended for a trusted LAN. You can set TELEOP_TOKEN
and pass it as a query param (?token=...) or header (X-Teleop-Token).

Requires:
  sudo apt install -y python3-flask
"""

from __future__ import annotations

import atexit
import os
import signal
import time
from threading import Lock

from flask import Flask, Response, jsonify, request, render_template_string

from motor_controller import MotorController


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).strip())
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except Exception:
        return default


def _check_token() -> bool:
    token = os.environ.get("TELEOP_TOKEN", "").strip()
    if not token:
        return True

    provided = request.args.get("token", "").strip()
    if not provided:
        provided = request.headers.get("X-Teleop-Token", "").strip()

    return provided == token


app = Flask(__name__)

# Control state
_state_lock = Lock()
_last_cmd_ts = 0.0
_last_throttle = 0.0
_last_steering = 0.0

# Safety / tuning
DEADMAN_S = _env_float("DEADMAN_S", 0.35)
MAX_PWM = _env_float("MAX_PWM", 0.6)  # keep it conservative for phone control
LEFT_MULT = _env_float("LEFT_MULT", 1.0)
RIGHT_MULT = _env_float("RIGHT_MULT", 0.87)

controller = MotorController(left_mult=LEFT_MULT, right_mult=RIGHT_MULT, max_pwm=MAX_PWM)


def _safe_shutdown():
    try:
        controller.stop()
    except Exception:
        pass
    try:
        controller.disable()
    except Exception:
        pass


atexit.register(_safe_shutdown)


def _handle_sigterm(_signum, _frame):
    # Ensure we stop/disable before exiting on service shutdown.
    _safe_shutdown()
    raise SystemExit(0)


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no" />
  <title>Robot Teleop</title>
  <style>
    :root { --bg:#0b0f14; --fg:#e7eef6; --muted:#8aa0b5; --card:#121a24; --accent:#4aa3ff; --danger:#ff4a4a; }
    body { margin:0; font-family: -apple-system, system-ui, Segoe UI, Roboto, Arial, sans-serif; background:var(--bg); color:var(--fg); }
    .wrap { max-width: 900px; margin: 0 auto; padding: 16px; }
    .row { display:flex; gap: 14px; flex-wrap: wrap; }
    .card { background:var(--card); border:1px solid rgba(255,255,255,0.06); border-radius: 14px; padding: 14px; }
    .grow { flex: 1 1 320px; }
    h1 { font-size: 18px; margin: 0 0 10px; }
    .muted { color:var(--muted); font-size: 13px; line-height: 1.4; }
    .pill { display:inline-block; padding: 6px 10px; border-radius:999px; background: rgba(255,255,255,0.06); font-size: 13px; }
    .pill.ok { background: rgba(74,163,255,0.16); color: var(--accent); }
    .pill.bad { background: rgba(255,74,74,0.16); color: var(--danger); }

    .joyWrap { display:flex; align-items:center; justify-content:center; }
    .joy {
      width: min(70vw, 360px);
      height: min(70vw, 360px);
      max-width: 360px;
      max-height: 360px;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 18px;
      position: relative;
      touch-action: none;
      user-select: none;
    }
    .centerDot {
      position:absolute; left:50%; top:50%; width:8px; height:8px; transform: translate(-50%,-50%);
      background: rgba(255,255,255,0.35); border-radius: 50%;
    }
    .knob {
      position:absolute; left:50%; top:50%; width: 84px; height: 84px; transform: translate(-50%,-50%);
      background: rgba(74,163,255,0.22);
      border: 1px solid rgba(74,163,255,0.55);
      border-radius: 22px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.35);
    }

    .btnRow { display:flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
    button {
      appearance:none; border:none; border-radius: 12px; padding: 12px 14px; font-weight: 700;
      background: rgba(255,255,255,0.08); color: var(--fg);
    }
    button.stop { background: rgba(255,74,74,0.20); border: 1px solid rgba(255,74,74,0.55); }
    button:active { transform: translateY(1px); }

    .kv { display:grid; grid-template-columns: 150px 1fr; gap: 8px 12px; margin-top: 8px; }
    .kv div { font-size: 13px; }
    .kv .k { color: var(--muted); }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="row">
      <div class="card grow">
        <h1>Robot Teleop (Wi‑Fi)</h1>
        <div class="muted">Touch + drag the pad. Release to stop. Keep this page open while driving.</div>
        <div style="margin-top:10px; display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
          <span id="status" class="pill">Connecting…</span>
          <span id="safety" class="pill">Deadman…</span>
          <span class="pill">Update: <span id="hz">0</span> Hz</span>
        </div>
        <div class="joyWrap" style="margin-top: 14px;">
          <div id="joy" class="joy">
            <div class="centerDot"></div>
            <div id="knob" class="knob"></div>
          </div>
        </div>
        <div class="btnRow">
          <button id="stop" class="stop">STOP</button>
          <button id="slow">Max 30%</button>
          <button id="med">Max 60%</button>
          <button id="fast">Max 90%</button>
        </div>

        <div class="muted" style="margin-top:10px;">Hold buttons to drive (sends continuously while pressed):</div>
        <div class="btnRow" style="margin-top:8px;">
          <button id="fwd" class="hold">FWD</button>
          <button id="left" class="hold">LEFT</button>
          <button id="right" class="hold">RIGHT</button>
          <button id="rev" class="hold">REV</button>
        </div>
      </div>

      <div class="card grow">
        <h1>Tips (iOS)</h1>
        <div class="muted">
          Open this page in Safari on your iPhone: <b>http://PI_IP:8080</b> (same Wi‑Fi).<br/>
          Optional: Share → <b>Add to Home Screen</b> for full-screen control.
        </div>
        <div class="kv">
          <div class="k">Throttle</div><div>Up = forward, down = reverse</div>
          <div class="k">Steering</div><div>Right = turn right, left = turn left</div>
          <div class="k">Safety</div><div>Deadman: if Wi‑Fi drops, robot stops</div>
        </div>
        <div class="muted" style="margin-top:10px;">
          If you set <code>TELEOP_TOKEN</code>, append <code>?token=...</code> to the URL.
        </div>
      </div>
    </div>
  </div>

<script>
(() => {
  const joy = document.getElementById('joy');
  const knob = document.getElementById('knob');
  const status = document.getElementById('status');
  const safety = document.getElementById('safety');
  const hzEl = document.getElementById('hz');

  let maxMag = 0.6;
  let active = false;
  let holdMode = false;
  let sendTimer = null;
  let desiredThrottle = 0;
  let desiredSteering = 0;
  let lastSend = 0;
  let sentCount = 0;
  let lastHzTs = performance.now();

  function setStatus(ok, text) {
    status.textContent = text;
    status.className = ok ? 'pill ok' : 'pill bad';
  }

  function setSafety(ok, text) {
    safety.textContent = text;
    safety.className = ok ? 'pill ok' : 'pill bad';
  }

  async function send(throttle, steering) {
    const now = performance.now();
    // ~20Hz
    if (now - lastSend < 50) return;
    lastSend = now;

    try {
      const res = await fetch('/api/drive' + location.search, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ throttle, steering })
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      setStatus(true, 'Connected');
      sentCount++;
    } catch (e) {
      setStatus(false, 'Disconnected');
    }

    const t = performance.now();
    if (t - lastHzTs > 1000) {
      hzEl.textContent = String(sentCount);
      sentCount = 0;
      lastHzTs = t;
    }
  }

  async function stop() {
    active = false;
    holdMode = false;
    if (sendTimer) {
      clearInterval(sendTimer);
      sendTimer = null;
    }
    desiredThrottle = 0;
    desiredSteering = 0;
    knob.style.left = '50%';
    knob.style.top = '50%';
    try {
      await fetch('/api/stop' + location.search, { method: 'POST' });
    } catch (_) {}
  }

  function ensureSendLoop() {
    if (sendTimer) return;
    // Keep sending while active to satisfy deadman.
    sendTimer = setInterval(() => {
      if (!active) return;
      send(desiredThrottle, desiredSteering);
    }, 50);
  }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function handlePoint(clientX, clientY) {
    holdMode = false;
    const rect = joy.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = clientX - cx;
    const dy = clientY - cy;

    const radius = Math.min(rect.width, rect.height) * 0.40;
    const nx = clamp(dx / radius, -1, 1);
    const ny = clamp(dy / radius, -1, 1);

    // Steering: right positive. Throttle: up positive.
    const steering = nx * maxMag;
    const throttle = (-ny) * maxMag;

    desiredThrottle = throttle;
    desiredSteering = steering;

    knob.style.left = (50 + nx * 40) + '%';
    knob.style.top = (50 + ny * 40) + '%';

    ensureSendLoop();
    send(desiredThrottle, desiredSteering);
  }

  function startHold(throttle, steering) {
    active = true;
    holdMode = true;
    desiredThrottle = throttle;
    desiredSteering = steering;
    ensureSendLoop();
    send(desiredThrottle, desiredSteering);
  }

  function bindHoldButton(el, throttleSign, steeringSign) {
    el.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      startHold(throttleSign * maxMag, steeringSign * maxMag);
    });
    el.addEventListener('pointerup', stop);
    el.addEventListener('pointercancel', stop);
    el.addEventListener('pointerleave', () => { if (active) stop(); });
  }

  joy.addEventListener('pointerdown', (e) => {
    active = true;
    joy.setPointerCapture(e.pointerId);
    ensureSendLoop();
    handlePoint(e.clientX, e.clientY);
  });

  joy.addEventListener('pointermove', (e) => {
    if (!active) return;
    handlePoint(e.clientX, e.clientY);
  });

  joy.addEventListener('pointerup', stop);
  joy.addEventListener('pointercancel', stop);

  document.getElementById('stop').addEventListener('click', stop);

  bindHoldButton(document.getElementById('fwd'),  1.0,  0.0);
  bindHoldButton(document.getElementById('rev'), -1.0,  0.0);
  bindHoldButton(document.getElementById('left'), 0.0, -1.0);
  bindHoldButton(document.getElementById('right'),0.0,  1.0);

  // If maxMag changes via buttons, keep hold buttons in sync.
  const setMaxMag = (v) => {
    maxMag = v;
    if (active) {
      if (holdMode) {
        desiredThrottle = Math.sign(desiredThrottle) * maxMag;
        desiredSteering = Math.sign(desiredSteering) * maxMag;
      } else {
        // Preserve joystick direction but clamp to new magnitude.
        desiredThrottle = Math.max(-maxMag, Math.min(maxMag, desiredThrottle));
        desiredSteering = Math.max(-maxMag, Math.min(maxMag, desiredSteering));
      }
    }
  };
  document.getElementById('slow').addEventListener('click', () => setMaxMag(0.30));
  document.getElementById('med').addEventListener('click', () => setMaxMag(0.60));
  document.getElementById('fast').addEventListener('click', () => setMaxMag(0.90));

  // Poll status so you can tell when deadman has fired.
  setInterval(async () => {
    try {
      const res = await fetch('/api/status' + location.search);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const s = await res.json();
      if (s.last_cmd_age_s == null) {
        setSafety(false, 'Deadman: idle');
      } else if (s.last_cmd_age_s > s.deadman_s) {
        setSafety(false, 'Deadman: STOPPED');
      } else {
        setSafety(true, 'Deadman: OK');
      }
    } catch (_) {
      setSafety(false, 'Deadman: ?');
    }
  }, 250);

  // Initial ping
  send(0, 0);
})();
</script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(HTML)


@app.post("/api/drive")
def api_drive():
    if not _check_token():
        return Response("Unauthorized\n", status=401)

    data = request.get_json(silent=True) or {}
    throttle = float(data.get("throttle", 0.0))
    steering = float(data.get("steering", 0.0))

    global _last_cmd_ts, _last_throttle, _last_steering
    with _state_lock:
        _last_cmd_ts = time.time()
        _last_throttle = throttle
        _last_steering = steering

    controller.drive_arcade(throttle, steering)
    return jsonify(ok=True)


@app.post("/api/stop")
def api_stop():
    if not _check_token():
        return Response("Unauthorized\n", status=401)
    global _last_cmd_ts, _last_throttle, _last_steering
    with _state_lock:
        _last_cmd_ts = time.time()
        _last_throttle = 0.0
        _last_steering = 0.0
    controller.stop()
    return jsonify(ok=True)


@app.get("/api/status")
def api_status():
    with _state_lock:
        age = time.time() - _last_cmd_ts if _last_cmd_ts else None
        return jsonify(
            last_cmd_age_s=age,
            deadman_s=DEADMAN_S,
            throttle=_last_throttle,
            steering=_last_steering,
            max_pwm=MAX_PWM,
            left_mult=LEFT_MULT,
            right_mult=RIGHT_MULT,
        )


def _deadman_loop():
    global _last_cmd_ts
    while True:
        time.sleep(0.05)
        with _state_lock:
            ts = _last_cmd_ts
        if not ts:
            continue
        if time.time() - ts > DEADMAN_S:
            controller.stop()


def main():
    import threading

    try:
        signal.signal(signal.SIGTERM, _handle_sigterm)
    except Exception:
        # Not all platforms support SIGTERM/signal handling the same way.
        pass

    threading.Thread(target=_deadman_loop, daemon=True).start()

    host = os.environ.get("HOST", "0.0.0.0")
    port = _env_int("PORT", 8080)

    print("Wi-Fi Teleop server")
    print(f"Open: http://<pi-ip>:{port}")
    if os.environ.get("TELEOP_TOKEN"):
        print("Token enabled: append ?token=... to the URL")

    try:
        app.run(host=host, port=port, threaded=True)
    finally:
        _safe_shutdown()


if __name__ == "__main__":
    main()
