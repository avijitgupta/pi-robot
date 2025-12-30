import sys, time, termios, tty, select
from gpiozero import PWMOutputDevice, DigitalOutputDevice

# ----- Pin mapping (BCM) -----
# Left motor (A)
PWMA=18; AIN1=23; AIN2=24
# Right motor (B) (direction fixed)
PWMB=13; BIN1=6; BIN2=5
# Standby
STBY=25

# ----- Devices -----
stby = DigitalOutputDevice(STBY)
stby.on()

left_pwm  = PWMOutputDevice(PWMA, frequency=1000)
left_in1  = DigitalOutputDevice(AIN1)
left_in2  = DigitalOutputDevice(AIN2)
right_pwm = PWMOutputDevice(PWMB, frequency=1000)
right_in1 = DigitalOutputDevice(BIN1)
right_in2 = DigitalOutputDevice(BIN2)

speed = 0.25
turn  = 0.25
timeout = 0.6  # deadman stop
left_mult = 1.0
right_mult = 0.87

def stop_all():
    left_pwm.value = 0; left_in1.off(); left_in2.off()
    right_pwm.value = 0; right_in1.off(); right_in2.off()

def forward():
    left_in1.on(); left_in2.off(); left_pwm.value = left_mult * speed
    right_in1.on(); right_in2.off(); right_pwm.value = right_mult * speed

def backward():
    left_in1.off(); left_in2.on(); left_pwm.value = left_mult * speed
    right_in1.off(); right_in2.on(); right_pwm.value = right_mult * speed

def left():
    left_in1.off(); left_in2.on(); left_pwm.value = turn
    right_in1.on(); right_in2.off(); right_pwm.value = turn

def right():
    left_in1.on(); left_in2.off(); left_pwm.value = turn
    right_in1.off(); right_in2.on(); right_pwm.value = turn

def read_key():
    r,_,_ = select.select([sys.stdin], [], [], 0.05)
    if not r:
        return None
    ch = sys.stdin.read(1)

    if ch == ' ': return 'space'
    return ch.lower()

def main():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    print("Interactive Teleop")
    print("W/A/S/D = move | SPACE = stop | Q = quit")
    stop_all()
    last = time.time()

    try:
        while True:
            key = read_key()
            now = time.time()

            if key:
                last = now
                if key == 'q':
                    break
                elif key in ('w'):
                    forward()
                elif key in ('s'):
                    backward()
                elif key in ('a'):
                    left()
                elif key in ('d'):
                    right()
                elif key == 'space':
                    stop_all()

            if now - last > timeout:
                stop_all()

    finally:
        stop_all()
        stby.off()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print("\nStopped.")

if __name__ == "__main__":
    main()
