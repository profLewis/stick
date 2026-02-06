# main.py -- stick: piezo-triggered buzzer tones + MIDI output
#
# Hardware: Pico 2 + Seengreat Pico Expansion Mini Rev 2.1
#
# Sensors via TCA9548A digital mux (supports daisy-chaining 2 hubs):
#   TCA9548A hub(s) on Grove 4 (SoftI2C: GP16 SDA, GP17 SCL)
#   Each channel carries up to 2 sensor D0 lines:
#     SDA wire = sensor A (D0), SCL wire = sensor B (D0)
#   D0 is active-low: 0 = hit, 1 = idle
#
# Hub addresses: 0x70 (default), 0x71 (A0 high) for second hub
# Max: 2 hubs x 8 channels x 2 sensors = 32 sensors
#
# Buzzer: PWM on GP18 (passive, BUZZER_SW jumper must be ON)
# Audio:  PWM on GP19 (audio jack output)
# MIDI:   UART0 TX on GP0 (Grove 1), 31250 baud
# RGB:    WS2812 on GP22 (status indicator)

import machine
import time
import neopixel
from lib.notes import freq, midi_note
from lib.midi import MidiOut
from lib.tca9548a import TCA9548A

# ---- Hub Configuration ----
# TCA9548A I2C addresses. Default is 0x70.
# For a second hub, set A0 high -> 0x71.
# Up to 8 hubs (0x70-0x77) by setting A0/A1/A2.
HUB_ADDRESSES = [0x70]  # Add 0x71 for a second hub

# ---- Sensor Configuration ----
# Each entry: (hub_addr, tca_channel, pin_index, note_name)
#   hub_addr:  I2C address of the TCA9548A (0x70, 0x71, etc.)
#   tca_channel: 0-7
#   pin_index: 0 = SDA wire (sensor A), 1 = SCL wire (sensor B)
#   note_name: must match a WAV filename stem
#
# Add/remove entries here when connecting more sensors.
SENSORS = [
    # Hub 0x70
    (0x70, 0, 0, "C4"),    # Hub 1, Ch 0, sensor A -> C4  (261 Hz)
    (0x70, 0, 1, "E4"),    # Hub 1, Ch 0, sensor B -> E4  (329 Hz)
    (0x70, 1, 0, "G4"),    # Hub 1, Ch 1, sensor A -> G4  (392 Hz)
    (0x70, 1, 1, "C5"),    # Hub 1, Ch 1, sensor B -> C5  (523 Hz)
    # Uncomment to add more on hub 0x70:
    # (0x70, 2, 0, "E5"),  # Hub 1, Ch 2, sensor A
    # (0x70, 2, 1, "G5"),  # Hub 1, Ch 2, sensor B
    #
    # Uncomment for second hub at 0x71 (set A0 high on the board):
    # (0x71, 0, 0, "A4"),  # Hub 2, Ch 0, sensor A
    # (0x71, 0, 1, "B4"),  # Hub 2, Ch 0, sensor B
]

# ---- Timing ----
TONE_DURATION_MS = 200
DEBOUNCE_MS = 50
POLL_MS = 5

# ---- Pin setup ----
MUX_SDA = 16   # Grove 4 pin 1
MUX_SCL = 17   # Grove 4 pin 2
BUZZER_PIN = 18
AUDIO_PIN = 19
RGB_PIN = 22

# ---- TCA9548A hubs ----
hubs = {}
for addr in HUB_ADDRESSES:
    hubs[addr] = TCA9548A(sda_pin=MUX_SDA, scl_pin=MUX_SCL, address=addr)

# ---- Buzzer + audio jack ----
buzzer = machine.PWM(machine.Pin(BUZZER_PIN))
buzzer.duty_u16(0)
audio = machine.PWM(machine.Pin(AUDIO_PIN))
audio.duty_u16(0)

# ---- RGB LED ----
rgb = neopixel.NeoPixel(machine.Pin(RGB_PIN), 1)


def set_rgb(r, g, b):
    rgb[0] = (r, g, b)
    rgb.write()


# ---- MIDI output ----
midi = MidiOut(uart_id=0, tx_pin=0, channel=0)


