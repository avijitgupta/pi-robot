"""Basic VL53L0X sanity test.

What this does:
- Optionally scans the I2C bus to confirm the sensor shows up (usually address 0x29)
- Reads distance continuously and prints it in millimeters

Recommended driver (Adafruit CircuitPython):
  pip3 install adafruit-blinka adafruit-circuitpython-vl53l0x smbus2

On Raspberry Pi, also enable I2C:
  sudo raspi-config   -> Interface Options -> I2C -> Enable
  sudo reboot

Quick checks:
  python3 src/test_vl53l0x.py --scan
  python3 src/test_vl53l0x.py

Notes:
- The VL53L0X is a sensor. TB6612FNG is your motor driver.
- Wiring (typical breakout): VIN/3V3, GND, SDA, SCL.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import time


def _scan_i2c(bus: int) -> list[int]:
    try:
        from smbus2 import SMBus
    except Exception as exc:
        raise RuntimeError(
            "smbus2 not installed. Install with: pip3 install smbus2\n"
            "Alternatively run: sudo apt install -y i2c-tools && i2cdetect -y 1"
        ) from exc

    found: list[int] = []
    with SMBus(bus) as smbus:
        for addr in range(0x03, 0x78):
            try:
                smbus.write_quick(addr)
                found.append(addr)
            except OSError:
                pass
    return found


def _format_addr(addr: int) -> str:
    return f"0x{addr:02X}"


def _init_sensor(address: int):
    try:
        import board
        import busio
        import adafruit_vl53l0x
    except Exception as exc:
        print(f"VL53L0X import error: {exc}")
        raise RuntimeError(
            "Missing dependencies for VL53L0X driver.\n\n"
            "Install:\n"
            "  pip3 install adafruit-blinka adafruit-circuitpython-vl53l0x\n\n"
            "If I2C isn't enabled on the Pi:\n"
            "  sudo raspi-config  (Interface Options -> I2C)\n"
        ) from exc

    # Initialize I2C
    i2c = busio.I2C(board.SCL, board.SDA)
    # Wait for lock (some systems need a moment)
    t0 = time.monotonic()
    while not i2c.try_lock():
        if time.monotonic() - t0 > 3.0:
            raise RuntimeError("Timed out acquiring I2C lock. Is I2C enabled and not used by another process?")
        time.sleep(0.01)
    i2c.unlock()

    # Create sensor; Adafruit driver supports address kwarg on most versions.
    try:
        sensor = adafruit_vl53l0x.VL53L0X(i2c, address=address)
    except TypeError:
        sensor = adafruit_vl53l0x.VL53L0X(i2c)

    return sensor


def main() -> int:
    parser = argparse.ArgumentParser(description="VL53L0X I2C scan + distance read")
    parser.add_argument("--bus", type=int, default=int(os.environ.get("I2C_BUS", "1")), help="I2C bus number (default: 1)")
    parser.add_argument(
        "--address",
        type=lambda s: int(s, 0),
        default=int(os.environ.get("VL53L0X_ADDR", "0x29"), 0),
        help="I2C address (default: 0x29)",
    )
    parser.add_argument("--hz", type=float, default=10.0, help="Read rate in Hz (default: 10)")
    parser.add_argument("--scan", action="store_true", help="Scan I2C and exit")
    args = parser.parse_args()

    if platform.system().lower() == "windows":
        print("This script is meant to run on the Raspberry Pi (Linux) connected to the VL53L0X over I2C.")
        print("You can still edit it on Windows; run it on the Pi via SSH.")

    # Always do a quick scan first so you get an immediate "is it detected" signal.
    try:
        addrs = _scan_i2c(args.bus)
        print(f"I2C bus {args.bus} devices: {', '.join(_format_addr(a) for a in addrs) if addrs else '(none)'}")
        if args.address not in addrs:
            print(f"Expected VL53L0X at {_format_addr(args.address)} was NOT found.")
            print("Check wiring (SDA/SCL swapped?), power, and that I2C is enabled.")
    except Exception as exc:
        print(f"I2C scan failed: {exc}")
        print("On Raspberry Pi you can also run: sudo apt install -y i2c-tools && i2cdetect -y 1")
        if args.scan:
            return 2

    if args.scan:
        return 0

    try:
        sensor = _init_sensor(args.address)
    except Exception as exc:
        print(str(exc))
        return 2

    period_s = 1.0 / max(0.5, float(args.hz))
    print(f"Reading VL53L0X at {_format_addr(args.address)} ({args.hz:.1f} Hz). Ctrl+C to stop.")

    consecutive_errors = 0
    try:
        while True:
            t = time.time()
            try:
                mm = int(sensor.range)
                consecutive_errors = 0
                print(f"{t:.3f}  range_mm={mm}")
            except Exception as exc:
                consecutive_errors += 1
                print(f"{t:.3f}  read_error={type(exc).__name__}: {exc}")
                if consecutive_errors >= 10:
                    print("Too many consecutive read errors; stopping.")
                    return 3

            time.sleep(period_s)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
