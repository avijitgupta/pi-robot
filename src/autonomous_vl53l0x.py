"""Autonomous obstacle-avoidance using VL53L0X.

This implements a simple "bump-and-avoid" style behavior:
- Drive forward while the path is clear
- If an obstacle is closer than a threshold, stop, back up, turn, and retry

It is intentionally conservative and designed to be started/stopped from a
higher-level controller (e.g., the web teleop server).

Environment variables (optional):
  VL53L0X_ADDR           I2C address (default 0x29)
  AUTO_FWD_SPEED         Forward throttle (0..1, default 0.22)
  AUTO_BACK_SPEED        Reverse throttle magnitude (0..1, default 0.18)
  AUTO_TURN_STEER        Steering magnitude (0..1, default 0.55)
  AUTO_CLEAR_MM          Distance considered "clear" (mm, default 350)
  AUTO_NEAR_MM           Distance considered "too close" (mm, default 220)
  AUTO_BACK_S            Seconds to back up on obstacle (default 0.40)
  AUTO_TURN_S_MIN        Min seconds to turn (default 0.35)
  AUTO_TURN_S_MAX        Max seconds to turn (default 0.70)
  AUTO_LOOP_HZ           Control loop rate (default 15)

Dependencies on the Pi:
  pip3 install adafruit-blinka adafruit-circuitpython-vl53l0x
  sudo apt install -y python3-rpi.gpio  (Ubuntu)
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from threading import Event

from motor_controller import MotorController


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).strip())
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip(), 0)
    except Exception:
        return default


@dataclass(frozen=True)
class AutoAvoidConfig:
    addr: int = 0x29
    fwd_speed: float = 0.22
    back_speed: float = 0.18
    turn_steer: float = 0.55
    clear_mm: int = 350
    near_mm: int = 220
    back_s: float = 0.40
    turn_s_min: float = 0.35
    turn_s_max: float = 0.70
    loop_hz: float = 15.0

    @staticmethod
    def from_env() -> "AutoAvoidConfig":
        return AutoAvoidConfig(
            addr=_env_int("VL53L0X_ADDR", 0x29),
            fwd_speed=_env_float("AUTO_FWD_SPEED", 0.22),
            back_speed=_env_float("AUTO_BACK_SPEED", 0.18),
            turn_steer=_env_float("AUTO_TURN_STEER", 0.55),
            clear_mm=int(_env_float("AUTO_CLEAR_MM", 350)),
            near_mm=int(_env_float("AUTO_NEAR_MM", 220)),
            back_s=_env_float("AUTO_BACK_S", 0.40),
            turn_s_min=_env_float("AUTO_TURN_S_MIN", 0.35),
            turn_s_max=_env_float("AUTO_TURN_S_MAX", 0.70),
            loop_hz=_env_float("AUTO_LOOP_HZ", 15.0),
        )


class VL53L0XReader:
    def __init__(self, *, address: int = 0x29):
        try:
            import board
            import busio
            import adafruit_vl53l0x
        except Exception as exc:
            raise RuntimeError(
                "VL53L0X dependencies missing. Install on the Pi:\n"
                "  pip3 install adafruit-blinka adafruit-circuitpython-vl53l0x\n"
                "Ubuntu also needs:\n"
                "  sudo apt install -y python3-rpi.gpio\n"
            ) from exc

        i2c = busio.I2C(board.SCL, board.SDA)
        t0 = time.monotonic()
        while not i2c.try_lock():
            if time.monotonic() - t0 > 3.0:
                raise RuntimeError("Timed out acquiring I2C lock")
            time.sleep(0.01)
        i2c.unlock()

        try:
            self._sensor = adafruit_vl53l0x.VL53L0X(i2c, address=address)
        except TypeError:
            self._sensor = adafruit_vl53l0x.VL53L0X(i2c)

    def read_mm(self) -> int:
        return int(self._sensor.range)


class AutoAvoidRunner:
    """Obstacle avoidance loop using the VL53L0X."""

    def __init__(self, controller: MotorController, *, cfg: AutoAvoidConfig | None = None):
        self._controller = controller
        self._cfg = cfg or AutoAvoidConfig.from_env()
        self._sensor = VL53L0XReader(address=self._cfg.addr)

    def run(self, stop_event: Event, *, heartbeat=None, on_status=None):
        cfg = self._cfg
        period_s = 1.0 / max(1.0, cfg.loop_hz)

        def beat(throttle: float = 0.0, steering: float = 0.0):
            if heartbeat:
                heartbeat(throttle, steering)

        def bounded_sleep(total_s: float):
            end = time.monotonic() + max(0.0, total_s)
            while not stop_event.is_set():
                remaining = end - time.monotonic()
                if remaining <= 0:
                    return
                time.sleep(min(0.05, remaining))
                beat(0.0, 0.0)

        last_mm: int | None = None
        obstacle = False

        self._controller.stop()
        beat(0.0, 0.0)

        while not stop_event.is_set():
            try:
                mm = self._sensor.read_mm()
                last_mm = mm
            except Exception:
                # If the sensor read fails momentarily, stop for safety.
                self._controller.stop()
                if on_status:
                    on_status({"mm": last_mm, "state": "sensor_error"})
                bounded_sleep(0.2)
                continue

            if on_status:
                on_status({"mm": mm, "state": "forward" if not obstacle else "avoid"})

            if mm <= cfg.near_mm:
                obstacle = True

            if not obstacle and mm >= cfg.clear_mm:
                # Clear path, drive forward.
                self._controller.drive_arcade(cfg.fwd_speed, 0.0)
                beat(cfg.fwd_speed, 0.0)
                time.sleep(period_s)
                continue

            # Obstacle handling: stop, back, turn, retry.
            self._controller.stop()
            beat(0.0, 0.0)
            bounded_sleep(0.08)

            # Back up
            self._controller.drive_arcade(-cfg.back_speed, 0.0)
            beat(-cfg.back_speed, 0.0)
            bounded_sleep(cfg.back_s)

            # Turn left or right randomly
            direction = random.choice([-1.0, 1.0])
            steer = direction * cfg.turn_steer
            self._controller.drive_arcade(0.0, steer)
            beat(0.0, steer)
            bounded_sleep(random.uniform(cfg.turn_s_min, cfg.turn_s_max))

            self._controller.stop()
            beat(0.0, 0.0)
            bounded_sleep(0.05)

            obstacle = False

        self._controller.stop()
        beat(0.0, 0.0)
