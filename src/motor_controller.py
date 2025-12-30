"""Reusable motor controller for TB6612FNG.

This is intentionally kept separate from the interactive keyboard teleop so you
can use the same motor logic from other entrypoints (web, gamepad, etc.).

Environment overrides (optional):
  PWMA, AIN1, AIN2, PWMB, BIN1, BIN2, STBY

Typical usage:
  from motor_controller import MotorController
  controller = MotorController(max_pwm=0.6)
  controller.drive_arcade(throttle=0.3, steering=-0.2)
"""

from __future__ import annotations

import os

from gpiozero import PWMOutputDevice, DigitalOutputDevice


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except Exception:
        return default


# ----- Pin mapping (BCM) -----
PWMA = _env_int("PWMA", 18)
AIN1 = _env_int("AIN1", 23)
AIN2 = _env_int("AIN2", 24)
PWMB = _env_int("PWMB", 13)
BIN1 = _env_int("BIN1", 6)
BIN2 = _env_int("BIN2", 5)
STBY = _env_int("STBY", 25)


class MotorController:
    def __init__(
        self,
        *,
        pwm_freq_hz: int = 1000,
        left_mult: float = 1.0,
        right_mult: float = 0.87,
        max_pwm: float = 1.0,
    ):
        self.stby = DigitalOutputDevice(STBY)
        self.left_pwm = PWMOutputDevice(PWMA, frequency=pwm_freq_hz)
        self.left_in1 = DigitalOutputDevice(AIN1)
        self.left_in2 = DigitalOutputDevice(AIN2)
        self.right_pwm = PWMOutputDevice(PWMB, frequency=pwm_freq_hz)
        self.right_in1 = DigitalOutputDevice(BIN1)
        self.right_in2 = DigitalOutputDevice(BIN2)

        self.left_mult = float(left_mult)
        self.right_mult = float(right_mult)
        self.max_pwm = float(max_pwm)

        self.enable()
        self.stop()

    def enable(self):
        self.stby.on()

    def disable(self):
        self.stby.off()

    def stop(self):
        self.left_pwm.value = 0
        self.left_in1.off()
        self.left_in2.off()
        self.right_pwm.value = 0
        self.right_in1.off()
        self.right_in2.off()

    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        return lo if v < lo else hi if v > hi else v

    def _apply_motor(self, pwm: PWMOutputDevice, in1: DigitalOutputDevice, in2: DigitalOutputDevice, value: float):
        value = self._clamp(value, -self.max_pwm, self.max_pwm)
        if value > 0:
            in1.on()
            in2.off()
            pwm.value = value
        elif value < 0:
            in1.off()
            in2.on()
            pwm.value = -value
        else:
            pwm.value = 0
            in1.off()
            in2.off()

    def drive_arcade(self, throttle: float, steering: float):
        """Arcade drive.

        throttle: -1..1 (forward positive)
        steering: -1..1 (right positive)
        """

        throttle = self._clamp(float(throttle), -1.0, 1.0)
        steering = self._clamp(float(steering), -1.0, 1.0)

        left = throttle + steering
        right = throttle - steering

        mag = max(abs(left), abs(right), 1.0)
        left /= mag
        right /= mag

        left *= self.left_mult
        right *= self.right_mult

        self._apply_motor(self.left_pwm, self.left_in1, self.left_in2, left)
        self._apply_motor(self.right_pwm, self.right_in1, self.right_in2, right)
