# main.py -- stick: piezo-triggered buzzer tones + MIDI output
#
# Hardware: Pico 2 + Seengreat Pico Expansion Mini Rev 2.1
#
# Sensors via I2C:
#   TCA9548A I2C hub on Grove 6 (I2C0: GP20 SDA, GP21 SCL)
#   S1a, S1b digital signals on TCA9548A channel 0
#   via PCF8574 GPIO expander (addr 0x20): S1a = P0, S1b = P1
#
# Buzzer: PWM on GP18 (passive, BUZZER_SW jumper must be ON)
# MIDI:   UART0 TX on GP0 (Grove 1), 31250 baud
# RGB:    WS2812 on GP22 (status indicator)

import machine
import time
import neopixel
from lib.notes import freq, midi_note
from lib.midi import MidiOut
from lib.tca9548a import TCA9548A

# ---- Configuration ----
SENSOR_MAP = {
    "S1a": "A4",   # PCF8574 P0 -> A4 (440 Hz, MIDI 69)
    "S1b": "C5",   # PCF8574 P1 -> C5 (523 Hz, MIDI 72)
}
TONE_DURATION_MS = 300
DEBOUNCE_MS = 50
POLL_MS = 5

# ---- I2C addresses ----
TCA9548A_ADDR = 0x70
PCF8574_ADDR = 0x20    # GPIO expander behind TCA9548A channel 0
SENSOR_CHANNEL = 0     # TCA9548A channel for sensors

# ---- Pin setup ----
I2C_SDA = 20   # Grove 6 pin 1
I2C_SCL = 21   # Grove 6 pin 2
BUZZER_PIN = 18
RGB_PIN = 22

# ---- I2C bus + TCA9548A ----
i2c = machine.I2C(0, sda=machine.Pin(I2C_SDA), scl=machine.Pin(I2C_SCL),
                   freq=100_000)
mux = TCA9548A(i2c, TCA9548A_ADDR)

# Select sensor channel and verify expander is present
mux.select(SENSOR_CHANNEL)
devices = i2c.scan()
if PCF8574_ADDR in devices:
    print("PCF8574 found at 0x{:02x} on TCA9548A ch {}".format(
        PCF8574_ADDR, SENSOR_CHANNEL))
else:
    print("WARNING: PCF8574 not found on TCA9548A ch {}".format(SENSOR_CHANNEL))
    print("  Devices on bus: {}".format(
        ["0x{:02x}".format(a) for a in devices]))

# ---- Buzzer ----
buzzer = machine.PWM(machine.Pin(BUZZER_PIN))
buzzer.duty_u16(0)

# ---- RGB LED (single WS2812) ----
rgb = neopixel.NeoPixel(machine.Pin(RGB_PIN), 1)


def set_rgb(r, g, b):
    rgb[0] = (r, g, b)
    rgb.write()


# ---- MIDI output ----
midi = MidiOut(uart_id=0, tx_pin=0, channel=0)


# ---- Sensor reading via I2C ----
def read_sensors():
    """Read S1a and S1b from PCF8574 via TCA9548A.

    PCF8574 pins are active-low when used as inputs (pulled high internally).
    A sensor trigger pulls the pin LOW, so we invert: triggered = 1.
    Returns (s1a, s1b) as 0 or 1.
    """
    mux.select(SENSOR_CHANNEL)
    try:
        data = i2c.readfrom(PCF8574_ADDR, 1)
        bits = data[0]
        s1a = 1 if not (bits & 0x01) else 0  # P0, active-low
        s1b = 1 if not (bits & 0x02) else 0  # P1, active-low
        return s1a, s1b
    except OSError:
        return 0, 0


# ---- Buzzer helpers ----
def buzzer_play(frequency_hz, duration_ms):
    """Play a tone on the passive buzzer via PWM."""
    buzzer.freq(int(frequency_hz))
    buzzer.duty_u16(32768)  # 50% duty cycle
    time.sleep_ms(duration_ms)
    buzzer.duty_u16(0)


def handle_hit(sensor_name):
    """Handle a sensor trigger: play buzzer tone + send MIDI."""
    note_name = SENSOR_MAP.get(sensor_name)
    if not note_name:
        return

    f = freq(note_name)
    mn = midi_note(note_name)
    print("{} -> {} ({} Hz, MIDI {})".format(sensor_name, note_name, f, mn))

    set_rgb(0, 20, 0)

    if mn is not None:
        midi.note_on(mn, 127)

    if f is not None:
        buzzer_play(f, TONE_DURATION_MS)

    if mn is not None:
        midi.note_off(mn)

    set_rgb(0, 0, 0)


# ---- Boot indicator ----
set_rgb(0, 0, 10)
time.sleep_ms(200)
set_rgb(0, 0, 0)
print("stick ready -- tap a sensor")

# ---- Main loop ----
prev_a = 0
prev_b = 0
last_a_ms = 0
last_b_ms = 0

while True:
    a, b = read_sensors()
    now = time.ticks_ms()

    if a and not prev_a:
        if time.ticks_diff(now, last_a_ms) > DEBOUNCE_MS:
            handle_hit("S1a")
            last_a_ms = now

    if b and not prev_b:
        if time.ticks_diff(now, last_b_ms) > DEBOUNCE_MS:
            handle_hit("S1b")
            last_b_ms = now

    prev_a = a
    prev_b = b
    time.sleep_ms(POLL_MS)