# ---- Tone helpers ----
def play_tone(frequency_hz, duration_ms):
    """Play a tone on buzzer and audio jack simultaneously."""
    buzzer.freq(int(frequency_hz))
    audio.freq(int(frequency_hz))
    buzzer.duty_u16(32768)
    audio.duty_u16(32768)
    time.sleep_ms(duration_ms)
    buzzer.duty_u16(0)
    audio.duty_u16(0)


def handle_hit(sensor):
    """Handle a sensor trigger: play tone + send MIDI."""
    hub_addr, ch, pin_idx, note_name = sensor
    f = freq(note_name)
    mn = midi_note(note_name)
    label = "0x{:02x}:Ch{}:{}".format(hub_addr, ch, "A" if pin_idx == 0 else "B")
    print("{} -> {} ({} Hz, MIDI {})".format(label, note_name, f, mn))

    set_rgb(0, 20, 0)

    if mn is not None:
        midi.note_on(mn, 127)

    if f is not None:
        play_tone(f, TONE_DURATION_MS)

    if mn is not None:
        midi.note_off(mn)

    set_rgb(0, 0, 0)


def read_sensor(sensor):
    """Read a single sensor's D0 state. Returns 1=hit, 0=idle."""
    hub_addr, ch, pin_idx, _ = sensor
    mux = hubs[hub_addr]
    a, b = mux.read_pins(ch)
    raw = a if pin_idx == 0 else b
    return 1 if raw == 0 else 0  # invert: active-low


# ---- Sensor status report ----
def report_sensors():
    """Read and report the state of all configured sensors."""
    hub_count = len(set(h for h, _, _, _ in SENSORS))
    ch_count = len(set((h, c) for h, c, _, _ in SENSORS))
    print()
    print("== Sensor Status ==")
    print("Configured: {} sensors on {} channels across {} hub(s)".format(
        len(SENSORS), ch_count, hub_count))
    print()
    for sensor in SENSORS:
        hub_addr, ch, pin_idx, note_name = sensor
        val = read_sensor(sensor)
        state = "TRIGGERED" if val else "IDLE"
        ab = "A(SDA)" if pin_idx == 0 else "B(SCL)"
        f = freq(note_name)
        mn = midi_note(note_name)
        print("  [0x{:02x}] Ch {} {} -> {:<3s} {:>7.1f} Hz  MIDI {:>3d}  [{}]".format(
            hub_addr, ch, ab, note_name, f, mn, state))
    print()


# ---- Detect hubs ----
from machine import SoftI2C, Pin
_i2c = SoftI2C(sda=Pin(MUX_SDA), scl=Pin(MUX_SCL), freq=50000)
_found = _i2c.scan()
print()
print("I2C bus scan: {}".format(["0x{:02x}".format(a) for a in _found]))
for addr in HUB_ADDRESSES:
    if addr in _found:
        print("  Hub 0x{:02x}: OK".format(addr))
    else:
        print("  Hub 0x{:02x}: NOT FOUND".format(addr))

# ---- Boot ----
set_rgb(0, 0, 10)
report_sensors()
set_rgb(0, 0, 0)
print("stick ready -- {} sensors active".format(len(SENSORS)))

# ---- Main loop ----
# State: {(hub, ch, pin): (prev_value, last_hit_ms)}
state = {}

# Initialize with current readings
for sensor in SENSORS:
    hub_addr, ch, pin_idx, _ = sensor
    val = read_sensor(sensor)
    state[(hub_addr, ch, pin_idx)] = (val, 0)

while True:
    now = time.ticks_ms()

    for sensor in SENSORS:
        hub_addr, ch, pin_idx, note_name = sensor
        key = (hub_addr, ch, pin_idx)

        current = read_sensor(sensor)
        prev, last_ms = state[key]

        # Rising edge with debounce
        if current and not prev:
            if time.ticks_diff(now, last_ms) > DEBOUNCE_MS:
                handle_hit(sensor)
                state[key] = (current, now)
            else:
                state[key] = (current, last_ms)
        else:
            state[key] = (current, last_ms)

    time.sleep_ms(POLL_MS)
