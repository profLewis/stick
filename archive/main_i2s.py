# main.py — stick: piezo sensor triggered sounds
# Hardware: Pico H + Waveshare Pico Audio HAT + Grove Shield for Pi Pico v1.0
#
# Sensors:
#   S1a digital -> GP16 (Grove D16 pin 1)
#   S1b digital -> GP17 (Grove D16 pin 2)
#
# I2S (Pico Audio HAT, PCM5101A):
#   DATA -> GP26, BCK -> GP27, LRCK -> GP28
#
# Generates two different tones at startup so no WAV files needed.
# S1a -> 440 Hz (A4), S1b -> 523 Hz (C5)

import machine
import math
import array
import time

# --- Pin config ---
I2S_SCK = 27        # BCK
I2S_WS = 28         # LRCK (must be SCK + 1)
I2S_SD = 26         # DATA
SAMPLE_RATE = 22050

S1A_PIN = 16
S1B_PIN = 17

# --- Generate a sine tone as int16 samples ---
def make_tone(freq, duration_ms):
    n = SAMPLE_RATE * duration_ms // 1000
    buf = array.array('h', (
        int(30000 * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
        for i in range(n)
    ))
    return buf

print("Generating tones...")
tone_a = make_tone(440, 300)  # A4, 300ms
tone_b = make_tone(523, 300)  # C5, 300ms
silence = bytearray(1024)

# --- Sensor inputs (pull-down: idle LOW, trigger HIGH) ---
# If your sensors are active-low, change PULL_DOWN to PULL_UP
# and invert the edge detection below.
s1a = machine.Pin(S1A_PIN, machine.Pin.IN, machine.Pin.PULL_DOWN)
s1b = machine.Pin(S1B_PIN, machine.Pin.IN, machine.Pin.PULL_DOWN)

# --- I2S audio output ---
audio = machine.I2S(
    0,
    sck=machine.Pin(I2S_SCK),
    ws=machine.Pin(I2S_WS),
    sd=machine.Pin(I2S_SD),
    mode=machine.I2S.TX,
    bits=16,
    format=machine.I2S.MONO,
    rate=SAMPLE_RATE,
    ibuf=4096,
)

print("stick ready — tap a sensor")

prev_a = 0
prev_b = 0

while True:
    a = s1a.value()
    b = s1b.value()

    # Rising edge detection
    if a and not prev_a:
        print("S1a hit")
        audio.write(tone_a)
        audio.write(silence)

    if b and not prev_b:
        print("S1b hit")
        audio.write(tone_b)
        audio.write(silence)

    prev_a = a
    prev_b = b
    time.sleep_ms(5)
