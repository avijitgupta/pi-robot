# Raspberry Pi Zero 2 W – 2WD Robot Base

A stable baseline for a **2-wheel drive robot** using a Raspberry Pi Zero 2 W and a TB6612FNG motor driver.

This repo is currently focused on **reliable drivetrain + teleop**. Sensors/autonomy are the next phase.

---

## Progress (Current State)

- Deterministic TB6612 control via a reusable motor module: [src/motor_controller.py](src/motor_controller.py)
- Wi‑Fi teleop web UI (phone friendly) with:
    - Deadman stop on the server
    - Continuous “hold to drive” controls (keeps motion going while pressed)
    - On-page deadman status indicator (low-frequency polling)
    - Control mode toggle: joystick vs autonomous
    - Safe shutdown: motors stop + TB6612 standby on exit
    - File: [src/teleop_web.py](src/teleop_web.py)
- Interactive keyboard teleop (separate script): [src/teleop_interactive.py](src/teleop_interactive.py)


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
* Deadman safety stop (server-side)
* Hold-to-drive buttons (continuous motion while held)
* Safer stop on exit (stop + standby)
* Less jerky motion via a simple slew-rate limiter in the motor controller

---

## Repository Structure

```
src/
    motor_controller.py
    teleop_interactive.py
    teleop_web.py
    readme.md
```

---

## Roadmap

### Phase 2 – Control Quality

* Left/right speed trim
* Straight-line calibration
* Acceleration ramping (implemented as a basic slew-rate limiter; tune/iterate)

### Phase 3 – Sensors

* Add proximity sensor support (ultrasonic / ToF)
* Obstacle stop / slow-down logic

---

## Autonomous Mode (Web UI)

The web UI now includes a **Control mode** toggle:

- **Joystick**: normal teleop.
- **Autonomous**: runs a conservative background “wander” loop (forward + turn) using the same motor controller.

Autonomy is designed to be extended with real sensors later; the implementation lives in:

- [src/autonomous.py](src/autonomous.py)

### Autonomy Tuning

Optional environment variables:

- `AUTO_SPEED` (0..1, default `0.25`)
- `AUTO_TURN` (0..1, default `0.55`)
- `AUTO_FWD_S` (seconds, default `1.2`)
- `AUTO_TURN_S` (seconds, default `0.55`)
- `AUTO_JITTER_S` (seconds, default `0.15`)

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
python3 src/teleop_web.py
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
MAX_PWM=0.6 python3 src/teleop_web.py
```

Other useful env vars:

- `DEADMAN_S` (seconds, default `0.35`)
- `LEFT_MULT`, `RIGHT_MULT` (motor trim)
- `TELEOP_TOKEN` (optional auth)

### Optional: Simple token

```bash
TELEOP_TOKEN=changeme python3 src/teleop_web.py
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


