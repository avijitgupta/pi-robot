Below is a **README-style version** of your design doc, rewritten for a repo audience, with **clearer structure and improved ASCII diagrams** (still plain text / Markdown-friendly, no RTF).

You can drop this directly into `README.md`.

---

# Raspberry Pi Zero 2 W – 2WD Robot Base

A stable, production-quality baseline for a **2-wheel drive robot** using a Raspberry Pi Zero 2 W and a TB6612FNG motor driver.
This repository establishes a **reliable drivetrain and teleoperation layer** before adding sensors, autonomy, or AI.

---

## Project Goals

* Build a **reliable 2WD robot base**
* Separate motor power from logic power
* Achieve deterministic motor control (no brownouts, no random stops)
* Provide interactive keyboard teleoperation
* Create a clean foundation for future sensors and vision

This phase intentionally **excludes sensors and camera** to focus on drivetrain correctness.

---

## Hardware Overview

### Core Components

* Raspberry Pi Zero 2 W
* TB6612FNG dual H-bridge motor driver
* 2× DC TT motors (2WD chassis)
* 4×AA battery pack (~6V) for motors
* USB power bank for Raspberry Pi

### Key Design Principle

**Motors are never powered by the Raspberry Pi.**
The Pi provides *control only*.

---

## Power Architecture (Critical)

### Separation of Power Domains

```
           USB Power Bank
                 |
                 v
        +-------------------+
        | Raspberry Pi Zero |
        |   3.3V / GPIO    |
        +-------------------+
                 |
                 |  (logic + control)
                 v
        +-------------------+
        |    TB6612FNG      |
        |  Logic (VCC)     |
        +-------------------+
                 |
                 |  (motor current)
                 v
        +-------------------+
        |    DC Motors      |
        +-------------------+
                 ^
                 |
          4×AA Battery Pack
```

### Power Connections

* Battery +  → TB6612FNG `VM`
* Battery −  → TB6612FNG `GND`
* Pi 3.3V   → TB6612FNG `VCC`
* Pi GND    → TB6612FNG `GND`

Important rules:

* Battery − and Pi GND **must be common**
* Never power motors from Pi 5V or 3.3V
* Never route motor current through the Pi

---

## TB6612FNG Enable (STBY) Strategy

### Final Decision

* `STBY` is **explicitly controlled via GPIO**

### Why

* Floating or loosely connected STBY caused intermittent shutdowns
* Explicit control made motor behavior deterministic
* Every motor-driving script asserts STBY HIGH

---

## GPIO Pin Mapping (Final, Verified)

### Left Motor (Motor A)

| Function | TB6612FNG | Pi GPIO (BCM) | Pi Pin |
| -------- | --------- | ------------- | ------ |
| PWM      | PWMA      | GPIO18        | Pin 12 |
| Dir      | AIN1      | GPIO23        | Pin 16 |
| Dir      | AIN2      | GPIO24        | Pin 18 |

### Right Motor (Motor B)

Note: Motor polarity was reversed and corrected in software.

| Function | TB6612FNG | Pi GPIO (BCM) | Pi Pin |
| -------- | --------- | ------------- | ------ |
| PWM      | PWMB      | GPIO13        | Pin 33 |
| Dir      | BIN1      | GPIO6         | Pin 31 |
| Dir      | BIN2      | GPIO5         | Pin 29 |

### Standby / Enable

| Function | TB6612FNG | Pi GPIO (BCM) | Pi Pin |
| -------- | --------- | ------------- | ------ |
| Enable   | STBY      | GPIO25        | Pin 22 |

---

## Wiring Diagram (ASCII)

### Logic + Power

```
Raspberry Pi Zero 2 W                 TB6612FNG
---------------------                 ---------

3.3V  (Pin 1)   ------------------->  VCC
GND   (Pin 6)   -----------+------->  GND
                            |
Battery -  -----------------+
Battery +  --------------------------> VM
```

### Motor Control Signals

```
Left Motor (A)
---------------
GPIO18  --------------------------->  PWMA
GPIO23  --------------------------->  AIN1
GPIO24  --------------------------->  AIN2

Right Motor (B)
---------------
GPIO13  --------------------------->  PWMB
GPIO6   --------------------------->  BIN1
GPIO5   --------------------------->  BIN2

Enable
------
GPIO25  --------------------------->  STBY
```

### Motors

```
Left DC Motor   -------------------->  AO1 / AO2
Right DC Motor  -------------------->  BO1 / BO2
```

---

## Software Architecture

### Language & Libraries

* Python 3
* gpiozero

The `gpiozero.Motor` abstraction is **not used** due to:

* Poor control over enable behavior
* Ambiguous PWM handling
* Reduced debuggability

### Control Model

* PWM on `PWMA` / `PWMB`
* Digital direction pins (`AINx`, `BINx`)
* Explicit STBY enable
* Software dead-man stop

---

## Known Issues & Fixes

| Issue                   | Root Cause              | Resolution               |
| ----------------------- | ----------------------- | ------------------------ |
| Motors stop randomly    | STBY floating           | GPIO-controlled STBY     |
| Robot spins             | Motor polarity mismatch | BIN1/BIN2 swapped        |
| Teleop no motion        | STBY not asserted       | Added STBY to teleop     |
| SSH keyboard unreliable | No raw TTY              | PTY + fallback teleop    |
| Robot drifts            | Motor speed mismatch    | Planned trim calibration |

---

## Current Capabilities

* Forward / backward motion
* Left / right turns
* Interactive keyboard teleoperation
* Wi‑Fi teleoperation from phone/browser (see below)
* Stable power behavior
* Deterministic motor response
* Clean, documented wiring

---

## Repository Structure (Suggested)

```
robo/
├── drive_test.py          # Deterministic motion test
├── teleop_interactive.py  # Keyboard control
├── teleop_web.py          # Wi‑Fi control (browser/iOS)
├── motor.py               # Future MotorController class
├── sensors/
│   └── vl53l0x.py
├── vision/
│   └── camera.py
└── docs/
    └── design.md
```

---

## Roadmap

### Phase 2 – Control Quality

* Left/right speed trim
* Straight-line calibration
* Acceleration ramping

### Phase 3 – Sensors

* VL53L0X distance sensor
* Obstacle stop / slow-down logic

### Phase 4 – Vision & AI

* Camera integration
* Vision-based behaviors
* Web or phone-based control UI

---

## Wi‑Fi Teleop (iOS / Browser)

This repo includes a small web server that exposes a touch joystick UI and a simple HTTP API.

### Install

```bash
sudo apt update
sudo apt install -y python3-flask
```

### Run

```bash
python3 teleop_web.py
```

Then on your iPhone (same Wi‑Fi), open Safari to:

```
http://<pi-ip>:8080
```

Tip: Safari → Share → **Add to Home Screen** for a full-screen controller.

### Safety / Tuning

- The server has a deadman stop (robot stops if commands stop arriving).
- Set a conservative max PWM (recommended on a phone):

```bash
MAX_PWM=0.6 python3 teleop_web.py
```

### Optional: Simple token

```bash
TELEOP_TOKEN=changeme python3 teleop_web.py
```

Then open:

```
http://<pi-ip>:8080/?token=changeme
```

---

## Final Notes

This project establishes a **solid, production-quality drivetrain baseline**:

* Deterministic
* Debuggable
* Extensible

With this foundation complete, adding autonomy, sensors, and AI becomes straightforward software work.


