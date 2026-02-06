# main.py -- stick: piezo-triggered buzzer tones + MIDI output
#
# Hardware: Pico 2 + Seengreat Pico Expansion Mini Rev 2.1
#
# Sensor modes:
#   Direct GPIO: D0 wired to a Pico GPIO pin (active-HIGH, needs pull-down)
#   TCA9548A:    D0 via I2C mux on Grove 4 (SoftI2C: GP16 SDA, GP17 SCL)
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

# ---- Load configuration from config.py ----
from config import HUB_ADDRESSES, SENSORS, TONE_DURATION_MS, DEBOUNCE_MS, POLL_MS

# ---- Pin setup ----
MUX_SDA = 16   # Grove 4 pin 1
MUX_SCL = 17   # Grove 4 pin 2
BUZZER_PIN = 18
AUDIO_PIN = 19
RGB_PIN = 22

# ---- TCA9548A hubs (only if configured) ----
hubs = {}
if HUB_ADDRESSES:
    from lib.tca9548a import TCA9548A
    for addr in HUB_ADDRESSES:
        hubs[addr] = TCA9548A(sda_pin=MUX_SDA, scl_pin=MUX_SCL, address=addr)

# ---- GPIO sensor pins (active-HIGH, pull-down) ----
gpio_pins = {}
for sensor in SENSORS:
    if sensor[0] == "gpio":
        pin_num = sensor[1]
        if pin_num not in gpio_pins:
            gpio_pins[pin_num] = machine.Pin(pin_num, machine.Pin.IN, machine.Pin.PULL_DOWN)

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

# ---- Animation timing ----
ANIM_STEP_MS = 10


# ---- Tone helpers ----
def play_tone_with_rgb(frequency_hz, duration_ms, midi_num):
    """Play a tone on buzzer + audio jack with animated RGB.

    Red flash on hit, then green=note identity, blue=fading intensity.
    """
    # Map note to green channel (C4=60 -> 0, E6=88 -> 255)
    green = min(255, max(0, (midi_num - 60) * 9))

    buzzer.freq(int(frequency_hz))
    audio.freq(int(frequency_hz))
    buzzer.duty_u16(32768)
    audio.duty_u16(32768)

    # Red flash on initial impact (20ms)
    set_rgb(255, 0, 0)
    time.sleep_ms(min(20, duration_ms))
    remaining = duration_ms - 20

    if remaining > 0:
        steps = max(1, remaining // ANIM_STEP_MS)
        for i in range(steps):
            # Blue = intensity, fades from 255 to 0
            blue = 255 - ((i * 255) // steps)
            set_rgb(0, green, blue)
            time.sleep_ms(ANIM_STEP_MS)

    buzzer.duty_u16(0)
    audio.duty_u16(0)
    set_rgb(0, 0, 0)


def handle_hit(sensor):
    """Handle a sensor trigger: play tone + send MIDI + animate RGB."""
    mode, ch, pin_idx, note_name = sensor
    f = freq(note_name)
    mn = midi_note(note_name)
    if mode == "gpio":
        label = "GPIO{}".format(ch)
    else:
        label = "0x{:02x}:Ch{}:{}".format(mode, ch, "A" if pin_idx == 0 else "B")
    print("{} -> {} ({} Hz, MIDI {})".format(label, note_name, f, mn))

    if mn is not None:
        midi.note_on(mn, 127)

    if f is not None and mn is not None:
        play_tone_with_rgb(f, TONE_DURATION_MS, mn)
    elif f is not None:
        play_tone_with_rgb(f, TONE_DURATION_MS, 60)

    if mn is not None:
        midi.note_off(mn)

    set_rgb(0, 0, 0)


def read_sensor(sensor):
    """Read a single sensor's D0 state. Returns 1=hit, 0=idle."""
    mode, ch, pin_idx, _ = sensor
    if mode == "gpio":
        # Direct GPIO: active-HIGH (D0 goes HIGH on hit)
        return gpio_pins[ch].value()
    else:
        # TCA9548A: active-LOW (D0 goes LOW on hit)
        mux = hubs[mode]
        a, b = mux.read_pins(ch)
        raw = a if pin_idx == 0 else b
        return 1 if raw == 0 else 0  # invert: active-low


# ---- Sensor status report ----
def report_sensors():
    """Read and report the state of all configured sensors."""
    gpio_count = sum(1 for s in SENSORS if s[0] == "gpio")
    hub_count = len(set(h for h, _, _, _ in SENSORS if h != "gpio"))
    print()
    print("== Sensor Status ==")
    print("Configured: {} sensors ({} GPIO, {} hub)".format(
        len(SENSORS), gpio_count, len(SENSORS) - gpio_count))
    print()
    for sensor in SENSORS:
        mode, ch, pin_idx, note_name = sensor
        val = read_sensor(sensor)
        state = "TRIGGERED" if val else "IDLE"
        f = freq(note_name)
        mn = midi_note(note_name)
        if mode == "gpio":
            print("  GPIO{:<3d}       -> {:<3s} {:>7.1f} Hz  MIDI {:>3d}  [{}]".format(
                ch, note_name, f, mn, state))
        else:
            ab = "A(SDA)" if pin_idx == 0 else "B(SCL)"
            print("  [0x{:02x}] Ch {} {} -> {:<3s} {:>7.1f} Hz  MIDI {:>3d}  [{}]".format(
                mode, ch, ab, note_name, f, mn, state))
    print()


# ---- Detect hubs (only if configured) ----
if HUB_ADDRESSES:
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
# State: {(mode, ch, pin): (prev_value, last_hit_ms)}
state = {}
breath_counter = 0

# Idle breathing: dim blue pulsing
BREATH_TABLE = [1, 2, 3, 5, 7, 9, 11, 13, 14, 15, 15, 14, 13, 11, 9, 7, 5, 3, 2, 1]

# Initialize with current readings
for sensor in SENSORS:
    mode, ch, pin_idx, _ = sensor
    val = read_sensor(sensor)
    state[(mode, ch, pin_idx)] = (val, 0)

while True:
    now = time.ticks_ms()
    hit_this_cycle = False

    for sensor in SENSORS:
        mode, ch, pin_idx, note_name = sensor
        key = (mode, ch, pin_idx)

        current = read_sensor(sensor)
        prev, last_ms = state[key]

        # Rising edge with debounce
        if current and not prev:
            if time.ticks_diff(now, last_ms) > DEBOUNCE_MS:
                handle_hit(sensor)
                state[key] = (current, now)
                hit_this_cycle = True
            else:
                state[key] = (current, last_ms)
        else:
            state[key] = (current, last_ms)

    # Idle breathing animation (dim blue pulse)
    if not hit_this_cycle:
        breath_counter = (breath_counter + 1) % (len(BREATH_TABLE) * 10)
        idx = breath_counter // 10
        b = BREATH_TABLE[idx]
        set_rgb(0, 0, b)

    time.sleep_ms(POLL_MS)
