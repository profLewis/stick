# boot.py -- Mount SD card and report disk space
#
# Seengreat Pico Expansion Mini Rev 2.1
# SD card on SPI1: GP10(SCK), GP11(MOSI), GP12(MISO), GP15(CS)

import machine
import os


def _disk_info(path):
    """Return (total_kb, free_kb) for a mounted filesystem."""
    stat = os.statvfs(path)
    block_size = stat[0]
    total_blocks = stat[2]
    free_blocks = stat[3]
    total_kb = (block_size * total_blocks) // 1024
    free_kb = (block_size * free_blocks) // 1024
    return total_kb, free_kb


# --- Report internal flash ---
total, free = _disk_info("/")
print("Flash: {} KB total, {} KB free".format(total, free))

# --- Mount SD card ---
sd_mounted = False
try:
    from lib.sdcard import SDCard

    spi = machine.SPI(
        1,
        baudrate=400_000,
        polarity=0,
        phase=0,
        sck=machine.Pin(10),
        mosi=machine.Pin(11),
        miso=machine.Pin(12),
    )
    cs = machine.Pin(15, machine.Pin.OUT, value=1)
    sd = SDCard(spi, cs)
    os.mount(sd, "/sd")
    sd_mounted = True

    total, free = _disk_info("/sd")
    print("SD:    {} KB total, {} KB free".format(total, free))

    try:
        wavs = [f for f in os.listdir("/sd") if f.endswith(".wav")]
        print("WAV files on SD: {}".format(len(wavs)))
    except OSError:
        print("WAV files on SD: (unable to list)")

except Exception as e:
    print("SD card mount FAILED:", e)
    print("Continuing without SD card.")


# --- Boot test tune: Tetris theme (Korobeiniki) ---
# Plays through buzzer (GP18) and audio jack (GP19)
import time

# (frequency_hz, duration_ms)  0 = rest
BPM = 150
Q = 60000 // BPM     # quarter note
E = Q // 2           # eighth note
H = Q * 2            # half note
DQ = Q + E           # dotted quarter

TETRIS = [
    (659, Q),    # E5
    (494, E),    # B4
    (523, E),    # C5
    (587, Q),    # D5
    (523, E),    # C5
    (494, E),    # B4
    (440, Q),    # A4
    (440, E),    # A4
    (523, E),    # C5
    (659, Q),    # E5
    (587, E),    # D5
    (523, E),    # C5
    (494, DQ),   # B4
    (523, E),    # C5
    (587, Q),    # D5
    (659, Q),    # E5
    (523, Q),    # C5
    (440, Q),    # A4
    (440, H),    # A4
]
GAP_MS = 20

try:
    buzzer = machine.PWM(machine.Pin(18))
    audio = machine.PWM(machine.Pin(19))
    print("Boot tune: Tetris theme")

    for freq, dur in TETRIS:
        if freq > 0:
            buzzer.freq(freq)
            audio.freq(freq)
            buzzer.duty_u16(32768)
            audio.duty_u16(32768)
            time.sleep_ms(dur - GAP_MS)
            buzzer.duty_u16(0)
            audio.duty_u16(0)
            time.sleep_ms(GAP_MS)
        else:
            time.sleep_ms(dur)

    buzzer.deinit()
    audio.deinit()
except Exception as e:
    print("Boot tune failed:", e)
