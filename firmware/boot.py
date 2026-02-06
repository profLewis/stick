# boot.py -- Mount SD card and report disk space
#
# Seengreat Pico Expansion Mini Rev 2.1
# SD card on SPI1: GP14(SCK), GP15(MOSI), GP12(MISO), GP13(CS)

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
        baudrate=1_000_000,
        polarity=0,
        phase=0,
        sck=machine.Pin(14),
        mosi=machine.Pin(15),
        miso=machine.Pin(12),
    )
    cs = machine.Pin(13, machine.Pin.OUT, value=1)
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
