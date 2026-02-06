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


# --- Boot test tunes ---
# Plays through buzzer (GP18) and audio jack (GP19)
import time

# (frequency_hz, duration_ms)  0 = rest
BPM_T = 150
Q_T = 60000 // BPM_T
E_T = Q_T // 2
H_T = Q_T * 2
DQ_T = Q_T + E_T

TETRIS = [
    (659, Q_T),    # E5
    (494, E_T),    # B4
    (523, E_T),    # C5
    (587, Q_T),    # D5
    (523, E_T),    # C5
    (494, E_T),    # B4
    (440, Q_T),    # A4
    (440, E_T),    # A4
    (523, E_T),    # C5
    (659, Q_T),    # E5
    (587, E_T),    # D5
    (523, E_T),    # C5
    (494, DQ_T),   # B4
    (523, E_T),    # C5
    (587, Q_T),    # D5
    (659, Q_T),    # E5
    (523, Q_T),    # C5
    (440, Q_T),    # A4
    (440, H_T),    # A4
]

# "In the Mood" - Glenn Miller, key of Ab major
# Based on MIDI analysis: sax section intro riff
# Swing timing: long=253ms, short=127ms, quarter=380ms
IN_THE_MOOD = [
    # Ascending arpeggio (Ab major chord)
    (415, 253),    # Ab4
    (523, 127),    # C5
    (622, 253),    # Eb5
    # Repeated Ab5 (building tension, on quarter beats)
    (831, 380),    # Ab5
    (831, 380),    # Ab5
    (831, 380),    # Ab5
    (831, 380),    # Ab5
    (831, 380),    # Ab5
    # Chromatic approach
    (784, 127),    # G5
    (831, 253),    # Ab5
    # Descending chromatic line (swing pairs)
    (622, 127),    # Eb5
    (523, 253),    # C5
    (622, 127),    # Eb5
    (587, 253),    # D5
    (554, 127),    # Db5
    (523, 253),    # C5
    (494, 127),    # B4
    (466, 253),    # Bb4
    (415, 760),    # Ab4 (long resolve)
]

# Star Wars Main Theme - John Williams, key of Bb major
# Based on MIDI analysis: trumpet melody
STAR_WARS = [
    # Three triplet pickups
    (466, 190),    # Bb4
    (466, 190),    # Bb4
    (466, 190),    # Bb4
    # Phrase 1: up to F5, quick descent, resolve on Bb5
    (466, 900),    # Bb4 (held)
    (698, 900),    # F5 (held)
    (622, 150),    # Eb5
    (587, 150),    # D5
    (523, 150),    # C5
    (932, 900),    # Bb5 (held)
    # Phrase 2: repeat with shorter F5
    (698, 400),    # F5
    (622, 150),    # Eb5
    (587, 150),    # D5
    (523, 150),    # C5
    (932, 900),    # Bb5 (held)
    # Phrase 3: variation ending on C5
    (698, 300),    # F5
    (622, 150),    # Eb5
    (587, 150),    # D5
    (622, 150),    # Eb5
    (523, 1000),   # C5 (long resolve)
]

TUNES = {"tetris": TETRIS, "mood": IN_THE_MOOD, "starwars": STAR_WARS}
GAP_MS = 20


def _get_boot_tune():
    """Read boot_tune setting from sensors.cfg. Returns 'tetris', 'mood', or 'random'."""
    for path in ["/sd/sensors.cfg", "sensors.cfg"]:
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("boot_tune"):
                        parts = line.split()
                        if len(parts) >= 2:
                            return parts[1].lower()
        except OSError:
            pass
    return "random"


def _pick_tune():
    """Pick a boot tune based on config setting."""
    choice = _get_boot_tune()
    if choice in TUNES:
        return choice, TUNES[choice]
    # Random: use os.urandom for a random bit
    rand = os.urandom(1)[0]
    names = list(TUNES.keys())
    name = names[rand % len(names)]
    return name, TUNES[name]


try:
    buzzer = machine.PWM(machine.Pin(18))
    audio = machine.PWM(machine.Pin(19))
    tune_name, tune_notes = _pick_tune()
    print("Boot tune: {}".format(tune_name))

    for freq, dur in tune_notes:
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
